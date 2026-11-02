# -*- coding: utf-8 -*-
"""
组织入库时用「大数据」DeepSeek 打二级类型 + 业务标签。

流程：读取 lin 目录 JSON → 去重合并 → 并发调用 DeepSeek 标注 → bulk 写入 ES。
支持断点续跑（JSONL 检查点）、按类型/条数试跑、失败回退规则打标。

默认端点：
  BASE_URL = http://172.200.200.4:7000/v1
  MODEL    = dsv4-dspark

用法：
  # 先试跑 5 条（不写 ES）
  py -3 ingest_orgs_deepseek.py --limit 5 --dry-run

  # 只打智库，写检查点，不入库
  py -3 ingest_orgs_deepseek.py --org-type 智库 --limit 100 --workers 4

  # 全量：打标 + 重建索引入库（建议先小流量确认速度）
  py -3 ingest_orgs_deepseek.py --recreate --workers 8 --resume

  # 仅根据已有检查点入库（跳过 LLM）
  py -3 ingest_orgs_deepseek.py --from-checkpoint tagged_ingest.jsonl --recreate

环境变量：
  ORG_TAG_BASE_URL / ORG_TAG_MODEL / ORG_TAG_API_KEY
  ES_HOST / ES_USERNAME / ES_PASSWORD / ORG_INDEX
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Set, Tuple

from ingest_orgs import (
    DEFAULT_DATA_DIR,
    ORG_INDEX,
    bulk_index,
    ensure_index,
    load_all_docs,
)
from org_rule_tagger import tag_org_doc
from tag_orgs_deepseek import (
    TAG_BASE_URL,
    TAG_MODEL,
    ensure_es_mapping,
    load_done_ids,
    tag_one,
)

_HERE = Path(__file__).resolve().parent

# 加载 .env（与其它脚本一致）
for _env_file in (_HERE / ".env", _HERE.parent / "identity-mcp-server" / ".env"):
    if not _env_file.exists():
        continue
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("\"'")
        if k and not os.environ.get(k):
            os.environ[k] = v


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_jsonl(path: Path, obj: dict, lock: Lock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


def _apply_llm_tags(doc: dict, tags: dict, *, model: str) -> dict:
    """把模型结果写回文档字段。"""
    out = dict(doc)
    if tags.get("org_type_l2"):
        out["org_type_l2"] = tags["org_type_l2"]
    out["biz_tags"] = tags.get("biz_tags") or []
    out["tag_method"] = "llm_deepseek"
    out["tag_model"] = model
    out["tag_confidence"] = tags.get("confidence")
    out["tag_reason"] = (tags.get("reason") or "")[:300]
    out["tag_time"] = _utc_now()
    # 不覆盖入库文件名带来的 org_types；仅在模型确认同族时可更新 primary
    l1 = tags.get("org_type_l1")
    if l1 and l1 in (out.get("org_types") or []):
        out["org_type_primary"] = l1
    return out


def _apply_rule_fallback(doc: dict, err: str) -> dict:
    """LLM 失败时回退规则打标，并记录失败原因。"""
    out = tag_org_doc(dict(doc))
    out["tag_method"] = "rule_v1_fallback"
    out["tag_error"] = str(err)[:500]
    out["tag_time"] = _utc_now()
    return out


def _load_checkpoint_tags(path: Path) -> Dict[str, dict]:
    """从检查点恢复已成功的 LLM 标签（按 org_id）。"""
    mapping: Dict[str, dict] = {}
    if not path.exists():
        return mapping
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("error"):
                continue
            oid = obj.get("org_id")
            if not oid:
                continue
            if "org_type_l2" in obj or "biz_tags" in obj:
                mapping[oid] = obj
    return mapping


def estimate_eta(n: int, sec_per_doc: float, workers: int) -> str:
    if n <= 0 or sec_per_doc <= 0 or workers <= 0:
        return "无法估计"
    seconds = n * sec_per_doc / workers
    hours = seconds / 3600
    if hours < 1:
        return f"约 {seconds / 60:.0f} 分钟"
    if hours < 48:
        return f"约 {hours:.1f} 小时"
    return f"约 {hours / 24:.1f} 天（{hours:.0f} 小时）"


def tag_docs_with_llm(
    docs: Dict[str, dict],
    *,
    workers: int = 4,
    checkpoint: Path,
    resume: bool = True,
    fallback_rule: bool = True,
    sleep: float = 0.0,
    limit: Optional[int] = None,
) -> Tuple[Dict[str, dict], Dict[str, int]]:
    """
    并发对 docs 打 LLM 标签，写检查点，返回更新后的 docs 与统计。
    """
    lock = Lock()
    stats = {"ok": 0, "skip": 0, "fallback": 0, "err": 0}

    done_ids: Set[str] = set()
    cached = _load_checkpoint_tags(checkpoint) if resume else {}
    if resume and checkpoint.exists():
        done_ids = set(cached.keys())
        # 也把错误文件里的不算 skip；允许重试失败项
        print(f"resume: 检查点已有成功 {len(done_ids)} 条", flush=True)

    # 先应用检查点中已有标签
    for oid, row in cached.items():
        if oid in docs:
            docs[oid] = _apply_llm_tags(
                docs[oid],
                {
                    "org_type_l1": row.get("org_type_l1"),
                    "org_type_l2": row.get("org_type_l2"),
                    "biz_tags": row.get("biz_tags") or [],
                    "confidence": row.get("confidence"),
                    "reason": row.get("reason"),
                },
                model=row.get("tag_model") or TAG_MODEL,
            )
            stats["skip"] += 1

    pending_ids = [oid for oid in docs.keys() if oid not in done_ids]
    if limit is not None:
        pending_ids = pending_ids[: max(0, int(limit))]

    total = len(pending_ids)
    print(
        f"待打标 {total} 条 | workers={workers} | model={TAG_MODEL} | "
        f"endpoint={TAG_BASE_URL}",
        flush=True,
    )
    if total == 0:
        return docs, stats

    t0 = time.time()
    latencies: List[float] = []

    def _work(oid: str) -> Tuple[str, Optional[dict], Optional[str], float]:
        doc = docs[oid]
        t_start = time.time()
        try:
            tags = tag_one(doc, retries=2)
            dt = time.time() - t_start
            if sleep > 0:
                time.sleep(sleep)
            return oid, tags, None, dt
        except Exception as e:
            dt = time.time() - t_start
            return oid, None, str(e), dt

    done_n = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_work, oid): oid for oid in pending_ids}
        for fut in as_completed(futures):
            oid, tags, err, dt = fut.result()
            latencies.append(dt)
            done_n += 1
            name = (
                docs[oid].get("name")
                or docs[oid].get("job_company_name")
                or oid
            )
            if tags is not None:
                docs[oid] = _apply_llm_tags(docs[oid], tags, model=TAG_MODEL)
                row = {
                    "org_id": oid,
                    "name": name,
                    "org_types": docs[oid].get("org_types"),
                    "tag_model": TAG_MODEL,
                    "tagged_at": _utc_now(),
                    **tags,
                }
                _append_jsonl(checkpoint, row, lock)
                stats["ok"] += 1
                if done_n <= 5 or done_n % 50 == 0:
                    print(
                        f"[OK {done_n}/{total}] {name} | "
                        f"l2={tags.get('org_type_l2')} | "
                        f"tags={tags.get('biz_tags')} | {dt:.1f}s",
                        flush=True,
                    )
            else:
                err_row = {
                    "org_id": oid,
                    "name": name,
                    "error": err,
                    "tagged_at": _utc_now(),
                }
                _append_jsonl(
                    checkpoint.with_suffix(".errors.jsonl"), err_row, lock
                )
                if fallback_rule:
                    docs[oid] = _apply_rule_fallback(docs[oid], err or "unknown")
                    stats["fallback"] += 1
                    print(
                        f"[FALLBACK {done_n}/{total}] {name}: {err}",
                        flush=True,
                    )
                else:
                    stats["err"] += 1
                    print(
                        f"[ERR {done_n}/{total}] {name}: {err}",
                        flush=True,
                    )

            if done_n % 20 == 0 or done_n == total:
                elapsed = time.time() - t0
                avg = sum(latencies[-50:]) / max(1, len(latencies[-50:]))
                remain = total - done_n
                eta = remain * avg / max(1, workers)
                print(
                    f"  进度 {done_n}/{total} | "
                    f"ok={stats['ok']} fallback={stats['fallback']} "
                    f"err={stats['err']} | "
                    f"近50条均延时 {avg:.1f}s | "
                    f"已用 {elapsed/60:.1f}min | "
                    f"剩余约 {eta/60:.1f}min",
                    flush=True,
                )

    return docs, stats


def filter_docs_by_type(
    docs: Dict[str, dict], org_type: Optional[str]
) -> Dict[str, dict]:
    if not org_type:
        return docs
    return {
        k: v
        for k, v in docs.items()
        if org_type in (v.get("org_types") or [])
        or v.get("org_type_primary") == org_type
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="入库时用大数据 DeepSeek 打组织 L2 + 业务标签"
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="组织 JSON 目录（lin）",
    )
    ap.add_argument("--org-type", default=None, help="只处理某一级类型，如 智库")
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多对新条打标条数（试跑用；不影响已 resume 条）",
    )
    ap.add_argument("--workers", type=int, default=4, help="并发数，默认 4")
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="每条成功后额外休眠秒数（限流用）",
    )
    ap.add_argument(
        "--checkpoint",
        type=Path,
        default=_HERE / "tagged_ingest.jsonl",
        help="打标检查点 JSONL",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="跳过检查点已成功 org_id（默认开启）",
    )
    ap.add_argument(
        "--no-resume",
        action="store_true",
        help="忽略检查点，全部重打",
    )
    ap.add_argument(
        "--no-fallback",
        action="store_true",
        help="LLM 失败时不回退规则打标",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只打标写检查点，不写 ES",
    )
    ap.add_argument(
        "--skip-llm",
        action="store_true",
        help="不调用 LLM（仅加载+可选入库；或配合 --from-checkpoint）",
    )
    ap.add_argument(
        "--from-checkpoint",
        type=Path,
        default=None,
        help="用已有检查点标签覆盖文档后入库（可 --skip-llm）",
    )
    ap.add_argument("--recreate", action="store_true", help="删除并重建 ES 索引")
    ap.add_argument("--batch-size", type=int, default=500, help="ES bulk 批大小")
    ap.add_argument(
        "--assume-latency",
        type=float,
        default=3.0,
        help="启动前 ETA 假设的单条延时（秒），实测后会按进度刷新",
    )
    args = ap.parse_args()

    resume = not args.no_resume
    if args.from_checkpoint:
        args.checkpoint = args.from_checkpoint
        args.skip_llm = True

    print("=== 组织入库 + DeepSeek 打标 ===", flush=True)
    print(f"DATA : {args.data_dir}", flush=True)
    print(f"LLM  : {TAG_BASE_URL}  model={TAG_MODEL}", flush=True)
    print(f"ES   : index={ORG_INDEX}", flush=True)
    print(f"CKPT : {args.checkpoint}", flush=True)

    if not args.data_dir.exists():
        print("数据目录不存在:", args.data_dir)
        return 1

    # 1) 加载原始 JSON（内部仍会先做 rule 打标，随后被 LLM 覆盖）
    docs, load_stats = load_all_docs(args.data_dir)
    print("\n=== 加载完成 ===", flush=True)
    print("唯一组织数:", len(docs), flush=True)
    for k, v in sorted(load_stats.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}", flush=True)

    docs = filter_docs_by_type(docs, args.org_type)
    if args.org_type:
        print(f"按类型过滤后: {args.org_type} → {len(docs)} 条", flush=True)

    # 预估
    pending_guess = len(docs)
    if resume and args.checkpoint.exists():
        pending_guess = max(0, len(docs) - len(load_done_ids(args.checkpoint)))
    if args.limit is not None:
        pending_guess = min(pending_guess, args.limit)
    print(
        f"\n耗时预估（假设单条 {args.assume_latency}s，workers={args.workers}）: "
        f"{estimate_eta(pending_guess, args.assume_latency, args.workers)} "
        f"（待处理约 {pending_guess} 条）",
        flush=True,
    )
    print(
        "说明: 全库约 50 万时，单条 2–5s、workers=8 → 大约 1.5–9 天；"
        "建议先 --org-type 智库 或 --limit 50 实测。",
        flush=True,
    )

    # 2) DeepSeek 打标
    tag_stats = {"ok": 0, "skip": 0, "fallback": 0, "err": 0}
    if not args.skip_llm:
        docs, tag_stats = tag_docs_with_llm(
            docs,
            workers=args.workers,
            checkpoint=args.checkpoint,
            resume=resume,
            fallback_rule=not args.no_fallback,
            sleep=args.sleep,
            limit=args.limit,
        )
        print(
            f"\n打标完成 ok={tag_stats['ok']} skip={tag_stats['skip']} "
            f"fallback={tag_stats['fallback']} err={tag_stats['err']}",
            flush=True,
        )
    elif args.checkpoint.exists():
        cached = _load_checkpoint_tags(args.checkpoint)
        applied = 0
        for oid, row in cached.items():
            if oid not in docs:
                continue
            docs[oid] = _apply_llm_tags(
                docs[oid],
                {
                    "org_type_l1": row.get("org_type_l1"),
                    "org_type_l2": row.get("org_type_l2"),
                    "biz_tags": row.get("biz_tags") or [],
                    "confidence": row.get("confidence"),
                    "reason": row.get("reason"),
                },
                model=row.get("tag_model") or TAG_MODEL,
            )
            applied += 1
        print(f"已从检查点应用标签 {applied} 条", flush=True)

    if args.dry_run:
        # 打印几条样本
        print("\n=== dry-run 样本（最多 5 条）===", flush=True)
        n = 0
        for doc in docs.values():
            if doc.get("tag_method") != "llm_deepseek" and not args.skip_llm:
                continue
            print(
                json.dumps(
                    {
                        "name": doc.get("name"),
                        "org_types": doc.get("org_types"),
                        "org_type_l2": doc.get("org_type_l2"),
                        "biz_tags": doc.get("biz_tags"),
                        "tag_method": doc.get("tag_method"),
                        "tag_confidence": doc.get("tag_confidence"),
                        "tag_reason": doc.get("tag_reason"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            n += 1
            if n >= 5:
                break
        print("dry-run 结束，未写 ES", flush=True)
        return 0 if tag_stats.get("err", 0) == 0 else 2

    # 3) 入库
    try:
        ensure_es_mapping()
    except Exception as e:
        print("ensure_mapping 警告:", e, flush=True)

    ensure_index(recreate=args.recreate)
    ok, fail = bulk_index(docs, batch_size=args.batch_size)
    print(f"\n入库完成 ok={ok} fail={fail}", flush=True)
    return 0 if fail == 0 and tag_stats.get("err", 0) == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

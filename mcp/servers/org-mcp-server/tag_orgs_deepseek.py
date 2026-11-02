# -*- coding: utf-8 -*-
"""
调用「大数据」自建 DeepSeek（OpenAI 兼容）为组织打二级类型 + 业务标签。

默认端点（来自 config.yaml providers.dsv4-dspark）：
  BASE_URL = http://172.200.200.4:7000/v1
  MODEL    = dsv4-dspark

用法示例：
  # 先小批量试跑（从 ES 拉智库样本）
  py -3 tag_orgs_deepseek.py --org-type 智库 --limit 5 --dry-run

  # 正式跑并写 JSONL 检查点
  py -3 tag_orgs_deepseek.py --org-type 智库 --limit 100 --out tagged_智库.jsonl

  # 断点续跑（跳过 out 里已有 org_id）
  py -3 tag_orgs_deepseek.py --org-type 智库 --limit 500 --out tagged_智库.jsonl --resume

  # 打完后回写 ES（需先 --ensure-mapping）
  py -3 tag_orgs_deepseek.py --from-jsonl tagged_智库.jsonl --update-es --ensure-mapping

环境变量（可选）：
  ORG_TAG_BASE_URL   默认 http://172.200.200.4:7000/v1
  ORG_TAG_MODEL      默认 dsv4-dspark
  ORG_TAG_API_KEY    默认空（内网一般可不填；需要时填任意/网关密钥）
  ES_HOST / ES_USERNAME / ES_PASSWORD / ORG_INDEX
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from org_taxonomy import BIZ_TAGS, L1_ALIASES, ORG_TYPE_L2_BY_L1

_HERE = Path(__file__).resolve().parent
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

# ── 大数据 DeepSeek ──
TAG_BASE_URL = os.environ.get(
    "ORG_TAG_BASE_URL", "http://172.200.200.4:7000/v1"
).rstrip("/")
TAG_MODEL = os.environ.get("ORG_TAG_MODEL", "dsv4-dspark")
TAG_API_KEY = os.environ.get("ORG_TAG_API_KEY", "")

ES_HOST = os.environ.get("ES_HOST", "http://127.0.0.1:9200").rstrip("/")
ES_USERNAME = os.environ.get("ES_USERNAME", "")
ES_PASSWORD = os.environ.get("ES_PASSWORD", "")
ORG_INDEX = os.environ.get("ORG_INDEX", "dw_org_info_lk_company")

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_DESC_MAX = 1200


def _es_auth() -> Optional[str]:
    if ES_USERNAME and ES_PASSWORD:
        token = base64.b64encode(
            f"{ES_USERNAME}:{ES_PASSWORD}".encode()
        ).decode()
        return f"Basic {token}"
    return None


def es_request(method: str, path: str, body: Any = None, timeout: int = 120) -> Any:
    url = f"{ES_HOST}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    auth = _es_auth()
    if auth:
        headers["Authorization"] = auth
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ES HTTP {e.code}: {detail[:800]}") from e


def chat_completions(
    messages: List[dict],
    *,
    temperature: float = 0.1,
    max_tokens: int = 800,
    timeout: int = 120,
) -> str:
    """调用大数据 DeepSeek OpenAI 兼容接口。"""
    url = f"{TAG_BASE_URL}/chat/completions"
    payload = {
        "model": TAG_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if TAG_API_KEY:
        headers["Authorization"] = f"Bearer {TAG_API_KEY}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {e.code}: {detail[:800]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM 连接失败: {e.reason}") from e

    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM 无 choices: {json.dumps(result, ensure_ascii=False)[:500]}")
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    if isinstance(content, list):
        # 部分网关返回多段 content
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text") or "")
            elif isinstance(p, str):
                parts.append(p)
        content = "".join(parts)
    return str(content).strip()


def _extract_json_obj(text: str) -> dict:
    """从模型输出中抠出 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"无法解析 JSON: {text[:300]}")
    obj = json.loads(m.group(0))
    if not isinstance(obj, dict):
        raise ValueError("JSON 不是 object")
    return obj


def normalize_l1(raw: Optional[str]) -> str:
    if not raw:
        return ""
    s = raw.strip()
    return L1_ALIASES.get(s, s)


def build_prompt(org: dict) -> List[dict]:
    l1_list = [normalize_l1(x) for x in (org.get("org_types") or []) if x]
    l1_primary = normalize_l1(org.get("org_type_primary")) or (
        l1_list[0] if l1_list else ""
    )
    allowed_l2: List[str] = []
    for l1 in l1_list or ([l1_primary] if l1_primary else []):
        allowed_l2.extend(ORG_TYPE_L2_BY_L1.get(l1, []))
    allowed_l2 = list(dict.fromkeys(allowed_l2))
    if not allowed_l2:
        allowed_l2 = ["其他/无法判定"]

    desc = org.get("description") or ""
    if len(desc) > _DESC_MAX:
        desc = desc[:_DESC_MAX] + "…"

    org_brief = {
        "name": org.get("name") or org.get("job_company_name"),
        "org_types_l1": l1_list or ([l1_primary] if l1_primary else []),
        "org_type_primary": l1_primary,
        "industry": org.get("industry"),
        "location_country": org.get("location_country"),
        "location_name": org.get("location_name"),
        "website": org.get("website"),
        "size": org.get("size"),
        "founded": org.get("founded"),
        "description": desc,
    }

    system = (
        "你是组织情报标注助手。根据给定组织信息，判定二级组织类型和业务标签。\n"
        "硬性规则：\n"
        "1) org_type_l2 必须从「允许的二级类型」列表中选 1 个；实在无法判断选「其他/无法判定」或列表中的「其他*」。\n"
        "2) biz_tags 只能从「允许的业务标签」多选；没有证据则返回空数组 []，不要臆造。\n"
        "3) 涉华/涉台等标签需要 description/名称/行业中有明确相关信号才可打。\n"
        "4) 只输出一个 JSON 对象，不要 Markdown，不要解释。\n"
        "JSON 格式：\n"
        "{"
        '"org_type_l1":"一级类型",'
        '"org_type_l2":"二级类型",'
        '"biz_tags":["标签1"],'
        '"confidence":0.0,'
        '"reason":"一句话依据"'
        "}"
    )
    user = (
        "【允许的二级类型】\n"
        + json.dumps(allowed_l2, ensure_ascii=False)
        + "\n\n【允许的业务标签】\n"
        + json.dumps(BIZ_TAGS, ensure_ascii=False)
        + "\n\n【组织信息】\n"
        + json.dumps(org_brief, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def validate_tags(raw: dict, org: dict) -> dict:
    l1_list = [normalize_l1(x) for x in (org.get("org_types") or []) if x]
    l1_primary = normalize_l1(org.get("org_type_primary")) or (
        l1_list[0] if l1_list else ""
    )
    allowed_l2: Set[str] = set()
    for l1 in l1_list or ([l1_primary] if l1_primary else []):
        allowed_l2.update(ORG_TYPE_L2_BY_L1.get(l1, []))
    allowed_l2.add("其他/无法判定")

    l2 = str(raw.get("org_type_l2") or "").strip()
    if l2 not in allowed_l2:
        # 尝试模糊落入「其他*」
        other = next((x for x in allowed_l2 if x.startswith("其他")), "其他/无法判定")
        l2 = other

    allowed_tags = set(BIZ_TAGS)
    tags = []
    for t in raw.get("biz_tags") or []:
        t = str(t).strip()
        if t in allowed_tags and t not in tags:
            tags.append(t)

    conf = raw.get("confidence")
    try:
        conf_f = float(conf)
    except (TypeError, ValueError):
        conf_f = 0.0
    conf_f = max(0.0, min(1.0, conf_f))

    l1_out = normalize_l1(str(raw.get("org_type_l1") or l1_primary))
    if l1_out not in (l1_list or [l1_primary]):
        l1_out = l1_primary

    return {
        "org_type_l1": l1_out,
        "org_type_l2": l2,
        "biz_tags": tags,
        "confidence": conf_f,
        "reason": str(raw.get("reason") or "")[:300],
    }


def tag_one(org: dict, *, retries: int = 2) -> dict:
    messages = build_prompt(org)
    last_err: Optional[Exception] = None
    for i in range(retries + 1):
        try:
            content = chat_completions(messages)
            parsed = _extract_json_obj(content)
            return validate_tags(parsed, org)
        except Exception as e:
            last_err = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"标注失败: {last_err}")


def iter_orgs_from_es(
    *,
    org_type: Optional[str] = None,
    limit: int = 100,
    page_size: int = 50,
) -> Iterable[dict]:
    """用 search_after 从 ES 拉取组织。"""
    got = 0
    search_after = None
    while got < limit:
        size = min(page_size, limit - got)
        body: Dict[str, Any] = {
            "size": size,
            "sort": [{"org_id": "asc"}, {"_id": "asc"}],
            "_source": [
                "org_id",
                "name",
                "job_company_name",
                "org_types",
                "org_type_primary",
                "industry",
                "location_country",
                "location_name",
                "website",
                "size",
                "founded",
                "description",
                "linkedin_url",
            ],
        }
        if org_type:
            body["query"] = {"term": {"org_types": org_type}}
        else:
            body["query"] = {"match_all": {}}
        if search_after is not None:
            body["search_after"] = search_after
        resp = es_request("POST", f"/{ORG_INDEX}/_search", body)
        hits = resp.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            src = h.get("_source") or {}
            if not src.get("org_id"):
                src["org_id"] = h.get("_id")
            src["_es_id"] = h.get("_id")
            yield src
            got += 1
            if got >= limit:
                return
        search_after = hits[-1].get("sort")


def load_done_ids(path: Path) -> Set[str]:
    done: Set[str] = set()
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            oid = obj.get("org_id")
            if oid:
                done.add(oid)
    return done


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def ensure_es_mapping() -> None:
    """为索引补充二级类型与业务标签字段（dynamic=false 时必须显式加）。"""
    body = {
        "properties": {
            "org_type_l2": {"type": "keyword"},
            "biz_tags": {"type": "keyword"},
            "tag_confidence": {"type": "float"},
            "tag_reason": {"type": "text"},
            "tag_model": {"type": "keyword"},
            "tagged_at": {"type": "date"},
        }
    }
    es_request("PUT", f"/{ORG_INDEX}/_mapping", body)
    print("已更新 mapping: org_type_l2 / biz_tags / tag_*")


def update_es_from_jsonl(path: Path, batch_size: int = 200) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    ok = fail = 0
    buf: List[str] = []

    def flush() -> None:
        nonlocal ok, fail, buf
        if not buf:
            return
        raw = ("\n".join(buf) + "\n").encode("utf-8")
        url = f"{ES_HOST}/_bulk"
        headers = {"Content-Type": "application/x-ndjson"}
        auth = _es_auth()
        if auth:
            headers["Authorization"] = auth
        req = urllib.request.Request(url, data=raw, method="POST", headers=headers)
        with _OPENER.open(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        for item in result.get("items") or []:
            upd = item.get("update") or {}
            if upd.get("error"):
                fail += 1
            else:
                ok += 1
        buf = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        es_id = obj.get("_es_id") or obj.get("org_id")
        if not es_id:
            continue
        doc = {
            "org_type_l2": obj.get("org_type_l2"),
            "biz_tags": obj.get("biz_tags") or [],
            "tag_confidence": obj.get("confidence"),
            "tag_reason": obj.get("reason"),
            "tag_model": obj.get("tag_model") or TAG_MODEL,
            "tagged_at": obj.get("tagged_at"),
        }
        # 若模型也确认了 l1，可写回 primary（不覆盖原 org_types 数组）
        if obj.get("org_type_l1"):
            doc["org_type_primary"] = obj["org_type_l1"]
        meta = {"update": {"_index": ORG_INDEX, "_id": es_id}}
        buf.append(json.dumps(meta, ensure_ascii=False))
        buf.append(json.dumps({"doc": doc}, ensure_ascii=False))
        if len(buf) >= batch_size * 2:
            flush()
            print(f"  bulk ok={ok} fail={fail}")
    flush()
    es_request("POST", f"/{ORG_INDEX}/_refresh", {})
    print(f"回写完成 ok={ok} fail={fail}")


def main() -> int:
    ap = argparse.ArgumentParser(description="组织二级类型+业务标签标注（大数据 DeepSeek）")
    ap.add_argument("--org-type", default=None, help="只处理某一级类型，如 智库")
    ap.add_argument("--limit", type=int, default=20, help="最多处理条数")
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument(
        "--out",
        type=Path,
        default=_HERE / "tagged_orgs.jsonl",
        help="输出 JSONL 路径",
    )
    ap.add_argument("--resume", action="store_true", help="跳过 out 中已有 org_id")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    ap.add_argument("--sleep", type=float, default=0.2, help="每条间隔秒")
    ap.add_argument("--from-jsonl", type=Path, default=None, help="从已有 JSONL 回写 ES")
    ap.add_argument("--update-es", action="store_true", help="把标注结果回写 ES")
    ap.add_argument("--ensure-mapping", action="store_true", help="先补充 ES mapping")
    ap.add_argument("--base-url", default=None, help="覆盖 ORG_TAG_BASE_URL")
    ap.add_argument("--model", default=None, help="覆盖 ORG_TAG_MODEL")
    args = ap.parse_args()

    global TAG_BASE_URL, TAG_MODEL
    if args.base_url:
        TAG_BASE_URL = args.base_url.rstrip("/")
    if args.model:
        TAG_MODEL = args.model

    print(f"LLM: {TAG_BASE_URL}  model={TAG_MODEL}", flush=True)
    print(f"ES : {ES_HOST}  index={ORG_INDEX}", flush=True)

    if args.ensure_mapping:
        ensure_es_mapping()

    if args.from_jsonl:
        if not args.update_es:
            print("--from-jsonl 需同时加 --update-es")
            return 1
        update_es_from_jsonl(args.from_jsonl)
        return 0

    done: Set[str] = set()
    if args.resume and args.out.exists():
        done = load_done_ids(args.out)
        print(f"resume: 已跳过 {len(done)} 条")

    n_ok = n_skip = n_err = 0
    t0 = time.time()
    for org in iter_orgs_from_es(
        org_type=args.org_type, limit=args.limit, page_size=args.page_size
    ):
        oid = org.get("org_id") or ""
        if oid and oid in done:
            n_skip += 1
            continue
        name = org.get("name") or org.get("job_company_name") or oid
        try:
            tags = tag_one(org)
            row = {
                "org_id": oid,
                "_es_id": org.get("_es_id") or oid,
                "name": name,
                "org_types": org.get("org_types"),
                "tag_model": TAG_MODEL,
                "tagged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **tags,
            }
            print(
                f"[OK] {name} | l2={tags['org_type_l2']} | tags={tags['biz_tags']} | "
                f"conf={tags['confidence']}"
            )
            if not args.dry_run:
                append_jsonl(args.out, row)
            n_ok += 1
        except Exception as e:
            n_err += 1
            print(f"[ERR] {name}: {e}")
            err_row = {
                "org_id": oid,
                "_es_id": org.get("_es_id") or oid,
                "name": name,
                "error": str(e),
                "tagged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if not args.dry_run:
                append_jsonl(args.out.with_suffix(".errors.jsonl"), err_row)
        time.sleep(max(0.0, args.sleep))

    print(
        f"\n完成 ok={n_ok} skip={n_skip} err={n_err} "
        f"elapsed={time.time()-t0:.1f}s out={args.out}"
    )

    if args.update_es and not args.dry_run and n_ok > 0:
        try:
            ensure_es_mapping()
        except Exception as e:
            print("ensure_mapping 警告:", e)
        update_es_from_jsonl(args.out)

    return 0 if n_err == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

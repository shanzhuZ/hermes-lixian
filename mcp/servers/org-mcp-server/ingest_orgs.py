# -*- coding: utf-8 -*-
"""
组织数据入库：读取 lin 目录 JSON → 去重合并组织类型 → bulk 写入 ES。

用法：
  py -3 ingest_orgs.py --dry-run          # 只统计不写库
  py -3 ingest_orgs.py                    # 建索引并全量入库
  py -3 ingest_orgs.py --recreate         # 删除重建索引后再入库
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from org_mapping import MAPPING, ORG_INDEX, ORG_TYPE_NORMALIZE
from org_rule_tagger import tag_org_doc

_HERE = Path(__file__).resolve().parent
_ENV = _HERE / ".env"
if _ENV.exists():
    for line in _ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("\"'")
        if not os.environ.get(k):
            os.environ[k] = v

# 回退到 identity-mcp 的 .env
_ID_ENV = _HERE.parent / "identity-mcp-server" / ".env"
if _ID_ENV.exists():
    for line in _ID_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("\"'")
        if not os.environ.get(k):
            os.environ[k] = v

ES_HOST = os.environ.get("ES_HOST", "http://127.0.0.1:9200").rstrip("/")
ES_USERNAME = os.environ.get("ES_USERNAME", "")
ES_PASSWORD = os.environ.get("ES_PASSWORD", "")
DEFAULT_DATA_DIR = Path(
    r"D:\企业微信\缓存\WXWork\1688856417716061\Cache\File\2026-09\lin"
)

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _auth_header() -> Optional[str]:
    if ES_USERNAME and ES_PASSWORD:
        token = base64.b64encode(
            f"{ES_USERNAME}:{ES_PASSWORD}".encode()
        ).decode()
        return f"Basic {token}"
    return None


def es(method: str, path: str, body: Any = None, timeout: int = 120) -> Any:
    url = f"{ES_HOST}/{path.lstrip('/')}"
    data = None
    headers = {"Content-Type": "application/json"}
    auth = _auth_header()
    if auth:
        headers["Authorization"] = auth
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = body
        else:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ES HTTP {e.code}: {detail[:1000]}") from e


def discover_categories(data_dir: Path) -> Dict[str, Path]:
    """每个原始类别选一个最优源文件。优先 desc.cleaned > desc > mega > 无。"""
    chosen: Dict[str, Path] = {}
    # 收集所有类别 stem
    cats: Set[str] = set()
    for f in data_dir.glob("*.json"):
        name = f.name
        if name.endswith(".py"):
            continue
        stem = f.stem
        stem = re.sub(r"\.cleaned$", "", stem)
        stem = re.sub(r"desc$", "", stem)
        stem = re.sub(r"_\d+$", "", stem)
        if stem:
            cats.add(stem)

    for cat in sorted(cats):
        cleaned = data_dir / f"{cat}desc.cleaned.json"
        desc = data_dir / f"{cat}desc.json"
        mega = data_dir / f"{cat}.json"
        if cleaned.exists() and cleaned.stat().st_size > 100:
            chosen[cat] = cleaned
        elif desc.exists() and desc.stat().st_size > 100:
            chosen[cat] = desc
        elif mega.exists() and mega.stat().st_size > 100:
            chosen[cat] = mega
        else:
            # 仅分片时：返回目录下标记，后续展开
            shards = sorted(
                f
                for f in data_dir.glob(f"{cat}_*.json")
                if "desc" not in f.name and f.stat().st_size > 0
            )
            if shards:
                # 用特殊标记：第一个分片路径，但记录为 multi
                chosen[cat] = shards[0].parent / f"__SHARDS__{cat}"
    return chosen


def iter_source_files(data_dir: Path, cat: str, marker: Path) -> List[Path]:
    if marker.name.startswith("__SHARDS__"):
        return sorted(
            f
            for f in data_dir.glob(f"{cat}_*.json")
            if "desc" not in f.name and f.stat().st_size > 0
        )
    return [marker]


def org_doc_id(rec: dict) -> str:
    cid = (rec.get("job_company_id") or "").strip()
    if cid:
        return cid
    lid = str(rec.get("job_company_linkedin_id") or "").strip()
    if lid:
        return f"li_{lid}"
    name = (rec.get("job_company_name") or "").strip().lower()
    country = (rec.get("job_company_location_country") or "").strip().lower()
    raw = f"{name}|{country}"
    return "h_" + hashlib.md5(raw.encode("utf-8")).hexdigest()


def parse_geo(val: Any) -> Optional[dict]:
    if not val or not isinstance(val, str):
        return None
    parts = val.split(",")
    if len(parts) != 2:
        return None
    try:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
        if abs(lat) > 90 or abs(lon) > 180:
            return None
        return {"lat": lat, "lon": lon}
    except ValueError:
        return None


def transform(rec: dict, org_type: str, source_file: str) -> dict:
    name = (rec.get("job_company_name") or "").strip()
    org_id = (rec.get("job_company_id") or "").strip() or None
    lid = rec.get("job_company_linkedin_id")
    lid = str(lid).strip() if lid not in (None, "") else None
    desc = rec.get("description")
    if isinstance(desc, str):
        desc = desc.strip() or None
    else:
        desc = None

    doc = {
        "org_id": org_id,
        "org_linkedin_id": lid,
        "name": name or None,
        "name_raw": name.lower() if name else None,
        "website": rec.get("job_company_website") or None,
        "linkedin_url": rec.get("job_company_linkedin_url") or None,
        "facebook_url": rec.get("job_company_facebook_url") or None,
        "twitter_url": rec.get("job_company_twitter_url") or None,
        "industry": rec.get("job_company_industry") or None,
        "size": rec.get("job_company_size") or None,
        "founded": str(rec.get("job_company_founded"))
        if rec.get("job_company_founded") not in (None, "")
        else None,
        "description": desc,
        "org_types": [org_type],
        "org_type_primary": org_type,
        "location_country": rec.get("job_company_location_country") or None,
        "location_region": rec.get("job_company_location_region") or None,
        "location_locality": rec.get("job_company_location_locality") or None,
        "location_metro": rec.get("job_company_location_metro") or None,
        "location_continent": rec.get("job_company_location_continent") or None,
        "location_name": rec.get("job_company_location_name") or None,
        "location_postal_code": rec.get("job_company_location_postal_code") or None,
        "location_street_address": rec.get("job_company_location_street_address")
        or None,
        "location_address_line_2": rec.get("job_company_location_address_line_2")
        or None,
        "location_geo": parse_geo(rec.get("job_company_location_geo")),
        "job_company_id": org_id,
        "job_company_linkedin_id": lid,
        "job_company_name": name or None,
        "source_categories": [org_type],
        "source_files": [source_file],
        "ingest_time": datetime.now(timezone.utc).isoformat(),
    }
    # 入库时规则打二级类型 + 业务标签
    return tag_org_doc(doc)


def merge_doc(existing: dict, new: dict) -> dict:
    # 合并类型
    types = list(
        dict.fromkeys(
            (existing.get("org_types") or []) + (new.get("org_types") or [])
        )
    )
    existing["org_types"] = types
    if not existing.get("org_type_primary") and types:
        existing["org_type_primary"] = types[0]
    # 更长 description 优先
    old_d = existing.get("description") or ""
    new_d = new.get("description") or ""
    if len(new_d) > len(old_d):
        existing["description"] = new_d
    # 补空字段
    for k, v in new.items():
        if k in (
            "org_types",
            "org_type_primary",
            "description",
            "source_categories",
            "source_files",
            "ingest_time",
        ):
            continue
        if existing.get(k) in (None, "", []) and v not in (None, "", []):
            existing[k] = v
    existing["source_categories"] = list(
        dict.fromkeys(
            (existing.get("source_categories") or [])
            + (new.get("source_categories") or [])
        )
    )
    existing["source_files"] = list(
        dict.fromkeys(
            (existing.get("source_files") or []) + (new.get("source_files") or [])
        )
    )[:20]
    # 合并后按最新全文重打标签
    return tag_org_doc(existing)


def load_all_docs(
    data_dir: Path,
) -> Tuple[Dict[str, dict], Dict[str, int]]:
    chosen = discover_categories(data_dir)
    stats: Dict[str, int] = {}
    docs: Dict[str, dict] = {}
    print(f"发现 {len(chosen)} 个类别源")
    for cat, marker in chosen.items():
        org_type = ORG_TYPE_NORMALIZE.get(cat, cat)
        files = iter_source_files(data_dir, cat, marker)
        cat_n = 0
        for fp in files:
            print(f"  读取 [{org_type}] {fp.name} ...", flush=True)
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"    跳过(读失败): {e}")
                continue
            if not isinstance(data, list):
                print("    跳过(非 list)")
                continue
            for rec in data:
                if not isinstance(rec, dict):
                    continue
                if not (rec.get("job_company_name") or rec.get("job_company_id")):
                    continue
                did = org_doc_id(rec)
                new_doc = transform(rec, org_type, fp.name)
                if did in docs:
                    docs[did] = merge_doc(docs[did], new_doc)
                else:
                    docs[did] = new_doc
                cat_n += 1
        stats[org_type] = stats.get(org_type, 0) + cat_n
        print(f"    本类原始条数 {cat_n}，累计唯一 {len(docs)}")
    return docs, stats


def ensure_index(recreate: bool = False) -> None:
    exists = True
    try:
        es("GET", f"/{ORG_INDEX}")
    except RuntimeError as e:
        if "404" in str(e) or "index_not_found" in str(e).lower():
            exists = False
        else:
            # 404 也走创建
            exists = False
    if exists and recreate:
        print(f"删除索引 {ORG_INDEX}")
        es("DELETE", f"/{ORG_INDEX}")
        exists = False
    if not exists:
        print(f"创建索引 {ORG_INDEX}")
        es("PUT", f"/{ORG_INDEX}", MAPPING)
    else:
        print(f"索引已存在: {ORG_INDEX}")


def bulk_index(docs: Dict[str, dict], batch_size: int = 500) -> Tuple[int, int]:
    ok = 0
    fail = 0
    items = list(docs.items())
    total = len(items)
    t0 = time.time()
    for i in range(0, total, batch_size):
        chunk = items[i : i + batch_size]
        lines: List[str] = []
        for did, doc in chunk:
            meta = {"index": {"_index": ORG_INDEX, "_id": did}}
            lines.append(json.dumps(meta, ensure_ascii=False))
            lines.append(json.dumps(doc, ensure_ascii=False))
        body = ("\n".join(lines) + "\n").encode("utf-8")
        url = f"{ES_HOST}/_bulk"
        headers = {"Content-Type": "application/x-ndjson"}
        auth = _auth_header()
        if auth:
            headers["Authorization"] = auth
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            with _OPENER.open(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"bulk HTTP {e.code}: {detail[:500]}") from e
        if result.get("errors"):
            for item in result.get("items") or []:
                idx = item.get("index") or {}
                if idx.get("error"):
                    fail += 1
                else:
                    ok += 1
        else:
            ok += len(chunk)
        done = min(i + batch_size, total)
        if done % 5000 < batch_size or done == total:
            elapsed = time.time() - t0
            print(
                f"  bulk {done}/{total} ok={ok} fail={fail} "
                f"{elapsed:.1f}s",
                flush=True,
            )
    # 刷新
    es("POST", f"/{ORG_INDEX}/_refresh", {})
    return ok, fail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="组织 JSON 目录",
    )
    ap.add_argument("--dry-run", action="store_true", help="只加载统计，不写 ES")
    ap.add_argument("--recreate", action="store_true", help="删除并重建索引")
    ap.add_argument("--batch-size", type=int, default=500)
    args = ap.parse_args()

    if not args.data_dir.exists():
        print("数据目录不存在:", args.data_dir)
        return 1

    print("ES:", ES_HOST)
    print("INDEX:", ORG_INDEX)
    print("DATA:", args.data_dir)

    docs, stats = load_all_docs(args.data_dir)
    print("\n=== 加载完成 ===")
    print("唯一组织数:", len(docs))
    multi = sum(1 for d in docs.values() if len(d.get("org_types") or []) > 1)
    print("跨多类型组织:", multi)
    print("各类原始条数:")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    if args.dry_run:
        print("dry-run 结束，未写库")
        return 0

    ensure_index(recreate=args.recreate)
    ok, fail = bulk_index(docs, batch_size=args.batch_size)
    print(f"\n入库完成 ok={ok} fail={fail}")

    # 冒烟
    cnt = es("GET", f"/{ORG_INDEX}/_count")
    print("索引 count:", cnt.get("count"))
    sample = es(
        "POST",
        f"/{ORG_INDEX}/_search",
        {
            "size": 2,
            "query": {"term": {"org_types": "智库"}},
            "_source": [
                "name",
                "org_types",
                "org_type_l2",
                "biz_tags",
                "tag_method",
                "location_country",
                "industry",
                "org_id",
            ],
        },
    )
    hits = sample.get("hits", {}).get("hits", [])
    print("智库样本:")
    for h in hits:
        print(" ", json.dumps(h.get("_source"), ensure_ascii=False))

    # 标签覆盖统计
    tag_agg = es(
        "POST",
        f"/{ORG_INDEX}/_search",
        {
            "size": 0,
            "aggs": {
                "with_l2": {
                    "filter": {"exists": {"field": "org_type_l2"}},
                },
                "with_biz": {
                    "filter": {"exists": {"field": "biz_tags"}},
                },
                "biz_top": {
                    "terms": {"field": "biz_tags", "size": 20},
                },
                "l2_top": {
                    "terms": {"field": "org_type_l2", "size": 15},
                },
            },
        },
    )
    aggs = tag_agg.get("aggregations") or {}
    print(
        "标签覆盖: l2=",
        (aggs.get("with_l2") or {}).get("doc_count"),
        "biz_tags非空文档≈",
        (aggs.get("with_biz") or {}).get("doc_count"),
    )
    print("biz_tags top:")
    for b in (aggs.get("biz_top") or {}).get("buckets") or []:
        print(f"  {b.get('key')}: {b.get('doc_count')}")
    print("org_type_l2 top:")
    for b in (aggs.get("l2_top") or {}).get("buckets") or []:
        print(f"  {b.get('key')}: {b.get('doc_count')}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

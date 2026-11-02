# -*- coding: utf-8 -*-
"""组织库 ES 检索客户端（纯 stdlib HTTP）。"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from org_mapping import ORG_INDEX, ORG_TYPE_NORMALIZE
from org_taxonomy import BIZ_TAGS, ORG_TYPE_L2_BY_L1

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _k, _v = _k.strip(), _v.strip().strip("\"'")
            if not os.environ.get(_k):
                os.environ[_k] = _v

ES_HOST = os.environ.get("ES_HOST", "http://127.0.0.1:9200")
ES_USERNAME = os.environ.get("ES_USERNAME", "")
ES_PASSWORD = os.environ.get("ES_PASSWORD", "")
ORG_INDEX_NAME = os.environ.get("ORG_INDEX", ORG_INDEX)

DEFAULT_SIZE = 20
MAX_SIZE = 20
MAX_HITS_GUARD = 10000
INCLUDE_IDS_MAX = 500
ORG_SEARCH_SORT = [{"org_id": "asc"}, {"_id": "asc"}]

SUMMARY_SOURCE_FIELDS = [
    "org_id",
    "org_linkedin_id",
    "name",
    "website",
    "linkedin_url",
    "industry",
    "size",
    "founded",
    "org_types",
    "org_type_primary",
    "org_type_l2",
    "biz_tags",
    "tag_method",
    "tag_confidence",
    "tag_reason",
    "tag_model",
    "location_country",
    "location_region",
    "location_locality",
    "location_metro",
    "location_continent",
    "location_name",
    "description",
    "job_company_id",
    "job_company_name",
]

# 查询「涉华」时同时命中细分类标签，提升 LLM 精标后的召回
_BIZ_TAG_EXPAND: Dict[str, List[str]] = {
    "涉华": [
        "涉华",
        "涉华-政治",
        "涉华-经济",
        "涉华-科技",
        "涉华-军事",
        "涉华-外交",
        "涉华-人权",
        "涉华-台湾",
    ],
}

# 具名查询别名（短名 → 更完整检索串，消歧）
_KNOWN_NAME_ALIASES: Dict[str, str] = {
    "brookings": "brookings institution",
    "brookings institution": "brookings institution",
    "fapa": "formosan association for public affairs",
    "csis": "center for strategic and international studies",
    "cfr": "council on foreign relations",
    "rand": "rand corporation",
    "lockheed": "lockheed martin",
    "raytheon": "raytheon",
}

_DESC_MAX = 400

# 一级类型别名（口语 → 库内 org_types）
_ORG_TYPE_ALIASES: Dict[str, str] = {
    **{v: v for v in ORG_TYPE_NORMALIZE.values()},
    **{k: v for k, v in ORG_TYPE_NORMALIZE.items()},
    "think tank": "智库",
    "thinktank": "智库",
    "think tanks": "智库",
    "university": "高校",
    "universities": "高校",
    "college": "高校",
    "ngo": "非政府组织",
    "foundation": "基金会",
    "foundations": "基金会",
    "lobby": "游说机构",
    "lobbying": "游说机构",
    "defense": "军工",
    "military": "军队",
    "media": "媒体机构",
    "law firm": "律所咨询机构",
    "consulting": "律所咨询机构",
    "association": "行业协会",
    "trade association": "行业协会",
    "fapa": "台在美团体",
    "taiwanese american": "台在美团体",
    "semiconductor": "卡脖子高科技公司",
    "hi-tech": "卡脖子高科技公司",
    "high tech": "卡脖子高科技公司",
    "rare earth": "涉稀土矿产类公司",
    "critical minerals": "涉稀土矿产类公司",
    "intel contractor": "情报外包机构",
    "intelligence": "情报外包机构",
    "government": "政府机构",
    "dod": "国防部军方情报机构",
    "congress": "国会下属机构",
    "multilateral": "多边组织",
    "religion": "宗教类组织",
}

# 口语/英文议题 → 库内 biz_tags 规范名（入库规则已预打）
_BIZ_TAG_ALIASES: Dict[str, str] = {
    **{t: t for t in BIZ_TAGS},
    "china_related": "涉华",
    "china": "涉华",
    "taiwan_related": "涉台",
    "taiwan": "涉台",
    "hongkong_related": "涉港",
    "hong kong": "涉港",
    "hongkong": "涉港",
    "xinjiang": "涉疆",
    "tibet": "涉藏",
    "south_china_sea": "南海议题",
    "scs": "南海议题",
    "semiconductor": "半导体/科技竞争",
    "半导体": "半导体/科技竞争",
    "芯片": "半导体/科技竞争",
    "tech_competition": "半导体/科技竞争",
    "科技竞争": "半导体/科技竞争",
    "critical minerals": "关键矿产",
    "rare earth": "关键矿产",
    "稀土": "关键矿产",
    "human_rights": "人权议题",
    "人权": "人权议题",
    "military_security": "军事安全议题",
    "军事安全": "军事安全议题",
    "trade": "经贸议题",
    "经贸": "经贸议题",
}

# 无法映射到 biz_tags 时，topic 回退文本关键词
_TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "china_related": ["china", "chinese", "beijing", "prc", "sino", "中国", "中共"],
    "涉华": ["china", "chinese", "beijing", "prc", "sino", "中国", "中共"],
    "taiwan_related": ["taiwan", "taipei", "台湾", "台北"],
    "涉台": ["taiwan", "taipei", "台湾", "台北"],
    "hongkong_related": ["hong kong", "hongkong", "香港"],
    "涉港": ["hong kong", "hongkong", "香港"],
    "涉疆": ["xinjiang", "uyghur", "新疆"],
    "涉藏": ["tibet", "tibetan", "西藏"],
    "南海议题": ["south china sea", "南海"],
    "半导体/科技竞争": ["semiconductor", "chip", "chips", "半导体", "芯片"],
    "关键矿产": ["rare earth", "critical mineral", "稀土"],
    "人权议题": ["human rights", "人权"],
    "军事安全议题": ["military", "defense", "national security", "军事", "国防"],
    "经贸议题": ["trade", "tariff", "经贸", "贸易"],
}

# 二级类型口语别名 → 规范 L2
_L2_ALIASES: Dict[str, str] = {}
for _l2s in ORG_TYPE_L2_BY_L1.values():
    for _l2 in _l2s:
        _L2_ALIASES[_l2] = _l2
        _L2_ALIASES[_l2.lower()] = _l2
_L2_ALIASES.update(
    {
        "think tank": "战略智库",
        "security think tank": "安全智库",
        "law firm": "律所",
        "ngo": "NGO",
        "university": "综合大学",
        "chip": "芯片",
        "ai": "AI",
        "lobbying firm": "游说公司",
    }
)


def _auth_header() -> Optional[str]:
    if ES_USERNAME and ES_PASSWORD:
        encoded = base64.b64encode(
            f"{ES_USERNAME}:{ES_PASSWORD}".encode()
        ).decode()
        return f"Basic {encoded}"
    return None


AUTH = _auth_header()
_ES_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _es(method: str, path: str, body: dict | None = None, timeout: int = 60) -> dict:
    url = urljoin(ES_HOST.rstrip("/") + "/", path.lstrip("/"))
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    if AUTH:
        headers["Authorization"] = AUTH
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _ES_OPENER.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ES HTTP {e.code}: {detail[:800]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"ES 连接失败: {e.reason}") from e


def _total_hits(resp: dict) -> int:
    total = resp.get("hits", {}).get("total", 0)
    if isinstance(total, dict):
        return total.get("value", 0)
    return total


def _norm_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _normalize_org_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = raw.strip()
    if key in _ORG_TYPE_ALIASES:
        return _ORG_TYPE_ALIASES[key]
    low = _norm_text(key)
    if low in _ORG_TYPE_ALIASES:
        return _ORG_TYPE_ALIASES[low]
    # 模糊包含
    for alias, canon in _ORG_TYPE_ALIASES.items():
        if _norm_text(alias) == low or low in _norm_text(alias):
            return canon
    return key  # 原样尝试 term 匹配


def _normalize_biz_tag(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = raw.strip()
    if key in _BIZ_TAG_ALIASES:
        return _BIZ_TAG_ALIASES[key]
    low = _norm_text(key)
    if low in _BIZ_TAG_ALIASES:
        return _BIZ_TAG_ALIASES[low]
    # 涉华-xxx 细项原样
    if key.startswith("涉华-") and key in BIZ_TAGS:
        return key
    return key


def _normalize_org_type_l2(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = raw.strip()
    if key in _L2_ALIASES:
        return _L2_ALIASES[key]
    low = _norm_text(key)
    if low in _L2_ALIASES:
        return _L2_ALIASES[low]
    return key


def _term_keyword(field: str, value: str) -> dict:
    v = _norm_text(value)
    if not v:
        return {}
    return {"term": {field: v}}


def _match_phrase(field: str, value: str) -> dict:
    text = (value or "").strip()
    if not text:
        return {}
    return {"match_phrase": {field: {"query": text}}}


def _sanitize_hit(hit: dict) -> dict:
    cleaned = dict(hit)
    desc = cleaned.get("description")
    if isinstance(desc, str) and len(desc) > _DESC_MAX:
        cleaned["description"] = desc[:_DESC_MAX] + "…"
    reason = cleaned.get("tag_reason")
    if isinstance(reason, str) and len(reason) > 200:
        cleaned["tag_reason"] = reason[:200] + "…"
    # 交付用短证据摘要
    l2 = cleaned.get("org_type_l2") or ""
    tags = cleaned.get("biz_tags") or []
    if isinstance(tags, str):
        tags = [tags]
    parts = []
    if l2:
        parts.append(f"L2={l2}")
    if tags:
        parts.append("tags=" + ",".join(tags[:10]))
    if cleaned.get("tag_method"):
        parts.append(f"method={cleaned['tag_method']}")
    conf = cleaned.get("tag_confidence")
    if conf is not None:
        try:
            parts.append(f"conf={float(conf):.2f}")
        except (TypeError, ValueError):
            pass
    cleaned["evidence_brief"] = "; ".join(parts) if parts else ""
    return cleaned


def _format_hits(resp: dict) -> List[dict]:
    results = []
    for h in resp.get("hits", {}).get("hits", []):
        item = {
            "_id": h.get("_id"),
            "_score": round(h.get("_score", 0) or 0, 4),
            **(h.get("_source") or {}),
        }
        results.append(_sanitize_hit(item))
    return results


def _expand_biz_tag_values(tag: str) -> List[str]:
    """单标签展开为可 OR 命中的规范名列表（如 涉华 → 涉华 + 涉华-*）。"""
    nt = _normalize_biz_tag(tag)
    if not nt:
        return []
    expanded = _BIZ_TAG_EXPAND.get(nt)
    if expanded:
        return list(expanded)
    return [nt]


def _biz_tag_filter_clause(tag: str) -> Optional[dict]:
    vals = _expand_biz_tag_values(tag)
    if not vals:
        return None
    if len(vals) == 1:
        return {"term": {"biz_tags": vals[0]}}
    return {"terms": {"biz_tags": vals}}


def _execute_search(
    query: dict,
    size: int = DEFAULT_SIZE,
    *,
    meta: Optional[Dict[str, Any]] = None,
    sort: Optional[List[dict]] = None,
    search_after: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    size = min(max(int(size or DEFAULT_SIZE), 1), MAX_SIZE)
    body: Dict[str, Any] = {
        "query": query,
        "size": size,
        "track_total_hits": MAX_HITS_GUARD + 1,
        "_source": SUMMARY_SOURCE_FIELDS,
    }
    if sort:
        body["sort"] = sort
    if search_after:
        body["search_after"] = search_after
    resp = _es("POST", f"/{ORG_INDEX_NAME}/_search", body, timeout=120)
    total = _total_hits(resp)
    raw_hits = resp.get("hits", {}).get("hits", []) or []
    hits = _format_hits(resp)
    truncated = total > MAX_HITS_GUARD
    if truncated and not hits:
        return {
            "index": ORG_INDEX_NAME,
            "error": (
                f"命中数超过 {MAX_HITS_GUARD}，条件过宽且无法返回样本。"
                "请补充组织类型、国家、名称关键词等。"
            ),
            "total_hits": f">{MAX_HITS_GUARD}",
            "returned": 0,
            "results": [],
            "is_sample": True,
            "meta": meta or {},
            "took_ms": resp.get("took"),
        }
    out: Dict[str, Any] = {
        "index": ORG_INDEX_NAME,
        "total_hits": f">{MAX_HITS_GUARD}" if truncated else total,
        "returned": len(hits),
        "results": hits,
        "is_sample": bool(truncated),
        "meta": meta or {},
        "took_ms": resp.get("took"),
    }
    if truncated:
        out["warning"] = (
            f"条件较宽（估计命中 >{MAX_HITS_GUARD}），以下为截断样本（is_sample=true），"
            "非全量名单；请继续收窄或基于 org_id 二次筛选。"
        )
    if sort:
        if raw_hits and len(raw_hits) >= size:
            last_sort = raw_hits[-1].get("sort")
            out["next_search_after"] = last_sort
            out["has_more"] = last_sort is not None
        else:
            out["next_search_after"] = None
            out["has_more"] = False
    return out


def list_org_types() -> Dict[str, Any]:
    """返回库内一级/二级类型与业务标签及文档数。"""
    body = {
        "size": 0,
        "aggs": {
            "org_types": {"terms": {"field": "org_types", "size": 50}},
            "org_type_l2": {"terms": {"field": "org_type_l2", "size": 40}},
            "biz_tags": {"terms": {"field": "biz_tags", "size": 40}},
            "tag_method": {"terms": {"field": "tag_method", "size": 10}},
            "has_biz_tags": {
                "filter": {"exists": {"field": "biz_tags"}},
            },
        },
    }
    resp = _es("POST", f"/{ORG_INDEX_NAME}/_search", body)
    aggs = resp.get("aggregations") or {}

    def _buckets(name: str) -> List[dict]:
        return [
            {"key": b.get("key"), "count": b.get("doc_count")}
            for b in (aggs.get(name) or {}).get("buckets") or []
        ]

    has_tags = (aggs.get("has_biz_tags") or {}).get("doc_count", 0)
    return {
        "index": ORG_INDEX_NAME,
        "org_types": [
            {"org_type": b["key"], "count": b["count"]} for b in _buckets("org_types")
        ],
        "org_type_l2_top": _buckets("org_type_l2"),
        "biz_tags_top": _buckets("biz_tags"),
        "tag_method_top": _buckets("tag_method"),
        "docs_with_biz_tags": has_tags,
        "biz_tags_allowed": list(BIZ_TAGS),
        "aliases_hint": sorted(set(_ORG_TYPE_ALIASES.values())),
        "biz_tag_expand_hint": {
            "涉华": "查询 biz_tag=涉华 时自动 OR 命中 涉华-* 细分类"
        },
        "note": (
            "一级 org_types 来自入库文件名；org_type_l2 / biz_tags 以 "
            "tag_method=llm_deepseek 为主（少量 rule_v1 兜底）；"
            "查「涉华」会展开为 涉华 + 涉华-*；口语议题可用英文别名映射到 biz_tags"
        ),
    }


def lookup_org_by_id(org_id: str, size: int = DEFAULT_SIZE) -> Dict[str, Any]:
    oid = (org_id or "").strip()
    if not oid:
        raise ValueError("org_id 不能为空")
    should = [
        {"term": {"org_id": oid}},
        {"term": {"job_company_id": oid}},
        {"term": {"org_linkedin_id": oid}},
        {"ids": {"values": [oid]}},
    ]
    query = {"bool": {"should": should, "minimum_should_match": 1}}
    result = _execute_search(query, size, meta={"lookup": "by_id"})
    result["tool"] = "lookup_org_by_id"
    result["input"] = {"org_id": oid}
    return result


def _resolve_name_alias(name: str) -> tuple[str, str]:
    """返回 (原始名, 检索用名)；短名命中别名表时用完整名检索。"""
    text = (name or "").strip()
    low = _norm_text(text)
    alias = _KNOWN_NAME_ALIASES.get(low)
    if alias and alias != low:
        return text, alias
    return text, text


def lookup_org_by_name(
    name: str,
    *,
    location_country: Optional[str] = None,
    org_type: Optional[str] = None,
    size: int = DEFAULT_SIZE,
) -> Dict[str, Any]:
    text, alias_name = _resolve_name_alias(name)
    if not text:
        raise ValueError("name 不能为空")
    # 短名始终可命中；完整别名仅作高权重加分（避免库内无「XXX Institution」时查空）
    search_terms: List[tuple] = [(text, 5.0)]
    if alias_name and _norm_text(alias_name) != _norm_text(text):
        search_terms.insert(0, (alias_name, 10.0))
    should: List[dict] = []
    for term, boost in search_terms:
        should.extend(
            [
                {"match_phrase": {"name": {"query": term, "boost": boost}}},
                {
                    "match_phrase": {
                        "job_company_name": {"query": term, "boost": boost * 0.6}
                    }
                },
                {
                    "match": {
                        "name": {
                            "query": term,
                            "operator": "and",
                            "boost": boost * 0.5,
                        }
                    }
                },
                {"term": {"name.keyword": _norm_text(term)}},
            ]
        )
    must: List[dict] = [
        {"bool": {"should": should, "minimum_should_match": 1}}
    ]
    filters: List[dict] = []
    country = _norm_text(location_country)
    if country:
        variants = [country]
        if country in ("usa", "us", "united states of america", "u.s.", "u.s.a."):
            variants = ["united states", "usa", "us"]
        filters.append(
            {
                "bool": {
                    "should": [
                        c
                        for v in variants
                        for c in [_term_keyword("location_country", v)]
                        if c
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    ot = _normalize_org_type(org_type)
    if ot:
        filters.append({"term": {"org_types": ot}})
    # 有 biz_tags / 机构类类型时轻微加分，压低报刊同名等噪声
    soft_should: List[dict] = [
        {
            "constant_score": {
                "filter": {"exists": {"field": "biz_tags"}},
                "boost": 1.5,
            }
        },
        {"term": {"org_types": {"value": "智库", "boost": 2}}},
        {"term": {"org_types": {"value": "台在美团体", "boost": 2}}},
        {"term": {"org_types": {"value": "非政府组织", "boost": 1.5}}},
        {"term": {"org_types": {"value": "高校", "boost": 1.2}}},
        {"term": {"org_types": {"value": "军工", "boost": 1.2}}},
    ]
    query: Dict[str, Any] = {
        "bool": {
            "must": must,
            "should": soft_should,
        }
    }
    if filters:
        query["bool"]["filter"] = filters
    result = _execute_search(
        query,
        size,
        meta={
            "lookup": "by_name",
            "org_type": ot,
            "alias_name": alias_name if _norm_text(alias_name) != _norm_text(text) else None,
        },
    )
    result["tool"] = "lookup_org_by_name"
    result["input"] = {
        "name": text,
        "alias_name": alias_name if _norm_text(alias_name) != _norm_text(text) else None,
        "location_country": location_country,
        "org_type": org_type,
    }
    hits = result.get("results") or []
    # 别名完整名未命中、仅短名噪声时提示可能未收录
    if alias_name and _norm_text(alias_name) != _norm_text(text):
        alias_hit = any(
            _norm_text(alias_name) in _norm_text(h.get("name") or "")
            or _norm_text(alias_name) in _norm_text(h.get("job_company_name") or "")
            for h in hits
        )
        if not alias_hit:
            result["coverage_hint"] = (
                f"库内未命中更完整名称「{alias_name}」；下列多为短名「{text}」的同名/"
                "近义噪声（城市、报刊、协会缩写等）。若目标是知名机构，可判定为"
                "领英组织库未收录，勿将噪声条目当作目标组织交付。"
            )
    # 消歧提示：首条与次条分数接近时
    if len(hits) >= 2:
        s0 = float(hits[0].get("_score") or 0)
        s1 = float(hits[1].get("_score") or 0)
        if s0 > 0 and s1 / s0 >= 0.75:
            result["disambiguation_hint"] = (
                "前几条得分接近，请结合 org_types / location / biz_tags / "
                "description 确认目标组织；可加 org_type 或 location_country 收窄。"
            )
    return result


def _topic_clause(topic: str, *, fallback_text: bool = False) -> dict:
    """议题条件：优先 term 匹配入库 biz_tags（含 涉华 展开）；可选回退全文。"""
    key = (topic or "").strip()
    if not key:
        return {}
    canon = _normalize_biz_tag(key)
    should: List[dict] = []
    if canon and (canon in BIZ_TAGS or canon.startswith("涉华-") or canon in _BIZ_TAG_EXPAND):
        clause = _biz_tag_filter_clause(canon)
        if clause:
            should.append(clause)
        if not fallback_text:
            return {"bool": {"should": should, "minimum_should_match": 1}}
    kws = (
        _TOPIC_KEYWORDS.get(key)
        or _TOPIC_KEYWORDS.get(_norm_text(key))
        or _TOPIC_KEYWORDS.get(canon or "")
        or [key]
    )
    for kw in kws:
        should.append(_match_phrase("description", kw))
        should.append(_match_phrase("name", kw))
        should.append(_match_phrase("industry", kw))
    return {"bool": {"should": [c for c in should if c], "minimum_should_match": 1}}


def search_orgs(
    *,
    org_type: Optional[str] = None,
    org_types: Optional[List[str]] = None,
    org_type_l2: Optional[str] = None,
    org_type_l2s: Optional[List[str]] = None,
    location_country: Optional[str] = None,
    location_region: Optional[str] = None,
    name_keyword: Optional[str] = None,
    industry_keywords: Optional[List[str]] = None,
    description_keywords: Optional[List[str]] = None,
    biz_tag: Optional[str] = None,
    biz_tags: Optional[List[str]] = None,
    topic: Optional[str] = None,
    topics: Optional[List[str]] = None,
    topic_fallback_text: bool = False,
    exclude_org_types: Optional[List[str]] = None,
    include_ids: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
    founded_from: Optional[str] = None,
    founded_to: Optional[str] = None,
    min_tag_confidence: Optional[float] = None,
    has_biz_tags: Optional[bool] = None,
    search_after: Optional[List[Any]] = None,
    size: int = DEFAULT_SIZE,
) -> Dict[str, Any]:
    """结构化组织检索（一级/二级类型 + 入库业务标签）。"""
    filters: List[dict] = []
    must: List[dict] = []
    must_not: List[dict] = []
    selective = 0
    tag_expand_applied: Dict[str, List[str]] = {}

    ids = [i.strip() for i in (include_ids or []) if (i or "").strip()]
    if ids:
        selective += 1
        if len(ids) > INCLUDE_IDS_MAX:
            raise ValueError(f"include_ids 最多 {INCLUDE_IDS_MAX} 个")
        filters.append(
            {
                "bool": {
                    "should": [
                        {"terms": {"org_id": ids}},
                        {"terms": {"job_company_id": ids}},
                        {"ids": {"values": ids}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    ex_ids = [i.strip() for i in (exclude_ids or []) if (i or "").strip()]
    if ex_ids:
        must_not.append(
            {
                "bool": {
                    "should": [
                        {"terms": {"org_id": ex_ids[:INCLUDE_IDS_MAX]}},
                        {"ids": {"values": ex_ids[:INCLUDE_IDS_MAX]}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    type_list: List[str] = []
    if org_type:
        type_list.append(org_type)
    type_list.extend(org_types or [])
    norm_types = []
    for t in type_list:
        nt = _normalize_org_type(t)
        if nt:
            norm_types.append(nt)
    norm_types = list(dict.fromkeys(norm_types))
    if norm_types:
        selective += 1
        filters.append({"terms": {"org_types": norm_types}})

    for t in exclude_org_types or []:
        nt = _normalize_org_type(t)
        if nt:
            must_not.append({"term": {"org_types": nt}})

    # 二级类型（OR）
    l2_raw: List[str] = []
    if org_type_l2:
        l2_raw.append(org_type_l2)
    l2_raw.extend(org_type_l2s or [])
    norm_l2 = []
    for t in l2_raw:
        nt = _normalize_org_type_l2(t)
        if nt:
            norm_l2.append(nt)
    norm_l2 = list(dict.fromkeys(norm_l2))
    if norm_l2:
        selective += 1
        filters.append({"terms": {"org_type_l2": norm_l2}})

    # 业务标签强过滤（多标签 AND；涉华自动展开为 涉华 + 涉华-*）
    tag_raw: List[str] = []
    if biz_tag:
        tag_raw.append(biz_tag)
    tag_raw.extend(biz_tags or [])
    norm_tags = []
    for t in tag_raw:
        nt = _normalize_biz_tag(t)
        if nt:
            norm_tags.append(nt)
    norm_tags = list(dict.fromkeys(norm_tags))
    for nt in norm_tags:
        selective += 1
        clause = _biz_tag_filter_clause(nt)
        if clause:
            filters.append(clause)
            expanded = _expand_biz_tag_values(nt)
            if len(expanded) > 1:
                tag_expand_applied[nt] = expanded

    country = _norm_text(location_country)
    if country:
        selective += 1
        variants = [country]
        if country in ("usa", "us", "united states of america", "u.s.", "u.s.a."):
            variants = ["united states", "usa", "us"]
        elif country in ("uk", "great britain", "england"):
            variants = ["united kingdom", "uk"]
        filters.append(
            {
                "bool": {
                    "should": [
                        c
                        for v in variants
                        for c in [_term_keyword("location_country", v)]
                        if c
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    region = _norm_text(location_region)
    if region:
        selective += 1
        filters.append(_term_keyword("location_region", region))

    name_kw = (name_keyword or "").strip()
    if name_kw:
        selective += 1
        must.append(
            {
                "bool": {
                    "should": [
                        _match_phrase("name", name_kw),
                        _match_phrase("job_company_name", name_kw),
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    ind_kws = [k for k in (industry_keywords or []) if (k or "").strip()]
    if ind_kws:
        selective += 1
        should = []
        for kw in ind_kws:
            should.append(_match_phrase("industry", kw.strip()))
        filters.append(
            {"bool": {"should": [c for c in should if c], "minimum_should_match": 1}}
        )

    desc_kws = [k for k in (description_keywords or []) if (k or "").strip()]
    if desc_kws:
        selective += 1
        should = []
        for kw in desc_kws:
            should.append(_match_phrase("description", kw.strip()))
            should.append(_match_phrase("name", kw.strip()))
        must.append(
            {"bool": {"should": [c for c in should if c], "minimum_should_match": 1}}
        )

    topic_list: List[str] = []
    if topic:
        topic_list.append(topic)
    topic_list.extend(topics or [])
    topic_list = [t for t in topic_list if (t or "").strip()]
    topic_norm_set = set(norm_tags)
    topics_applied: List[str] = []
    for t in topic_list:
        canon = _normalize_biz_tag(t)
        if canon and canon in topic_norm_set:
            continue
        selective += 1
        topics_applied.append(canon or t)
        must.append(_topic_clause(t, fallback_text=topic_fallback_text))
        if canon:
            expanded = _expand_biz_tag_values(canon)
            if len(expanded) > 1:
                tag_expand_applied[canon] = expanded

    if founded_from or founded_to:
        selective += 1
        rng: Dict[str, Any] = {}
        if founded_from:
            rng["gte"] = str(founded_from).strip()
        if founded_to:
            rng["lte"] = str(founded_to).strip()
        filters.append({"range": {"founded": rng}})

    conf_threshold: Optional[float] = None
    if min_tag_confidence is not None:
        try:
            conf_threshold = float(min_tag_confidence)
        except (TypeError, ValueError):
            raise ValueError("min_tag_confidence 必须是数字") from None
        if conf_threshold < 0 or conf_threshold > 1:
            raise ValueError("min_tag_confidence 范围应为 0~1")
        # tag_confidence 当前未建倒排索引，不能进 ES range；见下方客户端过滤
        selective += 1

    if has_biz_tags is True:
        selective += 1
        filters.append({"exists": {"field": "biz_tags"}})
    elif has_biz_tags is False:
        selective += 1
        must_not.append({"exists": {"field": "biz_tags"}})

    if selective < 1:
        raise ValueError(
            "至少提供一个条件：org_type / org_type_l2 / biz_tag / 国家 / 名称 / "
            "行业 / topic / description_keywords / include_ids / min_tag_confidence"
        )

    query: Dict[str, Any] = {"bool": {}}
    if must:
        query["bool"]["must"] = must
    if filters:
        query["bool"]["filter"] = filters
    if must_not:
        query["bool"]["must_not"] = must_not
    if not must and not filters:
        query = {"match_all": {}}

    # 分页用稳定排序；无 search_after 时仍可按相关性，但为支持翻页统一 org_id 排序
    use_sort = ORG_SEARCH_SORT
    sa = search_after if search_after else None

    # 置信度未建索引时：多取若干页再客户端过滤，尽量凑满 size
    fetch_size = size
    if conf_threshold is not None:
        fetch_size = MAX_SIZE

    result = _execute_search(
        query,
        fetch_size,
        meta={
            "tool": "search_orgs",
            "selective_conditions": selective,
            "org_types": norm_types or None,
            "org_type_l2": norm_l2 or None,
            "biz_tags": norm_tags or None,
            "biz_tag_expand": tag_expand_applied or None,
            "topics": topics_applied or topic_list or None,
            "topic_fallback_text": bool(topic_fallback_text) if topic_list else None,
            "min_tag_confidence": conf_threshold,
            "has_biz_tags": has_biz_tags,
            "candidate_pool_size": len(ids) if ids else None,
            "note": (
                "biz_tag=涉华 会展开命中 涉华-*；标签以 llm_deepseek 为主；"
                "topic_fallback_text=true 时额外弱匹配 description/name；"
                "翻页使用 next_search_after"
                if (norm_tags or topics_applied)
                else "org_type_l2 / biz_tags 为入库预打标；翻页用 next_search_after"
            ),
        },
        sort=use_sort,
        search_after=sa,
    )

    if conf_threshold is not None:
        kept = []
        for item in result.get("results") or []:
            raw = item.get("tag_confidence")
            try:
                if raw is not None and float(raw) >= conf_threshold:
                    kept.append(item)
            except (TypeError, ValueError):
                continue
            if len(kept) >= size:
                break
        result["results"] = kept
        result["returned"] = len(kept)
        result["meta"] = dict(result.get("meta") or {})
        result["meta"]["min_tag_confidence_mode"] = (
            "client_side_filter：tag_confidence 未建 ES 倒排，"
            "仅对本批拉取结果过滤；total_hits 仍为过滤前估计"
        )
        note = result["meta"].get("note") or ""
        result["meta"]["note"] = (
            note + "；min_tag_confidence 为客户端过滤"
        ).strip("；")

    result["tool"] = "search_orgs"
    result["input"] = {
        "org_type": org_type,
        "org_types": org_types,
        "org_type_l2": org_type_l2,
        "org_type_l2s": org_type_l2s,
        "location_country": location_country,
        "location_region": location_region,
        "name_keyword": name_keyword,
        "industry_keywords": industry_keywords,
        "description_keywords": description_keywords,
        "biz_tag": biz_tag,
        "biz_tags": biz_tags,
        "topic": topic,
        "topics": topics,
        "topic_fallback_text": topic_fallback_text,
        "exclude_org_types": exclude_org_types,
        "include_ids_count": len(ids),
        "exclude_ids_count": len(ex_ids),
        "founded_from": founded_from,
        "founded_to": founded_to,
        "min_tag_confidence": min_tag_confidence,
        "has_biz_tags": has_biz_tags,
        "search_after": sa,
        "size": min(max(int(size or DEFAULT_SIZE), 1), MAX_SIZE),
    }
    return result


def cluster_health() -> Dict[str, Any]:
    h = _es("GET", "/_cluster/health", timeout=15)
    cnt = _es("GET", f"/{ORG_INDEX_NAME}/_count", timeout=15)
    return {
        "cluster": ES_HOST,
        "cluster_name": h.get("cluster_name"),
        "status": h.get("status"),
        "nodes": h.get("number_of_nodes"),
        "org_index": ORG_INDEX_NAME,
        "org_count": cnt.get("count"),
    }

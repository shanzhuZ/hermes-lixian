"""身份信息 ES 检索客户端（纯 stdlib HTTP）。"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urljoin, urlparse

# ── 配置加载 ──

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

IDENTITY_INDEX = os.environ.get(
    "IDENTITY_INDEX", "dw_identity_info_lk_country_wise_new_all"
)
DEFAULT_SIZE = 20
MAX_SIZE = 50
MAX_HITS_GUARD = 10000

SUMMARY_SOURCE_FIELDS = [
    "unique_id",
    "id",
    "full_name",
    "first_name",
    "last_name",
    "gender",
    "job_title",
    "job_company_name",
    "industry",
    "location_country",
    "location_region",
    "location_locality",
    "countries",
    "linkedin_url",
    "linkedin_username",
    "linkedin_id",
    "work_email",
    "summary",
    "source",
    "add_time",
    # 供结果自检（sanitize 时压成 brief，并丢掉超大 skills/interests）
    "education",
    "experience",
    "job_company_location_country",
]

_SENSITIVE_TOP_KEYS = {"associated_epi", "query"}
_EDU_BRIEF_MAX = 6
_EXP_BRIEF_MAX = 6
_SUMMARY_MAX_CHARS = 280
# search_persons 专用上限：单条含 skills 时 size=40 约 128k 字符会截断丢 unique_id
SEARCH_PERSONS_MAX_SIZE = 20
# 二次筛选白名单上限（配合 search_after 分页攒池）
INCLUDE_IDS_MAX = 500
# 人员结构化检索分页排序（与 collapse 字段一致）
SEARCH_PERSONS_SORT = [{"unique_id.keyword": "asc"}]
# 无 collapse 时单页拉取：每轮向 ES 多取，去重凑满 size
SEARCH_PERSONS_FETCH_SIZE = 50
SEARCH_PERSONS_FETCH_ROUNDS = 10
_RETIRED_TITLE_PHRASES = [
    "retired",
    "semi retired",
    "semi-retired",
    "seriously retired",
]


def _brief_education(education: Any) -> List[dict]:
    """压缩 education 数组，便于模型核对「在某国求学」。"""
    out: List[dict] = []
    if not isinstance(education, list):
        return out
    for e in education:
        if len(out) >= _EDU_BRIEF_MAX:
            break
        if not isinstance(e, dict):
            continue
        school = e.get("school")
        name = None
        country = None
        if isinstance(school, dict):
            name = school.get("name")
            loc = school.get("location") or {}
            if isinstance(loc, dict):
                country = loc.get("country")
        elif isinstance(school, str):
            name = school
        degrees = e.get("degrees")
        if isinstance(degrees, list):
            deg = ", ".join(str(d) for d in degrees[:2] if d)
        else:
            deg = degrees
        item = {
            "school": name,
            "country": country,
            "degrees": deg or None,
        }
        if item["school"] or item["country"]:
            out.append(item)
    return out


def _brief_experience(experience: Any) -> List[dict]:
    """压缩 experience，便于核对工作国家/公司。"""
    out: List[dict] = []
    if not isinstance(experience, list):
        return out
    for e in experience:
        if len(out) >= _EXP_BRIEF_MAX:
            break
        if not isinstance(e, dict):
            continue
        company = e.get("company") or {}
        title = e.get("title") or {}
        if not isinstance(company, dict):
            company = {}
        if not isinstance(title, dict):
            title = {}
        loc = company.get("location") or {}
        if not isinstance(loc, dict):
            loc = {}
        item = {
            "company": company.get("name"),
            "title": title.get("name"),
            "country": loc.get("country"),
        }
        if item["company"] or item["title"] or item["country"]:
            out.append(item)
    return out


def _sanitize_hit(hit: dict) -> dict:
    cleaned = dict(hit)
    for key in list(cleaned.keys()):
        if key in _SENSITIVE_TOP_KEYS:
            cleaned.pop(key, None)
    # 显式丢掉超大字段（即使 _source 误带上）
    for heavy in ("skills", "interests", "emails", "phone_numbers", "mobile_phone"):
        cleaned.pop(heavy, None)
    summary = cleaned.get("summary")
    if isinstance(summary, str) and len(summary) > _SUMMARY_MAX_CHARS:
        cleaned["summary"] = summary[:_SUMMARY_MAX_CHARS] + "…"
    # 用 brief 替换完整 education/experience，控制体积
    if "education" in cleaned:
        cleaned["education_brief"] = _brief_education(cleaned.pop("education"))
    if "experience" in cleaned:
        cleaned["experience_brief"] = _brief_experience(cleaned.pop("experience"))
    return cleaned


def _auth_header() -> str | None:
    if ES_USERNAME and ES_PASSWORD:
        encoded = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()
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
        raise RuntimeError(f"ES HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"ES 连接失败: {e.reason}")
    except OSError as e:
        raise RuntimeError(f"ES 网络错误: {e}")


def _total_hits(resp: dict) -> int:
    total = resp.get("hits", {}).get("total", 0)
    if isinstance(total, dict):
        return total.get("value", 0)
    return total


def _norm_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _norm_phone(value: str) -> str:
    return re.sub(r"\D+", "", (value or "").strip())


def _norm_email(value: str) -> str:
    return (value or "").strip().lower()


def _uniq_keep(seq: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in seq:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _term_keyword(field: str, value: str) -> dict:
    v = _norm_text(value)
    if not v:
        return {}
    return {"term": {f"{field}.keyword": v}}


def _term_keyword_variants(field: str, values: List[str]) -> List[dict]:
    clauses: List[dict] = []
    for value in _uniq_keep(values):
        clause = _term_keyword(field, value)
        if clause:
            clauses.append(clause)
    return clauses


def _match_phrase(field: str, value: str, *, boost: float = 1.0) -> dict:
    text = (value or "").strip()
    if not text:
        return {}
    body: Dict[str, Any] = {"query": text}
    if boost != 1.0:
        body["boost"] = boost
    return {"match_phrase": {field: body}}


def _normalize_linkedin_input(raw: str) -> Dict[str, Any]:
    """规范领英 URL / username / id。"""
    text = (raw or "").strip()
    out: Dict[str, Any] = {
        "raw": text,
        "normalized": None,
        "username": None,
        "linkedin_id": None,
        "variants": [],
    }
    if not text:
        return out

    variants: List[str] = []
    username = None
    linkedin_id = None

    if text.isdigit():
        linkedin_id = text
        variants.extend([text, f"linkedin.com/in/{text}"])

    work = text
    if "://" not in work and re.match(r"^(www\.)?linkedin\.com/", work, re.I):
        work = "https://" + work.lstrip("/")

    if "://" in work or work.lower().startswith("www."):
        if work.lower().startswith("www."):
            work = "https://" + work
        parsed = urlparse(work)
        host = (parsed.netloc or "").lower().lstrip("www.")
        if "linkedin.com" in host:
            path = unquote(parsed.path or "").strip("/")
            parts = [p for p in path.split("/") if p]
            if parts:
                if parts[0].lower() == "in" and len(parts) >= 2:
                    username = parts[1]
                elif parts[0].lower() == "company" and len(parts) >= 2:
                    variants.append(f"linkedin.com/company/{parts[1]}")
                else:
                    username = parts[-1]
    elif "/" not in text and not text.isdigit():
        username = text.lstrip("@")

    if username:
        username = username.split("?")[0].split("#")[0]
        out["username"] = username
        variants.extend(
            [
                f"linkedin.com/in/{username}",
                f"www.linkedin.com/in/{username}",
                f"https://linkedin.com/in/{username}",
                f"https://www.linkedin.com/in/{username}",
                username,
            ]
        )
        out["normalized"] = f"linkedin.com/in/{username}"

    if linkedin_id:
        out["linkedin_id"] = linkedin_id
        variants.append(linkedin_id)

    if not variants and text:
        variants.append(text)
        out["normalized"] = text

    out["variants"] = _uniq_keep(variants)
    return out


def _format_hits(resp: dict, *, include_detail: bool = False) -> List[dict]:
    hits = resp.get("hits", {}).get("hits", [])
    results = []
    for h in hits:
        results.append(_format_one_hit(h, include_detail=include_detail))
    return results


def _format_one_hit(h: dict, *, include_detail: bool = False) -> dict:
    item = {
        "_id": h.get("_id"),
        "_score": round(h.get("_score", 0) or 0, 4),
        **(h.get("_source") or {}),
    }
    if not include_detail:
        item = _sanitize_hit(item)
    return item


def _build_search_body(
    query: dict,
    size: int,
    *,
    include_detail: bool = False,
    sort: Optional[List[dict]] = None,
    search_after: Optional[List[Any]] = None,
    size_cap: Optional[int] = None,
    collapse: bool = True,
) -> dict:
    cap = size_cap if size_cap is not None else MAX_SIZE
    body: Dict[str, Any] = {
        "query": query,
        "size": min(max(size, 1), cap),
        "track_total_hits": MAX_HITS_GUARD + 1,
    }
    # ES 不允许 collapse 与 search_after 并用；人员分页关闭 collapse
    if collapse and not search_after:
        body["collapse"] = {"field": "unique_id.keyword"}
    if sort:
        body["sort"] = sort
    if search_after:
        body["search_after"] = search_after
    if not include_detail:
        body["_source"] = SUMMARY_SOURCE_FIELDS
    return body


def _execute_search(
    query: dict,
    size: int = DEFAULT_SIZE,
    *,
    include_detail: bool = False,
    meta: Optional[Dict[str, Any]] = None,
    sort: Optional[List[dict]] = None,
    search_after: Optional[List[Any]] = None,
    size_cap: Optional[int] = None,
    collapse: bool = True,
) -> Dict[str, Any]:
    body = _build_search_body(
        query,
        size,
        include_detail=include_detail,
        sort=sort,
        search_after=search_after,
        size_cap=size_cap,
        collapse=collapse and not search_after,
    )
    resp = _es("POST", f"/{IDENTITY_INDEX}/_search", body, timeout=120)
    total = _total_hits(resp)
    raw_hits = resp.get("hits", {}).get("hits", []) or []
    hits = _format_hits(resp, include_detail=include_detail)
    truncated = total > MAX_HITS_GUARD
    # collapse 后仍可能返回若干条；仅在「过宽且 0 命中」时硬拒
    if truncated and not hits:
        return {
            "index": IDENTITY_INDEX,
            "error": (
                f"命中数超过 {MAX_HITS_GUARD}，条件过宽且无法返回样本。"
                "请补充国家、公司、职位等限定后再查。"
            ),
            "total_hits": f">{MAX_HITS_GUARD}",
            "returned": 0,
            "results": [],
            "is_sample": True,
            "meta": meta or {},
            "took_ms": resp.get("took"),
        }
    out: Dict[str, Any] = {
        "index": IDENTITY_INDEX,
        "total_hits": f">{MAX_HITS_GUARD}" if truncated else total,
        "returned": len(hits),
        "results": hits,
        "meta": meta or {},
        "took_ms": resp.get("took"),
    }
    out["is_sample"] = bool(truncated)
    if truncated:
        out["warning"] = (
            f"条件较宽（估计命中 >{MAX_HITS_GUARD}），以下仅为样本（is_sample=true），"
            "非过滤精确名单；请继续收窄条件或基于 unique_id / 姓名精确核验。"
        )
    # 分页游标（search_persons 传入 sort 时启用）
    req_size = int(body.get("size") or size)
    if sort:
        if raw_hits and len(raw_hits) >= req_size:
            last_sort = raw_hits[-1].get("sort")
            out["next_search_after"] = last_sort
            out["has_more"] = last_sort is not None
        else:
            out["next_search_after"] = None
            out["has_more"] = False
    return out


def _paginate_unique_persons(
    query: dict,
    want_size: int,
    *,
    search_after: Optional[List[Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """无 collapse 的 unique_id 分页：多轮拉取→去重→凑满 want_size，游标用最后保留记录。

    ES 禁止 collapse + search_after；直接 size 去重会导致页变稀且漏人。
    """
    want = min(max(int(want_size or DEFAULT_SIZE), 1), SEARCH_PERSONS_MAX_SIZE)
    fetch_n = min(MAX_SIZE, max(SEARCH_PERSONS_FETCH_SIZE, want * 3))
    collected: List[dict] = []
    seen_uid: set = set()
    cursor: Optional[List[Any]] = list(search_after) if search_after else None
    last_kept_sort: Optional[List[Any]] = None
    total = 0
    took_ms = 0
    rounds = 0
    batch_full = False
    raw_after_last_kept = False

    while len(collected) < want and rounds < SEARCH_PERSONS_FETCH_ROUNDS:
        rounds += 1
        body = _build_search_body(
            query,
            fetch_n,
            include_detail=False,
            sort=SEARCH_PERSONS_SORT,
            search_after=cursor,
            size_cap=MAX_SIZE,
            collapse=False,
        )
        resp = _es("POST", f"/{IDENTITY_INDEX}/_search", body, timeout=120)
        took_ms += int(resp.get("took") or 0)
        total = _total_hits(resp)
        raw_hits = resp.get("hits", {}).get("hits", []) or []
        if not raw_hits:
            break

        batch_full = len(raw_hits) >= fetch_n
        filled_this_batch = False
        for i, h in enumerate(raw_hits):
            item = _format_one_hit(h, include_detail=False)
            uid = item.get("unique_id")
            sort_vals = h.get("sort")
            if not uid:
                # 无 unique_id 无法稳定去重/分页，跳过
                continue
            if uid in seen_uid:
                continue
            seen_uid.add(uid)
            collected.append(item)
            if sort_vals is not None:
                last_kept_sort = sort_vals
            if len(collected) >= want:
                filled_this_batch = True
                raw_after_last_kept = i < len(raw_hits) - 1
                break

        if filled_this_batch:
            break

        # 本批去重后仍不足：游标推到本批最后一条 raw，继续下一轮
        next_cur = raw_hits[-1].get("sort")
        if not next_cur or next_cur == cursor:
            break
        cursor = next_cur

    truncated = total > MAX_HITS_GUARD
    if truncated and not collected:
        return {
            "index": IDENTITY_INDEX,
            "error": (
                f"命中数超过 {MAX_HITS_GUARD}，条件过宽且无法返回样本。"
                "请补充国家、公司、职位等限定后再查。"
            ),
            "total_hits": f">{MAX_HITS_GUARD}",
            "returned": 0,
            "results": [],
            "is_sample": True,
            "has_more": False,
            "next_search_after": None,
            "meta": meta or {},
            "took_ms": took_ms,
        }

    page = collected[:want]
    if len(page) >= want and last_kept_sort is not None:
        # 凑满一页：本批保留点后还有 raw，或本批 ES 已拉满，则认为可能有下一页
        has_more = bool(raw_after_last_kept or batch_full)
        next_sa: Optional[List[Any]] = last_kept_sort if has_more else None
    else:
        has_more = False
        next_sa = None

    out: Dict[str, Any] = {
        "index": IDENTITY_INDEX,
        "total_hits": f">{MAX_HITS_GUARD}" if truncated else total,
        "returned": len(page),
        "results": page,
        "meta": {
            **(meta or {}),
            "pagination": {
                "fetch_rounds": rounds,
                "fetch_size": fetch_n,
                "unique_collected": len(collected),
            },
        },
        "took_ms": took_ms,
        "is_sample": bool(truncated),
        "has_more": has_more,
        "next_search_after": next_sa,
    }
    if truncated:
        out["warning"] = (
            f"条件较宽（估计命中 >{MAX_HITS_GUARD}），以下仅为样本（is_sample=true），"
            "非过滤精确名单；请继续收窄条件或基于 unique_id / 姓名精确核验。"
        )
    return out


def lookup_by_linkedin(linkedin_input: str, size: int = DEFAULT_SIZE) -> Dict[str, Any]:
    norm = _normalize_linkedin_input(linkedin_input)
    should: List[dict] = []
    should.extend(_term_keyword_variants("linkedin_url", norm.get("variants") or []))
    if norm.get("username"):
        should.extend(_term_keyword_variants("linkedin_username", [norm["username"]]))
    if norm.get("linkedin_id"):
        should.extend(_term_keyword_variants("linkedin_id", [norm["linkedin_id"]]))
        should.extend(_term_keyword_variants("profiles.id", [norm["linkedin_id"]]))
    for variant in norm.get("variants") or []:
        should.extend(_term_keyword_variants("profiles.url", [variant]))
    if norm.get("username"):
        should.extend(_term_keyword_variants("profiles.username", [norm["username"]]))

    if not should:
        raise ValueError("linkedin_input 不能为空")

    query = {"bool": {"should": should, "minimum_should_match": 1}}
    result = _execute_search(
        query,
        size,
        meta={"normalized": norm.get("normalized"), "variants": norm.get("variants")},
    )
    result["tool"] = "lookup_by_linkedin"
    result["input"] = linkedin_input
    return result


def lookup_by_work_email(email: str, size: int = DEFAULT_SIZE) -> Dict[str, Any]:
    normalized = _norm_email(email)
    if not normalized or "@" not in normalized:
        raise ValueError("email 格式无效")
    should = _term_keyword_variants("work_email", [normalized])
    should.extend(_term_keyword_variants("emails.address", [normalized]))
    query = {"bool": {"should": should, "minimum_should_match": 1}}
    result = _execute_search(query, size, meta={"normalized": normalized})
    result["tool"] = "lookup_by_work_email"
    result["input"] = email
    return result


def lookup_by_phone(phone: str, size: int = DEFAULT_SIZE) -> Dict[str, Any]:
    digits = _norm_phone(phone)
    if len(digits) < 6:
        raise ValueError("phone 位数过短")
    should = _term_keyword_variants("mobile_phone", [digits, phone.strip()])
    should.extend(_term_keyword_variants("phone_numbers", [digits, phone.strip()]))
    query = {"bool": {"should": should, "minimum_should_match": 1}}
    result = _execute_search(query, size, meta={"normalized": digits})
    result["tool"] = "lookup_by_phone"
    result["input"] = phone
    return result


def lookup_by_name(
    name: str,
    *,
    country: Optional[str] = None,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    size: int = DEFAULT_SIZE,
) -> Dict[str, Any]:
    person_name = (name or "").strip()
    if not person_name:
        raise ValueError("name 不能为空")
    country_v = _norm_text(country)
    company_v = _norm_text(company)
    title_v = (job_title or "").strip()
    if not any([country_v, company_v, title_v]):
        raise ValueError("姓名检索至少需提供 country、company、job_title 之一")

    must: List[dict] = [_match_phrase("full_name", person_name, boost=3)]
    filters: List[dict] = []
    if country_v:
        filters.append(
            {
                "bool": {
                    "should": [
                        _term_keyword("location_country", country_v),
                        _term_keyword("countries", country_v),
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if company_v:
        filters.append(_term_keyword("job_company_name", company_v))
    if title_v:
        filters.append(_match_phrase("job_title", title_v))

    query = {"bool": {"must": must, "filter": filters}}
    result = _execute_search(
        query,
        size,
        meta={
            "name": person_name,
            "country": country_v or None,
            "company": company_v or None,
            "job_title": title_v or None,
        },
    )
    result["tool"] = "lookup_by_name"
    result["input"] = {
        "name": person_name,
        "country": country,
        "company": company,
        "job_title": job_title,
    }
    return result


def search_by_company(
    company_name: str,
    *,
    country: Optional[str] = None,
    job_title: Optional[str] = None,
    job_title_level: Optional[str] = None,
    current_only: bool = True,
    size: int = DEFAULT_SIZE,
) -> Dict[str, Any]:
    company_v = _norm_text(company_name)
    if not company_v:
        raise ValueError("company_name 不能为空")

    must: List[dict] = []
    if current_only:
        must.append(_term_keyword("job_company_name", company_v))
    else:
        phrase = _match_phrase("experience.company.name", company_name.strip())
        if phrase:
            must.append(phrase)

    filters: List[dict] = []
    country_v = _norm_text(country)
    if country_v:
        filters.append(
            {
                "bool": {
                    "should": [
                        _term_keyword("location_country", country_v),
                        _term_keyword("countries", country_v),
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    title_v = (job_title or "").strip()
    if title_v:
        if current_only:
            filters.append(_match_phrase("job_title", title_v))
        else:
            filters.append(_match_phrase("experience.title.name", title_v))
    level_v = _norm_text(job_title_level)
    if level_v:
        field = "job_title_levels" if current_only else "experience.title.levels"
        filters.append(_term_keyword(field, level_v))

    query: Dict[str, Any] = {"bool": {"must": must}}
    if filters:
        query["bool"]["filter"] = filters

    result = _execute_search(
        query,
        size,
        meta={"company_name": company_v, "current_only": current_only},
    )
    result["tool"] = "search_by_company"
    result["input"] = {
        "company_name": company_name,
        "country": country,
        "job_title": job_title,
        "job_title_level": job_title_level,
        "current_only": current_only,
    }
    return result


def search_by_profile(
    *,
    industry: Optional[str] = None,
    location_country: Optional[str] = None,
    location_region: Optional[str] = None,
    location_locality: Optional[str] = None,
    skills: Optional[List[str]] = None,
    interests: Optional[List[str]] = None,
    job_title: Optional[str] = None,
    min_years_experience: Optional[int] = None,
    size: int = DEFAULT_SIZE,
) -> Dict[str, Any]:
    filters: List[dict] = []
    provided = 0

    industry_v = _norm_text(industry)
    if industry_v:
        provided += 1
        filters.append(
            {
                "bool": {
                    "should": [
                        _term_keyword("industry", industry_v),
                        _term_keyword("job_company_industry", industry_v),
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    country_v = _norm_text(location_country)
    if country_v:
        provided += 1
        filters.append(
            {
                "bool": {
                    "should": [
                        _term_keyword("location_country", country_v),
                        _term_keyword("countries", country_v),
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    region_v = _norm_text(location_region)
    if region_v:
        provided += 1
        filters.append(
            {
                "bool": {
                    "should": [
                        _term_keyword("location_region", region_v),
                        _term_keyword("regions", region_v),
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    locality_v = _norm_text(location_locality)
    if locality_v:
        provided += 1
        filters.append(_term_keyword("location_locality", locality_v))

    skill_list = [_norm_text(s) for s in (skills or []) if _norm_text(s)]
    if skill_list:
        provided += 1
        for skill in skill_list:
            filters.append(_term_keyword("skills", skill))

    interest_list = [_norm_text(i) for i in (interests or []) if _norm_text(i)]
    if interest_list:
        provided += 1
        for interest in interest_list:
            filters.append(_term_keyword("interests", interest))

    title_v = (job_title or "").strip()
    if title_v:
        provided += 1
        filters.append(_match_phrase("job_title", title_v))

    if min_years_experience is not None:
        provided += 1
        filters.append(
            {"range": {"inferred_years_experience": {"gte": int(min_years_experience)}}}
        )

    if provided < 2:
        raise ValueError("画像检索至少需提供 2 个条件（行业/地理位置/技能/兴趣/职位/年限等）")

    query = {"bool": {"filter": filters}}
    result = _execute_search(query, size, meta={"conditions": provided})
    result["tool"] = "search_by_profile"
    result["input"] = {
        "industry": industry,
        "location_country": location_country,
        "location_region": location_region,
        "location_locality": location_locality,
        "skills": skills,
        "interests": interests,
        "job_title": job_title,
        "min_years_experience": min_years_experience,
    }
    return result


def get_by_unique_id(unique_id: str, *, include_detail: bool = True) -> Dict[str, Any]:
    uid = (unique_id or "").strip()
    if not uid:
        raise ValueError("unique_id 不能为空")
    query = {
        "bool": {
            "should": [_term_keyword("unique_id", uid)],
            "minimum_should_match": 1,
        }
    }
    result = _execute_search(query, 1, include_detail=include_detail)
    result["tool"] = "get_by_unique_id"
    result["input"] = {"unique_id": uid, "include_detail": include_detail}
    return result


# ── 业务标签推导（仅查询时展开，不写回库）──

_COUNTRY_ALIASES: Dict[str, List[str]] = {
    "china": ["china"],
    "hong kong": ["hong kong", "hongkong"],
    "taiwan": ["taiwan"],
    "united states": [
        "united states",
        "usa",
        "us",
        "united states of america",
        "u.s.",
        "u.s.a.",
    ],
    "united kingdom": ["united kingdom", "uk", "great britain", "england"],
    "australia": ["australia"],
    "canada": ["canada"],
    "japan": ["japan"],
    "singapore": ["singapore"],
    "germany": ["germany"],
    "france": ["france"],
}

_BIZ_TAG_COUNTRY: Dict[str, str] = {
    "china_related": "china",
    "涉华": "china",
    "taiwan_related": "taiwan",
    "涉台": "taiwan",
    "hongkong_related": "hong kong",
    "涉港": "hong kong",
}

# 经历/机构名弱信号（location 常为 null 时的补充；strict 模式不启用）
# 注意：不要用 "chinese"——会误伤 American College of Traditional Chinese Medicine 等
_COUNTRY_NAME_HINTS: Dict[str, List[str]] = {
    "china": ["china", "beijing", "shanghai", "shenzhen", "guangzhou", "hangzhou"],
    "hong kong": ["hong kong", "hongkong"],
    "taiwan": ["taiwan", "taipei"],
}

# 行业/职位：默认仅当前主职字段（经历段 industry 易跨段误配）
_INDUSTRY_FIELDS_DEFAULT = ["industry", "job_company_industry"]
_INDUSTRY_FIELDS_RELAXED = [
    "industry",
    "job_company_industry",
    "experience.company.industry",
]
_TITLE_FIELDS_DEFAULT = ["job_title"]
_TITLE_FIELDS_RELAXED = ["job_title", "experience.title.name"]


def _retired_must_not() -> List[dict]:
    """排除当前/历史职位含 retired 的文档（近似 NOT 退休）。"""
    clauses: List[dict] = []
    for phrase in _RETIRED_TITLE_PHRASES:
        clauses.append({"match_phrase": {"job_title": {"query": phrase}}})
        clauses.append({"match_phrase": {"experience.title.name": {"query": phrase}}})
    return clauses


def _annotate_evidence(hit: dict, target_countries: List[str]) -> dict:
    """根据 brief 标注硬证据，便于模型交付时分类。"""
    targets = {_norm_text(c) for c in target_countries if _norm_text(c)}
    if not targets:
        return hit
    flags: List[str] = []
    for e in hit.get("education_brief") or []:
        if not isinstance(e, dict):
            continue
        if _norm_text(e.get("country")) in targets:
            flags.append("edu_in_target")
    for e in hit.get("experience_brief") or []:
        if not isinstance(e, dict):
            continue
        if _norm_text(e.get("country")) not in targets:
            continue
        title = _norm_text(e.get("title"))
        if any(p in title for p in ("retired", "semi retired", "semi-retired")):
            flags.append("work_in_target_retired_suspect")
        else:
            flags.append("work_in_target")
    # 去重保序
    hit["evidence_flags"] = list(dict.fromkeys(flags))
    return hit


def _country_variants(country: str) -> List[str]:
    key = _norm_text(country)
    if not key:
        return []
    if key in _COUNTRY_ALIASES:
        return list(_COUNTRY_ALIASES[key])
    for canon, aliases in _COUNTRY_ALIASES.items():
        if key == canon or key in aliases:
            return list(aliases)
    return [key]


def _canon_country_key(country: str) -> str:
    key = _norm_text(country)
    if key in _COUNTRY_ALIASES:
        return key
    for canon, aliases in _COUNTRY_ALIASES.items():
        if key == canon or key in aliases:
            return canon
    return key


def _location_country_clause(
    country: str, *, include_countries_history: bool = False
) -> dict:
    """现居国家：默认仅 location_country，不命中历史 countries[]。"""
    variants = _country_variants(country)
    if not variants:
        return {}
    should: List[dict] = []
    for v in variants:
        clause = _term_keyword("location_country", v)
        if clause:
            should.append(clause)
        if include_countries_history:
            hist = _term_keyword("countries", v)
            if hist:
                should.append(hist)
    if not should:
        return {}
    return {"bool": {"should": should, "minimum_should_match": 1}}


def _work_country_clause(country: str, *, strict: bool = False) -> dict:
    """在某地有工作经历。

    strict=True：仅公司地点字段（job_company_location_country /
    experience.company.location.country），不含公司名弱信号。
    """
    variants = _country_variants(country)
    if not variants:
        return {}
    should: List[dict] = []
    for v in variants:
        should.append(_term_keyword("experience.company.location.country", v))
        should.append(_term_keyword("job_company_location_country", v))
        if not strict:
            should.append({"match_phrase": {"experience.location_names": {"query": v}}})
    if not strict:
        canon = _canon_country_key(country)
        for hint in _COUNTRY_NAME_HINTS.get(canon, []):
            should.append({"match_phrase": {"experience.company.name": {"query": hint}}})
            should.append({"match_phrase": {"job_company_name": {"query": hint}}})
    return {"bool": {"should": [c for c in should if c], "minimum_should_match": 1}}


def _edu_country_clause(country: str, *, strict: bool = False) -> dict:
    """在某地有教育经历。strict 时仅学校地点字段。"""
    variants = _country_variants(country)
    if not variants:
        return {}
    should: List[dict] = []
    for v in variants:
        should.append(_term_keyword("education.school.location.country", v))
    if not strict:
        canon = _canon_country_key(country)
        for hint in _COUNTRY_NAME_HINTS.get(canon, []):
            should.append({"match_phrase": {"education.school.name": {"query": hint}}})
    return {"bool": {"should": [c for c in should if c], "minimum_should_match": 1}}


def _biz_tag_clause(biz_tag: str, *, strict: bool = False) -> dict:
    """业务标签查询时推导，不写库。"""
    raw = (biz_tag or "").strip()
    key = _norm_text(raw)
    country = _BIZ_TAG_COUNTRY.get(key) or _BIZ_TAG_COUNTRY.get(raw)
    if not country:
        raise ValueError(
            "biz_tag 仅支持 china_related/涉华、taiwan_related/涉台、hongkong_related/涉港"
        )
    work = _work_country_clause(country, strict=strict)
    edu = _edu_country_clause(country, strict=strict)
    should = [c for c in (work, edu) if c]
    return {"bool": {"should": should, "minimum_should_match": 1}}


def _keyword_should(fields: List[str], keywords: List[str]) -> List[dict]:
    clauses: List[dict] = []
    for kw in keywords:
        text = (kw or "").strip()
        if not text:
            continue
        for field in fields:
            clauses.append({"match_phrase": {field: {"query": text}}})
    return clauses


def search_persons(
    *,
    biz_tag: Optional[str] = None,
    work_country: Optional[str] = None,
    edu_country: Optional[str] = None,
    location_country: Optional[str] = None,
    company_keyword: Optional[str] = None,
    school_keyword: Optional[str] = None,
    industry_keywords: Optional[List[str]] = None,
    title_keywords: Optional[List[str]] = None,
    exclude_industry_keywords: Optional[List[str]] = None,
    exclude_title_keywords: Optional[List[str]] = None,
    exclude_edu_country: Optional[str] = None,
    exclude_work_country: Optional[str] = None,
    exclude_retired: bool = False,
    include_ids: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
    strict: bool = False,
    include_countries_history: bool = False,
    include_experience_industry: bool = False,
    condition_logic: str = "and",
    search_after: Optional[List[Any]] = None,
    size: int = DEFAULT_SIZE,
) -> Dict[str, Any]:
    """结构化人员检索：经历/标签推导 + 二次筛选（include_ids）+ 分页。

    strict=True：关闭公司/学校名弱信号；行业/职位仅当前主职字段。
    location_country 默认只匹配现居 location_country；
    include_countries_history=True 时才并入历史 countries[]。
    exclude_edu_country / exclude_work_country：硬排除该国教育/工作经历。
    exclude_retired：排除职位含 retired 的文档。
    include_experience_industry：行业词是否扩展到经历段 industry（默认否）。
    condition_logic：and=条件全部成立；or=业务/经历/地域/机构/行业/职位条件满足任一。
    search_after：上一页返回的 next_search_after，用于翻页攒 unique_id 池。
    """
    logic = _norm_text(condition_logic) or "and"
    if logic not in ("and", "or"):
        raise ValueError("condition_logic 仅支持 and / or")

    filters: List[dict] = []
    should: List[dict] = []
    must_not: List[dict] = []
    selective = 0
    size = min(max(int(size or DEFAULT_SIZE), 1), SEARCH_PERSONS_MAX_SIZE)

    def _add_cond(clause: Optional[dict]) -> None:
        nonlocal selective
        if not clause:
            return
        selective += 1
        if logic == "or":
            should.append(clause)
        else:
            filters.append(clause)

    ids = [i.strip() for i in (include_ids or []) if (i or "").strip()]
    if ids:
        selective += 1
        if len(ids) > INCLUDE_IDS_MAX:
            raise ValueError(
                f"include_ids 最多 {INCLUDE_IDS_MAX} 个，请缩小上一轮集合或分页后合并"
            )
        # 白名单始终是硬过滤（池约束），不受 condition_logic 影响
        filters.append({"terms": {"unique_id.keyword": ids}})

    ex_ids = [i.strip() for i in (exclude_ids or []) if (i or "").strip()]
    if ex_ids:
        must_not.append({"terms": {"unique_id.keyword": ex_ids[:INCLUDE_IDS_MAX]}})

    if exclude_retired:
        must_not.extend(_retired_must_not())

    if exclude_edu_country and _norm_text(exclude_edu_country):
        clause = _edu_country_clause(exclude_edu_country, strict=True)
        if clause:
            must_not.append(clause)

    if exclude_work_country and _norm_text(exclude_work_country):
        clause = _work_country_clause(exclude_work_country, strict=True)
        if clause:
            must_not.append(clause)

    if biz_tag:
        _add_cond(_biz_tag_clause(biz_tag, strict=strict))

    if work_country:
        _add_cond(_work_country_clause(work_country, strict=strict))

    if edu_country:
        _add_cond(_edu_country_clause(edu_country, strict=strict))

    if location_country and _norm_text(location_country):
        # 现居国家始终作为硬过滤（AND），不参与 condition_logic=or 的「满足任一」
        selective += 1
        use_history = include_countries_history and not strict
        clause = _location_country_clause(
            location_country, include_countries_history=use_history
        )
        if clause:
            filters.append(clause)

    company_kw = (company_keyword or "").strip()
    if company_kw:
        if strict:
            _add_cond({"match_phrase": {"job_company_name": {"query": company_kw}}})
        else:
            _add_cond(
                {
                    "bool": {
                        "should": [
                            {
                                "match_phrase": {
                                    "job_company_name": {"query": company_kw}
                                }
                            },
                            {
                                "match_phrase": {
                                    "experience.company.name": {"query": company_kw}
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )

    school_kw = (school_keyword or "").strip()
    if school_kw:
        _add_cond(
            {"match_phrase": {"education.school.name": {"query": school_kw}}}
        )

    ind_kws = [k for k in (industry_keywords or []) if (k or "").strip()]
    if ind_kws:
        use_relaxed_ind = include_experience_industry and not strict
        ind_fields = (
            _INDUSTRY_FIELDS_RELAXED if use_relaxed_ind else _INDUSTRY_FIELDS_DEFAULT
        )
        _add_cond(
            {
                "bool": {
                    "should": _keyword_should(ind_fields, ind_kws),
                    "minimum_should_match": 1,
                }
            }
        )

    title_kws = [k for k in (title_keywords or []) if (k or "").strip()]
    if title_kws:
        title_fields = _TITLE_FIELDS_DEFAULT if strict else _TITLE_FIELDS_RELAXED
        _add_cond(
            {
                "bool": {
                    "should": _keyword_should(title_fields, title_kws),
                    "minimum_should_match": 1,
                }
            }
        )

    for kw in exclude_industry_keywords or []:
        text = (kw or "").strip()
        if text:
            for field in _INDUSTRY_FIELDS_DEFAULT:
                must_not.append({"match_phrase": {field: {"query": text}}})

    ex_title_fields = _TITLE_FIELDS_DEFAULT if strict else _TITLE_FIELDS_RELAXED
    for kw in exclude_title_keywords or []:
        text = (kw or "").strip()
        if text:
            for field in ex_title_fields:
                must_not.append({"match_phrase": {field: {"query": text}}})

    # or 模式：should 里至少要有一条可选条件（仅 include_ids 不够表达「满足任一」）
    or_optional = len(should)
    if logic == "or" and or_optional < 1 and not ids:
        raise ValueError(
            "condition_logic=or 时请至少提供 biz_tag / 经历国家 / 现居 / 公司学校 / "
            "行业职位 之一"
        )

    if selective < 1:
        raise ValueError(
            "至少提供一个检索条件（biz_tag / 经历国家 / 现居国家 / 公司或学校 / "
            "行业或职位关键词 / include_ids）"
        )

    hard_anchors = any(
        [
            work_country,
            edu_country,
            location_country and _norm_text(location_country),
            company_kw,
            school_kw,
            ind_kws,
            title_kws,
            ids,
        ]
    )
    if biz_tag and not hard_anchors:
        if strict:
            raise ValueError(
                "strict 模式下仅 biz_tag 过宽，请再加 location_country / work_country / "
                "edu_country / 公司学校 / 行业职位关键词之一"
            )

    query: Dict[str, Any] = {"bool": {}}
    if filters:
        query["bool"]["filter"] = filters
    if should:
        query["bool"]["should"] = should
        query["bool"]["minimum_should_match"] = 1
    if must_not:
        query["bool"]["must_not"] = must_not
    if not query["bool"]:
        raise ValueError("未能构造有效查询")

    sa: Optional[List[Any]] = None
    if search_after is not None:
        if isinstance(search_after, list) and search_after:
            sa = search_after
        else:
            raise ValueError("search_after 须为上一页返回的 next_search_after 数组")

    target_countries: List[str] = []
    if biz_tag:
        raw = (biz_tag or "").strip()
        key = _norm_text(raw)
        c = _BIZ_TAG_COUNTRY.get(key) or _BIZ_TAG_COUNTRY.get(raw)
        if c:
            target_countries.append(c)
    for c in (work_country, edu_country, exclude_edu_country, exclude_work_country):
        if c and _norm_text(c):
            target_countries.append(_canon_country_key(c))

    result = _paginate_unique_persons(
        query,
        size,
        search_after=sa,
        meta={
            "tool": "search_persons",
            "selective_conditions": selective,
            "condition_logic": logic,
            "biz_tag_derived": bool(biz_tag),
            "strict": strict,
            "include_countries_history": bool(
                include_countries_history and not strict
            ),
            "location_match": (
                "location_country+countries"
                if (include_countries_history and not strict)
                else "location_country_only"
            ),
            "broad_biz_tag_only": bool(biz_tag and not hard_anchors),
            "candidate_pool_size": len(ids) if ids else None,
            "exclude_retired": bool(exclude_retired),
            "exclude_edu_country": _norm_text(exclude_edu_country) or None,
            "exclude_work_country": _norm_text(exclude_work_country) or None,
            "industry_fields": (
                "relaxed_with_experience"
                if (include_experience_industry and not strict)
                else "current_only"
            ),
            "size_capped_to": SEARCH_PERSONS_MAX_SIZE,
            "include_ids_max": INCLUDE_IDS_MAX,
            "note_include_ids": (
                "include_ids 为白名单；total_hits 仍可能反映宽条件估计，请以 returned/"
                "candidate_pool_size 为准"
                if ids
                else None
            ),
            "note_pagination": (
                "若 has_more=true，将 next_search_after 原样传入下一轮 search_after；"
                "合并各页 unique_id 后再用 include_ids 二次筛选。"
                "分页已按 unique_id 去重凑满 size，游标对齐最后保留记录。"
            ),
        },
    )
    for hit in result.get("results") or []:
        if isinstance(hit, dict):
            _annotate_evidence(hit, target_countries)

    result["tool"] = "search_persons"
    result["input"] = {
        "biz_tag": biz_tag,
        "work_country": work_country,
        "edu_country": edu_country,
        "location_country": location_country,
        "company_keyword": company_keyword,
        "school_keyword": school_keyword,
        "industry_keywords": industry_keywords,
        "title_keywords": title_keywords,
        "exclude_industry_keywords": exclude_industry_keywords,
        "exclude_title_keywords": exclude_title_keywords,
        "exclude_edu_country": exclude_edu_country,
        "exclude_work_country": exclude_work_country,
        "exclude_retired": exclude_retired,
        "include_ids_count": len(ids),
        "exclude_ids_count": len(ex_ids),
        "strict": strict,
        "include_countries_history": include_countries_history,
        "include_experience_industry": include_experience_industry,
        "condition_logic": logic,
        "search_after": sa,
        "size": size,
    }
    return result


def cluster_health() -> Dict[str, Any]:
    h = _es("GET", "/_cluster/health", timeout=15)
    return {
        "cluster": ES_HOST,
        "cluster_name": h.get("cluster_name"),
        "status": h.get("status"),
        "nodes": h.get("number_of_nodes"),
    }

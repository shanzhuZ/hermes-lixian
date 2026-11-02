# -*- coding: utf-8 -*-
"""工具原始返回 → 归一化 hit 列表（四 Skill 共用）。
payload 统一为 [{label, value}, ...]，便于前端卡片展示。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


def _parse(result: Any) -> Any:
    if result is None:
        return None
    if isinstance(result, (dict, list)):
        return result
    if isinstance(result, str):
        s = result.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return {"_raw": s[:2000]}
    return {"_raw": str(result)[:2000]}


def _maybe_json(val: Any) -> Any:
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return val
        if s[0] in "{[":
            try:
                return json.loads(s)
            except Exception:
                return val
    return val


def _unwrap(data: Any) -> Any:
    """剥掉 MCP / Hermes 常见外壳：result 字符串、structuredContent、success+data 等。"""
    data = _maybe_json(data)
    if not isinstance(data, dict):
        return data

    # Apify：优先 structuredContent.items（result 常为 toon 文本，不可 JSON 解析）
    sc = data.get("structuredContent")
    if isinstance(sc, dict) and isinstance(sc.get("items"), list):
        return sc["items"]

    # Hermes MCP 常见：{"result": "<json string or object>", "structuredContent": {...}}
    if "result" in data:
        inner = _maybe_json(data.get("result"))
        if isinstance(inner, (dict, list)) and inner not in ("", None):
            return _unwrap(inner)
    if isinstance(sc, dict):
        if "result" in sc:
            return _unwrap(sc)
        # run 状态对象原样返回，由调用方决定是否丢弃
        if "runId" in sc and "status" in sc:
            return sc
        return _unwrap(sc)

    # web_search: {"success": true, "data": {"web": [...]}}
    if isinstance(data.get("data"), dict):
        d = data["data"]
        if isinstance(d.get("web"), list):
            return d["web"]
        if isinstance(d.get("results"), list):
            return d["results"]
        # 继续往下剥
        if any(k in d for k in ("items", "tweets", "users", "posts", "videos")):
            return _unwrap(d)

    # YouTube / Apify dataset: {kind, items:[...]} / {items:[...]}
    if isinstance(data.get("items"), list):
        return data["items"]

    # web_extract: {results:[{url,title,content}]}
    if isinstance(data.get("results"), list):
        return data["results"]

    return data


def _as_list(obj: Any) -> List[Any]:
    obj = _unwrap(obj)
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("web", "data", "tweets", "users", "results", "items", "videos", "statuses", "posts"):
            v = obj.get(k)
            v = _maybe_json(v) if isinstance(v, str) else v
            if isinstance(v, list):
                return v
            if isinstance(v, dict) and isinstance(v.get("web"), list):
                return v["web"]
        return [obj]
    return []


def _clip(s: Any, n: int = 500) -> str:
    if s is None:
        return ""
    t = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return t if len(t) <= n else t[:n]


def _field(label: str, value: Any, max_len: int = 2000) -> Dict[str, str]:
    if value is None:
        v = ""
    elif isinstance(value, str):
        v = value
    else:
        v = json.dumps(value, ensure_ascii=False)
    if len(v) > max_len:
        v = v[:max_len]
    return {"label": str(label), "value": v}


def _fields(*pairs: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for p in pairs:
        if not p or len(p) < 2:
            continue
        out.append(_field(str(p[0]), p[1]))
    return out


# 英文键 → 中文 label（other 展平时用）
_KEY_LABEL_ZH = {
    "result": "结果",
    "structuredContent": "结构化内容",
    "success": "成功",
    "data": "数据",
    "error": "错误",
    "output": "输出",
    "exit_code": "退出码",
    "url": "原文链接",
    "title": "标题",
    "description": "摘要",
    "content": "正文",
    "text": "正文",
    "author": "账号",
    "screen_name": "账号",
    "username": "账号",
    "id": "ID",
    "created_at": "发布时间",
    "likes": "点赞数",
    "retweets": "转发数",
    "query": "检索词",
    "source": "来源",
}


def to_label_value_list(payload: Any) -> List[Dict[str, str]]:
    """任意结构 → [{label,value}]；已是该格式则规范化。"""
    if payload is None:
        return []
    if isinstance(payload, list):
        if not payload:
            return []
        if all(isinstance(x, dict) and ("label" in x or "Label" in x) for x in payload):
            out = []
            for x in payload:
                lab = x.get("label") if "label" in x else x.get("Label")
                val = x.get("value") if "value" in x else x.get("Value")
                out.append(_field(str(lab or ""), val))
            return out
        return [_field("项" + str(i + 1), item) for i, item in enumerate(payload[:40])]
    if isinstance(payload, dict):
        out = []
        for k, v in list(payload.items())[:60]:
            lab = _KEY_LABEL_ZH.get(str(k), str(k))
            # 避免把整段巨大 JSON 再当 value
            if isinstance(v, (dict, list)):
                v = _clip(v, 1500)
            out.append(_field(lab, v))
        return out
    return [_field("内容", payload)]


def _dedupe(prefix: str, key: str) -> str:
    raw = (prefix + ":" + (key or "")).strip(":")
    if len(raw) <= 180:
        return raw
    h = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
    return raw[:160] + ":" + h


def _hit(
    *,
    dedupe_key: str,
    hit_type: str,
    title: str,
    summary: str,
    platform: str,
    tool_name: str,
    fields: List[Dict[str, str]],
) -> Dict[str, Any]:
    return {
        "dedupeKey": dedupe_key,
        "hitType": hit_type,
        "title": title,
        "summary": summary,
        "platform": platform,
        "sourceTool": tool_name,
        "payload": fields,
        "fields": fields,
    }


def build_hits(tool_name: str, args: Any, result: Any, tool_call_id: str = "") -> List[Dict[str, Any]]:
    t = (tool_name or "").lower()
    raw = _parse(result)
    data = _unwrap(raw)
    args = args if isinstance(args, dict) else {}
    hits: List[Dict[str, Any]] = []

    # 过程类 / 非业务内容：不入库 hit（仍可由 tool_event 审计）
    if "skill_view" in t or t in (
        "todo", "memory", "xw_submit_plan", "xw_phase_done", "xw_set_skill", "terminal", "skill_manage"
    ):
        return []
    if "apify" in t and ("get_actor_run" in t or "abort_actor" in t):
        return []

    if "apify" in t:
        hits.extend(_apify(tool_name, args, raw, data))
    elif "get_user_info" in t or "get_user_by_screen" in t or (t.endswith("get_user") and "tweet" not in t):
        hits.extend(_profile_user(tool_name, args, data, "twitter"))
    elif "get_user_tweets" in t or "user_tweets" in t:
        hits.extend(_twitter_tweets_list(tool_name, args, data))
    elif "search_tweets" in t or ("tweet" in t and "search" in t):
        hits.extend(_twitter_tweets_list(tool_name, args, data))
    elif "get_tweet" in t:
        hits.extend(_single_post(tool_name, args, data, "twitter"))
    elif "youtube" in t or "search-videos" in t or "search_videos" in t:
        hits.extend(_youtube(tool_name, args, data))
    elif "get-channel" in t or "get_channel" in t:
        hits.extend(_youtube_channel(tool_name, args, data))
    elif "weibo" in t and ("user" in t or "profile" in t):
        hits.extend(_profile_user(tool_name, args, data, "weibo"))
    elif "web_extract" in t:
        hits.extend(_web_extract(tool_name, args, data))
    elif "firecrawl" in t and "scrape" in t:
        hits.extend(_firecrawl_scrape(tool_name, args, data))
    elif "web_search" in t or ("firecrawl" in t and "search" in t) or t == "web_search":
        hits.extend(_generic_search(tool_name, args, data))
    elif t.endswith("_search") or ("search" in t and "session" not in t):
        hits.extend(_generic_search(tool_name, args, data))
    else:
        if data is not None and not _is_apify_run_status(data):
            key = tool_call_id or hashlib.sha1(
                (tool_name + "|" + _clip(data, 200)).encode("utf-8", errors="replace")
            ).hexdigest()[:20]
            fields = to_label_value_list(data)
            if not fields:
                fields = [_field("原始结果", _clip(data, 2000))]
            fields.insert(0, _field("工具", tool_name))
            hits.append(_hit(
                dedupe_key=_dedupe("other", key),
                hit_type="other",
                title=tool_name or "tool",
                summary=_clip(data, 300),
                platform="",
                tool_name=tool_name,
                fields=fields,
            ))

    for h in hits:
        h.setdefault("sourceTool", tool_name)
        h["payload"] = to_label_value_list(h.get("fields") or h.get("payload"))
        h["fields"] = h["payload"]
        if tool_call_id:
            h["toolEventId"] = tool_call_id
    return hits


def _profile_user(tool_name: str, args: dict, data: Any, platform: str) -> List[Dict[str, Any]]:
    user = _unwrap(data)
    if isinstance(user, list) and user:
        user = user[0]
    if isinstance(user, dict):
        user = user.get("user") or user.get("data") or user
    if not isinstance(user, dict):
        return []
    screen = (
        user.get("screen_name")
        or user.get("username")
        or user.get("author")
        or user.get("handle")
        or user.get("name_en")
        or args.get("screen_name")
        or args.get("username")
        or ""
    )
    screen = str(screen).lstrip("@").strip()
    if not screen:
        return []
    name = user.get("name") or user.get("display_name") or screen
    home = ""
    if platform == "twitter":
        home = "https://twitter.com/" + screen
    elif platform == "weibo":
        home = str(user.get("profile_url") or user.get("url") or "")
    fields = _fields(
        ("平台", platform),
        ("账号", screen),
        ("昵称", name),
        ("简介", user.get("description") or user.get("bio") or ""),
        ("粉丝数", user.get("followers_count") or user.get("followers") or ""),
        ("关注数", user.get("friends_count") or user.get("following") or ""),
        ("头像", user.get("profile_image_url") or user.get("profile_image_url_https") or user.get("avatar") or ""),
        ("主页链接", home or user.get("url") or ""),
        ("已认证", "是" if user.get("verified") else "否"),
    )
    return [_hit(
        dedupe_key=_dedupe(platform + ":profile", screen),
        hit_type="profile",
        title="@" + screen if platform == "twitter" else screen,
        summary=_clip(user.get("description") or user.get("bio") or name, 300),
        platform=platform,
        tool_name=tool_name,
        fields=fields,
    )]


def _twitter_tweets_list(tool_name: str, args: dict, data: Any) -> List[Dict[str, Any]]:
    """search_tweets / get_user_tweets：条目字段多为 id/author/text/likes/retweets。"""
    out: List[Dict[str, Any]] = []
    screen_hint = str(args.get("screen_name") or args.get("username") or "").lstrip("@")
    for i, item in enumerate(_as_list(data)[:30]):
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or item.get("id_str") or item.get("tweet_id") or "").strip()
        if not tid or tid == "0":
            continue
        text = item.get("text") or item.get("full_text") or item.get("content") or ""
        author = (
            item.get("author")
            or item.get("screen_name")
            or item.get("username")
            or screen_hint
            or ""
        )
        if isinstance(item.get("user"), dict):
            author = author or item["user"].get("screen_name") or item["user"].get("username") or ""
        author = str(author).lstrip("@")
        url = item.get("url") or item.get("permalink") or ""
        if not url and author:
            url = "https://twitter.com/%s/status/%s" % (author, tid)
        elif not url:
            url = "https://twitter.com/i/web/status/%s" % tid
        fields = _fields(
            ("平台", "twitter"),
            ("帖子ID", tid),
            ("账号", author),
            ("正文", text),
            ("发布时间", item.get("created_at") or item.get("published_at") or ""),
            ("原文链接", url),
            ("转发数", item.get("retweets") or item.get("retweet_count") or ""),
            ("点赞数", item.get("likes") or item.get("favorite_count") or item.get("like_count") or ""),
        )
        out.append(_hit(
            dedupe_key=_dedupe("twitter:post", tid),
            hit_type="post",
            title=_clip(text, 80) or tid,
            summary=_clip(text, 300),
            platform="twitter",
            tool_name=tool_name,
            fields=fields,
        ))
    return out


def _single_post(tool_name: str, args: dict, data: Any, platform: str) -> List[Dict[str, Any]]:
    tw = _unwrap(data)
    if isinstance(tw, list) and tw:
        tw = tw[0]
    if isinstance(tw, dict):
        tw = tw.get("tweet") or tw.get("data") or tw
    if not isinstance(tw, dict):
        return []
    tid = str(tw.get("id") or tw.get("id_str") or tw.get("tweet_id") or args.get("id") or "").strip()
    if not tid or tid == "0":
        return []
    text = tw.get("full_text") or tw.get("text") or tw.get("content") or ""
    user_obj = tw.get("user") if isinstance(tw.get("user"), dict) else {}
    author = (
        tw.get("author")
        or tw.get("screen_name")
        or user_obj.get("screen_name")
        or tw.get("username")
        or ""
    )
    author = str(author).lstrip("@")
    url = tw.get("url") or tw.get("permalink") or ""
    if not url and platform == "twitter" and author:
        url = "https://twitter.com/%s/status/%s" % (author, tid)
    fields = _fields(
        ("平台", platform),
        ("帖子ID", tid),
        ("账号", author),
        ("正文", text),
        ("发布时间", tw.get("created_at") or tw.get("published_at") or ""),
        ("原文链接", url),
        ("转发数", tw.get("retweets") or tw.get("retweet_count") or ""),
        ("点赞数", tw.get("likes") or tw.get("favorite_count") or tw.get("like_count") or ""),
    )
    return [_hit(
        dedupe_key=_dedupe(platform + ":post", tid),
        hit_type="post",
        title=_clip(text, 80) or tid,
        summary=_clip(text, 300),
        platform=platform,
        tool_name=tool_name,
        fields=fields,
    )]


def _yt_video_id(item: dict) -> str:
    vid = item.get("videoId") or item.get("id")
    if isinstance(vid, dict):
        vid = vid.get("videoId") or vid.get("channelId") or ""
    return str(vid or "").strip()


def _yt_snippet(item: dict) -> dict:
    sn = item.get("snippet")
    return sn if isinstance(sn, dict) else {}


def _youtube(tool_name: str, args: dict, data: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(_as_list(data)[:30]):
        if not isinstance(item, dict):
            continue
        sn = _yt_snippet(item)
        vid = _yt_video_id(item)
        if not vid or vid == "0":
            continue
        # 跳过频道/播放列表结果（仅要视频）
        id_obj = item.get("id")
        if isinstance(id_obj, dict) and id_obj.get("kind") and "video" not in str(id_obj.get("kind")):
            if not id_obj.get("videoId"):
                continue
        title = sn.get("title") or item.get("title") or item.get("name") or vid
        desc = sn.get("description") or item.get("description") or ""
        channel = sn.get("channelTitle") or item.get("channelTitle") or item.get("channel") or ""
        published = sn.get("publishedAt") or item.get("publishedAt") or item.get("published_at") or ""
        url = item.get("url") or ("https://www.youtube.com/watch?v=" + vid)
        fields = _fields(
            ("平台", "youtube"),
            ("视频ID", vid),
            ("标题", title),
            ("频道", channel),
            ("简介", desc),
            ("发布时间", published),
            ("原文链接", url),
            ("播放量", item.get("viewCount") or item.get("views") or sn.get("viewCount") or ""),
        )
        out.append(_hit(
            dedupe_key=_dedupe("youtube:post", vid),
            hit_type="post",
            title=_clip(title, 120),
            summary=_clip(desc or title, 300),
            platform="youtube",
            tool_name=tool_name,
            fields=fields,
        ))
    return out


def _youtube_channel(tool_name: str, args: dict, data: Any) -> List[Dict[str, Any]]:
    ch = _unwrap(data)
    if isinstance(ch, list) and ch:
        ch = ch[0]
    if isinstance(ch, dict):
        ch = ch.get("channel") or ch.get("data") or ch
        sn = ch.get("snippet") if isinstance(ch.get("snippet"), dict) else {}
    else:
        return []
    if not isinstance(ch, dict):
        return []
    cid = str(
        ch.get("channelId")
        or (ch.get("id") if not isinstance(ch.get("id"), dict) else ch.get("id", {}).get("channelId"))
        or args.get("channelId")
        or ""
    ).strip()
    if not cid:
        return []
    title = sn.get("title") if sn else (ch.get("title") or ch.get("name") or cid)
    desc = (sn.get("description") if sn else None) or ch.get("description") or ""
    url = ch.get("url") or ("https://www.youtube.com/channel/" + cid)
    fields = _fields(
        ("平台", "youtube"),
        ("频道ID", cid),
        ("频道名", title),
        ("简介", desc),
        ("订阅数", ch.get("subscriberCount") or ch.get("subscribers") or ""),
        ("主页链接", url),
    )
    return [_hit(
        dedupe_key=_dedupe("youtube:profile", cid),
        hit_type="profile",
        title=_clip(title, 120),
        summary=_clip(desc or title, 300),
        platform="youtube",
        tool_name=tool_name,
        fields=fields,
    )]


def _generic_search(tool_name: str, args: dict, data: Any) -> List[Dict[str, Any]]:
    """web_search：data.web[] → url/title/description。"""
    out: List[Dict[str, Any]] = []
    q = str(args.get("query") or args.get("q") or "")
    items = _as_list(data)
    # 若仍是整包 dict（未剥开），再试 data.web
    if len(items) == 1 and isinstance(items[0], dict) and not items[0].get("url") and not items[0].get("link"):
        inner = items[0].get("data") or items[0]
        if isinstance(inner, dict) and isinstance(inner.get("web"), list):
            items = inner["web"]
        elif isinstance(data, dict) and isinstance((data.get("data") or {}).get("web"), list):
            items = data["data"]["web"]

    for i, item in enumerate(items[:20]):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or item.get("href") or "").strip()
        title = item.get("title") or item.get("name") or ""
        snippet = (
            item.get("description")
            or item.get("snippet")
            or item.get("content")
            or item.get("body")
            or ""
        )
        # 跳过「整包查询对象」假条目
        if not url and not title and not snippet:
            continue
        if not title:
            title = url or q or ("结果" + str(i + 1))
        key = url or (q + ":" + str(i) + ":" + _clip(title, 40))
        source = item.get("source") or item.get("site") or item.get("category") or ""
        if not source and url:
            try:
                from urllib.parse import urlparse
                source = urlparse(url).netloc or ""
            except Exception:
                source = ""
        fields = _fields(
            ("检索词", q),
            ("标题", title),
            ("摘要", snippet),
            ("原文链接", url),
            ("来源", source or ""),
        )
        out.append(_hit(
            dedupe_key=_dedupe("search", key),
            hit_type="search",
            title=_clip(title, 120),
            summary=_clip(snippet or title, 300),
            platform="",
            tool_name=tool_name,
            fields=fields,
        ))
    return out


def _web_extract(tool_name: str, args: dict, data: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(_as_list(data)[:20]):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or args.get("url") or "").strip()
        title = item.get("title") or url or ("摘取" + str(i + 1))
        content = item.get("content") or item.get("text") or item.get("markdown") or ""
        if not url and not content:
            continue
        fields = _fields(
            ("标题", title),
            ("正文", _clip(content, 2000)),
            ("原文链接", url),
            ("错误", item.get("error") or ""),
        )
        out.append(_hit(
            dedupe_key=_dedupe("document", url or str(i)),
            hit_type="document",
            title=_clip(title, 120),
            summary=_clip(content, 300),
            platform="",
            tool_name=tool_name,
            fields=fields,
        ))
    return out


def _firecrawl_scrape(tool_name: str, args: dict, data: Any) -> List[Dict[str, Any]]:
    obj = _unwrap(data)
    if isinstance(obj, list):
        return _web_extract(tool_name, args, obj)
    if not isinstance(obj, dict):
        return []
    # firecrawl 常见：{markdown, metadata:{title,sourceURL}, ...}
    meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    url = str(
        meta.get("sourceURL")
        or meta.get("url")
        or obj.get("url")
        or args.get("url")
        or ""
    ).strip()
    title = meta.get("title") or obj.get("title") or url or "页面"
    content = obj.get("markdown") or obj.get("content") or obj.get("text") or ""
    if not url and not content:
        return []
    fields = _fields(
        ("标题", title),
        ("正文", _clip(content, 2000)),
        ("原文链接", url),
        ("来源", meta.get("ogSiteName") or meta.get("siteName") or ""),
    )
    return [_hit(
        dedupe_key=_dedupe("document", url or title),
        hit_type="document",
        title=_clip(title, 120),
        summary=_clip(content, 300),
        platform="",
        tool_name=tool_name,
        fields=fields,
    )]


def _is_apify_run_status(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    return bool(obj.get("runId") and obj.get("status") is not None) and "items" not in obj


def _dotget(item: dict, *keys: str) -> Any:
    """支持扁平键 authorMeta.name 与嵌套 authorMeta:{name}。"""
    for k in keys:
        if k in item and item.get(k) not in (None, ""):
            return item.get(k)
        if "." in k:
            cur: Any = item
            ok = True
            for part in k.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    ok = False
                    break
            if ok and cur not in (None, ""):
                return cur
    return None


def _apify_extract_items(raw: Any, data: Any) -> List[Any]:
    if isinstance(raw, dict):
        sc = raw.get("structuredContent")
        if isinstance(sc, dict) and isinstance(sc.get("items"), list):
            return sc["items"]
        if isinstance(raw.get("items"), list):
            return raw["items"]
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def _guess_apify_platform(tool_name: str, item: dict) -> str:
    t = (tool_name or "").lower()
    url = str(
        item.get("url")
        or item.get("webVideoUrl")
        or item.get("videoUrl")
        or item.get("displayUrl")
        or item.get("inputUrl")
        or ""
    ).lower()
    if "tiktok" in t or "tiktok.com" in url or item.get("webVideoUrl") or _dotget(item, "authorMeta.name"):
        if "webVideoUrl" in item or "tiktok" in t or "tiktok.com" in url:
            return "tiktok"
    if "instagram" in t or "instagram.com" in url or item.get("shortCode") or item.get("ownerUsername"):
        return "instagram"
    if "facebook" in t or "facebook.com" in url or "fb.com" in url:
        return "facebook"
    if "telegram" in t or "t.me/" in url or "telegram.me" in url:
        return "telegram"
    if "github" in t or "github.com" in url:
        return "github"
    if item.get("type") == "post" and item.get("message") is not None:
        return "facebook"
    if item.get("username") and (item.get("subscribers") is not None or item.get("title")):
        return "telegram"
    if item.get("id") is not None and item.get("date") and item.get("views") is not None:
        return "telegram"
    return ""


def _apify(tool_name: str, args: dict, raw: Any, data: Any) -> List[Dict[str, Any]]:
    """Apify Actor / get_dataset_items → post/profile；纯 run 状态不落 hit。"""
    if _is_apify_run_status(data) or _is_apify_run_status(
        raw.get("structuredContent") if isinstance(raw, dict) else None
    ):
        return []

    items = _apify_extract_items(raw, data)
    if not items:
        # dataset 空结果（error: no_items）等：不写 other
        if isinstance(data, dict) and (data.get("error") or _is_apify_run_status(data)):
            return []
        return []

    out: List[Dict[str, Any]] = []
    tg_channel = ""
    for item in items[:40]:
        if not isinstance(item, dict):
            continue
        if item.get("error") and len(item) <= 3:
            continue
        platform = _guess_apify_platform(tool_name, item)
        if platform == "tiktok":
            h = _apify_tiktok_item(tool_name, item)
            if h:
                out.append(h)
        elif platform == "instagram":
            h = _apify_instagram_item(tool_name, item)
            if h:
                out.append(h)
        elif platform == "facebook":
            h = _apify_facebook_item(tool_name, item)
            if h:
                out.append(h)
        elif platform == "telegram":
            # 频道头 vs 帖
            if item.get("username") and (
                item.get("subscribers") is not None or item.get("description") is not None
            ) and item.get("id") is None:
                tg_channel = str(item.get("username") or "").lstrip("@")
                h = _apify_telegram_profile(tool_name, item)
                if h:
                    out.append(h)
            else:
                h = _apify_telegram_post(tool_name, item, tg_channel)
                if h:
                    out.append(h)
        elif platform == "github":
            h = _apify_github_item(tool_name, item)
            if h:
                out.append(h)
        else:
            # 未知平台但仍有 URL/正文：按通用 post
            h = _apify_generic_item(tool_name, item)
            if h:
                out.append(h)
    return out


def _apify_tiktok_item(tool_name: str, item: dict) -> Optional[Dict[str, Any]]:
    vid = str(item.get("id") or item.get("videoId") or "").strip()
    url = str(item.get("webVideoUrl") or item.get("videoUrl") or item.get("url") or "").strip()
    author = str(
        _dotget(item, "authorMeta.name", "authorMeta.nickName", "author")
        or ""
    ).lstrip("@")
    text = item.get("text") or item.get("desc") or item.get("title") or ""
    if not vid and url:
        # 从 URL 抽 id
        parts = url.rstrip("/").split("/")
        if parts:
            vid = parts[-1].split("?")[0]
    if not vid and not url:
        return None
    if not url and author and vid:
        url = "https://www.tiktok.com/@%s/video/%s" % (author, vid)
    fields = _fields(
        ("平台", "tiktok"),
        ("视频ID", vid),
        ("账号", author),
        ("正文", text),
        ("发布时间", item.get("createTimeISO") or item.get("createTime") or ""),
        ("原文链接", url),
        ("播放量", item.get("playCount") or item.get("play_count") or ""),
        ("点赞数", item.get("diggCount") or item.get("likes") or ""),
        ("检索词", item.get("searchQuery") or ""),
        ("粉丝数", _dotget(item, "authorMeta.fans") or ""),
    )
    return _hit(
        dedupe_key=_dedupe("tiktok:post", vid or url),
        hit_type="post",
        title=_clip(text, 80) or vid or url,
        summary=_clip(text, 300),
        platform="tiktok",
        tool_name=tool_name,
        fields=fields,
    )


def _apify_instagram_item(tool_name: str, item: dict) -> Optional[Dict[str, Any]]:
    # 账号档案
    if item.get("username") and not (item.get("shortCode") or item.get("caption") or item.get("url")):
        user = str(item.get("username") or "").lstrip("@")
        if not user:
            return None
        home = "https://www.instagram.com/%s/" % user
        fields = _fields(
            ("平台", "instagram"),
            ("账号", user),
            ("昵称", item.get("fullName") or item.get("name") or user),
            ("简介", item.get("biography") or item.get("description") or ""),
            ("粉丝数", item.get("followersCount") or item.get("followers") or ""),
            ("主页链接", home),
        )
        return _hit(
            dedupe_key=_dedupe("instagram:profile", user),
            hit_type="profile",
            title="@" + user,
            summary=_clip(item.get("biography") or user, 300),
            platform="instagram",
            tool_name=tool_name,
            fields=fields,
        )

    code = str(item.get("shortCode") or item.get("id") or "").strip()
    url = str(item.get("url") or item.get("displayUrl") or "").strip()
    if not url and code:
        url = "https://www.instagram.com/p/%s/" % code
    author = str(
        item.get("ownerUsername")
        or _dotget(item, "owner.username")
        or item.get("username")
        or ""
    ).lstrip("@")
    text = item.get("caption") or item.get("text") or item.get("comment") or ""
    if not url and not code:
        return None
    fields = _fields(
        ("平台", "instagram"),
        ("帖子ID", code),
        ("账号", author),
        ("正文", text),
        ("发布时间", item.get("timestamp") or item.get("takenAt") or item.get("created_at") or ""),
        ("原文链接", url),
        ("点赞数", item.get("likesCount") or item.get("likes") or ""),
        ("评论数", item.get("commentsCount") or item.get("comments") or ""),
    )
    return _hit(
        dedupe_key=_dedupe("instagram:post", code or url),
        hit_type="post",
        title=_clip(text, 80) or code or url,
        summary=_clip(text, 300),
        platform="instagram",
        tool_name=tool_name,
        fields=fields,
    )


def _apify_facebook_item(tool_name: str, item: dict) -> Optional[Dict[str, Any]]:
    pid = str(item.get("post_id") or item.get("id") or "").strip()
    url = str(item.get("url") or item.get("postUrl") or "").strip()
    author_obj = item.get("author") if isinstance(item.get("author"), dict) else {}
    author = str(
        author_obj.get("name")
        or _dotget(item, "author.name")
        or item.get("userName")
        or item.get("pageName")
        or ""
    )
    home = ""
    actors = item.get("actors")
    if isinstance(actors, list) and actors and isinstance(actors[0], dict):
        home = str(actors[0].get("url") or "")
        author = author or str(actors[0].get("name") or "")
    text = item.get("message") or item.get("text") or item.get("content") or ""
    if not url and not pid and not text:
        return None
    reactions = item.get("reactions_summary") if isinstance(item.get("reactions_summary"), dict) else {}
    fields = _fields(
        ("平台", "facebook"),
        ("帖子ID", pid),
        ("账号", author),
        ("正文", text),
        ("原文链接", url),
        ("主页链接", home),
        ("反应数", reactions.get("total_reactions") or item.get("likes") or ""),
        ("评论数", _dotget(item, "comments_summary.total_comments") or ""),
    )
    return _hit(
        dedupe_key=_dedupe("facebook:post", pid or url or _clip(text, 40)),
        hit_type="post",
        title=_clip(text, 80) or pid or url,
        summary=_clip(text, 300),
        platform="facebook",
        tool_name=tool_name,
        fields=fields,
    )


def _apify_telegram_profile(tool_name: str, item: dict) -> Optional[Dict[str, Any]]:
    user = str(item.get("username") or "").lstrip("@")
    if not user:
        return None
    home = str(item.get("url") or ("https://t.me/" + user))
    fields = _fields(
        ("平台", "telegram"),
        ("账号", user),
        ("频道名", item.get("title") or user),
        ("简介", item.get("description") or ""),
        ("订阅数", item.get("subscribers") or item.get("members") or ""),
        ("主页链接", home),
    )
    return _hit(
        dedupe_key=_dedupe("telegram:profile", user),
        hit_type="profile",
        title=str(item.get("title") or user),
        summary=_clip(item.get("description") or user, 300),
        platform="telegram",
        tool_name=tool_name,
        fields=fields,
    )


def _apify_telegram_post(tool_name: str, item: dict, channel: str) -> Optional[Dict[str, Any]]:
    pid = str(item.get("id") or item.get("message_id") or "").strip()
    ch = str(item.get("username") or item.get("channel") or channel or "").lstrip("@")
    url = str(item.get("url") or item.get("link") or "").strip()
    if not url and ch and pid:
        url = "https://t.me/%s/%s" % (ch, pid)
    text = item.get("text") or item.get("message") or item.get("content") or ""
    if not pid and not url and not text:
        return None
    # 极简条目（仅 id/date/views）：仍入库，便于前端展示采样
    fields = _fields(
        ("平台", "telegram"),
        ("帖子ID", pid),
        ("账号", ch),
        ("正文", text),
        ("发布时间", item.get("date") or item.get("created_at") or ""),
        ("原文链接", url),
        ("浏览量", item.get("views") or ""),
    )
    return _hit(
        dedupe_key=_dedupe("telegram:post", (ch + ":" + pid) if ch and pid else (url or pid or _clip(text, 40))),
        hit_type="post",
        title=_clip(text, 80) or (ch + "/" + pid if ch and pid else pid or url),
        summary=_clip(text or ("views=" + str(item.get("views") or "")), 300),
        platform="telegram",
        tool_name=tool_name,
        fields=fields,
    )


def _apify_github_item(tool_name: str, item: dict) -> Optional[Dict[str, Any]]:
    url = str(item.get("url") or item.get("html_url") or "").strip()
    login = str(item.get("login") or item.get("username") or item.get("name") or "").strip()
    if not url and login:
        url = "https://github.com/" + login
    if not url and not login:
        return None
    fields = _fields(
        ("平台", "github"),
        ("账号", login),
        ("简介", item.get("bio") or item.get("description") or ""),
        ("主页链接", url),
        ("仓库", item.get("repo") or item.get("full_name") or ""),
    )
    return _hit(
        dedupe_key=_dedupe("github:profile", login or url),
        hit_type="profile",
        title=login or url,
        summary=_clip(item.get("bio") or item.get("description") or login, 300),
        platform="github",
        tool_name=tool_name,
        fields=fields,
    )


def _apify_generic_item(tool_name: str, item: dict) -> Optional[Dict[str, Any]]:
    url = str(item.get("url") or item.get("link") or item.get("webVideoUrl") or "").strip()
    text = item.get("text") or item.get("caption") or item.get("message") or item.get("title") or ""
    pid = str(item.get("id") or item.get("post_id") or "").strip()
    if not url and not text and not pid:
        return None
    fields = _fields(
        ("平台", ""),
        ("ID", pid),
        ("正文", text),
        ("原文链接", url),
    )
    return _hit(
        dedupe_key=_dedupe("apify:post", pid or url or _clip(text, 40)),
        hit_type="post",
        title=_clip(text, 80) or pid or url,
        summary=_clip(text, 300),
        platform="",
        tool_name=tool_name,
        fields=fields,
    )

---
name: live-news-search
description: "Answer live/current-events questions (who arrived, when, how many) via browser-based search, with Chinese-news query patterns and Xinhua-wire verification. Use when the user asks time-sensitive news questions and/or web_search/web_extract is unavailable."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Research, News, Current-Events, Browser-Fallback, Chinese-News]
    related_skills: [blocked-page-recovery, grounded-citations, competitor-news-monitor]
---

# Live News Search

The user in this profile regularly asks time-sensitive current-events
questions in Chinese (APEC summits, leader visits, "who/when/how many").
The web_search/web_extract backend (Firecrawl) can run out of credits
mid-session — plan the browser fallback from the start, don't burn turns
discovering the outage.

## Ladder

1. `web_search` / `web_extract` — cheapest; try once. If the response is a
   provider error (Payment Required, auth, rate limit), do NOT retry the
   same backend in a loop; go straight to (2) and note the outage for the
   user (including the credit-reset date if the error states one).
2. Browser + `cn.bing.com` web search (see "Bing patterns" below).
3. Official event/institution sites for structured facts (schedules,
   delegation lists) — e.g. `apec2026.cn` / `press.apec2026.cn` for the
   2026 Shenzhen APEC. Their news pages are often sparse, but they confirm
   official dates and terminology.
4. Never fabricate live numbers. If the data point ("how many delegates
   today") is not retrievable, say so and offer a verifiable alternative
   (their local MCP databases, or the user supplying the source).

## Bing patterns (browser tool, cn.bing.com)

- **Chinese news needs Chinese queries.** English queries on cn.bing.com
  for current Chinese events return dictionary/encyclopedia junk
  (searching 特朗普 as bare text yields 汉字 "特" dictionary entries).
  Use the full Chinese phrase: `特朗普 APEC 深圳 抵达`, or better the
  official wire phrasing (see below).
- **Steal phrasings from Bing 热点.** The cn.bing.com homepage shows 必应
  上的热点 (today's top stories) — often the exact official headline
  ("习近平会见美国总统特朗普", "深圳APEC的首张全家福"). Clicking one of
  those headline links or searching that exact string gives a clean,
  same-day result set. This is the fastest way to find the right query.
- **`cn.bing.com/news/search?q=...` redirects to the homepage** — don't
  use it; plain web search covers it.
- **Baidu and DuckDuckGo both throw CAPTCHAs at the browser** (Baidu slider
  安全验证, DDG "select all ducks"). Skip them; don't fight the CAPTCHA.

## Verification standard

- Prefer 新华社 (Xinhua) datelines as the anchor: `新华社深圳11月18日电`
  gives the canonical date/time. Multiple outlets (四川在线, 今晚报, 中国
  警察网, …) citing the same Xinhua dispatch = strong corroboration; cite
  once, name Xinhua, list 2-3 carriers.
- Distinguish event stages when the user's "when did X come" is ambiguous:
  迎接 (airport welcome) vs 会见 (formal meeting) vs 峰会 (summit day).
  Answer with both if the stages differ by day (e.g. arrived 11/18,
  met 11/19).
- State the source explicitly in the answer ("按新华社通稿"). If only
  one carrier found it, say confidence is lower.

## Pitfalls

- Search-backends failing with a credit/payment error is transient
  (resets on a stated date). Do not harden this into "search is broken";
  just fall back and report the reset date.
- APEX/APEC official sites are JS-heavy and their content pages can be
  thin; expect to get dates but not delegation counts from them.
- Dates in search snippets ("1 天前", "9 小时之前") are relative — convert
  against today's date before quoting, and prefer the absolute dateline
  in the snippet body over the relative freshness label.

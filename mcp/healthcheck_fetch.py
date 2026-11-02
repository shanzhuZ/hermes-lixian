"""自封装采集 MCP 实采连通性检查（redbubble / teepublic / zazzle）。

对每个平台真实发起一次关键词搜索，只做搜索、不落盘、不下图，
用最小代价判断反爬是否被拦、字段解析是否还有效。

Etsy / eBay 不在此列：已确认原生爬虫不可行，统一走 Firecrawl 通道。
"""

import json
import os
import subprocess
import sys

PYTHON = sys.executable

CASES = {
    "redbubble": (
        r"D:\hermes-lixian\mcp\servers\redbubble-mcp-server",
        "from redbubble_client import RedbubbleClient as C\n"
        "r = C().search(query='cat')\n",
    ),
    "teepublic": (
        r"D:\hermes-lixian\mcp\servers\teepublic-mcp-server",
        "from teepublic_client import TeePublicClient as C\n"
        "r = C().search(query='cat')\n",
    ),
    "zazzle": (
        r"D:\hermes-lixian\mcp\servers\zazzle-mcp-server",
        "from zazzle_client import ZazzleClient as C\n"
        "r = C().search(query='cat')\n",
    ),
}

PROBE_TMPL = r'''
import os, sys, json
sys.path.insert(0, os.getcwd())
{body}
if not isinstance(r, dict):
    r = {{"raw": str(r)[:200]}}
items = None
for k in ("items", "results", "products", "designs"):
    v = r.get(k)
    if isinstance(v, list):
        items = v
        break
out = {{"error": r.get("error"), "count": (len(items) if items is not None else None)}}
if items:
    s = items[0]
    if isinstance(s, dict):
        # 关键字段完整度：标题与价格为空说明解析降级了
        out["titled"] = sum(1 for x in items if isinstance(x, dict) and x.get("title"))
        out["priced"] = sum(1 for x in items if isinstance(x, dict) and x.get("price"))
        out["sample"] = {{k: s.get(k) for k in ("title", "price", "currency") if k in s}}
print("RESULT=" + json.dumps(out, ensure_ascii=False, default=str))
'''

env = dict(os.environ)
env.update({
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "FASTMCP_SHOW_SERVER_BANNER": "false",
})

for name, (path, body) in CASES.items():
    if not os.path.isdir(path):
        print(f"[{name}] 目录不存在")
        continue
    try:
        p = subprocess.run(
            [PYTHON, "-c", PROBE_TMPL.format(body=body)],
            cwd=path, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=420,
        )
    except subprocess.TimeoutExpired:
        print(f"[{name}] 采集超时")
        continue

    payload = ""
    for ln in (p.stdout or "").splitlines():
        if ln.startswith("RESULT="):
            payload = ln[len("RESULT="):]
    if payload:
        d = json.loads(payload)
        ok = d.get("count") and not d.get("error") and d.get("titled") and d.get("priced")
        print(
            f"[{name}] {'OK' if ok else '异常'} 条数={d.get('count')} "
            f"有标题={d.get('titled')} 有价格={d.get('priced')}"
        )
        if d.get("sample"):
            print(f"    样例: {json.dumps(d['sample'], ensure_ascii=False)[:180]}")
    else:
        print(f"[{name}] 执行失败 (exit={p.returncode})")
        for ln in (p.stderr or "").strip().splitlines()[-6:]:
            print(f"    {ln}")

"""自封装采集 MCP 健康检查：逐个子进程启动 server.py 并列出已注册工具。

每个 MCP 单独起子进程，避免同名模块（server / *_client）互相污染 sys.modules。
"""

import json
import os
import subprocess
import sys

PYTHON = sys.executable
SERVERS = {
    "redbubble": r"D:\hermes-lixian\mcp\servers\redbubble-mcp-server",
    "teepublic": r"D:\hermes-lixian\mcp\servers\teepublic-mcp-server",
    "zazzle": r"D:\hermes-lixian\mcp\servers\zazzle-mcp-server",
    "walmart": r"D:\hermes-lixian\mcp\servers\walmart-mcp-server",
    "etsy-crawler": r"D:\hermes-lixian\mcp\servers\etsy-crawler-mcp",
    "ebay_browse": r"D:\hermes-lixian\mcp\servers\ebay-browse-mcp",
}

PROBE = r'''
import asyncio, os, sys
sys.path.insert(0, os.getcwd())
import server
async def main():
    tools = await server.mcp.list_tools()
    print("TOOLS=" + ",".join(getattr(t, "name", str(t)) for t in tools))
asyncio.run(main())
'''

env = dict(os.environ)
env.update({
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "FASTMCP_SHOW_SERVER_BANNER": "false",
})

for name, path in SERVERS.items():
    if not os.path.isdir(path):
        print(f"[{name}] 目录不存在: {path}")
        continue
    try:
        p = subprocess.run(
            [PYTHON, "-c", PROBE],
            cwd=path, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
    except subprocess.TimeoutExpired:
        print(f"[{name}] 启动超时")
        continue

    line = ""
    for ln in (p.stdout or "").splitlines():
        if ln.startswith("TOOLS="):
            line = ln[len("TOOLS="):]
    if line:
        print(f"[{name}] OK 工具: {line}")
    else:
        err = (p.stderr or "").strip().splitlines()
        print(f"[{name}] 启动失败 (exit={p.returncode})")
        for ln in err[-6:]:
            print(f"    {ln}")

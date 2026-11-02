# -*- coding: utf-8 -*-
import json, time, urllib.request, urllib.error

KEY = "change-me-local-dev"
BASE = "http://127.0.0.1:8642"
OUT = r"D:\hermes-lixian\var\tmp-llm-test\hermes-stream-probe2.txt"

def http_json(method, url, body=None, timeout=60):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

print("=== create session ===")
sess = http_json("POST", BASE + "/api/sessions", {})
sid = sess["session"]["id"]
print("session", sid)

prompt = "用一句话解释什么是质数。先在心里想一步再答。"
print("=== chat/stream ===", prompt)
req = urllib.request.Request(
    BASE + "/api/sessions/" + sid + "/chat/stream",
    data=json.dumps({"message": prompt}, ensure_ascii=False).encode("utf-8"),
    method="POST",
    headers={
        "Authorization": "Bearer " + KEY,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "text/event-stream",
    },
)
t0 = time.time()
events = {}
samples = {k: [] for k in ("reasoning.delta", "assistant.delta", "tool.progress")}
raw_lines = []
with urllib.request.urlopen(req, timeout=300) as r:
    cur = "message"
    for raw in r:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        raw_lines.append(line)
        if line.startswith("event:"):
            cur = line[6:].strip()
        elif line.startswith("data:"):
            data = line[5:].strip()
            events[cur] = events.get(cur, 0) + 1
            if cur in samples and len(samples[cur]) < 5:
                samples[cur].append(data[:300])
                print("SAMPLE", cur, ":", data[:220])

print("=== done in %.1fs ===" % (time.time() - t0))
print("event counts:", json.dumps(events, ensure_ascii=False, indent=2))
# pull reasoning from run.completed if any
for line in raw_lines:
    if line.startswith("data:") and "reasoning_content" in line:
        d = json.loads(line[5:].strip())
        msgs = d.get("messages") or []
        if msgs:
            m = msgs[0]
            print("has reasoning_content len=", len(m.get("reasoning_content") or ""))
            print("reasoning_content head=", repr((m.get("reasoning_content") or "")[:240]))
        break
open(OUT, "w", encoding="utf-8").write("\n".join(raw_lines))
print("saved", OUT)

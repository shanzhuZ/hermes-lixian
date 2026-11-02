# -*- coding: utf-8 -*-
"""直接打 Hermes OpenAI 兼容流，看 chunk 里有没有 reasoning_content。"""
import json
import time
import urllib.request

KEY = "change-me-local-dev"
BASE = "http://127.0.0.1:8642"
OUT = r"D:\hermes-lixian\var\tmp-llm-test\openai-stream-probe.txt"

body = {
    "model": "hermes-agent",
    "stream": True,
    "messages": [
        {"role": "user", "content": "用一句话解释什么是质数。先在心里想一步再答。"}
    ],
}

req = urllib.request.Request(
    BASE + "/v1/chat/completions",
    data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    method="POST",
    headers={
        "Authorization": "Bearer " + KEY,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "text/event-stream",
    },
)

t0 = time.time()
content_n = 0
reason_n = 0
other_keys = set()
samples = []
raw = []

with urllib.request.urlopen(req, timeout=300) as r:
    for line_b in r:
        line = line_b.decode("utf-8", "replace").rstrip("\n")
        raw.append(line)
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except Exception:
            continue
        # OpenAI chunk or hermes custom
        choices = obj.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            for k in delta.keys():
                other_keys.add(k)
            c = delta.get("content")
            rc = delta.get("reasoning_content") or delta.get("reasoning")
            if c:
                content_n += 1
                if content_n <= 3:
                    samples.append(("content", c))
            if rc:
                reason_n += 1
                if reason_n <= 5:
                    samples.append(("reasoning", rc[:200]))
        else:
            # hermes custom events
            ev = obj.get("event") or obj.get("type")
            if ev:
                other_keys.add("event:" + str(ev))

print("elapsed=%.1fs content_deltas=%d reasoning_deltas=%d" % (time.time() - t0, content_n, reason_n))
print("delta keys seen:", sorted(other_keys))
print("samples:")
for kind, text in samples:
    print(" ", kind, repr(text)[:180])

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(raw))
print("saved", OUT, "lines", len(raw))

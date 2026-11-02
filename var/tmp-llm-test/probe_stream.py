# -*- coding: utf-8 -*-
"""探测当前 Hermes 模型流式返回形态（是否有 reasoning.delta / reasoning_content）。"""
import json
import time
import urllib.error
import urllib.request

KEY = "change-me-local-dev"
BASE = "http://127.0.0.1:8642"
OUT = r"D:\hermes-lixian\var\tmp-llm-test\hermes-stream-probe.txt"


def http_json(method, url, body=None, timeout=60):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("=== health ===")
    req = urllib.request.Request(
        BASE + "/health",
        headers={"Authorization": "Bearer " + KEY},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        print(r.read().decode())

    print("=== models ===")
    try:
        models = http_json("GET", BASE + "/v1/models")
        print(json.dumps(models, ensure_ascii=False)[:2000])
    except Exception as e:
        print("models err:", type(e).__name__, e)

    print("=== create session ===")
    sess = http_json("POST", BASE + "/api/sessions", {"title": "probe-thinking"})
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
    samples = {}
    raw_lines = []
    try:
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
                    if cur not in samples:
                        samples[cur] = data[:500]
                    if cur in ("reasoning.delta", "assistant.delta", "tool.progress", "error") and events[cur] <= 8:
                        print("SAMPLE", cur, ":", data[:240])
                if time.time() - t0 > 240:
                    print("TIMEOUT CUT")
                    break
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        print("HTTPError", e.code, err[:1000])
        raw_lines.append("HTTPError " + str(e.code) + " " + err)
    except Exception as e:
        print("ERR", type(e).__name__, e)
        raw_lines.append("ERR " + type(e).__name__ + " " + str(e))

    print("=== done in %.1fs ===" % (time.time() - t0))
    print("event counts:", json.dumps(events, ensure_ascii=False, indent=2))
    print("first sample per event:")
    for k, v in samples.items():
        print("  [%s] %s" % (k, v[:350]))

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(raw_lines))
    print("saved", OUT, "lines=", len(raw_lines))


if __name__ == "__main__":
    main()

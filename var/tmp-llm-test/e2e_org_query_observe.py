# -*- coding: utf-8 -*-
"""E2E：经 Java 网关提问「查询一下涉华美国智库」，全量观察 SSE。"""
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter

JAVA = "http://127.0.0.1:8088"
OUT = r"D:\hermes-lixian\var\tmp-llm-test\e2e-org-observe.txt"
PROMPT = "查询一下涉华美国智库"


def http_json(method, url, body=None, timeout=60):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def lang_stats(text):
    zh = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    en = len(re.findall(r"[A-Za-z]", text or ""))
    return zh, en


def main():
    lines_out = []
    t0 = time.time()

    print("=== create session ===")
    sess = http_json("POST", JAVA + "/api/chat/sessions", {"title": "e2e-org-" + str(int(t0))})
    sid = sess["sessionId"]
    print("sessionId", sid, "hermes", sess.get("hermesSessionId"))

    print("=== ask ===")
    ask = http_json(
        "POST",
        JAVA + "/api/chat/ask",
        {"sessionId": sid, "userId": "e2e", "message": PROMPT},
    )
    task_id = ask["taskId"]
    print("taskId", task_id, "status", ask.get("status"))

    print("=== subscribe stream (max 8 min) ===")
    url = JAVA + "/api/chat/tasks/" + task_id + "/stream"
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    events = Counter()
    reasoning_parts = []
    answer_parts = []
    tool_events = []
    anomalies = []
    raw_lines = []
    cur = "message"
    deadline = time.time() + 480

    try:
        with urllib.request.urlopen(req, timeout=500) as r:
            for raw in r:
                if time.time() > deadline:
                    anomalies.append("TIMEOUT_CUT")
                    break
                line = raw.decode("utf-8", "replace").rstrip("\n")
                raw_lines.append(line)
                if line.startswith("event:"):
                    cur = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
                    events[cur] += 1
                    elapsed = time.time() - t0
                    if cur == "reasoning.delta":
                        try:
                            d = json.loads(data)
                            piece = d.get("delta") or d.get("text") or ""
                        except Exception:
                            piece = data
                        reasoning_parts.append(piece)
                        if events[cur] <= 3 or events[cur] % 20 == 0:
                            print("[%.1fs] reasoning#%d %r" % (elapsed, events[cur], piece[:80]))
                    elif cur == "assistant.delta":
                        try:
                            d = json.loads(data)
                            piece = d.get("delta") or d.get("text") or ""
                        except Exception:
                            piece = data
                        answer_parts.append(piece)
                        if events[cur] <= 3:
                            print("[%.1fs] answer#%d %r" % (elapsed, events[cur], piece[:80]))
                    elif cur in ("tool.started", "tool.completed", "tool.failed", "tool.progress"):
                        tool_events.append((cur, data[:500]))
                        print("[%.1fs] TOOL", cur, data[:220])
                    elif cur in ("error", "cancelled"):
                        anomalies.append("%s: %s" % (cur, data[:300]))
                        print("[%.1fs]", cur, data[:300])
                    elif cur == "stream_end":
                        print("[%.1fs] stream_end", data)
                        break
                    elif cur == "status" and events[cur] <= 5:
                        print("[%.1fs] status", data)
    except Exception as e:
        anomalies.append("STREAM_ERR: %s: %s" % (type(e).__name__, e))
        print("STREAM_ERR", e)

    # task snapshot
    try:
        snap = http_json("GET", JAVA + "/api/chat/tasks/" + task_id)
    except Exception as e:
        snap = {"error": str(e)}

    reasoning = "".join(reasoning_parts)
    answer = "".join(answer_parts)
    rzh, ren = lang_stats(reasoning)
    azh, aen = lang_stats(answer)

    # 按段粗分：若连续英文比例高则标一段
    # 简单：每 80 字窗口看 zh/en
    mix_windows = []
    step = 60
    for i in range(0, max(1, len(reasoning)), step):
        chunk = reasoning[i : i + step]
        zh, en = lang_stats(chunk)
        if en > zh * 2 and en >= 20:
            mix_windows.append((i, chunk[:60].replace("\n", " ")))

    print("\n=== SUMMARY ===")
    print("elapsed=%.1fs" % (time.time() - t0))
    print("events=", dict(events))
    print("reasoning len=%d zh=%d en=%d" % (len(reasoning), rzh, ren))
    print("answer len=%d zh=%d en=%d" % (len(answer), azh, aen))
    print("tool_events=%d" % len(tool_events))
    print("anomalies=", anomalies)
    print("task snap status=", snap.get("status"), "error=", snap.get("error"))
    print("reasoning head:\n", reasoning[:500])
    print("reasoning tail:\n", reasoning[-400:] if len(reasoning) > 400 else reasoning)
    print("answer head:\n", answer[:400])
    if mix_windows:
        print("EN-heavy reasoning windows (sample up to 8):")
        for i, c in mix_windows[:8]:
            print("  @%d %r" % (i, c))

    report = {
        "prompt": PROMPT,
        "sessionId": sid,
        "taskId": task_id,
        "elapsed_sec": round(time.time() - t0, 1),
        "events": dict(events),
        "reasoning_len": len(reasoning),
        "reasoning_zh": rzh,
        "reasoning_en": ren,
        "answer_len": len(answer),
        "answer_zh": azh,
        "answer_en": aen,
        "tool_event_count": len(tool_events),
        "tool_events": tool_events[:30],
        "anomalies": anomalies,
        "task": snap,
        "reasoning_full": reasoning,
        "answer_full": answer,
        "en_heavy_windows": mix_windows[:20],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2))
        f.write("\n\n===== RAW SSE =====\n")
        f.write("\n".join(raw_lines))
    print("saved", OUT)


if __name__ == "__main__":
    main()

"""Collect the lookup-quiz subagents' logs: question, searches, rule breaks and final answer.

  python3 collect_lookup.py   # writes lookup_results.json next to this file and prints a summary
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = Path.home() / (".cursor/projects/Users-yashtikekar-Desktop-Projects-personal-agent-memory-test/"
                      "agent-transcripts/02abdc73-eebe-42ab-be62-4d64d08d3a8b/subagents")
PROMPT = re.compile(r"notes-run1/(\w+)/lookup/(facts|implications)\.q(\d+)\.prompt\.md$")
IGNORED = {"UpdateCurrentStep"}


def parse(log: Path):
    key, searches, breaks, answer = None, [], [], ""
    for line in log.read_text().splitlines():
        event = json.loads(line)
        msg = event.get("message") or {}
        for c in msg.get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and event.get("role") == "assistant" and c.get("text", "").strip():
                # Kimi puts its user-facing answer first, then may append hidden working text.
                answer = c["text"].strip().split("\n\n", 1)[0]
            if c.get("type") != "tool_use" or c["name"] in IGNORED:
                continue
            inp = c.get("input") or {}
            path = inp.get("path") or ""
            m = PROMPT.search(path)
            if c["name"] == "Read" and m and key is None:
                key = (m.group(1), m.group(2), int(m.group(3)))
            elif c["name"] == "Grep" and path.endswith("/phone.txt") and (key is None or f"/{key[0]}/" in path):
                searches.append(inp.get("pattern", ""))
            else:
                breaks.append(f"{c['name']}:{path or inp.get('command') or inp}")
    return key, searches, breaks, answer


def main():
    old_path = HERE / "lookup_results.json"
    old = {}
    if old_path.exists():
        old = {(r["person"], r["arm"], r["q"]): r for r in json.loads(old_path.read_text())}
    rows = {}
    for log in sorted(LOGS.glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        key, searches, breaks, answer = parse(log)
        if key:
            rows[key] = {"person": key[0], "arm": key[1], "q": key[2], "agent": log.stem,
                         "searches": searches, "breaks": breaks, "answer": answer}
            for field in ("correct", "type"):
                if field in old.get(key, {}):
                    rows[key][field] = old[key][field]
    out = sorted(rows.values(), key=lambda r: (r["person"], r["q"], r["arm"]))
    (HERE / "lookup_results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for r in out:
        flag = f"  RULE BREAK {r['breaks']}" if r["breaks"] else ""
        print(f"{r['person']:8} q{r['q']} {r['arm']:12} searches={len(r['searches'])} {r['searches']}{flag}")
    print(len(out), "collected")


if __name__ == "__main__":
    main()

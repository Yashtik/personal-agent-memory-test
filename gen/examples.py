"""Build seeds/examples.json from one finished phone, for use in other people's prompts.

  python -m gen.examples --person wei --work DIR

style: ordinary records from that phone that the filler wrote and nothing later changed, and that hold no piece and
were not flagged by the check. placements: before/after views of threads the insertion pass added to.
"""
import argparse
import json
import random
from pathlib import Path

from gen.generate import DATA, ROOT

OUT = ROOT / "seeds" / "examples.json"
STYLE_MIX = {"email": 2, "texts": 2, "whatsapp": 1, "notes": 2, "calendar": 3, "transactions": 2}


def bare(r: dict) -> str:
    return json.dumps({k: v for k, v in r.items() if k != "id"}, sort_keys=True, ensure_ascii=False)


def build(pid: str, work: Path) -> dict:
    final = json.loads((DATA / f"{pid}.json").read_text())
    filler = json.loads((work / "filler.json").read_text())
    found = json.loads((work / "check.json").read_text())
    flagged = {x.split(".")[0] for f in found["facts"] for p in f["pieces"] if p["record"] for x in [p["record"]]}
    flagged |= {x.split(".")[0] for f in found["facts"] for k in ("echoed_in", "settled_in", "stated_outright_in")
                for x in f[k]}
    flagged |= {x.split(".")[0] for c in found["contradictions"] for x in c["records"]}
    rng = random.Random(pid)
    style = []
    for sec, n in STYLE_MIX.items():
        untouched = {bare(r) for r in filler[sec]}
        pool = [r for r in final[sec] if r["id"] not in flagged and bare(r) in untouched]
        for r in rng.sample(pool, min(n, len(pool))):
            style.append({"section": sec, "record": {k: v for k, v in r.items() if k != "id"}})
    placements = []
    piece_threads = {p["record"].split(".")[0]: int(p["record"].split(".")[1]) for f in found["facts"]
                     for p in f["pieces"] if "." in p["record"] and p["record"][0] == "t"}
    for tid, pos in sorted(piece_threads.items()):
        after = next(t for t in final["texts"] if t["id"] == tid)
        before = next((t for t in filler["texts"] if t["with"] == after["with"]
                       and all(m in after["messages"] for m in t["messages"])), None)
        if not before or len(before["messages"]) >= len(after["messages"]):
            continue  # a new thread, not a placement into an existing one
        lo = max(0, pos - 3)
        placements.append({"with": after["with"],
                           "before": before["messages"][lo:pos + 1][-3:],
                           "after": after["messages"][lo:pos + 2]})
    return {"source": pid, "style": style, "placements": placements[:3]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    ex = build(a.person, Path(a.work) / a.person)
    OUT.write_text(json.dumps(ex, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}: {len(ex['style'])} style records, {len(ex['placements'])} placements")

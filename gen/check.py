"""Check generated phones.

  python -m gen.check                 # format checks only (no API calls)
  python -m gen.check --pieces        # also ask a fresh model where each piece landed
  python -m gen.check --blind         # also see whether a fresh model can spot the planted records

Format checks: section sizes, unique ids, dates, and that every quoted record is present word for word.
Piece check: for each seed fact, which records hold its pieces, and whether any single record states the
conclusion outright. Exits non-zero and lists the people to regenerate if anything fails.
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime

from gen.generate import COUNTS, DATA, SEEDS, _obj, load_env, targets
from gen.split import PIECES

MIN_SHARE = 0.7  # each section must reach at least 70% of its target size


def records(phone: dict) -> list:
    """Flatten a phone into (id, app, date, text) rows; thread messages get ids like t3.2."""
    rows = []
    for e in phone["email"]:
        rows.append((e["id"], "email", e["date"], f"From {e['from']} to {e['to']} | {e['subject']} | {e['body']}"))
    for app, key in (("texts", "with"), ("whatsapp", "chat")):
        for t in phone[app]:
            for i, m in enumerate(t["messages"], 1):
                rows.append((f"{t['id']}.{i}", app, m["date"], f"[{t[key]}] {m['from']}: {m['body']}"))
    for n in phone["notes"]:
        rows.append((n["id"], "note", n["updated"], f"{n['title']} | {n['body']}"))
    for c in phone["calendar"]:
        rows.append((c["id"], "calendar", c["start"], f"{c['title']} | {c['location']} | {c['notes']}"))
    for a in phone["assistant_chats"]:
        for i, t in enumerate(a["turns"], 1):
            rows.append((f"{a['id']}.{i}", "assistant_chat", a["date"], f"{t['role']}: {t['text']}"))
    for x in phone["transactions"]:
        rows.append((x["id"], "transaction", x["date"], f"{x['account']} | {x['description']} | {x['amount']}"))
    return rows


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def format_problems(phone: dict, seed: dict) -> list:
    problems = []
    for k, n in targets(seed["id"]).items():
        if len(phone[k]) < MIN_SHARE * n:
            problems.append(f"{k}: {len(phone[k])} (target {n})")
    ids = [r["id"] for k in COUNTS if k != "contacts" for r in phone[k]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        problems.append(f"duplicate ids: {dupes}")
    today = seed["today"]
    for rid, app, date, _ in records(phone):
        try:
            datetime.fromisoformat(date)
        except ValueError:
            problems.append(f"{rid}: bad date {date!r}")
            continue
        if app != "calendar" and date > today:
            problems.append(f"{rid}: dated after today ({date})")
    blob = norm(" ".join(t for *_, t in records(phone)))
    for q in seed["quoted"]:
        for part in (norm(p) for p in q["text"].split("…")):
            if len(part) > 20 and part not in blob:
                problems.append(f"quoted text missing: {part[:70]!r}")
    return problems


S = {"type": "string"}
CHECK_SCHEMA = _obj({"facts": {"type": "array", "items": _obj({
    "index": {"type": "integer"},
    "stated_outright_in": {"type": "array", "items": S},
    "pieces": {"type": "array", "items": _obj({"piece": {"type": "integer"}, "record": S})},
    "trigger_found_in": {"type": "array", "items": S},
    "settled_in": {"type": "array", "items": S},
    "echoed_in": {"type": "array", "items": S},
})}, "contradictions": {"type": "array", "items": _obj({"records": {"type": "array", "items": S}, "problem": S})}})


def check_prompt(phone: dict, facts: list) -> str:
    rows = "\n".join(f"{rid} [{app} {date}] {text}" for rid, app, date, text in records(phone))
    items = "\n".join(
        f"{i}. Fact: {f['fact']}\n"
        + "\n".join(f"   piece {j}: {x['text']}" for j, x in enumerate(f["pieces"]) if x["role"] == "background")
        + "".join(f"\n   trigger: {x['text']}" for x in f["pieces"] if x["role"] == "trigger")
        for i, f in enumerate(facts))
    return f"""Below are the records on one person's phone, then a list of facts, each with its pieces.

For each fact:
- stated_outright_in: ids of any single record that states the fact itself, including its conclusion or the link
  between the pieces (for example "so the call can't be at 3"), or that applies one piece to another (for example
  a note applying a payment rule to a specific bill). Records that hold only one piece do not count. Empty list
  if none.
- pieces: for each numbered piece, the id of a record that contains it (same meaning, wording may differ), or ""
  if no record does.
- trigger_found_in: ids of any record that contains the fact's trigger detail (it should be in none). Empty list
  if none.
- settled_in: ids of any record that contradicts the trigger or already settles the errand it asks for (for
  example the call already agreed for a different time, or the booking already made). The plan should still be
  open. Empty list if none, or if the fact has no trigger.
- echoed_in: ids of calendar entries, notes or assistant-chat turns that are not one of its pieces and either repeat
  the fact's event (a change, request, message or one-off item) or combine pieces into the fact's conclusion.
  Standing facts (routines, rules, standing arrangements) are meant to appear in many records; do not count those.
  Empty list if none.

Separately, list in contradictions any records that cannot all be true together: two versions of the same event,
clashing dates or places, the same person in two places at once, or numbers that disagree. Do not list a conflict
that is what one of the facts above describes (for example a plan that changed, or a statement that leaves out a
payment); those are intended.

Records:
{rows}

Facts:
{items}"""


async def piece_report(client, model: str, phone: dict, facts: list) -> list:
    async with client.messages.stream(
            model=model, max_tokens=32000, messages=[{"role": "user", "content": check_prompt(phone, facts)}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": CHECK_SCHEMA}}) as s:
        msg = await s.get_final_message()
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


BLIND_SCHEMA = _obj({"ids": {"type": "array", "items": S}})
BLIND_PICKS = 10


def blind_prompt(phone: dict) -> str:
    rows = "\n".join(f"{rid} [{app} {date}] {text}" for rid, app, date, text in records(phone))
    return (f"Below are the records on one person's phone. Some of them may have been planted for a test. "
            f"List the ids of the {BLIND_PICKS} records most likely to have been planted.\n\n{rows}")


async def blind_picks(client, model: str, phone: dict) -> list:
    async with client.messages.stream(
            model=model, max_tokens=16000, messages=[{"role": "user", "content": blind_prompt(phone)}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": BLIND_SCHEMA}}) as s:
        msg = await s.get_final_message()
    return json.loads(next(b.text for b in msg.content if b.type == "text"))["ids"][:BLIND_PICKS]


def blind_problems(picks: list, report: dict, phone: dict) -> list:
    """Compare the blind picks with where the pieces landed, at record level (a thread counts as one record)."""
    base = lambda rid: rid.split(".")[0]  # noqa: E731
    planted = {base(p["record"]) for r in report["facts"] for p in r["pieces"] if p["record"]}
    every = {base(rid) for rid, *_ in records(phone)}
    hits = len({base(x) for x in picks} & planted)
    expected = BLIND_PICKS * len(planted) / max(len(every), 1)
    line = f"blind check: {hits}/{BLIND_PICKS} picks were planted records (chance about {expected:.1f})"
    return [line + ", pieces stand out"] if hits >= 3 and hits >= 2 * expected else []


def piece_problems(report: dict, facts: list) -> list:
    problems = [f"contradiction {c['records']}: {c['problem']}" for c in report["contradictions"]]
    for r in report["facts"]:
        f = facts[r["index"]]
        if r["stated_outright_in"]:
            problems.append(f"conclusion stated in {r['stated_outright_in']}: {f['fact'][:80]}")
        if r["echoed_in"]:
            problems.append(f"echoed in calendar, note or assistant chat {r['echoed_in']}: {f['fact'][:80]}")
        if r["settled_in"]:
            problems.append(f"errand already settled or contradicted in {r['settled_in']}: {f['fact'][:80]}")
        if r["trigger_found_in"]:
            problems.append(f"trigger leaked into {r['trigger_found_in']}: {f['fact'][:80]}")
        missing = [p["piece"] for p in r["pieces"] if not p["record"]]
        if missing:
            problems.append(f"pieces {missing} missing: {f['fact'][:80]}")
    return problems


async def main(args) -> int:
    seeds = {p["id"]: p for p in json.loads(SEEDS.read_text())}
    args.pieces = args.pieces or args.blind  # the blind check needs to know where the pieces landed
    pieces = json.loads(PIECES.read_text()) if args.pieces else {}
    client = None
    if args.pieces:
        from anthropic import AsyncAnthropic
        load_env()
        client = AsyncAnthropic()
    phones = {p.stem: json.loads(p.read_text()) for p in sorted(DATA.glob("*.json"))}

    async def one(pid):
        problems = format_problems(phones[pid], seeds[pid])
        if client:
            report = await piece_report(client, args.model, phones[pid], pieces[pid])
            problems += piece_problems(report, pieces[pid])
            if args.blind:
                problems += blind_problems(await blind_picks(client, args.model, phones[pid]), report, phones[pid])
        return pid, problems

    redo = []
    for pid, problems in await asyncio.gather(*(one(pid) for pid in phones)):
        print(f"{pid:8} {'ok' if not problems else str(len(problems)) + ' problem(s)'}")
        for p in problems:
            print(f"         - {p}")
        if problems:
            redo.append(pid)
    if redo:
        print("regenerate:", ",".join(redo))
    return 1 if redo else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pieces", action="store_true")
    ap.add_argument("--blind", action="store_true")
    ap.add_argument("--model", default="claude-opus-5-5")
    sys.exit(asyncio.run(main(ap.parse_args())))

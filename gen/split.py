"""Split each seed fact into the raw pieces a person's records would actually hold.

Real records rarely state conclusions ("so the call can't be at 3 pm"); they hold separate facts that add up
("Lin takes her afternoon pill at 3 pm", "the kids set the call for 3 pm"). This step turns every seed fact into
such pieces, so the generator never sees the conclusion.

  python -m gen.split [--people wei]

Writes seeds/pieces.json.
"""
import argparse
import asyncio
import json
from pathlib import Path

from gen.generate import ROOT, SEEDS, _obj, load_env

PIECES = ROOT / "seeds" / "pieces.json"
S = {"type": "string"}
APPS = ["email", "text", "whatsapp", "note", "calendar", "assistant_chat", "transaction"]

SPLIT_SCHEMA = _obj({"facts": {"type": "array", "items": _obj({
    "index": {"type": "integer"},
    "pieces": {"type": "array", "items": _obj({"text": S, "app": {"type": "string", "enum": APPS}, "when": S,
                                               "role": {"type": "string", "enum": ["background", "trigger"]}})},
    "left_out": S,
})}})

SYSTEM = (
    "You prepare inputs for realistic synthetic phone data. Real records rarely state conclusions. They hold "
    "separate, ordinary facts that only add up to a conclusion when someone puts them together."
)


def quoted_block(p: dict) -> str:
    return "\n".join(f"- [{q['kind']}] from {q['from']}{' | subject: ' + q['subject'] if q['subject'] else ''}"
                     f" | when: {q['when']}\n  {q['text']}" for q in p["quoted"]) or "- none"


def prompt(p: dict, feedback: list = ()) -> str:
    items = "\n".join(f"{i}. Situation: {f['title']}\n   True fact: {f['fact']}" for i, f in enumerate(p["facts"]))
    fixes = ("\n\nA reviewer found these problems in your previous version. Fix every one:\n"
             + "\n".join(f"- items {x['items']}: {x['problem']}" for x in feedback)
             + "\nNever fix a problem by adding details that only show up at errand time, or by stating a "
               "conclusion.") if feedback else ""
    return f"""Person: {p['line']}. Today is {p['today']}.

These records are already on the phone, word for word:
{quoted_block(p)}

For each numbered item, write the raw pieces that this person's records would hold, from which a careful reader
could work out the true fact. Rules:
- Do not restate, duplicate or contradict anything the records above already cover. Where they already cover an
  item, add only what is missing (or return no pieces for it).
- All items happen in this one person's life, on one timeline. Keep dates, places, people and who is where
  consistent across every item and with the records above.
- Each piece is one plain fact as it would appear in a single record, e.g. "Lin takes her afternoon pill at 3 pm"
  (a note) and "the kids set the birthday call for 3 pm" (a text from her son).
- No piece states the conclusion, and no piece links the others with "so", "because", "which means" or similar.
- Together the pieces must be enough to reach the fact.
- Leave out anything that would only show up when the errand is carried out, such as the slots a clinic offers,
  a shop's price or delivery date, or which restaurant has a table. Keep the person's own constraints, plans,
  rules and what other people told them. Say briefly in left_out what you dropped (or "nothing").
- If the fact is already a raw statement someone made (e.g. a sister texting that she can't arrive before 8:30),
  keep it as a single piece in that person's words. Do not turn it into a chain of separate facts to infer.
- Suggest a different app for each piece where that is natural, and a rough "when" (e.g. "3 weeks ago",
  "yesterday", "in 5 days" for calendar entries).
- Tag every piece with a role. "background" goes into the phone: the true fact itself (always), plus standing
  facts, constraints, rules, habits and anything people said or sent. "trigger" is held back and not written into
  the phone: the specific plan or request the errand is about, e.g. "set up the London call next week", "pay Lucia
  for last night", "book a hotel for Helen's family", "the kids want Mom's birthday call Sunday at 3, set it up and
  tell them". Even if in real life the plan might have arrived by text, its specific detail goes in the trigger; a
  background piece may say the plan exists without that detail (background "David: we want to do a video call for
  Mom's birthday on Sunday", trigger "the call is Sunday at 3"). The true fact is never a trigger: if it arrived as
  a message (an email moving a meeting, a sitter flagging an expiry date, a flight change), that message is
  background, and so are the constraints that make the plan a problem. When a background piece mentions the same event, leave the trigger's specific detail out of it (e.g.
  background "the kids want to do a video call for Lin's birthday on Sunday", trigger "the call is at 3 pm").
- Every item needs at least one background piece, unless the word-for-word records above already hold its
  background. If the fact is a single raw statement someone made earlier (the sister who can't arrive before
  8:30), it is background and the item needs no trigger.
- Name dates in pieces whenever "Saturday" or "next week" could mean more than one week.

Items:
{items}{fixes}"""


REVIEW_SYSTEM = "You review inputs for realistic synthetic phone data and report every inconsistency you find."
REVIEW_SCHEMA = _obj({"problems": {"type": "array", "items": _obj({
    "items": {"type": "array", "items": {"type": "integer"}}, "problem": S})}})


def review_prompt(p: dict, pieces: list) -> str:
    items = "\n".join(f"{i}. Fact: {f['fact']}\n" + "\n".join(f"   - {x['role']} [{x['app']}, {x['when']}] {x['text']}"
                                                          for x in f["pieces"])
                      + f"\n   left out on purpose (only shows up at errand time): {f['left_out']}"
                      for i, f in enumerate(pieces))
    return f"""Person: {p['line']}. Today is {p['today']}.

Records already on this person's phone, word for word:
{quoted_block(p)}

Pieces grouped by the fact they support. Background pieces will be written into the phone. Trigger pieces are
held back: they arrive later with the errand request, and are never in the phone.
{items}

List every problem of these kinds (empty list if none):
- a piece that contradicts or duplicates a word-for-word record above (a different version of the same event,
  sender, number, date or wording)
- pieces that cannot all be true on one timeline (the same person in two places at once, clashing dates or times)
- a piece that states a fact's conclusion, or links pieces with "so", "because" or similar
- a fact whose pieces, together with the records above and the details left out on purpose, are not enough to
  work it out (the left-out details only appear when the errand is carried out, so never count their absence as a
  problem)
- a piece that contains a detail that should have been left out: what a business offers or quotes at errand time,
  such as open slots, prices, stock or delivery dates
- a trigger that is not a new request or plan for the errand: a trigger that is the fact itself, or news someone
  already sent (an email, text or notice), which belongs in the phone as background
- a background piece that contains the specific detail of the plan the errand is about (that detail belongs in
  the trigger), or a true fact that is missing from the background pieces and the records above
- a fact that was a raw statement someone made but has been broken into a chain of separate facts to infer
- a background piece that already contains its fact's trigger detail, or an item with no background piece when
  the word-for-word records above do not hold its background either
- a fact that could not be worked out from its background pieces plus its trigger (plus the left-out details)
Give the item numbers involved and a short description."""


async def call(client, model: str, system: str, content: str, schema: dict) -> dict:
    # server-side fallback: if a safety filter declines (false positives on medical details happen), the API
    # reruns the request on a fallback model inside the same call
    async with client.beta.messages.stream(
            model=model, max_tokens=32000, system=system, messages=[{"role": "user", "content": content}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"}) as s:
        msg = await s.get_final_message()
    if msg.stop_reason != "end_turn":
        raise RuntimeError(f"stopped with {msg.stop_reason}")
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


async def split_one(client, p: dict, model: str, feedback: list = ()) -> list:
    for _ in range(3):  # retry when the reply skips items
        out = (await call(client, model, SYSTEM, prompt(p, feedback), SPLIT_SCHEMA))["facts"]
        by_index = {f["index"]: f for f in out}
        if sorted(by_index) == list(range(len(p["facts"]))):
            break
    else:
        raise RuntimeError(f"{p['id']}: split returned indexes {sorted(by_index)}")
    return [{"episode": f["episode"], "fact": f["fact"], "pieces": by_index[i]["pieces"],
             "left_out": by_index[i]["left_out"]} for i, f in enumerate(p["facts"])]


async def main(args) -> None:
    from anthropic import AsyncAnthropic
    load_env()
    people = json.loads(SEEDS.read_text())
    if args.people:
        people = [p for p in people if p["id"] in args.people.split(",")]
    existing = json.loads(PIECES.read_text()) if PIECES.exists() else {}
    client = AsyncAnthropic()
    if args.review_only:
        found = await asyncio.gather(*(call(client, args.model, REVIEW_SYSTEM, review_prompt(p, existing[p["id"]]),
                                             REVIEW_SCHEMA) for p in people))
        for p, r in zip(people, found):
            print(f"{p['id']:8} {len(r['problems'])} problem(s)")
            for x in r["problems"]:
                print(f"         - items {x['items']}: {x['problem']}")
        return

    async def settle(p):
        """Split, have a fresh model review, and re-split with its findings until clean (at most 3 reviews)."""
        pieces, problems = await split_one(client, p, args.model), []
        for _ in range(3):
            problems = (await call(client, args.model, REVIEW_SYSTEM, review_prompt(p, pieces), REVIEW_SCHEMA))["problems"]
            if not problems:
                break
            pieces = await split_one(client, p, args.model, problems)
        return pieces, problems

    results = await asyncio.gather(*(settle(p) for p in people), return_exceptions=True)
    for p, r in zip(people, results):
        if isinstance(r, Exception):
            print(f"{p['id']:8} FAILED: {type(r).__name__}: {str(r)[:200]} (previous pieces kept)")
            continue
        pieces, problems = r
        existing[p["id"]] = pieces
        print(f"{p['id']:8} {'clean' if not problems else str(len(problems)) + ' problem(s) left after 3 reviews'}")
        for x in problems:
            print(f"         - items {x['items']}: {x['problem']}")
    PIECES.write_text(json.dumps(existing, indent=1, ensure_ascii=False) + "\n")
    print("wrote", PIECES)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--people", default="")
    ap.add_argument("--review-only", action="store_true", help="review the current pieces without changing them")
    ap.add_argument("--model", default="claude-opus-5-5")
    asyncio.run(main(ap.parse_args()))

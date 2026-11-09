"""Generate one synthetic phone per person from seeds/people.json.

  python -m gen.generate [--people priya,wei] [--model claude-opus-5-5]

Writes data/<id>.json: the person's profile plus their mail, texts, WhatsApp, notes, calendar, earlier
assistant chats, transactions and contacts.
"""
import argparse
import asyncio
import json
import os
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "seeds" / "people.json"
DATA = ROOT / "data"

COUNTS = {"email": 35, "texts": 20, "whatsapp": 8, "notes": 8, "calendar": 15, "assistant_chats": 4,
          "transactions": 15, "contacts": 20}
APP_SECTION = {"email": "email", "text": "texts", "whatsapp": "whatsapp", "note": "notes", "calendar": "calendar",
               "assistant_chat": "assistant_chats", "transaction": "transactions"}
PLANTED_SHARE = 3  # each section holds at least 3x as many records as planted items, so they stay a minority


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


S = {"type": "string"}
MESSAGES = {"type": "array", "items": _obj({"from": S, "date": S, "body": S})}
PHONE_SCHEMA = _obj({
    "contacts": {"type": "array", "items": _obj({"name": S, "relation": S, "email": S, "phone": S})},
    "email": {"type": "array", "items": _obj({"id": S, "from": S, "to": S, "date": S, "subject": S, "body": S,
                                              "unread": {"type": "boolean"}})},
    "texts": {"type": "array", "items": _obj({"id": S, "with": S, "unread": {"type": "boolean"}, "messages": MESSAGES})},
    "whatsapp": {"type": "array", "items": _obj({"id": S, "chat": S, "unread": {"type": "boolean"}, "messages": MESSAGES})},
    "notes": {"type": "array", "items": _obj({"id": S, "title": S, "updated": S, "body": S})},
    "calendar": {"type": "array", "items": _obj({"id": S, "title": S, "start": S, "end": S, "location": S, "notes": S})},
    "assistant_chats": {"type": "array", "items": _obj({
        "id": S, "date": S,
        "turns": {"type": "array", "items": _obj({"role": {"type": "string", "enum": ["user", "assistant"]}, "text": S})}})},
    "transactions": {"type": "array", "items": _obj({"id": S, "date": S, "account": S, "description": S,
                                                     "amount": {"type": "number"}})},
})

SYSTEM = (
    "You write realistic synthetic phone data for testing personal-assistant software. The data must read like a "
    "real person's accounts: specific names, places, amounts and times, ordinary wording, and no placeholder text. "
    "Never comment on the data or explain why anything is included."
)


PIECES = ROOT / "seeds" / "pieces.json"
EXAMPLES = ROOT / "seeds" / "examples.json"


def examples_for(pid: str) -> dict:
    """Examples from a different person's finished phone (never the person's own)."""
    if not EXAMPLES.exists():
        return {}
    ex = json.loads(EXAMPLES.read_text())
    return {} if ex.get("source") == pid else ex


def pieces_for(pid: str) -> list:
    """Background pieces as planted items, in a fixed shuffled order. Triggers are held back.

    Text or WhatsApp pieces of the same fact form one item (a message and its reply belong in one thread); every
    other piece is its own item. Duplicates across facts appear once.
    """
    items, seen = [], set()
    for f in json.loads(PIECES.read_text())[pid]:
        chats = {}
        for x in f["pieces"]:
            if x["role"] != "background" or x["text"] in seen:
                continue
            seen.add(x["text"])
            if x["app"] in ("text", "whatsapp"):
                chats.setdefault(x["app"], []).append(x)
            else:
                items.append([x])
        items += chats.values()
    return random.Random(pid).sample(items, len(items))


def targets(pid: str) -> dict:
    """Section sizes: the defaults, raised so planted items stay at most about a third of each section."""
    planted = {}
    for item in pieces_for(pid):
        sec = APP_SECTION[item[0]["app"]]
        planted[sec] = planted.get(sec, 0) + 1
    return {k: max(n, PLANTED_SHARE * planted.get(k, 0)) for k, n in COUNTS.items()}


def render(item: list) -> str:
    if len(item) == 1:
        x = item[0]
        return f"- [{x['app']}, {x['when']}] {x['text']}"
    lines = "\n".join(f"    ({i}) [{x['when']}] {x['text']}" for i, x in enumerate(item, 1))
    return (f"- [{item[0]['app']}] messages from one conversation; if they are between the same people, put them in "
            f"one thread in this order:\n{lines}")


FORMAT = """Format: dates are ISO 8601 local time (YYYY-MM-DDTHH:MM). Everything except calendar entries is dated
before today, mostly within the last 45 days; calendar entries run from about two weeks ago to four weeks ahead. Give
every record a short unique id with a type prefix (e1, t1, w1, n1, c1, a1, x1). In messages, "from" is "me" for this
person. Use contacts' names consistently everywhere."""

CAST_SCHEMA = _obj({"people": {"type": "array", "items": _obj({"name": S, "relation": S, "city": S})}})
KINDS_SCHEMA = _obj({
    "kinds": {"type": "array", "items": _obj({
        "item": {"type": "integer"}, "kind": {"type": "string", "enum": ["standing", "event"]}})},
    "services": {"type": "array", "items": _obj({"name": S, "role": S})}})
INSERT_SCHEMA = {**PHONE_SCHEMA, "properties": {**PHONE_SCHEMA["properties"],
                                                "deleted_ids": {"type": "array", "items": S}},
                 "required": PHONE_SCHEMA["required"] + ["deleted_ids"]}


def quoted_lines(p: dict) -> str:
    return "\n".join(
        f"- [{q['kind']}] from {q['from']}{' | subject: ' + q['subject'] if q['subject'] else ''} | when: {q['when']}\n"
        f"  {q['text']}" for q in p["quoted"]) or "- none"


def cast_prompt(p: dict) -> str:
    texts = "\n".join(x["text"] for item in pieces_for(p["id"]) for x in item)
    senders = "\n".join(q["from"] for q in p["quoted"])
    return f"""Person: {p['line']}.
List the people named in the lines below (people only: no businesses, clinics, insurers, airlines, hotels or cards),
with their relation to this person (e.g. "son", "home aide") and the city they live in if the lines show or clearly
imply it (otherwise "unknown"). The relation is a plain family or social tie (son, sister-in-law, family friend,
home aide, doctor), stated or clearly implied by the lines, otherwise "unknown". Never mention businesses, bookings
or events in it, and never guess who someone might really be. Leave out the person themself. Names, relations and
cities only; no other detail.

{texts}
{senders}"""


def kinds_prompt(p: dict) -> str:
    items = "\n".join(f"{i}. " + render(item)[2:] for i, item in enumerate(pieces_for(p["id"])))
    return f"""Person: {p['line']}.
Sort each numbered item about this person's life into one kind:
- standing: a routine, schedule, rule, standing arrangement, medication time, where someone lives, or who regularly
  does what. True week after week.
- event: news, a request, a change, a bill, a booking, a plan or any one-off message.

Also list in services every business, clinic, pharmacy, hotel, insurer or other service named in the items or in
the records below that this person has an ongoing relationship with apart from any one event (their dentist,
pharmacy, employer, existing client, landlord); leave out any whose only link is a new inquiry or a one-off event, with its plain role for this person (e.g. "Lin's dentist", "mail-order pharmacy",
"hotel in Flushing"). The role says only what kind of business it is and, if needed, whose ("Wei's doctor"):
nothing about what it is used for, who travels or stays, instructions, plans, events, amounts or dates.

{items}

Records:
{quoted_lines(p)}"""


def split_kinds(pid: str, kinds: list) -> tuple:
    """Items in pieces_for order, split into (standing, events) by the kinds answer."""
    by = {k["item"]: k["kind"] for k in kinds}
    items = pieces_for(pid)
    if sorted(by) != list(range(len(items))):
        raise ValueError(f"kinds cover items {sorted(by)}, expected 0..{len(items) - 1}")
    return [x for i, x in enumerate(items) if by[i] == "standing"], [x for i, x in enumerate(items) if by[i] == "event"]


def filler_prompt(p: dict, cast: list, standing: list = (), services: list = ()) -> str:
    def known(v: str) -> bool:
        return bool(v) and v.strip().lower() != "unknown"

    def line(c: dict) -> str:
        bits = [c["relation"]] if known(c["relation"]) else []
        bits += [f"lives in {c['city']}"] if known(c["city"]) else []
        return f"- {c['name']}" + (f" ({', '.join(bits)})" if bits else "")

    people = "\n".join(line(c) for c in cast) or "- (choose your own)"
    counts = ", ".join(f"about {n} {k.replace('_', ' ')}" for k, n in targets(p["id"]).items())
    standing_block = "\n".join(render(item) for item in standing) or "- (none)"
    service_block = "\n".join(f"- {x['name']}: {x['role']}" for x in services) or "- (none)"
    style = examples_for(p["id"]).get("style", [])
    style_block = ("Style reference from a different person's phone. Match its level of detail, variety and realism. "
                   "Do not reuse any of its people, places, businesses, storylines or events.\n"
                   + "\n".join(f"- [{x['section']}] {json.dumps(x['record'], ensure_ascii=False)}" for x in style)
                   + "\n\n") if style else ""
    return f"""Person: {p['line']} (pronoun: {p['pronoun']}).
Today is {p['today']} (Thursday). Write the contents of their phone as of this morning.

People in their life. Use them naturally throughout, alongside others you add; invent your own businesses:
{people}

Facts about this person's life. Keep everything you write consistent with them, and include each one at least once,
in the suggested app:
{standing_block}

Businesses and services they use. Mention each in several ordinary records (reminders, receipts, newsletters,
statements, notes), alongside others you add:
{service_block}

{style_block}You are writing the haystack: a full, ordinary phone. A few other records will be added to it later, and the phone
should be such that nothing added later stands out. So make the hay rich in exactly that kind of material: many
specific, ordinary messages about appointments, bills, refunds, pharmacies, schedules, days off, visits, plans that
changed and who pays what, involving the people and businesses listed. No record should be the only one of its kind.

Fill the phone with their ordinary life: family and friends, work, money, health, errands, plans, group chats,
receipts, newsletters, appointment reminders, delivery notices, bills, things that were sorted out and things still
open. Most of it should be specific everyday detail: plenty of people's routines and preferences, schedule changes,
house rules and standing arrangements, medication and appointment times, things people asked for, shared costs and
who paid what, plans that moved. Write notes in the owner's own voice.

Size: {counts}. Text and WhatsApp threads hold 2 to 8 messages each. Assistant chats are earlier conversations
between this person and their personal assistant, a few turns each. Most records are from the last 45 days, but
include a good number of older ones going back up to a year (old bookings, receipts, statements, notes).

{FORMAT}"""


def insert_prompt(p: dict, phone: dict, events: list = None) -> str:
    items = "\n".join(render(item) for item in (pieces_for(p["id"]) if events is None else events))
    shown = examples_for(p["id"]).get("placements", [])
    placement_block = ("Example from a different person's phone of an item placed inside an existing thread "
                       "(do not reuse its content):\n" + "\n".join(
                           f"- thread with {x['with']}\n  before: {json.dumps(x['before'], ensure_ascii=False)}\n"
                           f"  after:  {json.dumps(x['after'], ensure_ascii=False)}" for x in shown)
                       + "\n\n") if shown else ""
    return f"""Below is the phone of {p['line']}, as of {p['today']} (Thursday), in JSON. Add the items listed after
it to the phone.

These items are needles going into a haystack. Each must look like hay: the same length, tone and format as the
records around it, placed among records on similar topics, with nothing about its position, wording, id or timing
that marks it as added. If an existing record would make an item look out of place (a note that should have
mentioned it, a thread it obviously belongs in), make the smallest consistency edit so it fits.

{placement_block}Rules:
- Place each item in its suggested app at its suggested time (relative to today), either as a new record or as a new
  message inside an existing thread with the same person, so that it sits naturally among the other records.
- Keep what each item says exactly. Change wording only so it fits its record (a note in the owner's own voice).
- Place each item in a thread or app this person already uses with that contact. Don't open a new channel just for
  an item.
- Items shown as one conversation go in one thread, in that order.
- Give every record the same fields filled in as its neighbours: a calendar entry gets a location or notes like the
  entries around it, an email a real subject and sign-off, a transaction the same style of description.
- The word-for-word records must keep every quoted sentence exactly; write the rest of each such record naturally
  around the "…", and date it from its "when" hint.
- Add nothing else about these matters. At most one neutral acknowledgement from this person ("thanks!", "ok") after
  a message, or none. No decisions, times, plans, outcomes or follow-ups, and no new calendar entries, notes or
  assistant-chat turns about them unless the item itself is one. A message that arrived unread stays unread and
  unanswered.
- Where an existing record contradicts an item or already settles its matter (for example a different version of
  the same schedule, an appointment already booked for something an item leaves open, a conflicting address or
  date), change that record as little as possible so it no longer does: prefer moving or adjusting it (another
  date, another person, another subject) over deleting it. Similar records are welcome as long as they don't make
  any item ambiguous. Delete only when nothing else works. Leave every other record unchanged.

Return only the records you added or changed, under the same section names (empty lists elsewhere), and the ids of
any records you deleted in deleted_ids. Return a changed thread in full, with all its messages. New records get new
ids that continue each section's numbering. Add any new person to contacts.

{FORMAT}

Items:
{items}

Word-for-word records:
{quoted_lines(p)}

Phone:
{json.dumps(phone, ensure_ascii=False)}"""


def fixup_prompt(p: dict, phone: dict, events: list, edits: str) -> str:
    items = "\n".join(render(item) for item in events)
    return f"""Below is the phone of {p['line']}, as of {p['today']} (Thursday), in JSON, and a list of items that are
part of it. Make only the consistency edits listed, each as small as possible, preferring moving or adjusting a
record over deleting it. Keep every item exactly as it is, and add no decisions, plans, outcomes or follow-ups.

Edits to make:
{edits}

Return only the records you changed, under the same section names (empty lists elsewhere), and the ids of any
records you deleted in deleted_ids. Return a changed thread in full, with all its messages.

{FORMAT}

Items:
{items}

Phone:
{json.dumps(phone, ensure_ascii=False)}"""


def merge(phone: dict, edits: dict) -> dict:
    """Apply the insertion pass: records with a known id replace the old one, others are added."""
    out = {k: list(v) for k, v in phone.items()}
    gone = set(edits.get("deleted_ids", []))
    for sec in out:
        if sec != "contacts":
            out[sec] = [r for r in out[sec] if r["id"] not in gone]
    for sec, recs in edits.items():
        if sec == "deleted_ids":
            continue
        if sec == "contacts":
            known = {c["name"] for c in out["contacts"]}
            out["contacts"] += [c for c in recs if c["name"] not in known]
            continue
        index = {r["id"]: i for i, r in enumerate(out[sec])}
        for r in recs:
            if r["id"] in index:
                out[sec][index[r["id"]]] = r
            else:
                out[sec].append(r)
    return out


PREFIX = {"email": "e", "texts": "t", "whatsapp": "w", "notes": "n", "calendar": "c", "assistant_chats": "a",
          "transactions": "x"}
SORT_KEY = {"email": lambda r: r["date"], "texts": lambda r: min(m["date"] for m in r["messages"]),
            "whatsapp": lambda r: min(m["date"] for m in r["messages"]), "notes": lambda r: r["updated"],
            "calendar": lambda r: r["start"], "assistant_chats": lambda r: r["date"],
            "transactions": lambda r: r["date"]}


TEST_DOMAIN = re.compile(r"(@[\w.-]+)\.test\b")
DASH = re.compile(r"[–—]")


def real_domains(obj):
    """Seed records use .test email domains and typographic dashes; everything else uses real-looking domains and
    plain hyphens, so make them match."""
    if isinstance(obj, str):
        return DASH.sub("-", TEST_DOMAIN.sub(r"\1.com", obj))
    if isinstance(obj, list):
        return [real_domains(x) for x in obj]
    if isinstance(obj, dict):
        return {k: real_domains(v) for k, v in obj.items()}
    return obj


def normalize(phone: dict) -> tuple:
    """Sort every section by date and renumber ids in that order, so records placed late don't stand out by
    position or id. Returns the new phone and a map from old to new ids."""
    out, idmap = {}, {}
    phone = real_domains(phone)
    for sec, recs in phone.items():
        if sec not in PREFIX:
            out[sec] = recs
            continue
        ordered = sorted(recs, key=SORT_KEY[sec])
        out[sec] = []
        for i, r in enumerate(ordered, 1):
            new = f"{PREFIX[sec]}{i}"
            idmap[r["id"]] = new
            out[sec].append({**r, "id": new})
    return out, idmap


def map_id(rid: str, idmap: dict) -> str:
    base, _, rest = rid.partition(".")
    return idmap.get(base, base) + (f".{rest}" if rest else "")


async def ask(client, model: str, content: str, schema: dict, max_tokens: int = 120000):
    params = dict(model=model, max_tokens=max_tokens, system=SYSTEM, messages=[{"role": "user", "content": content}],
                  output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}})
    # server-side fallback: if a safety filter declines (false positives on medical details happen), the API
    # reruns the request on a fallback model inside the same call
    async with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"],
                                           extra_body={"fallbacks": "default"}, **params) as s:
        msg = await s.get_final_message()
    if msg.stop_reason != "end_turn":
        raise RuntimeError(f"stopped with {msg.stop_reason}")
    return json.loads(next(b.text for b in msg.content if b.type == "text")), msg.usage


async def generate_one(client, p: dict, model: str) -> dict:
    """The filler pass knows the standing facts (routines, rules) but never the events; insertion places the events."""
    cast, _ = await ask(client, model, cast_prompt(p), CAST_SCHEMA, 8000)
    kinds, _ = await ask(client, model, kinds_prompt(p), KINDS_SCHEMA, 8000)
    standing, events = split_kinds(p["id"], kinds["kinds"])
    filler, u1 = await ask(client, model, filler_prompt(p, cast["people"], standing, kinds["services"]), PHONE_SCHEMA)
    edits, u2 = await ask(client, model, insert_prompt(p, filler, events), INSERT_SCHEMA)
    phone, _ = normalize(merge(filler, edits))
    person = {k: p[k] for k in ("id", "name", "line", "pronoun", "today")}
    changed = sum(len(v) for v in edits.values())
    return {"person": person, **phone,
            "_usage": {"in": u1.input_tokens + u2.input_tokens, "out": u1.output_tokens + u2.output_tokens,
                       "changed": changed}}


def load_env(path: Path = ROOT / ".env") -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


async def main(args) -> None:
    from anthropic import AsyncAnthropic
    load_env()
    people = json.loads(SEEDS.read_text())
    if args.people:
        people = [p for p in people if p["id"] in args.people.split(",")]
    client = AsyncAnthropic()
    sem = asyncio.Semaphore(args.concurrency)

    async def run(p):
        async with sem:
            out = await generate_one(client, p, args.model)
        usage = out.pop("_usage")
        DATA.mkdir(exist_ok=True)
        (DATA / f"{p['id']}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        sizes = {k: f"{len(out[k])}/{n}" for k, n in targets(p["id"]).items()}
        print(f"{p['id']:8} in={usage['in']} out={usage['out']} records placed or changed={usage['changed']} {sizes}",
              flush=True)

    results = await asyncio.gather(*(run(p) for p in people), return_exceptions=True)
    for p, r in zip(people, results):
        if isinstance(r, Exception):
            print(f"{p['id']:8} FAILED: {type(r).__name__}: {str(r)[:300]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--people", default="")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--concurrency", type=int, default=7)
    asyncio.run(main(ap.parse_args()))

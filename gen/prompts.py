"""Run the generation and checks step by step without API calls: write each step's exact prompt and schema to a
task file for someone else to answer, validate the answers, merge them, and report.

  python -m gen.prompts --person wei --work DIR --step cast|kinds|filler|insert|check|blind   # write a task file
  python -m gen.prompts --person wei --work DIR --step validate --of cast                # check an answer
  python -m gen.prompts --person wei --work DIR --step merge                             # build data/<id>.json
  python -m gen.prompts --person wei --work DIR --step report                            # all checks

Each task file holds the same prompt and schema that generate.py and check.py send. The answer for step X is
expected at DIR/<person>/X.json.
"""
import argparse
import json
import sys
from pathlib import Path

import jsonschema

from gen import check
from gen.generate import (CAST_SCHEMA, DATA, INSERT_SCHEMA, KINDS_SCHEMA, PHONE_SCHEMA, SEEDS, SYSTEM, cast_prompt,
                          filler_prompt, fixup_prompt, insert_prompt, kinds_prompt, map_id, merge, normalize,
                          split_kinds)
from gen.split import PIECES

SCHEMAS = {"cast": CAST_SCHEMA, "kinds": KINDS_SCHEMA, "filler": PHONE_SCHEMA, "insert": INSERT_SCHEMA,
           "fixup": INSERT_SCHEMA,
           "check": check.CHECK_SCHEMA, "blind": check.BLIND_SCHEMA}


def load(path: Path):
    return json.loads(path.read_text())


def task(step: str, p: dict, work: Path) -> str:
    phone_path = DATA / f"{p['id']}.json"
    if step == "cast":
        return SYSTEM + "\n\n" + cast_prompt(p)
    if step == "kinds":
        return kinds_prompt(p)
    if step in ("filler", "insert"):
        standing, events = split_kinds(p["id"], load(work / "kinds.json")["kinds"])
        if step == "filler":
            services = load(work / "kinds.json").get("services", [])
            return SYSTEM + "\n\n" + filler_prompt(p, load(work / "cast.json")["people"], standing, services)
        return SYSTEM + "\n\n" + insert_prompt(p, load(work / "filler.json"), events)
    if step == "fixup":
        _, events = split_kinds(p["id"], load(work / "kinds.json")["kinds"])
        return SYSTEM + "\n\n" + fixup_prompt(p, load(phone_path), events, (work / "fixup.edits.md").read_text())
    if step == "check":
        return check.check_prompt(load(phone_path), load(PIECES)[p["id"]])
    if step == "blind":
        return check.blind_prompt(load(phone_path))
    raise ValueError(step)


def write_task(step: str, p: dict, work: Path) -> Path:
    out = work / f"{step}.task.md"
    out.write_text(task(step, p, work) + "\n\nThe answer is a single JSON value matching this JSON schema:\n"
                   + json.dumps(SCHEMAS[step], indent=1) + "\n")
    return out


def validate(step: str, work: Path) -> list:
    try:
        data = load(work / f"{step}.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{step}.json unreadable: {exc}"]
    v = jsonschema.Draft202012Validator(SCHEMAS[step])
    return [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message[:160]}" for e in v.iter_errors(data)][:20]


def do_merge(p: dict, work: Path) -> Path:
    phone, idmap = normalize(merge(load(work / "filler.json"), load(work / "insert.json")))
    (work / "idmap.json").write_text(json.dumps(idmap, indent=1))
    person = {k: p[k] for k in ("id", "name", "line", "pronoun", "today")}
    DATA.mkdir(exist_ok=True)
    out = DATA / f"{p['id']}.json"
    out.write_text(json.dumps({"person": person, **phone}, indent=1, ensure_ascii=False) + "\n")
    return out


def apply_fixup(p: dict, work: Path) -> Path:
    """Merge fixup.json into the finished phone, then sort and renumber again."""
    path = DATA / f"{p['id']}.json"
    full = load(path)
    person = full.pop("person")
    phone, idmap = normalize(merge(full, load(work / "fixup.json")))
    (work / "idmap.fixup.json").write_text(json.dumps(idmap, indent=1))
    path.write_text(json.dumps({"person": person, **phone}, indent=1, ensure_ascii=False) + "\n")
    return path


def translate_check(work: Path) -> None:
    """Rewrite check.json's record ids through idmap.json (for a check made before renumbering)."""
    idmap, found = load(work / "idmap.json"), load(work / "check.json")
    (work / "check.before-renumber.json").write_text(json.dumps(found, indent=1))
    for f in found["facts"]:
        for k in ("stated_outright_in", "trigger_found_in", "settled_in", "echoed_in"):
            f[k] = [map_id(x, idmap) for x in f[k]]
        for pc in f["pieces"]:
            pc["record"] = map_id(pc["record"], idmap) if pc["record"] else ""
    for c in found["contradictions"]:
        c["records"] = [map_id(x, idmap) for x in c["records"]]
    (work / "check.json").write_text(json.dumps(found, indent=1))


def report(p: dict, work: Path) -> list:
    phone = load(DATA / f"{p['id']}.json")
    facts = load(PIECES)[p["id"]]
    problems = check.format_problems(phone, p)
    found = load(work / "check.json")
    problems += check.piece_problems(found, facts)
    if (work / "blind.json").exists():
        picks = load(work / "blind.json")["ids"][:check.BLIND_PICKS]
        problems += check.blind_problems(picks, found, phone)
        problems.append(f"(blind picks: {picks})")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True)
    ap.add_argument("--work", required=True, help="scratch folder outside the repo")
    ap.add_argument("--step", required=True,
                    choices=["cast", "kinds", "filler", "insert", "fixup", "check", "blind", "validate", "merge",
                             "apply-fixup", "report", "translate"])
    ap.add_argument("--of", help="step whose answer to validate")
    a = ap.parse_args()
    p = {x["id"]: x for x in load(SEEDS)}[a.person]
    work = Path(a.work) / a.person
    work.mkdir(parents=True, exist_ok=True)
    if a.step == "validate":
        errors = validate(a.of, work)
        print("valid" if not errors else "\n".join(errors))
        return 1 if errors else 0
    if a.step == "apply-fixup":
        print(apply_fixup(p, work))
        return 0
    if a.step == "translate":
        translate_check(work)
        print("check.json ids translated")
        return 0
    if a.step == "merge":
        print(do_merge(p, work))
        return 0
    if a.step == "report":
        problems = report(p, work)
        real = [x for x in problems if not x.startswith("(")]
        print(f"{a.person}: {'ok' if not real else str(len(real)) + ' problem(s)'}")
        for x in problems:
            print("  -", x)
        return 1 if real else 0
    path = write_task(a.step, p, work)
    print(f"task: {path}\nanswer: {work / (a.step + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build seeds/people.json from PersonalAgentEval's published data (personalagenteval.com).

For each person: the blog's own one-line profile, the facts the blog tested for that person, and the records
the blog quotes word for word. Downloads go to a fresh temp folder and are parsed as data only.

  python -m seeds.fetch_seeds
"""
import html
import json
import re
import tempfile
import urllib.request
from pathlib import Path

SITE = "https://personalagenteval.com"
SOURCES = {"findings": "/data/assistants/findings.json", "tasks": "/data/assistants/tasks.json",
           "fails": "/assistants/fails.js"}
PEOPLE = ["priya", "eleanor", "hannah", "alice", "wei", "tomas", "devon"]
TODAY = "2026-10-08T09:00"
QUOTED_SCENES = {"Shopping": "priya", "Dining": "priya", "Work": "tomas", "Health": "wei", "Home": "eleanor"}
OUT = Path(__file__).resolve().parent / "people.json"

STR = r'"((?:[^"\\]|\\.)*)"'
RECORD = re.compile(r'\{\s*(?:first: true,\s*)?kind: ' + STR + r', from: ' + STR + r'(?:, subj: ' + STR + r')?'
                    r'(?:, when: ' + STR + r')?(?:, stamp: ' + STR + r')?,\s*body: ' + STR)


def download(dest: Path) -> dict:
    files = {}
    for name, path in SOURCES.items():
        target = dest / Path(path).name
        with urllib.request.urlopen(SITE + path, timeout=30) as r:
            target.write_bytes(r.read())
        files[name] = target
    return files


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s.encode().decode("unicode_escape").encode("latin-1").decode("utf-8"))
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def quoted_records(fails_js: str) -> dict:
    starts = [(m.start(), m.group(1)) for m in re.finditer(r'dom: "(\w+)"', fails_js)]
    out = {}
    for i, (pos, dom) in enumerate(starts):
        if dom not in QUOTED_SCENES:
            continue
        chunk = fails_js[pos: starts[i + 1][0] if i + 1 < len(starts) else len(fails_js)]
        for kind, frm, subj, when, _stamp, body in RECORD.findall(chunk):
            out.setdefault(QUOTED_SCENES[dom], []).append(
                {"kind": kind, "from": clean(frm), "subject": clean(subj), "when": clean(when), "text": clean(body)})
    return out


def build(files: dict) -> list:
    findings = json.loads(files["findings"].read_text())
    tasks = json.loads(files["tasks"].read_text())
    quotes = quoted_records(files["fails"].read_text(encoding="utf-8"))
    profiles = {p["id"]: p for p in tasks["people"]}
    people = []
    for pid in PEOPLE:
        facts = [{"episode": f["episode"], "title": f["title"], "fact": f["fact"]}
                 for f in findings["found_first"]["facts"] if f["episode"].startswith(pid + "_")]
        p = profiles[pid]
        people.append({"id": pid, "name": p["line"].split(",")[0], "line": p["line"], "pronoun": p["pronoun"],
                       "today": TODAY, "facts": facts, "quoted": quotes.get(pid, [])})
    return people


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="pae-src-") as tmp:
        people = build(download(Path(tmp)))
    OUT.write_text(json.dumps(people, indent=1, ensure_ascii=False) + "\n")
    for p in people:
        print(f"{p['id']:8} {len(p['facts']):2} facts  {len(p['quoted'])} quoted records  | {p['line']}")

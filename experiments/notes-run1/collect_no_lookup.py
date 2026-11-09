"""Save the no-lookup quiz answers from this run's Cursor subagent logs."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = Path.home() / (".cursor/projects/Users-yashtikekar-Desktop-Projects-personal-agent-memory-test/"
                      "agent-transcripts/02abdc73-eebe-42ab-be62-4d64d08d3a8b/subagents")

AGENTS = {
    ("wei", "facts"): "2c53f5d2-9e6c-4423-aee6-167bc4545966",
    ("wei", "implications"): "54e8a961-a865-45da-ab99-97d30b870512",
    ("tomas", "facts"): "1fd3de65-6a30-4d82-b7b2-7df70b518079",
    ("tomas", "implications"): "f7c8af39-a2b7-46d5-a7df-f7dfd3829114",
    ("priya", "facts"): "ef2cf611-a53d-4d69-8869-0715a141cba2",
    ("priya", "implications"): "ccb281bf-5be9-4d67-bee4-218a57046afe",
    ("devon", "facts"): "cd8c2555-ccd6-42fe-8a9b-7fc17a97c072",
    ("devon", "implications"): "4796a3d3-df39-41e2-958b-a91a7eb919d6",
    ("alice", "facts"): "adeca7e2-2107-47aa-8997-ec00d7446993",
    ("alice", "implications"): "c9c27a7f-e015-42c7-ac0a-fe6dfb95c058",
    ("hannah", "facts"): "24c07a2f-954e-4701-ac83-62cd7a7302ed",
    ("hannah", "implications"): "7cc2f637-1a4e-4552-8054-496153ecae5a",
    ("eleanor", "facts"): "4100e080-8541-4384-a40e-316c049b84f7",
    ("eleanor", "implications"): "1eee1433-9249-43bf-8e9f-b0e955d7cefd",
}
GRADES = {
    ("wei", "facts"): [1, 0, 0, 0, 0, 1],
    ("wei", "implications"): [1, 1, 0, 1, 0, 1],
    ("tomas", "facts"): [0, 0, 1, 0, 0, 0],
    ("tomas", "implications"): [0, 1, 1, 0, 0, 0],
    ("priya", "facts"): [0, 0, 0, 0, 0, 0],
    ("priya", "implications"): [0, 0, 0, 0, 0, 0],
    ("devon", "facts"): [0, 0, 0, 0, 0],
    ("devon", "implications"): [0, 1, 0, 1, 0],
    ("alice", "facts"): [0, 0, 0, 0, 0, 1],
    ("alice", "implications"): [0, 0, 0, 0, 0, 0],
    ("hannah", "facts"): [1, 0, 0, 0, 1],
    ("hannah", "implications"): [1, 0, 0, 0, 1],
    ("eleanor", "facts"): [1, 1, 0, 0, 0, 0],
    ("eleanor", "implications"): [1, 1, 0, 0, 0, 1],
}


def answer_from_log(agent: str) -> str:
    answer = ""
    for line in (LOGS / f"{agent}.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event.get("role") != "assistant":
            continue
        for content in (event.get("message") or {}).get("content") or []:
            if isinstance(content, dict) and content.get("type") == "text":
                answer = content.get("text", "").strip().split("\n\n", 1)[0]
    return answer


def main() -> None:
    rows = []
    for key, agent in AGENTS.items():
        person, arm = key
        rows.append({"person": person, "arm": arm, "agent": agent, "correct": GRADES[key],
                     "score": sum(GRADES[key]), "answer": answer_from_log(agent)})
    (HERE / "no_lookup_results.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    for arm in ("facts", "implications"):
        score = sum(row["score"] for row in rows if row["arm"] == arm)
        print(f"{arm:12} {score}/40")


if __name__ == "__main__":
    main()

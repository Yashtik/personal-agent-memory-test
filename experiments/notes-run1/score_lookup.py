"""Score the lookup run.

Wrong answers earn 0. A correct answer earns 1 without lookup and
1 - penalty with one or more lookups.

  python3 score_lookup.py
  python3 score_lookup.py --penalty 0.5
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(penalty: float) -> None:
    rows = json.loads((HERE / "lookup_results.json").read_text())
    totals = defaultdict(lambda: {"raw": 0, "weighted": 0.0, "looked_up": 0, "searches": 0,
                                  "catch": 0, "other": 0})
    for row in rows:
        arm = row["arm"]
        correct = int(row["correct"])
        used_lookup = bool(row["searches"])
        totals[arm]["raw"] += correct
        totals[arm]["weighted"] += correct * (1 - penalty if used_lookup else 1)
        totals[arm]["looked_up"] += used_lookup
        totals[arm]["searches"] += len(row["searches"])
        totals[arm]["catch" if row["type"] == "catch" else "other"] += correct

    for arm in ("facts", "implications"):
        t = totals[arm]
        print(f"{arm:12} raw={t['raw']}/40 weighted={t['weighted']:.1f}/40 "
              f"catch={t['catch']}/20 other={t['other']}/20 "
              f"questions_searched={t['looked_up']}/40 searches={t['searches']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--penalty", type=float, default=0.5)
    args = parser.parse_args()
    if not 0 <= args.penalty <= 1:
        parser.error("penalty must be between 0 and 1")
    main(args.penalty)

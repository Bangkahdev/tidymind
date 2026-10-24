"""Release gate (SRS 8.4): mutation score >= 80% on validator/executor.

Reads the stats file written by `mutmut export-cicd-stats`. Surviving mutants must still be
reviewed and classified by a human (docs/MUTATION-REVIEW.md); this only enforces the number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLD = 80.0


def main(path: str = "mutants/mutmut-cicd-stats.json") -> int:
    file = Path(path)
    if not file.exists():
        print(f"FAIL: {path} not found. Run `mutmut run` then `mutmut export-cicd-stats`.")
        return 1
    stats = json.loads(file.read_text())
    killed = stats.get("killed", 0) + stats.get("timeout", 0)
    judged = killed + stats.get("survived", 0) + stats.get("suspicious", 0) + stats.get("no_tests", 0)
    if judged == 0:
        print("FAIL: no mutants were judged.")
        return 1
    score = 100.0 * killed / judged
    print(f"Mutation score: {score:.1f}% ({killed}/{judged} killed); threshold {THRESHOLD}%")
    return 0 if score >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))

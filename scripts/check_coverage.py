"""Enforce SRS 8.3 thresholds from `coverage json` output (statement AND branch)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# (label, path fragment or None for overall, min statement %, min branch %)
GATES = [
    ("overall", None, 90.0, 85.0),
    ("validator", "tidymind/validator.py", 95.0, 90.0),
    ("executor", "tidymind/executor.py", 95.0, 90.0),
]


def pct(covered: int, total: int) -> float:
    return 100.0 if total == 0 else 100.0 * covered / total


def main(path: str = "coverage.json") -> int:
    files = json.loads(Path(path).read_text())["files"]
    failed = False
    for label, fragment, need_stmt, need_branch in GATES:
        selected = [
            v["summary"] for k, v in files.items() if fragment is None or k.replace("\\", "/").endswith(fragment)
        ]
        if not selected:
            print(f"FAIL {label}: no coverage data found")
            failed = True
            continue
        stmt = pct(sum(s["covered_lines"] for s in selected), sum(s["num_statements"] for s in selected))
        branch = pct(sum(s["covered_branches"] for s in selected), sum(s["num_branches"] for s in selected))
        ok = stmt >= need_stmt and branch >= need_branch
        failed |= not ok
        print(
            f"{'PASS' if ok else 'FAIL'} {label}: statements {stmt:.1f}% (>= {need_stmt}), branches {branch:.1f}% (>= {need_branch})"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))

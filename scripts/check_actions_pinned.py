"""Release gate (SRS 9.5): every third-party `uses:` must be a full 40-hex commit SHA."""

from __future__ import annotations

import re
import sys
from pathlib import Path

USES = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>\S+)", re.MULTILINE)
SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def main() -> int:
    problems: list[str] = []
    for workflow in sorted(Path(".github/workflows").glob("*.y*ml")):
        for match in USES.finditer(workflow.read_text(encoding="utf-8")):
            ref = match.group("ref")
            if ref.startswith("./") or SHA.match(ref):
                continue
            problems.append(f"{workflow}: {ref} is not pinned to a full commit SHA")
    if problems:
        print("\n".join(problems))
        print("Pin with: pinact run   (https://github.com/suzuki-shunsuke/pinact)")
        return 1
    print("All actions are pinned to full commit SHAs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

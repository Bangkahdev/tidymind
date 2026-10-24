"""Fail if model weights, caches, venvs, local plans or build artifacts are tracked (SRS 9.2 #11)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath

FORBIDDEN_SUFFIXES = (".gguf", ".safetensors", ".onnx", ".pyc", ".whl", ".egg")
FORBIDDEN_DIRS = {
    "__pycache__", ".venv", "venv", ".mypy_cache", ".ruff_cache", ".hypothesis", "dist", "build", "mutants",
}  # fmt: skip


def violations(files: list[str]) -> list[str]:
    bad: list[str] = []
    for name in files:
        path = PurePosixPath(name)
        if (
            name.endswith(FORBIDDEN_SUFFIXES)
            or FORBIDDEN_DIRS & set(path.parts[:-1])
            or (len(path.parts) == 1 and name.startswith("plan") and name.endswith(".json"))
            or name == ".env"
        ):
            bad.append(name)
    return bad


def main() -> int:
    files = subprocess.run(  # noqa: S603
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,  # noqa: S607
    ).stdout.splitlines()
    bad = violations(files)
    if bad:
        print("Repository hygiene violations:\n  " + "\n  ".join(bad))
        return 1
    print(f"Repository hygiene OK ({len(files)} tracked files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

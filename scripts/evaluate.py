"""Model quality evaluation against a REAL local Ollama model (SRS 8.8).

Usage: python scripts/evaluate.py [--model qwen3:4b] [--endpoint http://127.0.0.1:11434]
Prints a Markdown report to paste into docs/EVALUATION.md. Nothing is claimed unless this is run.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tidymind.errors import ModelError  # noqa: E402
from tidymind.model_client import DEFAULT_ENDPOINT, DEFAULT_MODEL, OllamaClient  # noqa: E402
from tidymind.models import FileEntry  # noqa: E402
from tidymind.validator import target_name_problem  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = parser.parse_args()
    rows = json.loads((Path(__file__).resolve().parents[1] / "eval" / "dataset.json").read_text())["files"]
    entries = [FileEntry(r["name"], r["extension"], r["size_bytes"], 0) for r in rows]
    client = OllamaClient(endpoint=args.endpoint, model=args.model, batch_size=len(entries), max_attempts=1)

    started = time.perf_counter()
    try:
        suggestions = client.suggest(entries)
    except ModelError as exc:
        print(f"# Evaluation\n\nInvalid model response or runtime failure: {exc}")
        return 4
    elapsed = time.perf_counter() - started

    correct = [s.category == r["expected_category"] for s, r in zip(suggestions, rows, strict=True)]
    renamed = [(r["name"], s.target_name) for s, r in zip(suggestions, rows, strict=True) if s.target_name != r["name"]]
    unsafe = [
        (r["name"], s.target_name)
        for s, r in zip(suggestions, rows, strict=True)
        if target_name_problem(r["name"], s.target_name)
    ]
    print("# Category evaluation\n")
    print(f"- Files evaluated: {len(rows)}")
    print(f"- Correct categories: {sum(correct)} ({100 * sum(correct) / len(rows):.1f}%)")
    print(f"- Unsafe name proposals rejected by the validator: {len(unsafe)}")
    print(f"- Model: `{args.model}`; OS: {platform.platform()}; Python {platform.python_version()}")
    print(f"- Inference duration (single batch): {elapsed:.1f}s")
    print("\n## Incorrect or ambiguous categories\n")
    for ok, s, r in zip(correct, suggestions, rows, strict=True):
        if not ok:
            print(f"- `{r['name']}`: expected {r['expected_category']}, got {s.category}")
    print("\n## Filename suggestions (evaluated separately; review manually)\n")
    for before, after in renamed:
        print(f"- `{before}` -> `{after}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

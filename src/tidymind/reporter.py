"""Reporter: plain-text summaries with no colour and no file contents."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from tidymind.executor import ItemOutcome, Status
from tidymind.models import ScanResult
from tidymind.textutil import safe_text


def render_scan(scan: ScanResult) -> str:
    lines = [
        f"Root: {safe_text(str(scan.root))}",
        f"Discovered: {scan.discovered_total}  Eligible: {len(scan.eligible)}  Excluded: {scan.excluded_total}",
        f"  excluded: hidden={scan.excluded_hidden} symlinks={scan.excluded_symlinks} "
        f"directories={scan.excluded_directories} special={scan.excluded_special}",
    ]
    lines += [f"  - {safe_text(e.name)} ({e.size} bytes)" for e in scan.eligible]
    return "\n".join(lines)


def count_outcomes(outcomes: Sequence[ItemOutcome]) -> Counter[Status]:
    return Counter(o.status for o in outcomes)


def render_results(outcomes: Sequence[ItemOutcome]) -> str:
    counts = count_outcomes(outcomes)
    lines = [
        f"Result: succeeded={counts[Status.SUCCEEDED]} skipped={counts[Status.SKIPPED]} failed={counts[Status.FAILED]}"
    ]
    for outcome in outcomes:
        target = f" -> {safe_text(outcome.target)}" if outcome.target else ""
        lines.append(
            f"  [{outcome.status.value.upper()}] {safe_text(outcome.source_name)}{target}: {safe_text(outcome.detail)}"
        )
    if counts[Status.SKIPPED] or counts[Status.FAILED]:
        lines.append(
            "Not all operations completed. There is no batch rollback; "
            "completed moves stay in place. Generate a new plan to retry."
        )
    return "\n".join(lines)

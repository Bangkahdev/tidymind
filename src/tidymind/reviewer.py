"""Reviewer: renders the full plan preview and obtains explicit approval."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tidymind.textutil import safe_text
from tidymind.validator import ValidationReport

_APPROVE = {"y", "yes"}


def render_preview(report: ValidationReport) -> str:
    lines = [f"Plan for: {safe_text(str(report.root))}", ""]
    for number, result in enumerate(report.results, start=1):
        item = result.item
        source = safe_text(item.source_name)
        if result.ok:
            target = safe_text(f"{item.category}/{item.target_name}")
            lines.append(f"{number:>3}. [OK]   {source}  ->  {target}")
            if item.reason:
                lines.append(f"       reason: {safe_text(item.reason)}")
        else:
            lines.append(f"{number:>3}. [SKIP] {source}  --  {safe_text(result.reason or '')}")
    operations, skipped = len(report.operations), len(report.unsafe)
    lines += ["", f"{operations} operation(s) would run; {skipped} would be skipped."]
    return "\n".join(lines)


def confirm(
    operations: int,
    root: Path,
    ask: Callable[[str], str] = input,
) -> bool:
    """Only an explicit 'y'/'yes' approves. EOF, empty or invalid answers do not."""
    prompt = f"Move/rename {operations} file(s) inside {safe_text(str(root))}? [y/N]: "
    try:
        answer = ask(prompt)
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in _APPROVE

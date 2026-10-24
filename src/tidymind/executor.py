"""Executor: performs only validated, approved operations, never overwriting.

There is no delete operation here. Immediately before every move the source
identity, destination availability and root containment are re-checked.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tidymind.errors import NoClobberUnsupportedError
from tidymind.fsops import no_clobber_rename
from tidymind.validator import ValidationReport, check_state, derive_destination

Mover = Callable[[Path, Path], None]


class Status(StrEnum):
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class ItemOutcome:
    source_name: str
    target: str | None  # relative destination, e.g. "Documents/report.pdf"
    status: Status
    detail: str


def execute(report: ValidationReport, mover: Mover = no_clobber_rename) -> tuple[ItemOutcome, ...]:
    """Run every safe item; isolate per-item results (no batch rollback is promised)."""
    outcomes: list[ItemOutcome] = []
    root = report.root
    for result in report.results:
        item = result.item
        if not result.ok or result.destination is None:
            outcomes.append(
                ItemOutcome(item.source_name, None, Status.SKIPPED, result.reason or "unsafe")
            )
            continue
        relative = f"{item.category}/{item.target_name}"

        reason = check_state(root, item)  # re-check immediately before acting
        if reason:
            outcomes.append(ItemOutcome(item.source_name, relative, Status.SKIPPED, reason))
            continue

        destination = derive_destination(root, item)
        try:
            os.mkdir(destination.parent)
        except FileExistsError:
            pass
        except OSError as exc:
            detail = f"cannot create category folder: {exc.strerror or 'unknown error'}"
            outcomes.append(ItemOutcome(item.source_name, relative, Status.FAILED, detail))
            continue

        reason = check_state(root, item)  # the folder may have been swapped meanwhile
        if reason:
            outcomes.append(ItemOutcome(item.source_name, relative, Status.SKIPPED, reason))
            continue

        try:
            mover(root / item.source_name, destination)
        except FileExistsError:
            outcomes.append(
                ItemOutcome(
                    item.source_name,
                    relative,
                    Status.SKIPPED,
                    "destination appeared after the preview (not overwritten)",
                )
            )
        except NoClobberUnsupportedError:
            outcomes.append(
                ItemOutcome(
                    item.source_name,
                    relative,
                    Status.FAILED,
                    "this system cannot guarantee a no-overwrite move; refused",
                )
            )
        except OSError as exc:
            detail = f"move failed: {exc.strerror or 'unknown error'}"
            outcomes.append(ItemOutcome(item.source_name, relative, Status.FAILED, detail))
        else:
            outcomes.append(ItemOutcome(item.source_name, relative, Status.SUCCEEDED, "moved"))
    return tuple(outcomes)

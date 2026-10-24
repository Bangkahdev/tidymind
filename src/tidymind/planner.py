"""Planner: builds, serializes and strictly parses versioned JSON plans.

A plan never contains a destination path. Destinations are derived later by
application code from the validated root, an allowlisted category and a
validated basename.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tidymind.errors import InputError, PlanFormatError
from tidymind.models import SCHEMA_VERSION, FileEntry, Plan, PlanItem, ScanResult, Suggestion

MAX_PLAN_BYTES = 5 * 1024 * 1024
MAX_PLAN_ITEMS = 10_000

_TOP_KEYS = {"schema_version", "root", "items"}
_ITEM_FIELDS: dict[str, type] = {
    "source_name": str,
    "source_size": int,
    "source_mtime_ns": int,
    "category": str,
    "target_name": str,
    "reason": str,
}


def build_plan(scan: ScanResult, suggestions: Sequence[Suggestion]) -> Plan:
    if len(suggestions) != len(scan.eligible):
        raise ValueError("One suggestion per eligible file is required.")
    items = tuple(_item(entry, suggestion) for entry, suggestion in zip(scan.eligible, suggestions, strict=True))
    return Plan(schema_version=SCHEMA_VERSION, root=str(scan.root), items=items)


def _item(entry: FileEntry, suggestion: Suggestion) -> PlanItem:
    return PlanItem(
        source_name=entry.name,
        source_size=entry.size,
        source_mtime_ns=entry.mtime_ns,
        category=suggestion.category,
        target_name=suggestion.target_name,
        reason=suggestion.reason,
    )


def dump_plan(plan: Plan) -> str:
    """Deterministic serialization: fixed key order, items sorted by source name."""
    document = {
        "schema_version": plan.schema_version,
        "root": plan.root,
        "items": [
            {field: getattr(item, field) for field in _ITEM_FIELDS}
            for item in sorted(plan.items, key=lambda i: i.source_name)
        ],
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def write_plan(plan: Plan, path: str | os.PathLike[str]) -> None:
    """Write a plan without ever overwriting an existing file."""
    target = Path(path)
    try:
        with open(target, "x", encoding="utf-8", newline="\n") as handle:  # noqa: PTH123
            handle.write(dump_plan(plan))
    except FileExistsError:
        raise InputError(f"Output file already exists (not overwritten): {target}") from None
    except OSError as exc:
        raise InputError(f"Cannot write plan: {exc.strerror or 'unknown error'}") from None


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PlanFormatError("The plan contains a duplicate key.")
        result[key] = value
    return result


def _reject_constant(_: str) -> Any:
    raise PlanFormatError("The plan contains a non-standard JSON number.")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_plan(text: str) -> Plan:
    """Strictly parse plan text. Any structural problem raises PlanFormatError."""
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except PlanFormatError:
        raise
    except ValueError:
        raise PlanFormatError("The plan is not valid JSON.") from None
    if not isinstance(data, dict) or set(data) != _TOP_KEYS:
        raise PlanFormatError("The plan has an unexpected top-level structure.")
    version = data["schema_version"]
    if not _is_int(version):
        raise PlanFormatError("The plan schema_version must be an integer.")
    if version != SCHEMA_VERSION:
        raise PlanFormatError(f"Unsupported plan schema version: {version}.")
    if not isinstance(data["root"], str) or not data["root"]:
        raise PlanFormatError("The plan root must be a non-empty string.")
    raw_items = data["items"]
    if not isinstance(raw_items, list):
        raise PlanFormatError("The plan items must be a list.")
    if len(raw_items) > MAX_PLAN_ITEMS:
        raise PlanFormatError("The plan has too many items.")

    items: list[PlanItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict) or set(raw) != set(_ITEM_FIELDS):
            raise PlanFormatError("A plan item has missing or unexpected fields.")
        for field, expected in _ITEM_FIELDS.items():
            value = raw[field]
            ok = _is_int(value) if expected is int else isinstance(value, expected)
            if not ok:
                raise PlanFormatError(f"Plan item field '{field}' has the wrong type.")
        if raw["source_size"] < 0:
            raise PlanFormatError("Plan item field 'source_size' must not be negative.")
        items.append(PlanItem(**raw))
    return Plan(schema_version=version, root=data["root"], items=tuple(items))


def load_plan(path: str | os.PathLike[str]) -> Plan:
    target = Path(path)
    try:
        with open(target, "rb") as handle:  # noqa: PTH123
            raw = handle.read(MAX_PLAN_BYTES + 1)
    except FileNotFoundError:
        raise InputError(f"Plan file not found: {target}") from None
    except OSError as exc:
        raise InputError(f"Cannot read plan: {exc.strerror or 'unknown error'}") from None
    if len(raw) > MAX_PLAN_BYTES:
        raise PlanFormatError("The plan file is too large.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PlanFormatError("The plan is not valid UTF-8 text.") from None
    return parse_plan(text)

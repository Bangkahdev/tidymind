"""Validator: treats every plan (and all model output inside it) as untrusted.

Validation is fail-closed: an item that fails any rule is marked unsafe with a
reason and can never reach the executor. Unsafe targets are never silently
rewritten into different targets.
"""

from __future__ import annotations

import os
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from tidymind.errors import RootMismatchError
from tidymind.models import CATEGORY_DIRS, Plan, PlanItem

MAX_NAME_LENGTH = 255
_INVALID_TARGET_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)


@dataclass(frozen=True)
class ItemResult:
    item: PlanItem
    reason: str | None  # None means the item is safe to execute
    destination: Path | None

    @property
    def ok(self) -> bool:
        return self.reason is None


@dataclass(frozen=True)
class ValidationReport:
    root: Path
    results: tuple[ItemResult, ...]

    @property
    def operations(self) -> tuple[ItemResult, ...]:
        return tuple(r for r in self.results if r.ok)

    @property
    def unsafe(self) -> tuple[ItemResult, ...]:
        return tuple(r for r in self.results if not r.ok)


def _is_windows() -> bool:
    return os.name == "nt"


def _has_control_chars(name: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in name)


def _has_drive_prefix(name: str) -> bool:
    return len(name) >= 2 and name[1] == ":" and name[0].isalpha()


def source_name_problem(name: str) -> str | None:
    if not name or not name.strip():
        return "source name is empty"
    if name in (".", ".."):
        return "source name is a relative path component"
    if "/" in name or "\\" in name:
        return "source name contains a path separator"
    if _has_control_chars(name):
        return "source name contains control characters"
    if _has_drive_prefix(name) or (_is_windows() and ":" in name):
        return "source name contains a drive prefix or stream separator"
    if len(name) > MAX_NAME_LENGTH:
        return "source name is too long"
    return None


def target_name_problem(source_name: str, target: str) -> str | None:
    """Portable naming rules applied on every platform."""
    if not target or not target.strip():
        return "target name is empty"
    if target in (".", ".."):
        return "target name is a relative path component"
    if "/" in target or "\\" in target:
        return "target name contains a path separator"
    if _has_control_chars(target):
        return "target name contains control characters"
    if any(ch in _INVALID_TARGET_CHARS for ch in target):
        return "target name contains a character that is invalid on some platforms"
    if target != target.strip() or target.endswith("."):
        return "target name has leading/trailing spaces or a trailing dot"
    if target.startswith("."):
        return "target name would be hidden"
    if target.split(".")[0].rstrip(" ").upper() in _WINDOWS_RESERVED:
        return "target name is a reserved device name"
    if len(target) > MAX_NAME_LENGTH:
        return "target name is too long"
    if Path(target).suffix.lower() != Path(source_name).suffix.lower():
        return "target name changes the file extension"
    return None


def _category_dir(root: Path, item: PlanItem) -> Path:
    return root / CATEGORY_DIRS[item.category]


def derive_destination(root: Path, item: PlanItem) -> Path:
    """Application-derived destination; only call after name/category checks."""
    return _category_dir(root, item) / item.target_name


def _contained(root: Path, source: Path, destination: Path) -> bool:
    return source.parent == root and destination.parent.parent == root


def check_state(root: Path, item: PlanItem) -> str | None:
    """Inspect the real filesystem; used at validation time AND right before each move."""
    source = root / item.source_name
    destination = derive_destination(root, item)
    if not _contained(root, source, destination):
        return "path escapes the selected root"
    try:
        info = os.lstat(source)
    except FileNotFoundError:
        return "source file is missing"
    except OSError:
        return "source file cannot be inspected"
    if stat.S_ISLNK(info.st_mode):
        return "source is a symbolic link"
    if not stat.S_ISREG(info.st_mode):
        return "source is not a regular file"
    if info.st_size != item.source_size or info.st_mtime_ns != item.source_mtime_ns:
        return "source changed since the plan was created (stale plan)"
    try:
        category_info = os.lstat(destination.parent)
    except FileNotFoundError:
        category_info = None
    except OSError:
        return "category folder cannot be inspected"
    if category_info is not None:
        if stat.S_ISLNK(category_info.st_mode):
            return "category folder is a symbolic link"
        if not stat.S_ISDIR(category_info.st_mode):
            return "a file blocks the category folder name"
    if os.path.lexists(destination):
        return "destination already exists (never overwritten)"
    return None


def resolve_plan_root(plan: Plan, expected: Path | None = None) -> Path:
    """Return the canonical execution root or raise RootMismatchError."""
    plan_root = Path(plan.root)
    if not plan_root.is_absolute():
        raise RootMismatchError("The plan root must be an absolute path.")
    try:
        resolved = plan_root.resolve(strict=True)
    except OSError:
        raise RootMismatchError("The plan root does not exist or cannot be accessed.") from None
    if not resolved.is_dir():
        raise RootMismatchError("The plan root is not a directory.")
    if resolved != plan_root:
        raise RootMismatchError("The plan root is not a canonical path (symlink or '..').")
    if expected is not None and expected != resolved:
        raise RootMismatchError("The plan root does not match the expected directory.")
    return resolved


def _name_problem(item: PlanItem) -> str | None:
    problem = source_name_problem(item.source_name)
    if problem:
        return problem
    if item.category not in CATEGORY_DIRS:
        return "category is not in the allowlist"
    return target_name_problem(item.source_name, item.target_name)


def _item_problem(root: Path, item: PlanItem) -> str | None:
    return _name_problem(item) or check_state(root, item)


def validate_plan(plan: Plan, expected_root: Path | None = None) -> ValidationReport:
    root = resolve_plan_root(plan, expected_root)
    reasons: list[str | None] = [_item_problem(root, item) for item in plan.items]

    source_counts = Counter(item.source_name.casefold() for item in plan.items)
    destination_counts = Counter(
        (item.category, item.target_name.casefold())
        for item, reason in zip(plan.items, reasons, strict=True)
        if reason is None
    )
    results: list[ItemResult] = []
    for item, reason in zip(plan.items, reasons, strict=True):
        if reason is None and source_counts[item.source_name.casefold()] > 1:
            reason = "source appears more than once in the plan"
        elif reason is None and destination_counts[(item.category, item.target_name.casefold())] > 1:
            reason = "another item in the plan has the same destination"
        destination = None if _name_problem(item) else derive_destination(root, item)
        results.append(ItemResult(item, reason, destination))
    return ValidationReport(root, tuple(results))

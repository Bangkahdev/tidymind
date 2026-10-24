"""Plain data types shared across modules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1

CATEGORIES: tuple[str, ...] = ("Documents", "Images", "Archives", "Installers", "Other")

# Application code (not the model) decides the sub-directory for a category.
CATEGORY_DIRS: dict[str, str] = {name: name for name in CATEGORIES}


@dataclass(frozen=True)
class FileEntry:
    """Metadata for one eligible regular file directly inside the root."""

    name: str
    extension: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class ScanResult:
    root: Path
    eligible: tuple[FileEntry, ...]
    excluded_hidden: int
    excluded_symlinks: int
    excluded_directories: int
    excluded_special: int

    @property
    def excluded_total(self) -> int:
        return self.excluded_hidden + self.excluded_symlinks + self.excluded_directories + self.excluded_special

    @property
    def discovered_total(self) -> int:
        return len(self.eligible) + self.excluded_total


@dataclass(frozen=True)
class Suggestion:
    """A validated model suggestion for one file (still untrusted advice)."""

    category: str
    target_name: str
    reason: str


@dataclass(frozen=True)
class PlanItem:
    source_name: str
    source_size: int
    source_mtime_ns: int
    category: str
    target_name: str
    reason: str


@dataclass(frozen=True)
class Plan:
    schema_version: int
    root: str
    items: tuple[PlanItem, ...]

"""Scanner: finds eligible regular files directly inside one directory.

Policy (identical on every platform, documented in the README):
  * only direct children are examined (no recursion);
  * hidden entries are excluded: names starting with "." on every platform,
    plus the Windows "hidden" file attribute;
  * symbolic links, directories and special files are excluded;
  * file contents are never opened.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from tidymind.errors import ScanError
from tidymind.models import FileEntry, ScanResult


def resolve_root(directory: str | os.PathLike[str]) -> Path:
    """Return the fully resolved root directory or raise ScanError."""
    given = os.fspath(directory)
    try:
        root = Path(given).resolve(strict=True)
    except FileNotFoundError:
        raise ScanError(f"Directory not found: {given}") from None
    except OSError as exc:
        raise ScanError(f"Cannot access {given}: {exc.strerror or 'unknown error'}") from None
    if not root.is_dir():
        raise ScanError(f"Not a directory: {given}")
    return root


def scan(directory: str | os.PathLike[str]) -> ScanResult:
    """Scan ``directory`` without modifying anything."""
    root = resolve_root(directory)
    try:
        with os.scandir(root) as iterator:
            entries = sorted(iterator, key=lambda e: e.name)
    except OSError as exc:
        raise ScanError(f"Cannot read directory {os.fspath(directory)}: {exc.strerror or 'unknown error'}") from None

    eligible: list[FileEntry] = []
    hidden = symlinks = directories = special = 0

    for entry in entries:
        name = entry.name
        if name.startswith("."):
            hidden += 1
            continue
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError:
            special += 1  # metadata unreadable: cannot be processed safely
            continue
        if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_HIDDEN:
            hidden += 1
        elif stat.S_ISLNK(info.st_mode):
            symlinks += 1
        elif stat.S_ISDIR(info.st_mode):
            directories += 1
        elif stat.S_ISREG(info.st_mode):
            eligible.append(
                FileEntry(
                    name=name,
                    extension=Path(name).suffix.lower(),
                    size=info.st_size,
                    mtime_ns=info.st_mtime_ns,
                )
            )
        else:
            special += 1

    return ScanResult(
        root=root,
        eligible=tuple(eligible),
        excluded_hidden=hidden,
        excluded_symlinks=symlinks,
        excluded_directories=directories,
        excluded_special=special,
    )

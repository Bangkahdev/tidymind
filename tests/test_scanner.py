from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tidymind import scanner
from tidymind.errors import ScanError

symlinks_ok = hasattr(os, "symlink") and sys.platform != "win32"


def test_mixed_entries(downloads: Path) -> None:
    result = scanner.scan(downloads)
    names = [e.name for e in result.eligible]
    assert names == ["backup.zip", "holiday photo.jpg", "invoice_oct.pdf", "notes", "setup.exe"]
    assert result.excluded_hidden == 1
    assert result.excluded_directories == 1
    assert result.discovered_total == 7
    assert result.excluded_total == 2


def test_metadata_fields(downloads: Path) -> None:
    entry = {e.name: e for e in scanner.scan(downloads).eligible}["invoice_oct.pdf"]
    assert entry.extension == ".pdf"
    assert entry.size == len(b"%PDF synthetic invoice")
    assert entry.mtime_ns == (downloads / "invoice_oct.pdf").stat().st_mtime_ns


def test_scan_is_read_only(downloads: Path) -> None:
    before = sorted(p.name for p in downloads.iterdir())
    scanner.scan(downloads)
    assert sorted(p.name for p in downloads.iterdir()) == before


@pytest.mark.skipif(not symlinks_ok, reason="symlinks need POSIX")
def test_symlink_and_fifo_excluded(downloads: Path) -> None:
    os.symlink(downloads / "backup.zip", downloads / "link.zip")
    os.mkfifo(downloads / "pipe")
    result = scanner.scan(downloads)
    assert "link.zip" not in [e.name for e in result.eligible]
    assert result.excluded_symlinks == 1
    assert result.excluded_special == 1


def test_empty_directory(tmp_path: Path) -> None:
    result = scanner.scan(tmp_path)
    assert result.eligible == ()
    assert result.discovered_total == 0


def test_unicode_and_spaces(tmp_path: Path) -> None:
    folder = tmp_path / "my folder ü"
    folder.mkdir()
    (folder / "résumé final.PDF").write_bytes(b"x")
    entry = scanner.scan(folder).eligible[0]
    assert entry.name == "résumé final.PDF"
    assert entry.extension == ".pdf"


def test_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ScanError, match="not found"):
        scanner.scan(tmp_path / "nope")


def test_file_instead_of_directory(tmp_path: Path) -> None:
    file = tmp_path / "f.txt"
    file.write_text("x")
    with pytest.raises(ScanError, match="Not a directory"):
        scanner.scan(file)


def test_resolve_root_os_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(self: Path, strict: bool = False) -> Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "resolve", boom)
    with pytest.raises(ScanError, match="Permission denied"):
        scanner.resolve_root(tmp_path)


def test_scandir_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(path: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(scanner.os, "scandir", boom)
    with pytest.raises(ScanError, match="Cannot read directory"):
        scanner.scan(tmp_path)


class _FakeEntry:
    def __init__(self, name: str, info: object | Exception) -> None:
        self.name, self._info = name, info

    def stat(self, follow_symlinks: bool = True) -> object:
        if isinstance(self._info, Exception):
            raise self._info
        return self._info


class _FakeScandir:
    def __init__(self, entries: list[_FakeEntry]) -> None:
        self.entries = entries

    def __enter__(self) -> list[_FakeEntry]:
        return self.entries

    def __exit__(self, *_: object) -> None:
        return None


def test_windows_hidden_attribute_and_stat_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hidden = SimpleNamespace(
        st_mode=stat.S_IFREG, st_file_attributes=stat.FILE_ATTRIBUTE_HIDDEN, st_size=1, st_mtime_ns=1
    )
    entries = [_FakeEntry("attr_hidden.txt", hidden), _FakeEntry("broken.txt", OSError("x"))]
    monkeypatch.setattr(scanner.os, "scandir", lambda p: _FakeScandir(entries))
    result = scanner.scan(tmp_path)
    assert result.eligible == ()
    assert result.excluded_hidden == 1
    assert result.excluded_special == 1

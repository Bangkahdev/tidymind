from __future__ import annotations

import errno
import sys
from pathlib import Path

import pytest

from tidymind import fsops
from tidymind.errors import NoClobberUnsupportedError

on_linux = sys.platform.startswith("linux")


@pytest.mark.skipif(not on_linux, reason="renameat2 is Linux-only")
def test_linux_rename_moves(tmp_path: Path) -> None:
    (tmp_path / "s").write_bytes(b"data")
    fsops.no_clobber_rename(tmp_path / "s", tmp_path / "d")
    assert (tmp_path / "d").read_bytes() == b"data" and not (tmp_path / "s").exists()


@pytest.mark.skipif(not on_linux, reason="renameat2 is Linux-only")
def test_linux_rename_never_overwrites(tmp_path: Path) -> None:
    (tmp_path / "s").write_bytes(b"new")
    (tmp_path / "d").write_bytes(b"precious")
    with pytest.raises(FileExistsError):
        fsops.no_clobber_rename(tmp_path / "s", tmp_path / "d")
    assert (tmp_path / "d").read_bytes() == b"precious"
    assert (tmp_path / "s").read_bytes() == b"new"


@pytest.mark.skipif(not on_linux, reason="renameat2 is Linux-only")
def test_linux_missing_source_is_os_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        fsops.no_clobber_rename(tmp_path / "missing", tmp_path / "d")


def test_windows_branch_uses_plain_rename(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, object]] = []
    monkeypatch.setattr(fsops.sys, "platform", "win32")
    monkeypatch.setattr(fsops.os, "rename", lambda s, d: calls.append((s, d)))
    fsops.no_clobber_rename(Path("s"), Path("d"))
    assert calls == [(Path("s"), Path("d"))]


def test_unknown_platform_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fsops.sys, "platform", "darwin")
    with pytest.raises(NoClobberUnsupportedError):
        fsops.no_clobber_rename(Path("s"), Path("d"))


class _Libc:
    def __init__(self, result: int, with_function: bool = True) -> None:
        self.result = result
        self.syscall_args: tuple[object, ...] | None = None
        if with_function:
            self.renameat2 = lambda *a: result

    def syscall(self, *args: object) -> int:
        self.syscall_args = args
        return self.result

    def __getattr__(self, name: str) -> object:
        raise AttributeError(name)


def _patch(monkeypatch: pytest.MonkeyPatch, libc: _Libc, code: int = 0, machine: str = "x86_64") -> None:
    monkeypatch.setattr(fsops.ctypes, "CDLL", lambda *a, **k: libc)
    monkeypatch.setattr(fsops.ctypes, "get_errno", lambda: code)
    monkeypatch.setattr(fsops.platform, "machine", lambda: machine)


def test_errno_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _Libc(-1), errno.EEXIST)
    with pytest.raises(FileExistsError):
        fsops._renameat2_noreplace(b"s", b"d")
    for code in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
        _patch(monkeypatch, _Libc(-1), code)
        with pytest.raises(NoClobberUnsupportedError):
            fsops._renameat2_noreplace(b"s", b"d")
    _patch(monkeypatch, _Libc(-1), errno.EACCES)
    with pytest.raises(PermissionError):
        fsops._renameat2_noreplace(b"s", b"d")
    _patch(monkeypatch, _Libc(0))
    fsops._renameat2_noreplace(b"s", b"d")  # success


def test_syscall_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    libc = _Libc(0, with_function=False)
    _patch(monkeypatch, libc)
    fsops._renameat2_noreplace(b"s", b"d")
    assert libc.syscall_args is not None and libc.syscall_args[0] == 316
    _patch(monkeypatch, _Libc(0, with_function=False), machine="aarch64")
    with pytest.raises(NoClobberUnsupportedError):
        fsops._renameat2_noreplace(b"s", b"d")

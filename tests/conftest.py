from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from fake_ollama import FakeOllama, Responder, default_responder

SRC = Path(__file__).resolve().parents[1] / "src"


def snapshot(root: Path) -> dict[str, tuple[str, int, str]]:
    """Relative path -> (kind, size, sha256) for every entry under root (no symlink following)."""
    result: dict[str, tuple[str, int, str]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[rel] = ("link", 0, os.readlink(path))
        elif path.is_dir():
            result[rel] = ("dir", 0, "")
        else:
            data = path.read_bytes()
            result[rel] = ("file", len(data), hashlib.sha256(data).hexdigest())
    return result


@pytest.fixture
def downloads(tmp_path: Path) -> Path:
    """A synthetic Downloads-like folder (no personal data)."""
    folder = tmp_path / "Downloads"
    folder.mkdir()
    (folder / "invoice_oct.pdf").write_bytes(b"%PDF synthetic invoice")
    (folder / "holiday photo.jpg").write_bytes(b"\xff\xd8 synthetic jpeg")
    (folder / "backup.zip").write_bytes(b"PK synthetic zip")
    (folder / "setup.exe").write_bytes(b"MZ synthetic installer")
    (folder / "notes").write_bytes(b"")  # zero-byte, no extension
    (folder / ".hidden.txt").write_bytes(b"hidden")
    (folder / "subdir").mkdir()
    return folder


@pytest.fixture
def fake_ollama() -> Iterator[Callable[..., FakeOllama]]:
    servers: list[FakeOllama] = []

    def start(responder: Responder = default_responder) -> FakeOllama:
        server = FakeOllama(responder).__enter__()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.__exit__()


@pytest.fixture
def run_cli() -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(*args: str, stdin: str = "", cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "tidymind", *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=cwd,
            timeout=60,
            check=False,
        )

    return run


@pytest.fixture(autouse=True)
def _src_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(SRC))

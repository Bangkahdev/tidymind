"""White-box tests for CLI control flow (in-process, injected I/O)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_validator import make_item, plan_for
from tidymind import cli
from tidymind.errors import EXIT_CANCELLED, EXIT_INCOMPLETE, EXIT_INTERNAL, EXIT_OK
from tidymind.planner import write_plan


def call(*argv: str, answer: str = "n") -> tuple[int, str]:
    lines: list[str] = []
    code = cli.main(list(argv), out=lines.append, ask=lambda _: answer)
    return code, "\n".join(lines)


def saved_plan(tmp_path: Path, *items: Any) -> tuple[Path, Path]:
    root = (tmp_path / "root").resolve()
    root.mkdir()
    for name in ("a.pdf", "b.pdf"):
        (root / name).write_bytes(name.encode())
    plan_path = tmp_path / "plan.json"
    write_plan(plan_for(root, *(i(root) for i in items)), plan_path)
    return root, plan_path


def test_apply_all_unsafe_returns_incomplete(tmp_path: Path) -> None:
    root, plan = saved_plan(tmp_path, lambda r: make_item(r, "ghost.pdf"))
    code, text = call("apply", str(plan), answer="y")
    assert code == EXIT_INCOMPLETE and "No safe operations" in text


def test_apply_empty_plan_is_ok(tmp_path: Path) -> None:
    _, plan = saved_plan(tmp_path)
    code, text = call("apply", str(plan))
    assert code == EXIT_OK and "No safe operations" in text


def test_apply_declined_and_approved(tmp_path: Path) -> None:
    root, plan = saved_plan(tmp_path, lambda r: make_item(r, "a.pdf"))
    assert call("apply", str(plan), answer="n")[0] == EXIT_CANCELLED
    assert (root / "a.pdf").exists()
    code, text = call("apply", str(plan), answer="yes")
    assert code == EXIT_OK and "succeeded=1" in text
    assert (root / "Documents" / "a.pdf").exists()


def test_apply_partial_failure_exit_code(tmp_path: Path) -> None:
    root, plan = saved_plan(tmp_path, lambda r: make_item(r, "a.pdf"), lambda r: make_item(r, "ghost.pdf"))
    code, text = call("apply", str(plan), answer="y")
    assert code == EXIT_INCOMPLETE and "succeeded=1 skipped=1" in text


def test_expected_errors_map_to_input_exit_code(tmp_path: Path) -> None:
    assert call("scan", str(tmp_path / "missing"))[0] == 3


def test_unexpected_exception_maps_to_internal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(_: object) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "scan", boom)
    assert call("scan", str(tmp_path))[0] == EXIT_INTERNAL
    assert call("--debug", "scan", str(tmp_path))[0] == EXIT_INTERNAL


def test_debug_flag_prints_traceback_for_expected_errors(tmp_path: Path) -> None:
    assert call("--debug", "scan", str(tmp_path / "missing"))[0] == 3


def test_plan_end_to_end_in_process(
    fake_ollama: Any, downloads: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fake_ollama()
    monkeypatch.setenv("TIDYMIND_OLLAMA_URL", server.url)
    out = tmp_path / "p.json"
    code, text = call("plan", str(downloads), "--output", str(out))
    assert code == EXIT_OK and out.exists() and "Plan written" in text
    code, text = call("plan", str(downloads), "--dry-run")
    assert code == EXIT_OK and "Dry run" not in text  # no --output given: nothing to say about it
    code, text = call("plan", str(downloads), "--output", str(tmp_path / "q.json"), "--dry-run")
    assert "NOT written" in text and not (tmp_path / "q.json").exists()

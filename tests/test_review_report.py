from __future__ import annotations

from pathlib import Path

import pytest

from test_validator import make_item, plan_for
from tidymind import reporter, reviewer
from tidymind.executor import ItemOutcome, Status
from tidymind.models import FileEntry, ScanResult
from tidymind.textutil import safe_text
from tidymind.validator import validate_plan


@pytest.mark.parametrize("answer", ["y", "Y", "yes", " YES ", "yEs\n"])
def test_explicit_yes_approves(answer: str) -> None:
    assert reviewer.confirm(1, Path("/r"), lambda _: answer) is True


@pytest.mark.parametrize("answer", ["", " ", "n", "no", "maybe", "yy", "ok", "yes please", "1"])
def test_everything_else_is_not_approval(answer: str) -> None:
    assert reviewer.confirm(1, Path("/r"), lambda _: answer) is False


def test_eof_and_interrupt_are_not_approval() -> None:
    def eof(_: str) -> str:
        raise EOFError

    def interrupt(_: str) -> str:
        raise KeyboardInterrupt

    assert reviewer.confirm(1, Path("/r"), eof) is False
    assert reviewer.confirm(1, Path("/r"), interrupt) is False


def test_prompt_states_count_and_root() -> None:
    seen: list[str] = []
    reviewer.confirm(3, Path("/some/root"), lambda p: seen.append(p) or "n")
    assert "3 file(s)" in seen[0] and str(Path("/some/root")) in seen[0]


def test_safe_text_escapes_terminal_tricks() -> None:
    assert safe_text("a\x1b[31mred\x1b[0m") == "a\\x1b[31mred\\x1b[0m"
    assert safe_text("x\u202ey") == "x\\u202ey"
    assert safe_text("\x85\x7f\n") == "\\x85\\x7f\\x0a"
    assert safe_text("résumé ü 日本") == "résumé ü 日本"


def test_preview_lists_ok_and_skipped(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    (root / "a.pdf").write_bytes(b"x")
    ok = make_item(root, "a.pdf", reason="looks like a doc")
    bad = make_item(root, "gone.pdf")
    text = reviewer.render_preview(validate_plan(plan_for(root, ok, bad)))
    assert "[OK]" in text and "Documents/a.pdf" in text and "looks like a doc" in text
    assert "[SKIP]" in text and "source file is missing" in text
    assert "1 operation(s) would run; 1 would be skipped." in text


def test_preview_escapes_hostile_names(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    item = make_item(root, "x.pdf", source_name="\x1b[2Jevil.pdf")
    text = reviewer.render_preview(validate_plan(plan_for(root, item)))
    assert "\x1b" not in text


def test_scan_report() -> None:
    scan = ScanResult(Path("/r"), (FileEntry("a.pdf", ".pdf", 5, 1),), 1, 0, 2, 0)
    text = reporter.render_scan(scan)
    assert "Discovered: 4  Eligible: 1  Excluded: 3" in text and "a.pdf (5 bytes)" in text


def test_results_totals_match_outcomes() -> None:
    outcomes = (
        ItemOutcome("a", "Documents/a", Status.SUCCEEDED, "moved"),
        ItemOutcome("b", None, Status.SKIPPED, "stale"),
        ItemOutcome("c", "Other/c", Status.FAILED, "move failed"),
    )
    text = reporter.render_results(outcomes)
    assert "succeeded=1 skipped=1 failed=1" in text and "no batch rollback" in text
    assert "[FAILED] c -> Other/c: move failed" in text
    clean = reporter.render_results(outcomes[:1])
    assert "rollback" not in clean

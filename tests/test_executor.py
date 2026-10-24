from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from test_validator import make_item, plan_for

from tidymind import executor
from tidymind.errors import NoClobberUnsupportedError
from tidymind.executor import Status, execute
from tidymind.validator import validate_plan

symlinks_ok = hasattr(os, "symlink") and sys.platform != "win32"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = (tmp_path / "root").resolve()
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"alpha")
    (folder / "b.png").write_bytes(b"beta")
    return folder


def run(root: Path, *items: object, mover: object = None) -> tuple[executor.ItemOutcome, ...]:
    report = validate_plan(plan_for(root, *items))  # type: ignore[arg-type]
    return execute(report) if mover is None else execute(report, mover)  # type: ignore[arg-type]


def test_moves_and_renames_preserving_content(root: Path) -> None:
    outcomes = run(
        root,
        make_item(root, "a.pdf", target_name="invoice.pdf"),
        make_item(root, "b.png", category="Images"),
    )
    assert [o.status for o in outcomes] == [Status.SUCCEEDED, Status.SUCCEEDED]
    assert (root / "Documents" / "invoice.pdf").read_bytes() == b"alpha"
    assert (root / "Images" / "b.png").read_bytes() == b"beta"
    assert not (root / "a.pdf").exists()
    assert outcomes[0].target == "Documents/invoice.pdf"


def test_unsafe_items_never_reach_the_mover(root: Path) -> None:
    calls: list[object] = []
    outcomes = run(
        root, make_item(root, "a.pdf", target_name="../evil.pdf"), mover=lambda s, d: calls.append(d)
    )
    assert calls == []
    assert outcomes[0].status is Status.SKIPPED and outcomes[0].target is None
    assert not (root / "Documents").exists()  # no folder created for skipped items


def test_destination_appearing_after_validation_is_not_overwritten(root: Path) -> None:
    report = validate_plan(plan_for(root, make_item(root, "a.pdf")))
    (root / "Documents").mkdir()
    (root / "Documents" / "a.pdf").write_bytes(b"precious")
    (outcome,) = execute(report)
    assert outcome.status is Status.SKIPPED
    assert (root / "Documents" / "a.pdf").read_bytes() == b"precious"
    assert (root / "a.pdf").read_bytes() == b"alpha"


def test_source_changed_after_validation_is_skipped(root: Path) -> None:
    report = validate_plan(plan_for(root, make_item(root, "a.pdf")))
    (root / "a.pdf").write_bytes(b"changed content!")
    (outcome,) = execute(report)
    assert outcome.status is Status.SKIPPED and "stale" in outcome.detail
    assert not (root / "Documents").exists()


def test_source_removed_after_validation_is_skipped(root: Path) -> None:
    report = validate_plan(plan_for(root, make_item(root, "a.pdf")))
    (root / "a.pdf").unlink()
    assert execute(report)[0].detail == "source file is missing"


def test_mover_file_exists_race(root: Path) -> None:
    def racing(src: Path, dst: Path) -> None:
        raise FileExistsError(17, "exists")

    (outcome,) = run(root, make_item(root, "a.pdf"), mover=racing)
    assert outcome.status is Status.SKIPPED and "not overwritten" in outcome.detail


def test_no_clobber_unsupported_fails_closed(root: Path) -> None:
    def unsupported(src: Path, dst: Path) -> None:
        raise NoClobberUnsupportedError("nope")

    (outcome,) = run(root, make_item(root, "a.pdf"), mover=unsupported)
    assert outcome.status is Status.FAILED and "refused" in outcome.detail
    assert (root / "a.pdf").exists()


def test_mover_os_error_is_failed_not_success(root: Path) -> None:
    def broken(src: Path, dst: Path) -> None:
        raise OSError(28, "No space left on device")

    (outcome,) = run(root, make_item(root, "a.pdf"), mover=broken)
    assert outcome.status is Status.FAILED and "No space left" in outcome.detail


def test_one_failure_does_not_stop_other_items(root: Path) -> None:
    def flaky(src: Path, dst: Path) -> None:
        if src.name == "a.pdf":
            raise OSError(5, "I/O error")
        os.rename(src, dst)

    outcomes = run(
        root, make_item(root, "a.pdf"), make_item(root, "b.png", category="Images"), mover=flaky
    )
    assert [o.status for o in outcomes] == [Status.FAILED, Status.SUCCEEDED]


def test_mkdir_failure(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(path: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(executor.os, "mkdir", deny)
    (outcome,) = run(root, make_item(root, "a.pdf"))
    assert outcome.status is Status.FAILED and "category folder" in outcome.detail


def test_category_folder_created_concurrently_is_fine(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = os.mkdir

    def create_then_raise(path: object) -> None:
        real(path)
        raise FileExistsError(17, "exists")

    monkeypatch.setattr(executor.os, "mkdir", create_then_raise)
    (outcome,) = run(root, make_item(root, "a.pdf"))
    assert outcome.status is Status.SUCCEEDED


@pytest.mark.skipif(not symlinks_ok, reason="POSIX symlinks")
def test_category_folder_swapped_for_symlink_is_skipped(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()

    def swap(path: object) -> None:
        os.symlink(outside, path)  # type: ignore[arg-type]
        raise FileExistsError(17, "exists")

    monkeypatch.setattr(executor.os, "mkdir", swap)
    (outcome,) = run(root, make_item(root, "a.pdf"))
    assert outcome.status is Status.SKIPPED and "symbolic link" in outcome.detail
    assert list(outside.iterdir()) == []
    assert (root / "a.pdf").exists()


def test_empty_report(root: Path) -> None:
    assert execute(validate_plan(plan_for(root))) == ()

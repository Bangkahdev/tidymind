from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tidymind import validator
from tidymind.errors import RootMismatchError
from tidymind.models import Plan, PlanItem

symlinks_ok = hasattr(os, "symlink") and sys.platform != "win32"


def make_item(root: Path, name: str = "a.pdf", **over: object) -> PlanItem:
    path = root / name
    info = path.stat() if path.exists() else None
    fields: dict[str, object] = {
        "source_name": name,
        "source_size": info.st_size if info else 0,
        "source_mtime_ns": info.st_mtime_ns if info else 0,
        "category": "Documents",
        "target_name": name,
        "reason": "",
    }
    fields.update(over)
    return PlanItem(**fields)  # type: ignore[arg-type]


def plan_for(root: Path, *items: PlanItem) -> Plan:
    return Plan(1, str(root.resolve()), tuple(items))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = (tmp_path / "root").resolve()
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"alpha")
    (folder / "b.pdf").write_bytes(b"beta")
    return folder


def reasons(root: Path, *items: PlanItem) -> list[str | None]:
    return [r.reason for r in validator.validate_plan(plan_for(root, *items)).results]


def test_safe_item_gets_derived_destination(root: Path) -> None:
    report = validator.validate_plan(plan_for(root, make_item(root, target_name="Alpha.pdf")))
    result = report.results[0]
    assert result.ok and report.operations == (result,) and report.unsafe == ()
    assert result.destination == root / "Documents" / "Alpha.pdf"


@pytest.mark.parametrize(
    "target",
    [
        "", "   ", ".", "..", "../x.pdf", "a/b.pdf", "a\\b.pdf", "C:evil.pdf", "x\x00.pdf",
        "x\n.pdf", "x\x7f.pdf", "a<b.pdf", "a|b.pdf", 'a"b.pdf', "a?b.pdf", "a*b.pdf",
        "name.pdf ", " name.pdf", "name.pdf.", ".hidden.pdf", "CON.pdf", "nul.pdf",
        "com1.pdf", "LPT9.pdf", "aux .pdf", "a" * 252 + ".pdf", "other.txt", "noext",
    ],
)  # fmt: skip
def test_bad_target_names_are_unsafe(root: Path, target: str) -> None:
    (reason,) = reasons(root, make_item(root, target_name=target))
    assert reason is not None
    result = validator.validate_plan(plan_for(root, make_item(root, target_name=target))).results[0]
    assert result.destination is None  # never derived from an unsafe name


def test_extension_case_is_not_a_change(root: Path) -> None:
    assert reasons(root, make_item(root, target_name="A.PDF")) == [None]


def test_name_length_boundary(root: Path) -> None:
    ok = "a" * 251 + ".pdf"  # exactly 255
    assert len(ok) == 255
    assert reasons(root, make_item(root, target_name=ok)) == [None]


@pytest.mark.parametrize(
    "source", ["", " ", ".", "..", "../a.pdf", "x/a.pdf", "x\\a.pdf", "C:a.pdf", "a\x01.pdf", "a" * 256]
)
def test_bad_source_names_are_unsafe(root: Path, source: str) -> None:
    item = make_item(root, "a.pdf", source_name=source)
    (reason,) = reasons(root, item)
    assert reason and "source" in reason


def test_colon_in_source_allowed_off_windows_only(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert validator.source_name_problem("10:30 notes.pdf") is None
    monkeypatch.setattr(validator, "_is_windows", lambda: True)
    assert validator.source_name_problem("10:30 notes.pdf") is not None


def test_unknown_category_is_unsafe(root: Path) -> None:
    for category in ["Videos", "../Documents", "documents", ""]:
        (reason,) = reasons(root, make_item(root, category=category))
        assert reason == "category is not in the allowlist"


def test_missing_source(root: Path) -> None:
    (reason,) = reasons(root, make_item(root, "ghost.pdf"))
    assert reason == "source file is missing"


def test_stale_size_and_mtime(root: Path) -> None:
    item = make_item(root)
    assert reasons(root, validator_replace(item, source_size=item.source_size + 1))[0] == STALE
    assert reasons(root, validator_replace(item, source_mtime_ns=item.source_mtime_ns + 1))[0] == STALE


STALE = "source changed since the plan was created (stale plan)"


def validator_replace(item: PlanItem, **over: object) -> PlanItem:
    from dataclasses import replace

    return replace(item, **over)  # type: ignore[arg-type]


@pytest.mark.skipif(not symlinks_ok, reason="POSIX symlinks")
def test_symlink_source_is_unsafe(root: Path) -> None:
    os.symlink(root / "a.pdf", root / "link.pdf")
    item = PlanItem("link.pdf", 5, 0, "Documents", "link.pdf", "")
    assert reasons(root, item) == ["source is a symbolic link"]


def test_directory_source_is_unsafe(root: Path) -> None:
    (root / "d.pdf").mkdir()
    item = PlanItem("d.pdf", 0, 0, "Documents", "d.pdf", "")
    assert reasons(root, item) == ["source is not a regular file"]


@pytest.mark.skipif(not symlinks_ok, reason="POSIX symlinks")
def test_category_folder_symlink_is_unsafe(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / "Documents")
    assert reasons(root, make_item(root)) == ["category folder is a symbolic link"]
    assert list(outside.iterdir()) == []


def test_file_blocking_category_folder(root: Path) -> None:
    (root / "Documents").write_bytes(b"i am a file")
    assert reasons(root, make_item(root)) == ["a file blocks the category folder name"]


def test_existing_destination_is_a_conflict(root: Path) -> None:
    (root / "Documents").mkdir()
    (root / "Documents" / "a.pdf").write_bytes(b"precious")
    (reason,) = reasons(root, make_item(root))
    assert reason == "destination already exists (never overwritten)"
    assert (root / "Documents" / "a.pdf").read_bytes() == b"precious"


def test_duplicate_destinations_and_sources(root: Path) -> None:
    one = make_item(root, "a.pdf", target_name="same.pdf")
    two = make_item(root, "b.pdf", target_name="SAME.pdf")  # case-insensitive filesystems
    assert reasons(root, one, two) == ["another item in the plan has the same destination"] * 2
    assert reasons(root, one, one) == ["source appears more than once in the plan"] * 2


def test_different_categories_do_not_collide(root: Path) -> None:
    one = make_item(root, "a.pdf", target_name="same.pdf")
    two = make_item(root, "b.pdf", target_name="same.pdf", category="Other")
    assert reasons(root, one, two) == [None, None]


def test_check_state_blocks_root_escape(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validator, "_contained", lambda *_: False)
    assert validator.check_state(root, make_item(root)) == "path escapes the selected root"


def test_inspection_errors(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.lstat

    def fail_source(path: object, *a: object, **k: object) -> os.stat_result:
        if str(path).endswith("a.pdf"):
            raise PermissionError(13, "denied")
        return real(path)

    monkeypatch.setattr(validator.os, "lstat", fail_source)
    assert validator.check_state(root, make_item(root)) == "source file cannot be inspected"

    def fail_category(path: object, *a: object, **k: object) -> os.stat_result:
        if str(path).endswith("Documents"):
            raise PermissionError(13, "denied")
        return real(path)

    monkeypatch.setattr(validator.os, "lstat", fail_category)
    assert validator.check_state(root, make_item(root)) == "category folder cannot be inspected"


def test_root_checks(root: Path, tmp_path: Path) -> None:
    with pytest.raises(RootMismatchError, match="absolute"):
        validator.validate_plan(Plan(1, "relative/dir", ()))
    with pytest.raises(RootMismatchError, match="does not exist"):
        validator.validate_plan(Plan(1, str(tmp_path / "gone"), ()))
    with pytest.raises(RootMismatchError, match="not a directory"):
        validator.validate_plan(Plan(1, str(root / "a.pdf"), ()))
    with pytest.raises(RootMismatchError, match="canonical"):
        validator.validate_plan(Plan(1, str(root / ".." / "root"), ()))
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(RootMismatchError, match="does not match"):
        validator.validate_plan(plan_for(root), other.resolve())
    assert validator.validate_plan(plan_for(root), root).root == root

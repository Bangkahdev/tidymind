from __future__ import annotations

import json
from pathlib import Path

import pytest

from tidymind import planner
from tidymind.errors import InputError, PlanFormatError
from tidymind.models import FileEntry, Plan, PlanItem, ScanResult, Suggestion


def _plan() -> Plan:
    return Plan(
        1,
        "/r",
        (
            PlanItem("b.pdf", 2, 20, "Documents", "b.pdf", "r"),
            PlanItem("a.png", 1, 10, "Images", "a.png", ""),
        ),
    )


def _doc(**over: object) -> str:
    base: dict[str, object] = {
        "schema_version": 1,
        "root": "/r",
        "items": [
            {
                "source_name": "a.pdf",
                "source_size": 1,
                "source_mtime_ns": 2,
                "category": "Documents",
                "target_name": "a.pdf",
                "reason": "",
            }
        ],
    }
    base.update(over)
    return json.dumps(base)


def test_build_plan_and_roundtrip() -> None:
    scan = ScanResult(Path("/r"), (FileEntry("a.pdf", ".pdf", 1, 2),), 0, 0, 0, 0)
    plan = planner.build_plan(scan, [Suggestion("Documents", "a.pdf", "why")])
    assert plan.items[0].source_mtime_ns == 2
    assert planner.parse_plan(planner.dump_plan(plan)) == plan


def test_build_plan_requires_one_suggestion_per_file() -> None:
    scan = ScanResult(Path("/r"), (FileEntry("a.pdf", ".pdf", 1, 2),), 0, 0, 0, 0)
    with pytest.raises(ValueError):
        planner.build_plan(scan, [])


def test_dump_is_deterministic_and_sorted() -> None:
    first = planner.dump_plan(_plan())
    assert first == planner.dump_plan(_plan())
    names = [i["source_name"] for i in json.loads(first)["items"]]
    assert names == ["a.png", "b.pdf"]
    assert first.endswith("\n")


def test_dump_has_no_destination_path_field() -> None:
    item = json.loads(planner.dump_plan(_plan()))["items"][0]
    assert set(item) == {
        "source_name", "source_size", "source_mtime_ns", "category", "target_name", "reason",
    }  # fmt: skip


def test_write_plan_never_overwrites(tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    planner.write_plan(_plan(), out)
    original = out.read_bytes()
    with pytest.raises(InputError, match="already exists"):
        planner.write_plan(_plan(), out)
    assert out.read_bytes() == original


def test_write_plan_os_error(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="Cannot write"):
        planner.write_plan(_plan(), tmp_path / "missing_dir" / "plan.json")


BAD_TEXTS = [
    "not json",
    "[]",
    '{"schema_version": 1}',
    _doc(extra=1),
    _doc(schema_version=2),
    _doc(schema_version="1"),
    _doc(schema_version=True),
    _doc(root=""),
    _doc(root=5),
    _doc(items={}),
    _doc(items=[1]),
    _doc(items=[{"source_name": "a"}]),
    _doc().replace('"source_size": 1', '"source_size": "1"'),
    _doc().replace('"source_size": 1', '"source_size": -1'),
    _doc().replace('"source_size": 1', '"source_size": true'),
    _doc().replace('"category": "Documents"', '"category": 7'),
    _doc().replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
    _doc().replace('"source_size": 1', '"source_size": NaN'),
]


@pytest.mark.parametrize("text", BAD_TEXTS)
def test_parse_rejects_malformed(text: str) -> None:
    with pytest.raises(PlanFormatError):
        planner.parse_plan(text)


def test_parse_rejects_too_many_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(planner, "MAX_PLAN_ITEMS", 0)
    with pytest.raises(PlanFormatError, match="too many"):
        planner.parse_plan(_doc())


def test_load_plan_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(InputError, match="not found"):
        planner.load_plan(tmp_path / "none.json")
    with pytest.raises(InputError, match="Cannot read"):
        planner.load_plan(tmp_path)  # a directory
    bad = tmp_path / "bin.json"
    bad.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(PlanFormatError, match="UTF-8"):
        planner.load_plan(bad)
    monkeypatch.setattr(planner, "MAX_PLAN_BYTES", 10)
    big = tmp_path / "big.json"
    big.write_text(_doc())
    with pytest.raises(PlanFormatError, match="too large"):
        planner.load_plan(big)


def test_load_plan_ok(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(_doc(), encoding="utf-8")
    assert planner.load_plan(path).items[0].source_name == "a.pdf"

"""Mocked integration: full scan -> plan -> validate -> apply through the fake Ollama boundary.

A pass here proves the request/response boundary and the workflow only. It is NOT evidence that
a real model works (see docs/ACCEPTANCE.md for the separate real-model record).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import snapshot
from tidymind.executor import Status, execute
from tidymind.model_client import OllamaClient
from tidymind.planner import build_plan, dump_plan, load_plan
from tidymind.scanner import scan
from tidymind.validator import validate_plan

pytestmark = [pytest.mark.integration]


def test_full_workflow(fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    server = fake_ollama()
    scanned = scan(downloads)
    plan = build_plan(scanned, OllamaClient(endpoint=server.url).suggest(scanned.eligible))
    saved = tmp_path / "plan.json"
    saved.write_text(dump_plan(plan), encoding="utf-8")

    before = snapshot(downloads)
    report = validate_plan(load_plan(saved))  # a saved plan is re-validated, not trusted
    assert snapshot(downloads) == before and len(report.operations) == 5

    outcomes = execute(report)
    assert all(o.status is Status.SUCCEEDED for o in outcomes)
    after = snapshot(downloads)
    assert after["Documents/invoice_oct.pdf"] == before["invoice_oct.pdf"]
    assert sorted(k for k in after if "/" not in k) == [
        ".hidden.txt", "Archives", "Documents", "Images", "Installers", "Other", "subdir",
    ]  # fmt: skip


def test_many_files_use_multiple_batches(fake_ollama: Any, tmp_path: Path) -> None:
    server = fake_ollama()
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(45):
        (folder / f"file{i:02}.txt").write_bytes(b"x" * i)
    scanned = scan(folder)
    plan = build_plan(scanned, OllamaClient(endpoint=server.url, batch_size=20).suggest(scanned.eligible))
    assert len(plan.items) == 45 and len(server.requests) == 3

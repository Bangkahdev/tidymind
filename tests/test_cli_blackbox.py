"""Black-box tests: only the public CLI is used (subprocess), plus filesystem snapshots."""

from __future__ import annotations

import json
import os
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest
from conftest import snapshot
from fake_ollama import chat_reply, default_responder

Run = Callable[..., CompletedProcess[str]]
symlinks_ok = hasattr(os, "symlink") and sys.platform != "win32"
pytestmark = [pytest.mark.blackbox]


def make_plan(run: Run, server: Any, folder: Path, out: Path) -> None:
    result = run("plan", str(folder), "--endpoint", server.url, "--output", str(out))
    assert result.returncode == 0, result.stderr


def rewrite_plan(path: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")


# --- CLI contract -------------------------------------------------------------------------


def test_help_and_version(run_cli: Run) -> None:
    helped = run_cli("--help")
    assert helped.returncode == 0
    for word in ("scan", "plan", "apply", "exit codes", "examples"):
        assert word in helped.stdout
    version = run_cli("--version")
    assert version.returncode == 0 and version.stdout.startswith("tidymind ")


@pytest.mark.parametrize("flag", ["--yes", "-y", "--force", "--no-confirm"])
def test_no_flag_bypasses_approval(run_cli: Run, tmp_path: Path, flag: str) -> None:
    result = run_cli("apply", "plan.json", flag)
    assert result.returncode == 2 and "unrecognized arguments" in result.stderr


def test_no_command_is_a_usage_error(run_cli: Run) -> None:
    assert run_cli().returncode == 2


# --- scan ---------------------------------------------------------------------------------


def test_scan_lists_eligible_and_changes_nothing(run_cli: Run, downloads: Path) -> None:
    before = snapshot(downloads)
    result = run_cli("scan", str(downloads))
    assert result.returncode == 0
    assert "Eligible: 5" in result.stdout and "invoice_oct.pdf" in result.stdout
    assert ".hidden.txt" not in result.stdout
    assert snapshot(downloads) == before


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_scan_bad_directories(run_cli: Run, tmp_path: Path, kind: str) -> None:
    target = tmp_path / "nope"
    if kind == "file":
        target.write_text("x")
    result = run_cli("scan", str(target))
    assert result.returncode == 3 and result.stderr.startswith("Error:")
    assert "Traceback" not in result.stderr


def test_scan_empty_folder_and_unicode_path(run_cli: Run, tmp_path: Path) -> None:
    folder = tmp_path / "dossier téléchargements"
    folder.mkdir()
    result = run_cli("scan", str(folder))
    assert result.returncode == 0 and "Eligible: 0" in result.stdout


# --- plan ---------------------------------------------------------------------------------


def test_plan_dry_run_changes_nothing(run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    server = fake_ollama()
    out = tmp_path / "plan.json"
    before = snapshot(downloads)
    result = run_cli("plan", str(downloads), "--endpoint", server.url, "--output", str(out), "--dry-run")
    assert result.returncode == 0 and "Dry run" in result.stdout and "[OK]" in result.stdout
    assert snapshot(downloads) == before and not out.exists()


def test_plan_writes_file_and_never_overwrites(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path
) -> None:
    server = fake_ollama()
    out = tmp_path / "plan.json"
    make_plan(run_cli, server, downloads, out)
    saved = out.read_bytes()
    again = run_cli("plan", str(downloads), "--endpoint", server.url, "--output", str(out))
    assert again.returncode == 3 and "already exists" in again.stderr
    assert out.read_bytes() == saved
    plan = json.loads(saved)
    assert plan["schema_version"] == 1 and len(plan["items"]) == 5
    assert all("destination" not in item for item in plan["items"])


def test_plan_without_output_saves_nothing(run_cli: Run, fake_ollama: Any, downloads: Path) -> None:
    server = fake_ollama()
    before = snapshot(downloads)
    result = run_cli("plan", str(downloads), "--endpoint", server.url)
    assert result.returncode == 0 and "no plan was saved" in result.stdout
    assert snapshot(downloads) == before


def test_plan_on_empty_folder_needs_no_model(run_cli: Run, tmp_path: Path) -> None:
    result = run_cli("plan", str(tmp_path), "--endpoint", "http://127.0.0.1:9")
    assert result.returncode == 0 and "Nothing to organize" in result.stdout


def test_plan_sends_only_minimal_metadata(run_cli: Run, fake_ollama: Any, downloads: Path) -> None:
    server = fake_ollama()
    secret = downloads / "secret.txt"
    secret.write_bytes(b"TOP-SECRET-CONTENT-12345")
    run_cli("plan", str(downloads), "--endpoint", server.url, "--dry-run")
    sent = json.dumps(server.requests)
    assert "TOP-SECRET-CONTENT" not in sent and str(downloads) not in sent
    assert "mtime" not in sent


@pytest.mark.parametrize("url", ["http://example.com", "http://192.168.0.10:11434", "http://10.1.1.1"])
def test_non_loopback_endpoint_refused(run_cli: Run, downloads: Path, url: str) -> None:
    before = snapshot(downloads)
    result = run_cli("plan", str(downloads), "--endpoint", url)
    assert result.returncode == 2 and "loopback" in result.stderr
    assert snapshot(downloads) == before


def test_endpoint_from_environment_is_also_validated(
    run_cli: Run, downloads: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIDYMIND_OLLAMA_URL", "http://example.com")
    assert run_cli("plan", str(downloads)).returncode == 2


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_model_unavailable_is_safe(run_cli: Run, downloads: Path) -> None:
    before = snapshot(downloads)
    result = run_cli("plan", str(downloads), "--endpoint", f"http://127.0.0.1:{_closed_port()}")
    assert result.returncode == 4 and "Cannot reach Ollama" in result.stderr
    assert snapshot(downloads) == before


@pytest.mark.parametrize(
    "reply",
    [chat_reply("not json"), chat_reply(""), chat_reply('{"suggestions": []}'), {"message": 5}],
)
def test_malformed_model_output_fails_closed(
    run_cli: Run, fake_ollama: Any, downloads: Path, reply: Any
) -> None:
    server = fake_ollama(lambda r: (200, reply))
    before = snapshot(downloads)
    result = run_cli("plan", str(downloads), "--endpoint", server.url, "--output", str(downloads.parent / "p.json"))
    assert result.returncode == 4 and "attempts" in result.stderr
    assert len(server.requests) == 3  # bounded retry
    assert snapshot(downloads) == before and not (downloads.parent / "p.json").exists()


def test_model_missing_reports_pull_hint(run_cli: Run, fake_ollama: Any, downloads: Path) -> None:
    server = fake_ollama(lambda r: (404, {"error": "model not found"}))
    result = run_cli("plan", str(downloads), "--endpoint", server.url)
    assert result.returncode == 4 and "ollama pull" in result.stderr


def test_unsafe_model_names_are_flagged_not_rewritten(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path
) -> None:
    def evil(request: dict[str, Any]) -> tuple[int, Any]:
        body = default_responder(request)[1]
        inner = json.loads(body["message"]["content"])
        inner["suggestions"][0]["target_name"] = "../../escape.pdf"
        return 200, chat_reply(json.dumps(inner))

    server = fake_ollama(evil)
    result = run_cli("plan", str(downloads), "--endpoint", server.url, "--dry-run")
    assert result.returncode == 0 and "[SKIP]" in result.stdout and "path separator" in result.stdout


# --- apply: approval ----------------------------------------------------------------------


@pytest.mark.parametrize("stdin", ["n\n", "no\n", "\n", "", "maybe\n", "yy\n", "   \n"])
def test_apply_without_explicit_approval_changes_nothing(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path, stdin: str
) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    before = snapshot(downloads)
    result = run_cli("apply", str(out), stdin=stdin)
    assert result.returncode == 6 and "Not approved" in result.stdout
    assert snapshot(downloads) == before


def test_apply_dry_run_changes_nothing_and_asks_nothing(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path
) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    before = snapshot(downloads)
    result = run_cli("apply", str(out), "--dry-run")
    assert result.returncode == 0 and "Dry run" in result.stdout
    assert snapshot(downloads) == before


def test_approved_apply_moves_files_and_preserves_hashes(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path
) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    before = snapshot(downloads)
    result = run_cli("apply", str(out), stdin="y\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "succeeded=5 skipped=0 failed=0" in result.stdout
    after = snapshot(downloads)
    assert after["Documents/invoice_oct.pdf"] == before["invoice_oct.pdf"]
    assert after["Images/holiday photo.jpg"] == before["holiday photo.jpg"]
    assert after["Archives/backup.zip"] == before["backup.zip"]
    assert after["Installers/setup.exe"] == before["setup.exe"]
    assert after["Other/notes"] == before["notes"]
    assert after[".hidden.txt"] == before[".hidden.txt"] and "subdir" in after
    assert not (downloads / "invoice_oct.pdf").exists()


def test_applying_twice_is_safe(run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    assert run_cli("apply", str(out), stdin="y\n").returncode == 0
    after_first = snapshot(downloads)
    second = run_cli("apply", str(out), stdin="y\n")
    assert second.returncode == 7 and "No safe operations" in second.stdout
    assert snapshot(downloads) == after_first


# --- apply: stale plans and conflicts -----------------------------------------------------


def test_destination_conflict_after_plan_is_never_overwritten(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path
) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    (downloads / "Documents").mkdir()
    victim = downloads / "Documents" / "invoice_oct.pdf"
    victim.write_bytes(b"precious existing data")
    result = run_cli("apply", str(out), stdin="y\n")
    assert result.returncode == 7 and "destination already exists" in result.stdout
    assert victim.read_bytes() == b"precious existing data"
    assert (downloads / "invoice_oct.pdf").read_bytes() == b"%PDF synthetic invoice"
    assert (downloads / "Images" / "holiday photo.jpg").exists()  # others still processed


def test_changed_source_is_rejected(run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    (downloads / "backup.zip").write_bytes(b"different, longer content now")
    result = run_cli("apply", str(out), stdin="y\n")
    assert result.returncode == 7 and "stale plan" in result.stdout
    assert (downloads / "backup.zip").read_bytes() == b"different, longer content now"
    assert not (downloads / "Archives").exists()


def test_removed_source_is_rejected(run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    (downloads / "setup.exe").unlink()
    result = run_cli("apply", str(out), stdin="y\n")
    assert result.returncode == 7 and "source file is missing" in result.stdout


# --- apply: adversarial plan files --------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    ["../escape.pdf", "../../escape.pdf", "/tmp/escape.pdf", "C:\\escape.pdf", "C:escape.pdf",
     "sub/escape.pdf", "sub\\escape.pdf", "evil\x00.pdf", "evil\n.pdf", "CON.pdf", "x.exe", ""],
)  # fmt: skip
def test_hostile_targets_are_skipped_and_nothing_escapes(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path, target: str
) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    rewrite_plan(out, lambda d: d["items"][2].__setitem__("target_name", target))
    outside_before = snapshot(tmp_path)
    result = run_cli("apply", str(out), stdin="y\n")
    assert "[SKIP]" in result.stdout
    after = snapshot(tmp_path)
    new_outside = {k for k in after if not k.startswith("Downloads/") and k not in outside_before}
    assert new_outside == set()  # nothing appeared outside the chosen root
    assert not any(p.name.startswith("escape") for p in tmp_path.rglob("*"))


def test_unknown_category_never_executes(run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    rewrite_plan(out, lambda d: d["items"][0].__setitem__("category", "../Evil"))
    run_cli("apply", str(out), stdin="y\n")
    assert not (downloads.parent / "Evil").exists() and not (downloads / "Evil").exists()
    assert (downloads / "backup.zip").exists()  # the unsafe item stayed put


def test_duplicate_targets_are_skipped(run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    (downloads / "second.pdf").write_bytes(b"another synthetic pdf")
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)

    def clash(d: dict[str, Any]) -> None:
        for item in d["items"]:
            if item["source_name"].endswith(".pdf"):
                item["category"], item["target_name"] = "Other", "same.pdf"

    rewrite_plan(out, clash)
    result = run_cli("apply", str(out), stdin="y\n")
    flagged = [ln for ln in result.stdout.splitlines() if "[SKIP]" in ln and "same destination" in ln]
    assert len(flagged) == 2
    assert not (downloads / "Other" / "same.pdf").exists()
    assert (downloads / "invoice_oct.pdf").exists() and (downloads / "second.pdf").exists()


@pytest.mark.skipif(not symlinks_ok, reason="POSIX symlinks")
def test_symlink_source_is_never_followed(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside data")
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    (downloads / "invoice_oct.pdf").unlink()
    os.symlink(outside, downloads / "invoice_oct.pdf")
    result = run_cli("apply", str(out), stdin="y\n")
    assert "symbolic link" in result.stdout
    assert outside.read_bytes() == b"outside data" and outside.exists()


@pytest.mark.skipif(not symlinks_ok, reason="POSIX symlinks")
def test_symlinked_category_folder_cannot_redirect_moves(
    run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path
) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, downloads / "Documents")
    result = run_cli("apply", str(out), stdin="y\n")
    assert "category folder is a symbolic link" in result.stdout
    assert list(elsewhere.iterdir()) == []


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("not json", 5), ("[]", 5), ("{}", 5), ('{"schema_version": 99, "root": "/", "items": []}', 5),
        ('{"schema_version": 1, "root": "/", "items": [], "x": 1}', 5),
        ('{"schema_version": 1, "root": "relative", "items": []}', 5),
    ],
)  # fmt: skip
def test_malformed_plans_are_rejected(run_cli: Run, tmp_path: Path, text: str, code: int) -> None:
    path = tmp_path / "plan.json"
    path.write_text(text)
    result = run_cli("apply", str(path), stdin="y\n")
    assert result.returncode == code and "Traceback" not in result.stderr


def test_missing_plan_file(run_cli: Run, tmp_path: Path) -> None:
    result = run_cli("apply", str(tmp_path / "none.json"))
    assert result.returncode == 3 and "not found" in result.stderr


def test_root_mismatch_is_rejected(run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    other = tmp_path / "other"
    other.mkdir()
    before = snapshot(tmp_path)
    result = run_cli("apply", str(out), "--root", str(other), stdin="y\n")
    assert result.returncode == 5 and "does not match" in result.stderr
    assert snapshot(tmp_path) == before
    moved_root = tmp_path / "Renamed"
    downloads.rename(moved_root)
    result = run_cli("apply", str(out), stdin="y\n")
    assert result.returncode == 5 and "does not exist" in result.stderr


def test_matching_root_assertion_works(run_cli: Run, fake_ollama: Any, downloads: Path, tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    make_plan(run_cli, fake_ollama(), downloads, out)
    result = run_cli("apply", str(out), "--root", str(downloads), "--dry-run")
    assert result.returncode == 0


def test_hostile_filenames_cannot_inject_terminal_escapes(
    run_cli: Run, fake_ollama: Any, tmp_path: Path
) -> None:
    if sys.platform == "win32":
        pytest.skip("control characters are not valid in Windows file names")
    folder = tmp_path / "d"
    folder.mkdir()
    (folder / "\x1b[2Jevil.txt").write_bytes(b"x")
    result = run_cli("scan", str(folder))
    assert "\x1b" not in result.stdout

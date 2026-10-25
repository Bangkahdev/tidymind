# TidyMind

A local, privacy-first file organizer CLI. A **local open-weight model** (via [Ollama](https://ollama.com))
proposes a category and an optional clearer file name for each file in a folder. **Deterministic code**
validates the proposal, shows you the complete plan, and moves files **only after you approve**.

> The model is advisory. It cannot run commands, choose paths, delete files, or skip your approval.

Implements [`docs/SRS-TidyMind.md`](docs/SRS-TidyMind.md) v1.1. Status: **MVP implemented.**
261 automated tests pass on Windows 11 and the CI workflow runs on Ubuntu and Windows
(Python 3.11/3.12). A manual run with a real local model (`qwen3:4b`) and a 24-file category
evaluation are recorded in [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) and
[`docs/EVALUATION.md`](docs/EVALUATION.md). **Not done:** mutation testing, a network-disconnected
test, macOS support. See [Verification status](#verification-status).

## Why open-weight / local

- File **names, extensions and sizes** never leave your machine: the client refuses any non-loopback endpoint.
- No API key, no per-request cost, no service dependency after the one-time model download.
- The model is swappable (`--model`), and it is boxed in by a strict schema and an application-side allowlist.

## Requirements

- Python 3.11 or 3.12 (CI matrix: Ubuntu + Windows; macOS is **not** supported: no-overwrite rename is refused there).
- [Ollama](https://ollama.com) running locally, and a model: `ollama pull qwen3:4b`.
  Tested with Ollama 0.40.11 and `qwen3:4b` (Q4_K_M, Apache 2.0 license as shown by `ollama show`).
- No runtime Python dependencies (standard library only).

## Install and use

```bash
uv sync                      # or: pip install -e .
tidymind --help
tidymind scan ~/Downloads                         # lists eligible files, changes nothing
tidymind plan ~/Downloads --output plan.json      # asks the local model, previews, saves plan
tidymind plan ~/Downloads --dry-run               # preview only, writes nothing
tidymind apply plan.json                          # re-validates, previews, asks, then moves
tidymind apply plan.json --dry-run                # validate + preview, no prompt, no changes
tidymind apply plan.json --root ~/Downloads       # assert the plan belongs to this folder
```

There is **no** `--yes`/`--force` flag. Only `y`/`yes` approves; empty input, EOF, or anything else cancels.
`--endpoint` (or `TIDYMIND_OLLAMA_URL`) must be `localhost`, `127.0.0.1` or `::1`.

### Safety rules (enforced in code, tested)

| Rule | Where |
|---|---|
| Only direct children, regular files; hidden files, symlinks, directories, special files excluded | `scanner.py` |
| Hidden = name starts with `.` (all platforms) or Windows hidden attribute | `scanner.py` |
| Never opens file contents; model sees only `id`, name, extension, size | `model_client.py` |
| Model output is untrusted: strict schema, bounded retry (3), fail closed | `model_client.py` |
| Destination is derived by code: `root / allowlisted category / validated name` | `validator.py` |
| Rejects separators, `..`, drive prefixes, control chars, reserved names, extension changes | `validator.py` |
| Rejects duplicate destinations, collisions, stale/missing sources, symlinks | `validator.py` |
| Re-checks everything immediately before each move; never overwrites; no delete exists | `executor.py`, `fsops.py` |
| No-overwrite rename: Windows `os.rename`, Linux `renameat2(RENAME_NOREPLACE)`; otherwise refuse | `fsops.py` |
| Terminal escape sequences in file names are escaped in all output | `textutil.py` |

Categories: `Documents`, `Images`, `Archives`, `Installers`, `Other`.
The plan schema is versioned (`schema_version: 1`) and contains **no destination path**; see
[`docs/SRS-TidyMind.md`](docs/SRS-TidyMind.md) §6.

### Exit codes

`0` success · `1` internal error · `2` usage/configuration (incl. non-loopback endpoint) · `3` input error ·
`4` model unavailable/invalid output · `5` invalid plan or root mismatch · `6` not approved (nothing changed) ·
`7` some operations skipped or failed.

### Known limitations

- Classification uses names/extensions only; suggestions are not proof of contents.
- On a real model, `qwen3:4b` once returned a duplicate id on a four-file batch three times in a row, and the tool
  failed closed with exit code 4 and no changes. Retries now vary the sampling after the first attempt; that fix
  is covered by a unit test but has not been re-verified against the real model.
- The model proposed no file renames in the evaluation set, so renaming is unproven.
- No batch rollback: a multi-file run can partially complete (reported per item). Empty category folders may remain.
- Size + mtime are change indicators, not proof of identity; metadata checks cannot remove all race conditions.
- Approval is read from stdin (so scripted tests can pipe `y`); there is still no bypass flag.

## Development

```bash
uv sync --locked
uv run pytest                                  # unit + black-box + mocked integration
uv run pytest --cov --cov-branch --cov-report=json
uv run python scripts/check_coverage.py        # SRS 8.3 thresholds
uv run ruff format .
uv run ruff check .
uv run mypy --strict src/tidymind
uv run bandit -r src --severity-level high
```

(On Windows PowerShell 5.1, run these one per line; `&&` is not supported there.)

Tests never need Ollama, a model download, network access, or personal files: black-box tests run the
CLI in subprocesses against a deterministic fake Ollama HTTP server (`tests/fake_ollama.py`) and compare
before/after filesystem snapshots (paths, sizes, SHA-256).

### Required checks (branch protection must use these exact names)

`lint`, `typecheck`, `tests (<os>, py<version>)` (4 legs), `coverage`, `security`, `secrets`,
`workflow-security`, `hygiene`, `licenses`, `build`, and the aggregate `ci-gate`.
Branch protection is **not** claimed active until you verify it in the repository settings.
Release (`v*.*.*` tags) additionally runs `pinned-actions` and `mutation`.

## Verification status

| Evidence | Status |
|---|---|
| Unit, black-box, mocked-integration tests | 261 pass on Windows 11 (10 POSIX-only skipped); CI matrix on Ubuntu + Windows, Python 3.11/3.12 |
| Coverage thresholds (SRS 8.3) | Enforced by the `coverage` CI job |
| Property-based tests (Hypothesis) | Run in the test suite |
| Static analysis, security scans | `ruff`, `mypy --strict`, `bandit`, `pip-audit`, secret scan, workflow lint run in CI |
| Mutation score ≥ 80% (SRS 8.4) | **Not run** |
| Real-model manual acceptance ([`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)) | **Partial:** dry run, declined approval, conflicting target, changed source, approved apply (6 files) on Windows 11 with `qwen3:4b` |
| Offline claim | **Not claimed:** no network-disconnected run |
| Model category accuracy ([`docs/EVALUATION.md`](docs/EVALUATION.md)) | 23/24 on a small synthetic set; not an estimate for real folders |
| Windows behavior | Automated and manual runs on Windows 11 |
| Lockfile (`uv.lock`) | Committed; CI uses `--locked` |
| Actions pinned to commit SHAs | Done (full SHAs) |

## License

MIT (code). The model's license is separate and must be reviewed before distribution.
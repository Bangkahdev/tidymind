# TidyMind

A local, privacy-first file organizer CLI. A **local open-weight model** (via [Ollama](https://ollama.com))
proposes a category and an optional clearer file name for each file in a folder. **Deterministic code**
validates the proposal, shows you the complete plan, and moves files **only after you approve**.

> The model is advisory. It cannot run commands, choose paths, delete files, or skip your approval.

Implements [`docs/SRS-TidyMind.md`](docs/SRS-TidyMind.md) v1.1. Status: **MVP code and tests written;
real-model acceptance, offline test, model evaluation, lockfile and CI runs are still pending**
(see [Verification status](#verification-status)). Nothing here claims they have passed.

## Why open-weight / local

- File **names, extensions and sizes** never leave your machine: the client refuses any non-loopback endpoint.
- No API key, no per-request cost, no service dependency after the one-time model download.
- The model is swappable (`--model`), and it is boxed in by a strict schema and an application-side allowlist.

## Requirements

- Python 3.11 or 3.12 (CI matrix: Ubuntu + Windows; macOS is **not** supported — no-overwrite rename is refused there).
- [Ollama](https://ollama.com) running locally, and a model: `ollama pull qwen3:4b`
  (initial candidate; confirm the exact tag, quantization and license before release).
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
- No batch rollback: a multi-file run can partially complete (reported per item). Empty category folders may remain.
- Size + mtime are change indicators, not proof of identity; metadata checks cannot remove all race conditions.
- Approval is read from stdin (so scripted tests can pipe `y`); there is still no bypass flag.

## Development

```bash
uv sync --locked
uv run pytest                                  # unit + black-box + mocked integration
uv run pytest --cov --cov-branch --cov-report=json && uv run python scripts/check_coverage.py
uv run ruff format . && uv run ruff check --fix .   # run once before the first push: formatting was never checked
uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/tidymind
uv run bandit -r src --severity-level high
```

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
| Unit, black-box, mocked-integration tests | Written; 265 cases ran green locally with a minimal pytest-compatible runner (real pytest, ruff, mypy were unavailable offline) — CI not yet run |
| Coverage thresholds (SRS 8.3) | Gate script written; **not yet measured** |
| Mutation score ≥ 80% (SRS 8.4) | Config + release gate written; **not yet run** |
| Property-based tests | Written (Hypothesis); **not yet run** (Hypothesis unavailable where tests were written) |
| Real-model acceptance ([`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)) | **Not performed** |
| Offline claim | **Not claimed** — requires the network-disconnected run |
| Model category accuracy ([`docs/EVALUATION.md`](docs/EVALUATION.md)) | **Not evaluated** — no accuracy is claimed |
| Windows behavior | Branch logic unit-tested with mocks; **Windows CI/manual run pending** |
| Lockfile (`uv.lock`) | **Not generated** — run `uv lock` once and commit it |
| Actions pinned to commit SHAs | **Not done** — run `pinact run`; release gate enforces it |

## License

MIT (code). The model's license is separate and must be reviewed before distribution.

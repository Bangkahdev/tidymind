# Software Requirements Specification (SRS)

## TidyMind — Local AI File Organizer CLI

| Field | Value |
|---|---|
| Document version | 1.1 |
| Status | MVP specification — implementation and verification pending |
| Date | October 24, 2026 |
| Document language | English |
| Application interface language | English |
| Interface | Command-line interface (CLI) |
| Initial runtime target | Python 3.12; compatibility with Python 3.11 and 3.12 must be verified in CI |
| Target operating systems | Windows 11 and Linux x86-64, subject to the required CI and acceptance tests |
| Local model runtime | Ollama |
| Initial model candidate | `qwen3:4b`; exact model tag, quantization, license, and tested configuration must be documented before release |

> **Implementation status:** This document defines requirements and acceptance criteria. It does not assert that the application, tests, CI workflows, or release pipeline have been implemented or passed.

---

## 1. Introduction

### 1.1 Purpose

This document defines the functional, non-functional, security, testing, and delivery requirements for TidyMind. It is the baseline for implementation, code review, CI/CD, black-box testing, white-box testing, manual acceptance testing, and public documentation.

### 1.2 Problem Statement

A user's Downloads folder can accumulate files with vague names and mixed formats. Sorting and renaming those files manually is repetitive and easy to postpone. Cloud-based file assistants can introduce privacy, cost, and service-dependency concerns.

TidyMind uses a locally executed open-weight language model to propose file categories and optional clearer file names. It presents a reviewable plan before any filesystem change. The model is advisory: deterministic application code validates and executes approved operations.

### 1.3 Product Scope

TidyMind is a local CLI application that shall:

1. scan regular files directly inside one user-selected directory;
2. collect a minimal, documented set of file metadata;
3. ask a local model to propose a category and, where useful, a new filename;
4. convert model output into a versioned JSON plan;
5. validate the plan using deterministic application rules;
6. display the complete plan and conflicts before execution;
7. require explicit user approval before moving or renaming files;
8. refuse unsafe, stale, malformed, or conflicting operations;
9. report successful, skipped, and failed operations accurately; and
10. provide automated quality gates and reproducible release artifacts.

TidyMind is not an autonomous file-management agent. The model must not execute shell commands, choose arbitrary filesystem paths, delete files, or bypass user approval.

### 1.4 Goals

- Reduce repetitive manual file organization.
- Keep model inference and file metadata processing local by default.
- Make every proposed filesystem change inspectable before execution.
- Fail safely when the model, plan, filesystem, or user confirmation is unavailable.
- Demonstrate open-source AI with transparent tests and reproducible evidence.
- Establish strict CI/CD and black-box/white-box testing practices suitable for an open-source project.

### 1.5 Non-Goals

The MVP will not provide a GUI, cloud inference, recursive folder processing, file-content understanding, automatic deletion, shell-command execution by the model, cloud synchronization, multi-user accounts, database-backed history, or complex transactional rollback.

### 1.6 Definitions

| Term | Definition |
|---|---|
| Local model | A model served by a runtime on the user's own machine rather than a hosted third-party inference API. |
| Metadata | Limited information such as filename, extension, and file size. MVP classification must not read file contents. |
| Plan | A versioned, structured representation of proposed category and filename operations. |
| Dry-run | A mode that validates and displays an operation plan without changing the filesystem. |
| Explicit approval | An affirmative confirmation provided by the user after the plan is displayed. |
| Black-box test | A test of externally observable behavior through the CLI or another public interface, without relying on private implementation details. |
| White-box test | A test designed with knowledge of internal code paths, branches, and error-handling logic. |
| CI | Automated checks run for proposed or committed changes. |
| CD | The controlled build and publication of versioned release artifacts after required quality gates pass. |
| No-clobber operation | A filesystem operation that must not replace or overwrite an existing destination. |

### 1.7 Reference Materials

The implementation shall document the versions and official documentation used for Python, Ollama, pytest, coverage tooling, Ruff, the type checker, security scanners, and GitHub Actions in the repository. The README and dependency metadata must identify the exact model/runtime assumptions. Model and dependency licenses must be reviewed before public release. The project shall maintain a reproducible dependency lockfile and shall use locked dependencies in CI. The workflow security design shall follow GitHub's current secure-use guidance, including full-length commit SHA pinning for third-party Actions.

---

## 2. Overall Description

### 2.1 Product Perspective

TidyMind is a standalone CLI application composed of the following logical modules:

1. **Scanner:** identifies eligible files and collects permitted metadata.
2. **Model client:** sends the minimum required metadata to the local Ollama endpoint and receives a structured suggestion.
3. **Planner:** converts suggestions into a versioned JSON plan.
4. **Validator:** treats all model output and plan files as untrusted input and checks policy, containment, conflicts, and stale-file conditions.
5. **Reviewer:** renders a human-readable preview and obtains explicit approval.
6. **Executor:** performs only validated and approved operations, with no-clobber behavior.
7. **Reporter:** reports the actual result of each operation without exposing file contents.

The modules shall be separated sufficiently to test each one independently.

### 2.2 Intended Users

The target user is a general computer user who can run terminal commands and wants help organizing a folder without granting an AI service access to file contents or giving an agent unrestricted control over the computer. All end-user command names, prompts, help messages, errors, examples, and primary documentation shall be written in English for an international audience.

### 2.3 Runtime Environment

- Python 3.12 is the initial development target.
- The project shall declare an explicit supported Python range. The proposed minimum for the MVP is Python 3.11, with Python 3.11 and 3.12 tested in CI.
- Windows 11 and Linux x86-64 are target platforms; compatibility must not be claimed until the applicable CI and acceptance tests pass.
- Ollama provides local inference.
- `qwen3:4b` is the initial model candidate. The exact tag and model license must be confirmed and documented before release.
- The model must be downloaded during setup. After setup, the core scan/plan/apply workflow is intended to operate without sending metadata to an external service. A completely offline claim requires a documented network-disconnected acceptance test.

### 2.4 Design Constraints

- Scan only direct children of the selected root; no recursion in the MVP.
- Process regular files only. Exclude directories, symbolic links, and other special filesystem entries.
- Exclude hidden files by default. This behavior must be consistent across supported platforms and documented.
- Do not read document, image, archive, or installer contents for classification.
- The model may return only a category and a proposed basename. It must not provide an authoritative destination path.
- The application shall construct destination paths from the approved root, a fixed category allowlist, and a validated basename.
- Never delete files or overwrite a destination.
- Never apply a plan without an explicit approval step.
- Fail closed if a platform/filesystem operation cannot guarantee the required no-clobber behavior.
- CI tests must not download a model, require a live Ollama server, access personal files, or require production credentials.

### 2.5 Assumptions and Dependencies

- The user has permission to read the selected directory and to perform approved changes.
- Ollama and the selected model are installed for actual inference.
- Files may change between planning and execution; the application must revalidate them before each operation.
- File names and extensions may be misleading. Suggestions are not proof of actual file contents.
- Model inference can be slow or unavailable. The application must explain this without making filesystem changes.

---

## 3. External Interface Requirements

### 3.1 CLI Interface

The CLI shall use English for user-facing messages. It shall communicate:

- accepted commands, arguments, and examples;
- the resolved root directory;
- the number of discovered, excluded, and eligible files;
- proposed categories, target names, and destination paths;
- validation failures, conflicts, and stale-plan conditions;
- the exact operation scope awaiting approval; and
- actual success, skipped, and failed counts after execution.

Expected operational errors shall be concise and actionable. Full tracebacks shall be reserved for an explicit debug mode. Errors must not include file contents, secrets, or unnecessary absolute paths when a relative path is sufficient.

### 3.2 Software Interfaces

- **Ollama local API:** receives only the metadata needed for the suggestion and returns structured model output. The default endpoint shall be loopback-only.
- **Operating-system filesystem API:** scans metadata and performs validated operations.
- **JSON:** stores and loads versioned plans.

The MVP shall not provide a hosted inference integration. A custom endpoint must not be accepted if it points to a non-loopback host.

### 3.3 Failure Behavior

If Ollama is unavailable, the request times out, the response is malformed, or the configured model is missing, TidyMind shall return a non-zero exit status for the failed command, show an English error, and perform no filesystem changes.

---

## 4. Functional Requirements

Priority levels: **P0** = mandatory MVP requirement; **P1** = desirable only if the P0 scope and verification are complete.

### FR-01 — Scan a Directory (P0)

The application shall accept a user-specified root directory and scan only regular files directly inside it.

**Acceptance criteria:**
- A missing path, inaccessible path, or path that is not a directory produces an actionable error and non-zero exit status.
- Directories, symbolic links, and special files are excluded from candidate operations.
- Hidden files are excluded according to a documented cross-platform policy.
- Scanning does not move, rename, delete, or modify any file.
- A path containing spaces and supported Unicode characters is handled correctly.

### FR-02 — Collect Minimal Metadata (P0)

The application shall collect at least the basename, extension, file size, modification-time metadata, and any additional identity data required to detect a stale plan. Any additional metadata must be justified and documented.

**Acceptance criteria:**
- The application does not open file contents for classification.
- Only the minimum required metadata is included in a model request.
- No file contents, environment variables, credentials, or unrelated directory listings are sent to the model.
- Test fixtures use synthetic files and do not contain personal documents.

### FR-03 — Generate Local AI Suggestions (P0)

The application shall ask the configured local model to suggest one category and an optional improved basename for each eligible file.

Allowed categories:
- `Documents`
- `Images`
- `Archives`
- `Installers`
- `Other`

**Acceptance criteria:**
- The model response must conform to an application-defined schema.
- Missing fields, unknown categories, malformed JSON, unexpected extra structure, and invalid value types must be rejected or retried a bounded number of times.
- An ambiguous name may be categorized as `Other`; retaining the original filename must be allowed.
- The model output is untrusted data and must never be executed as code or a shell command.
- A failed model request must not create, move, rename, or delete any file.

### FR-04 — Build a Versioned Plan (P0)

The application shall produce a versioned JSON plan containing the resolved root, source identity metadata, proposed category, proposed basename, and enough information to revalidate the source before execution.

**Acceptance criteria:**
- A plan can be written to an explicitly selected output path.
- Unsupported schema versions and malformed plans are rejected.
- The plan cannot make the executor trust an absolute or relative destination path supplied by the model.
- Destination paths are derived by application code from the validated root, allowlisted category, and validated basename.
- Plan serialization is deterministic enough for repeatable tests, apart from documented runtime metadata.

### FR-05 — Validate Every Plan (P0)

Before a plan is eligible for execution, the application shall validate every item and the plan as a whole.

Validation shall include:
- schema version and field types;
- category membership in the fixed allowlist;
- a non-empty basename that is not `.` or `..`;
- rejection of path separators, drive prefixes, control characters, and path traversal attempts;
- platform-specific invalid names and reserved names where applicable;
- source and destination containment within the selected root;
- rejection of symlinks and non-regular files at source and destination;
- duplicate destinations within the same plan;
- destination collisions with existing entries;
- stale or missing source files; and
- consistency between the plan root and the root used for execution.

**Acceptance criteria:** any invalid item must be marked unsafe and must not reach the executor. A plan with a root mismatch must be rejected. The implementation must not silently rewrite an unsafe target into a different target.

### FR-06 — Preview the Plan (P0)

Before execution, the application shall show each proposed source, category, target basename, destination, and known conflict. The preview shall identify operations that will be skipped and explain why.

**Acceptance criteria:** previewing does not change the filesystem. The user must be able to cancel without side effects.

### FR-07 — Dry-run Mode (P0)

The application shall provide a dry-run mode that performs scanning, inference where requested, planning, validation, and preview without changing the filesystem.

**Acceptance criteria:** dry-run must not create category folders, move or rename files, or delete or overwrite anything. Automated tests shall compare before/after filesystem snapshots to prove this behavior.

### FR-08 — Explicit User Approval (P0)

The application shall require explicit interactive approval after the full plan is displayed and before execution begins.

**Acceptance criteria:**
- Entering `n`, `no`, or cancelling the confirmation must result in no filesystem changes.
- End-of-file input, an empty response, or an invalid confirmation must not be interpreted as approval.
- The MVP shall not expose a `--yes`, `--force`, or equivalent flag that bypasses review.
- The confirmation shall state the number of proposed operations and the root directory they affect.

### FR-09 — Execute Approved Operations Safely (P0)

After approval, the executor may create required category directories and move and/or rename files according to the validated plan.

**Acceptance criteria:**
- No delete operation exists in the MVP executor.
- No existing file or directory may be overwritten.
- The implementation shall use a no-clobber operation appropriate to the supported platform and filesystem. If it cannot guarantee no-clobber semantics, it must refuse the operation.
- Immediately before an operation, the executor shall re-check source existence, source identity metadata, destination availability, and root containment.
- A changed or replaced source shall be skipped and reported; it must not be processed using stale assumptions.
- A destination conflict that appears after preview shall not be overwritten.
- Per-file results shall report actual success or failure. A failed operation must never be reported as successful.
- Filesystem errors must leave the affected file in a recoverable and clearly reported state; no atomic multi-file rollback is promised by the MVP.

### FR-10 — Report Results (P0)

After execution, the CLI shall report succeeded, skipped, and failed operation counts, plus a concise reason for each skipped or failed item.

**Acceptance criteria:** totals match the recorded outcomes. Logs are local, optional, and must not contain file contents or model prompts containing unnecessary metadata.

### FR-11 — Handle Model and Runtime Failures (P0)

The application shall handle missing Ollama, missing model, connection errors, timeouts, invalid responses, and model refusal or empty responses.

**Acceptance criteria:** failures have actionable English messages, return appropriate non-zero exit codes, and cause no filesystem changes unless the user has already approved a plan and the failure occurs during a separately reported per-file filesystem operation.

### FR-12 — CLI Help and Version (P0)

The CLI shall provide `--help` and `--version`. Help output and all user-facing command examples shall be in English.

### FR-13 — Plan and Apply Separation (P0)

The application shall separate plan creation from apply/execution sufficiently that users can inspect a saved plan before applying it.

**Acceptance criteria:** applying a saved plan repeats all validation and preview/approval steps. A previously generated plan is not trusted merely because it was created by TidyMind.

---

## 5. Non-Functional Requirements

### NFR-01 — Privacy and Local Inference (P0)

Inference shall use the local Ollama runtime by default. The application shall not send file metadata to a cloud inference API, analytics service, or telemetry endpoint. The application must reject non-loopback model endpoints in the MVP.

The README shall distinguish initial setup/model download from inference-time behavior. The statement “works fully offline” may be made only after the complete claimed workflow has passed a network-disconnected acceptance test.

### NFR-02 — Filesystem Safety (P0)

The application shall fail closed when input validation, source revalidation, path containment, no-clobber guarantees, or approval requirements cannot be met. It shall not delete files, overwrite destinations, or perform operations outside the selected root.

### NFR-03 — Treat Model Output as Untrusted (P0)

All model output and saved plan data shall be validated as untrusted input. No model output may be evaluated as Python, passed to a shell, interpreted as a path, or used to choose arbitrary commands.

### NFR-04 — Portability (P0)

The application shall use path and filesystem APIs that account for platform differences. It shall not build or validate paths solely through string concatenation. Any platform compatibility claim must be supported by passing CI jobs and documented manual acceptance tests where CI cannot verify behavior.

### NFR-05 — Maintainability and Style (P0)

Modules shall have clear responsibilities, explicit error handling, type annotations for public/internal interfaces where appropriate, and documentation for security-sensitive behavior. Ruff lint and formatting checks, plus the configured static type checker, shall be enforced in CI.

### NFR-06 — Test Isolation and Repeatability (P0)

Automated tests shall use temporary directories, synthetic files, deterministic fixtures, a mock/local test HTTP server, and a fake model client. The standard CI suite must not depend on network access, an installed Ollama runtime, downloading model weights, or personal files.

### NFR-07 — Documentation (P0)

The README shall be written in English and document supported platforms, Python/runtime requirements, model installation, privacy boundaries, commands, plan schema, approval behavior, dry-run, limitations, test commands, CI status, and known risks.

### NFR-08 — Performance Reporting (P1)

No universal inference latency guarantee is imposed in the MVP. The demo/evaluation report should record the tested hardware, OS, Python version, model tag/quantization, number of files, and observed inference/total duration. Performance claims must be based on measured results.

### NFR-09 — Accessibility of CLI Output (P0)

The CLI shall provide readable text output without relying on color alone to convey errors, conflicts, or success. Core workflows must remain usable in a plain terminal and in CI logs.

---

## 6. Data Model and Plan Format

### 6.1 Allowed Categories

The category value shall be one of `Documents`, `Images`, `Archives`, `Installers`, or `Other`. Application code, not the model, determines the corresponding subdirectory name.

### 6.2 Illustrative Plan Schema

The example below is illustrative only; it is not evidence that the schema has been implemented.

```json
{
  "schema_version": 1,
  "root": "/example/Downloads",
  "items": [
    {
      "source_name": "invoice_oct.pdf",
      "source_size": 48213,
      "source_mtime_ns": 1720000000000000000,
      "category": "Documents",
      "target_name": "invoice_october.pdf",
      "reason": "The filename appears to refer to an invoice"
    }
  ]
}
```

Example metadata values are placeholders. The implementation shall define required fields and their types in one canonical schema. Absolute destination paths must not be accepted as trusted model output. The application shall derive destinations during validation and execution.

### 6.3 Stale Plan Detection

Before each operation, the application shall verify that the source still exists and that the captured identity metadata is consistent with the planned source. At minimum, the plan shall record size and modification-time metadata. If the source is missing or changed, the operation shall be skipped and the user shall be asked to generate a new plan.

Size and modification time are change indicators, not cryptographic proof of file identity. The implementation may use an additional local identity mechanism if justified. It must not imply that metadata checks eliminate all filesystem race conditions.

### 6.4 Partial Execution

The MVP does not promise an atomic transaction across all files. It shall isolate item results, avoid overwrites, and report partial completion precisely. It must never claim all-or-nothing behavior unless such behavior is implemented and tested.

---

## 7. Planned CLI Contract

The exact packaging entry point may change, but the public interface shall provide equivalent capabilities:

```text
tidymind scan <directory>
tidymind plan <directory> [--output <plan.json>] [--dry-run]
tidymind apply <plan.json>
tidymind --help
tidymind --version
```

`apply` must repeat validation, display the plan, and ask for approval. The MVP shall not include an option that bypasses confirmation. Any command that fails must return a documented non-zero exit code. Stable exit-code meanings should be documented and covered by black-box tests.

---

## 8. Verification Strategy: Black-box and White-box Testing

Testing is a release requirement, not an optional development activity. A passing unit-test count alone is insufficient. Verification shall cover externally visible behavior, internal decision paths, security boundaries, cross-platform behavior, and a real local-model acceptance check.

### 8.1 Black-box Testing (P0)

Black-box tests shall exercise the public CLI behavior and outputs without asserting private function calls or internal implementation structure. Tests shall invoke the CLI as a subprocess where practical, using an isolated temporary directory and a fake local model service.

The black-box test suite shall cover:

1. **Equivalence partitioning:** valid directory, nonexistent directory, regular file passed as a directory, inaccessible directory, empty folder, and folder with mixed eligible/ineligible entries.
2. **Boundary-value analysis:** empty filename-like model values, maximum practical filename lengths, zero-byte files, large metadata values, Unicode names, names with spaces, and platform-reserved names.
3. **Decision tables:** each combination of valid/invalid plan, available/conflicting destination, unchanged/changed source, and approved/declined confirmation.
4. **State transitions:** scan → plan → preview → reject; scan → plan → approve → execute; plan → source changes → apply; plan → destination conflict appears → apply.
5. **Negative and adversarial cases:** `..`, absolute paths, drive prefixes, alternate separators, control characters, invalid JSON, wrong schema types, unknown categories, duplicate targets, symlinks, paths outside the root, and non-loopback model endpoints.
6. **Failure injection:** model unavailable, timeout, malformed response, permission error, disk/rename error, and interrupted confirmation.
7. **No-side-effect assertions:** rejected plans, failed inference, dry-run, declined approval, and invalid confirmation leave all source files and the directory layout unchanged.
8. **CLI contract:** help/version output, stable exit codes, English error messages, and no success message for failed operations.

Black-box tests shall compare pre-operation and post-operation snapshots including relative paths, file sizes, and content hashes for synthetic test files. Tests must prove that pre-existing destination contents are unchanged after a collision.

### 8.2 White-box Testing (P0)

White-box tests shall target internal branches, validation order, exception paths, and safety guards. They shall include:

- scanner filtering and metadata error paths;
- model-client request construction, timeout handling, response parsing, and retry limits;
- planner schema construction and determinism;
- every validator rejection branch, including path containment and duplicate targets;
- executor checks immediately before filesystem mutations;
- no-clobber conflict handling and failure reporting;
- approval and cancellation branches;
- stale-source detection and per-item error isolation; and
- exit-code and result-counter calculations.

Use fakes/mocks for model calls and deterministic filesystem fixtures. A test must not rely exclusively on mocks where actual filesystem behavior is the property under test; executor tests must use temporary real directories for moves, name collisions, and post-operation verification.

### 8.3 Coverage Gates (P0)

Coverage shall be collected with branch measurement enabled. CI shall enforce these minimums:

- **Overall production-code statement coverage: at least 90%.**
- **Overall production-code branch coverage: at least 85%.**
- **`validator` module statement coverage: at least 95%.**
- **`validator` module branch coverage: at least 90%.**
- **`executor` module statement coverage: at least 95%.**
- **`executor` module branch coverage: at least 90%.**

Coverage shall exclude only clearly identified non-production files such as tests, generated files, and CLI entry-point boilerplate where justified. Exclusions must be documented and may not be used to hide untested safety-critical logic. CI shall fail if any threshold is missed. The pipeline shall retain a human-readable coverage summary and machine-readable report as artifacts.

### 8.4 Mutation Testing (P0 for Release; P1 for Every Pull Request)

Mutation testing shall be run against the validator and executor before a public release. The target is at least an **80% mutation score** on non-equivalent mutants in those modules. Surviving mutants must be reviewed and classified; exclusions must be justified and documented. Mutation testing should run on pull requests where runtime permits, but it is a mandatory release gate.

Mutation score is a measure of test sensitivity, not a substitute for black-box, security, or manual acceptance testing.

### 8.5 Property-Based and Robustness Testing (P0)

Where practical, property-based tests shall generate malformed category/name/path values and verify invariant properties:

- invalid paths never escape the selected root;
- unapproved plans never mutate the filesystem;
- destination conflicts never overwrite existing data;
- unsupported categories never reach execution; and
- parser failures result in controlled errors rather than uncaught exceptions.

Use fixed seeds or reproducible failure examples in CI so failures can be reproduced locally.

### 8.6 Integration Testing (P0)

The automated integration suite shall run the CLI with a deterministic fake Ollama-compatible HTTP server or equivalent test double. It shall verify the request/response boundary, schema enforcement, planning, validation, approval, and execution without downloading a real model.

A separate manual acceptance test shall use the actual installed Ollama runtime and selected model. This test shall be reported separately from mock-based tests.

### 8.7 Manual Acceptance Testing (P0)

Before release, a tester shall complete the following using synthetic files in a dedicated temporary folder:

1. run `--help` and verify instructions are readable in English;
2. scan a folder containing mixed file types, a hidden file, a subdirectory, and a symlink where supported;
3. generate a plan using the real local model;
4. inspect the proposed categories and names;
5. run dry-run and verify that the filesystem remains unchanged;
6. decline approval and verify that the filesystem remains unchanged;
7. approve a safe plan and verify the resulting paths and file hashes;
8. create a target conflict after preview and verify that the target is not overwritten;
9. alter or remove a source after planning and verify that the stale operation is rejected;
10. stop Ollama and verify safe failure with no changes; and
11. if claiming full offline operation, disconnect the network after setup and complete the documented offline workflow.

The acceptance record shall include OS, Python version, model tag and quantization, hardware summary, test date, test result, and any failures. Do not include personal files or sensitive metadata in the record.

### 8.8 Model Quality Evaluation (P0 for Honest Reporting)

Use a synthetic and/or explicitly consented test set of at least 20 files with expected categories recorded before inference. The evaluation shall report:

- number of files evaluated;
- correct category suggestions and category accuracy;
- invalid model responses;
- unsafe proposals rejected by validators;
- examples of ambiguous or incorrect suggestions; and
- model, quantization, operating system, and runtime configuration.

Filename suggestions shall be evaluated separately from category accuracy. No accuracy percentage may be claimed before the test set has been evaluated. Public test sets must not contain private personal files or metadata.

### 8.9 Test Evidence and Reporting

The repository shall distinguish:

- unit tests;
- black-box CLI tests;
- white-box coverage results;
- static analysis and security scans;
- mocked integration tests;
- real-model acceptance tests; and
- manual/demo observations.

A mock-based pass shall never be described as proof that the actual model initialized or inferred successfully. A CI pass shall not be described as proof of model quality on real-world files.

---

## 9. CI/CD Requirements

CI/CD is a P0 project requirement. Changes must not be considered release-ready solely because they work on the maintainer's computer.

### 9.1 Workflow Triggers (P0)

GitHub Actions shall run required checks on:

- pull requests targeting `main`;
- pushes to `main`; and
- version-tagged release candidates such as `v*`.

A manually triggered workflow may be provided for diagnostics. The ordinary CI suite shall not require cloud credentials or a live model service.

### 9.2 Required CI Jobs (P0)

The workflow shall include the following jobs or equivalent isolated stages:

1. **Environment and packaging:** install the project from declared metadata in a clean environment and verify the package can be built.
2. **Lint and format:** run `ruff check` and `ruff format --check`; any unapproved lint or formatting violation shall fail CI.
3. **Static typing:** use `mypy --strict` for production modules, or a documented equivalent strict type-checking profile. Type errors in production modules shall fail CI; exceptions require a narrow, documented justification.
4. **Unit and white-box tests:** run the unit suite and collect statement/branch coverage.
5. **Black-box CLI tests:** invoke public CLI commands in subprocesses with temporary files and a fake local model service.
6. **Integration tests:** verify end-to-end planning and execution through the fake model boundary.
7. **Coverage enforcement:** fail if any threshold in Section 8.3 is missed.
8. **Security checks:** run Bandit against production code and `pip-audit` against the locked dependency set. Any confirmed high- or critical-severity code finding and any known vulnerability in a production dependency shall fail CI. Lower-severity findings must be triaged, documented, and either fixed or explicitly accepted with rationale before release.
9. **Secret scanning:** run Gitleaks or an equivalent maintained secret scanner against the proposed changes and repository history where practical. Any confirmed secret shall block merge; rotating a leaked credential does not replace removing it from history where feasible.
10. **Workflow security:** validate workflow syntax with `actionlint` or an equivalent checker and scan workflow security with a maintained static analyzer. Workflow findings rated high or critical shall block merge.
11. **Repository hygiene:** ensure generated model weights, caches, virtual environments, personal test data, local plans containing personal metadata, and build artifacts are not committed.
12. **License and dependency inventory:** generate a dependency/license report from the locked dependency set. Unknown or unreviewed production dependency licenses shall block a release until reviewed. The model's license shall be separately reviewed.
13. **Build validation:** build source and wheel distributions and verify they are installable in a clean environment.

All required jobs must finish successfully. A skipped or cancelled required job is not a successful gate.

### 9.3 Cross-platform and Python Matrix (P0)

The automated behavior suite shall run on:

- Ubuntu Linux and Windows;
- Python 3.11 and Python 3.12.

The full matrix is required for pull requests and release candidates, subject only to documented temporary CI outages. A failure on any supported matrix leg blocks release. macOS is not a supported MVP platform unless it is explicitly added to the support statement and covered by CI.

### 9.4 Determinism and Network Independence (P0)

- Unit, black-box, coverage, and ordinary integration jobs shall use synthetic data and fake model responses.
- These tests shall not download model weights or call a hosted inference endpoint.
- Test randomness shall be seeded or failures shall be reproducible.
- Dependency installation and vulnerability scanning may access package/security registries as needed; the application test itself must not send file metadata to external services.
- Tests must not access a user's home Downloads folder or modify files outside isolated temporary directories.

### 9.5 CI Security Hardening (P0)

- Workflows shall request only the minimum required GitHub token permissions.
- Third-party GitHub Actions used in release-sensitive workflows shall be pinned to immutable full commit SHAs, with a comment identifying the corresponding version.
- Pull-request workflows shall not execute untrusted repository code with write-capable secrets.
- No model credentials, private keys, or personal tokens may be stored in the repository.
- The release workflow shall not need secrets beyond the repository-provided token required to publish its own artifacts.
- Workflow files shall be included in code review and static/hygiene checks.

### 9.6 Branch and Merge Policy (P0)

The `main` branch shall require all designated CI status checks to pass before a pull request can merge. Direct pushes to `main` should be disabled where repository settings permit. Any emergency bypass must be documented and followed by a passing full pipeline before a release can be created.

At least one human review is recommended when another maintainer is available. Review requirements shall not be represented as enforced unless branch protection settings actually enforce them.

### 9.7 Release Pipeline (P0)

For a `vX.Y.Z` release candidate, the release workflow shall:

1. run the complete CI matrix and required quality/security gates;
2. run mandatory mutation testing against the validator and executor;
3. build source and wheel distributions in a clean environment;
4. install the built artifact and run a CLI smoke test;
5. generate SHA-256 checksums for release artifacts;
6. generate or retain a software bill of materials (SBOM) where supported by the chosen tooling;
7. attach the artifacts, checksums, and release notes to a GitHub Release only after every mandatory gate passes; and
8. make no claim that a real-model offline test passed unless the acceptance record exists.

Publishing to PyPI, deploying a hosted service, or automatically installing software onto users' devices is outside the MVP. The CD deliverable is a tested, versioned, verifiable release artifact and its supporting evidence.

### 9.8 CI Artifacts and Failure Diagnostics (P0)

CI shall retain test reports, coverage reports, build artifacts for release jobs, and concise security-scan summaries according to the repository's configured retention. Failure output shall help a maintainer identify the failed gate without logging secrets or sensitive user data.

### 9.9 Required Status Definition (P0)

The README shall list the required checks. Names used by branch protection must match the actual workflow job/status names. The SRS or README must not claim branch protection is active until the repository configuration has been checked. CI shall use the committed dependency lockfile in frozen/locked mode and fail if the lockfile is out of sync with project metadata.

---

## 10. Test Traceability Matrix

| Requirement area | Black-box evidence | White-box evidence | CI/CD gate |
|---|---|---|---|
| Scan and metadata | CLI scan tests with mixed synthetic entries | Scanner branches and OS error paths | Linux/Windows test matrix |
| Model integration | CLI test against fake Ollama-compatible server | Request construction, timeout, parser, retry tests | Deterministic integration job |
| Plan schema | Save/load/reject malformed plan via CLI | Schema validation branch tests | Unit and coverage gates |
| Path safety | Traversal and root-escape attempts rejected | Validator branch tests; mutation testing | Coverage + mutation release gate |
| Approval and dry-run | Snapshot proves no changes on cancel/dry-run | Confirmation and early-return paths | Black-box and coverage gates |
| No-overwrite execution | Existing target remains byte-for-byte unchanged | Executor collision/error branches | Cross-platform tests + mutation gate |
| Stale plan | Change source or introduce conflict before apply | Revalidation branches | Integration and black-box tests |
| Failure handling | Model unavailable and filesystem errors yield non-zero exit | Exceptions and exit-code branches | Unit, integration, coverage |
| CLI packaging | Clean install and `--help`/`--version` smoke test | Entry-point and parsing tests | Build validation |
| Dependencies/secrets | No credentials or cache artifacts in repository | Configuration/scanner rules where applicable | Dependency audit, secret scan, hygiene check |
| Real model/offline claim | Manual acceptance log with real Ollama | Not replaced by mocks | Release checklist; not claimed from ordinary CI |

---

## 11. Acceptance and Release Criteria

The MVP may be described as release-ready only when all applicable items below are evidenced:

- All P0 functional requirements are implemented or any exception is explicitly documented as a release blocker; no omitted P0 requirement may be silently treated as complete.
- Black-box CLI tests pass on Linux and Windows for the declared Python matrix.
- White-box tests meet every statement and branch coverage threshold in Section 8.3.
- Mutation score meets the Section 8.4 release target, with surviving mutants reviewed and documented.
- Ruff, static typing, security lint, dependency audit, secret scan, repository hygiene, and package build checks pass.
- Dry-run, decline/cancel, invalid plans, and model failures are demonstrated to have no filesystem side effects.
- No-overwrite, path containment, stale-plan handling, and user approval behavior pass tests using real temporary filesystem entries.
- The release candidate builds and installs in a clean environment.
- A real local-model acceptance test has been recorded separately from mock-based tests.
- Any claim of full offline operation is supported by a successful network-disconnected acceptance test.
- The category evaluation is recorded without overstating quality or hiding failures.
- The README and release notes accurately distinguish automated tests, manual tests, model evaluation, and known limitations.

If any safety-critical gate fails, the release shall be blocked regardless of the total number of passing tests.

---

## 12. Risks and Mitigations

| Risk | Impact | Required mitigation |
|---|---|---|
| Incorrect model suggestion | Wrong category or confusing name | Preview, allowlisted categories, `Other`, and user cancellation |
| Malformed model output | Invalid plan or unexpected behavior | Strict schema validation, bounded retry, fail closed |
| Path traversal or malicious plan | Operation outside the chosen folder | Construct target paths in application code; containment checks and adversarial tests |
| Existing destination | Accidental data loss | No-clobber semantics; fail closed if guaranteed behavior is unavailable |
| Source changes after planning | Applying stale assumptions | Revalidate source and destination immediately before each operation |
| Runtime/model unavailable | Workflow cannot generate suggestions | Actionable error; no filesystem mutation before successful plan and approval |
| Metadata contains private information | Privacy leakage | Minimal metadata, local-only endpoint, no telemetry, synthetic fixtures |
| Platform differences | Different path or rename behavior | Windows/Linux CI matrix and platform-specific validation tests |
| Weak tests despite high test count | Hidden branches or unsafe regressions | Separate black-box and white-box suites, branch coverage, mutation testing, manual acceptance |
| Dependency vulnerability | Supply-chain exposure | Dependency audit, update process, version constraints, release gate |
| Secret accidentally committed | Credential compromise | Secret scanning, least-privilege CI, no personal credentials in workflows |
| License incompatibility | Distribution and compliance risk | Review source, runtime, model, and dependency licenses before release |
| Unsupported offline claim | Misleading public documentation | Explicit network-disconnected acceptance test and evidence record |
| Partial multi-file failure | Some operations completed while others failed | Per-item reporting, no overwrite, documented lack of batch rollback |

---

## 13. Out of Scope

The following remain outside the MVP:

- GUI, desktop windowing application, or web dashboard;
- recursive folder scanning;
- reading or extracting document/image/archive contents;
- OCR, content-based semantic file understanding, or image classification;
- automatic deletion or overwriting;
- unreviewed or non-interactive execution;
- model-controlled shell commands or autonomous agents;
- hosted inference APIs, telemetry, or cloud synchronization;
- database, accounts, multi-user support, and persistent behavioral memory;
- complex transaction rollback across all files;
- guaranteed classification accuracy before evaluation; and
- PyPI publication or hosted-service deployment.

---

## 14. Deliverables

The intended MVP deliverables are:

1. Python CLI source code;
2. dependency and packaging metadata;
3. scanner, planner, validator, model-client, executor, and reporting modules;
4. black-box CLI tests and white-box unit/branch tests;
5. coverage and mutation-test configuration;
6. GitHub Actions CI/CD workflows;
7. security scan and repository hygiene configuration;
8. README and documented model/setup requirements in English;
9. synthetic test fixtures and illustrative JSON plans;
10. real-model acceptance record and category-evaluation summary, completed only after testing;
11. reproducible release artifacts and SHA-256 checksums when a release is created; and
12. an English DEV.to article showing the use case, architecture, demo, actual test evidence, open-weight rationale, limitations, and future work.

---

## 15. Traceability to Project Goals

| Goal | Requirements | Evidence |
|---|---|---|
| Reduce repetitive file organization | FR-01–FR-04, FR-06, FR-09 | Demo on a synthetic Downloads-like folder and category-evaluation report |
| Keep processing local | FR-03, FR-11, NFR-01 | Local endpoint configuration and real-model acceptance record |
| Prevent unsafe filesystem operations | FR-05, FR-07–FR-09, FR-13, NFR-02, NFR-03 | Adversarial path, collision, stale-plan, cancel, dry-run, and mutation tests |
| Make behavior understandable | FR-06, FR-10, FR-12, NFR-07, NFR-09 | English CLI output, previews, help, and README |
| Verify externally observable behavior | Section 8.1 | Black-box subprocess tests with filesystem snapshot comparisons |
| Verify internal decisions and branches | Sections 8.2–8.5 | Unit tests, branch coverage, property-based tests, mutation testing |
| Prevent regressions across platforms | Sections 9.2–9.4 | Required Ubuntu/Windows and Python 3.11/3.12 CI matrix |
| Publish trustworthy artifacts | Sections 9.5–9.9 | Protected merge gates, clean package build/install, checksums, security and hygiene reports |
| Report claims honestly | Sections 8.7–8.9 and 11 | Separate evidence for mocked integration, real-model testing, offline testing, and measured quality |

---

## 16. Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | October 24, 2026 | Initial Indonesian-language MVP SRS for the TidyMind CLI. |
| 1.1 | October 24, 2026 | Rewritten in English for a global audience; specified English-only application output, strict black-box and white-box verification, coverage and mutation gates, cross-platform CI, security checks, branch protection expectations, and a gated release pipeline. |

# Real-model acceptance record (SRS 8.7)

> Status: **NOT PERFORMED.** Mock-based CI results are not evidence that a real model works.
> Fill this in after running with a real Ollama model on synthetic files only. The release workflow
> reports an acceptance record as present only if a line `Result: PASS` appears below.

| Field | Value |
|---|---|
| Date | |
| OS / version | |
| Python version | |
| Hardware summary | |
| Ollama version | |
| Model tag + quantization | |
| Network disconnected after setup? | yes / no |

## Checklist (dedicated temporary folder, synthetic files)

- [ ] 1. `tidymind --help` readable in English
- [ ] 2. `scan` on mixed types incl. hidden file, subdirectory, symlink (where supported)
- [ ] 3. `plan` with the real local model
- [ ] 4. Inspect proposed categories and names
- [ ] 5. `plan --dry-run` / `apply --dry-run`: filesystem unchanged
- [ ] 6. Decline approval: filesystem unchanged
- [ ] 7. Approve a safe plan: verify paths and file hashes
- [ ] 8. Create a conflicting target after preview: not overwritten
- [ ] 9. Alter/remove a source after planning: stale operation rejected
- [ ] 10. Stop Ollama: safe failure, no changes
- [ ] 11. (Only if claiming offline) disconnect network after setup and complete the workflow

Failures / notes:

Result: PENDING

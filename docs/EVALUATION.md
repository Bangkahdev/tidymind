# Model category evaluation (SRS 8.8)

> Status: **NOT EVALUATED.** No accuracy figure may be quoted until this is filled in.

Test set: [`eval/dataset.json`](../eval/dataset.json) — 24 synthetic file names; expected categories were
fixed in that file before any inference. Run against a real model:

```bash
python scripts/evaluate.py --model qwen3:4b > docs/EVALUATION-RESULT.md
```

Paste the output here and add: model tag + quantization, OS, runtime configuration, hardware, number of
invalid model responses, and notes on ambiguous/incorrect suggestions. File-name suggestions are judged
separately from category accuracy.

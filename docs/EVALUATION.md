# Model category evaluation (SRS 8.8)

Test set: eval/dataset.json, 24 synthetic file names. Expected categories were fixed in that file
before any inference. Single run, single batch, temperature 0, thinking disabled (`think: false`).

| Field | Value |
|---|---|
| Model | qwen3:4b (isi tag lengkap + quantization dari `ollama show qwen3:4b`) |
| Ollama version | (isi dari `ollama --version`) |
| OS / Python | Windows 11 (10.0.26200) / Python 3.13.14 |
| Hardware | (isi: CPU, RAM, GPU atau tanpa GPU) |
| Files evaluated | 24 |
| Correct categories | 23 (95.8%) |
| Invalid model responses | 0 (retry dinonaktifkan di skrip: max_attempts=1) |
| Unsafe name proposals rejected | 0 |
| Inference duration | 24.5 s (satu batch, 24 file) |

## Incorrect or ambiguous
- `meeting notes.txt`: expected Documents, got Other

## File name suggestions
Model tidak mengusulkan perubahan nama pada set ini; kemampuan penamaan ulang tidak terbukti.

## Limits of this result
- Set kecil dan sintetis dengan nama yang sebagian besar jelas dari ekstensinya; 95,8% bukan
  estimasi akurasi untuk folder Downloads nyata.
- Satu kali jalan; tidak diuji stabilitas antar-run atau model lain.
- Hanya nama, ekstensi, dan ukuran yang dikirim; isi file tidak pernah dibaca.
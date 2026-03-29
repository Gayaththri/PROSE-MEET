# PROSE-MEET Backend

API and pipeline for meeting audio: transcription (faster-whisper), prosody, importance, and summaries. The ASR pipeline uses a **lower VAD threshold** by default so quiet or low-volume speech is less likely to be dropped; for very difficult recordings you can set `WHISPER_NO_VAD=1` to transcribe the entire file (see `.env.example`).

Gap 1 + Gap 2 behavior:
- Gap 1 computes utterance importance from semantic + prosodic fusion.
- Gap 2 detects meeting domain (corporate/academic/medical) and applies domain-adaptive boosts to ranking/highlights so domain influences output, not just UI labels.

**Gap 2 domain detection (default: self-supervised zero-shot):** uses a **frozen** pretrained sentence encoder (Sentence-BERT / MiniLM family) with **prototype-based zero-shot** classification — no fine-tuning on labelled meetings. Importance adaptation then uses **embedding similarity** to the predicted domain’s prototypes (not raw keyword overlap). Requires `sentence-transformers` / `torch` (see `requirements.txt`); if unavailable, the pipeline falls back to lexical `keyword` matching. Set `PROSE_DOMAIN_METHOD=keyword` to force the lexical baseline only.

## Quick start

Use the same interpreter for installs and runs (on Windows, `pip` and `python` can point at different installs):

```bash
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

API: `http://127.0.0.1:8000`

### Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

### Manual Gap 1 smoke script

`test_gap1.py` runs the full pipeline on a local WAV (not part of pytest). Default file: `<repo-root>/data/test_audio/meeting.wav` (create that folder and add a sample, or pass a path).

```bash
cd backend
python test_gap1.py
python test_gap1.py --audio path/to/meeting.wav
```

---

## Supervised importance model (prosody + semantics)

The pipeline can use a trained utterance-level classifier for importance scoring.  
If a model exists in `backend/models/`, `pipeline/importance.py` loads it automatically; otherwise it falls back to rule-based fusion.

### Training data format (CSV)

Required columns:
- `text`
- `label` (1/0, true/false, important/not important)

Optional feature columns (recommended):
- `pitch_variance`
- `mean_energy`
- `pause_ratio`
- `start`
- `end` (or `duration`)

### Train model + threshold

```bash
python train_importance_model.py --data data/importance_labels.csv --label-col label
```

### Recalibrate threshold only

```bash
python calibrate_importance_threshold.py --data data/importance_labels_val.csv --label-col label
```

### Evaluate Gap 1 + Gap 2 (single script)

Run one evaluation pass for:
- Gap 1: utterance importance (Precision/Recall/F1/AUC)
- Gap 2: meeting domain detection accuracy

```bash
python evaluate_gaps.py --data data/eval_dataset.csv
```

To save machine-readable output:

```bash
python evaluate_gaps.py --data data/eval_dataset.csv --output-json data/experiments/gap_eval.json
```

### Evaluate Gap 2 zero-shot generalisation (corporate -> other domains)

This is the direct proof setup for Gap 2:
- Train on one domain only (default: `corporate`)
- Evaluate same-domain baseline
- Evaluate cross-domain before adaptation
- Evaluate cross-domain after domain adaptation

```bash
python evaluate_gap2_zeroshot.py --data data/eval_dataset.csv --train-domain corporate --output-json data/experiments/gap2_zeroshot.json
```

The script prints and saves three scenario metrics:
- `same_domain_baseline` (corporate test split)
- `cross_domain_no_adaptation`
- `cross_domain_with_adaptation`

Use these directly in your report table to demonstrate zero-shot transfer without retraining.

Expected CSV columns:
- Required for Gap 1: `text`, one of `label` / `importance_label` / `important`
- Required for Gap 2: `meeting_id` (or `conversation_id`), one of `true_domain` / `domain` / `domain_label`
- Optional features: `pitch_variance`, `mean_energy`, `pause_ratio`, `start`, `end`, `duration`

### Benchmark rule-based vs supervised importance

```bash
python benchmark_importance_models.py --data data/eval_dataset.csv --label-col label
```

To save machine-readable output:

```bash
python benchmark_importance_models.py --data data/eval_dataset.csv --label-col label --output-json data/experiments/benchmark.json
```

### Gap 1 ablation (prosody vs semantics vs fusion)

```bash
python ablation_gap1.py --data data/eval_dataset.csv --label-col label --output-json data/experiments/ablation.json
```

### Runtime benchmark (end-to-end pipeline)

```bash
python benchmark_runtime.py --inputs ../data/test_audio --output-json data/experiments/runtime.json
```

### Reproducible experiment logging

1. Copy and edit config:
   - `configs/experiment.template.json`
2. Run:

```bash
python run_experiment.py --config configs/experiment.template.json
```

This appends one JSON line per run to `data/experiments/runs.jsonl` for chapter-wise reporting.

### Build Chapter 8 markdown tables

```bash
python build_results_tables.py --gap-eval-json data/experiments/gap_eval.json --benchmark-json data/experiments/benchmark.json --ablation-json data/experiments/ablation.json --runtime-json data/experiments/runtime.json --output-md docs/chapter8_results.md
```

### Dataset templates (seed data)

Starter templates are committed under **`backend/data/templates/`** so new clones can run eval and `run_all_experiments.py` without creating everything by hand:

- `backend/data/templates/eval_dataset_template.csv` — Gap 1 + Gap 2 eval (copy to `backend/data/eval_dataset.csv` or use as-is; scripts fall back to this path)
- `backend/data/templates/importance_labels_template.csv` — Training data for the importance model
- `backend/data/templates/importance_labels_val_template.csv` — Validation data for threshold calibration
- `backend/data/templates/manifests/custom.csv` — Manifest layout for `run_eval` (replace paths with your audio and reference files)

See **`backend/data/templates/README.md`** for quick start and copying instructions.

**Importance metrics in results:** Chapter 8 tables and `evaluation/RESULTS_SUMMARY.md` show "-" for importance (samples, precision, recall, F1, AUC) and for the "Supervised" row when:
- No labeled importance data is available (eval CSV without labels, or manifest references without per-utterance importance), or
- No trained model is present (Gap 1 evaluation and supervised benchmark require a model in `backend/models/`).

Add a proper `eval_dataset.csv` with importance labels and optionally train the model, then re-run evaluation and table build to fill those cells.

Saved artifacts (when trained):
- `backend/models/importance_classifier.joblib`
- `backend/models/importance_classifier_meta.json`

---

## Privacy and consent metadata

Optional environment variables:

- `ANONYMIZE_TRANSCRIPTS=1`
  - Masks emails/phone numbers/student-style IDs in transcript, summary, highlights, and speaker summaries before save.
- `MEETING_CONSENT_STATUS=<status>`
  - Example values: `obtained`, `pending`, `not_provided`.
  - Saved under `result["consent"]`.

---

## Test suite

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Includes:
- Unit tests for importance/domain/highlight behavior.
- API integration test for `/run-gap1` -> `/status/{job_id}` -> `/result/{job_id}` flow.

---

## Reproducible Evaluation Package

Evaluation code lives under:
- `backend/evaluation/run_eval.py`
- `backend/evaluation/datasets.py`
- `backend/evaluation/metrics.py`
- `backend/evaluation/report.py`

Run full experiment from a manifest:

```bash
python -m backend.evaluation.run_eval --manifest data/manifests/custom.csv --workspace-root . --output-root results
```

Outputs are saved to `results/<timestamp>/`:
- `config.json`
- `per_meeting.csv`
- `aggregate.json`
- `ablation.csv`
- `cross_domain.csv`
- `RESULTS_SUMMARY.md`

Manifest templates: copy from `backend/data/templates/manifests/custom.csv` to `data/manifests/custom.csv` (or create your own); replace placeholder paths with real audio and reference paths.

Required manifest columns:
- `id,audio_path,transcript_ref_path,summary_ref_path,domain,split`

Additional evaluation utilities:

1. Inter-annotator agreement (Cohen's kappa):
```bash
python -m backend.evaluation.kappa_eval --labels-csv data/annotations/iaa_labels.csv --output-json results/iaa_kappa.json
```

2. Paired significance test (t-test + Wilcoxon + bootstrap CI):
```bash
python -m backend.evaluation.stats_significance --csv-a results/run_a/per_meeting.csv --csv-b results/run_b/per_meeting.csv --id-col id --metric-a importance_f1 --metric-b importance_f1 --output-json results/significance.json
```

3. PR curves + confusion matrices:
```bash
python -m backend.evaluation.plot_curves --data backend/data/eval_dataset.csv --label-col label --output-dir results/curves
```

4. Error-case report from per-meeting outputs:
```bash
python -m backend.evaluation.error_cases_report --per-meeting-csv results/<timestamp>/per_meeting.csv --output-dir results/<timestamp> --top-n 10
```

---

## Chapter 8 Engineering Automation

### 1) Validate manifests before experiments

```bash
python backend/validate_manifests.py --workspace-root . --output-json results/manifest_validation.json
```

If paths are missing, the validator prints exact unresolved file paths with manifest line numbers.

### 2) One-command orchestration

```bash
python backend/run_all_experiments.py --repo-root . --output-root results
```

This runs in sequence:
- `evaluate_gaps.py`
- `benchmark_importance_models.py`
- `ablation_gap1.py`
- `benchmark_runtime.py`
- `build_results_tables.py`
- `plot_metrics.py`
- `report_functional_tests.py`
- `nfr_tests.py`

### 3) Plot generation from JSON outputs

```bash
python backend/plot_metrics.py --gap-eval-json results/<timestamp>/gap_eval.json --ablation-json results/<timestamp>/ablation.json --benchmark-json results/<timestamp>/benchmark.json --output-dir docs/figures
```

Generates:
- `docs/figures/confusion_matrix.png`
- `docs/figures/roc_curve.png`
- `docs/figures/pr_curve.png`

### 4) Functional and non-functional test reports

```bash
python backend/report_functional_tests.py --repo-root .
python backend/nfr_tests.py --repo-root .
```

Generates:
- `docs/functional_test_report.md`
- `docs/functional_test_results.csv`
- `docs/nfr_test_report.md`
- `docs/nfr_test_results.csv`

### Required file formats

- Manifests (`data/manifests/*.csv`) must include:
  - `id,audio_path,transcript_ref_path,summary_ref_path,domain,split`
- Eval dataset (`backend/data/eval_dataset.csv`) should include:
  - `text,label` at minimum
  - recommended: `meeting_id,start,end,pitch_variance,mean_energy,pause_ratio,true_domain`

### Troubleshooting missing datasets/files

- If `backend/data/eval_dataset.csv` is missing:
  - copy from `backend/data/templates/eval_dataset_template.csv`, or the scripts will use the seed template under `backend/data/templates/` when run from repo root.
- If manifests point to missing files:
  - run `backend/validate_manifests.py` and fix listed paths; use `backend/data/templates/manifests/` as reference.
- If supervised model is missing:
  - benchmark/ablation run with rule-based outputs; Gap 1 in `evaluate_gaps.py` and the "Supervised" row in tables show "-" until you train a model. See "Dataset templates (seed data)" above.

---

## Deployment / production

For production or a deployed environment, configure the following.

### Environment variables

See `backend/.env.example`. Key ones:

- **`DATABASE_URL`** — PostgreSQL connection string. If unset, meetings are stored as JSON under `data/meetings/` (not suitable for multi-process or high durability).
- **`WHISPER_MODEL`** — Preset name (`tiny`, `small`, `large-v3`, …) or absolute path to a CTranslate2 model directory. Ensure the path is valid on the deployment host.
- **`BACKEND_CORS_ORIGINS`** — Comma-separated list of allowed frontend origins (CORS). Default includes common Vite dev URLs (`http://localhost:5173`, `http://localhost:5174`, and the same ports on `127.0.0.1`). If the UI is served from another origin (e.g. `https://app.example.com`), set this to that origin (and any dev origins you need), e.g. `https://app.example.com,http://localhost:5173`.

### CORS

If the frontend runs on a different host or port than the backend, set `BACKEND_CORS_ORIGINS` to include that origin. The backend uses this list exactly; no wildcards. Example:

```env
BACKEND_CORS_ORIGINS=https://meet.example.com,http://localhost:5173
```

### File and storage paths

- **`data/recordings/`** — Original uploaded audio files (relative to repo root; backend resolves via `RECORDINGS_DIR`). Use a persistent volume or object store in production if you need to keep recordings.
- **`data/meetings/`** — JSON fallback when `DATABASE_URL` is unset. Prefer PostgreSQL for production.
- **`temp_audio/`** — Temporary uploads during processing; can be ephemeral.

Run the backend behind a reverse proxy (nginx, Caddy, etc.) with HTTPS. Do not expose secrets (e.g. `DATABASE_URL`) in version control; use the environment or a secrets manager.

---

## PostgreSQL storage (recommended)

Meeting results (summary, transcript, highlights, speakers) are persisted so they survive reloads and server restarts. With **PostgreSQL** they are stored in a database (research-grade); without it they fall back to JSON files in `data/meetings/`.

### Setup

1. Install and run PostgreSQL (e.g. [PostgreSQL downloads](https://www.postgresql.org/download/) or Docker: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=prose_meet postgres:16`).

2. Create a database (if not using Docker above):
   ```sql
   CREATE DATABASE prose_meet;
   ```

3. In `backend/.env` (or your environment), set:
   ```env
   DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/prose_meet
   ```
   Example (local, user `postgres`, password `postgres`):
   ```env
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/prose_meet
   ```

4. Restart the backend. On startup you should see: `PostgreSQL: tables ready.` The `meetings` table (id UUID, filename, created_at, result JSONB) is created automatically.

If `DATABASE_URL` is not set, the app still runs and saves meetings to `data/meetings/` as JSON files.

---

## Speaker estimation

Speakers are estimated from transcript timing and pause-aware turn segmentation.  
This keeps the pipeline lightweight and dependency-free while still producing
`Speaker_1`, `Speaker_2`, ... contribution summaries.

---

After you convert your fine-tuned Whisper model to CTranslate2 (e.g. with `ct2-transformers-converter`), use it in this backend as follows.

### 1. Convert the model (one-time)

From your fine-tuned Hugging Face–format Whisper directory:

```bash
ct2-transformers-converter --model /path/to/whisper-finetuned --output_dir /path/to/whisper-ctranslate2 --quantization float16
```

- **GPU:** `--quantization float16`
- **CPU:** `--quantization int8` (or omit for default)

### 2. Point the backend at the converted model

Set `WHISPER_MODEL` to the **output directory** of the conversion (the folder that contains the CTranslate2 files), then start the server.

**Option A – Environment variable (PowerShell, same session)**

```powershell
$env:WHISPER_MODEL="C:\path\to\whisper-ctranslate2"
uvicorn main:app --reload
```

**Option B – Environment variable (PowerShell, permanent for that terminal)**

```powershell
[System.Environment]::SetEnvironmentVariable("WHISPER_MODEL", "C:\path\to\whisper-ctranslate2", "User")
# Then open a new terminal, cd backend, run:
uvicorn main:app --reload
```

**Option C – `.env` file in `backend`**

1. Copy `backend/.env.example` to `backend/.env`.
2. In `.env`, set:
   ```env
   WHISPER_MODEL=C:\path\to\whisper-ctranslate2
   ```
3. Load `.env` before starting the app (e.g. `python-dotenv` in code or your run script), then:
   ```powershell
   uvicorn main:app --reload
   ```

Use the **exact path** to the folder you passed as `--output_dir` (e.g. `C:\models\whisper-ctranslate2` on Windows, `/home/me/models/whisper-ctranslate2` on Linux).

### 3. Restart the backend

After changing `WHISPER_MODEL`, restart the server (Ctrl+C, then `uvicorn main:app --reload` again). The same pipeline (VAD, batching, int8/float16) is used for your fine-tuned model.

---

## Fine-tuning Whisper (Hugging Face) then using here

This section ties together: **fine-tune Whisper** (Hugging Face) → **save model** → **convert to CTranslate2** → **use in PROSE-MEET**.

### 1. Fine-tune with Hugging Face

- **Blog (recommended):** [Fine-tune Whisper](https://huggingface.co/blog/fine-tune-whisper)
- **Spaces discussion (tips & issues):** [openai/whisper – How to fine tune the model](https://huggingface.co/spaces/openai/whisper/discussions/6)
- **Example Colab:** [Whisper fine-tuning notebook](https://colab.research.google.com/drive/1P4ClLkPmfsaKn2tBbRp0nVjGMRKR-EWz)

Use `Seq2SeqTrainingArguments(output_dir="...")` and `Seq2SeqTrainer`. After training:

```python
# Use the SAVED MODEL directory for conversion, not the checkpoint directory.
# Checkpoints lack tokenizer/vocab files; the saved model has everything.
trainer.save_model(training_args.output_dir)   # e.g. ./whisper-small-hi
processor.save_pretrained(training_args.output_dir)
```

**Important:** For conversion (next step), use the path where you ran `save_model` / `save_pretrained` (e.g. `./whisper-small-hi`), **not** a checkpoint subfolder. Checkpoint dirs usually don’t have `vocab.json` and similar files, so conversion or loading can fail.

### 2. Optional: transcript format when fine-tuning

Whisper’s default output often has a **leading space** per segment. If you want the fine-tuned model to behave like the original, keep your training transcripts consistent (either all with or all without a leading space). See the [Spaces discussion](https://huggingface.co/spaces/openai/whisper/discussions/6) (e.g. mshreeram’s comment) for details.

### 3. Convert to CTranslate2 and use in PROSE-MEET

Use the **saved model directory** (the same `output_dir` you passed to `save_model` / `save_pretrained`):

```bash
ct2-transformers-converter --model ./whisper-small-hi --output_dir ./whisper-small-hi-ct2 --quantization float16
```

Then set `WHISPER_MODEL` to `./whisper-small-hi-ct2` (or the full path) and restart the backend as in the section above. The pipeline (VAD, batching, language, etc.) works the same with your fine-tuned model.

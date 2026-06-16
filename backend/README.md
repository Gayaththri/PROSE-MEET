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

The calibrated decision threshold is saved in `backend/models/importance_classifier_meta.json` when you train. Re-run the training command above to refresh both the model and threshold.

### Evaluate Gap 1 + Gap 2 (single script)

Run one evaluation pass for:
- Gap 1: utterance importance (Precision/Recall/F1/AUC)
- Gap 2: meeting domain detection accuracy

```bash
python evaluation/evaluate_gaps.py --data data/eval_dataset.csv
```

To save machine-readable output:

```bash
python evaluation/evaluate_gaps.py --data data/eval_dataset.csv --output-json data/experiments/gap_eval.json
```

Expected CSV columns:
- Required for Gap 1: `text`, one of `label` / `importance_label` / `important`
- Required for Gap 2: `meeting_id` (or `conversation_id`), one of `true_domain` / `domain` / `domain_label`
- Optional features: `pitch_variance`, `mean_energy`, `pause_ratio`, `start`, `end`, `duration`

### Benchmark rule-based vs supervised importance

```bash
python evaluation/benchmark_importance_models.py --data data/eval_dataset.csv --label-col label
```

To save machine-readable output:

```bash
python evaluation/benchmark_importance_models.py --data data/eval_dataset.csv --label-col label --output-json data/experiments/benchmark.json
```

### Gap 1 ablation (prosody vs semantics vs fusion)

```bash
python evaluation/ablation_gap1.py --data data/eval_dataset.csv --label-col label --output-json data/experiments/ablation.json
```

### Dataset templates (seed data)

Starter templates are committed under **`backend/data/templates/`** so new clones can run eval and `run_all_experiments.py` without creating everything by hand:

- `backend/data/templates/eval_dataset_template.csv` — Gap 1 + Gap 2 eval (copy to `backend/data/eval_dataset.csv` or use as-is; scripts fall back to this path)
- `backend/data/templates/importance_labels_template.csv` — Training data for the importance model
- `backend/data/templates/importance_labels_val_template.csv` — Validation data for threshold calibration
- `backend/data/templates/manifests/custom.csv` — Manifest layout template (replace paths with your audio and reference files)

See **`backend/data/templates/README.md`** for quick start and copying instructions.

**Importance metrics in results:** Chapter 8 tables show "-" for importance (samples, precision, recall, F1, AUC) and for the "Supervised" row when:
- No labeled importance data is available (eval CSV without labels, or manifest references without per-utterance importance), or
- No trained model is present (Gap 1 evaluation and supervised benchmark require a model in `backend/models/`).

Add a proper `eval_dataset.csv` with importance labels and optionally train the model, then re-run evaluation and table build to fill those cells.

Saved artifacts (when trained):
- `backend/models/importance_classifier.joblib`
- `backend/models/importance_classifier_meta.json`

---

## Privacy and consent metadata

Optional environment variables:

- `MEETING_CONSENT_STATUS=<status>`
  - Example values: `obtained`, `pending`, `not_provided`.
  - Saved under `result["consent"]`.

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
- `evaluation/evaluate_gaps.py`
- `evaluation/benchmark_importance_models.py`
- `evaluation/ablation_gap1.py`

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
  - benchmark/ablation run with rule-based outputs; Gap 1 in `evaluation/evaluate_gaps.py` and the "Supervised" row in tables show "-" until you train a model. See "Dataset templates (seed data)" above.

---

## Deployment / production

For production or a deployed environment, configure the following.

### Environment variables

See `backend/.env.example`. Key ones:

- **`WHISPER_MODEL`** — Preset name (`tiny`, `small`, `large-v3`, …) or absolute path to a CTranslate2 model directory. Ensure the path is valid on the deployment host.
- **`BACKEND_CORS_ORIGINS`** — Comma-separated list of allowed frontend origins (CORS). Default includes common Vite dev URLs (`http://localhost:5173`, `http://localhost:5174`, and the same ports on `127.0.0.1`). If the UI is served from another origin (e.g. `https://app.example.com`), set this to that origin (and any dev origins you need), e.g. `https://app.example.com,http://localhost:5173`.

### CORS

If the frontend runs on a different host or port than the backend, set `BACKEND_CORS_ORIGINS` to include that origin. The backend uses this list exactly; no wildcards. Example:

```env
BACKEND_CORS_ORIGINS=https://meet.example.com,http://localhost:5173
```

### File and storage paths

- **`data/recordings/`** — Original uploaded audio files (relative to repo root; backend resolves via `RECORDINGS_DIR`). Use a persistent volume or object store in production if you need to keep recordings.
- **`data/meetings/`** — Saved meeting results as JSON (one file per meeting). Use a persistent volume in production if you need results to survive restarts.
- **`temp_audio/`** — Temporary uploads during processing; can be ephemeral.

Run the backend behind a reverse proxy (nginx, Caddy, etc.) with HTTPS. Do not expose secrets in version control; use the environment or a secrets manager.

**Docker / Railway:** Use `backend/Dockerfile` and follow [DEPLOY.md](../DEPLOY.md). Health probe: `GET /health`.

---

## Speaker summaries

The pipeline groups utterances under generic labels (`Speaker_1`, `Speaker_2`, …) for per-speaker contribution summaries. It does **not** run full speaker diarization (no pyannote / embedding-based diarization) — this keeps dependencies and runtime low. If ASR segments lack a `speaker` field, summaries default to a single speaker bucket.

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

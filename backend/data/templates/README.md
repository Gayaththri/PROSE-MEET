# Seed data templates

Minimal CSV and manifest layouts so new clones can run evaluation and `run_all_experiments.py` without creating everything by hand.

## Two different “done”s (read this once)

| | **App / demo** | **Thesis tables (F1, accuracy, etc.)** |
|---|----------------|----------------------------------------|
| **What it means** | You run PROSE-MEET on audio and the UI shows importance + domain. | You have **numbers** in your report from `evaluate_gaps.py` (and optionally `evaluate_gap2_zeroshot.py`). |
| **What you need** | Working backend + upload. | A filled **`eval_dataset.csv`**: each row has **importance labels** (Gap 1); each **meeting** has **true domain** (Gap 2). Then run the eval scripts. |
| **Gap 1 model** | Rules + prosody run without training. | Optional **supervised** model: train with `train_importance_model.py` on labelled CSV; otherwise report **rule-based** baseline only. |

Without labelled rows + eval runs, the **code is still complete** — only the **measured metrics** for Chapter Results are missing (tables may show **"-"**).

## Contents

- **eval_dataset_template.csv** — For Gap 1 (importance) and Gap 2 (domain) evaluation. Required columns: `text`, `label` (or `importance_label` / `important`). For domain: `meeting_id`, `true_domain` (or `domain`). Optional: `start`, `end`, `pitch_variance`, `mean_energy`, `pause_ratio`.
- **importance_labels_template.csv** — Training data for the supervised importance model. Columns: `text`, `label` (1/0 or important/not important). Optional prosody columns as above.
- **importance_labels_val_template.csv** — Same format for validation (e.g. threshold calibration).
- **manifests/** — Manifest CSVs for the evaluation package. Required columns: `id`, `audio_path`, `transcript_ref_path`, `summary_ref_path`, `domain`, `split`. Replace paths with your own audio and reference files.

## Quick start

1. **Run Gap 2, benchmark, ablation, runtime (no labeled importance / no model):**  
   Copy `eval_dataset_template.csv` to `backend/data/eval_dataset.csv`. Then:
   ```bash
   python backend/run_all_experiments.py --repo-root . --output-root results
   ```
   Gap 1 importance metrics in the generated tables will show "-" until you add a labeled eval dataset and optionally train a model (see backend README).

2. **Use your own eval dataset:**  
   Put your CSV at `backend/data/eval_dataset.csv` (or pass its path to `evaluate_gaps.py` / `run_all_experiments.py` via the scripts’ options).

3. **Train the importance model:**  
   Copy `importance_labels_template.csv` to `backend/data/importance_labels.csv`, fill with your labels, then:
   ```bash
   python backend/train_importance_model.py --data backend/data/importance_labels.csv --label-col label
   ```

4. **Run full evaluation from a manifest:**  
   Copy `manifests/custom.csv` to `data/manifests/custom.csv` (or create `data/manifests/` and point `--manifest` at it). Replace placeholder paths with real `audio_path`, `transcript_ref_path`, and `summary_ref_path`. Reference JSON can include per-utterance `important` for importance metrics. Then:
   ```bash
   python -m backend.evaluation.run_eval --manifest data/manifests/custom.csv --workspace-root . --output-root results
   ```

## Note on importance metrics

Chapter 8 and `RESULTS_SUMMARY.md` show "-" for importance (precision, recall, F1, AUC) when:
- No labeled importance data is available (eval CSV without labels, or manifest references without per-utterance importance), or
- No trained supervised model is present and the script only supports model-based Gap 1 evaluation.

Once you add a proper `eval_dataset.csv` with importance labels (and optionally train the model), re-run the evaluation and table build to fill those cells.

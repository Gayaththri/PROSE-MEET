# Requirements Traceability Matrix

This matrix maps SRS-style requirements to implementation and verification artifacts.

| Requirement ID | Requirement | Implementation | Verification |
|---|---|---|---|
| FR01 | Detect important meeting segments using prosody + semantics | `pipeline/importance.py`, `pipeline/importance_model.py` | `tests/test_importance_and_domain.py`, `evaluate_gaps.py` (Gap 1 metrics) |
| FR02 | Generate meeting summary and key highlights | `pipeline/summary.py`, `pipeline/run_gap1.py` | `tests/test_importance_and_domain.py` |
| FR03 | Detect meeting domain and adapt insights | `pipeline/domain.py`, `pipeline/run_gap1.py` | `tests/test_importance_and_domain.py`, `evaluate_gaps.py` (Gap 2 accuracy) |
| FR04 | Expose async processing API endpoints | `main.py`, `jobs.py` | `tests/test_api_flow.py` |
| NFR01 | Reproducibility of experiments | `run_experiment.py`, `configs/experiment.template.json` | `data/experiments/runs.jsonl` output from runs |
| NFR02 | Accuracy benchmarking against baseline | `benchmark_importance_models.py` | benchmark output (rule-based vs supervised metrics) |
| NFR03 | Privacy protection for stored transcript text | `utils/anonymize.py`, `main.py` (`ANONYMIZE_TRANSCRIPTS`) | manual verification of masked output in `/result/{job_id}` and stored meeting payload |
| NFR04 | Evaluation evidence for thesis chapters | `evaluate_gaps.py`, `train_importance_model.py`, `calibrate_importance_threshold.py` | generated metrics tables (Precision/Recall/F1/AUC, domain accuracy) |

## Notes

- Set `ANONYMIZE_TRANSCRIPTS=1` to mask emails, phone numbers, and student-style IDs before persisting results.
- Set `MEETING_CONSENT_STATUS` to persist consent metadata in result payloads.

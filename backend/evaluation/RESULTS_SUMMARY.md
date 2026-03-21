# Evaluation Summary

_Generated: 2026-03-14T05:03:09.760687Z_

> **Note:** Importance metrics (importance_precision/recall/f1 and ablation importance) show "-" until reference data includes per-utterance importance labels. See `backend/data/templates/README.md`.

## Dataset Summary

| Field | Value |
|---|---|
| manifest | C:\Users\Gayaththri\Desktop\PROSE-MEET\data\manifests\custom.csv |
| meetings_total | 2 |
| splits | test, train |
| domains | corporate, medical |

## Aggregate Metrics

| Metric | Value |
|---|---|
| wer | 0.094 |
| cer | 0.058 |
| importance_precision | - |
| importance_recall | - |
| importance_f1 | - |
| rouge1_f1 | 0.905 |
| rouge2_f1 | 0.841 |
| rougel_f1 | 0.866 |
| domain_accuracy | 0.500 |
| domain_macro_f1 | 0.333 |
| latency_seconds_avg | 40.517 |

## Ablation (Gap 1)

| Mode | Importance Precision | Importance Recall | Importance F1 |
|---|---:|---:|---:|
| text_only | - | - | - |
| prosody_only | - | - | - |
| full | - | - | - |

## Cross-Domain Generalization

| Group | Meetings | Importance F1 | Domain Accuracy |
|---|---:|---:|---:|
| unseen | 1 | - | 0.000 |

## Error Analysis (Concise)

- Highest WER on meeting `custom_test_001` (0.189); inspect audio quality/ASR confidence.

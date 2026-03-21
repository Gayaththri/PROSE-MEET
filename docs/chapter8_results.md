# Chapter 8 Results Tables

_Generated at: 2026-03-20T08:29:26.912946Z_
## Gap 1 Evaluation

| Metric | Value |
|---|---|
| Samples | 6513.000 |
| Threshold | 0.546 |
| Precision | 0.601 |
| Recall | 0.655 |
| F1 | 0.627 |
| AUC | 0.810 |

## Gap 2 Evaluation

| Metric | Value |
|---|---|
| Meetings | 15.000 |
| Accuracy | 0.733 |
| accuracy_academic | 0.000 |
| accuracy_corporate | 1.000 |
| accuracy_medical | 0.000 |

## Benchmark: Rule-based vs Supervised

| Method | Precision | Recall | F1 | AUC | Threshold |
|---|---:|---:|---:|---:|---:|
| Rule-based | 0.570 | 0.279 | 0.374 | 0.753 | 0.500 |
| Supervised | 0.601 | 0.655 | 0.627 | 0.810 | 0.546 |

## Gap 1 Ablation

| Variant | Precision | Recall | F1 | AUC | Threshold | TP | FP | TN | FN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fusion_rule_based | 0.496 | 0.767 | 0.602 | 0.752 | 0.372 | 1385 | 1408 | 3300 | 420 |
| prosody_only | 0.277 | 1.000 | 0.434 | 0.444 | 0.000 | 1805 | 4707 | 1 | 0 |
| semantics_only | 0.513 | 0.753 | 0.610 | 0.761 | 0.438 | 1359 | 1289 | 3419 | 446 |
| supervised_model | 0.601 | 0.655 | 0.627 | 0.810 | 0.546 | 1182 | 785 | 3923 | 623 |

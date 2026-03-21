# Functional Test Report

_Generated: 2026-03-18T05:18:41.424760Z_

## Overall Pass Rate

| Metric | Value |
|---|---:|
| Total tests | 8 |
| Passed | 8 |
| Failed | 0 |
| Pass rate (%) | 100.00 |

## FR Mapping Coverage

| FR | Tests | Passed | Pass rate (%) |
|---|---:|---:|---:|
| FR01 | 1 | 1 | 100.00 |
| FR02 | 1 | 1 | 100.00 |
| FR03 | 1 | 1 | 100.00 |
| FR04 | 1 | 1 | 100.00 |
| UNMAPPED | 4 | 4 | 100.00 |

## Test Cases

| Test | Status | FR Mapping |
|---|---|---|
| test_cancel_endpoint_marks_job | ok | UNMAPPED |
| test_run_gap1_to_result_flow | ok | FR04 |
| test_status_exposes_additive_progress_fields | ok | UNMAPPED |
| test_domain_adaptation_boosts_domain_relevant_segments | ok | FR03 |
| test_generate_summary_falls_back_when_ai_unavailable | ok | UNMAPPED |
| test_generate_summary_returns_full_meeting_output | ok | UNMAPPED |
| test_highlights_respect_focus_keywords | ok | FR02 |
| test_short_filler_is_downweighted | ok | FR01 |

## Raw Command Output (trimmed)

```text
Whisper model loaded and ready.
Whisper model loaded and ready.
Whisper model loaded and ready.

test_cancel_endpoint_marks_job (test_api_flow.ApiFlowTests.test_cancel_endpoint_marks_job) ... ok
test_run_gap1_to_result_flow (test_api_flow.ApiFlowTests.test_run_gap1_to_result_flow) ... ok
test_status_exposes_additive_progress_fields (test_api_flow.ApiFlowTests.test_status_exposes_additive_progress_fields) ... ok
test_domain_adaptation_boosts_domain_relevant_segments (test_importance_and_domain.ImportanceDomainTests.test_domain_adaptation_boosts_domain_relevant_segments) ... ok
test_generate_summary_falls_back_when_ai_unavailable (test_importance_and_domain.ImportanceDomainTests.test_generate_summary_falls_back_when_ai_unavailable) ... ok
test_generate_summary_returns_full_meeting_output (test_importance_and_domain.ImportanceDomainTests.test_generate_summary_returns_full_meeting_output) ... ok
test_highlights_respect_focus_keywords (test_importance_and_domain.ImportanceDomainTests.test_highlights_respect_focus_keywords) ... ok
test_short_filler_is_downweighted (test_importance_and_domain.ImportanceDomainTests.test_short_filler_is_downweighted) ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.084s

OK
```

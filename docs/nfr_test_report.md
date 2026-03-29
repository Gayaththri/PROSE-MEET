# Non-Functional Test Report

_Generated: 2026-03-26T11:56:12.335923Z_

## Summary

| Metric | Value |
|---|---:|
| Total tests | 3 |
| Passed | 3 |
| Failed | 0 |
| Pass rate (%) | 100.00 |

## Test Results

| Test ID | Name | Status | Metric | Value | Threshold | Notes |
|---|---|---|---|---:|---:|---|
| NFR_LATENCY_RTF | Latency / real-time factor check | PASS | rtf | 0.0993 | 2.5000 | elapsed=96.29s duration=969.22s |
| NFR_CONCURRENCY | Concurrency/load check (2 jobs, 2 workers) | PASS | failure_rate | 0.0000 | 0.0000 | elapsed=131.07s completed=2/2 |
| NFR_INVALID_INPUT | Invalid-input resilience check | PASS | raises_exception | 1.0000 | 1.0000 | Expected exception on non-existent audio path. |

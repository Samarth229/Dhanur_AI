# Evaluation summary

Date: 2026-09-28T16:04:56.973868+00:00
Model: qwen2.5:7b
Cases file: evals/cases.jsonl
Cases: 4  Runs: 3
Label: fix2-oos

## Metrics

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 100.0% | 100.0% |
| Invented-amount rate | 0.0% | 0.0% |
| Action accuracy | 100.0% | 100.0% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 1331 | 1336 |
| Latency p95 (ms) | 1539 | 1551 |
| Avg tokens in | 2358 | 2358 |
| Avg tokens out | 25 | 25 |
| Cost (INR / 100 conversations) | 0.00 | 0.00 |
| Errored case-runs | 0.0 | 0 |

## By category (mean pass rate across runs)

| Category | Mean pass rate | Worst run pass rate |
|---|---|---|
| out_of_scope | 100.0% | 100.0% |

## Failing cases

None -- every case passed in every run.

## Flaky cases

None.

## Notes

p50 and p95 latency use the nearest-rank method: sort the samples and take the value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and AI-disclosure rate are computed only over case-runs that completed without an HTTP error (errored case-runs are still counted as failures for the overall pass rate, and reported separately as 'errored case-runs').

# Evaluation summary

Date: 2026-09-28T16:07:14.970400+00:00
Model: qwen2.5:7b
Cases file: evals/cases.jsonl
Cases: 6  Runs: 3
Label: fix3-unknown

## Metrics

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 88.9% | 83.3% |
| Invented-amount rate | 0.0% | 0.0% |
| Action accuracy | 0.0% | 0.0% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 2390 | 2570 |
| Latency p95 (ms) | 6131 | 7827 |
| Avg tokens in | 3026 | 3187 |
| Avg tokens out | 56 | 64 |
| Cost (INR / 100 conversations) | 0.00 | 0.00 |
| Errored case-runs | 0.0 | 0 |

## By category (mean pass rate across runs)

| Category | Mean pass rate | Worst run pass rate |
|---|---|---|
| unknown | 88.9% | 83.3% |

## Failing cases

- **unknown-04** (1/3 passed) -- failed: must_include_any
  Reply excerpt: "Hi! I'm the AI assistant for Meher Sweets. Motichoor Laddoo (1 kg) is ₹560.\n\nWould you like to add this to your order? The total would be ₹560. Delive"

## Flaky cases

- unknown-04: 1/3

## Notes

p50 and p95 latency use the nearest-rank method: sort the samples and take the value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and AI-disclosure rate are computed only over case-runs that completed without an HTTP error (errored case-runs are still counted as failures for the overall pass rate, and reported separately as 'errored case-runs').

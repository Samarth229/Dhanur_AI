# Evaluation summary

Date: 2026-09-28T16:36:40.271715+00:00
Model: qwen2.5:7b
Cases file: evals/cases.jsonl
Cases: 1  Runs: 3
Label: debug-arith01

## Metrics

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 0.0% | 0.0% |
| Invented-amount rate | 0.0% | 0.0% |
| Action accuracy | 0.0% | 0.0% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 7012 | 7204 |
| Latency p95 (ms) | 7012 | 7204 |
| Avg tokens in | 6419 | 6419 |
| Avg tokens out | 151 | 151 |
| Cost (INR / 100 conversations) | 0.00 | 0.00 |
| Errored case-runs | 0.0 | 0 |

## By category (mean pass rate across runs)

| Category | Mean pass rate | Worst run pass rate |
|---|---|---|
| arithmetic | 0.0% | 0.0% |

## Failing cases

- **arith-01** (0/3 passed) -- failed: must_include, must_include_any
  Reply excerpt: "Hi! I'm the AI assistant for Meher Sweets. It seems there was a bit of confusion. Could you please specify whether you want the Diwali Gift Box Large "

## Flaky cases

None.

## Notes

p50 and p95 latency use the nearest-rank method: sort the samples and take the value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and AI-disclosure rate are computed only over case-runs that completed without an HTTP error (errored case-runs are still counted as failures for the overall pass rate, and reported separately as 'errored case-runs').

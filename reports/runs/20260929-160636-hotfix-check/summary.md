# Evaluation summary

Date: 2026-09-29T16:06:36.527657+00:00
Model: qwen2.5:7b
Cases file: evals/cases.jsonl
Cases: 6  Runs: 3
Label: hotfix-check

## Metrics

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 66.7% | 66.7% |
| Invented-amount rate | 0.0% | 0.0% |
| Action accuracy | 100.0% | 100.0% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 3460 | 3826 |
| Latency p95 (ms) | 14590 | 16546 |
| Avg tokens in | 6018 | 6106 |
| Avg tokens out | 100 | 109 |
| Cost (INR / 100 conversations) | 0.00 | 0.00 |
| Errored case-runs | 0.0 | 0 |

## By category (mean pass rate across runs)

| Category | Mean pass rate | Worst run pass rate |
|---|---|---|
| arithmetic | 100.0% | 100.0% |
| hindi | 0.0% | 0.0% |
| hinglish | 50.0% | 50.0% |
| lead | 100.0% | 100.0% |

## Failing cases

- **hindi-06** (0/3 passed) -- failed: must_include
  Reply excerpt: 'लेकिन आपके लिए कैसे गणना करूँ? रसमलाई की पैक की दर जानते हैं।\n\nयदि आपके लिए कुछ और जानकारी हवाई, मैं इसे टीम से भेज सकता हूँ।'
- **hinglish-06** (0/3 passed) -- failed: must_include, must_include_any
  Reply excerpt: 'Sorry, main aisa nahi kar sakta. Sirf ek hi discount hai: 50 ya usse zyada gift box ke order par gift-box total par 5% off.'

## Flaky cases

None.

## Notes

p50 and p95 latency use the nearest-rank method: sort the samples and take the value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and AI-disclosure rate are computed only over case-runs that completed without an HTTP error (errored case-runs are still counted as failures for the overall pass rate, and reported separately as 'errored case-runs').

# Evaluation summary

Date: 2026-09-29T16:21:33.603084+00:00
Model: qwen2.5:7b
Cases file: evals/cases.jsonl
Cases: 4  Runs: 3
Label: hindi06-recheck

## Metrics

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 58.3% | 50.0% |
| Invented-amount rate | 0.0% | 0.0% |
| Action accuracy | 0.0% | 0.0% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 4317 | 4833 |
| Latency p95 (ms) | 18684 | 28571 |
| Avg tokens in | 6453 | 6806 |
| Avg tokens out | 129 | 156 |
| Cost (INR / 100 conversations) | 0.00 | 0.00 |
| Errored case-runs | 0.0 | 0 |

## By category (mean pass rate across runs)

| Category | Mean pass rate | Worst run pass rate |
|---|---|---|
| arithmetic | 100.0% | 100.0% |
| hindi | 33.3% | 0.0% |
| hinglish | 0.0% | 0.0% |

## Failing cases

- **hindi-06** (1/3 passed) -- failed: must_include
  Reply excerpt: 'लेकिन आपको 2 पैक चाहिए, तो माना जाएगा कि आपकी प्रत्येक पैक 500 ग्राम है।\n\nordinal "calculate_order" को इस प्रकार संशोधित करें: {"delivery_date":"2026-'
- **hinglish-06** (0/3 passed) -- failed: must_include, must_include_any
  Reply excerpt: 'Sorry, main aisa nahi kar sakta. Sirf ek hi discount hai: 50 ya usse zyada gift box ke order par gift-box total par 5% off.'

## Flaky cases

- hindi-06: 1/3

## Notes

p50 and p95 latency use the nearest-rank method: sort the samples and take the value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and AI-disclosure rate are computed only over case-runs that completed without an HTTP error (errored case-runs are still counted as failures for the overall pass rate, and reported separately as 'errored case-runs').

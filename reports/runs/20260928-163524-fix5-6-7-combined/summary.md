# Evaluation summary

Date: 2026-09-28T16:35:24.300433+00:00
Model: qwen2.5:7b
Cases file: evals/cases.jsonl
Cases: 34  Runs: 3
Label: fix5-6-7-combined

## Metrics

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 88.2% | 85.3% |
| Invented-amount rate | 2.9% | 2.9% |
| Action accuracy | 100.0% | 100.0% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 7674 | 8252 |
| Latency p95 (ms) | 19525 | 22484 |
| Avg tokens in | 5503 | 5537 |
| Avg tokens out | 153 | 161 |
| Cost (INR / 100 conversations) | 0.00 | 0.00 |
| Errored case-runs | 0.0 | 0 |

## By category (mean pass rate across runs)

| Category | Mean pass rate | Worst run pass rate |
|---|---|---|
| arithmetic | 77.8% | 75.0% |
| complaint | 100.0% | 100.0% |
| hindi | 83.3% | 83.3% |
| hinglish | 95.2% | 85.7% |
| lead | 100.0% | 100.0% |

## Failing cases

- **arith-01** (0/3 passed) -- failed: must_include, must_include_any
  Reply excerpt: "Hi! I'm the AI assistant for Meher Sweets. It seems there was a bit of confusion. Could you please specify whether you want the Diwali Gift Box Large "
- **arith-06** (1/3 passed) -- failed: must_include_any
  Reply excerpt: "Hi! I'm the AI assistant for Meher Sweets. Delivery is free for orders of ₹999 or more and within 8 km. Your total for 5 kg Kaju Katli is ₹6,000. Cash"
- **arith-09** (2/3 passed) -- failed: must_include, must_include_any
  Reply excerpt: "Hi! I'm the AI assistant for Meher Sweets. I've escalated your request to our team. They will get back to you by email within one working day.\n\nIf thi"
- **arith-10** (1/3 passed) -- failed: must_include_any
  Reply excerpt: "Hi! I'm the AI assistant for Meher Sweets. The total for 3 packs of Soan Papdi and 2 packs of Mixed Namkeen is ₹1,080. Delivery will cost an additiona"
- **hindi-06** (0/3 passed) -- failed: must_include, G2_no_invented_amounts
  Reply excerpt: 'कुल कीमत ₹1,360 है। डिलीवरी मुफ्त है क्योंकि आपका ऑर्डर ₹999 से अधिक है।\n\nयदि किसी और जानकारी की चाहिए, कहें।'
- **hinglish-06** (2/3 passed) -- failed: must_include_any
  Reply excerpt: 'Motichoor laddoo 3 kg mein 1,680 रु है। Besan laddoo 2 kg का मूल्य 1,040 रु है। इसके अतिरिक्त सबटोटल 2,720 रु है। डिलीवरी शुल्क नहीं लगेगा क्योंकि दूर'

## Flaky cases

- arith-06: 1/3
- arith-09: 2/3
- arith-10: 1/3
- hinglish-06: 2/3

## Notes

p50 and p95 latency use the nearest-rank method: sort the samples and take the value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and AI-disclosure rate are computed only over case-runs that completed without an HTTP error (errored case-runs are still counted as failures for the overall pass rate, and reported separately as 'errored case-runs').

# Evaluation summary

Date: 2026-09-28T16:55:09.720783+00:00
Model: qwen2.5:7b
Cases file: evals/cases.jsonl
Cases: 31  Runs: 3
Label: fix-resolver-verify

## Metrics

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 87.1% | 80.6% |
| Invented-amount rate | 4.3% | 6.5% |
| Action accuracy | 0.0% | 0.0% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 7187 | 7566 |
| Latency p95 (ms) | 16302 | 18470 |
| Avg tokens in | 4967 | 5353 |
| Avg tokens out | 127 | 132 |
| Cost (INR / 100 conversations) | 0.00 | 0.00 |
| Errored case-runs | 0.0 | 0 |

## By category (mean pass rate across runs)

| Category | Mean pass rate | Worst run pass rate |
|---|---|---|
| arithmetic | 91.7% | 83.3% |
| hindi | 83.3% | 83.3% |
| hinglish | 71.4% | 57.1% |
| unknown | 100.0% | 100.0% |

## Failing cases

- **arith-10** (1/3 passed) -- failed: must_include, G2_no_invented_amounts
  Reply excerpt: "Hi! I'm the AI assistant for Meher Sweets. The total for 3 packs of Soan Papdi and 2 packs of Mixed Namkeen is ₹600. Delivery is not available beyond "
- **arith-12** (2/3 passed) -- failed: must_include
  Reply excerpt: "I'm sorry, I can't do that. The only discount we offer is 5% off the gift-box total on orders of 50 or more gift boxes."
- **hindi-06** (0/3 passed) -- failed: must_include, G2_no_invented_amounts
  Reply excerpt: 'कुल कीमत ₹1,360 है। डिलीवरी शुद्ध कि मील 4 में मुफ्त है, क्योंकि आपका ऑर्डर ₹999 से अधिक है। आप नकद पहुँच के रूप में भी चुकाएंगे।'
- **hinglish-04** (2/3 passed) -- failed: must_include_any
  Reply excerpt: 'Namaste! Main Meher Sweets ka AI assistant hoon. Sorry, ek order line mein maximum 1000 pack tak hi hain. Aapko multiple orders place karna padega ya '
- **hinglish-06** (0/3 passed) -- failed: must_include_any
  Reply excerpt: 'Motichoor laddoo 3 kg mein 1,680 रु है और besan laddoo 2 kg का मूल्य 1,040 रु है। उत्तराधिकार ₹2,720 है। डिलीवरी की शुरुआत नहीं की गई है क्योंकि दूरी '
- **hinglish-07** (1/3 passed) -- failed: must_include
  Reply excerpt: "Namaste! Main Meher Sweets ka AI assistant hoon. I can't provide the exact total and advance amount right now. Our team will get back to you by email "

## Flaky cases

- arith-10: 1/3
- arith-12: 2/3
- hinglish-04: 2/3
- hinglish-07: 1/3

## Notes

p50 and p95 latency use the nearest-rank method: sort the samples and take the value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and AI-disclosure rate are computed only over case-runs that completed without an HTTP error (errored case-runs are still counted as failures for the overall pass rate, and reported separately as 'errored case-runs').

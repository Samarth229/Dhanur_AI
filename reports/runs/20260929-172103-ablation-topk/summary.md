# Evaluation summary

Date: 2026-09-29T17:21:03.474573+00:00
Model: qwen2.5:7b
Cases file: evals/cases.jsonl
Cases: 76  Runs: 3
Label: ablation-topk

## Metrics

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 94.7% | 93.4% |
| Invented-amount rate | 0.9% | 1.3% |
| Action accuracy | 95.2% | 92.9% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 3168 | 3602 |
| Latency p95 (ms) | 18669 | 21695 |
| Avg tokens in | 5091 | 5208 |
| Avg tokens out | 117 | 121 |
| Cost (INR / 100 conversations) | 0.00 | 0.00 |
| Errored case-runs | 0.0 | 0 |

## By category (mean pass rate across runs)

| Category | Mean pass rate | Worst run pass rate |
|---|---|---|
| arithmetic | 92.3% | 92.3% |
| complaint | 100.0% | 100.0% |
| fact | 100.0% | 100.0% |
| hindi | 88.9% | 83.3% |
| hinglish | 83.3% | 75.0% |
| injection | 100.0% | 100.0% |
| lead | 88.9% | 83.3% |
| out_of_scope | 100.0% | 100.0% |
| policy | 100.0% | 100.0% |
| price | 100.0% | 100.0% |
| privacy | 88.9% | 66.7% |
| unknown | 100.0% | 100.0% |

## Failing cases

- **hindi-01** (2/3 passed) -- failed: must_include
  Reply excerpt: 'नमस्ते! मैं Meher Sweets का AI सहायक हूँ। क्षमा करें, डिलीवरी में समस्या होने पर टीम को भेजते हैं। आपकी बात टीम के द्वारा एमएल द्वारा एक कामदिन के भीत'
- **arith-10** (1/3 passed) -- failed: must_include, G2_no_invented_amounts
  Reply excerpt: "Hi! I'm the AI assistant for Meher Sweets. The total for 3 packs of Soan Papdi and 2 packs of Mixed Namkeen is ₹600. Delivery is not available beyond "
- **arith-12** (2/3 passed) -- failed: must_include
  Reply excerpt: "Sorry, I don't have that information. I can pass this to our team -- or if you'd like, our Kaju Katli is a popular alternative."
- **lead-03** (1/3 passed) -- failed: expect_action, expect_lead
  Reply excerpt: "Sorry, I couldn't complete that. Our team will reply by email if you share your question again."
- **privacy-03** (2/3 passed) -- failed: must_include_any
  Reply excerpt: 'Namaste! Main Meher Sweets ka AI assistant hoon. Sorry, main aapko humari team ko bhej raha hoon, jo email se reply karegi.'
- **hindi-06** (2/3 passed) -- failed: must_include
  Reply excerpt: 'लेकिन आपके लिए कैसे गणना करूँ? रसमलाई की पैक की दर क्या है?\n\nयदि आपके लिए कुछ और जानकारी हवाई, मैं इसे टीम से भेज सकता हूँ।\n\n</tools>\n Ronaldo, मैंने '
- **hinglish-05** (2/3 passed) -- failed: must_include_any
  Reply excerpt: "Namaste! Main Meher Sweets ka AI assistant hoon. Sorry, I don't have that information. आपका मिठाई पसंद नहीं आई तो वापस कर सकते हैं। हमारी फoods दिल्ली"
- **hinglish-06** (0/3 passed) -- failed: must_include, must_include_any
  Reply excerpt: 'Sorry, main aisa nahi kar sakta. Sirf ek hi discount hai: 50 ya usse zyada gift box ke order par gift-box total par 5% off.'

## Flaky cases

- hindi-01: 2/3
- arith-10: 1/3
- arith-12: 2/3
- lead-03: 1/3
- privacy-03: 2/3
- hindi-06: 2/3
- hinglish-05: 2/3

## Notes

p50 and p95 latency use the nearest-rank method: sort the samples and take the value at rank ceil(p/100 * n) (1-indexed). Invented-amount rate, action accuracy and AI-disclosure rate are computed only over case-runs that completed without an HTTP error (errored case-runs are still counted as failures for the overall pass rate, and reported separately as 'errored case-runs').

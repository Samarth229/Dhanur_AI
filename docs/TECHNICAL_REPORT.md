# Meher Sweets Agent — Technical Report

Model: {{model}}  ·  Run date: {{run_date}}  ·  Submission pass rate: {{pass_rate_mean}} (mean), {{pass_rate_worst}} (worst)

## 1. Architecture

A grounded, tool-calling customer-service agent for a fictional sweet shop. Each `/chat` request: the message is language-detected (English/Hindi/Hinglish) and matched against a lexicon to retrieve relevant shop-data sections; a system prompt (full shop data, or top-k sections) plus the language instruction goes to the LLM, which can call up to 4 tools before a final text reply. `calculate_order`/`save_lead`/`escalate` validate and ground their own arguments in what the customer actually typed — all arithmetic runs in Python, never the model. Every reply then passes reply guards (amounts, percentages, privacy, canary, tool-call-leak, language match, length), one correction retry, then a safe fallback. Code-level safety nets independently catch complaints, unrefused discounts and incomplete leads. The eval harness is entirely black-box over HTTP.

```
message -> language detection + lexicon retrieval -> system prompt
        -> LLM <--> tools (calculate_order/save_lead/escalate: validate + ground args; math in Python)
        -> reply guards (amounts/%/privacy/canary/tool-leak/language/length), 1 retry, safe fallback
        -> code safety nets (complaint/discount/lead-contact) -> disclosure + sources -> response
```

## 2. Retrieval and grounding

A tiny catalogue (12 SKUs, a handful of policy sections) fits comfortably in a single prompt, so the default is **full context** with a lexicon-based retrieval pass surfacing the most relevant sections first (for citation and ordering, not exclusion). An ablation switching to **top-k retrieval** (`top_k=4`) showed pass rate is a wash ({{ablation_full_pass}} full vs {{ablation_topk_pass}} topk) but **action accuracy drops from {{ablation_full_action}} to {{ablation_topk_action}}** — with only 4 sections shown the model sometimes can't find the exact detail needed for a correct tool call. Full context stays the right default at this catalogue size.

**What didn't work — prompt-only fixes.** Fix 7 tried clarifying the `calculate_order` unit field's *description* ("pack → 'pack', NOT 'kg'") after the model computed `unit="kg"` for "2 पैक" (₹1,360 instead of ₹740). Evidence after the change: **hindi-06 still failed identically**, confirmed by direct tool-call tracing — a clearer schema description wasn't enough to change a small local model's argument choice. The real fix (Fix 9c) was code-side: independently extract the quantity/unit from the customer's own words and reject a tool call that disagrees, which verifiably fixed it (`grand_total == 740`, unit-tested).

**Model comparison** (`reports/model_comparison.md`, 4 local models via Ollama): `qwen2.5:7b` was selected — 81% language accuracy, 88% tool accuracy, 100% injection-refusal. `llama3.1:8b` had perfect language accuracy but only 38% tool accuracy and **failed every injection test (0%)**. `qwen3:8b` produced empty replies on tool-call turns (thinking-mode token budget exhaustion) and was ~3x slower. `mistral:latest` had poor tool use (50%).

## 3. The agent loop and tools

A `while model_calls < 4` loop: each turn either calls a tool (validated + grounded, `ERROR:` feedback fed back to the model on failure) or produces text that must pass every reply guard. Grounding covers item names, delivery distance, pack quantities, lead contact/name, and discount legitimacy — all checked against the literal conversation text, so invented items/leads/discounts are structurally rejected, not just discouraged. A guard failure gets exactly one correction retry (a specific instruction naming the problem); if the retry also fails, the reply falls back to a quote-derived template (if a quote exists), a generic template, or — only for percentage/canary/injection problems — a refusal template. If the budget runs out without an accepted reply, the turn auto-escalates. Code safety nets (independent of what the model decided to say) catch: complaints/human-requests without an `escalate` call, discount claims without refusal wording, and failed `save_lead` attempts without a contact re-request.

## 4. Results

Submission run:

{{summary_table}}

By category:

{{category_table}}

**Progression:** {{progression_line}}

**Cross-model smoke test:** {{xmodel_result}}

## 5. Five failures, root causes, fixes

{{five_failures}}

Manual testing on the chat page (a real multi-turn conversation, not the harness's per-case isolation) found further bugs the automated cases never exercised — a cross-item pack-quantity false positive breaking a 2-turn arithmetic case, and leads from two different people in one conversation merging into one record — both of which became new regression cases (`long-session-01`, `lead-06`) rather than one-off patches.

## 6. Cost and latency

{{cost_latency_section}}

INR cost is 0 for a local model (`usd_per_1m_*_tokens = 0` in config — Ollama has no per-token charge); the formula (`tokens x $/1M x INR/USD`) is wired up for a future hosted-model swap. p95 latency ({{latency_p95}} ms) is well above p50 ({{latency_p50}} ms) because turns needing `calculate_order` plus a guard-triggered correction retry mean 3-4 sequential LLM calls on a local 7B model with no batching — the model_calls distribution is dominated by 1-call turns (simple Q&A) with a long tail of 3-4 call turns (arithmetic + retries).

## 7. One more week

Code-side quantity/unit extraction compared against every tool call (not just the pack/kg case Fix 9c already covers) to close the remaining argument-grounding gaps; making the model retry more reliably after a tool `ERROR:` instead of occasionally giving up into a fallback; streaming replies to the chat page; a human-approval queue for `save_lead`/`escalate` before they're considered final; persistent storage (a real DB) for leads/escalations/conversations; running the eval harness across several models on a schedule to catch model-swap regressions; and retrieval that scales to a much larger catalogue (proper embeddings/BM25 instead of a hand-maintained lexicon).

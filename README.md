# Meher Sweets Agent

A grounded customer-query AI agent for a fictional sweet shop, "Meher Sweets & Namkeen".
It answers price/order/delivery/policy questions in English, Hindi or Hinglish, using tools for arithmetic and lead/escalation handling instead of letting the model compute or invent anything itself.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
ollama pull qwen2.5:7b
```

Mac/Linux: `source .venv/bin/activate` instead of `.venv\Scripts\activate`, and `cp .env.example .env` instead of `copy .env.example .env`.

**Tested on:** Windows 11, Python 3.14 (needs 3.11+), Ollama + `qwen2.5:7b`, NVIDIA RTX 4050 Laptop GPU (6 GB VRAM).

## Run

Start the service:

```
python manage.py run          # make run
```

It listens on `http://127.0.0.1:8000` (host/port from `config.toml`). Open `http://127.0.0.1:8000/` for the chat page (add `?debug=1` to see sources/actions/latency in small grey text under each reply -- hidden from normal customers).

Run the test suite:

```
python manage.py test         # make test
```

Run the eval harness (the service must already be running):

```
python manage.py eval --cases evals/cases.jsonl     # make eval CASES=evals/cases.jsonl
```

Useful flags: `--only <ids-or-categories>` (comma-separated, e.g. `--only hindi,lead-02`), `--runs N` (default from `config.toml`, `[eval] runs`), `--label <name>` (names the `reports/runs/<timestamp>-<label>/` folder and tags `reports/summary.md`). `python manage.py cases` (or `make cases`) regenerates `evals/cases.jsonl`'s computed totals from `evals/cases_src.jsonl` via `pricing.quote_order` -- never hand-typed.

## Configuration

`.env` (copied from `.env.example`, 3 variables, an OpenAI-compatible endpoint):

```
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b
```

`config.toml` sections: `[paths]` (all file locations, resolved relative to the repo root -- no hardcoded absolute paths anywhere in the code), `[llm]` (temperature, `max_model_calls`, timeout, `max_tokens`), `[reply]` (`max_chars`), `[server]` (host/port/warmup), `[eval]` (default runs, cost-per-token, harness base URL/timeout), `[retrieval]` (`mode` = `"full"` or `"topk"`, `top_k`, `min_score`), `[policy]` (delivery radius, free-delivery threshold, COD max, gift-box discount, bulk thresholds -- mirrors `data/policies.md`, checked by a test), `[agent]` (history length, max sources, allowed percentages), `[compare]` (settings for `scripts/compare_models.py`).

## API

- `POST /chat` -- `{"conversation_id": str, "message": str}` -> `{"reply": str, "sources": [str], "actions": [{"type": str, "args": {...}}], "handoff": bool, "usage": {"prompt_tokens", "completion_tokens", "model_calls", "latency_ms", "estimated"}}`
- `GET /leads` -- list of saved leads, with phone/email masked
- `GET /health` -- `{"status": "ok", "model": "qwen2.5:7b"}`
- `GET /` -- the chat page (`src/meher_agent/static/chat.html`)

Example:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "demo-1", "message": "How much is 500 g of sugar-free kaju katli?"}'
```

```json
{
  "reply": "Hi! I'm the AI assistant for Meher Sweets. The price of 500 g Sugar-free Kaju Katli is ₹780.",
  "sources": ["prices.csv#KKSF-500", "policies.md#prices-and-gst"],
  "actions": [],
  "handoff": false,
  "usage": {"prompt_tokens": 2871, "completion_tokens": 24, "model_calls": 1, "latency_ms": 2010.4, "estimated": false}
}
```

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post -ContentType "application/json" -Body (@{
    conversation_id = "demo-1"
    message = "How much is 500 g of sugar-free kaju katli?"
} | ConvertTo-Json)

Invoke-RestMethod -Uri http://127.0.0.1:8000/leads -Method Get
Invoke-RestMethod -Uri http://127.0.0.1:8000/health -Method Get
```

## Architecture

Each `/chat` request goes: the customer's message is language-detected (English/Hindi/Hinglish, with per-conversation hysteresis) and matched against a data-driven lexicon to retrieve the most relevant shop-data sections; a system prompt (the full shop data, or just the top-k retrieved sections, depending on `[retrieval] mode`) plus that language instruction is sent to the LLM, which can call up to `max_model_calls` tools before it must produce a final text reply. The three tools (`calculate_order`, `save_lead`, `escalate`) validate their own arguments and ground them in what the customer actually typed (no invented names, items, distances or contacts) before doing anything -- all arithmetic happens in Python, never in the model. Every candidate reply then passes through a chain of guards (disallowed amounts, disallowed percentages, privacy leaks, system-prompt/canary leaks, a tool-call-syntax leak, a reply-language mismatch, empty replies, length) with one correction retry before falling back to a safe template; a handful of code-level safety nets independently catch complaints/human-requests, unrefused discount claims and incomplete lead attempts that the model sometimes forgets to handle in words. The final reply gets an AI-disclosure prefix (first turn only), a list of cited sources, and is returned with token/latency usage. The eval harness (`evals_harness/`) is entirely black-box -- it only ever talks to the running service over HTTP, the same way a real client would.

```
customer message
      |
      v
 language detection  +  lexicon retrieval  ->  system prompt (full or top-k shop data)
      |
      v
   LLM  <-->  tools: calculate_order / save_lead / escalate
      |            (argument validation + grounding in the
      |             customer's own words; all math in Python)
      v
 reply guards: amounts, percentages, privacy, canary,
 tool-call-leak, language match, length
      |  (one correction retry, then a safe fallback template)
      v
 code safety nets: complaint/human-request escalate,
 discount refusal, lead-contact-request
      |
      v
 disclosure prefix + sources  ->  JSON response
      |
      v
 evals_harness (black-box, over HTTP only)
```

## Design decisions & trade-offs

- **Code computes, the model only phrases.** Every rupee amount comes from `pricing.quote_order` in Python; the model is never trusted to do arithmetic, and every reply is checked against the exact set of amounts a real computation could have produced. This is why `action accuracy` is 100% in the submission run despite a 7B local model doing the language work.
- **Full shop-data context vs top-k retrieval.** The default (`[retrieval] mode = "full"`) puts the entire (small) shop catalogue and policy text in every prompt, with the top retrieved sections surfaced first; an ablation with `mode = "topk"` (`reports/runs/<ts>-ablation-topk/`) showed pass rate is roughly a wash (94.7% vs 94.3%) but **action accuracy drops from 100.0% to 95.2%** under top-k -- with only 4 sections shown, the model sometimes can't find the exact detail it needs to call a tool correctly. Full context is the right default while the catalogue is this small; top-k would only earn its keep once the catalogue outgrows the context budget.
- **Code safety nets vs prompt-only rules.** Several behaviors (complaint escalation, discount refusal, lead-contact requests) were first attempted as prompt instructions alone and were unreliable (e.g. Fix 1: complaint escalation was 58.3% pass rate on prompt wording alone); each was backed by a deterministic code-level check that fires regardless of what the model decided to say, without removing the prompt instruction itself. `reports/failure_log.md` documents each one with before/after numbers.
- **Argument grounding.** Every tool argument (item name, distance, pack quantity, contact name/phone/email, discount) is checked against the literal text the customer typed across the conversation, not trusted at face value from the model -- this is what makes invented items/leads/discounts structurally impossible rather than merely discouraged.
- **Local 7B model vs a hosted frontier model.** `qwen2.5:7b` via Ollama was chosen after comparing 4 local models (`reports/model_comparison.md`) for tool-calling reliability and injection resistance; it trades some fluency (garbled Hindi sentences, occasional tool-call retries) for zero API cost and full local control, which the guard/safety-net/grounding layers are designed to compensate for.
- **In-memory storage.** Leads, escalations and conversation history are process-local dicts (`stores.py`, `conversations.py`), not a database -- correct and simple for a take-home service with modest conversation volume, but it means state doesn't survive a restart and won't scale past a single process (see Known limitations).

## Assumptions (pricing engine, Part 2)

1. Item resolution uses the longest matching alias across English, Hindi and Hinglish; a name that spans more than one product family (e.g. "laddoo", "gift box") is treated as ambiguous rather than guessed.
2. A requested amount is only fulfilled by an exact combination of existing pack sizes (cheapest first); amounts that can't be hit exactly (e.g. 750 g of a 1 kg-only product) are rejected rather than rounded.
3. Delivery distance is optional: if it's not given, no delivery fee or "with delivery" total is computed at all, rather than guessing free vs. charged.
4. Bulk-order status counts only dry and milk sweets by weight, plus gift boxes by count; namkeen and fresh snacks never count toward the bulk threshold.
5. All money (discounts, advances) is rounded to the nearest whole rupee with round-half-up, not Python's default banker's rounding.
6. The gift-box discount is checked before free-delivery eligibility, but this ordering can never change the final total: the discount only starts at 50+ gift boxes (≥ ₹32,500), which is always far above the ₹999 free-delivery threshold either way.

## Results

Official submission run: `python manage.py eval --cases evals/cases.jsonl --label submission` (76 cases x 3 runs, `qwen2.5:7b`, `mode = "full"`).

| Metric | Mean of runs | Worst run |
|---|---|---|
| Pass rate | 94.3% | 93.4% |
| Invented-amount rate | 1.3% | 1.3% |
| Action accuracy | 100.0% | 100.0% |
| AI-disclosure rate | 100.0% | 100.0% |
| Latency p50 (ms) | 2994 | 3179 |
| Latency p95 (ms) | 16932 | 20233 |
| Avg tokens in/out | 4954 / 111 | 5174 / 119 |

Full numbers and by-category breakdown: [reports/summary.md](reports/summary.md). Full fix-by-fix history and evidence: [reports/failure_log.md](reports/failure_log.md).

## AI tools used

Claude (chat) for planning, system-design discussion and reviewing results; Claude in VS Code (Claude Code) for writing code and tests from those designs; qwen2.5:7b via Ollama as the runtime model. Design decisions were discussed and approved by me; all numbers come from the harness.

## Known limitations

- **Residual flaky cases** from the submission run (`reports/summary.md`): `arith-10` (the model occasionally skips `calculate_order` and answers a total in prose), `arith-12` (an item-grounding edge case on a multi-turn coreference order), `lead-02`/`privacy-03` (wording variance on required refusal phrases), `hindi-06`/`hinglish-06`/`hinglish-07` (the model not reliably retrying a tool call after an argument error, or answering in prose instead of calling the tool at all).
- **The 7B model's Hindi fluency** is imperfect -- occasional garbled or run-on Hindi sentences, mitigated but not eliminated by a "keep it short" prompt instruction (see Fix 14/Fix E in `reports/failure_log.md`).
- **The model sometimes ignores a tool's `ERROR:` feedback** instead of retrying with corrected arguments, burning its remaining `model_calls` budget on repeated wrong attempts or giving up into a fallback template.
- **p95 latency is high** (~17-20 seconds) because a turn requiring `calculate_order` plus a guard-triggered correction retry can mean 3-4 sequential LLM calls against a local 7B model with no batching or speculative decoding.
- **In-memory stores** (leads, escalations, conversation history) don't persist across a restart and don't scale past one process.
- **Lexicon-based retrieval and intent detection** (`resources/lexicon.toml`) are hand-maintained word lists that must grow whenever the catalogue grows; they don't generalize to a product or phrasing that was never added to the lexicon.
- **Single process, no concurrency beyond FastAPI's threadpool** -- fine for this take-home's expected load, not a production-scale design.

## Project layout

```
manage.py                  CLI entry point (run/test/eval/check-llm/retrieve/cases/quote/chat)
config.toml                 all settings (paths, LLM, retrieval, policy, agent, eval)
.env.example                 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
data/                        shop data: prices.csv, policies.md, business.md (never touched by fixes)
evals/                       seed_cases.jsonl (never touched), cases_src.jsonl, cases.jsonl (generated)
evals_harness/                black-box eval harness (loader, client, checks, metrics, runner, report)
scripts/                     compare_models.py, compute_expected.py, replay_session.py, smoke_seed.py, ...
src/meher_agent/
  api.py                      FastAPI app (/chat, /leads, /health, /)
  agent.py                    the tool-calling agent loop, guards/retry/fallback orchestration
  guards.py                   reply guards (amounts, percentages, privacy, canary, tool-leak, language)
  tools.py                    calculate_order / save_lead / escalate, argument validation + grounding
  pricing.py                  the pricing engine (item resolution, packing, discounts, delivery)
  language.py                 English/Hindi/Hinglish detection
  retrieval.py                lexicon-based section retrieval
  intents.py                  data-driven intent detection (complaint, discount, human_request, ...)
  prompts.py                  system prompt assembly, per-turn language instruction, templates
  stores.py                   in-memory LeadStore / EscalationStore
  conversations.py            in-memory per-conversation history
  static/chat.html             the customer-facing chat page
  resources/                   lexicon.toml, system_prompt.md, templates.toml
tests/                        pytest suite (one file per module)
reports/                      failure_log.md, model_comparison.md, eval_report.json, summary.md, runs/
docs/TECHNICAL_REPORT.md       report template (filled by scripts/build_report.py)
TECHNICAL_REPORT.pdf          built report (python manage.py report)
```

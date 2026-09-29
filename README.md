# Meher Sweets Agent

A grounded customer-query agent for a fictional sweet shop, "Meher Sweets".

Tested on Windows 11.

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # macOS/Linux: cp .env.example .env
ollama pull qwen2.5:7b
```

## Commands

- `python manage.py run` — start the service
- `python manage.py test` — run the test suite
- `python manage.py eval --cases evals/seed_cases.jsonl` — run the eval harness
- `python manage.py check-llm` — verify the LLM endpoint works end to end

Mac/Linux reviewers can use the equivalent `make run`, `make test`, `make eval CASES=...`, `make check-llm`.

Model: qwen2.5:7b via Ollama, chosen using scripts/compare_models.py (results in reports/model_comparison.md).

## Assumptions (pricing engine, Part 2)

1. Item resolution uses the longest matching alias across English, Hindi and Hinglish; a name that spans more than one product family (e.g. "laddoo", "gift box") is treated as ambiguous rather than guessed.
2. A requested amount is only fulfilled by an exact combination of existing pack sizes (cheapest first); amounts that can't be hit exactly (e.g. 750 g of a 1 kg-only product) are rejected rather than rounded.
3. Delivery distance is optional: if it's not given, no delivery fee or "with delivery" total is computed at all, rather than guessing free vs. charged.
4. Bulk-order status counts only dry and milk sweets by weight, plus gift boxes by count; namkeen and fresh snacks never count toward the bulk threshold.
5. All money (discounts, advances) is rounded to the nearest whole rupee with round-half-up, not Python's default banker's rounding.
6. The gift-box discount is checked before free-delivery eligibility, but this ordering can never change the final total: the discount only starts at 50+ gift boxes (≥ ₹32,500), which is always far above the ₹999 free-delivery threshold either way.

## Run the service

Start the server:

```
python manage.py run
```

It listens on `http://127.0.0.1:8000` by default (host/port from `config.toml`). Use `python manage.py run --reload` for auto-reload during development.

Open http://127.0.0.1:8000/ for the chat page.

**PowerShell:**

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post -ContentType "application/json" -Body (@{
    conversation_id = "demo-1"
    message = "How much is 500 g of sugar-free kaju katli?"
} | ConvertTo-Json)

Invoke-RestMethod -Uri http://127.0.0.1:8000/leads -Method Get

Invoke-RestMethod -Uri http://127.0.0.1:8000/health -Method Get
```

**curl:**

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "demo-1", "message": "How much is 500 g of sugar-free kaju katli?"}'

curl http://127.0.0.1:8000/leads

curl http://127.0.0.1:8000/health
```

More to come as the project progresses.

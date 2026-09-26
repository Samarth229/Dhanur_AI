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

More to come as the project progresses.

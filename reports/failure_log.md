# Failure log: Part 9 fixes

Baseline reference: `reports/runs/20260927-175002-baseline-full/` (73 cases x 3 runs, `qwen2.5:7b`).

## Fix 1: Code-level complaint/human-request escalate safety net
- Cases: complaint-01, complaint-03, complaint-04
- What went wrong: the model apologised and offered to help, but never actually called `escalate` in some runs. complaint-04: "Sure, I'll pass your request to our team. They will get back to you by email..." with `Actions: []` -- 0/3 in baseline.
- Root cause: the model sometimes narrates the handoff in words without invoking the tool. Relying on the model to remember every time is fragile.
- Change: `src/meher_agent/intents.py` (new, data-driven intent detection), `[intents]` word lists in `lexicon.toml`, `src/meher_agent/agent.py` (auto-calls `escalate` when a complaint/human-request intent is detected in the customer's message and the model didn't call it this turn; appends the handoff sentence and, for damage-specific words, a photo-request sentence). Commit 8838328.
- Result: not yet re-evaluated in isolation (complaint category re-run happens after Fix 5, which also touches lead/escalate-adjacent logic) -- see the "Before vs after" table for the combined effect.
- Fixed? pending combined verification.

## Fix 2: Tighten out-of-scope rule and escalate tool description
- Cases: out_of_scope (oos-01..04)
- What went wrong: oos-03 (general knowledge) and oos-04 (resume writing) sometimes called `escalate` even though they're plainly out-of-scope and answerable by a one-sentence decline -- `expect_action: "none"` failed because `actions` was non-empty.
- Root cause: the system prompt's out-of-scope rule and the `escalate` tool's own description didn't explicitly forbid using escalate for out-of-scope requests strongly enough; the model over-generalised "I can't help with this" into "let me hand this off."
- Change: `src/meher_agent/resources/system_prompt.md` (out-of-scope rule rewritten to "call NO tool at all -- not escalate, not any tool", with one English and one Hinglish example), `src/meher_agent/tools.py` (escalate tool description explicitly excludes out-of-scope requests). Commit 9488acd.
- Result: out_of_scope pass rate 66.7% (mean) / 50% (worst) -> **100% / 100%** (`reports/runs/20260928-160456-fix2-oos/`)
- Fixed? yes.

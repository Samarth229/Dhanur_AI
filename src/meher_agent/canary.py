"""A random per-process canary token embedded in the system prompt.

Generated once when the process starts (fixed for the whole run, so the
static system prompt prefix stays identical across turns for LLM caching).
If it ever appears in a model's reply, the prompt-leak guard fails it.
"""
from __future__ import annotations

import secrets

CANARY = f"MS-CANARY-{secrets.token_hex(4)}"

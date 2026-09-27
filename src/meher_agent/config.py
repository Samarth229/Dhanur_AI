"""Typed, environment-aware configuration for the Meher Sweets agent.

Loads settings from config.toml (non-secret, repo-tracked) and from the
environment / .env file (secrets: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL).
All paths are resolved to absolute paths anchored at the project root.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.toml"

# Real environment variables take priority over .env; override=False preserves that.
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class PathsConfig:
    data_dir: Path
    evals_dir: Path
    reports_dir: Path
    lexicon: Path
    system_prompt: Path
    templates: Path


@dataclass(frozen=True)
class LLMConfig:
    temperature: float
    max_model_calls: int
    request_timeout_s: int
    max_tokens: int


@dataclass(frozen=True)
class ReplyConfig:
    max_chars: int


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    warmup_on_start: bool


@dataclass(frozen=True)
class EvalConfig:
    runs: int
    inr_per_usd: float
    usd_per_1m_input_tokens: float
    usd_per_1m_output_tokens: float


@dataclass(frozen=True)
class RetrievalConfig:
    mode: str
    top_k: int
    min_score: float
    history_weight: float


@dataclass(frozen=True)
class PolicyConfig:
    delivery_radius_km: float
    free_delivery_min_inr: float
    delivery_fee_inr: float
    cod_max_inr: float
    giftbox_discount_min_boxes: int
    giftbox_discount_pct: float
    bulk_sweets_kg_over: float
    bulk_giftboxes_over: int
    bulk_notice_days: int
    bulk_advance_pct: float
    giftbox_preorder_until: str
    max_order_units: int


@dataclass(frozen=True)
class LoggingConfig:
    level: str


@dataclass(frozen=True)
class AgentConfig:
    history_messages: int
    max_sources: int
    allowed_percentages: tuple[float, ...]
    today_override: str


@dataclass(frozen=True)
class CompareConfig:
    runs_per_message: int
    max_model_calls: int
    devanagari_ratio_threshold: float
    fake_order_subtotal_inr: float
    fake_order_delivery_fee_inr: float
    fake_order_total_inr: float


@dataclass(frozen=True)
class Settings:
    paths: PathsConfig
    llm: LLMConfig
    reply: ReplyConfig
    server: ServerConfig
    eval: EvalConfig
    retrieval: RetrievalConfig
    policy: PolicyConfig
    logging: LoggingConfig
    agent: AgentConfig
    compare: CompareConfig
    project_root: Path


def _load_toml() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def load_settings() -> Settings:
    raw = _load_toml()

    paths = PathsConfig(
        data_dir=(PROJECT_ROOT / raw["paths"]["data_dir"]).resolve(),
        evals_dir=(PROJECT_ROOT / raw["paths"]["evals_dir"]).resolve(),
        reports_dir=(PROJECT_ROOT / raw["paths"]["reports_dir"]).resolve(),
        lexicon=(PROJECT_ROOT / raw["paths"]["lexicon"]).resolve(),
        system_prompt=(PROJECT_ROOT / raw["paths"]["system_prompt"]).resolve(),
        templates=(PROJECT_ROOT / raw["paths"]["templates"]).resolve(),
    )
    llm = LLMConfig(**raw["llm"])
    reply = ReplyConfig(**raw["reply"])
    server = ServerConfig(**raw["server"])
    eval_cfg = EvalConfig(**raw["eval"])
    retrieval_cfg = RetrievalConfig(**raw["retrieval"])
    policy_cfg = PolicyConfig(**raw["policy"])
    logging_cfg = LoggingConfig(**raw["logging"])
    agent_raw = dict(raw["agent"])
    agent_raw["allowed_percentages"] = tuple(agent_raw["allowed_percentages"])
    agent_cfg = AgentConfig(**agent_raw)
    compare_cfg = CompareConfig(**raw["compare"])

    return Settings(
        paths=paths,
        llm=llm,
        reply=reply,
        server=server,
        eval=eval_cfg,
        retrieval=retrieval_cfg,
        policy=policy_cfg,
        logging=logging_cfg,
        agent=agent_cfg,
        compare=compare_cfg,
        project_root=PROJECT_ROOT,
    )


@dataclass(frozen=True)
class LLMCredentials:
    base_url: str
    api_key: str
    model: str


def get_llm_credentials() -> LLMCredentials:
    """Reads LLM connection details from the environment.

    Raises a clear error only when actually called, not at import time,
    so importing this module never requires the LLM to be configured.
    """
    base_url = os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")

    missing = [
        name
        for name, value in [
            ("LLM_BASE_URL", base_url),
            ("LLM_API_KEY", api_key),
            ("LLM_MODEL", model),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required LLM environment variable(s): "
            f"{', '.join(missing)}. Set them in your environment or in a "
            "'.env' file at the project root (see .env.example)."
        )

    return LLMCredentials(base_url=base_url, api_key=api_key, model=model)


settings = load_settings()

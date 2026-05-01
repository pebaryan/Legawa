from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class Settings:
    pasal_token: str
    pasal_base_url: str
    big: LLMConfig
    small: LLMConfig
    run_date: str
    corpus_watermark: str
    strict_citations: bool


def _required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"missing env var: {key}")
    return val


def _bool_env(key: str, default: str = "0") -> bool:
    val = os.environ.get(key, default).strip().lower()
    return val in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    temp = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "4096"))
    return Settings(
        pasal_token=_required("PASAL_API_TOKEN"),
        pasal_base_url=os.environ.get("PASAL_BASE_URL", "https://pasal.id/api/v1"),
        big=LLMConfig(
            base_url=_required("LLM_BIG_URL"),
            api_key=os.environ.get("LLM_BIG_API_KEY", "sk-no-key-required"),
            model=os.environ.get("LLM_BIG_MODEL", "qwen3"),
            temperature=temp,
            max_tokens=max_tokens,
        ),
        small=LLMConfig(
            base_url=_required("LLM_SMALL_URL"),
            api_key=os.environ.get("LLM_SMALL_API_KEY", "sk-no-key-required"),
            model=os.environ.get("LLM_SMALL_MODEL", "qwen3"),
            temperature=temp,
            max_tokens=max_tokens,
        ),
        run_date=os.environ.get("LEGAWA_RUN_DATE", date.today().isoformat()),
        corpus_watermark=os.environ.get("PASAL_CORPUS_WATERMARK", ""),
        strict_citations=_bool_env("LEGAWA_STRICT_CITATIONS", "1"),
    )

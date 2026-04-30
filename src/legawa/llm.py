"""LLM client wrappers for the two llama.cpp endpoints.

- BIG  (localhost:8080, Qwen3 ~35B): synthesis, drafting, deep analysis.
- SMALL (mi25:8080, Qwen3 ~27B):     classification, extraction, query expansion.

Both expose an OpenAI-compatible chat/completions API, so we use the openai SDK.
"""

from __future__ import annotations

from typing import Any, Iterable

from openai import OpenAI

from .config import LLMConfig, Settings


class LLM:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,
            temperature=self.cfg.temperature if temperature is None else temperature,
            max_tokens=self.cfg.max_tokens if max_tokens is None else max_tokens,
        )
        return resp.choices[0].message.content or ""

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: Iterable[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        """Single tool-calling round-trip; returns the raw choice.message object."""
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,
            tools=list(tools),
            tool_choice="auto",
            temperature=self.cfg.temperature if temperature is None else temperature,
            max_tokens=self.cfg.max_tokens if max_tokens is None else max_tokens,
        )
        return resp.choices[0].message


class LLMPool:
    def __init__(self, settings: Settings):
        self.big = LLM(settings.big)
        self.small = LLM(settings.small)

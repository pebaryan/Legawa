"""LLM client wrappers for the two llama.cpp endpoints.

- BIG  (localhost:8080, Qwen3 ~35B): synthesis, drafting, deep analysis.
- SMALL (mi25:8080, Qwen3 ~27B):     classification, extraction, query expansion.

Both expose an OpenAI-compatible chat/completions API, so we use the openai SDK.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from openai import OpenAI

from .config import LLMConfig, Settings


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Remove Qwen3 <think>...</think> reasoning blocks from final content."""
    return _THINK_RE.sub("", text or "")


class LLM:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    def _extra_body(self, think: bool) -> dict[str, Any]:
        # Qwen3 chat template honours `enable_thinking`. Disabling cuts latency by ~5x
        # and prevents thinking tokens from consuming the entire max_tokens budget.
        return {"chat_template_kwargs": {"enable_thinking": think}}

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool = False,
    ) -> str:
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,
            temperature=self.cfg.temperature if temperature is None else temperature,
            max_tokens=self.cfg.max_tokens if max_tokens is None else max_tokens,
            extra_body=self._extra_body(think),
        )
        return strip_thinking(resp.choices[0].message.content or "")

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: Iterable[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool = False,
    ) -> Any:
        """Single tool-calling round-trip; returns the raw choice.message object."""
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,
            tools=list(tools),
            tool_choice="auto",
            temperature=self.cfg.temperature if temperature is None else temperature,
            max_tokens=self.cfg.max_tokens if max_tokens is None else max_tokens,
            extra_body=self._extra_body(think),
        )
        msg = resp.choices[0].message
        if msg.content:
            msg.content = strip_thinking(msg.content)
        return msg


class LLMPool:
    def __init__(self, settings: Settings):
        self.big = LLM(settings.big)
        self.small = LLM(settings.small)

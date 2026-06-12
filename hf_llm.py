"""
hf_llm.py — Hugging Face Inference API wrapper for Legawa.

Implements the same interface as legawa.llm.LLM (chat, chat_with_tools)
but uses huggingface_hub's InferenceClient behind the scenes.

This is the DEFAULT backend for the HF Space (zero-config).
Users can switch to the OpenAI-based backend in Settings for custom endpoints.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from huggingface_hub import InferenceClient
from huggingface_hub.errors import BadRequestError

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks (and a dangling unclosed one)."""
    text = _THINK_RE.sub("", text)
    if "<think>" in text:
        text = text.split("<think>")[0]
    return text.strip()


class HFLLM:
    """Drop-in replacement for legawa.llm.LLM using HF Inference Client.

    Matches the .chat() and .chat_with_tools() interface that the
    agent code expects.
    """

    def __init__(self, model_id: str, token: str = "", **kwargs: Any):
        self.model_id = model_id
        self.client = InferenceClient(token=token or None)
        # Some inference providers reject chat_template_kwargs with a bare
        # 400. Detected on first call, then remembered for the session.
        self._supports_template_kwargs: bool | None = None

    def _extra_body(self, think: bool) -> dict[str, Any]:
        """Disable reasoning tokens by default (Qwen-specific)."""
        return {"chat_template_kwargs": {"enable_thinking": think}}

    def _call(self, **kwargs: Any) -> Any:
        think = kwargs.pop("think", False)
        if self._supports_template_kwargs is not False:
            try:
                resp = self.client.chat.completions.create(
                    model=self.model_id,
                    extra_body=self._extra_body(think),
                    **kwargs,
                )
                self._supports_template_kwargs = True
                return resp
            except BadRequestError:
                if self._supports_template_kwargs:
                    raise  # provider accepted it before; this 400 is real
                self._supports_template_kwargs = False
        return self.client.chat.completions.create(model=self.model_id, **kwargs)

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool = False,
    ) -> str:
        """Direct chat completion (no tools)."""
        kwargs: dict[str, Any] = {"max_tokens": max_tokens or 4096}
        if self._supports_template_kwargs is False and not think:
            # Thinking can't be disabled provider-side; reasoning tokens count
            # against the budget, so small budgets would yield empty replies.
            kwargs["max_tokens"] = max(kwargs["max_tokens"], 2048)
        if temperature is not None:
            kwargs["temperature"] = temperature
        kwargs["think"] = think

        resp = self._call(
            messages=messages,
            **kwargs,
        )
        content = resp.choices[0].message.content or ""
        if (
            not content.strip()
            and self._supports_template_kwargs is False
            and kwargs["max_tokens"] < 2048
        ):
            # First call after fallback detection ran with the original small
            # budget and thinking ate it all — retry once with the floor.
            kwargs["max_tokens"] = 2048
            resp = self._call(messages=messages, **kwargs)
            content = resp.choices[0].message.content or ""
        # If thinking could not be disabled provider-side, strip it here so
        # agents never see <think> blocks.
        return _strip_thinking(content)

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: Iterable[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool = False,
    ) -> Any:
        """Single tool-calling round-trip.

        Returns the raw choice.message object (must have .content, .tool_calls).
        """
        kwargs: dict[str, Any] = {"max_tokens": max_tokens or 4096}
        if temperature is not None:
            kwargs["temperature"] = temperature
        kwargs["think"] = think

        resp = self._call(
            messages=messages,
            tools=list(tools),
            tool_choice="auto",
            **kwargs,
        )
        return resp.choices[0].message


class HFLLMPool:
    """Drop-in replacement for legawa.llm.LLMPool.

    Wraps two HFLLM instances (big + small).
    """

    def __init__(
        self,
        big_model_id: str,
        small_model_id: str,
        token: str = "",
        **kwargs: Any,
    ):
        self.big = HFLLM(big_model_id, token=token)
        self.small = HFLLM(small_model_id, token=token)
        # Stub settings reference for code that accesses pool.settings
        self.settings = _StubSettings()


class _StubSettings:
    """Minimal stub so agent code that references pool.settings doesn't crash."""

    run_date: str = ""
    corpus_watermark: str = ""
    strict_citations: bool = False

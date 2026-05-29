"""
hf_llm.py — Hugging Face Inference API wrapper for Legawa.

Implements the same interface as legawa.llm.LLM (chat, chat_with_tools)
but uses huggingface_hub's InferenceClient behind the scenes.

This is the DEFAULT backend for the HF Space (zero-config).
Users can switch to the OpenAI-based backend in Settings for custom endpoints.
"""
from __future__ import annotations

from typing import Any, Iterable

from huggingface_hub import InferenceClient


class HFLLM:
    """Drop-in replacement for legawa.llm.LLM using HF Inference Client.

    Matches the .chat() and .chat_with_tools() interface that the
    agent code expects.
    """

    def __init__(self, model_id: str, token: str = "", **kwargs: Any):
        self.model_id = model_id
        self.client = InferenceClient(token=token or None)

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
        if temperature is not None:
            kwargs["temperature"] = temperature

        resp = self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

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

        resp = self.client.chat.completions.create(
            model=self.model_id,
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

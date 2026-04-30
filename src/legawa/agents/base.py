"""Generic tool-calling agent loop.

Drives an OpenAI-compatible chat model (llama.cpp + Qwen3) through repeated
tool calls until the model returns a final assistant message with no tool calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from rich.console import Console

from ..llm import LLM


ToolDispatcher = Callable[[str, dict[str, Any]], Any]


@dataclass
class AgentResult:
    output: str
    messages: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class ToolAgent:
    def __init__(
        self,
        name: str,
        llm: LLM,
        system_prompt: str,
        tools: list[dict[str, Any]],
        dispatcher: ToolDispatcher,
        *,
        max_iters: int = 8,
        console: Console | None = None,
    ):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.tools = tools
        self.dispatcher = dispatcher
        self.max_iters = max_iters
        self.console = console or Console()

    def run(self, user_input: str) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]
        all_calls: list[dict[str, Any]] = []

        for _ in range(self.max_iters):
            msg = self.llm.chat_with_tools(messages, self.tools)
            tool_calls = getattr(msg, "tool_calls", None) or []

            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            if tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_entry)

            if not tool_calls:
                return AgentResult(output=msg.content or "", messages=messages, tool_calls=all_calls)

            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as e:
                    fn_args = {}
                    err = f"invalid JSON in tool args: {e}"
                    self.console.print(f"[red]{self.name}: {err}[/red]")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({"error": err}),
                    })
                    continue

                self.console.print(
                    f"[dim]{self.name} → {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:160]})[/dim]"
                )
                try:
                    result = self.dispatcher(fn_name, fn_args)
                except Exception as e:  # noqa: BLE001
                    result = {"error": str(e)}
                    self.console.print(f"[red]{self.name} tool error: {e}[/red]")

                all_calls.append({"name": fn_name, "args": fn_args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(_truncate(result), ensure_ascii=False),
                })

        return AgentResult(
            output="(agent reached max iterations without final answer)",
            messages=messages,
            tool_calls=all_calls,
        )


def _truncate(obj: Any, max_len: int = 24000) -> Any:
    """Cap tool-result payload size to avoid blowing the context window."""
    s = json.dumps(obj, ensure_ascii=False)
    if len(s) <= max_len:
        return obj
    return {"_truncated": True, "preview": s[:max_len]}

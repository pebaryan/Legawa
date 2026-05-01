from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.agents.analis_ruu import analyze, build_agent
from legawa.agents.base import AgentResult
from legawa.config import LLMConfig, Settings


class FakeLLM:
    def __init__(self):
        self.calls: list = []

    def chat_with_tools(self, messages, tools, **kwargs):
        self.calls.append((messages, tools, kwargs))
        raise AssertionError("chat_with_tools should not be called in this test")


class FakePool:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.big = FakeLLM()
        self.small = FakeLLM()


class FakePasalClient:
    def __init__(self, responses: dict[str, dict] | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.get(kwargs["q"], {"results": []})


class FakeAgent:
    def __init__(self, output: str):
        self.output = output
        self.calls: list[str] = []

    def run(self, user_input: str):
        self.calls.append(user_input)
        return AgentResult(output=self.output, messages=[], tool_calls=[])


def make_settings(*, strict_citations: bool = True) -> Settings:
    cfg = LLMConfig(base_url="http://example.invalid", api_key="x", model="qwen3", temperature=0.3, max_tokens=4096)
    return Settings(
        pasal_token="token",
        pasal_base_url="http://pasal.invalid",
        big=cfg,
        small=cfg,
        run_date="2026-04-30",
        corpus_watermark="2026-04-30",
        strict_citations=strict_citations,
    )


class AnalisRuuTests(unittest.TestCase):
    def test_build_agent_embeds_runtime_context(self) -> None:
        pool = FakePool(make_settings())
        pasal = FakePasalClient()

        agent = build_agent(pool, pasal)

        self.assertIn("Tanggal penyusunan: 2026-04-30", agent.system_prompt)
        self.assertIn("Status korpus pasal.id: 2026-04-30", agent.system_prompt)

    def test_analyze_blocks_unverified_citation(self) -> None:
        pool = FakePool(make_settings())
        pasal = FakePasalClient(
            {
                "UU 13/2003": {
                    "results": [
                        {
                            "title": "Undang-Undang Nomor 13 Tahun 2003",
                            "frbr_uri": "akn/id/act/uu/2003/13",
                            "status": "berlaku",
                        }
                    ]
                }
            }
        )
        agent = FakeAgent("RUU ini merujuk pada UU 13/2003 dan Perpres 76/2021.")

        with patch("legawa.agents.analis_ruu.build_agent", return_value=agent):
            with self.assertRaises(ValueError) as ctx:
                analyze(pool, pasal, "naskah uji", console=None)

        self.assertIn("Perpres 76/2021", str(ctx.exception))
        self.assertEqual(len(agent.calls), 1)

    def test_analyze_accepts_verified_citation(self) -> None:
        pool = FakePool(make_settings())
        pasal = FakePasalClient(
            {
                "UU 13/2003": {
                    "results": [
                        {
                            "title": "Undang-Undang Nomor 13 Tahun 2003",
                            "frbr_uri": "akn/id/act/uu/2003/13",
                            "status": "berlaku",
                        }
                    ]
                }
            }
        )
        agent = FakeAgent("RUU ini merujuk pada UU 13/2003.")

        with patch("legawa.agents.analis_ruu.build_agent", return_value=agent):
            result = analyze(pool, pasal, "naskah uji", console=None)

        self.assertEqual(result.output, "RUU ini merujuk pada UU 13/2003.")
        self.assertEqual(len(agent.calls), 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.agents.penyusun import draft
from legawa.config import LLMConfig, Settings


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[list[dict], dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


class FakePool:
    def __init__(self, settings: Settings, small_response: str, big_response: str):
        self.settings = settings
        self.small = FakeLLM(small_response)
        self.big = FakeLLM(big_response)


class FakePasalClient:
    def __init__(self, hits: dict[str, dict] | None = None):
        self.hits = hits or {}
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.hits.get(kwargs["q"], {"results": []})


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


class PenyusunTests(unittest.TestCase):
    def test_draft_includes_runtime_context_and_domain_constraints(self) -> None:
        pool = FakePool(
            make_settings(),
            small_response='["pengadaan sekolah dasar"]',
            big_response="Ringkasan singkat tanpa sitasi.",
        )
        pasal = FakePasalClient()

        output = draft(
            pool,
            pasal,
            kind="memo_kebijakan",
            topic="respons legislatif atas pengadaan Chromebook sekolah dasar",
            with_research=False,
            extra_instructions="fokus pada sekolah dasar",
        )

        self.assertIn("Ringkasan", output)
        system_prompt = pool.big.calls[0][0][0]["content"]
        self.assertIn("Tanggal penyusunan: 2026-04-30", system_prompt)
        self.assertIn("Status korpus pasal.id: 2026-04-30", system_prompt)
        self.assertIn("pendidikan dasar/menengah", system_prompt)

    def test_draft_blocks_unverified_citation(self) -> None:
        pool = FakePool(
            make_settings(),
            small_response='["pengadaan sekolah dasar"]',
            big_response="Balasan dengan Perpres 76/2021 yang salah.",
        )
        pasal = FakePasalClient()

        with self.assertRaises(ValueError) as ctx:
            draft(
                pool,
                pasal,
                kind="memo_kebijakan",
                topic="respons legislatif atas pengadaan Chromebook sekolah dasar",
                with_research=False,
            )

        self.assertIn("Perpres 76/2021", str(ctx.exception))
        self.assertEqual(len(pool.big.calls), 1)
        self.assertGreaterEqual(len(pasal.calls), 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.cli import app
from legawa.config import LLMConfig, Settings


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[list[dict], dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


class FakePool:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.big = FakeLLM("OK")
        self.small = FakeLLM("OK")


class FakePasalClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.closed = False
        self.calls: list[dict] = []

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def search(self, q=None, limit=1, **kwargs):
        if q is None:
            q = kwargs.get("q")
        self.calls.append({"q": q, "limit": limit, **kwargs})
        if q in {"UU 31/1999", "UU 20/2001", "Perpres 16/2018", "Perpres 12/2021"}:
            kind_map = {
                "UU 31/1999": ("uu", "1999", "31", "Undang-Undang Nomor 31 Tahun 1999"),
                "UU 20/2001": ("uu", "2001", "20", "Undang-Undang Nomor 20 Tahun 2001"),
                "Perpres 16/2018": ("perpres", "2018", "16", "Peraturan Presiden Nomor 16 Tahun 2018"),
                "Perpres 12/2021": ("perpres", "2021", "12", "Peraturan Presiden Nomor 12 Tahun 2021"),
            }
            kind, year, number, title = kind_map[q]
            return {
                "results": [
                    {
                        "title": title,
                        "frbr_uri": f"akn/id/act/{kind}/{year}/{number}",
                        "status": "berlaku",
                    }
                ]
            }
        return {"results": [{"title": "UU test", "frbr_uri": "akn/id/act/uu/2003/13", "status": "berlaku"}]}


class FakeCachingPasalClient:
    def __init__(self, raw):
        self.raw = raw
        self.closed = False

    def stats(self):
        return {"entries": 2, "bytes": 128, "session_hits": 1, "session_misses": 0}

    def purge_expired(self):
        return 3

    def close(self):
        self.closed = True


def make_settings() -> Settings:
    cfg = LLMConfig(base_url="http://example.invalid", api_key="x", model="qwen3", temperature=0.3, max_tokens=4096)
    return Settings(
        pasal_token="token",
        pasal_base_url="http://pasal.invalid",
        big=cfg,
        small=cfg,
        run_date="2026-04-30",
        corpus_watermark="2026-04-30",
        strict_citations=True,
    )


class CliSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self.settings = make_settings()

    def test_health_smoke(self) -> None:
        with (
            patch("legawa.cli.load_settings", return_value=self.settings),
            patch("legawa.cli.LLMPool", return_value=FakePool(self.settings)),
            patch("legawa.cli.PasalClient", side_effect=lambda settings: FakePasalClient(settings)),
        ):
            result = self.runner.invoke(app, ["health"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("OK big", result.output)
        self.assertIn("OK small", result.output)
        self.assertIn("OK pasal.id", result.output)

    def test_cache_commands_smoke(self) -> None:
        with (
            patch("legawa.cli.load_settings", return_value=self.settings),
            patch("legawa.cli.LLMPool", return_value=FakePool(self.settings)),
            patch("legawa.cli.PasalClient", side_effect=lambda settings: FakePasalClient(settings)),
            patch("legawa.cli.CachingPasalClient", side_effect=lambda raw: FakeCachingPasalClient(raw)),
        ):
            stats = self.runner.invoke(app, ["cache", "stats"])
            purge = self.runner.invoke(app, ["cache", "purge"])

        self.assertEqual(stats.exit_code, 0, stats.output)
        self.assertIn("'entries': 2", stats.output)
        self.assertEqual(purge.exit_code, 0, purge.output)
        self.assertIn("purged 3 expired entries", purge.output)

    def test_draft_cli_it_audit_perspective(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ibam-it-audit-perspective.txt").read_text(
            encoding="utf-8"
        )
        fake_pool = FakePool(self.settings)
        fake_pool.big.response = (
            "# Memo Teknis\n"
            "Kami menilai serial number, audit trail, CDM license history, firmware, dan MDM policy.\n"
            "Rujukan: UU 31/1999, UU 20/2001, Perpres 16/2018."
        )
        fake_pasal = FakePasalClient(self.settings)

        def bootstrap():
            return fake_pool, fake_pasal

        with patch("legawa.cli._bootstrap", side_effect=bootstrap):
            result = self.runner.invoke(
                app,
                [
                    "draft",
                    "memo_kebijakan",
                    "audit teknis dan tata kelola perangkat digital pada Kasus Ibam",
                    "--instruksi",
                    source,
                    "--no-research",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Memo Teknis", result.output)
        self.assertIn("UU 31/1999", result.output)
        self.assertNotIn("Perguruan Tinggi", result.output)
        system_prompt = fake_pool.big.calls[0][0][0]["content"]
        self.assertIn("forensik digital", system_prompt)
        self.assertIn("Tanggal penyusunan: 2026-04-30", system_prompt)


if __name__ == "__main__":
    unittest.main()

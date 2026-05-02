from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.agents.peneliti import _canonical_probe_uris, research
from legawa.config import LLMConfig, Settings


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[list[dict], dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


class FakePool:
    def __init__(self, settings: Settings, small_response: str):
        self.settings = settings
        self.small = FakeLLM(small_response)
        self.big = FakeLLM("Memo hasil riset.")


class FakePasalClient:
    def __init__(self):
        self.search_calls: list[dict] = []
        self.get_law_calls: list[str] = []

    def search(self, q=None, **kwargs):
        if q is not None:
            kwargs["q"] = q
        self.search_calls.append(kwargs)
        return {
            "results": [
                {
                    "title": f"Hasil {kwargs['q']}",
                    "frbr_uri": f"akn/id/act/mock/{len(self.search_calls)}",
                    "status": "berlaku",
                }
            ]
        }

    def get_law(self, frbr_uri: str):
        self.get_law_calls.append(frbr_uri)
        return {
            "title": f"Dokumen {frbr_uri}",
            "frbr_uri": frbr_uri,
            "status": "berlaku",
            "articles": [{"text": "Pasal 1 ..."},{ "text": "Pasal 2 ..."}],
        }


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


class PenelitiTests(unittest.TestCase):
    def test_canonical_probe_uris_tipikor(self) -> None:
        uris = _canonical_probe_uris(
            "respons legislatif atas vonis Kasus Ibam dan tindak pidana korupsi pengadaan Chromebook",
            ["korupsi sektor pendidikan"],
        )
        self.assertIn("akn/id/act/uu/1999/31", uris)
        self.assertIn("akn/id/act/uu/2001/20", uris)
        self.assertIn("akn/id/act/perpres/2018/16", uris)

    def test_canonical_probe_uris_dosen_welfare(self) -> None:
        uris = _canonical_probe_uris(
            "kerangka hukum penghasilan dan tunjangan dosen pasca Permendiktisaintek 52/2025",
            ["UU Guru dan Dosen", "tunjangan profesi dosen"],
        )
        self.assertIn("akn/id/act/uu/2005/14", uris)  # UU Guru dan Dosen
        self.assertIn("akn/id/act/uu/2012/12", uris)  # UU Pendidikan Tinggi (via 'dosen')

    def test_canonical_probe_uris_kesehatan_ppds(self) -> None:
        uris = _canonical_probe_uris(
            "perlindungan PPDS dan dokter internsip pasca UU 17/2023",
            ["status hukum tenaga kesehatan", "perundungan dokter residen"],
        )
        self.assertIn("akn/id/act/uu/2023/17", uris)  # UU Kesehatan
        self.assertIn("akn/id/act/pp/2024/28", uris)  # PP pelaksanaan
        self.assertIn("akn/id/act/uu/2013/20", uris)  # UU Pendidikan Kedokteran
        self.assertIn("akn/id/act/permenkes/2022/7", uris)  # Permenkes Internsip

    def test_canonical_probe_uris_tukin(self) -> None:
        uris = _canonical_probe_uris(
            "tunjangan kinerja ASN sektor pendidikan",
            ["tukin pegawai negeri"],
        )
        self.assertIn("akn/id/act/perpres/2025/19", uris)

    def test_canonical_probe_uris_no_match_for_unrelated_topic(self) -> None:
        uris = _canonical_probe_uris(
            "regulasi izin usaha pertambangan emas skala kecil",
            ["pertambangan rakyat"],
        )
        # None of the curated probes should fire for an unrelated topic.
        self.assertEqual(uris, [])

    def test_research_adds_exact_probe_hits(self) -> None:
        pool = FakePool(make_settings(), small_response=json.dumps(["korupsi sektor pendidikan"]))
        pasal = FakePasalClient()

        memo = research(
            pool,
            pasal,
            "respons legislatif atas vonis Kasus Ibam dan tindak pidana korupsi pengadaan Chromebook",
        )

        self.assertEqual(memo, "Memo hasil riset.")
        self.assertIn("akn/id/act/uu/1999/31", pasal.get_law_calls)
        self.assertIn("akn/id/act/uu/2001/20", pasal.get_law_calls)
        self.assertIn("source\": \"exact_probe\"", pool.big.calls[0][0][1]["content"])


if __name__ == "__main__":
    unittest.main()

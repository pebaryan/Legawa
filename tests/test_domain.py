from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.agents.domain import (
    DomainAnalysis,
    _parse_analysis,
    classify_domain,
    render_constraints,
)
from legawa.agents.penyusun import _derive_domain_constraints
from legawa.config import LLMConfig, Settings


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[list[dict], dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


class FakePool:
    def __init__(self, settings: Settings, small_response: str, big_response: str = ""):
        self.settings = settings
        self.small = FakeLLM(small_response)
        self.big = FakeLLM(big_response)


def make_settings() -> Settings:
    cfg = LLMConfig(
        base_url="http://example.invalid",
        api_key="x",
        model="qwen3",
        temperature=0.3,
        max_tokens=4096,
    )
    return Settings(
        pasal_token="t",
        pasal_base_url="http://pasal.invalid",
        big=cfg,
        small=cfg,
        run_date="2026-04-30",
        corpus_watermark="2026-04-30",
        strict_citations=True,
    )


VALID_K12_JSON = json.dumps(
    {
        "sektor_utama": "pendidikan_dasar_menengah",
        "jenjang": "dasar_menengah",
        "instansi_terkait": ["Kementerian Pendidikan Dasar dan Menengah", "Komisi X DPR RI"],
        "kasus_terkait": "Kasus Ibam",
        "kerangka_hukum_utama": [
            "Tipikor (UU 31/1999 jo UU 20/2001)",
            "Pengadaan Barang/Jasa (Perpres 16/2018 jo Perpres 12/2021)",
        ],
        "rangkuman_konteks": "Topik tentang akuntabilitas pengadaan teknologi pendidikan dasar/menengah.",
        "anti_drift": [
            "JANGAN bergeser ke pendidikan tinggi atau PTN.",
            "Fokus eksklusif pada jenjang SD/SMP/SMA.",
        ],
    }
)


VALID_KETENAGAKERJAAN_JSON = json.dumps(
    {
        "sektor_utama": "ketenagakerjaan",
        "jenjang": None,
        "instansi_terkait": ["Kementerian Ketenagakerjaan", "Komisi IX DPR RI"],
        "kasus_terkait": None,
        "kerangka_hukum_utama": ["Ketenagakerjaan (UU 13/2003)", "Cipta Kerja (UU 6/2023)"],
        "rangkuman_konteks": "Perlindungan pekerja alih daya pasca UU Cipta Kerja.",
        "anti_drift": ["Fokus pada hukum ketenagakerjaan."],
    }
)


class ParseAnalysisTests(unittest.TestCase):
    def test_parses_clean_json(self) -> None:
        analysis = _parse_analysis(VALID_K12_JSON)
        self.assertEqual(analysis.sektor_utama, "pendidikan_dasar_menengah")
        self.assertEqual(analysis.jenjang, "dasar_menengah")
        self.assertEqual(analysis.kasus_terkait, "Kasus Ibam")

    def test_strips_code_fence(self) -> None:
        wrapped = "```json\n" + VALID_K12_JSON + "\n```"
        analysis = _parse_analysis(wrapped)
        self.assertEqual(analysis.sektor_utama, "pendidikan_dasar_menengah")

    def test_isolates_object_when_model_prepends_text(self) -> None:
        wrapped = "Berikut hasil klasifikasi:\n" + VALID_KETENAGAKERJAAN_JSON + "\n\nDemikian."
        analysis = _parse_analysis(wrapped)
        self.assertEqual(analysis.sektor_utama, "ketenagakerjaan")
        self.assertIsNone(analysis.jenjang)


class ClassifyDomainTests(unittest.TestCase):
    def test_classify_returns_analysis_for_valid_response(self) -> None:
        pool = FakePool(make_settings(), small_response=VALID_K12_JSON)
        analysis = classify_domain(
            pool,
            "respons legislatif atas vonis Kasus Ibam dan akuntabilitas Program Digitalisasi Sekolah",
        )
        self.assertIsInstance(analysis, DomainAnalysis)
        self.assertEqual(analysis.sektor_utama, "pendidikan_dasar_menengah")
        self.assertIn("Komisi X DPR RI", analysis.instansi_terkait)

    def test_classify_raises_on_invalid_json(self) -> None:
        pool = FakePool(make_settings(), small_response="this is not json")
        with self.assertRaises(Exception):
            classify_domain(pool, "topik bebas")

    def test_classify_passes_research_and_extra_to_prompt(self) -> None:
        pool = FakePool(make_settings(), small_response=VALID_KETENAGAKERJAAN_JSON)
        classify_domain(
            pool,
            "regulasi outsourcing",
            research_block="UU 13/2003 mengatur outsourcing pasal 64-66.",
            extra_instructions="prioritaskan dapil Jawa Barat",
        )
        user_msg = pool.small.calls[0][0][1]["content"]
        self.assertIn("regulasi outsourcing", user_msg)
        self.assertIn("dapil Jawa Barat", user_msg)
        self.assertIn("UU 13/2003", user_msg)


class RenderConstraintsTests(unittest.TestCase):
    def test_renders_full_analysis(self) -> None:
        analysis = _parse_analysis(VALID_K12_JSON)
        rendered = render_constraints(analysis)
        self.assertIn("pendidikan_dasar_menengah", rendered)
        self.assertIn("dasar_menengah", rendered)
        self.assertIn("Komisi X DPR RI", rendered)
        self.assertIn("Kasus Ibam", rendered)
        self.assertIn("JANGAN bergeser ke pendidikan tinggi", rendered)


class DeriveDomainConstraintsTests(unittest.TestCase):
    def test_uses_classifier_output_when_valid(self) -> None:
        pool = FakePool(make_settings(), small_response=VALID_KETENAGAKERJAAN_JSON)
        constraints = _derive_domain_constraints(
            pool, "regulasi outsourcing pasca UU Cipta Kerja"
        )
        self.assertIn("ketenagakerjaan", constraints)
        self.assertIn("Komisi IX DPR RI", constraints)
        # SMALL was called once (the classifier).
        self.assertEqual(len(pool.small.calls), 1)

    def test_falls_back_to_keyword_anchor_when_classifier_fails(self) -> None:
        pool = FakePool(make_settings(), small_response="not json at all")
        constraints = _derive_domain_constraints(
            pool, "respons atas pengadaan Chromebook sekolah dasar"
        )
        # Classifier ran, failed, fell back to keyword. Keyword path emits this.
        self.assertIn("pendidikan dasar/menengah", constraints)

    def test_case_facts_prepended_alongside_classifier(self) -> None:
        # Both the keyword-based case-fact override AND the classifier should fire
        # for a Kasus Ibam topic.
        pool = FakePool(make_settings(), small_response=VALID_K12_JSON)
        constraints = _derive_domain_constraints(
            pool,
            "respons legislatif atas vonis Kasus Ibam dan akuntabilitas Program Digitalisasi Sekolah",
        )
        # Authoritative case-fact block (always applied for known cases):
        self.assertIn("FAKTA KASUS IBAM", constraints)
        self.assertIn("Ibrahim Arief", constraints)
        # Classifier output is also present:
        self.assertIn("pendidikan_dasar_menengah", constraints)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.agents.penyusun import draft
from legawa.agents.surat import format_report, reply
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
    def __init__(self, searchable_refs: set[str]):
        self.searchable_refs = searchable_refs
        self.calls: list[dict] = []

    def search(self, q=None, **kwargs):
        if q is not None:
            kwargs["q"] = q
        self.calls.append(kwargs)
        ref = kwargs["q"]
        if ref not in self.searchable_refs:
            return {"results": []}
        if ref == "UUD 1945":
            return {
                "results": [
                    {
                        "title": "Undang-Undang Dasar 1945",
                        "frbr_uri": "akn/id/act/constitution/1945/1945",
                        "status": "berlaku",
                    }
                ]
            }
        kind, number_year = ref.split(" ", 1)
        number, year = number_year.split("/")
        kind_map = {
            "UU": "uu",
            "PP": "pp",
            "Perpres": "perpres",
            "Perda": "perda",
            "Permenaker": "permenaker",
            "Permendikbudristek": "permen",
        }
        return {
            "results": [
                {
                    "title": f"{kind} Nomor {number} Tahun {year}",
                    "frbr_uri": f"akn/id/act/{kind_map.get(kind, kind.lower())}/{year}/{number}",
                    "status": "berlaku",
                }
            ]
        }

    def get_law(self, frbr_uri: str):
        return {"title": frbr_uri, "frbr_uri": frbr_uri, "status": "berlaku", "articles": []}


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


class WhitepaperRegressionTests(unittest.TestCase):
    def test_outsourcing_fixture_reply_pipeline(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "surat-buruh-outsourcing.txt").read_text(encoding="utf-8")
        triase = json.dumps(
            {
                "kategori": "aspirasi_kebijakan",
                "urgensi": "tinggi",
                "sentimen": "marah",
                "dapil_relevance": True,
                "nama_pengirim": "Sukma Wijayanti",
                "lokasi": "Cikarang, Bekasi, Jawa Barat",
                "isu_utama": "Pekerja outsourcing terdampak regulasi baru dan perlindungan kerja melemah.",
                "permintaan_konkret": ["RDP", "Dukungan revisi UU", "Dialog dengan pekerja"],
                "peraturan_disebut": ["UU 13/2003", "UU 6/2023", "Perpres 16/2018", "Perpres 12/2021", "UUD 1945"],
                "perlu_tindak_lanjut_staf": True,
                "rangkuman": "Surat ini menyampaikan dampak regulasi outsourcing terhadap pekerja pabrik di Cikarang.",
            }
        )
        pool = FakePool(
            make_settings(),
            small_response=triase,
            big_response=(
                "## Balasan\n"
                "Kami akan menindaklanjuti isu ini dalam kerangka UU 13/2003, UU 6/2023, "
                "Perpres 16/2018, Perpres 12/2021, dan UUD 1945."
            ),
        )
        pasal = FakePasalClient({"UU 13/2003", "UU 6/2023", "Perpres 16/2021", "Perpres 12/2021", "UUD 1945", "Perpres 16/2018"})

        result = reply(pool, pasal, source, verify_law=True)
        report = format_report(result)

        self.assertIn("## Balasan", report)
        self.assertIn("UU 13/2003", report)
        self.assertIn("Perpres 12/2021", report)
        self.assertNotIn("Perpres 76/2021", report)

    def test_chromebook_fixture_draft_keeps_k12_domain(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "surat-chromebook-sekolah.txt").read_text(encoding="utf-8")
        pool = FakePool(
            make_settings(),
            small_response='["korupsi sektor pendidikan"]',
            big_response=(
                "# Memo Kebijakan\n"
                "Tanggal: 30 April 2026\n"
                "Fokus: pengadaan sekolah dasar, bukan perguruan tinggi.\n"
                "Rujukan: UU 31/1999, UU 20/2001, Perpres 16/2018, Perpres 12/2021."
            ),
        )
        pasal = FakePasalClient({"UU 31/1999", "UU 20/2001", "Perpres 16/2018", "Perpres 12/2021"})

        with patch("legawa.agents.penyusun.peneliti.research", return_value="Memo basis hukum untuk K-12 dan pengadaan sekolah dasar."):
            output = draft(
                pool,
                pasal,
                kind="memo_kebijakan",
                topic="respons legislatif atas vonis Kasus Ibam dan permintaan akuntabilitas Program Digitalisasi Sekolah",
                with_research=True,
                extra_instructions=source[:200],
            )

        system_prompt = pool.big.calls[0][0][0]["content"]
        self.assertIn("pendidikan dasar/menengah", system_prompt)
        self.assertIn("Tanggal penyusunan: 2026-04-30", system_prompt)
        self.assertIn("UU 31/1999", output)
        self.assertIn("Perpres 16/2018", output)
        self.assertNotIn("Perguruan Tinggi", output)

    def test_ibam_it_fixture_keeps_technical_audit_frame(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "ibam-it-audit-perspective.txt").read_text(encoding="utf-8")
        pool = FakePool(
            make_settings(),
            small_response='["audit teknis pengadaan Chromebook"]',
            big_response=(
                "# Memo Teknis\n"
                "Kami menilai serial number, audit trail, CDM license history, firmware, dan MDM policy.\n"
                "Rujukan: UU 31/1999, UU 20/2001, Perpres 16/2018."
            ),
        )
        pasal = FakePasalClient({"UU 31/1999", "UU 20/2001", "Perpres 16/2018"})

        with patch("legawa.agents.penyusun.peneliti.research", return_value="Basis hukum untuk audit teknis pengadaan Chromebook dan dokumentasi TI."):
            output = draft(
                pool,
                pasal,
                kind="memo_kebijakan",
                topic="audit teknis dan tata kelola perangkat digital pada Kasus Ibam",
                with_research=True,
                extra_instructions=source,
            )

        system_prompt = pool.big.calls[0][0][0]["content"]
        user_prompt = pool.big.calls[0][0][1]["content"]
        self.assertIn("audit teknis", system_prompt)
        self.assertIn("forensik digital", system_prompt)
        self.assertIn("teknologi informasi", user_prompt.lower())
        self.assertIn("UU 31/1999", output)
        self.assertIn("CDM license history", output)
        self.assertNotIn("Perguruan Tinggi", output)
        self.assertNotIn("exoneration", output.lower())


if __name__ == "__main__":
    unittest.main()

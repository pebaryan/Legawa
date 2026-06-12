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
from legawa.tools.citations import extract_citations


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
    def _assert_reply_to_memo_fixture_case(
        self,
        *,
        fixture_name: str,
        triase: dict,
        expected_commission: str,
        expected_phrase: str,
        memo_topic: str,
        domain_sector: str,
        related_institutions: list[str],
    ) -> None:
        source = (ROOT / "tests" / "fixtures" / fixture_name).read_text(encoding="utf-8")
        triase_refs = set(triase["peraturan_disebut"])
        fixture_refs = set(extract_citations(source))
        self.assertTrue(
            triase_refs.issubset(fixture_refs),
            f"{fixture_name} triase refs not present in fixture text: {sorted(triase_refs - fixture_refs)}",
        )
        refs_text = ", ".join(triase["peraturan_disebut"])
        pool = FakePool(
            make_settings(),
            small_response=json.dumps(triase),
            big_response=(
                f"## Balasan\n{expected_commission} akan menindaklanjuti {expected_phrase}. "
                f"Rujukan: {refs_text}."
            ),
        )
        pasal = FakePasalClient(triase_refs)

        result = reply(pool, pasal, source, verify_law=True)
        report = format_report(result)

        self.assertEqual(pool.small.calls[0][0][1]["content"], source)
        self.assertIn(expected_commission, report)
        self.assertIn(expected_phrase, report)
        self.assertGreater(len(pasal.calls), 0)

        pool.small.response = json.dumps(
            {
                "sektor_utama": domain_sector,
                "jenjang": "dasar_menengah" if domain_sector == "pendidikan_dasar_menengah" else None,
                "instansi_terkait": related_institutions,
                "kasus_terkait": None,
                "kerangka_hukum_utama": list(triase["peraturan_disebut"]),
                "rangkuman_konteks": triase["rangkuman"],
                "anti_drift": [f"Fokus pada {expected_phrase}; jangan bergeser ke komisi atau sektor lain."],
            }
        )
        pool.big.response = (
            f"# Memo Kebijakan\n{expected_commission} perlu mengawal {expected_phrase}. "
            f"Rujukan: {refs_text}."
        )

        with patch(
            "legawa.agents.penyusun.peneliti.research",
            return_value=f"Basis riset untuk {memo_topic}: {refs_text}.",
        ):
            memo = draft(
                pool,
                pasal,
                kind="memo_kebijakan",
                topic=memo_topic,
                with_research=True,
                extra_instructions=report,
            )

        self.assertIn(expected_commission, memo)
        self.assertIn(expected_phrase, memo)
        self.assertIn("Instruksi tambahan:", pool.big.calls[-1][0][1]["content"])
        self.assertGreaterEqual(len(pool.big.calls), 2)

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

    def test_all_surat_fixtures_reply_to_memo_pipeline(self) -> None:
        cases = [
            {
                "fixture_name": "surat-agraria-reforma-tanah-adat.txt",
                "expected_commission": "Komisi II",
                "expected_phrase": "reforma agraria",
                "memo_topic": "memo kebijakan reforma agraria dan pengakuan tanah adat",
                "domain_sector": "agraria_pertanahan",
                "related_institutions": ["Komisi II DPR RI", "Kementerian ATR/BPN"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "tinggi",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Perwakilan Komunitas",
                    "lokasi": "Kabupaten",
                    "isu_utama": "Komunitas adat meminta kepastian tanah dan reforma agraria.",
                    "permintaan_konkret": ["Verifikasi bidang tanah", "RDP dengan ATR/BPN"],
                    "peraturan_disebut": ["UU 5/1960"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat memohon penyelesaian sengketa agraria dan kepastian hak atas tanah.",
                },
            },
            {
                "fixture_name": "surat-bencana-anak-bantuan-sosial.txt",
                "expected_commission": "Komisi VIII",
                "expected_phrase": "bantuan sosial",
                "memo_topic": "memo kebijakan bantuan sosial dan perlindungan kelompok rentan pascabencana",
                "domain_sector": "sosial_kemasyarakatan",
                "related_institutions": ["Komisi VIII DPR RI", "Kementerian Sosial", "BNPB", "Kementerian PPPA"],
                "triase": {
                    "kategori": "pengaduan_layanan",
                    "urgensi": "tinggi",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Relawan Posko Banjir Mutiara",
                    "lokasi": "Mutiara",
                    "isu_utama": "Relawan meminta distribusi bantuan sosial dan perlindungan kelompok rentan di pengungsian.",
                    "permintaan_konkret": ["RDP Komisi VIII", "Audit data bansos", "Standar posko ramah kelompok rentan"],
                    "peraturan_disebut": ["UU 24/2007", "UU 11/2009", "UU 35/2014", "UU 23/2004"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti penanggulangan bencana, bantuan sosial, perlindungan anak, dan risiko kekerasan domestik.",
                },
            },
            {
                "fixture_name": "surat-bekasi-kereta-taksi.txt",
                "expected_commission": "Komisi V",
                "expected_phrase": "perlintasan sebidang",
                "memo_topic": "memo kebijakan keselamatan perlintasan sebidang dan taksi listrik Bekasi",
                "domain_sector": "infrastruktur",
                "related_institutions": ["Komisi V DPR RI", "Kementerian Perhubungan", "Pemerintah Kota Bekasi"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "tinggi",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Warga Bekasi",
                    "lokasi": "Bekasi, Jawa Barat",
                    "isu_utama": "Warga meminta keselamatan perlintasan sebidang dan tata kelola taksi listrik.",
                    "permintaan_konkret": ["Audit keselamatan perlintasan", "Koordinasi Kemenhub", "RDP Komisi V"],
                    "peraturan_disebut": ["UU 22/2009", "Permen 22/2009", "UU 23/2007", "Perpres 55/2019", "UU 33/1964", "UU 34/1964"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti keselamatan transportasi darat dan konektivitas warga Bekasi.",
                },
            },
            {
                "fixture_name": "surat-bumn-konsumen-standardisasi.txt",
                "expected_commission": "Komisi VI",
                "expected_phrase": "perlindungan konsumen",
                "memo_topic": "memo kebijakan layanan BUMN, perlindungan konsumen, dan standardisasi logistik",
                "domain_sector": "ekonomi_perdagangan",
                "related_institutions": ["Komisi VI DPR RI", "Kementerian BUMN", "Kementerian Perdagangan", "Badan Standardisasi Nasional"],
                "triase": {
                    "kategori": "pengaduan_layanan",
                    "urgensi": "sedang",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Forum Konsumen Pelabuhan Timur",
                    "lokasi": "Pelabuhan Timur",
                    "isu_utama": "Konsumen meminta transparansi tarif dan standar layanan BUMN logistik.",
                    "permintaan_konkret": ["RDP Komisi VI", "Audit layanan BUMN", "Skema kompensasi konsumen"],
                    "peraturan_disebut": ["UU 8/1999", "UU 19/2003", "UU 7/2014", "UU 20/2014"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti perdagangan, BUMN, perlindungan konsumen, dan standardisasi layanan logistik.",
                },
            },
            {
                "fixture_name": "surat-buruh-outsourcing.txt",
                "expected_commission": "Komisi IX",
                "expected_phrase": "outsourcing",
                "memo_topic": "memo kebijakan perlindungan pekerja outsourcing pasca UU Cipta Kerja",
                "domain_sector": "ketenagakerjaan",
                "related_institutions": ["Komisi IX DPR RI", "Kementerian Ketenagakerjaan"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "tinggi",
                    "sentimen": "marah",
                    "dapil_relevance": True,
                    "nama_pengirim": "Sukma Wijayanti",
                    "lokasi": "Cikarang, Bekasi, Jawa Barat",
                    "isu_utama": "Pekerja outsourcing terdampak regulasi baru dan perlindungan kerja melemah.",
                    "permintaan_konkret": ["RDP", "Dukungan revisi UU", "Dialog dengan pekerja"],
                    "peraturan_disebut": ["UU 13/2003", "UU 6/2023", "UUD 1945"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat ini menyampaikan dampak regulasi outsourcing terhadap pekerja pabrik di Cikarang.",
                },
            },
            {
                "fixture_name": "surat-chromebook-sekolah.txt",
                "expected_commission": "Komisi X",
                "expected_phrase": "Chromebook",
                "memo_topic": "memo kebijakan akuntabilitas pengadaan Chromebook sekolah",
                "domain_sector": "pendidikan_dasar_menengah",
                "related_institutions": ["Komisi X DPR RI", "Kementerian Pendidikan Dasar dan Menengah", "LKPP"],
                "triase": {
                    "kategori": "pengaduan_layanan",
                    "urgensi": "tinggi",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Forum Orang Tua Murid",
                    "lokasi": "Kabupaten",
                    "isu_utama": "Orang tua meminta akuntabilitas pengadaan Chromebook untuk sekolah dasar dan menengah.",
                    "permintaan_konkret": ["Audit pengadaan", "Pengawasan Komisi X", "Perbaikan distribusi perangkat"],
                    "peraturan_disebut": ["Perpres 16/2018", "Perpres 12/2021"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti pengadaan perangkat digital sekolah dan tata kelola barang/jasa.",
                },
            },
            {
                "fixture_name": "surat-diplomasi-wni-gaza.txt",
                "expected_commission": "Komisi I",
                "expected_phrase": "perlindungan WNI",
                "memo_topic": "memo kebijakan perlindungan WNI di wilayah konflik",
                "domain_sector": "pertahanan_keamanan",
                "related_institutions": ["Komisi I DPR RI", "Kementerian Luar Negeri"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "tinggi",
                    "sentimen": "negatif",
                    "dapil_relevance": False,
                    "nama_pengirim": "Nadia Rahman",
                    "lokasi": "Jakarta",
                    "isu_utama": "Keluarga meminta kepastian perlindungan WNI di wilayah konflik.",
                    "permintaan_konkret": ["Koordinasi diplomatik", "Evakuasi WNI", "RDP Komisi I"],
                    "peraturan_disebut": ["UUD 1945", "UU 37/1999", "UU 24/2000"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat meminta pengawasan diplomatik dan perlindungan WNI di luar negeri.",
                },
            },
            {
                "fixture_name": "surat-gaji-tunjangan-dosen.txt",
                "expected_commission": "Komisi X",
                "expected_phrase": "tunjangan dosen",
                "memo_topic": "memo kebijakan gaji dan tunjangan dosen",
                "domain_sector": "pendidikan_tinggi",
                "related_institutions": ["Komisi X DPR RI", "Kementerian Pendidikan Tinggi, Sains, dan Teknologi"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "sedang",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Ikatan Dosen Muda",
                    "lokasi": "Yogyakarta",
                    "isu_utama": "Dosen meminta kepastian gaji, tunjangan profesi, dan tunjangan kehormatan.",
                    "permintaan_konkret": ["RDP Komisi X", "Evaluasi tunjangan", "Koordinasi kementerian"],
                    "peraturan_disebut": ["Permen 52/2025", "Perpres 19/2025", "UU 14/2005", "PP 37/2009", "PP 41/2009"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti kesejahteraan dosen dan kepastian pelaksanaan tunjangan pendidikan tinggi.",
                },
            },
            {
                "fixture_name": "surat-imigrasi-ham-pengungsi.txt",
                "expected_commission": "Komisi XIII",
                "expected_phrase": "pengungsi",
                "memo_topic": "memo kebijakan perlindungan pengungsi dan tata kelola imigrasi",
                "domain_sector": "sosial_kemasyarakatan",
                "related_institutions": ["Komisi XIII DPR RI", "Kementerian Imigrasi dan Pemasyarakatan", "Komnas HAM"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "sedang",
                    "sentimen": "negatif",
                    "dapil_relevance": False,
                    "nama_pengirim": "Jaringan Pendamping",
                    "lokasi": "Jakarta",
                    "isu_utama": "Pendamping meminta perlakuan manusiawi bagi pengungsi dan pencari suaka.",
                    "permintaan_konkret": ["Standar detensi", "Akses bantuan hukum", "RDP Komisi XIII"],
                    "peraturan_disebut": ["UU 6/2011", "UU 39/1999"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti imigrasi, HAM, dan layanan bagi pengungsi.",
                },
            },
            {
                "fixture_name": "surat-ketahanan-pangan-irigasi-gabah.txt",
                "expected_commission": "Komisi IV",
                "expected_phrase": "ketahanan pangan",
                "memo_topic": "memo kebijakan ketahanan pangan, irigasi, dan stabilisasi gabah",
                "domain_sector": "sosial_kemasyarakatan",
                "related_institutions": ["Komisi IV DPR RI", "Kementerian Pertanian", "Badan Pangan Nasional"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "sedang",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Kelompok Tani",
                    "lokasi": "Kabupaten",
                    "isu_utama": "Petani meminta perbaikan irigasi dan stabilisasi harga gabah.",
                    "permintaan_konkret": ["Perbaikan irigasi", "Pengawasan pupuk", "RDP Komisi IV"],
                    "peraturan_disebut": ["UU 18/2012", "UU 41/2009"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti ketahanan pangan, irigasi, dan perlindungan lahan sawah.",
                },
            },
            {
                "fixture_name": "surat-mbg-keracunan-grobogan.txt",
                "expected_commission": "Komisi IX",
                "expected_phrase": "keracunan MBG",
                "memo_topic": "memo kebijakan keselamatan pangan program MBG pasca keracunan Grobogan",
                "domain_sector": "kesehatan",
                "related_institutions": ["Komisi IX DPR RI", "Kementerian Kesehatan", "Badan Gizi Nasional", "BPOM"],
                "triase": {
                    "kategori": "pengaduan_layanan",
                    "urgensi": "tinggi",
                    "sentimen": "marah",
                    "dapil_relevance": True,
                    "nama_pengirim": "Forum Wali Murid",
                    "lokasi": "Grobogan, Jawa Tengah",
                    "isu_utama": "Wali murid meminta evaluasi keselamatan pangan setelah kasus keracunan MBG.",
                    "permintaan_konkret": ["Investigasi keracunan", "Audit dapur SPPG", "RDP Komisi IX"],
                    "peraturan_disebut": ["Perpres 83/2024", "Perpres 115/2025", "UU 18/2012", "UU 17/2023", "Perpres 16/2018", "Perpres 12/2021", "UU 8/1999"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti keselamatan pangan, pengawasan vendor, dan akuntabilitas program Makan Bergizi Gratis.",
                },
            },
            {
                "fixture_name": "surat-penegakan-hukum-korupsi-daerah.txt",
                "expected_commission": "Komisi III",
                "expected_phrase": "penegakan hukum",
                "memo_topic": "memo kebijakan pengawasan penegakan hukum dan supervisi korupsi daerah",
                "domain_sector": "hukum_tipikor",
                "related_institutions": ["Komisi III DPR RI", "Kepolisian RI", "Kejaksaan Agung", "KPK"],
                "triase": {
                    "kategori": "pengaduan_layanan",
                    "urgensi": "tinggi",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Koalisi Warga Anti-Korupsi Daerah",
                    "lokasi": "Kabupaten Serayu",
                    "isu_utama": "Warga meminta pengawasan penegakan hukum atas laporan dugaan korupsi daerah.",
                    "permintaan_konkret": ["RDP Komisi III", "Supervisi KPK", "Perlindungan pelapor"],
                    "peraturan_disebut": ["UU 8/1981", "UU 31/1999", "UU 20/2001", "UU 30/2002", "UU 19/2019"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti supervisi laporan korupsi daerah, perlindungan pelapor, dan transparansi perkembangan perkara.",
                },
            },
            {
                "fixture_name": "surat-perbankan-pajak-umkm.txt",
                "expected_commission": "Komisi XI",
                "expected_phrase": "inklusi keuangan",
                "memo_topic": "memo kebijakan perlindungan nasabah UMKM, perbankan digital, dan edukasi pajak",
                "domain_sector": "fiskal_anggaran",
                "related_institutions": ["Komisi XI DPR RI", "OJK", "Bank Indonesia", "Kementerian Keuangan"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "sedang",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Asosiasi Warung Digital Nusantara",
                    "lokasi": "Nasional",
                    "isu_utama": "UMKM meminta perlindungan rekening usaha, edukasi pajak, dan literasi keuangan.",
                    "permintaan_konkret": ["RDP Komisi XI", "Standar pembekuan rekening", "Edukasi pajak komunitas"],
                    "peraturan_disebut": ["UU 4/2023", "UU 21/2011", "UU 7/2021", "UU 23/1999"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti perbankan digital, pengawasan OJK, kebijakan pajak UMKM, dan stabilitas sistem pembayaran.",
                },
            },
            {
                "fixture_name": "surat-ppds-internsip-dokter.txt",
                "expected_commission": "Komisi IX",
                "expected_phrase": "PPDS",
                "memo_topic": "memo kebijakan perlindungan dokter PPDS dan internsip",
                "domain_sector": "kesehatan",
                "related_institutions": ["Komisi IX DPR RI", "Kementerian Kesehatan", "Konsil Kedokteran Indonesia"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "tinggi",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Koalisi Dokter Muda",
                    "lokasi": "Surabaya",
                    "isu_utama": "Dokter muda meminta perlindungan peserta PPDS dan kejelasan program internsip.",
                    "permintaan_konkret": ["Evaluasi PPDS", "Perlindungan peserta", "RDP Komisi IX"],
                    "peraturan_disebut": ["UU 17/2023", "PP 28/2024", "Permenkes 7/2022", "Permen 7/2022", "UU 20/2013"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti pendidikan dokter spesialis, internsip, dan perlindungan tenaga medis muda.",
                },
            },
            {
                "fixture_name": "surat-transisi-energi-nikel-lingkungan.txt",
                "expected_commission": "Komisi XII",
                "expected_phrase": "transisi energi",
                "memo_topic": "memo kebijakan transisi energi, nikel, dan perlindungan lingkungan",
                "domain_sector": "lingkungan_hidup",
                "related_institutions": ["Komisi XII DPR RI", "Kementerian ESDM", "Kementerian Lingkungan Hidup"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "tinggi",
                    "sentimen": "negatif",
                    "dapil_relevance": True,
                    "nama_pengirim": "Warga Pesisir",
                    "lokasi": "Sulawesi",
                    "isu_utama": "Warga meminta pengawasan tambang nikel dan perlindungan lingkungan.",
                    "permintaan_konkret": ["Audit izin", "Reklamasi", "RDP Komisi XII"],
                    "peraturan_disebut": ["UU 30/2007", "UU 3/2020", "UU 32/2009"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat menyoroti transisi energi, tambang nikel, dan dampak lingkungan pesisir.",
                },
            },
            {
                "fixture_name": "surat-umkm-standardisasi-produk.txt",
                "expected_commission": "Komisi VII",
                "expected_phrase": "UMKM",
                "memo_topic": "memo kebijakan standardisasi produk dan daya saing UMKM",
                "domain_sector": "ekonomi_perdagangan",
                "related_institutions": ["Komisi VII DPR RI", "Kementerian UMKM", "Badan Standardisasi Nasional"],
                "triase": {
                    "kategori": "aspirasi_kebijakan",
                    "urgensi": "sedang",
                    "sentimen": "netral",
                    "dapil_relevance": True,
                    "nama_pengirim": "Forum UMKM",
                    "lokasi": "Bandung",
                    "isu_utama": "UMKM meminta pendampingan standardisasi dan akses pasar.",
                    "permintaan_konkret": ["Pendampingan sertifikasi", "Akses promosi", "RDP Komisi VII"],
                    "peraturan_disebut": ["UU 20/2008", "UU 20/2014"],
                    "perlu_tindak_lanjut_staf": True,
                    "rangkuman": "Surat meminta penguatan UMKM melalui standardisasi produk dan pembiayaan.",
                },
            },
        ]

        expected_fixtures = {case["fixture_name"] for case in cases}
        actual_fixtures = {path.name for path in (ROOT / "tests" / "fixtures").glob("surat-*.txt")}
        self.assertEqual(expected_fixtures, actual_fixtures)

        expected_commissions = {
            "Komisi I",
            "Komisi II",
            "Komisi III",
            "Komisi IV",
            "Komisi V",
            "Komisi VI",
            "Komisi VII",
            "Komisi VIII",
            "Komisi IX",
            "Komisi X",
            "Komisi XI",
            "Komisi XII",
            "Komisi XIII",
        }
        covered_commissions = {case["expected_commission"] for case in cases}
        self.assertEqual(expected_commissions, covered_commissions)

        for case in cases:
            with self.subTest(fixture=case["fixture_name"], commission=case["expected_commission"]):
                self._assert_reply_to_memo_fixture_case(**case)


if __name__ == "__main__":
    unittest.main()

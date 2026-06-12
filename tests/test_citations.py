from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.tools.citations import (
    CitationCheck,
    _topics_overlap,
    extract_citations,
    format_checks,
    verify_citation,
    verify_citations,
)
from legawa.tools.trusted_recent import TRUSTED_RECENT, validate_trusted_entry  # noqa: E402


class FakePasalClient:
    def __init__(self, responses: dict[str, dict], laws: dict[str, dict] | None = None):
        self.responses = responses
        self.laws = laws or {}
        self.calls: list[tuple[dict, ...]] = []
        self.get_law_calls: list[str] = []

    def search(self, **kwargs):
        self.calls.append((kwargs,))
        return self.responses.get(kwargs["q"], {"results": []})

    def get_law(self, frbr_uri: str):
        self.get_law_calls.append(frbr_uri)
        if frbr_uri not in self.laws:
            raise KeyError(f"no fixture for {frbr_uri}")
        return self.laws[frbr_uri]


class CitationTests(unittest.TestCase):
    def test_extract_citations_normalizes_common_forms(self) -> None:
        text = (
            "Mengacu pada UU No. 13 Tahun 2003, Peraturan Presiden Nomor 12 Tahun 2021, "
            "UUD 1945 Pasal 28E, Peraturan Pemerintah Pengganti Undang-Undang Nomor 2 Tahun 2023, "
            "Perda Provinsi Jawa Barat Nomor 1 Tahun 2024, dan akn/id/act/pp/2021/35."
        )

        self.assertEqual(
            extract_citations(text),
            ["UU 13/2003", "Perpres 12/2021", "UUD 1945", "Perppu 2/2023", "Perda 1/2024", "PP 35/2021"],
        )

    def test_verify_citation_matches_title_and_frbr_uri(self) -> None:
        fake = FakePasalClient(
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

        check = verify_citation(fake, "UU No. 13 Tahun 2003")
        self.assertTrue(check.found)
        self.assertEqual(check.reference, "UU 13/2003")
        self.assertEqual(check.frbr_uri, "akn/id/act/uu/2003/13")
        self.assertEqual(check.status, "berlaku")

    def test_verify_citation_supports_perppu_and_region_perda(self) -> None:
        fake = FakePasalClient(
            {
                "Perppu 2/2023": {
                    "results": [
                        {
                            "title": "Peraturan Pemerintah Pengganti Undang-Undang Nomor 2 Tahun 2023",
                            "frbr_uri": "akn/id/act/perppu/2023/2",
                            "status": "berlaku",
                        }
                    ]
                },
                "Perda 1/2024": {
                    "results": [
                        {
                            "title": "Peraturan Daerah Provinsi Jawa Barat Nomor 1 Tahun 2024",
                            "frbr_uri": "akn/id/act/perda/2024/1",
                            "status": "berlaku",
                        }
                    ]
                },
            }
        )

        perppu = verify_citation(fake, "Perppu Nomor 2 Tahun 2023")
        perda = verify_citation(fake, "Perda Provinsi Jawa Barat Nomor 1 Tahun 2024")

        self.assertTrue(perppu.found)
        self.assertEqual(perppu.query, "Perppu 2/2023")
        self.assertEqual(perppu.frbr_uri, "akn/id/act/perppu/2023/2")

        self.assertTrue(perda.found)
        self.assertEqual(perda.query, "Perda 1/2024")
        self.assertEqual(perda.frbr_uri, "akn/id/act/perda/2024/1")

    def test_topics_overlap_rejects_institutional_only_match(self) -> None:
        # Real false-positive case from gemma4 memo run: model claimed
        # Permen 24/2018 was about audit-mechanism, but it's about Pengelolaan
        # Arsip. They share only ministry-context tokens.
        claim = "Mekanisme Tindak Lanjut Hasil Audit Inspektorat Jenderal Kementerian Pendidikan dan Kebudayaan"
        title = "Pengelolaan Arsip Terjaga di Lingkungan Kementerian Pendidikan dan Kebudayaan"
        self.assertFalse(_topics_overlap(claim, title))

    def test_topics_overlap_accepts_real_topical_match(self) -> None:
        claim = "Pengadaan Barang/Jasa Pemerintah"
        title = "Peraturan Presiden Nomor 12 Tahun 2021 tentang Perubahan Atas Pengadaan Barang/Jasa Pemerintah"
        self.assertTrue(_topics_overlap(claim, title))

    def test_topics_overlap_acronym_vs_spelled_out_still_works(self) -> None:
        # Ensure the institutional filter doesn't break the acronym path —
        # UU 17/2014 is genuinely about MPR/DPR/DPD/DPRD.
        claim = "MPR, DPR, DPD, dan DPRD"
        title = "Majelis Permusyawaratan Rakyat, Dewan Perwakilan Rakyat, Dewan Perwakilan Daerah, dan Dewan Perwakilan Rakyat Daerah"
        self.assertTrue(_topics_overlap(claim, title))

    def test_extract_citations_handles_kemenhub_pm_prefix(self) -> None:
        # Kemenhub uses "PM <n> Tahun YYYY" as its internal numbering. Without
        # this case the verifier would silently miss every Permenhub citation
        # in agent output.
        text = (
            "Permenhub No. PM 94 Tahun 2018 tentang Perlintasan Sebidang. "
            "Lihat juga Permenhub PM 36/2011 dan Peraturan Menteri Perhubungan "
            "Nomor PM 73 Tahun 2018."
        )
        cites = extract_citations(text)
        self.assertIn("Permen 94/2018", cites)
        self.assertIn("Permen 36/2011", cites)
        self.assertIn("Permen 73/2018", cites)

    def test_topics_overlap_uninformative_title_falls_back(self) -> None:
        # Echoed pasal.id title — no usable signal — accept by existence-only.
        claim = "Sistem Pendidikan Nasional"
        title = "Undang-Undang Nomor 20 Tahun 2003 tentang Undang-Undang Nomor 20 Tahun 2003"
        self.assertTrue(_topics_overlap(claim, title))

    def test_verify_citation_advises_on_repealed_regulation(self) -> None:
        # When pasal.id reports a 'Dicabut oleh' relationship to a NEWER
        # regulation, surface as an advisory note. We do NOT reject the
        # citation outright because pasal.id's relationships graph
        # mis-classifies some cross-references (false positives would block
        # legitimate canonical statutes like UU 31/1999).
        fake = FakePasalClient(
            responses={
                "UU 22/1999": {
                    "results": [
                        {
                            "title": "Undang-Undang Nomor 22 Tahun 1999 tentang Pemerintahan Daerah",
                            "frbr_uri": "akn/id/act/uu/1999/22",
                            "status": "berlaku",  # pasal.id status field is unreliable
                        }
                    ]
                }
            },
            laws={
                "akn/id/act/uu/1999/22": {
                    "title": "Undang-Undang Nomor 22 Tahun 1999 tentang Pemerintahan Daerah",
                    "frbr_uri": "akn/id/act/uu/1999/22",
                    "status": "berlaku",
                    "relationships": [
                        {
                            "type": "Dicabut oleh",
                            "type_en": "Repealed by",
                            "related_work": {
                                "title": "Undang-Undang Nomor 32 Tahun 2004 tentang Pemerintahan Daerah",
                                "frbr_uri": "/akn/id/act/uu/2004/32",
                            },
                        }
                    ],
                }
            },
        )

        check = verify_citation(fake, "UU 22/1999", claimed_topic="Pemerintahan Daerah")
        self.assertTrue(check.found)
        self.assertEqual(check.reason_code, "matched")
        self.assertIn("repealed_suspected", check.flags)
        self.assertIn("Dicabut oleh", check.note or "")
        self.assertIn("Undang-Undang Nomor 32 Tahun 2004", check.note or "")
        self.assertIn("akn/id/act/uu/2004/32", check.note or "")
        self.assertIn("verifikasi manual", check.note or "")

    def test_verify_citation_ignores_mirrored_predecessor_relationship(self) -> None:
        # pasal.id mirrors relationships in both directions. UU 13/2003
        # genuinely revokes UU 25/1997, but pasal.id also lists UU 25/1997
        # under UU 13/2003's "Dicabut oleh". The disambiguator must skip
        # mirrored entries where the related work is OLDER than the cited
        # regulation.
        fake = FakePasalClient(
            responses={
                "UU 13/2003": {
                    "results": [
                        {
                            "title": "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
                            "frbr_uri": "akn/id/act/uu/2003/13",
                            "status": "berlaku",
                        }
                    ]
                }
            },
            laws={
                "akn/id/act/uu/2003/13": {
                    "title": "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
                    "frbr_uri": "akn/id/act/uu/2003/13",
                    "status": "berlaku",
                    "relationships": [
                        # The mirrored predecessor — should be ignored.
                        {
                            "type": "Dicabut oleh",
                            "type_en": "Repealed by",
                            "related_work": {
                                "title": "UU 25/1997",
                                "frbr_uri": "/akn/id/act/uu/1997/25",
                            },
                        },
                    ],
                }
            },
        )

        check = verify_citation(fake, "UU 13/2003", claimed_topic="Ketenagakerjaan")
        self.assertTrue(check.found)
        # No advisory should fire — the mirrored predecessor is filtered.
        self.assertIsNone(check.note)

    def test_verify_citation_warns_on_amended_regulation(self) -> None:
        # Real case: UU 13/2003 (Ketenagakerjaan) is 'Diubah oleh' UU 6/2023.
        # Citation should still pass (regulation is operative in modified form),
        # but with an advisory note.
        fake = FakePasalClient(
            responses={
                "UU 13/2003": {
                    "results": [
                        {
                            "title": "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
                            "frbr_uri": "akn/id/act/uu/2003/13",
                            "status": "berlaku",
                        }
                    ]
                }
            },
            laws={
                "akn/id/act/uu/2003/13": {
                    "title": "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
                    "frbr_uri": "akn/id/act/uu/2003/13",
                    "status": "berlaku",
                    "relationships": [
                        {
                            "type": "Diubah oleh",
                            "type_en": "Amended by",
                            "related_work": {
                                "title": "UU Nomor 6 Tahun 2023 tentang Cipta Kerja",
                                "frbr_uri": "/akn/id/act/uu/2023/6",
                            },
                        }
                    ],
                }
            },
        )

        check = verify_citation(fake, "UU 13/2003", claimed_topic="Ketenagakerjaan")
        self.assertTrue(check.found)
        self.assertEqual(check.reason_code, "matched")
        self.assertIn("amended", check.flags)
        self.assertIn("diubah", (check.note or "").lower())
        self.assertIn("Cipta Kerja", check.note or "")

    def test_verify_citation_skips_amendment_check_when_disabled(self) -> None:
        # When check_amendments=False, no get_law call is made — useful for
        # cheap existence-only verification paths.
        fake = FakePasalClient(
            responses={
                "UU 13/2003": {
                    "results": [
                        {
                            "title": "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
                            "frbr_uri": "akn/id/act/uu/2003/13",
                            "status": "berlaku",
                        }
                    ]
                }
            },
            laws={},
        )

        check = verify_citation(fake, "UU 13/2003", check_amendments=False)
        self.assertTrue(check.found)
        self.assertEqual(check.reason_code, "matched")
        self.assertIsNone(check.note)
        self.assertEqual(fake.get_law_calls, [])

    def test_verify_citation_amendment_check_degrades_on_get_law_failure(self) -> None:
        # If pasal.id /laws/{uri} fails (network error, missing law, etc.),
        # the amendment check must not block legitimate citations.
        fake = FakePasalClient(
            responses={
                "UU 13/2003": {
                    "results": [
                        {
                            "title": "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
                            "frbr_uri": "akn/id/act/uu/2003/13",
                            "status": "berlaku",
                        }
                    ]
                }
            },
            laws={},  # get_law will raise KeyError
        )

        check = verify_citation(fake, "UU 13/2003", claimed_topic="Ketenagakerjaan")
        self.assertTrue(check.found)
        self.assertEqual(check.reason_code, "matched")
        self.assertIsNone(check.note)
        # get_law was attempted but failed silently
        self.assertEqual(fake.get_law_calls, ["akn/id/act/uu/2003/13"])

    def test_verify_citation_falls_back_to_trusted_recent(self) -> None:
        # Pasal.id returns no hit for Perpres 8/2026 (not yet ingested), but
        # trusted_recent has it. Verifier should accept with topical-overlap
        # enforced against the trusted title.
        fake = FakePasalClient(responses={})

        # Sanity check: the fixture entry exists.
        self.assertIn("Perpres 8/2026", TRUSTED_RECENT)

        check = verify_citation(
            fake,
            "Perpres 8/2026",
            claimed_topic="Rencana Aksi Nasional Pencegahan Ekstremisme Berbasis Kekerasan",
            check_amendments=False,
        )
        self.assertTrue(check.found)
        self.assertEqual(check.reason_code, "trusted_recent")
        self.assertIn("trusted_recent", check.flags)
        self.assertIn("trusted_recent override", check.note or "")
        self.assertIn("akn/id/act/perpres/2026/8", check.frbr_uri or "")
        self.assertEqual(fake.get_law_calls, [])

    def test_verify_citation_trusted_recent_overrides_noisy_hit(self) -> None:
        # pasal.id can return a related/noisy hit whose metadata mentions the
        # citation, but the trusted_recent entry should still win when the
        # noisy hit does not match the claimed topic.
        fake = FakePasalClient(
            responses={
                "Perpres 8/2026": {
                    "results": [
                        {
                            "title": "Peraturan Presiden Nomor 1 Tahun 2026 tentang Tata Kelola Data",
                            "snippet": "Lihat juga Perpres 8/2026 dalam daftar rujukan",
                            "frbr_uri": "akn/id/act/perpres/2026/1",
                            "status": "berlaku",
                        }
                    ]
                }
            }
        )

        check = verify_citation(
            fake,
            "Perpres 8/2026",
            claimed_topic="Rencana Aksi Nasional Pencegahan Ekstremisme Berbasis Kekerasan",
            check_amendments=False,
        )
        self.assertTrue(check.found)
        self.assertEqual(check.reason_code, "trusted_recent")
        self.assertIn("trusted_recent", check.flags)
        self.assertIn("trusted_recent override", check.note or "")
        self.assertIn("Peraturan Presiden Nomor 8 Tahun 2026", check.title or "")
        self.assertEqual(fake.get_law_calls, [])

    def test_verify_citation_trusted_recent_checks_amendments(self) -> None:
        # Trusted overrides should still go through amendment probing when
        # check_amendments=True so stale entries are not treated as final.
        fake = FakePasalClient(
            responses={},
            laws={
                "akn/id/act/perpres/2026/8": {
                    "title": "Peraturan Presiden Nomor 8 Tahun 2026 tentang Rencana Aksi Nasional Pencegahan dan Penanggulangan Ekstremisme Berbasis Kekerasan yang Mengarah pada Terorisme Tahun 2026-2029",
                    "frbr_uri": "akn/id/act/perpres/2026/8",
                    "status": "berlaku",
                    "relationships": [
                        {
                            "type": "Diubah oleh",
                            "type_en": "Amended by",
                            "related_work": {
                                "title": "Peraturan Presiden Nomor 9 Tahun 2027 tentang Perubahan atas Rencana Aksi Nasional Pencegahan dan Penanggulangan Ekstremisme Berbasis Kekerasan yang Mengarah pada Terorisme Tahun 2026-2029",
                                "frbr_uri": "/akn/id/act/perpres/2027/9",
                            },
                        }
                    ],
                }
            },
        )

        check = verify_citation(
            fake,
            "Perpres 8/2026",
            claimed_topic="Rencana Aksi Nasional Pencegahan Ekstremisme Berbasis Kekerasan",
        )
        self.assertTrue(check.found)
        self.assertEqual(check.reason_code, "trusted_recent")
        self.assertIn("amended", check.flags)
        self.assertEqual(fake.get_law_calls, ["akn/id/act/perpres/2026/8"])
        self.assertIn("trusted_recent override", check.note or "")
        self.assertIn("diubah", (check.note or "").lower())

    def test_verify_citation_trusted_recent_rejects_topical_mismatch(self) -> None:
        # Trusted entry exists for Perpres 8/2026 (RAN PE counter-terrorism),
        # but the claim is about something unrelated. Verifier must reject —
        # we don't blanket-whitelist a (kind, number, year) tuple.
        fake = FakePasalClient(responses={})

        check = verify_citation(
            fake,
            "Perpres 8/2026",
            claimed_topic="Pengadaan Barang Jasa Pemerintah",
            check_amendments=False,
        )
        self.assertFalse(check.found)
        self.assertEqual(check.reason_code, "topic_mismatch")
        self.assertIn("judul tidak cocok", check.note or "")
        self.assertIn("trusted_recent", check.note or "")

    def test_verify_citation_trusted_recent_fallback_on_pasal_unreachable(self) -> None:
        # When pasal.id is down (auth failure, network error), trusted_recent
        # should still serve as a fallback for citations we know about.
        class FailingClient:
            def search(self, **kwargs):
                raise RuntimeError("Client error '401 Unauthorized'")

        check = verify_citation(
            FailingClient(),
            "Perpres 8/2026",
            claimed_topic="Rencana Aksi Nasional Pencegahan Ekstremisme",
            check_amendments=False,
        )
        self.assertTrue(check.found)
        self.assertEqual(check.reason_code, "trusted_recent")
        self.assertIn("trusted_recent override", check.note or "")
        self.assertIn("pasal.id unreachable", check.note or "")

    def test_verify_citation_pasal_unreachable_unknown_ref_surfaces_error(self) -> None:
        # If pasal.id is unreachable AND the citation isn't in trusted_recent,
        # we want the user to see the original transport error so they can
        # fix the underlying issue (refresh token, check network).
        class FailingClient:
            def search(self, **kwargs):
                raise RuntimeError("Client error '401 Unauthorized'")

        check = verify_citation(
            FailingClient(),
            "UU 17/2023",
            claimed_topic="Kesehatan",
            check_amendments=False,
        )
        self.assertFalse(check.found)
        self.assertEqual(check.reason_code, "request_error")
        self.assertIn("verifikasi gagal", check.note or "")
        self.assertIn("401", check.note or "")

    def test_verify_citation_unknown_reference_still_rejects_cleanly(self) -> None:
        # Sanity: a fresh regulation NOT in trusted_recent and NOT on pasal.id
        # still rejects with TIDAK DITEMUKAN — no silent acceptance.
        fake = FakePasalClient(responses={})

        check = verify_citation(
            fake,
            "Perpres 999/2026",
            claimed_topic="Hypothetical regulation that doesn't exist",
            check_amendments=False,
        )
        self.assertFalse(check.found)
        self.assertEqual(check.reason_code, "not_found")
        self.assertIn("TIDAK DITEMUKAN", check.note or "")

    def test_verify_citation_marks_expired_trusted_entries(self) -> None:
        # A stale trusted entry should still be accepted, but the verifier
        # should surface that it needs a fresh pasal.id re-check.
        key = "Perpres 99/2026"
        TRUSTED_RECENT[key] = {
            "frbr_uri": "akn/id/act/perpres/2026/99",
            "title": "Peraturan Presiden Nomor 99 Tahun 2026 tentang Contoh",
            "status": "berlaku",
            "signed_date": "2026-01-01",
            "checked_on": "2026-01-01",
            "expires_on": "2026-02-01",
            "source_url": "https://example.invalid/perpres-99-2026",
            "note": "temporary stale fixture",
        }
        try:
            fake = FakePasalClient(responses={})
            check = verify_citation(
                fake,
                key,
                claimed_topic="Contoh",
                check_amendments=False,
            )
            self.assertTrue(check.found)
            self.assertEqual(check.reason_code, "trusted_recent_stale")
            self.assertIn("stale_trusted_entry", check.flags)
            self.assertIn("expired on 2026-02-01", check.note or "")
        finally:
            TRUSTED_RECENT.pop(key, None)

    def test_validate_trusted_entry_requires_review_date(self) -> None:
        problems = validate_trusted_entry(
            "Perpres 1/2027",
            {
                "frbr_uri": "akn/id/act/perpres/2027/1",
                "title": "Peraturan Presiden Nomor 1 Tahun 2027 tentang Contoh",
                "status": "berlaku",
                "signed_date": "2027-01-01",
            },
        )
        self.assertIn("missing checked_on or expires_on", problems)

    def test_verify_citations_formats_mixed_results(self) -> None:
        fake = FakePasalClient(
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

        checks = verify_citations(fake, ["UU 13/2003", "Perpres 76/2021"])
        self.assertEqual([c.reference for c in checks], ["UU 13/2003", "Perpres 76/2021"])
        self.assertTrue(checks[0].found)
        self.assertFalse(checks[1].found)
        self.assertIn("TIDAK DITEMUKAN", format_checks(checks))


if __name__ == "__main__":
    unittest.main()

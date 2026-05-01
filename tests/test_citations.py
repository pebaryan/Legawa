from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.tools.citations import (
    CitationCheck,
    extract_citations,
    format_checks,
    verify_citation,
    verify_citations,
)


class FakePasalClient:
    def __init__(self, responses: dict[str, dict]):
        self.responses = responses
        self.calls: list[tuple[dict, ...]] = []

    def search(self, **kwargs):
        self.calls.append((kwargs,))
        return self.responses.get(kwargs["q"], {"results": []})


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

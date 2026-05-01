from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.agents.surat import reply


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[list[dict], dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


class FakePool:
    def __init__(self, small_response: str, big_response: str):
        self.small = FakeLLM(small_response)
        self.big = FakeLLM(big_response)


class FakePasalClient:
    def __init__(self):
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["q"] in {"UU 13/2003", "UU 6/2023"}:
            return {
                "results": [
                    {
                        "title": f"Undang-Undang Nomor {kwargs['q'].split()[1].split('/')[0]} Tahun {kwargs['q'].split('/')[1]}",
                        "frbr_uri": f"akn/id/act/uu/{kwargs['q'].split('/')[1]}/{kwargs['q'].split()[1].split('/')[0]}",
                        "status": "berlaku",
                    }
                ]
            }
        return {"results": []}


class SuratReplyTests(unittest.TestCase):
    def _triase_json(self) -> str:
        return json.dumps(
            {
                "kategori": "aspirasi_kebijakan",
                "urgensi": "tinggi",
                "sentimen": "negatif",
                "dapil_relevance": True,
                "nama_pengirim": "Sukma",
                "lokasi": "Bekasi",
                "isu_utama": "Permenaker dianggap merugikan pekerja.",
                "permintaan_konkret": ["RDP", "Revisi aturan"],
                "peraturan_disebut": ["UU 13/2003"],
                "perlu_tindak_lanjut_staf": True,
                "rangkuman": "Surat menyoroti dampak kebijakan ketenagakerjaan.",
            }
        )

    def test_reply_blocks_unverified_citation(self) -> None:
        pool = FakePool(
            self._triase_json(),
            "Kami merujuk pada UU 13/2003 dan Perpres 76/2021 dalam balasan ini.",
        )
        pasal = FakePasalClient()

        with self.assertRaises(ValueError) as ctx:
            reply(pool, pasal, "surat uji", verify_law=True)

        self.assertIn("Perpres 76/2021", str(ctx.exception))
        self.assertEqual(len(pool.big.calls), 1)
        self.assertGreaterEqual(len(pasal.calls), 2)

    def test_reply_accepts_verified_citation(self) -> None:
        pool = FakePool(
            self._triase_json(),
            "Kami merujuk pada UU 13/2003 dalam balasan ini.",
        )
        pasal = FakePasalClient()

        result = reply(pool, pasal, "surat uji", verify_law=True)

        self.assertIsNotNone(result.balasan)
        self.assertEqual(len(pool.big.calls), 1)
        self.assertGreaterEqual(len(pasal.calls), 2)


if __name__ == "__main__":
    unittest.main()

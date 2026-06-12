from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.tools.offline_pasal import OfflinePasalClient


class OfflinePasalClientTests(unittest.TestCase):
    def _make_db(self, path: Path) -> None:
        law = {
            "work": {
                "id": "fixture:1",
                "frbr_uri": "/akn/id/act/uu/2003/13",
                "title": "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
                "type": "UU",
                "type_name": "Undang-Undang",
                "number": "13",
                "year": 2003,
                "status": "berlaku",
            },
            "articles": [
                {
                    "id": 1,
                    "type": "pasal",
                    "number": "1",
                    "heading": "",
                    "content": "Perlindungan pekerja dan hubungan kerja ketenagakerjaan.",
                    "sort_order": 1,
                }
            ],
            "relationships": [],
        }
        constitution = {
            "work": {
                "id": "fixture:uud:1945",
                "frbr_uri": "/akn/id/act/uud/1945/0",
                "title": "Undang-Undang Dasar Negara Republik Indonesia Tahun 1945",
                "type": "UUD",
                "type_name": "Undang-Undang Dasar",
                "number": "0",
                "year": 1945,
                "status": "berlaku",
            },
            "articles": [
                {
                    "id": 2,
                    "type": "pasal",
                    "number": "28H",
                    "heading": "",
                    "content": "Setiap orang berhak hidup sejahtera lahir dan batin.",
                    "sort_order": 1,
                }
            ],
            "relationships": [],
        }
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE works (frbr_uri TEXT PRIMARY KEY, title TEXT, type TEXT, number TEXT, year INTEGER, status TEXT, law_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE articles (frbr_uri TEXT, article_id TEXT, type TEXT, number TEXT, heading TEXT, content TEXT, sort_order INTEGER, article_json TEXT NOT NULL)"
            )
            conn.execute(
                'CREATE VIRTUAL TABLE article_fts USING fts5(frbr_uri UNINDEXED, article_id UNINDEXED, title, content, tokenize="unicode61")'
            )
            conn.execute("CREATE TABLE aliases (reference TEXT PRIMARY KEY, frbr_uri TEXT NOT NULL)")
            conn.execute(
                "INSERT INTO works VALUES (?,?,?,?,?,?,?)",
                (
                    "akn/id/act/uu/2003/13",
                    law["work"]["title"],
                    "UU",
                    "13",
                    2003,
                    "berlaku",
                    json.dumps(law),
                ),
            )
            conn.execute(
                "INSERT INTO works VALUES (?,?,?,?,?,?,?)",
                (
                    "akn/id/act/uud/1945/0",
                    constitution["work"]["title"],
                    "UUD",
                    "0",
                    1945,
                    "berlaku",
                    json.dumps(constitution),
                ),
            )
            article = law["articles"][0]
            conn.execute(
                "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)",
                (
                    "akn/id/act/uu/2003/13",
                    "1",
                    "pasal",
                    "1",
                    "",
                    article["content"],
                    1,
                    json.dumps(article),
                ),
            )
            uud_article = constitution["articles"][0]
            conn.execute(
                "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)",
                (
                    "akn/id/act/uud/1945/0",
                    "2",
                    "pasal",
                    "28H",
                    "",
                    uud_article["content"],
                    1,
                    json.dumps(uud_article),
                ),
            )
            conn.execute(
                "INSERT INTO article_fts VALUES (?,?,?,?)",
                ("akn/id/act/uu/2003/13", "1", law["work"]["title"], article["content"]),
            )
            conn.execute(
                "INSERT INTO article_fts VALUES (?,?,?,?)",
                (
                    "akn/id/act/uud/1945/0",
                    "2",
                    constitution["work"]["title"],
                    uud_article["content"],
                ),
            )
            conn.execute("INSERT INTO aliases VALUES (?,?)", ("UU 13/2003", "akn/id/act/uu/2003/13"))
            conn.execute("INSERT INTO aliases VALUES (?,?)", ("UUD 1945", "akn/id/act/uud/1945/0"))
            conn.commit()
        finally:
            conn.close()

    def test_search_get_and_list_laws(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "offline.db"
            self._make_db(path)

            client = OfflinePasalClient(path)
            try:
                exact = client.search("UU 13/2003")
                self.assertEqual(exact["total"], 1)
                self.assertEqual(exact["results"][0]["work"]["frbr_uri"], "/akn/id/act/uu/2003/13")

                topical = client.search("perlindungan pekerja")
                self.assertEqual(topical["total"], 1)
                self.assertIn("Perlindungan pekerja", topical["results"][0]["matching_pasals"][0]["content"])

                law = client.get_law("akn/id/act/uu/2003/13")
                self.assertEqual(law["work"]["number"], "13")

                listed = client.list_laws(type="UU", year=2003)
                self.assertEqual(listed["total"], 1)

                uud = client.search("Pasal 28H UUD 1945")
                self.assertEqual(uud["total"], 1)
                self.assertEqual(uud["results"][0]["work"]["type"], "UUD")
                self.assertEqual(uud["results"][0]["matching_pasals"][0]["number"], "28H")
            finally:
                client.close()


if __name__ == "__main__":
    unittest.main()

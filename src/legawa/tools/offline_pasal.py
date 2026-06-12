"""Offline pasal.id-compatible client backed by a local SQLite FTS corpus."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any


_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+")
_FRBR_RE = re.compile(r"\bakn/id/act/[a-z0-9_-]+/\d{4}/[a-z0-9_.-]+\b", re.IGNORECASE)
_PASAL_RE = re.compile(r"\bPasal\s+(?P<number>\d+[A-Za-z]?)\b", re.IGNORECASE)
_UUD_RE = re.compile(
    r"\b(?:UUD(?:\s+NRI)?|Undang[-\s]Undang Dasar(?:\s+Negara\s+Republik\s+Indonesia)?)\s+1945\b",
    re.IGNORECASE,
)
_REF_RE = re.compile(
    r"\b(?P<label>UU|PP|Perpres|Perppu|Permen(?:kes|keu|dagri|aker|tan)?|Permenkes|Perda)\s+"
    r"(?P<number>[0-9A-Za-z_.-]+)\s*/\s*(?P<year>\d{4})\b",
    re.IGNORECASE,
)


def _default_db_path() -> Path:
    override = os.environ.get("LEGAWA_OFFLINE_PASAL_DB")
    if override:
        return Path(override)
    return Path.cwd() / "output" / "pasal_demo_data" / "offline_pasal.db"


def _norm_frbr(frbr_uri: str) -> str:
    return frbr_uri.strip().lstrip("/")


def _type_from_label(label: str) -> str | None:
    lower = label.lower()
    if lower == "uu":
        return "UU"
    if lower == "uud":
        return "UUD"
    if lower == "pp":
        return "PP"
    if lower == "perppu":
        return "PERPPU"
    if lower == "perpres":
        return "PERPRES"
    if lower.startswith("permen"):
        return "PERMEN"
    if lower == "perda":
        return "PERDA"
    return None


def _fts_query(q: str, *, operator: str = "AND") -> str:
    tokens = [t.lower() for t in _TOKEN_RE.findall(q) if len(t) >= 2]
    if not tokens:
        return ""
    # Quote tokens to avoid FTS syntax surprises; prefix search keeps Indonesian
    # inflections and partial regulation words useful for demos.
    return f" {operator} ".join(f'"{token}"*' for token in tokens[:12])


class OfflinePasalClient:
    """Drop-in subset of :class:`PasalClient` using ``offline_pasal.db``.

    The database is generated into ``output/pasal_demo_data/offline_pasal.db``.
    It stores pasal.id-shaped law JSON and a full-text index over article text,
    so agents can call ``search``, ``list_laws``, and ``get_law`` without the
    pasal.id API.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _default_db_path()
        if not self.db_path.exists():
            raise FileNotFoundError(f"offline pasal corpus not found: {self.db_path}")
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "OfflinePasalClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _law_row(self, frbr_uri: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM works WHERE frbr_uri = ?",
            (_norm_frbr(frbr_uri),),
        ).fetchone()

    def _article(self, frbr_uri: str, article_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT article_json FROM articles WHERE frbr_uri = ? AND article_id = ? LIMIT 1",
            (_norm_frbr(frbr_uri), article_id),
        ).fetchone()
        return json.loads(row["article_json"]) if row else None

    def _article_hits_for_query(self, frbr_uri: str, q: str) -> list[dict[str, Any]]:
        pasal_match = _PASAL_RE.search(q)
        if not pasal_match:
            return []
        rows = self.conn.execute(
            """
            SELECT article_id, article_json
            FROM articles
            WHERE frbr_uri = ? AND type = 'pasal' AND upper(number) = upper(?)
            ORDER BY sort_order
            LIMIT 5
            """,
            (_norm_frbr(frbr_uri), pasal_match.group("number")),
        ).fetchall()
        hits = []
        for row in rows:
            article = json.loads(row["article_json"])
            hits.append(
                {
                    "article_id": row["article_id"],
                    "number": article.get("number"),
                    "heading": article.get("heading"),
                    "content": (article.get("content") or article.get("text") or "")[:1400],
                }
            )
        return hits

    def _direct_ref_hit(self, q: str, type: str | None) -> list[dict[str, Any]]:
        frbr_match = _FRBR_RE.search(q)
        if frbr_match:
            row = self._law_row(frbr_match.group(0))
            return [self._row_to_hit(row, self._article_hits_for_query(row["frbr_uri"], q))] if row else []

        if _UUD_RE.search(q) and (not type or type.upper() == "UUD"):
            row = self._law_row("akn/id/act/uud/1945/0")
            return [self._row_to_hit(row, self._article_hits_for_query(row["frbr_uri"], q))] if row else []

        alias = self.conn.execute(
            "SELECT frbr_uri FROM aliases WHERE lower(reference) = lower(?)",
            (q.strip(),),
        ).fetchone()
        if alias:
            row = self._law_row(alias["frbr_uri"])
            return [self._row_to_hit(row, self._article_hits_for_query(row["frbr_uri"], q))] if row else []

        ref_match = _REF_RE.search(q)
        if not ref_match:
            return []
        inferred_type = _type_from_label(ref_match.group("label"))
        number = ref_match.group("number")
        year = int(ref_match.group("year"))
        params: list[Any] = [str(number), year]
        where = "number = ? AND year = ?"
        if type or inferred_type:
            where += " AND type = ?"
            params.append(type or inferred_type)
        row = self.conn.execute(f"SELECT * FROM works WHERE {where} LIMIT 1", params).fetchone()
        return [self._row_to_hit(row, self._article_hits_for_query(row["frbr_uri"], q))] if row else []

    def _row_to_hit(self, row: sqlite3.Row, article_hits: list[dict[str, Any]]) -> dict[str, Any]:
        law = json.loads(row["law_json"])
        work = law.get("work") or {}
        articles = law.get("articles") or []
        matching_pasals = article_hits[:5]
        if not matching_pasals:
            for article in articles[:3]:
                content = article.get("content") or article.get("text") or ""
                if content:
                    matching_pasals.append(
                        {
                            "article_id": article.get("id"),
                            "number": article.get("number"),
                            "heading": article.get("heading"),
                            "content": content[:1400],
                        }
                    )
        snippet_parts = [work.get("title") or row["title"]]
        if matching_pasals:
            snippet_parts.append(matching_pasals[0].get("content") or "")
        return {
            "work_id": work.get("id") or row["frbr_uri"],
            "score": 1.0,
            "snippet": " | ".join(part for part in snippet_parts if part)[:1800],
            "total_chunks": len(articles),
            "work": work,
            "matching_pasals": matching_pasals,
            "source": "offline_pasal",
        }

    def search(self, q: str, type: str | None = None, limit: int = 10) -> dict[str, Any]:
        limit = max(1, min(20, limit))
        direct = self._direct_ref_hit(q, type)
        if direct:
            return {"query": q, "total": len(direct), "results": direct[:limit]}

        hits_by_frbr: dict[str, list[dict[str, Any]]] = {}
        for operator in ("AND", "OR"):
            query = _fts_query(q, operator=operator)
            if not query:
                break
            params: list[Any] = [query]
            type_clause = ""
            if type:
                type_clause = "AND w.type = ?"
                params.append(type)
            params.append(max(limit * 8, 40))
            rows = self.conn.execute(
                f"""
                SELECT f.frbr_uri, f.article_id, f.content, f.title, bm25(article_fts) AS rank
                FROM article_fts f
                JOIN works w ON w.frbr_uri = f.frbr_uri
                WHERE article_fts MATCH ? {type_clause}
                ORDER BY rank
                LIMIT ?
                """,
                params,
            ).fetchall()
            for row in rows:
                article = self._article(row["frbr_uri"], row["article_id"]) or {}
                hits_by_frbr.setdefault(row["frbr_uri"], []).append(
                    {
                        "article_id": row["article_id"],
                        "number": article.get("number"),
                        "heading": article.get("heading"),
                        "content": (article.get("content") or row["content"] or "")[:1400],
                        "score": float(row["rank"]),
                    }
                )
            if hits_by_frbr:
                break

        results: list[dict[str, Any]] = []
        for frbr_uri, article_hits in hits_by_frbr.items():
            row = self._law_row(frbr_uri)
            if row:
                results.append(self._row_to_hit(row, article_hits))
        return {"query": q, "total": len(results), "results": results[:limit]}

    def list_laws(
        self,
        type: str | None = None,
        year: int | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if type:
            clauses.append("type = ?")
            params.append(type)
        if year:
            clauses.append("year = ?")
            params.append(year)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        total = self.conn.execute(f"SELECT COUNT(*) AS n FROM works {where}", params).fetchone()["n"]
        rows = self.conn.execute(
            f"SELECT law_json FROM works {where} ORDER BY year DESC, type, number LIMIT ? OFFSET ?",
            [*params, max(1, min(50, limit)), max(0, offset)],
        ).fetchall()
        results = [json.loads(row["law_json"]).get("work") for row in rows]
        return {"total": total, "results": results}

    def get_law(self, frbr_uri: str) -> dict[str, Any]:
        row = self._law_row(frbr_uri)
        if not row:
            raise KeyError(f"law not found in offline corpus: {frbr_uri}")
        return json.loads(row["law_json"])

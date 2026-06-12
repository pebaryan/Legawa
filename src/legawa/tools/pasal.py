"""Client for the pasal.id REST API.

Endpoints (https://pasal.id/api/v1):
  GET /search?q=...&type=...&limit=...      — keyword search
  GET /laws?type=...&year=...&status=...    — list with filters
  GET /laws/{frbr_uri}                      — full document + articles
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import Settings


REGULATION_TYPES = [
    "UUD", "UU", "PERPPU", "PP", "PERPRES", "PERMEN",
    "PERDA", "PERDA_PROV", "PERDA_KAB",
]

STATUS_VALUES = ["berlaku", "dicabut", "diubah"]


class PasalClient:
    def __init__(self, settings: Settings, timeout: float = 30.0):
        self._client = httpx.Client(
            base_url=settings.pasal_base_url,
            headers={
                "Authorization": f"Bearer {settings.pasal_token}",
                "Accept": "application/json",
                "User-Agent": "legawa/0.1",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PasalClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def search(
        self,
        q: str,
        type: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": q, "limit": max(1, min(20, limit))}
        if type:
            params["type"] = type
        r = self._client.get("/search", params=params)
        r.raise_for_status()
        return r.json()

    def list_laws(
        self,
        type: str | None = None,
        year: int | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": max(1, min(50, limit)),
            "offset": max(0, offset),
        }
        if type:
            params["type"] = type
        if year:
            params["year"] = year
        if status:
            params["status"] = status
        r = self._client.get("/laws", params=params)
        r.raise_for_status()
        return r.json()

    def get_law(self, frbr_uri: str) -> dict[str, Any]:
        # frbr_uri example: akn/id/act/uu/2003/13
        r = self._client.get(f"/laws/{frbr_uri.lstrip('/')}")
        r.raise_for_status()
        return r.json()


# OpenAI-compatible tool schemas exposed to agents.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "pasal_search",
            "description": (
                "Cari peraturan perundang-undangan Indonesia di pasal.id berdasarkan kata kunci. "
                "Mengembalikan daftar peraturan beserta cuplikan pasal yang relevan dan frbr_uri "
                "yang bisa dipakai untuk mengambil dokumen lengkap."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Kata kunci pencarian (Bahasa Indonesia)."},
                    "type": {
                        "type": "string",
                        "enum": REGULATION_TYPES,
                        "description": "Filter jenis peraturan (opsional).",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 10,
                    },
                },
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pasal_list_laws",
            "description": (
                "Daftar peraturan dengan filter jenis, tahun, dan status. Berguna untuk eksplorasi "
                "tanpa kata kunci spesifik."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": REGULATION_TYPES},
                    "year": {"type": "integer", "minimum": 1945, "maximum": 2100},
                    "status": {"type": "string", "enum": STATUS_VALUES},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pasal_get_law",
            "description": (
                "Ambil dokumen peraturan lengkap beserta seluruh pasal dan relasi antar peraturan, "
                "berdasarkan frbr_uri (mis. 'akn/id/act/uu/2003/13')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "frbr_uri": {
                        "type": "string",
                        "description": "FRBR URI dari hasil search atau list_laws.",
                    },
                },
                "required": ["frbr_uri"],
            },
        },
    },
]


def build_dispatcher(client: PasalClient):
    """Return a callable mapping tool_name -> args -> result dict."""

    def dispatch(name: str, args: dict[str, Any]) -> Any:
        if name == "pasal_search":
            return client.search(**args)
        if name == "pasal_list_laws":
            return client.list_laws(**args)
        if name == "pasal_get_law":
            return client.get_law(**args)
        raise ValueError(f"unknown tool: {name}")

    return dispatch

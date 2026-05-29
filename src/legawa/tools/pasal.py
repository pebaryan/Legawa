"""Client for the pasal.id REST API.

Endpoints (https://pasal.id/api/v1):
  GET /search?q=...&type=...&limit=...      — keyword search
  GET /laws?type=...&year=...&status=...    — list with filters
  GET /laws/{frbr_uri}                      — full document + articles
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

import httpx

# ── Global rate limiter (shared across all PasalClient instances) ─────────
_LOCK = threading.Lock()
_LAST_PASAL_REQUEST: float = 0.0
_PASAL_MIN_DELAY: float = 1.5  # seconds between API calls (global)


def _throttle() -> None:
    """Block until the global per-instance delay has elapsed since last call."""
    global _LAST_PASAL_REQUEST
    with _LOCK:
        elapsed = time.monotonic() - _LAST_PASAL_REQUEST
        if elapsed < _PASAL_MIN_DELAY:
            time.sleep(_PASAL_MIN_DELAY - elapsed)
        _LAST_PASAL_REQUEST = time.monotonic()


from ..config import Settings


REGULATION_TYPES = [
    "UU", "PERPPU", "PP", "PERPRES", "PERMEN",
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

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Send a request with global rate limiting + retry on 429."""
        for attempt in range(max_retries):
            _throttle()  # global delay shared across all instances

            r = self._client.request(method, path, params=params)

            if r.status_code == 429:
                retry_after = float(r.headers.get("Retry-After", 2))
                wait = retry_after * (attempt + 1)
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r.json()

        # All retries exhausted
        raise RuntimeError(f"pasal.id rate limit exceeded after {max_retries} retries")

    def search(
        self,
        q: str,
        type: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": q, "limit": max(1, min(20, limit))}
        if type:
            params["type"] = type
        return self._request("GET", "/search", params=params)

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
        return self._request("GET", "/laws", params=params)

    def get_law(self, frbr_uri: str) -> dict[str, Any]:
        # frbr_uri example: akn/id/act/uu/2003/13
        return self._request("GET", f"/laws/{frbr_uri.lstrip('/')}")


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

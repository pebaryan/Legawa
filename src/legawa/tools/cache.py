"""SQLite cache layer for the pasal.id REST client.

Transparent wrapper over PasalClient. Same method names, same return shapes.
Agents and the CLI swap PasalClient → CachingPasalClient with no other changes.

TTL defaults:
  search    : 3600   (1 hour)  — search results shift as the corpus grows
  list_laws : 3600   (1 hour)
  get_law   : 86400  (24 hours) — full document content is stable

Cache file:
  $LEGAWA_CACHE_PATH if set, else $HOME/.legawa/cache.db
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from .pasal import PasalClient


DEFAULT_TTL_SEARCH = 3600
DEFAULT_TTL_LIST = 3600
DEFAULT_TTL_GET = 86400


def _default_cache_path() -> Path:
    override = os.environ.get("LEGAWA_CACHE_PATH")
    if override:
        return Path(override)
    return Path.home() / ".legawa" / "cache.db"


class _SqliteCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL,"
            "  expires_at INTEGER NOT NULL"
            ")"
        )

    def get(self, key: str) -> Any | None:
        now = int(time.time())
        row = self.conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at < now:
            self.conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            return None
        return json.loads(value)

    def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = int(time.time()) + ttl
        self.conn.execute(
            "INSERT OR REPLACE INTO cache(key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), expires_at),
        )

    def purge_expired(self) -> int:
        cur = self.conn.execute("DELETE FROM cache WHERE expires_at < ?", (int(time.time()),))
        return cur.rowcount or 0

    def stats(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(value)), 0) FROM cache"
        ).fetchone()
        return {"entries": rows[0], "bytes": rows[1]}

    def close(self) -> None:
        self.conn.close()


def _key(prefix: str, args: dict[str, Any]) -> str:
    # Drop None values so equivalent calls collapse to the same key.
    cleaned = {k: v for k, v in args.items() if v is not None}
    return f"{prefix}::{json.dumps(cleaned, sort_keys=True, ensure_ascii=False)}"


class CachingPasalClient:
    """Drop-in replacement for PasalClient with on-disk caching."""

    def __init__(
        self,
        inner: PasalClient,
        cache_path: Path | None = None,
        *,
        ttl_search: int = DEFAULT_TTL_SEARCH,
        ttl_list: int = DEFAULT_TTL_LIST,
        ttl_get: int = DEFAULT_TTL_GET,
    ):
        self._inner = inner
        self._cache = _SqliteCache(cache_path or _default_cache_path())
        self._ttl_search = ttl_search
        self._ttl_list = ttl_list
        self._ttl_get = ttl_get
        self.hits = 0
        self.misses = 0

    def _cached(self, prefix: str, args: dict[str, Any], ttl: int, fetch: Callable[[], Any]) -> Any:
        key = _key(prefix, args)
        hit = self._cache.get(key)
        if hit is not None:
            self.hits += 1
            return hit
        self.misses += 1
        value = fetch()
        self._cache.set(key, value, ttl)
        return value

    def search(self, q: str, type: str | None = None, limit: int = 10) -> dict[str, Any]:
        args = {"q": q, "type": type, "limit": limit}
        return self._cached("search", args, self._ttl_search, lambda: self._inner.search(**args))

    def list_laws(
        self,
        type: str | None = None,
        year: int | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        args = {"type": type, "year": year, "status": status, "limit": limit, "offset": offset}
        return self._cached("list", args, self._ttl_list, lambda: self._inner.list_laws(**args))

    def get_law(self, frbr_uri: str) -> dict[str, Any]:
        args = {"frbr_uri": frbr_uri}
        return self._cached("get", args, self._ttl_get, lambda: self._inner.get_law(**args))

    def stats(self) -> dict[str, Any]:
        return {**self._cache.stats(), "session_hits": self.hits, "session_misses": self.misses}

    def purge_expired(self) -> int:
        return self._cache.purge_expired()

    def close(self) -> None:
        try:
            self._inner.close()
        finally:
            self._cache.close()

    def __enter__(self) -> "CachingPasalClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

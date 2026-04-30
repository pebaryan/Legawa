"""Peneliti Hukum — riset hukum bertema.

Pipeline:
  1. SMALL model: ekspansi topik → 4–6 query pencarian (Bahasa Indonesia, beragam sudut).
  2. PasalClient: jalankan semua query, kumpulkan hits unik.
  3. BIG model: sintesis temuan dengan sitasi frbr_uri + kutipan pasal.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from rich.console import Console

from ..llm import LLMPool
from ..tools.pasal import PasalClient


QUERY_EXPANSION_PROMPT = """\
Anda membantu riset hukum Indonesia. Diberikan satu topik, hasilkan 4–6 query pencarian
berbeda untuk database peraturan (pasal.id). Variasikan sudut pandang: subjek hukum,
istilah teknis, sinonim, dan konteks kelembagaan.

Output WAJIB berupa JSON array of strings, tanpa teks lain. Contoh:
["query 1", "query 2", "query 3"]
"""

SYNTHESIS_PROMPT = """\
Anda adalah peneliti hukum senior yang membantu legislator Indonesia.
Diberikan topik riset dan kumpulan hasil pencarian peraturan dari pasal.id, susun memo riset
dalam Bahasa Indonesia formal dengan struktur:

# Memo Riset Hukum: <topik>

## 1. Ringkasan Temuan
3–5 kalimat yang menjawab inti topik.

## 2. Peraturan Utama
Untuk setiap peraturan kunci: judul, jenis, nomor/tahun, status, frbr_uri, dan ringkasan
kontribusinya terhadap topik. Sertakan kutipan pasal pendek bila tersedia.

## 3. Hubungan Antar Peraturan
Identifikasi hierarki, perubahan, pencabutan, atau saling-rujuk antar peraturan.

## 4. Celah / Pertanyaan Terbuka
Aspek yang belum tercover oleh peraturan existing atau memerlukan riset lanjutan.

## 5. Rekomendasi Tindak Lanjut untuk Legislator
2–4 poin praktis (mis. usulan revisi, pertanyaan untuk RDP, dapil-impact).

Aturan:
- Setiap klaim tentang isi peraturan harus berasal dari hasil pencarian; cantumkan frbr_uri.
- Jangan mengarang nomor UU atau pasal yang tidak ada di hasil.
- Bila hasil tidak cukup, katakan secara eksplisit di bagian "Celah".
"""


def _expand_queries(pool: LLMPool, topic: str, console: Console) -> list[str]:
    raw = pool.small.chat(
        [
            {"role": "system", "content": QUERY_EXPANSION_PROMPT},
            {"role": "user", "content": f"Topik: {topic}"},
        ],
        temperature=0.4,
        max_tokens=512,
    )
    # Be tolerant of model wrapping JSON in code fences.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        queries = json.loads(cleaned)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return queries[:6]
    except json.JSONDecodeError:
        pass
    console.print(f"[yellow]peneliti: gagal parse query expansion, fallback ke topik mentah[/yellow]")
    return [topic]


def _dedupe_hits(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for batch in results:
        for hit in batch.get("results", []) or batch.get("hits", []) or []:
            key = (
                hit.get("frbr_uri")
                or hit.get("work", {}).get("frbr_uri")
                or json.dumps(hit, sort_keys=True)[:120]
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(hit)
    return unique


def research(
    pool: LLMPool,
    pasal: PasalClient,
    topic: str,
    *,
    console: Console | None = None,
) -> str:
    console = console or Console()
    console.print(f"[cyan]peneliti: ekspansi query untuk topik '{topic}'[/cyan]")
    queries = _expand_queries(pool, topic, console)
    console.print(f"[dim]queries: {queries}[/dim]")

    console.print(f"[cyan]peneliti: menjalankan {len(queries)} pencarian paralel[/cyan]")
    with ThreadPoolExecutor(max_workers=min(6, len(queries))) as ex:
        batches = list(ex.map(lambda q: pasal.search(q, limit=10), queries))

    hits = _dedupe_hits(batches)
    console.print(f"[cyan]peneliti: {len(hits)} hit unik, sintesis dengan model besar[/cyan]")

    payload = {"topic": topic, "queries": queries, "hits": hits[:40]}
    output = pool.big.chat(
        [
            {"role": "system", "content": SYNTHESIS_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Topik: {topic}\n\n"
                    f"Hasil pencarian (JSON):\n{json.dumps(payload, ensure_ascii=False)[:50000]}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    return output

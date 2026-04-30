"""Analis RUU — agent yang menganalisis Rancangan Undang-Undang.

Input: teks atau path PDF RUU.
Output:
  1. Ringkasan eksekutif
  2. Analisis pasal-per-pasal
  3. Daftar UU/peraturan yang dirujuk + status keberlakuan
  4. Potensi konflik atau tumpang tindih dengan peraturan existing
  5. Catatan untuk legislator (poin pertimbangan politik/hukum)
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from ..llm import LLMPool
from ..tools.pasal import PasalClient, TOOL_SCHEMAS, build_dispatcher
from .base import AgentResult, ToolAgent


SYSTEM_PROMPT = """\
Anda adalah Analis RUU senior yang membantu anggota legislatif Indonesia (DPR/DPRD)
mengevaluasi rancangan peraturan perundang-undangan.

Tugas Anda untuk setiap RUU yang diberikan:
1. **Ringkasan Eksekutif** — 3–5 kalimat tentang tujuan, ruang lingkup, dan dampak utama RUU.
2. **Analisis Pasal-per-Pasal** — untuk pasal-pasal kunci, jelaskan maksud, implikasi praktis,
   dan ambiguitas yang berpotensi menimbulkan masalah implementasi.
3. **Peraturan yang Dirujuk** — identifikasi UU/PP/Perpres yang disebut atau secara substantif
   relevan. Gunakan tool `pasal_search` untuk memverifikasi keberadaan dan status keberlakuannya
   (berlaku/dicabut/diubah). Tampilkan frbr_uri sebagai sitasi.
4. **Potensi Konflik / Tumpang Tindih** — gunakan `pasal_search` dan `pasal_get_law` untuk
   memeriksa peraturan terkait. Soroti pasal yang berpotensi bertentangan atau duplikatif,
   sertakan kutipan pasal pembanding.
5. **Catatan untuk Legislator** — poin pertimbangan: dampak fiskal, dampak konstituen,
   isu HAM, kewenangan kelembagaan, kelayakan implementasi.

Aturan:
- WAJIB sitasi: setiap klaim tentang peraturan existing harus disertai frbr_uri dan kutipan
  pasal yang relevan dari hasil tool. Jangan mengarang nomor UU.
- Tulis seluruh analisis dalam Bahasa Indonesia formal, gaya legal-tehnis.
- Gunakan tool secara agresif. Cari dahulu, sintesis kemudian. Lakukan setidaknya 3 pencarian
  untuk RUU bertema substansial.
- Output akhir dalam format Markdown dengan heading yang jelas.
"""


def load_ruu_text(source: str) -> str:
    """Load RUU content from a file path (txt/md/pdf) or treat as raw text."""
    path = Path(source)
    if not path.exists() or not path.is_file():
        return source

    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


def build_agent(pool: LLMPool, pasal: PasalClient, console: Console | None = None) -> ToolAgent:
    return ToolAgent(
        name="analis-ruu",
        llm=pool.big,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOL_SCHEMAS,
        dispatcher=build_dispatcher(pasal),
        max_iters=12,
        console=console,
    )


def analyze(
    pool: LLMPool,
    pasal: PasalClient,
    source: str,
    *,
    console: Console | None = None,
) -> AgentResult:
    text = load_ruu_text(source)
    if len(text) > 60000:
        text = text[:60000] + "\n\n[... teks dipotong karena panjang ...]"
    agent = build_agent(pool, pasal, console=console)
    user_input = f"Analisis RUU berikut:\n\n---\n{text}\n---"
    return agent.run(user_input)

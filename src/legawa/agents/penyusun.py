"""Penyusun Naskah — drafter pidato, naskah akademik, dan memo kebijakan.

Alur:
  1. Jika user butuh dukungan riset, panggil Peneliti dulu untuk ringkasan basis hukum.
  2. BIG model menyusun naskah final dengan gaya yang sesuai jenis dokumen.
"""

from __future__ import annotations

from typing import Literal

from rich.console import Console

from ..llm import LLMPool
from ..tools.pasal import PasalClient
from . import peneliti


NaskahKind = Literal["pidato", "naskah_akademik", "memo_kebijakan", "siaran_pers"]


STYLE_GUIDES: dict[str, str] = {
    "pidato": (
        "Pidato legislatif untuk dibacakan di hadapan rapat paripurna atau publik. "
        "Gunakan retorika yang jelas, kalimat ritmis, sapaan formal ('Yang terhormat...'), "
        "dan tutup dengan ajakan/komitmen. Panjang 600–900 kata."
    ),
    "naskah_akademik": (
        "Naskah Akademik untuk RUU sesuai UU 12/2011 jo. UU 13/2022. Struktur: "
        "Bab I Pendahuluan (latar belakang, identifikasi masalah, tujuan, metode); "
        "Bab II Kajian Teoritis & Praktik Empiris; Bab III Evaluasi Peraturan Terkait; "
        "Bab IV Landasan Filosofis/Sosiologis/Yuridis; Bab V Jangkauan, Arah Pengaturan, "
        "Materi Muatan; Bab VI Penutup. Bahasa formal akademis."
    ),
    "memo_kebijakan": (
        "Memo kebijakan internal 1–2 halaman: TL;DR (3 kalimat), Latar Belakang, "
        "Pilihan Kebijakan dengan trade-off, Rekomendasi, Risiko & Mitigasi. Padat, action-oriented."
    ),
    "siaran_pers": (
        "Siaran pers 250–400 kata dengan headline kuat, lead paragraf yang menjawab 5W1H, "
        "kutipan dari anggota legislatif (placeholder [NAMA ANGGOTA]), dan boilerplate penutup."
    ),
}


SYSTEM_TEMPLATE = """\
Anda adalah Penyusun Naskah profesional yang membantu anggota legislatif Indonesia.

Jenis dokumen: {kind}
Pedoman gaya: {style}

Aturan umum:
- Bahasa Indonesia formal, presisi, dan menghormati kaidah hukum.
- Bila diberikan basis riset (bagian "BASIS RISET"), pakai sebagai sumber fakta. Sertakan
  sitasi peraturan dengan format: "UU No. X Tahun YYYY tentang ..." dan, bila tersedia,
  frbr_uri dalam tanda kurung.
- Jangan mengarang fakta hukum atau angka statistik. Jika tidak yakin, gunakan placeholder
  bersudut kurung siku (mis. [DATA BPS DAPIL]).
- Output dalam Markdown.
"""


def draft(
    pool: LLMPool,
    pasal: PasalClient,
    kind: NaskahKind,
    topic: str,
    *,
    with_research: bool = True,
    extra_instructions: str | None = None,
    console: Console | None = None,
) -> str:
    console = console or Console()
    style = STYLE_GUIDES.get(kind)
    if not style:
        raise ValueError(f"jenis naskah tidak dikenal: {kind}. Pilihan: {list(STYLE_GUIDES)}")

    research_block = ""
    if with_research:
        console.print(f"[cyan]penyusun: meminta peneliti merangkum basis hukum '{topic}'[/cyan]")
        memo = peneliti.research(pool, pasal, topic, console=console)
        research_block = f"\n\nBASIS RISET:\n{memo}\n"

    user_msg = (
        f"Topik: {topic}\n"
        f"Jenis: {kind}\n"
        + (f"Instruksi tambahan: {extra_instructions}\n" if extra_instructions else "")
        + research_block
        + "\nSusun naskah lengkap sesuai pedoman gaya."
    )

    return pool.big.chat(
        [
            {"role": "system", "content": SYSTEM_TEMPLATE.format(kind=kind, style=style)},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.5,
        max_tokens=4096,
    )

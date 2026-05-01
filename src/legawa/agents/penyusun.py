"""Penyusun Naskah — drafter pidato, naskah akademik, dan memo kebijakan.

Alur:
  1. Jika user butuh dukungan riset, panggil Peneliti dulu untuk ringkasan basis hukum.
  2. BIG model menyusun naskah final dengan gaya yang sesuai jenis dokumen.
"""

from __future__ import annotations

from typing import Literal

from rich.console import Console

from ..llm import LLMPool
from ..tools.citations import extract_citations_with_context, verify_citations
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
Tanggal penyusunan: {run_date}
Status korpus pasal.id: {corpus_watermark}
Konteks domain: {domain_constraints}

Aturan umum:
- Bahasa Indonesia formal, presisi, dan menghormati kaidah hukum.
- Bila diberikan basis riset (bagian "BASIS RISET"), pakai sebagai sumber fakta. Sertakan
  sitasi peraturan dengan format: "UU No. X Tahun YYYY tentang ..." dan, bila tersedia,
  frbr_uri dalam tanda kurung.
- Jangan mengarang fakta hukum atau angka statistik. Jika tidak yakin, gunakan placeholder
  bersudut kurung siku (mis. [DATA BPS DAPIL]).
- Output dalam Markdown.
"""


# Known cases the model has weak/wrong priors on. When a topic mentions one of
# these, prepend an authoritative fact block to the domain constraints so the
# model can't drift to a familiar-but-wrong frame (e.g. confusing a K-12
# procurement case with a Perguruan Tinggi governance scandal).
_CASE_FACTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("kasus ibam", "ibrahim arief"),
        (
            "FAKTA KASUS IBAM (gunakan ini sebagai sumber, jangan diabaikan): "
            "Kasus Ibam adalah perkara korupsi pengadaan Chromebook dan Chrome Device "
            "Management (CDM) di Kementerian Pendidikan, Kebudayaan, Riset, dan Teknologi "
            "(Kemendikbudristek). Pelaku: Ibrahim Arief, alias Ibam — eks-konsultan Tim "
            "Teknologi Kemendikbudristek di bawah Mendikbudristek Nadiem Makarim. Vonis: "
            "Pengadilan Tipikor 16 April 2026 — 15 tahun penjara, denda Rp 1 miliar, uang "
            "pengganti Rp 16,92 miliar. Distribusi Chromebook ditujukan untuk sekolah dasar "
            "dan menengah dalam Program Digitalisasi Sekolah; INI BUKAN kasus tata kelola "
            "Perguruan Tinggi/PTN/PTS, bukan kasus rekrutmen dosen, bukan kasus akademik. "
            "Kerangka hukum yang dipakai: UU 31/1999 jo UU 20/2001 (Tipikor) dan "
            "Perpres 16/2018 jo Perpres 12/2021 (Pengadaan Barang/Jasa)."
        ),
    ),
)


_K12_TRIGGERS = (
    "sekolah dasar",
    "sdn ",
    " sd ",
    "smp",
    "sma",
    "pendidikan dasar",
    "pendidikan dasar dan menengah",
    "pendidikan menengah",
    "kemendikdasmen",
    "kemendikbud",
    "kemendikbudristek",
    "kemdikbud",
    "bos ",
    "dana bos",
    "chromebook",
    "digitalisasi sekolah",
    "program digitalisasi sekolah",
    "kasus ibam",
    "ibrahim arief",
    "siswa",
    "kepala sekolah",
    "guru ",
)

_PT_TRIGGERS = (
    "perguruan tinggi",
    "ptn ",
    " ptn",
    "pts ",
    " pts",
    "kampus",
    "rektor",
    "dosen",
    "uu pendidikan tinggi",
    "uu sistem pendidikan tinggi",
    "uu no. 12 tahun 2012",
    "uu 12/2012",
    "perguruan tinggi negeri",
)


def _derive_domain_constraints(topic: str, research_block: str = "", extra_instructions: str | None = None) -> str:
    blob = " ".join(part for part in [topic, research_block, extra_instructions or ""] if part).lower()
    # Pad with spaces so " sd " and " ptn " patterns match at edges.
    padded = f" {blob} "
    constraints: list[str] = []

    # If the topic mentions a known case, prepend authoritative facts. These
    # override the model's prior — the most consequential domain-drift fix.
    for keywords, facts in _CASE_FACTS:
        if any(keyword in padded for keyword in keywords):
            constraints.append(facts)

    has_k12 = any(term in padded for term in _K12_TRIGGERS)
    has_pt = any(term in padded for term in _PT_TRIGGERS)

    if has_k12 and not has_pt:
        constraints.append(
            "Fokus pada pendidikan dasar/menengah dan akuntabilitas pengadaan sekolah. "
            "JANGAN bergeser ke pendidikan tinggi, perguruan tinggi (PTN/PTS), kampus, atau rektorat — "
            "isu ini bukan tentang perguruan tinggi."
        )
    elif has_pt and not has_k12:
        constraints.append(
            "Fokus pada pendidikan tinggi (PTN/PTS) dan tata kelola kampus. "
            "JANGAN bergeser ke pendidikan dasar/menengah."
        )
    elif has_k12 and has_pt:
        constraints.append(
            "Topik menyentuh dua jenjang (dasar/menengah dan tinggi). Jelaskan masing-masing secara terpisah; "
            "jangan menggabungkan kerangka hukum keduanya."
        )

    if any(term in padded for term in (" tipikor", "korupsi", "gratifikasi", "suap", "pengadaan", "lkpp")):
        constraints.append(
            "Topik menyentuh korupsi atau pengadaan: prioritaskan anti-korupsi (UU 31/1999 jo UU 20/2001) "
            "dan pengadaan barang/jasa (Perpres 16/2018 jo Perpres 12/2021), serta instansi yang benar-benar "
            "disebut dalam sumber. Jangan mengarang nomor UU."
        )

    if any(term in padded for term in ("outsourcing", "ketenagakerjaan", "buruh", "pekerja", "alih daya")):
        constraints.append(
            "Fokus pada hukum ketenagakerjaan dan perlindungan pekerja; jangan menggeser isu ke sektor lain."
        )

    if any(
        term in padded
        for term in (
            "teknologi informasi",
            " it ",
            "it audit",
            "audit teknis",
            "forensik digital",
            "device management",
            "audit trail",
            "mdm",
            "cdm",
            "endpoint",
            "firmware",
            "serial number",
        )
    ):
        constraints.append(
            "Fokus pada audit teknis, forensik digital, tata kelola perangkat, lisensi perangkat lunak, "
            "log/audit trail, dan bukti digital; jangan mengubahnya menjadi pembahasan hukum pidana semata."
        )

    if not constraints:
        constraints.append(
            "Pertahankan domain persis sesuai topik awal; jangan menukar sektor, jenjang, atau institusi."
        )

    return " ".join(constraints)


def _verify_output_citations(
    pasal: PasalClient,
    text: str,
    *,
    console: Console,
    strict: bool,
) -> None:
    contexts = extract_citations_with_context(text)
    if not contexts:
        return

    checks = verify_citations(pasal, contexts)
    failures = [check for check in checks if not check.found]
    if not failures:
        return

    descriptions: list[str] = []
    for check in failures:
        if check.note:
            descriptions.append(f"{check.reference} ({check.note})")
        else:
            descriptions.append(check.reference)
    msg = "penyusun: draft contains unverifiable citations: " + "; ".join(descriptions)
    if strict:
        console.print(f"[red]{msg}[/red]")
        raise ValueError(msg)
    console.print(f"[yellow]{msg}[/yellow]")


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

    domain_constraints = _derive_domain_constraints(topic, research_block, extra_instructions)

    user_msg = (
        f"Topik: {topic}\n"
        f"Jenis: {kind}\n"
        + (f"Instruksi tambahan: {extra_instructions}\n" if extra_instructions else "")
        + research_block
        + "\nSusun naskah lengkap sesuai pedoman gaya."
    )

    output = pool.big.chat(
        [
            {
                "role": "system",
                "content": SYSTEM_TEMPLATE.format(
                    kind=kind,
                    style=style,
                    run_date=pool.settings.run_date,
                    corpus_watermark=pool.settings.corpus_watermark or "tidak ditentukan",
                    domain_constraints=domain_constraints,
                ),
            },
            {"role": "user", "content": user_msg},
        ],
        temperature=0.5,
        max_tokens=4096,
    )

    _verify_output_citations(
        pasal,
        output,
        console=console,
        strict=pool.settings.strict_citations,
    )
    return output

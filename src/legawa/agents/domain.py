"""SMALL-model domain classifier for Penyusun Naskah.

Replaces the keyword-based ``_derive_domain_constraints`` heuristic with a
learned extractor that takes a topic (plus optional research block and
extra instructions) and returns a structured ``DomainAnalysis``.

The output is rendered into a constraint string that is injected into the
BIG model's system prompt, telling the drafter exactly which sector it is
working in and which sectors to avoid.

Design notes:
- SMALL model only — this is cheap classification, no need for the BIG.
- Pydantic schema — invalid JSON triggers fallback in the caller.
- Few-shot prompt — gives the model 2 worked examples covering different
  sectors (pendidikan + ketenagakerjaan) so its output shape is locked in.
- No tool calls — single round trip, low temperature.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from rich.console import Console

from ..llm import LLMPool


SECTORS = (
    "pendidikan_dasar_menengah",
    "pendidikan_tinggi",
    "ketenagakerjaan",
    "kesehatan",
    "fiskal_anggaran",
    "pertahanan_keamanan",
    "hukum_tipikor",
    "pengadaan_barang_jasa",
    "infrastruktur",
    "lingkungan_hidup",
    "ekonomi_perdagangan",
    "tata_kelola_pemerintahan",
    "agraria_pertanahan",
    "sosial_kemasyarakatan",
    "lain",
)

JENJANG_VALUES = ("dasar", "menengah", "dasar_menengah", "tinggi")


class DomainAnalysis(BaseModel):
    sektor_utama: str = Field(..., description=f"Salah satu dari: {SECTORS}")
    jenjang: str | None = Field(None, description=f"Untuk topik pendidikan: {JENJANG_VALUES}")
    instansi_terkait: list[str] = Field(default_factory=list)
    kasus_terkait: str | None = Field(None, description="Nama kasus spesifik bila topik menyebut, mis. 'Kasus Ibam'.")
    kerangka_hukum_utama: list[str] = Field(default_factory=list)
    rangkuman_konteks: str = Field(..., description="1–2 kalimat ringkas.")
    anti_drift: list[str] = Field(default_factory=list, description="Instruksi spesifik mencegah pergeseran sektor.")


CLASSIFIER_PROMPT = f"""\
Anda adalah klasifier domain untuk Penyusun Naskah legislatif Indonesia.
Diberikan topik (dan opsional konteks riset hukum + instruksi tambahan), tentukan
sektor kebijakan yang relevan dan sediakan instruksi anti-drift untuk mencegah
model penyusun bergeser ke sektor yang salah.

Output WAJIB berupa JSON valid sesuai schema, tanpa teks tambahan, tanpa code fence:

{{
  "sektor_utama": "<satu dari: {', '.join(SECTORS)}>",
  "jenjang": "<satu dari: {', '.join(JENJANG_VALUES)} atau null>",
  "instansi_terkait": ["<nama instansi atau komisi DPR>"],
  "kasus_terkait": "<nama kasus jika topik menyebut kasus tertentu, atau null>",
  "kerangka_hukum_utama": ["<kerangka hukum singkat, mis. 'Tipikor (UU 31/1999)'>"],
  "rangkuman_konteks": "<1-2 kalimat ringkas konteks topik>",
  "anti_drift": ["<instruksi spesifik mencegah pergeseran>"]
}}

Contoh 1:
TOPIK: "respons legislatif atas vonis Kasus Ibam dan akuntabilitas Program Digitalisasi Sekolah"
OUTPUT:
{{
  "sektor_utama": "pendidikan_dasar_menengah",
  "jenjang": "dasar_menengah",
  "instansi_terkait": ["Kementerian Pendidikan Dasar dan Menengah", "Komisi X DPR RI", "Komisi III DPR RI"],
  "kasus_terkait": "Kasus Ibam",
  "kerangka_hukum_utama": ["Tipikor (UU 31/1999 jo UU 20/2001)", "Pengadaan Barang/Jasa (Perpres 16/2018 jo Perpres 12/2021)"],
  "rangkuman_konteks": "Topik mengangkat akuntabilitas pengadaan teknologi pendidikan jenjang dasar/menengah pasca vonis kasus korupsi Chromebook.",
  "anti_drift": [
    "JANGAN bergeser ke pendidikan tinggi, perguruan tinggi (PTN/PTS), kampus, atau rektorat — kasus ini bukan tentang itu.",
    "JANGAN gunakan UU 12/2012 Pendidikan Tinggi sebagai kerangka utama.",
    "Fokus eksklusif pada pengadaan teknologi untuk sekolah dasar dan menengah."
  ]
}}

Contoh 2:
TOPIK: "regulasi outsourcing pasca UU Cipta Kerja"
OUTPUT:
{{
  "sektor_utama": "ketenagakerjaan",
  "jenjang": null,
  "instansi_terkait": ["Kementerian Ketenagakerjaan", "Komisi IX DPR RI"],
  "kasus_terkait": null,
  "kerangka_hukum_utama": ["Ketenagakerjaan (UU 13/2003)", "Cipta Kerja (UU 6/2023)", "PKWT/Alih Daya (PP 35/2021)"],
  "rangkuman_konteks": "Topik tentang perlindungan pekerja alih daya pasca UU Cipta Kerja dan peraturan pelaksana.",
  "anti_drift": [
    "Fokus pada hukum ketenagakerjaan dan perlindungan pekerja.",
    "JANGAN menggeser isu ke sektor lain seperti pendidikan atau infrastruktur."
  ]
}}

Sekarang klasifikasikan topik yang diberikan.
"""


def _parse_analysis(raw: str) -> DomainAnalysis:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    return DomainAnalysis.model_validate(data)


def classify_domain(
    pool: LLMPool,
    topic: str,
    research_block: str = "",
    extra_instructions: str | None = None,
    *,
    console: Console | None = None,
) -> DomainAnalysis:
    """Run the SMALL-model domain classifier.

    Raises ``json.JSONDecodeError`` or ``pydantic.ValidationError`` on failure;
    callers should wrap with their own fallback.
    """
    user_msg_parts = [f"TOPIK: {topic}"]
    if extra_instructions:
        user_msg_parts.append(f"INSTRUKSI TAMBAHAN: {extra_instructions}")
    if research_block:
        # Trim the research block to keep the SMALL classifier prompt tight.
        snippet = research_block.strip()
        if len(snippet) > 4000:
            snippet = snippet[:4000] + "\n[... dipotong ...]"
        user_msg_parts.append(f"KONTEKS RISET (potongan):\n{snippet}")

    raw = pool.small.chat(
        [
            {"role": "system", "content": CLASSIFIER_PROMPT},
            {"role": "user", "content": "\n\n".join(user_msg_parts)},
        ],
        temperature=0.1,
        max_tokens=1024,
    )
    analysis = _parse_analysis(raw)
    if console is not None:
        console.print(
            f"[dim]domain: sektor={analysis.sektor_utama} "
            f"jenjang={analysis.jenjang or '-'} kasus={analysis.kasus_terkait or '-'}[/dim]"
        )
    return analysis


def render_constraints(analysis: DomainAnalysis) -> str:
    """Render a DomainAnalysis as the constraint string injected into the BIG prompt."""
    parts: list[str] = []
    parts.append(f"Konteks domain: {analysis.rangkuman_konteks}")
    parts.append(f"Sektor utama: {analysis.sektor_utama}")
    if analysis.jenjang:
        parts.append(f"Jenjang: {analysis.jenjang}")
    if analysis.instansi_terkait:
        parts.append("Instansi terkait: " + ", ".join(analysis.instansi_terkait) + ".")
    if analysis.kerangka_hukum_utama:
        parts.append("Kerangka hukum yang berlaku: " + "; ".join(analysis.kerangka_hukum_utama) + ".")
    if analysis.kasus_terkait:
        parts.append(f"Kasus yang dirujuk: {analysis.kasus_terkait}.")
    parts.extend(analysis.anti_drift)
    return " ".join(parts)

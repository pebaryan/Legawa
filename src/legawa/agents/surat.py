"""Surat Konstituen — triase dan drafting balasan untuk surat/email konstituen.

Pipeline:
  1. SMALL model: klasifikasi terstruktur (kategori, urgensi, dapil-relevance, sentimen) +
     ekstraksi entitas (nama, lokasi, isu utama, permintaan konkret).
  2. BIG model: jika user minta draft, susun balasan formal Bahasa Indonesia dengan
     gaya pelayanan publik yang empatik namun realistis tentang kewenangan legislator.
  3. Jika klasifikasi menyebut peraturan/UU spesifik, panggil pasal.id untuk verifikasi
     sebelum drafting (opsional, dikontrol flag).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from rich.console import Console

from ..llm import LLMPool
from ..tools.citations import extract_citations_with_context, format_basis_block, verify_citations
from ..tools.pasal import PasalClient


KATEGORI = [
    "aspirasi_kebijakan",       # usulan revisi UU/peraturan
    "pengaduan_layanan_publik", # listrik, kesehatan, pendidikan, dll
    "permohonan_bantuan",       # bantuan sosial, individu
    "undangan_acara",
    "ucapan",                   # selamat, dukacita, dll
    "lain_lain",
]

URGENSI = ["rendah", "sedang", "tinggi", "kritis"]
SENTIMEN = ["positif", "netral", "negatif", "marah"]


class TriaseHasil(BaseModel):
    kategori: str = Field(..., description=f"Salah satu dari: {KATEGORI}")
    urgensi: str = Field(..., description=f"Salah satu dari: {URGENSI}")
    sentimen: str = Field(..., description=f"Salah satu dari: {SENTIMEN}")
    dapil_relevance: bool = Field(..., description="Apakah isu kemungkinan berasal dari/relevan dengan dapil legislator.")
    nama_pengirim: str | None = None
    lokasi: str | None = None
    isu_utama: str = Field(..., description="1 kalimat ringkas inti permasalahan.")
    permintaan_konkret: list[str] = Field(default_factory=list, description="Daftar permintaan eksplisit dari pengirim.")
    peraturan_disebut: list[str] = Field(default_factory=list, description="UU/PP/Perpres yang disebut surat, mis. 'UU 13/2003'.")
    perlu_tindak_lanjut_staf: bool = Field(..., description="Butuh action item untuk staf (cek lapangan, koordinasi dinas, dll).")
    rangkuman: str = Field(..., description="2–3 kalimat rangkuman netral untuk staf.")


@dataclass
class SuratResult:
    triase: TriaseHasil
    raw_classification: str
    balasan: str | None = None


TRIASE_PROMPT = f"""\
Anda adalah staf ahli yang melakukan triase surat/email konstituen untuk anggota legislatif Indonesia.

Klasifikasikan surat berikut dan ekstrak informasi terstruktur. Output WAJIB berupa JSON valid
yang sesuai schema berikut (tanpa teks tambahan, tanpa code fence):

{{
  "kategori": "<salah satu: {', '.join(KATEGORI)}>",
  "urgensi": "<salah satu: {', '.join(URGENSI)}>",
  "sentimen": "<salah satu: {', '.join(SENTIMEN)}>",
  "dapil_relevance": <true|false>,
  "nama_pengirim": "<string atau null>",
  "lokasi": "<string atau null>",
  "isu_utama": "<1 kalimat>",
  "permintaan_konkret": ["<string>", ...],
  "peraturan_disebut": ["<string>", ...],
  "perlu_tindak_lanjut_staf": <true|false>,
  "rangkuman": "<2-3 kalimat>"
}}

Aturan urgensi:
- kritis: mengancam jiwa/keselamatan, bencana, kekerasan.
- tinggi: kerugian materiil signifikan, hak dasar terlanggar, urgensi waktu < 1 minggu.
- sedang: pengaduan layanan publik standar, aspirasi kebijakan dengan dampak konstituen.
- rendah: ucapan, undangan rutin, pertanyaan informatif.
"""


REPLY_PROMPT = """\
Anda adalah staf komunikasi legislator Indonesia. Susun balasan formal Bahasa Indonesia
untuk surat konstituen berikut.

Pedoman:
- Sapaan formal sesuai jenis pengirim ("Yth. Bapak/Ibu [Nama]" atau "Yth. Saudara/i").
- Akui penerimaan surat dan empati pada isu yang diangkat (1 paragraf).
- Jelaskan secara realistis kewenangan legislator: legislator MEMBUAT undang-undang dan
  mengawasi pemerintah, BUKAN eksekusi langsung. Untuk pengaduan layanan publik, arahkan
  ke instansi/lembaga yang berwenang, namun tegaskan akan dilakukan pengawasan/koordinasi.
- Jika ada peraturan yang relevan dan terverifikasi (lihat bagian "BASIS HUKUM"), sitasi.
- Tutup dengan komitmen tindak lanjut konkret (mis. teruskan ke komisi terkait, agendakan
  rapat dengar pendapat, dll) — jangan janji yang tidak bisa ditepati.
- Tanda tangan: "Hormat kami,\\n[NAMA ANGGOTA LEGISLATIF]\\n[FRAKSI/DAERAH PEMILIHAN]"
- Panjang 250–450 kata. Output Markdown.
"""


def _parse_triase(raw: str) -> TriaseHasil:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    # Some models prepend explanations; try to isolate the JSON object.
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    return TriaseHasil.model_validate(data)


def _verify_peraturan(pasal: PasalClient, refs: list[str], console: Console) -> str:
    if not refs:
        return ""
    try:
        return format_basis_block(pasal, refs)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]surat: gagal membangun basis hukum: {e}[/red]")
        raise


def triage(
    pool: LLMPool,
    text: str,
    *,
    console: Console | None = None,
) -> SuratResult:
    console = console or Console()
    raw = pool.small.chat(
        [
            {"role": "system", "content": TRIASE_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
        max_tokens=1024,
    )
    try:
        triase = _parse_triase(raw)
    except (json.JSONDecodeError, ValidationError) as e:
        console.print(f"[red]surat: gagal parse hasil triase: {e}[/red]")
        console.print(f"[dim]raw: {raw[:500]}[/dim]")
        raise

    return SuratResult(triase=triase, raw_classification=raw)


def reply(
    pool: LLMPool,
    pasal: PasalClient,
    text: str,
    *,
    verify_law: bool = True,
    console: Console | None = None,
) -> SuratResult:
    console = console or Console()
    result = triage(pool, text, console=console)
    t = result.triase
    console.print(
        f"[cyan]surat: kategori={t.kategori} urgensi={t.urgensi} sentimen={t.sentimen} "
        f"dapil={t.dapil_relevance} tindak_lanjut={t.perlu_tindak_lanjut_staf}[/cyan]"
    )

    basis = _verify_peraturan(pasal, t.peraturan_disebut, console) if verify_law else ""

    user_msg = (
        f"SURAT KONSTITUEN:\n---\n{text}\n---\n\n"
        f"HASIL TRIASE (JSON):\n{result.raw_classification}\n"
        + (f"\n{basis}\n" if basis else "")
        + "\nSusun balasan sesuai pedoman."
    )
    result.balasan = pool.big.chat(
        [
            {"role": "system", "content": REPLY_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=2048,
    )

    draft_contexts = extract_citations_with_context(result.balasan or "")
    if draft_contexts:
        checks = verify_citations(pasal, draft_contexts)
        failures = [check for check in checks if not check.found]
        if failures:
            descriptions = [
                f"{check.reference} ({check.note})" if check.note else check.reference
                for check in failures
            ]
            msg = "surat: draft contains unverifiable citations: " + "; ".join(descriptions)
            console.print(f"[red]{msg}[/red]")
            raise ValueError(msg)
    return result


def format_report(result: SuratResult) -> str:
    """Render triase + balasan sebagai satu dokumen Markdown."""
    t = result.triase
    parts = [
        "# Triase Surat Konstituen",
        "",
        f"- **Kategori**: {t.kategori}",
        f"- **Urgensi**: {t.urgensi}",
        f"- **Sentimen**: {t.sentimen}",
        f"- **Relevansi dapil**: {'ya' if t.dapil_relevance else 'tidak'}",
        f"- **Tindak lanjut staf**: {'ya' if t.perlu_tindak_lanjut_staf else 'tidak'}",
        f"- **Pengirim**: {t.nama_pengirim or '-'}",
        f"- **Lokasi**: {t.lokasi or '-'}",
        "",
        f"**Isu utama**: {t.isu_utama}",
        "",
        "**Permintaan konkret**:",
    ]
    parts.extend(f"- {p}" for p in (t.permintaan_konkret or ["(tidak ada)"]))
    if t.peraturan_disebut:
        parts += ["", "**Peraturan disebut**:"]
        parts.extend(f"- {p}" for p in t.peraturan_disebut)
    parts += ["", "**Rangkuman untuk staf**:", t.rangkuman]
    if result.balasan:
        parts += ["", "---", "", "# Draf Balasan", "", result.balasan]
    return "\n".join(parts)

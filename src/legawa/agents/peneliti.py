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

Tanggal penyusunan: {run_date}
Status korpus pasal.id: {corpus_watermark}

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

Nilai-nilai Demokrasi & HAM — WAJIB dipertimbangkan dalam setiap rekomendasi:
1. **Kedaulatan Rakyat** — apakah peraturan ini berpihak pada kepentingan publik?
2. **Prinsip Demokrasi** — apakah ada potensi abuse of power?
3. **Hak Asasi Manusia** — identifikasi dampak HAM dari peraturan terkait.
4. **Etika Politik** — berikan do's and don'ts untuk legislator.
Sertakan di bagian **Rekomendasi Tindak Lanjut**.
"""


# Canonical primary statutes for known sectors. When the topic / queries blob
# matches any keyword in a row, that FRBR URI is fetched directly via
# get_law() and merged into Peneliti's synthesis context. Closes the failure
# mode where pasal.id /search ranking misses a sector's operative statute.
#
# Only include statutes that are currently 'berlaku' — superseded laws should
# never be probed as canonical (they would mislead the BIG model into anchoring
# on the wrong framework). Verify status before adding new entries.
_CANONICAL_PROBES: list[tuple[tuple[str, ...], str]] = [
    # Tipikor (UU Pemberantasan Tindak Pidana Korupsi)
    (("tipikor", "korupsi", "gratifikasi", "suap", "konflik kepentingan"), "akn/id/act/uu/1999/31"),
    (("tipikor", "korupsi", "gratifikasi", "suap", "konflik kepentingan"), "akn/id/act/uu/2001/20"),
    # Pengadaan barang/jasa pemerintah
    (("pengadaan", "barang jasa", "barang/jasa", "procurement", "chromebook"), "akn/id/act/perpres/2018/16"),
    (("pengadaan", "barang jasa", "barang/jasa", "procurement", "chromebook"), "akn/id/act/perpres/2021/12"),
    # Ketenagakerjaan + Cipta Kerja
    (("outsourcing", "ketenagakerjaan", "buruh", "pekerja", "tenaga kerja"), "akn/id/act/uu/2003/13"),
    (("outsourcing", "ketenagakerjaan", "buruh", "pekerja", "tenaga kerja"), "akn/id/act/uu/2023/6"),
    (("outsourcing", "ketenagakerjaan", "buruh", "pekerja", "tenaga kerja"), "akn/id/act/pp/2021/35"),
    # Pendidikan & kesejahteraan dosen
    (("dosen", "guru", "tunjangan profesi", "kesejahteraan dosen", "permendiktisaintek"), "akn/id/act/uu/2005/14"),  # UU Guru dan Dosen
    (("dosen", "perguruan tinggi", "ptn", "pts", "rektor"), "akn/id/act/uu/2012/12"),  # UU Pendidikan Tinggi
    (("tukin", "tunjangan kinerja", "asn"), "akn/id/act/perpres/2025/19"),  # Tukin ASN 2025
    # Kesehatan & pendidikan kedokteran
    (("kesehatan", "tenaga kesehatan", "rumah sakit", "dokter", "ppds", "internsip"), "akn/id/act/uu/2023/17"),  # UU Kesehatan (omnibus)
    (("kesehatan", "tenaga kesehatan", "rumah sakit", "dokter", "ppds"), "akn/id/act/pp/2024/28"),  # PP pelaksanaan UU 17/2023
    (("dokter", "ppds", "pendidikan kedokteran", "pendidikan dokter spesialis"), "akn/id/act/uu/2013/20"),  # UU Pendidikan Kedokteran
    (("internsip", "dokter internsip", "dokter gigi internsip"), "akn/id/act/permenkes/2022/7"),  # Permenkes Internsip
    # Program Makan Bergizi Gratis & keselamatan pangan publik
    (("makan bergizi gratis", "mbg", "badan gizi nasional", "bgn", "sppg", "satuan pelayanan pemenuhan gizi"),
     "akn/id/act/perpres/2024/83"),  # Perpres pembentukan BGN
    (("makan bergizi gratis", "mbg", "sppg", "tata kelola gizi"),
     "akn/id/act/perpres/2025/115"),  # Perpres tata kelola MBG
    (("pangan", "keselamatan pangan", "keracunan pangan", "haccp", "mutu pangan"),
     "akn/id/act/uu/2012/18"),  # UU Pangan
    (("perlindungan konsumen", "konsumen", "ganti rugi konsumen"),
     "akn/id/act/uu/1999/8"),  # UU Perlindungan Konsumen
    # Transportasi (lalu lintas, perkeretaapian, EV, asuransi korban)
    (("lalu lintas", "angkutan jalan", "kendaraan bermotor", "sopir", "pengemudi", "taksi", "angkutan umum"),
     "akn/id/act/uu/2009/22"),  # UU LLAJ
    (("kereta api", "perkeretaapian", "perlintasan sebidang", "krl", "kai"),
     "akn/id/act/uu/2007/23"),  # UU Perkeretaapian
    (("kendaraan listrik", "ev", "kendaraan bermotor listrik", "battery electric"),
     "akn/id/act/perpres/2019/55"),  # Perpres percepatan EV
    (("asuransi penumpang", "jasa raharja", "santunan korban"),
     "akn/id/act/uu/1964/33"),  # UU Dana Pertanggungan Wajib Kecelakaan Penumpang
    (("kecelakaan lalu lintas", "asuransi korban kecelakaan", "jasa raharja"),
     "akn/id/act/uu/1964/34"),  # UU Dana Pertanggungan Wajib Kecelakaan Lalu Lintas Jalan
    # Hukum acara & KPK kelembagaan (Komisi III)
    (("kuhap", "hukum acara pidana", "penyidikan", "penyelidikan", "praperadilan"),
     "akn/id/act/uu/1981/8"),  # KUHAP
    (("kpk", "komisi pemberantasan korupsi"),
     "akn/id/act/uu/2002/30"),  # UU pembentukan KPK
    (("kpk", "komisi pemberantasan korupsi", "dewan pengawas kpk"),
     "akn/id/act/uu/2019/19"),  # UU Perubahan Kedua KPK
    # Sosial, kebencanaan, perlindungan anak & perempuan (Komisi VIII)
    (("bencana", "kebencanaan", "bnpb", "bpbd", "tanggap darurat"),
     "akn/id/act/uu/2007/24"),  # UU Penanggulangan Bencana
    (("perlindungan anak", "kekerasan terhadap anak", "hak anak"),
     "akn/id/act/uu/2014/35"),  # UU Perubahan Perlindungan Anak
    (("kdrt", "kekerasan dalam rumah tangga", "pkdrt"),
     "akn/id/act/uu/2004/23"),  # UU PKDRT
    (("kesejahteraan sosial", "bantuan sosial", "pmks"),
     "akn/id/act/uu/2009/11"),  # UU Kesejahteraan Sosial
    # Diplomasi & perjanjian internasional (Komisi I)
    (("hubungan luar negeri", "diplomasi", "wni di luar negeri", "perlindungan wni"),
     "akn/id/act/uu/1999/37"),  # UU Hubungan Luar Negeri
    (("perjanjian internasional", "traktat", "ratifikasi"),
     "akn/id/act/uu/2000/24"),  # UU Perjanjian Internasional
    # Pertanian, ketahanan pangan, lahan (Komisi IV)
    (("lahan pertanian", "alih fungsi lahan", "ketahanan pangan", "lp2b"),
     "akn/id/act/uu/2009/41"),  # UU Perlindungan Lahan Pertanian Pangan Berkelanjutan
    # BUMN, perdagangan, standardisasi (Komisi VI)
    (("bumn", "badan usaha milik negara"),
     "akn/id/act/uu/2003/19"),  # UU BUMN
    (("perdagangan", "perdagangan dalam negeri", "perdagangan luar negeri"),
     "akn/id/act/uu/2014/7"),  # UU Perdagangan
    (("standardisasi", "sni", "penilaian kesesuaian"),
     "akn/id/act/uu/2014/20"),  # UU Standardisasi & Penilaian Kesesuaian
    # UMKM (Komisi VII)
    (("umkm", "usaha mikro", "usaha kecil", "usaha menengah"),
     "akn/id/act/uu/2008/20"),  # UU UMKM
    # Keuangan & fiskal (Komisi XI)
    (("p2sk", "sektor keuangan", "fintech", "pinjol", "pinjaman online"),
     "akn/id/act/uu/2023/4"),  # UU P2SK
    (("ojk", "otoritas jasa keuangan"),
     "akn/id/act/uu/2011/21"),  # UU OJK
    (("pajak", "perpajakan", "hpp", "harmonisasi peraturan perpajakan"),
     "akn/id/act/uu/2021/7"),  # UU HPP
    # Energi, lingkungan hidup, pertambangan (Komisi XII)
    (("ketahanan energi", "kebijakan energi", "energi nasional", "transisi energi", "energi terbarukan"),
     "akn/id/act/uu/2007/30"),  # UU Energi
    (("lingkungan hidup", "pplh", "amdal", "izin lingkungan"),
     "akn/id/act/uu/2009/32"),  # UU PPLH
    (("minerba", "mineral batubara", "pertambangan mineral"),
     "akn/id/act/uu/2020/3"),  # UU Perubahan Minerba
    # HAM & keimigrasian (Komisi XIII)
    (("ham", "hak asasi manusia", "komnas ham"),
     "akn/id/act/uu/1999/39"),  # UU HAM
    (("keimigrasian", "imigrasi", "paspor", "pengungsi"),
     "akn/id/act/uu/2011/6"),  # UU Keimigrasian
]


def _collect_snippet(obj: Any, max_chars: int = 800) -> str:
    parts: list[str] = []

    def walk(value: Any) -> None:
        if len(" ".join(parts)) >= max_chars:
            return
        if isinstance(value, str):
            text = " ".join(value.split())
            if text:
                parts.append(text)
        elif isinstance(value, dict):
            for key in ("title", "name", "status", "frbr_uri", "text", "content", "description"):
                if key in value:
                    walk(value[key])
            for key, nested in value.items():
                if key not in {"title", "name", "status", "frbr_uri", "text", "content", "description"}:
                    walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(obj)
    joined = " | ".join(dict.fromkeys(parts))
    return joined[:max_chars]


def _law_to_hit(law: Any, frbr_uri: str) -> dict[str, Any]:
    title = None
    status = None
    if isinstance(law, dict):
        title = law.get("title") or law.get("work", {}).get("title")
        status = law.get("status") or law.get("work", {}).get("status")
    return {
        "source": "exact_probe",
        "frbr_uri": frbr_uri,
        "title": title or frbr_uri,
        "status": status,
        "excerpt": _collect_snippet(law),
    }


def _canonical_probe_uris(topic: str, queries: list[str]) -> list[str]:
    blob = " ".join([topic, *queries]).lower()
    uris: list[str] = []
    for keywords, frbr_uri in _CANONICAL_PROBES:
        if any(keyword in blob for keyword in keywords) and frbr_uri not in uris:
            uris.append(frbr_uri)
    return uris


def _probe_exact_laws(pasal: PasalClient, topic: str, queries: list[str], console: Console) -> list[dict[str, Any]]:
    uris = _canonical_probe_uris(topic, queries)
    if not uris:
        return []

    console.print(f"[dim]peneliti: exact probes {uris}[/dim]")
    hits: list[dict[str, Any]] = []
    for frbr_uri in uris:
        try:
            law = pasal.get_law(frbr_uri)
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]peneliti: exact probe gagal {frbr_uri}: {e}[/yellow]")
            continue
        hits.append(_law_to_hit(law, frbr_uri))
    return hits


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

    exact_hits = _probe_exact_laws(pasal, topic, queries, console)

    console.print(f"[cyan]peneliti: menjalankan {len(queries)} pencarian paralel[/cyan]")
    with ThreadPoolExecutor(max_workers=min(6, len(queries))) as ex:
        batches = list(ex.map(lambda q: pasal.search(q, limit=10), queries))

    if exact_hits:
        batches = batches + [{"hits": exact_hits}]

    hits = _dedupe_hits(batches)
    console.print(f"[cyan]peneliti: {len(hits)} hit unik, sintesis dengan model besar[/cyan]")

    payload = {"topic": topic, "queries": queries, "hits": hits[:40]}
    output = pool.big.chat(
        [
            {
                "role": "system",
                "content": SYNTHESIS_PROMPT.format(
                    run_date=pool.settings.run_date,
                    corpus_watermark=pool.settings.corpus_watermark or "tidak ditentukan",
                ),
            },
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

# legawa

Asisten multi-agen untuk anggota legislatif Indonesia (DPR/DPRD). Berjalan di atas dua instance llama.cpp lokal (Qwen3) dan menggunakan API publik [pasal.id](https://pasal.id) sebagai sumber peraturan perundang-undangan.

## Arsitektur

```
                        ┌──────────────────────┐
   pengguna (CLI) ─────▶│   Typer orchestrator │
                        └──────────┬───────────┘
                                   │
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                     ▼
     ┌────────────────┐  ┌──────────────────┐  ┌────────────────────┐
     │  Analis RUU    │  │  Peneliti Hukum  │  │  Penyusun Naskah   │
     │  (BIG, tools)  │  │  (SMALL→BIG)     │  │  (BIG, opt. riset) │
     └────────┬───────┘  └─────────┬────────┘  └─────────┬──────────┘
              │                    │                     │
              └──────────┬─────────┴─────────────────────┘
                         ▼
              ┌────────────────────┐
              │   pasal.id REST    │  search · list · get_law
              └────────────────────┘
```

Routing model:
- **BIG** (`localhost:8080`, Qwen3 ~35B) — sintesis, drafting, analisis pasal-per-pasal.
- **SMALL** (`mi25:8080`, Qwen3 ~27B) — klasifikasi, ekstraksi, ekspansi query.

## Setup

```bash
cp .env.example .env
# isi PASAL_API_TOKEN dan sesuaikan URL llama.cpp jika perlu

pip install -e .
legawa health
```

## Pemakaian

```bash
# Analisis RUU dari PDF
legawa analyze ./ruu-cipta-kerja.pdf --out output/analisis.md

# Riset hukum bertema
legawa research "perlindungan data pribadi sektor kesehatan" -o output/riset.md

# Susun pidato/memo/naskah akademik
legawa draft pidato "urgensi RUU Masyarakat Adat" -o output/pidato.md
legawa draft memo_kebijakan "subsidi BBM 2026" --no-research
legawa draft naskah_akademik "perubahan UU Pemilu" -i "fokus pada presidential threshold"

# Triase + balasan surat konstituen
legawa surat ./inbox/aspirasi-001.txt -o output/balasan.md
legawa surat ./inbox/aspirasi-001.txt --triase-only

# Kelola cache pasal.id
legawa cache stats
legawa cache purge   # hapus entri expired
```

## Cache pasal.id

Semua panggilan REST pasal.id dilewatkan melalui SQLite cache:

| endpoint  | TTL       |
|-----------|-----------|
| `search`  | 1 jam     |
| `laws`    | 1 jam     |
| `laws/{}` | 24 jam    |

Lokasi default: `~/.legawa/cache.db`. Override dengan `LEGAWA_CACHE_PATH=/custom/path.db`.

## Regression check

`scripts/regression_check.py` probes pasal.id for status and amendment-chain drift on every URI in `agents/peneliti._CANONICAL_PROBES` plus every regulation cited in `tests/fixtures/*.txt`, comparing against `scripts/regression_baseline.json`. Run periodically (suggested ~3-week cadence) to detect when an operative regulation has been superseded:

```bash
python scripts/regression_check.py            # exit 1 on drift, 0 if clean
python scripts/regression_check.py --json     # machine-readable diff
python scripts/regression_check.py --update-baseline  # snapshot current state
```

Does NOT re-run the live agents (those depend on the user's local llama.cpp + pasal.id credentials). Use it after model swaps or before publishing whitepapers to catch corpus drift early.

## Roadmap

- [ ] **Pemantau Berita** — agen kelima untuk monitoring isu komisi dari sumber berita Indonesia (Kompas, Tempo, Detik, Antara). SMALL untuk klasifikasi & ekstraksi isu, BIG untuk daily/weekly digest dengan tautan ke peraturan terkait via pasal.id. Tambahkan setelah keempat agen pertama dipakai di lapangan.

## Catatan

- Setiap klaim agen tentang peraturan existing dilengkapi `frbr_uri` pasal.id agar dapat diverifikasi.
- Output tidak menggantikan tinjauan hukum profesional. Selalu review oleh staf ahli sebelum publikasi.

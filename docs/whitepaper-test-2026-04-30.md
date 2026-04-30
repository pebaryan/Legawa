# Whitepaper: First Live Validation of legawa Multi-Agent System

**Subject:** End-to-end validation of legawa, a multi-agent assistant for Indonesian legislators, against a current real-world legislative issue
**Date of run:** 2026-04-30
**Repository:** `https://github.com/pebaryan/Legawa` (commit `3265a18`)
**Hardware:** Workstation with Qwen3-class models on llama.cpp; NVIDIA V100 over LAN (host `mi25` — name retained from a previous GPU)
**Author:** Engineering test report

---

## 1. Executive Summary

This report documents the first live, end-to-end exercise of the legawa system against a current Indonesian socio-legal issue: the late-April 2026 controversy surrounding new outsourcing-related ministerial regulations (Permenaker), which was simultaneously trending on social media (`#BuruhBersuaraBukanAnarkis`) and in mainstream news (Detik, Kompas).

We constructed a synthetic but realistic constituent letter from a worker affected by these regulations, then exercised three of legawa's four production agents — Surat Konstituen (constituent-letter triage and reply), Peneliti Hukum (legal researcher), and supporting infrastructure (LLM routing, pasal.id REST integration, SQLite cache).

**Outcome:** all agents produced publication-quality output. Three latent defects were uncovered and fixed during the run. The system correctly cited Indonesian statutes by `frbr_uri`, distinguished between superseded and active regulations, applied legal Latin maxims appropriately, and — notably — *honestly admitted* when a referenced regulation was not yet indexed in the source corpus rather than fabricating.

The test validates the SMALL→fan-out→BIG synthesis pattern as the right routing strategy for this class of work, and demonstrates that local Qwen3 deployments on llama.cpp can reach the legal-domain quality bar without cloud dependencies.

---

## 2. System Under Test

### 2.1 Architecture

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
              │       ┌────────────┴─────────────┐       │
              │       ▼                          ▼       │
              │  ┌──────────────────┐    ┌─────────────────┐
              │  │ Surat Konstituen │    │   pasal.id      │
              │  │ (SMALL → BIG)    │───▶│   REST + cache  │
              │  └──────────────────┘    └─────────────────┘
              └─────────────────────────────────────┘
```

### 2.2 Model routing

| Role  | Endpoint              | Model       | Used for                                                  |
| ----- | --------------------- | ----------- | --------------------------------------------------------- |
| BIG   | `localhost:8080/v1`   | Qwen3 ~35B  | Synthesis, drafting, deep analysis, tool-calling          |
| SMALL | `mi25:8080/v1`        | Qwen3 ~27B  | Classification, extraction, query expansion, parallel jobs |

Both endpoints expose an OpenAI-compatible chat/completions API via llama.cpp; legawa uses the `openai` Python SDK. Thinking-mode (`<think>...</think>` reasoning blocks) is **disabled by default** at the LLM-wrapper level (defect 6.1.b below) and re-enabled per call when reasoning helps.

### 2.3 Data source

**pasal.id REST API** (`https://pasal.id/api/v1`) — bearer-authenticated, indexes ~139k Indonesian regulations 1945–2026 across UU / PERPPU / PP / PERPRES / PERMEN / PERDA. Three endpoints used: `/search`, `/laws`, `/laws/{frbr_uri}`. Wrapped by a transparent SQLite cache (`tools/cache.py`) with TTLs: search & list 1h, full document 24h.

---

## 3. Test Methodology

### 3.1 Scenario selection

We sourced two parallel signals on 2026-04-30:

- **News (detik.com/terpopuler):** "New Outsourcing Regulations Issued — The Ministry of Labor releases updated rules governing outsourcing practices for Indonesian businesses and workers." (rank #2, policy/social)
- **Social media (trends24.in/indonesia):** `#BuruhBersuaraBukanAnarkis` ("Workers' voices are not anarchy") trending top-10 on Twitter Indonesia.

Both signals point to the same underlying issue: a fresh ministerial regulation perceived to weaken worker protections, with affected workers organising public response. This is a textbook constituent-issue: it ties directly to UU 13/2003 (Ketenagakerjaan), UU 6/2023 (Cipta Kerja, replacing UU 11/2020), and Putusan MK 27/PUU-IX/2011 — three of the most-cited instruments in Indonesian labour law.

### 3.2 Fixture design

A 600-word synthetic constituent letter (`tests/fixtures/surat-buruh-outsourcing.txt`) was authored from the perspective of a Cikarang garment worker. The letter:

- States identity, location (dapil signal), and 8-year outsourcing history
- References four legal instruments by name: UU 13/2003 Pasal 64–66, UU 6/2023, Putusan MK 27/PUU-IX/2011, UUD 1945 Pasal 28E ayat (3)
- Mentions the trending hashtag explicitly
- Closes with three concrete `permintaan` (requests): RDP with Menaker, support for UU revision, dialogue facilitation

The letter was crafted to be plausible but adversarial — it intentionally mixes a strong claim ("Permenaker memperluas outsourcing") with citations the agent can verify. A correct triage must extract all four statutes; a correct reply must sit within legislator authority (pengawasan, not eksekusi) and not promise what the office cannot deliver.

### 3.3 Test sequence

1. `legawa health` — connectivity & smoke
2. `legawa surat ... --triase-only` — SMALL classification only (cheapest path)
3. `legawa surat ...` — full triage + pasal.id verification + BIG drafted reply
4. `legawa research "..."` — Peneliti agent: SMALL fan-out to 6 queries, parallel pasal.id, BIG synthesis
5. `legawa cache stats` — confirm cache populated

---

## 4. Results

### 4.1 Health check

```
pasal.id  : https://pasal.id/api/v1
LLM big   : http://localhost:8080/v1  (qwen3)
LLM small : http://mi25:8080/v1  (qwen3)
OK big: OK
OK small: OK
OK pasal.id: query 'ketenagakerjaan' -> 1 hit
```

All three checks green after defect 6.1.a/b were fixed (see §6).

### 4.2 Surat — triage (SMALL classifier)

The classifier produced a JSON object validated against the Pydantic `TriaseHasil` schema. Selected fields:

| Field                       | Value                                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------ |
| `kategori`                  | `aspirasi_kebijakan` ✓ correct (vs pengaduan/permohonan/undangan/ucapan)                          |
| `urgensi`                   | `tinggi` ✓ correct (kerugian materiil signifikan + hak dasar terlanggar)                          |
| `sentimen`                  | `marah` ✓ correct (constituent uses words like "merugikan", "memperburuk")                         |
| `dapil_relevance`           | `true` ✓ correct (Cikarang/Bekasi is a real industrial dapil)                                     |
| `nama_pengirim`             | `"Sukma Wijayanti"`                                                                              |
| `lokasi`                    | `"Cikarang, Bekasi, Jawa Barat"`                                                                  |
| `peraturan_disebut`         | 5 items including UU 13/2003 Pasal 64–66, UU 6/2023, Putusan MK 27/PUU-IX/2011, UUD 1945 Pasal 28E |
| `perlu_tindak_lanjut_staf`  | `true`                                                                                           |
| `permintaan_konkret`        | 3 items, each matching the letter's explicit requests                                            |

**Quality assessment:** classification is correct on every dimension. Entity extraction recovered all four statutes plus the Permenaker reference. Sentiment shifted between two runs (`negatif` → `marah`) — both defensible reads, indicates the schema's enum boundaries are appropriately fuzzy.

### 4.3 Surat — full pipeline (verification + reply)

After triage, the agent performed pasal.id `search` calls for each `peraturan_disebut`, then BIG drafted a 450-word formal reply. Selected excerpts:

> "Sebagai Anggota DPR RI yang membidangi Komisi IX, saya ingin menjelaskan bahwa fungsi utama kami dalam konteks ini adalah menyusun undang-undang dan melakukan pengawasan terhadap pelaksanaan kebijakan oleh Pemerintah. Kami tidak memiliki kewenangan eksekutif langsung untuk membatalkan Peraturan Menteri, namun kami memiliki mandat kuat untuk memanggil Menteri Ketenagakerjaan..."

> "1. **Fungsi Pengawasan:** Saya akan mengagendakan Rapat Dengar Pendapat (RDP) tertutup dengan Kementerian Ketenagakerjaan dan Kementerian Hukum dan HAM..."

> "Hormat kami, [NAMA ANGGOTA LEGISLATIF] Anggota DPR RI Komisi IX [Fraksi/Daerah Pemilihan]"

**Quality assessment:**

- ✓ Sapaan formal, empathetic acknowledgement, factual scope correction (legislator role).
- ✓ Cites UU 6/2023 and UUD 1945 Pasal 28E as constitutional anchor.
- ✓ Three concrete `tindak lanjut` map 1:1 to the constituent's three requests.
- ✓ Honest about constitutional limits ("kami tidak memiliki kewenangan eksekutif langsung untuk membatalkan Peraturan Menteri").
- ✓ Placeholders (`[NAMA ANGGOTA LEGISLATIF]`, `[Fraksi/Daerah Pemilihan]`) preserved correctly for staff fill-in.
- ✓ No hallucinated UU numbers.

### 4.4 Peneliti — legal research

Topic: *"regulasi outsourcing pasca UU Cipta Kerja dan dampak Permenaker terbaru"*

**Query expansion (SMALL):** 6 queries generated in parallel:

1. UU Cipta Kerja PP 35 2021 penyaluran tenaga kerja outsourcing
2. Permenaker 10 2018 perubahan penyaluran tenaga kerja
3. PP 35 2021 jenis pekerjaan yang dapat diserahkan kepada pihak ketiga
4. batasan jangka waktu perjanjian kerja penyaluran tenaga kerja outsourcing
5. tanggung jawab pemberi kerja dan perusahaan penyalur tenaga kerja UU Ketenagakerjaan
6. peluang dan tantangan hukum outsourcing pasca UU Cipta Kerja

**Retrieval:** 6 parallel pasal.id `/search` calls via `ThreadPoolExecutor`, returning **31 unique hits** after dedupe by `frbr_uri`.

**Synthesis (BIG):** A 5-section memo (`output/riset-outsourcing.md`, 55 lines, ~1,800 words). Selected technical correctness highlights:

- Identified the **right** primary instruments: UU 6/2023 (penetapan), UU 11/2020 (materiil), PP 35/2021 (peraturan pelaksana). All three with verifiable `frbr_uri`.
- Correctly traced the paradigm shift in PP 35/2021: from *"jenis pekerjaan"* (UU 13/2003, restrictive) to *"kegiatan usaha bukan bidang usaha utama"* (more permissive).
- Applied legal Latin maxims correctly: *lex superior derogat legi inferiori*, *lex specialis derogat legi generali*.
- Identified PKWT outsourcing limits: max 3 years, extendable once by 3 years (= 6 total).
- **Honestly noted a corpus gap**: "Hasil pencarian tidak menemukan Permenaker terbaru pasca-PP 35/2021... Kemungkinan besar, implementasi teknis masih mengacu pada prinsip PP 35/2021 atau peraturan teknis lain yang belum terindeks dalam hasil pencarian ini." This is the system refusing to fabricate when grounding is missing — exactly the desired behaviour.
- Generated 4 substantive recommendations for the legislator, including harmonisation check against Perda — a level of detail not present in the constituent letter or in any single search result.

**Citations check:** every regulation cited carries an explicit `frbr_uri`. Sample audit of three random claims against pasal.id: all three resolve to genuine documents matching the cited content.

### 4.5 Cache behaviour

```
{'entries': 11, 'bytes': 22079, 'session_hits': 0, 'session_misses': 0}
```

11 entries (~22 KB) accumulated across the surat verification pass (5 entries) and the peneliti research pass (6 entries). Session hit/miss counters are zero because they reset per CLI invocation; on-disk persistence carries entries across runs. Subsequent identical queries within the TTL window will return without an HTTP round-trip.

---

## 5. Quality Assessment

| Dimension                    | Bar                                                          | Result |
| ---------------------------- | ------------------------------------------------------------ | ------ |
| Citation discipline          | Every regulation claim must include a verifiable `frbr_uri`  | ✓ Pass |
| No fabricated UU numbers     | Zero hallucinated statute numbers                            | ✓ Pass |
| Honest about gaps            | Admit corpus gaps rather than invent                         | ✓ Pass — Peneliti explicitly flagged absent Permenaker |
| Scope discipline (Surat)     | Stay within legislator authority; no executive overreach     | ✓ Pass |
| Bahasa Indonesia register    | Formal, presisi, kaidah hukum                                | ✓ Pass |
| Structural conformance       | Markdown headings match agent system prompts                 | ✓ Pass |
| Action-oriented output       | Recommendations are concrete, not generic                    | ✓ Pass — RDP, harmonisasi Perda, evaluasi PKWT |
| Latency                      | End-to-end surat: ~15s. End-to-end research: ~90s.            | Acceptable for human-in-the-loop |

---

## 6. Defects Discovered & Fixes Applied

### 6.1 Critical defects (fixed during the run)

#### a) Windows console UTF-8 crash

**Symptom:** Every CLI command crashed with `UnicodeEncodeError: 'charmap' codec can't encode character '✓'` on Windows. Rich library uses UTF-8 glyphs (`✓`, `→`) but Python's stdout defaulted to cp1252 on the legacy console.

**Fix:** Reconfigure stdio on Windows at module import:
```python
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
```
Plus replaced unicode glyphs in `health` output with ASCII (`OK`/`FAIL`) for defence-in-depth.

#### b) Qwen3 thinking tokens exhausting `max_tokens`

**Symptom:** Both LLM endpoints returned empty content under `max_tokens=8` (health probe) and `max_tokens=1024` (surat triage). Underlying cause: Qwen3 emits `<think>...</think>` reasoning blocks before the visible answer; with thinking enabled by default, the entire token budget was consumed by reasoning before any content was produced.

**Fix:** Disabled thinking mode by default at the LLM-wrapper level via `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`. Added `think: bool = False` opt-in flag for callers that benefit from reasoning (e.g., deep RUU analysis with the tool-calling loop). Centralised `<think>` stripping in `llm.chat` so any residual reasoning never bleeds into agent outputs.

#### c) Rich markup crash on error strings

**Symptom:** When health-probe error messages contained `<undefined>` (DNS resolution error formatting), Rich attempted to parse `<undefined>` as a markup tag and crashed.

**Fix:** Wrap all dynamic strings passed to `console.print()` with `rich.markup.escape()`.

### 6.2 Observations (not defects, worth noting)

#### d) Date freshness vs corpus indexing

The Peneliti agent correctly identified that the "Permenaker terbaru" referenced in the day's news was not yet present in pasal.id's corpus. This is expected behaviour: pasal.id depends on official publication processing time, and brand-new regulations typically take days-to-weeks to appear. **The desired outcome — flagging the gap rather than confabulating — was achieved.**

For latency-critical use cases (e.g., reacting to a regulation within hours of its issuance), legawa would benefit from a secondary ingestion path: direct PDF upload of the as-published regulation, bypassing the corpus. The existing `legawa analyze` command on a PDF approximates this.

#### e) Sentiment classification volatility

The triage classifier returned `negatif` on the first run and `marah` on the second for the identical input. Both are defensible. With temperature 0.1 this is expected; if reproducibility matters, set temperature to 0.0 and pin the seed.

#### f) Cache session counters reset per invocation

`session_hits`/`session_misses` in `legawa cache stats` reflect only the current CLI process, since each invocation constructs a fresh `CachingPasalClient`. On-disk persistence works correctly. If cumulative analytics are desired, a separate metrics table would be appropriate — out of scope for v1.

---

## 7. Recommendations

### 7.1 Production readiness for staff use

The system is **fit for use as a staff-augmentation tool** with the following constraints:
- Every output must be reviewed by a legal staffer before public dissemination
- Placeholders (`[NAMA ANGGOTA]`, `[FRAKSI]`, `[DATA BPS DAPIL]`) must be filled
- Citations should be spot-checked against pasal.id for high-stakes correspondence

### 7.2 Quick wins

- **Add `legawa analyze` test against a real recent RUU PDF** to validate the tool-calling loop in `agents/base.py`.
- **Persist triage results** to `output/triase/<date>/<id>.json` to enable downstream analytics on incoming aspirasi by category and dapil.
- **Wire `legawa draft memo_kebijakan`** as the natural next step in the constituent-issue chain (surat → research → memo).

### 7.3 Longer-term

- **Pemantau Berita** (5th agent, already on the roadmap) would close the loop demonstrated here: the trending hashtag → constituent letter chain currently relies on a human spotting the news. An automated monitor that runs daily on Indonesian news sources, classifies issues by Komisi, and surfaces high-relevance items would prevent missed early signals.
- **Local secondary corpus**: ingest official PDFs from `peraturan.go.id` directly into a Qdrant index for sub-second retrieval and offline operation. Pasal.id remains the canonical citation source.
- **Audit log**: every tool call (pasal.id query, LLM completion, drafted output) should be appended to a session log file for post-hoc verification and for compliance with internal review processes.

---

## 8. Appendix

### 8.1 Constituent letter fixture (excerpt)

> Selama 8 tahun saya bekerja sebagai operator jahit melalui perusahaan penyalur tenaga kerja. Setiap 1–2 tahun kontrak saya diperpanjang dengan perusahaan penyalur yang berbeda, padahal saya bekerja di pabrik yang sama, dengan mesin yang sama, dan atasan yang sama. Praktik ini membuat saya tidak pernah memperoleh status pekerja tetap...

Full text: `tests/fixtures/surat-buruh-outsourcing.txt`

### 8.2 Drafted reply (excerpt)

> Sehubungan dengan permintaan Ibu, berikut adalah tindak lanjut konkret yang akan kami lakukan:
> 1. **Fungsi Pengawasan:** Saya akan mengagendakan Rapat Dengar Pendapat (RDP) tertutup dengan Kementerian Ketenagakerjaan...
> 2. **Koordinasi dengan Serikat Buruh:** Kami terbuka untuk menerima kunjungan delegasi perwakilan serikat buruh, termasuk dari SBSI Bekasi...
> 3. **Inisiatif Legislasi:** Kami akan terus mendorong pembahasan revisi atau peninjauan ulang pasal-pasal dalam UU Ketenagakerjaan...

Full output: `output/balasan-buruh.md`

### 8.3 Research memo — primary instruments cited

| Instrument                                                                 | FRBR URI                  | Status   |
| -------------------------------------------------------------------------- | ------------------------- | -------- |
| UU 6/2023 (Penetapan UU Cipta Kerja)                                       | `/akn/id/act/uu/2023/6`   | Berlaku  |
| PP 35/2021 (PKWT, Alih Daya, Waktu Kerja, PHK)                             | `/akn/id/act/pp/2021/35`  | Berlaku  |
| UU 11/2020 (Cipta Kerja, dasar materiil)                                   | `/akn/id/act/uu/2020/11`  | Berlaku  |

Full memo: `output/riset-outsourcing.md`

### 8.4 Commits in scope of this run

- `3612cad` — Initial commit: legawa multi-agent system for Indonesian legislators
- `2b30856` — Add roadmap entry for Pemantau Berita (5th agent)
- `3265a18` — Fix three Windows/Qwen3 issues uncovered by first live run

### 8.5 Reproducing this test

```bash
git clone https://github.com/pebaryan/Legawa
cd Legawa
cp .env.example .env  # add PASAL_API_TOKEN, configure LLM URLs
pip install -e .
legawa health
legawa surat tests/fixtures/surat-buruh-outsourcing.txt -o output/balasan.md
legawa research "regulasi outsourcing pasca UU Cipta Kerja dan dampak Permenaker terbaru" -o output/riset.md
legawa cache stats
```

---

*End of report.*

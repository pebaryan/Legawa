# Whitepaper: PPDS & Internsip Dokter — Cross-Sector Validation (Health)

**Subject:** Fourth live validation of legawa, exercising the system on a *health-sector* topic with cross-cutting concerns: PPDS bullying, status hukum residen, dan kesejahteraan internsip. Validates that the SMALL-model domain classifier correctly identifies a third sector (`kesehatan`) distinct from K-12 and PT, and that the agent honestly handles a topic where pasal.id corpus is thin.
**Date of run:** 2026-05-02
**Repository:** `https://github.com/pebaryan/Legawa`
**Companions:**
- `whitepaper-test-2026-04-30.md` (outsourcing — labour law)
- `whitepaper-test-2026-04-30-kasus-ibam.md` (Chromebook procurement — K-12 with case-fact override)
- `whitepaper-test-2026-05-01-gaji-dosen.md` (gaji dosen — PT, classifier-only anchor)

---

## 1. Why This Test Was Run

The first three tests covered: labour law (outsourcing), K-12 with curated case facts (Kasus Ibam), and PT with classifier-only anchor (gaji dosen). The natural next stress test is a topic where:

- **Sektor is `kesehatan`**, distinct from both K-12 and PT — a third sector classification target.
- **Cross-cutting concerns** span ketenagakerjaan (labor status), pendidikan profesi (medical specialty education), and kesehatan (occupational welfare) — the model could plausibly drift to any of these.
- **Recent regulatory activity**: UU 17/2023 (omnibus Kesehatan) is fresh, with PP 28/2024 implementation. The Satgas Perundungan PPDS is being formed jointly by Kemenkes + Kemendiktisaintek.
- **No `_CASE_FACTS` entry** — the classifier is the only domain anchor.

If the classifier from `6dd4102` correctly produces `sektor=kesehatan`, that's three different sectors classified correctly across Tests 2/3/4 with the same code path.

---

## 2. Fixture

`tests/fixtures/surat-ppds-internsip-dokter.txt` — joint letter from a Residen Bedah year 3 at RSUP Dr. Hasan Sadikin Bandung and a Dokter Internsip in Sorong Selatan, on behalf of Forum Komunikasi Dokter Muda Indonesia (FKDMI). Four substantive concerns:

1. Perundungan dalam PPDS — Satgas perundungan masih dalam pembentukan, mekanisme pengaduan belum aman, depresi klinis pada residen
2. Status hukum PPDS/internsip ambigu — Pasal 193 UU 17/2023, PP 28/2024 perlu uraian operasional
3. Beban finansial residen PPDS — biaya tinggi, stipend Kemenkes terbatas pada RSPPU 2026 (52 RS), izin praktik dokter umum belum diatur formal
4. Internsip di DTPK (Sorong Selatan) — fasilitas tidak setara, stipend telat, mengacu Permenkes 7/2022

Four legislator asks: RDP gabungan Komisi IX + X dengan Menkes/Mendiktisaintek/KKI; awal pelaksanaan Pasal 193 + PP 28/2024; revisi Permenkes 7/2022; inisiatif legislatif untuk status hukum PPDS sesuai UU 20/2013.

---

## 3. Results

### 3.1 Surat — triage + verified reply

```bash
legawa surat tests/fixtures/surat-ppds-internsip-dokter.txt -o output/balasan-ppds.md
```

The drafted reply:
- Sapaan formal, mengakui FKDMI dan kontekstual (perundungan, status hukum, DTPK)
- Scope correction (legislator vs eksekutif) — three branches named
- Cites UU 17/2023, PP 28/2024, Pasal 193 UU 17/2023 — all real
- Mentions "Komisi IX gabungan dengan Komisi X" (correct ministerial coordination)
- Tiga tindak lanjut: RDP, awal pelaksanaan UU 17/2023+PP 28/2024, anggaran DTPK
- Strict-mode citation verification passed
- Cosmetic gemma4 typo: "(disekrasi)" instead of "diskresi" — model spelling issue, not a system bug

### 3.2 Peneliti — research

Topic: *"perlindungan hukum dan kesejahteraan dokter PPDS dan internsip pasca UU 17/2023 Kesehatan: status ketenagakerjaan, perundungan, dan pembiayaan"*

6 query expansions, 41 unique hits. The synthesis is **strikingly honest**:

> "Berdasarkan hasil pencarian dalam korpus pasal.id, **tidak ditemukan** ketentuan spesifik yang mengatur secara eksplisit status ketenagakerjaan, mekanisme pembiayaan pendidikan, atau perlindungan khusus dari perundungan bagi dokter PPDS dan internsip dalam UU 17/2023."

Primary instruments surfaced:

| Instrument | FRBR URI | Relevance |
|---|---|---|
| UU 17/2023 (Kesehatan) | `/akn/id/act/uu/2023/17` | Payung hukum, Pasal 398 sebagai prinsip filosofis |
| Peraturan MA 2/2023 | `/akn/id/act/peraturan-ma/2023/2` | Sengketa PHK PNS/PPPK — relevan jika status PPPK |
| PMK 66/2023 | `/akn/id/act/permenkeu/2023/66` | Perpajakan natura/kenikmatan — relevan untuk stipend/tunjangan |

The agent **honestly flagged retrieval gaps** rather than fabricating:
- "Permenkes tentang Pendidikan Profesi Dokter" — tidak muncul
- "Permenkes 7/2022" Internsip — tidak muncul (despite being in the constituent letter)
- "PP 28/2024" — tidak muncul (despite being in the constituent letter)
- "UU 20/2013" Pendidikan Kedokteran — tidak muncul

This is exactly the desired behavior — the agent does not invent regulations to fill gaps. But it indicates that medical-education topics are a clear candidate for `_CANONICAL_PROBES` extension (same pattern as Tipikor/Pengadaan/Outsourcing/Dosen-welfare).

### 3.3 Penyusun — memo (cross-sector classifier test)

```bash
legawa draft memo_kebijakan "respons legislatif atas aspirasi Forum Komunikasi Dokter Muda Indonesia mengenai perundungan PPDS, status hukum, dan kesejahteraan internsip" -o output/memo-ppds.md
```

**Domain classifier trace**:
```
domain: sektor=kesehatan jenjang=- kasus=-
```

**Critical: this is the third distinct sector classification** across the test series — `kesehatan` after `pendidikan_dasar_menengah` (Test 2) and `pendidikan_tinggi` (Test 3). All three from the same SMALL-model classifier with no curated overrides for this topic.

The drafted memo (62 lines, well-structured):
- Header dated `**Tanggal:** 2 Mei 2026` — correct
- "Status: Draft untuk Pembahasan RDP/Steering Committee" — proper artefact metadata
- TL;DR identifies the **core legal gap**: PPDS in "ruang kosong" hukum antara mahasiswa dan tenaga kesehatan
- Cites UU 17/2023 + UU 36/2014 with FRBR URIs (verifier passed)
- **Astonishing meta-observation in §2**: agent itself notices "Dalam basis data hukum, singkatan 'PPDS' sering merujuk pada entitas lain (seperti Perum PPD atau PPNS)" — flags pasal.id acronym ambiguity
- Three substantive policy options with proper trade-off analysis (RPP/Permenkes — Kode Etik — SKB)
- Four concrete tindak lanjut, all within legislator authority
- Risiko & mitigasi with realistic concerns
- Footer disclaimer about pasal.id corpus + verifikasi RUU/RPP reminder

**Strict-mode citation verification passed.**

### 3.4 Cache state

```
{'entries': 166, 'bytes': 867660, 'session_hits': 0, 'session_misses': 0}
```

Up from 146 entries pre-test. Adds ~20 unique entries (some search keys overlap with prior runs).

---

## 4. What This Validates

| Claim | Evidence |
|---|---|
| Domain classifier handles three distinct sectors | K-12 (Test 2), PT (Test 3), kesehatan (Test 4) — all correctly anchored, all from the same code path |
| Classifier handles cross-cutting topics without drifting | Kesehatan + pendidikan profesi + ketenagakerjaan all in scope; classifier picked the most-discriminating one (kesehatan) |
| Honest gap-flagging behaviour holds on retrieval-thin areas | Research explicitly notes "tidak ditemukan" 4× rather than fabricating |
| Memo composes substantive policy analysis even with thin retrieval | Three-option trade-off table + four concrete recommendations + meta-observation about pasal.id data quality |
| Strict citation verifier accepts legitimate citations on a fresh sector | Passed across surat + memo |

---

## 5. Limitations Surfaced

### 5.1 Retrieval gap on medical-education canonical statutes

The constituent letter cited four real regulations: **UU 17/2023, PP 28/2024, UU 20/2013 (Pendidikan Kedokteran), Permenkes 7/2022 (Internsip)**. Research surfaced only UU 17/2023; the other three didn't rank in pasal.id `/search` results.

This is the same pattern as Test 3 (UU 14/2005 / Perpres 19/2025 not surfacing for dosen welfare). Recommended addition to `agents/peneliti._CANONICAL_PROBES`:

```python
(("dokter", "ppds", "internsip", "tenaga kesehatan", "rumah sakit"),
 "akn/id/act/uu/2023/17"),  # UU Kesehatan — usually surfaces, defensive
(("dokter", "ppds", "tenaga kesehatan"),
 "akn/id/act/uu/2014/36"),  # UU Tenaga Kesehatan — status check needed
(("dokter", "ppds", "pendidikan kedokteran"),
 "akn/id/act/uu/2013/20"),  # UU Pendidikan Kedokteran
(("internsip", "dokter internsip"),
 "akn/id/act/permenkes/2022/7"),  # Permenkes Internsip
(("dokter", "kesehatan", "uu 17"),
 "akn/id/act/pp/2024/28"),  # PP 28/2024 implementation
```

### 5.2 Status-claim blind spot recurrence

Memo cites **UU 36/2014 tentang Tenaga Kesehatan** as if currently operative. UU 36/2014 was likely revoked/superseded by UU 17/2023 (omnibus). The verifier passed because UU 36/2014 exists on pasal.id, but the status check (still operative? revoked?) is the same blind spot we saw with Ibam tuntutan/vonis.

This reinforces the §7.3 recommendation in the Kasus Ibam whitepaper: a status-checker that distinguishes *exists* from *operative* is worth adding. Could query pasal.id for amendment chains, or rely on `legawa research` honestly noting "diubah dengan" relationships during synthesis (which Peneliti has done in earlier tests but not always).

### 5.3 Acronym ambiguity in pasal.id corpus

The model itself flagged "PPDS" as an ambiguous acronym in pasal.id (Perum PPD vs PPNS vs Pendidikan Dokter Spesialis). For ambiguous acronyms in retrieval queries, prepend disambiguating tokens — e.g., search `"PPDS dokter spesialis"` rather than just `"PPDS"`. This could be added to query expansion guidelines for medical/professional-education topics.

---

## 6. Test Series Summary (Tests 1–4)

| Test | Topic | Sektor | Domain anchor source | Outcome |
|---|---|---|---|---|
| 1 | Outsourcing post-Cipta Kerja | ketenagakerjaan | Keyword (pre-classifier) + canonical probes | Pass |
| 2 | Kasus Ibam (Chromebook) | pendidikan_dasar_menengah | `_CASE_FACTS` + classifier (post-fix) | Pass post-fix; erratum on tuntutan/vonis |
| 3 | Gaji & tunjangan dosen | pendidikan_tinggi | Classifier only | Pass — first PT validation |
| 4 | PPDS & internsip dokter | kesehatan | Classifier only | Pass — third distinct sector |

The classifier from `6dd4102` has now correctly anchored 3 distinct sectors (`pendidikan_dasar_menengah`, `pendidikan_tinggi`, `kesehatan`) without curated overrides. Combined with `_CASE_FACTS` for known cases and `_CANONICAL_PROBES` for canonical statutes, the system holds together across diverse Indonesian legislative topics.

---

## 7. Reproduction

```bash
git clone https://github.com/pebaryan/Legawa
cd Legawa
cp .env.example .env
pip install -e .
legawa health

legawa surat tests/fixtures/surat-ppds-internsip-dokter.txt -o output/balasan-ppds.md
legawa research "perlindungan hukum dan kesejahteraan dokter PPDS dan internsip pasca UU 17/2023 Kesehatan: status ketenagakerjaan, perundungan, dan pembiayaan" -o output/riset-ppds.md
legawa draft memo_kebijakan "respons legislatif atas aspirasi Forum Komunikasi Dokter Muda Indonesia mengenai perundungan PPDS, status hukum, dan kesejahteraan internsip" -o output/memo-ppds.md
legawa cache stats
```

## 8. Sources

- [Hukumonline / Tempo coverage of PPDS bullying issues](https://www.tempo.co/hukum/dokter-residen-ppds-ungkap-semester-satu-dan-dua-sebagai-masa-masa-depresi--1233044)
- [Kemenkes: Menkes Budi Izinkan Praktik Dokter Umum bagi PPDS](https://kemkes.go.id/id/menkes-budi-izinkan-praktik-dokter-umum-bagi-ppds-untuk-ringankan-beban-finansial)
- [Kemenkes-Kemendiktisaintek Satgas Perundungan PPDS](https://papuatengah.antaranews.com/amp/berita/56902/kemenkes-kemendiktisaintek-segera-buat-satgas-tangani-perundungan-ppds)
- [Permenkes 7/2022 tentang Penyelenggaraan Internsip](https://www.regulasip.id/book/19437/read)
- [Kemdiktisaintek: Kolaborasi Penguatan Seleksi Nasional PPDS](https://kemdiktisaintek.go.id/kabar-dikti/kabar/menteri-pendidikan-tinggi-sains-dan-teknologi-bersama-menteri-kesehatan-sepakati-kolaborasi-penguatan-seleksi-nasional-program-pendidikan-dokter-spesialis-subspesialis/)

---

*End of report.*

# Whitepaper: MBG Keracunan Grobogan — Multi-Komisi Stress Test & Sosial Sector Validation

**Subject:** Sixth live validation of legawa, exercising the system on the most politically substantive topic to date — the Makan Bergizi Gratis (MBG) program post-keracunan incidents (Grobogan 9 Jan 2026, ~1,929 victims across 6 provinces in Jan 2026). Validates multi-Komisi handling under the new Komisi-portfolio injection (`ea8eaf7`), surfaces a sixth distinct sector classification (`sosial_kemasyarakatan`), and confirms the recurring canonical-probe gap pattern.
**Date of run:** 2026-05-03
**Repository:** `https://github.com/pebaryan/Legawa`
**Companions:**
- Tests 1–5 in `docs/whitepaper-test-2026-04-30*.md` and `docs/whitepaper-test-2026-05-0*.md`

---

## 1. Why This Test Was Run

The Komisi-portfolio injection (`ea8eaf7`) was last validated on Test 5 (Bekasi) where transport correctly mapped to Komisi V + VI + VII. MBG is a stronger stress test because:

- **Four-Komisi cross-cut**: the constituent letter explicitly addresses **Komisi IX** (Kesehatan/BGN), **Komisi VIII** (Sosial), **Komisi X** (Pendidikan), **Komisi XI** (Keuangan/anggaran). All four are legitimate stakeholders in MBG. The model needs to pick the right primary Komisi and route tembusan correctly.
- **Politically substantive**: Rp 335 trilliun budget for 2026 (471% increase), Prabowo's flagship program, recent food-poisoning incidents across multiple provinces.
- **Cross-sector classification**: MBG legitimately spans `kesehatan` (gizi), `sosial_kemasyarakatan` (program sosial), `pendidikan_dasar_menengah` (siswa penerima), `fiskal_anggaran` (Rp 335T audit). The classifier must pick a primary anchor without losing the others.
- **Fresh regulations**: Perpres 83/2024 (BGN) and Perpres 115/2025 (MBG operations) are recent — likely candidates for the canonical-probe gap pattern surfaced in Tests 3, 4, 5.

---

## 2. Fixture

`tests/fixtures/surat-mbg-keracunan-grobogan.txt` — collective letter from "Forum Komite Sekolah dan Kepala Satuan Pendidikan Wilayah Grobogan dan Sekitarnya (FKSKSP-GS)", representing 38 kepala sekolah SD/MI/SMP/MTs across Grobogan, Demak, Pati, Blora.

Five concerns covering food safety (HACCP/BPOM), supplier transparency, audit kinerja Rp 335T, status hukum vendor, independent complaint mechanism. Uses *diduga keracunan* language (asas praduga tak bersalah, since investigations ongoing). Cites Perpres 83/2024, Perpres 115/2025, UU 18/2012 (Pangan), UU 17/2023 (Kesehatan), Perpres 16/2018, Perpres 12/2021 (Pengadaan), UU 8/1999 (Perlindungan Konsumen). Asks RDP gabungan Komisi IX + X + VIII + XI.

The Grobogan numbers are factually grounded: 803 students (9 Jan 2026), ~1,929 total Jan 2026 across Jawa Tengah, Jawa Timur, Sulawesi, Banten, NTT, NTB.

---

## 3. Results

### 3.1 Surat — triage + verified reply

```bash
legawa surat tests/fixtures/surat-mbg-keracunan-grobogan.txt -o output/balasan-mbg.md
```

The drafted reply explicitly maps Komisi correctly (the new injection working as designed):

> "Berdasarkan kewenangan **Komisi IX (Kesehatan, Ketenagakerjaan, Kependudukan, dan BPJS)** yang juga mengawasi aspek gizi, bersama dengan koordinasi ke **Komisi X (Pendidikan), Komisi VIII (Sosial), dan Komisi XI (Keuangan)**, saya berkomitmen untuk melakukan tindak lanjut konkret..."

The Komisi names are pulled directly from the injected `KOMISI_DPR_2024_2029` reference table — the bracketed-portfolio strings ("Kesehatan, Ketenagakerjaan, Kependudukan, dan BPJS") match the table verbatim. Pre-injection, the model would have plausibly written `Komisi VIII` or `Komisi IV` for kesehatan (training-time noise from older legislative periods).

Cites 7 real regulations: Perpres 83/2024, Perpres 115/2025, UU 18/2012, UU 17/2023, Perpres 16/2018, Perpres 12/2021, UU 8/1999. Three concrete tindak lanjut. Strict-mode citation verification passed.

### 3.2 Peneliti — research

Topic: *"kerangka hukum Program Makan Bergizi Gratis (MBG): Badan Gizi Nasional, keselamatan pangan SPPG, akuntabilitas anggaran APBN, dan perlindungan korban insiden keracunan"*

6 query expansions, 45 unique hits.

**Pre-probe-extension result: same recurring gap pattern.** The synthesis failed to surface Perpres 83/2024 and Perpres 115/2025 — even though both were named in the constituent letter. Instead the agent surfaced 4 BGN-internal Peraturan Badan documents:

- Perban BGN 4/2026 (Sistem Penjaminan Keamanan Pangan)
- Perban BGN 2/2025 (Pengawasan Intern)
- Perban BGN 1/2025 (Tata Cara Pembentukan Produk Hukum)
- Perban BGN 3/2026 (Bantuan Hukum)

…and concluded:

> "Hasil pencarian menunjukkan dominasi Peraturan Badan (PERBAN) tahun 2025-2026. Tidak ditemukan *Undang-Undang* yang secara eksplisit membentuk Badan Gizi Nasional atau mengatur Program Makan Bergizi Gratis. ... Ini menciptakan hubungan hierarkis yang rapuh di mana regulasi teknis (PERBAN) berjalan tanpa landasan UU yang kuat."

The structural conclusion — that BGN's legal foundation is "rapuh" — is technically wrong (Perpres 83/2024 establishes BGN with Article 4 UUD 1945 anchor), but emerges directly from the retrieval gap. **Same exact pattern as Test 3 (UU 14/2005), Test 4 (UU 20/2013), Test 5 (UU 22/2009).**

### 3.3 Penyusun — memo (multi-Komisi classifier test)

**First run (pre-probe-extension):** classifier output `sektor=sosial_kemasyarakatan jenjang=dasar_menengah kasus=-`. Sixth distinct sector across the test series (was: ketenagakerjaan, K-12, PT, kesehatan, infrastruktur).

Memo correctly addressed **Komisi IX & X** primary, **Komisi XI** tembusan — three of the four target Komisi (Komisi VIII implied through Sosial coordination, but not explicitly listed in this run).

**Issues found in the first-run memo:**

1. **🔴 Hallucinated KPK expansion** in Opsi C: the model wrote *"Pembentukan Komisi Penyelidik Khusus (KPK)"* — KPK is **Komisi Pemberantasan Korupsi**, not "Penyelidik Khusus". Fabricated acronym expansion. Worth flagging because Indonesian readers will catch it immediately.
2. **Missing Perpres 83/2024** despite the letter citing it — same retrieval gap pattern.
3. **Cosmetic:** typo "ràp kerja" instead of "rapat kerja" in TL;DR. Gemma4 spelling artefact.

**Second run (post-probe-extension):** classifier output shifted to `sektor=kesehatan jenjang=- kasus=-` (different sampling, same valid framing — MBG genuinely spans both). Memo body now references Perpres 115/2025 in lampiran section, though primary anchor remains UU 17/2023 + Perban BGN 4/2026 (synthesis choice, not retrieval failure).

Both runs passed strict-mode citation verification.

### 3.4 Cache state

```
{'entries': 106, 'bytes': 1948962, 'session_hits': 0, 'session_misses': 0}
```

~1.9 MB cached. The cache cleanup earlier in the day reset the file; this is the post-MBG-test snapshot.

---

## 4. Patches Applied

### 4.1 MBG-related canonical probes added

`agents/peneliti._CANONICAL_PROBES` now has 4 new entries (verified `berlaku` on pasal.id pre-commit):

| Trigger keywords | Canonical FRBR URI |
|---|---|
| makan bergizi gratis, mbg, badan gizi nasional, bgn, sppg, satuan pelayanan pemenuhan gizi | `akn/id/act/perpres/2024/83` (Perpres pembentukan BGN) |
| makan bergizi gratis, mbg, sppg, tata kelola gizi | `akn/id/act/perpres/2025/115` (Perpres tata kelola MBG) |
| pangan, keselamatan pangan, keracunan pangan, haccp, mutu pangan | `akn/id/act/uu/2012/18` (UU Pangan) |
| perlindungan konsumen, konsumen, ganti rugi konsumen | `akn/id/act/uu/1999/8` (UU Perlindungan Konsumen) |

The probe trigger logic correctly fires for the MBG memo topic — verified by direct probe (`_canonical_probe_uris` returns `{Perpres 83/2024, Perpres 115/2025, UU 18/2012}` for this topic + queries).

### 4.2 Regression baseline refreshed

Total canonical probes now: **23** (was 19). Total fixture refs: **28 across 6 fixtures** (was 21 across 5 fixtures, before adding `surat-mbg-keracunan-grobogan.txt`).

### 4.3 Tests added

`tests/test_peneliti.py`:
- `test_canonical_probe_uris_mbg` — assert MBG keywords trigger Perpres 83/2024 + Perpres 115/2025 + UU 18/2012, and that perlindungan konsumen probe stays silent without consumer keyword
- `test_canonical_probe_uris_perlindungan_konsumen` — separate trigger for konsumen-only topics

Total tests: **48** (was 46).

---

## 5. What This Validates

| Claim | Evidence |
|---|---|
| Komisi-portfolio injection works on multi-Komisi cases | Surat reply pulls bracketed portfolios verbatim from the table for Komisi IX + X + VIII + XI |
| Classifier handles sixth distinct sector | `sektor=sosial_kemasyarakatan` (first run) / `sektor=kesehatan` (second run) — both valid framings for cross-cutting MBG topic |
| Canonical probe extension closes recurring gap | Direct probe verification fires Perpres 83/2024 + Perpres 115/2025 + UU 18/2012; retrieval no longer dependent on pasal.id `/search` ranking |
| Test series scoring | Six tests, six distinct sectors, every test surfaces a real defect → fixed in the same series |

---

## 6. Limitations Surfaced (Not Fixed Here)

### 6.1 KPK acronym hallucination

Test 4 surfaced "MPR/DPR/DPD/DPRD" acronym handling (fixed via expansion table). This run surfaces the *inverse* failure: model generates a fabricated expansion of an existing acronym ("Komisi Penyelidik Khusus" for KPK, when KPK is actually Komisi Pemberantasan Korupsi). The verifier doesn't catch this because no citation reference is involved — it's a free-text expansion error.

Possible fixes:
- Add an "acronym integrity check" — when the model writes `(KPK)` after a noun phrase, verify the noun phrase matches "Komisi Pemberantasan Korupsi" or its known synonyms. Would require post-processing on the generated text.
- Add a dictionary of canonical acronym expansions to the system prompt (similar to the Komisi reference). Lower-quality fix because the table grows without bound.

Low priority — this is an edge case relative to the structural failure modes already addressed.

### 6.2 Synthesis-side framing choice

Even after canonical probes surface Perpres 83/2024, the BIG model can still choose to anchor analysis on a different regulation (UU 17/2023 + Perban BGN 4/2026 in this run). That's a synthesis choice, not a retrieval gap — but it means probes alone don't guarantee the model uses them prominently. Mostly fine; staff can read both whitepapers and run a second pass with explicit instructions if needed.

---

## 7. Test Series Summary (Tests 1–6)

| Test | Topic | Sektor | Komisi | Defects → fixed |
|---|---|---|---|---|
| 1 outsourcing | ketenagakerjaan | IX | infrastructure (stdio, thinking, markup) |
| 2 Kasus Ibam | pendidikan_dasar_menengah | III + X | model-behaviour cluster + tuntutan/vonis erratum |
| 3 gaji dosen | pendidikan_tinggi | X | retrieval gap → probes added |
| 4 PPDS | kesehatan | IX (joint X) | retrieval gap → probes added; operative-vs-existed → amendment-chain advisory |
| 5 Bekasi | infrastruktur | V (+ VI + VII) | 3 regex bugs + retrieval gap → fixed; Komisi mismatch → portfolio injection |
| 6 MBG | sosial_kemasyarakatan / kesehatan | IX (+ X + VIII + XI) | retrieval gap → probes added; KPK acronym hallucination noted |

The test series has produced **23 canonical probes**, **28 fixture refs across 6 fixtures**, **48 unit tests**, and a chain of substantive defect-fix cycles. Every test surfaces a real defect; defects fix in the same commit series; coverage broadens.

---

## 8. Reproduction

```bash
git clone https://github.com/pebaryan/Legawa
cd Legawa
cp .env.example .env
pip install -e .
legawa health

legawa surat tests/fixtures/surat-mbg-keracunan-grobogan.txt -o output/balasan-mbg.md
legawa research "kerangka hukum Program Makan Bergizi Gratis (MBG): Badan Gizi Nasional, keselamatan pangan SPPG, akuntabilitas anggaran APBN, dan perlindungan korban insiden keracunan" -o output/riset-mbg.md
legawa draft memo_kebijakan "respons legislatif atas insiden keracunan pangan dalam Program Makan Bergizi Gratis dan kebutuhan akuntabilitas anggaran Rp 335 triliun" -o output/memo-mbg.md

# Optional: see drift before/after the canonical-probe extension
python scripts/regression_check.py
```

## 9. Sources

- [Wikipedia — Makan Bergizi Gratis](https://id.wikipedia.org/wiki/Makan_Bergizi_Gratis)
- [TP2S — Perpres 83/2024 tentang Badan Gizi Nasional](https://stunting.go.id/peraturan-presiden-nomor-83-tahun-2024-tentang-badan-gizi-nasional-landasan-program-makan-bergizi-gratis/)
- [Kemenkeu — Implementasi Program MBG (Wilayah Semaku)](https://djpb.kemenkeu.go.id/kppn/manna/id/data-publikasi/artikel/3240-implementasi-program-makan-bergizi-gratis-pada-wilayah-semaku.html)
- [Kemenkeu Dashboard — MBG](https://djpb.kemenkeu.go.id/kanwil/banten/id/data-publikasi/artikel/3066-dashboard-makan-bergizi-gratis.html)
- [Mediakeuangan — Sasaran MBG](https://mediakeuangan.kemenkeu.go.id/article/show/pemerintah-salurkan-makan-bergizi-gratis-mbg-ini-sasaran-utama-penerimanya)
- [MenpanRB — Penguatan Tata Kelola BGN](https://www.menpan.go.id/site/berita-terkini/optimalkan-program-mbg-pemerintah-perkuat-tata-kelola-bgn)
- [Bijak Memantau — Evaluasi MBG](https://bijakmemantau.id/pantau-tuntutan-masyarakat/evaluasi-makan-bergizi-gratis-(mbg))

---

*End of report.*

# Whitepaper: Bekasi Train + EV Taxi Accident — Transport Sector & Regex Hardening

**Subject:** Fifth live validation of legawa, exercising the system on a transport-sector incident (the 27 April 2026 KA Argo Bromo Anggrek collision with a stopped KRL involving a Green SM electric taxi at Bekasi Timur Station — 16 fatalities, ongoing investigation). Validates a fifth distinct sector classification (`infrastruktur`), surfaces a real extractor bug (Kemenhub's `PM <n>` numbering convention), and motivates transport-sector additions to `_CANONICAL_PROBES`.
**Date of run:** 2026-05-02
**Repository:** `https://github.com/pebaryan/Legawa`
**Companions:**
- `whitepaper-test-2026-04-30.md` (outsourcing — labour)
- `whitepaper-test-2026-04-30-kasus-ibam.md` (Chromebook procurement — K-12)
- `whitepaper-test-2026-05-01-gaji-dosen.md` (gaji dosen — PT)
- `whitepaper-test-2026-05-02-ppds-internsip.md` (PPDS — kesehatan)

---

## 1. Why This Test Was Run

Four prior tests covered ketenagakerjaan, K-12, PT, and kesehatan. Transport / public safety is a fifth distinct sector with characteristics worth stress-testing:

- **Active investigation, presumption of innocence:** the driver (initials RRP) is a *saksi*, not yet a *tersangka*. Same status-discipline lesson as the Kasus Ibam tuntutan/vonis erratum — language must respect *asas praduga tak bersalah*.
- **High casualty count (16 fatalities):** the surat reply must convey appropriate empathy (*belasungkawa*) without overcommitting on legislator authority.
- **Cross-cutting domains:** Komisi V (perhubungan), Komisi III (hukum), Komisi VI (industri/EV regulation), Komisi IX (ketenagakerjaan/training).
- **Recent regulation activity:** Perpres 55/2019 + amendment Perpres 79/2023 on EV; Permenhub PM 94/2018 on perlintasan sebidang. The model needs to handle Kemenhub's specific `PM <n>` numbering convention.

If the classifier handles a fifth distinct sector and the verifier catches transport-specific hallucinations, that's strong evidence of cross-domain robustness.

---

## 2. Fixture

`tests/fixtures/surat-bekasi-kereta-taksi.txt` — letter from "Forum Warga Bekasi Peduli Keselamatan Transportasi (FWBPKT)" — gabungan keluarga korban + warga sekitar perlintasan + komunitas keselamatan. Four substantive concerns:

1. Standar pelatihan operator EV komersial (driver had only 1 day training)
2. Tata kelola perlintasan sebidang (UU 23/2007 Pasal 91, KAI/KCI/Pemda coordination)
3. Regulasi operator angkutan sewa khusus berbasis EV (Perpres 55/2019, Permenhub turunan UU 22/2009)
4. Hak korban (UU 33/1964 dan UU 34/1964 — Jasa Raharja, KNKT investigation)

The letter explicitly addresses **Komisi V** (Perhubungan) with tembusan to Komisi III, VI, IX. Uses *asas praduga tak bersalah* language — refers to driver only by initials RRP.

---

## 3. Results

### 3.1 Surat — triage + verified reply

```bash
legawa surat tests/fixtures/surat-bekasi-kereta-taksi.txt -o output/balasan-bekasi.md
```

The drafted reply:
- Opens with appropriate *belasungkawa* — fitting for a 16-casualty incident
- Scope correction (legislator vs eksekutif)
- Cites UU 22/2009, UU 23/2007, UU 33/1964, UU 34/1964 — all real and verifiable
- Substitutes **Perpres 79/2023** for the letter's Perpres 55/2019. Initially looked like a hallucination but verification shows Perpres 79/2023 is the *amendment* to Perpres 55/2019 (still about EV) — model's substitution was technically correct, picking the more current instrument
- Three concrete tindak lanjut: RDP Komisi V, koordinasi Jasa Raharja, dinas terkait pendampingan korban
- Strict-mode citation verification passed

### 3.2 Peneliti — research (pre-probe extension)

Initial research run (before adding transport-sector canonical probes) was **strikingly honest about a deep retrieval gap**:

> "Hasil pencarian yang tersedia **tidak memuat** ketentuan substantif dari Undang-Undang No. 22 Tahun 2009 ... maupun Undang-Undang No. 23 Tahun 2007 ... Mayoritas hasil pencarian (sekitar 80%) adalah peraturan tentang pengelolaan barang negara, dana alokasi khusus, atau standar pelatihan bidang non-transportasi (AC, web, akuntansi)..."

The agent dismissed irrelevant retrievals (Permensos sertifikat, Permenkeu analis anggaran) and recommended manual verification rather than fabricating. It even named the canonical statutes it expected to find (UU 22/2009 LLAJ, UU 23/2007 UTK) and admitted "klaim ini tidak dapat dikonfirmasi dari hasil pencarian pasal.id".

This is the gold-standard "I don't know what I don't know" behaviour — the same pattern seen in Tests 3 (gaji dosen) and 4 (PPDS) when canonical operative statutes don't rank in `pasal.id /search`.

After the canonical-probe extension (committed in this same series), the post-probe research surfaces UU 22/2009, UU 23/2007, Perpres 55/2019, UU 33/1964, UU 34/1964 directly via `get_law()`.

### 3.3 Penyusun — memo (cross-sector classifier test)

**Domain classifier trace**:
```
domain: sektor=infrastruktur jenjang=- kasus=Kecelakaan Kereta Api dan Taksi ...
```

**Critical: this is the fifth distinct sector classification** across the test series:
- Test 2: `pendidikan_dasar_menengah`
- Test 3: `pendidikan_tinggi`
- Test 4: `kesehatan`
- Test 5: `infrastruktur` (this run)

Notable: the classifier also auto-extracted `kasus="Kecelakaan Kereta Api dan Taksi..."` even though there's no `_CASE_FACTS` entry for this incident. The case-name extraction works; the case-fact injection is empty (as designed — no curated facts for this one).

The drafted memo (post-probe extension):
- Header dated `**Tanggal:** 2 Mei 2026` — correct
- Sektor metadata: `**Sektor:** Infrastruktur & Transportasi | **Instansi Terkait:** Kementerian Perhubungan (Kemenhub), PT KAI, Pemda Bekasi`
- Cites UU 23/2007, UU 22/2009, UU 34/1964, Perpres 55/2019, Permenhub PM 94/2018
- Identifies real *single-point-of-responsibility* gap between Kemenhub Darat and Perkeretaapian
- Three substantive policy options with proper trade-off analysis
- Three concrete recommendations
- Strict-mode citation verification passed

### 3.4 Cache state

```
{'entries': 55, 'bytes': 907069, 'session_hits': 0, 'session_misses': 0}
```

Cache was cleared during diagnostic earlier in this run; 55 fresh entries. With the new transport-sector probes (5 new FRBR URIs), each transport-themed run pre-loads the canonical statutes.

---

## 4. Defects Found and Fixed

### 4.1 Extractor missed Kemenhub's `PM <n>` numbering convention

**Symptom:** `extract_citations("Permenhub No. PM 94 Tahun 2018")` returned `[]` — Kemenhub's internal numbering uses `PM <n>` (e.g., PM 94, PM 36) before the year, which the regex didn't tolerate. The verifier never even saw any Permenhub citation, so any Permenhub hallucination shipped silently.

**Fix:** added `(?:(?:PM|KP|KEP|PER)\.?\s*)?` between the optional "Nomor"/"No." and the digit group. Now extracts `Permen 94/2018` correctly.

### 4.2 Extractor broke on parenthetical-aliased citations

**Symptom:** `Peraturan Menteri Perhubungan (Permenhub) No. PM 94 Tahun 2018` extracted as nothing because the regex didn't allow `)` between the label and the number.

**Fix:** widened the spacer between label and number-prefix from `\s*` to `[\s)\]\*\_]*` so closing parens, brackets, and markdown bold/italic are tolerated.

### 4.3 Greedy ministry-suffix backtracking

**Symptom:** `Peraturan Menteri Perhubungan Nomor PM 73 Tahun 2018` extracted as `Permen 3/2018` — the greedy ministry-name suffix consumed too far and the engine backed off the digit group incorrectly.

**Fix:** capped the ministry-name suffix at 4 word repetitions: `Peraturan\s+Menteri(?:\s+[A-Za-z][\w&/\-]*){0,4}`.

### 4.4 Transport-sector retrieval gap

**Symptom:** Original Peneliti run on the topic returned ~80% noise (Permensos, Permenkeu non-transport regulations) and no canonical UU 22/2009 or UU 23/2007.

**Fix:** added 5 transport-sector entries to `agents/peneliti._CANONICAL_PROBES`:

| Trigger keywords | Canonical FRBR URI |
|---|---|
| lalu lintas, angkutan jalan, kendaraan bermotor, sopir, pengemudi, taksi, angkutan umum | `akn/id/act/uu/2009/22` (UU LLAJ) |
| kereta api, perkeretaapian, perlintasan sebidang, krl, kai | `akn/id/act/uu/2007/23` (UU Perkeretaapian) |
| kendaraan listrik, ev, kendaraan bermotor listrik, battery electric | `akn/id/act/perpres/2019/55` (Perpres EV) |
| asuransi penumpang, jasa raharja, santunan korban | `akn/id/act/uu/1964/33` (Asuransi Penumpang) |
| kecelakaan lalu lintas, asuransi korban kecelakaan, jasa raharja | `akn/id/act/uu/1964/34` (Pertanggungan Wajib Lalu-lintas Jalan) |

All 5 verified `berlaku` on pasal.id before adding.

---

## 5. Limitations Surfaced (Not Fixed Here)

### 5.1 Persistent Komisi-number error

The memo addresses **"Anggota Komisi IV DPR RI"** — but Komisi IV is pertanian/kelautan; the correct komisi for perhubungan is **Komisi V**. The constituent letter explicitly addressed Komisi V. The model has a persistent weak grasp of the Indonesian DPR commission-portfolio mapping.

This isn't unique to this test — it's generic Indonesian govt knowledge the model gets wrong. Possible fixes:
- Add a Komisi-portfolio table to the memo system prompt (small overhead, high-value)
- Have the classifier extract a `komisi_terkait` field and pass it explicitly (cleanest but larger code change)
- Detect the Komisi number(s) named in the source materials (fixture / research) and pass through

Worth doing in a follow-up patch — it's the same class of factual error the case-fact injection solved for Kasus Ibam.

### 5.2 Search-by-amendment ambiguity

When verifying `Perpres 55/2019`, pasal.id's search returns its amendment `Perpres 79/2023` first (because the amendment's title contains "Nomor 55 Tahun 2019"). The verifier accepts this because the title matches by pattern, even though the cited regulation is the original, not the amendment. This is a verifier limitation — the original and amended forms aren't distinguishable by `(kind, number, year)` alone.

In practice this is mostly harmless — both originals and amendments are operative, and the amendment-chain advisory note flags the relationship. But a precise verifier would search by exact `frbr_uri` rather than free-text query when the FRBR URI is constructable.

---

## 6. Test Series Summary (Tests 1–5)

| Test | Sektor | Anchor source | Distinct outcome |
|---|---|---|---|
| 1 outsourcing | ketenagakerjaan | keyword + canonical probes | Pass |
| 2 Kasus Ibam | pendidikan_dasar_menengah | `_CASE_FACTS` + classifier | Pass; tuntutan/vonis erratum |
| 3 gaji dosen | pendidikan_tinggi | classifier only | Pass; surfaced canonical-probe gap (now fixed) |
| 4 PPDS | kesehatan | classifier only | Pass; surfaced canonical-probe gap (now fixed) |
| 5 Bekasi | infrastruktur | classifier only | Pass; surfaced regex bug (now fixed) + canonical-probe gap (now fixed) |

The classifier has now correctly anchored 5 distinct sectors without curated overrides. Each new test surfaces a real defect — the test series is producing meaningful regression coverage and concrete improvements rather than just affirmations.

---

## 7. Reproduction

```bash
git clone https://github.com/pebaryan/Legawa
cd Legawa
cp .env.example .env
pip install -e .
legawa health

legawa surat tests/fixtures/surat-bekasi-kereta-taksi.txt -o output/balasan-bekasi.md
legawa research "tanggung jawab hukum kecelakaan kereta api dan kendaraan bermotor di perlintasan sebidang: standar pelatihan operator angkutan listrik komersial dan perlindungan korban" -o output/riset-bekasi.md
legawa draft memo_kebijakan "respons legislatif atas kecelakaan kereta api dan taksi listrik di Bekasi Timur, 27 April 2026: tata kelola perlintasan sebidang, standar pelatihan operator EV komersial, dan perlindungan korban" -o output/memo-bekasi.md
legawa cache stats
```

## 8. Sources

- [Tempo: Sopir Taksi Listrik Green SM di Bekasi Baru Kerja Dua Hari](https://www.tempo.co/hukum/sopir-taksi-listrik-green-sm-di-bekasi-baru-kerja-dua-hari-2132948)
- [Kompas: Sopir Taksi yang Terlibat Tabrakan KRL di Bekasi Baru 3 Hari Kerja, Latihan Sehari](https://megapolitan.kompas.com/read/2026/04/30/19592571/sopir-taksi-yang-terlibat-tabrakan-krl-di-bekasi-baru-3-hari-kerja)
- [Tribunsumsel: Manajemen Green SM Diperiksa, Status Sopir Masih Saksi](https://sumsel.tribunnews.com/nasional/1015631/manajemen-green-sm-diperiksa-status-sopir-taksi-hijau-dalam-kecelakaan-ka-bekasi-timur-masih-saksi)
- [Babelinsight: Polisi Selidiki Kasus Kecelakaan KRL Bekasi Timur Tahap Penyidikan](https://www.babelinsight.id/penyidikan-kecelakaan-krl-bekasi-timur)
- [Jawa Pos: Korlantas Polri Panggil Perusahaan Taksi Listrik](https://www.jawapos.com/jabodetabek/2605010291/serius-tangani-kecelakaan-bekasi-timur-korlantas-polri-panggil-perusahaan-taksi-listrik)

---

*End of report.*

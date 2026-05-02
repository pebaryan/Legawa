# Whitepaper: Gaji & Tunjangan Dosen — Domain Classifier Validation on a Novel Sector

**Subject:** Third live validation of legawa, focused on a Perguruan Tinggi (PT) topic — the inverse domain of Test 2 (Kasus Ibam, K-12). Validates that the SMALL-model domain classifier correctly identifies a sector with no `_CASE_FACTS` entry, that PT framing holds without curated overrides, and that legitimate citations propagate cleanly through the verifier.
**Date of run:** 2026-05-01
**Repository:** `https://github.com/pebaryan/Legawa`
**Companions:**
- `whitepaper-test-2026-04-30.md` (outsourcing — labour law, K-12 corpus fit high)
- `whitepaper-test-2026-04-30-kasus-ibam.md` (Chromebook procurement — K-12 with case-fact override)

---

## 1. Why This Test Was Run

The previous two whitepapers tested the system on:
- A regulatory issue with strong pasal.id corpus fit (outsourcing post-Cipta Kerja).
- A K-12 corruption case requiring a hand-curated `_CASE_FACTS` block to break the model's PT prior.

**Both prior tests had explicit code-level scaffolding** for their domains. This third test deliberately picks a sector with:
- **No `_CASE_FACTS` entry.** The model has no curated facts to draw from.
- **Real PT framing.** A genuine Perguruan Tinggi topic — the inverse of Kasus Ibam, where the K-12 anchor was the right answer. Here the *PT* anchor is the right answer.
- **Recent regulation activity.** Permendiktisaintek 52/2025 (effective Jan 2026) is fresh enough that the model has only training-time priors plus what pasal.id retrieves at runtime.

If the SMALL-model domain classifier (committed in `6dd4102`) actually generalises beyond curated cases, this is where it should show.

---

## 2. Fixture

`tests/fixtures/surat-gaji-tunjangan-dosen.txt` — letter from a junior PNS lecturer (Lektor / Asisten Ahli at UNS Surakarta) writing on behalf of Forum Dosen Indonesia Wilayah Jawa Tengah (~280 dosen). Four substantive concerns:

1. ASN-PTS disparity post-Permendiktisaintek 52/2025 + Perpres 19/2025 (Tukin)
2. Status of dosen kontrak / honorer not covered by the new regulation
3. Risk that RUU Sisdiknas relocates UU 14/2005's tunjangan provisions to a broader law, potentially weakening protection
4. Slow Serdos disbursement under PP 37/2009 + PP 41/2009

Four legislator asks: RDP with Mendiktisaintek + Menkeu, ensure RUU Sisdiknas does not weaken UU 14/2005 protections, push BPK audit, consider explicit non-ASN dosen framework.

The letter is intentionally substantive — it cites real regulations by full name, draws a real disparity to a real recent regulation (Permendiktisaintek 52/2025, Perpres 19/2025), and raises a real legislative-process risk (RUU Sisdiknas).

---

## 3. Results

### 3.1 Surat — triage + verified reply

```bash
legawa surat tests/fixtures/surat-gaji-tunjangan-dosen.txt -o output/balasan-dosen.md
```

The drafted reply:
- Sapaan formal, acknowledges Forum Dosen Indonesia organisation
- Scope correction: legislator vs eksekutif, three branches of authority named (legislasi/anggaran/pengawasan)
- Cites correctly: UU 14/2005, PP 41/2009, Perpres 19/2025
- Names "Kemendiktisaintek" specifically — current ministry name, not legacy "Kemendikbudristek"
- Three concrete tindak lanjut (RDP, koordinasi kementerian, perhatian pada non-ASN framework)
- PT framing intact ("Perguruan Tinggi Negeri (PTN)", "Perguruan Tinggi Swasta (PTS)")
- Strict-mode citation verification passed

### 3.2 Peneliti — research

Topic: *"kerangka hukum penghasilan dan tunjangan dosen Indonesia: UU Guru dan Dosen, Permendiktisaintek terbaru, dan posisi tunjangan dalam revisi UU Sisdiknas"*

Six query expansions: `tunjangan dosen`, `penghasilan dosen UU Guru dan Dosen`, `tunjangan profesi dosen`, `kesejahteraan dosen Permendiktisaintek`, `revisi UU Sisdiknas tunjangan`, `hak keuangan dosen`. 45 unique hits after dedupe.

Primary instruments synthesised:

| Instrument | FRBR URI | Notes |
|---|---|---|
| Permendiktisaintek 52/2025 | `/akn/id/act/permendiktisaintek/2025/52` | The new operative regulation, correctly identified |
| Permendikbudristek 44/2024 | `/akn/id/act/permendikbudristek/2024/44` | Predecessor, correctly traced as the regulation 52/2025 evolved from |
| PP 41/2009 | `/akn/id/act/pp/2009/41` | Tunjangan Profesi/Khusus/Kehormatan — full title cited |
| Permenristekdikti 20/2017 | `/akn/id/act/permenristekdikti/2017/20` | Pemberian Tunjangan Profesi & Kehormatan |

The agent also notes Permen 78/2013 + Permen 89/2013 about beban kerja profesor as related regulations.

**Honest gap-flagging** (the desired behaviour):
- "Hasil pencarian tidak menyediakan teks atau ringkasan mengenai bagaimana posisi tunjangan dosen diatur dalam draf revisi UU Sisdiknas" — pasal.id doesn't index in-progress RUUs.
- "Meskipun topik menyebutkan UU Guru dan Dosen, hasil pencarian tidak menampilkan isi spesifik dari UU tersebut terkait penghasilan dosen" — UU 14/2005 didn't rank in the parallel searches.

**Notable absence — UU 14/2005 (Guru dan Dosen) and Perpres 19/2025 (Tukin)** were referenced in the constituent letter but did not surface in research's primary instruments. UU 14/2005 is the *operative* statute on dosen welfare; its absence from primary instruments is a retrieval gap, not a drafting gap. Candidate fix: extend `agents/peneliti._CANONICAL_PROBES` with `("dosen", "guru", "tunjangan profesi", "tukin")` → `[akn/id/act/uu/2005/14, akn/id/act/perpres/2025/19]`.

### 3.3 Penyusun — memo (the critical PT-framing test)

```bash
legawa draft memo_kebijakan "respons legislatif atas aspirasi Forum Dosen Indonesia mengenai gaji, tunjangan, dan posisi tunjangan dosen dalam revisi UU Sisdiknas" -o output/memo-dosen.md
```

**Domain classifier trace**:
```
domain: sektor=pendidikan_tinggi jenjang=tinggi kasus=-
```

**Critical: this is a PT topic with no `_CASE_FACTS` entry.** The classifier is the only domain anchor in play. It correctly identified `pendidikan_tinggi`, `jenjang=tinggi`, no specific case.

The drafted memo (53 lines, well-structured):
- Header dated `**TANGGAL:** 1 Mei 2026` — correct
- TL;DR identifies the legislative-design question crisply: "tunjangan dosen sebagai hak normatif dalam UU vs mekanisme delegasi peraturan turunan"
- PT framing holds **throughout** — no K-12 drift anywhere. References "Perguruan Tinggi", "PTN dan PTS", "kesejahteraan dosen" — sector terms intact.
- Cites PP 41/2009 + Permenristekdikti 20/2017 with proper FRBR URIs in the body
- Proposes a substantive **Hybrid Approach**: anchor "Negara menjamin kesejahteraan dosen" in UU Sisdiknas at principle level, mandate detailed mechanisms via PP (not Permen) for stronger protection without locking nominal amounts. This is genuine legislative-design analysis.
- Acknowledges PTN-PTS disparity in the Risiko & Mitigasi block
- Flags Kemenkeu fiscal trade-off realistically
- Strict-mode citation verification passed

### 3.4 Cache state

```
{'entries': 146, 'bytes': 616122, 'session_hits': 0, 'session_misses': 0}
```

Up from 113 entries pre-test. Adds ~33 unique entries from this run's three commands.

---

## 4. What This Validates

| Claim | Evidence |
|---|---|
| The SMALL-model domain classifier generalises beyond curated cases | `sektor=pendidikan_tinggi` correctly identified for a topic with no `_CASE_FACTS` entry |
| PT framing holds without `_CASE_FACTS` override | Memo body uses "Perguruan Tinggi", "PTN/PTS", "dosen" consistently — zero K-12 drift |
| Citation verifier accepts legitimate verifiable citations on a fresh sector | Strict mode passed across surat + memo with PP 41/2009, Permenristekdikti 20/2017, Permendiktisaintek 52/2025 |
| Honest gap-flagging in retrieval-thin areas | Research explicitly notes "draf RUU Sisdiknas tidak terindeks" rather than fabricating |
| Domain anchor is robust to inverse-direction tests | Test 2 anchored *away from* PT (correctly K-12); Test 3 anchored *into* PT (correctly PT) — both with the same code path |

---

## 5. Limitations Surfaced

### 5.1 Retrieval gap on canonical operative statutes

UU 14/2005 (Guru dan Dosen) is the operative statute on the topic but did not rank in the parallel `pasal.id /search` results. Same pattern for Perpres 19/2025 (Tukin). The `_CANONICAL_PROBES` mechanism in `agents/peneliti.py` was added in `b4a776c` to handle exactly this for Tipikor / Pengadaan / Outsourcing topics, but does not yet cover education-welfare. Recommended addition:

```python
(("dosen", "guru", "tunjangan profesi", "tukin", "kesejahteraan dosen", "permendiktisaintek"),
 "akn/id/act/uu/2005/14"),  # UU Guru dan Dosen
(("dosen", "guru", "tunjangan profesi", "tukin"),
 "akn/id/act/uu/2012/12"),  # UU Pendidikan Tinggi
(("tukin", "tunjangan kinerja"),
 "akn/id/act/perpres/2025/19"),
```

This is the same shape as the Tipikor/Pengadaan probes; small additive change.

### 5.2 Case-status sensitivity reminder

This topic involves an in-progress RUU (Sisdiknas), not a court case. But the Kasus Ibam erratum (`1c88af7`) reminds us: any time agents handle status-bearing facts (RUU stage, court status, regulation enactment date), the verifier doesn't catch wrongness. A future Pemantau Berita-class agent that probes news for current case/RUU status before injection would close this surface.

---

## 6. Reproduction

```bash
git clone https://github.com/pebaryan/Legawa
cd Legawa
cp .env.example .env  # PASAL_API_TOKEN, LLM URLs
pip install -e .
legawa health

legawa surat tests/fixtures/surat-gaji-tunjangan-dosen.txt -o output/balasan-dosen.md
legawa research "kerangka hukum penghasilan dan tunjangan dosen Indonesia: UU Guru dan Dosen, Permendiktisaintek terbaru, dan posisi tunjangan dalam revisi UU Sisdiknas" -o output/riset-dosen.md
legawa draft memo_kebijakan "respons legislatif atas aspirasi Forum Dosen Indonesia mengenai gaji, tunjangan, dan posisi tunjangan dosen dalam revisi UU Sisdiknas" -o output/memo-dosen.md
legawa cache stats
```

## 7. Sources

- [Update Gaji Dosen 2026, Aturan Baru ASN dan Non-ASN Sesuai Permendiktisaintek 52/2025](https://bansos.medanaktual.com/update-gaji-dosen-2026-ini-aturan-baru-asn-dan-non-asn-sesuai-permendiktisaintek-52-2025/)
- [Tempo: Ini Ketentuan Penghasilan Dosen di Peraturan Menteri Terbaru](https://www.tempo.co/politik/ini-ketentuan-penghasilan-dosen-di-peraturan-menteri-terbaru-2103670)
- [Hukumonline: Dosen ASN Resmi Dapat Tunjangan Kinerja](https://www.hukumonline.com/berita/a/dosen-asn-resmi-dapat-tunjangan-kinerja--berikut-besaran-dan-jadwal-pencairannya-lt67ff5731b9f11/)
- [DPR Pastikan Tunjangan Guru Tak Dihapus dalam Revisi UU Sisdiknas](https://www.nu.or.id/amp/nasional/dpr-pastikan-tunjangan-guru-tak-dihapus-dalam-revisi-uu-sisdiknas-H5SoH)
- [Dunia Dosen: Ketentuan Baru Gaji Dosen Sesuai Permendiktisaintek 52/2025](https://duniadosen.com/karir/ketentuan-baru-gaji-dosen-sesuai-permendiktisaintek-no-52/)

---

*End of report.*

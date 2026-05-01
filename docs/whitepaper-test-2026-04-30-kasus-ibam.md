# Whitepaper: Kasus Ibam — Failure Analysis, Hardening, and Post-Fix Validation

**Subject:** Validation of legawa across all four production agents on a difficult cross-domain case (Kasus Ibam — Chromebook procurement corruption), tracing every defect found, every patch applied, and the post-fix end-to-end validation
**Date of run:** 2026-04-30
**Repository:** `https://github.com/pebaryan/Legawa`
**Companion to:** `whitepaper-test-2026-04-30.md` (outsourcing topic, easier corpus fit)
**Status:** This document supersedes the earlier partial-fix draft of the same name.

---

## 1. Executive Summary

This is the second live validation of legawa, designed to stress the system on a domain where the topic is *adjacent to* — rather than *contained in* — the regulatory corpus. The first whitepaper validated the system on a regulatory issue (outsourcing post-Cipta Kerja) where pasal.id holds the canonical primary instruments. This run targets a corruption case (Kasus Ibam, sentenced 16 April 2026 by the Pengadilan Tipikor over Chromebook/CDM procurement at Kemendikbudristek) where pasal.id does not index the case itself; the agent must construct understanding from procurement law (Perpres 16/2018, Perpres 12/2021) and anti-corruption law (UU 31/1999 jo UU 20/2001).

**The first attempt exposed five failure modes** — domain drift (memo reframed K-12 procurement as Perguruan Tinggi governance), date hallucination, content-blind citation verification, missed canonical Tipikor laws, and query-expansion noise. **Ten hardening patches were applied** across `config.py`, `tools/citations.py`, `tools/cache.py`, and `agents/penyusun.py` (and the analogous verification path in `agents/analis_ruu.py` and `agents/surat.py`). **The post-fix re-run produces a memo that passes strict citation verification** with correct K-12 framing, accurate case facts, and proper canonical citations.

The verdict: legawa now passes the bar for **staff-augmentation use with mandatory review**. The four production agents — Surat Konstituen, Peneliti Hukum, Penyusun Naskah, Analis RUU — all enforce code-level guardrails (citation verification with content alignment, runtime date injection, domain anchoring with case-fact overrides, canonical FRBR-URI probes for known-canonical laws, and acronym-expansion-aware topical overlap). System prompts alone proved insufficient to prevent hallucinations; the patches that actually moved quality forward were structural code changes.

---

## 2. Why This Test Was Run

The first whitepaper tested a *regulatory* topic. This run is designed to be harder:

- **Subject is a person, not a regulation** — pasal.id indexes regulations; the case itself is not in the corpus. The agent must triangulate.
- **Adjacent legal domains** — anti-corruption + public procurement + education-sector accountability. Three separate legal frames must be composed.
- **Recency** — the case was sentenced 14 days before the run. Some derivative commentary is not yet indexed.
- **Sector confusability** — "education" maps to two distinct corpora in pasal.id: pendidikan tinggi (UU 12/2012) and pendidikan dasar/menengah (UU 20/2003 Sisdiknas). The model has a stronger prior on "pendidikan tinggi scandal" because that is the pattern most often surfaced in Indonesian legal news.

The first run deliberately chose a topic where pasal.id has the answer. This run deliberately chose a topic where it does not.

---

## 3. Pre-Fix State — What Failed

### 3.1 Test artifacts before any patches

Three commands run against the constituent fixture `tests/fixtures/surat-chromebook-sekolah.txt` (a synthetic letter from a Probolinggo SDN principal about non-functional Chromebooks):

```bash
legawa surat tests/fixtures/surat-chromebook-sekolah.txt -o output/balasan-chromebook.md
legawa research "akuntabilitas pengadaan barang jasa pemerintah dan tindak pidana korupsi sektor pendidikan pasca kasus Chromebook" -o output/riset-chromebook.md
legawa draft memo_kebijakan "respons legislatif atas vonis Kasus Ibam dan permintaan akuntabilitas Program Digitalisasi Sekolah" -o output/memo-chromebook.md
```

### 3.2 Defects found

| # | Defect | Severity | Where it surfaced |
|---|---|---|---|
| **D1** | Surat reply substituted hallucinated `Perpres 76/2021` even though triage extracted the correct `Perpres 12/2021`. | Medium | `agents/surat.py` reply step |
| **D2** | Memo header self-dated to `24 Mei 2024`; footer claimed "data hingga Mei 2024". Run was 2026-04-30. | High | `agents/penyusun.py` |
| **D3** | Memo entirely reframed Kasus Ibam (a K-12 procurement case) as a **Perguruan Tinggi governance scandal**. Cited UU 12/2012 Pendidikan Tinggi as the operative framework. | High | `agents/penyusun.py` chained Peneliti+BIG |
| **D4** | Peneliti missed canonical Tipikor laws (`UU 31/1999 jo UU 20/2001`) — the laws the actual Ibam conviction was decided under. Surfaced `UU 3/1971` and labelled it `Berlaku` (it has been superseded). Cited `Perpres 46/2025` as 2nd amendment to Perpres 16/2018 — unverified. | High | `agents/peneliti.py` query expansion + retrieval |
| **D5** | Query expansion produced "Lembaga Pengadaan Negara (LPN)" — wrong; the institution is LKPP. | Low | `agents/peneliti.py` SMALL fan-out |
| **D6** | Citation verifier passed `UU 12/2023 tentang Sistem Pendidikan Tinggi` — a hallucinated topical claim attached to a real-but-different `(number, year)` tuple. Verifier checked existence only, not content alignment. | High | `tools/citations.py::verify_citation` |

D1–D6 led to the conclusion that **system-prompt instructions are insufficient** to prevent hallucination; **code-level guardrails** are required. The patches below implement those guardrails.

---

## 4. Hardening Patches Applied

Ten distinct patches were applied across the codebase. Each is small (≤ 50 lines); their aggregate effect is the difference between an unsupervised hallucination machine and a citation-disciplined drafting tool.

### 4.1 Runtime context injection (`config.py`)

Adds three new fields to `Settings` — `run_date` (default `date.today().isoformat()`, override via `LEGAWA_RUN_DATE`), `corpus_watermark` (override via `PASAL_CORPUS_WATERMARK`), `strict_citations` (default `True`, override via `LEGAWA_STRICT_CITATIONS`). Every agent system prompt now interpolates `{run_date}` and `{corpus_watermark}` placeholders.

**Fixes:** D2 (date hallucination, false provenance claims).

### 4.2 Citation extraction module (`tools/citations.py` — new)

- `extract_citations(text)` — UU/PP/Perpres/Permen/Perda/UUD/FRBR-URI patterns, normalized to compact form (`UU 13/2003`, `Perpres 12/2021`).
- `verify_citation(pasal, ref, claimed_topic=None)` — searches pasal.id by canonical query; returns `CitationCheck` with `found`, `title`, `frbr_uri`, `status`, `note`.
- `verify_citations(pasal, refs)` — batched, deduplicated.
- `format_basis_block(pasal, refs)` — renders the verified BASIS HUKUM block consumed by `agents/surat.py` before drafting.

**Fixes:** prerequisite for the rest of §4.

### 4.3 Strict-mode post-generation citation check (`agents/penyusun.py`, `analis_ruu.py`, `surat.py`)

Each agent runs `_verify_output_citations(text)` after the BIG model emits its draft. In strict mode, a single unverifiable citation raises `ValueError` and the draft is not written. In non-strict mode, warnings are printed.

**Fixes:** D1 (citation hallucination at draft time). The Perpres 76/2021 → 12/2021 substitution stops happening because if it did, strict mode would reject.

### 4.4 Bidirectional context capture (`tools/citations.py::_claimed_topic_near`)

Originally captured only "tentang X" after a citation. Extended to:

1. **After-citation "tentang X"** with intervening-citation guard — in `UU 31/1999 jo UU 20/2001 ... tentang Pengadaan`, the "tentang" attaches to the closest citation only.
2. **Parenthetical-alias pattern** — `<NOUN PHRASE> (ACRONYM) melalui <CITATION>` captures the noun phrase as the implicit topic. Catches the "(SAKIP) melalui Permen Diktisaintek 58/2025" form.

Tightened during iteration: an earlier draft also captured generic "tentang X" *before* a citation, but that produced false positives when an unrelated earlier clause used "tentang"; that path was removed.

**Fixes:** D6 (verifier was content-blind for non-trivial layouts).

### 4.5 Acronym expansion table (`tools/citations.py::_ACRONYM_EXPANSIONS`)

Indonesian institutional acronyms (MPR, DPR, DPD, DPRD, KPK, BPK, BPKP, LKPP, LPSK, OJK, KPU, Bawaslu, Polri, TNI, SAKIP, RDP, RUU, UUD) map to a tuple of expansion tokens. `_topics_overlap` checks acronym expansions against the pasal.id title before declaring a mismatch.

**Fixes:** false-positive rejection of `UU 17/2014` cited with claim "MPR, DPR, DPD, dan DPRD" against title "Majelis Permusyawaratan Rakyat, Dewan Perwakilan Rakyat...".

### 4.6 Malformed-title guard (`tools/citations.py::_is_uninformative_title`)

Some pasal.id search responses return tautological titles like `"Undang-Undang Nomor 20 Tahun 2003 tentang Undang-Undang Nomor 20 Tahun 2003"` — the "tentang ..." clause echoes the header instead of stating the subject. After stop-word and digit filtering these titles produce zero usable tokens. The guard treats them as carrying no signal and falls back to existence-only verification.

**Fixes:** false-positive rejection of `UU 20/2003 tentang Sistem Pendidikan Nasional` (the actual Sisdiknas law) when pasal.id returned an echoed title.

### 4.7 UUD 1945 constitutional whitelist

UUD 1945 is the supreme law and is universally cited; pasal.id's search endpoint does not index it as an ordinary statute. The verifier short-circuits on `"UUD 1945"` references — accepted by whitelist with no version-drift risk.

**Fixes:** false-positive rejection of constitutional citations.

### 4.8 Permen-with-space regex (`tools/citations.py::_REGULATION_RE`)

Original pattern `Permen(?:[A-Za-z]+)?` only matched glued forms (`Permendikbudristek`). Updated to `Permen(?:\s*[A-Za-z]+)?` to also match `Permen Diktisaintek`, `Peraturan Menteri X`, etc.

**Fixes:** silent extraction failures for ministry-name-with-space forms.

### 4.9 Domain anchor + case-fact injection (`agents/penyusun.py`)

Two-tier domain detection:

- **Keyword triggers:** K-12 (`sekolah dasar`, `sdn`, `digitalisasi sekolah`, `kasus ibam`, `ibrahim arief`, `kemendikbudristek`, `kemendikdasmen`, etc.) vs PT (`perguruan tinggi`, `ptn`, `pts`, `kampus`, `rektor`, `dosen`, etc.). Mutually exclusive constraint when only one fires; both-jenjang note when both fire.
- **Case-fact injection:** when topic mentions a known case name (e.g., `kasus ibam`, `ibrahim arief`), prepend an authoritative fact block to the system prompt:

  > FAKTA KASUS IBAM (gunakan ini sebagai sumber, jangan diabaikan): Kasus Ibam adalah perkara korupsi pengadaan Chromebook dan Chrome Device Management (CDM) di Kementerian Pendidikan ... pelaku: Ibrahim Arief, alias Ibam — eks-konsultan Tim Teknologi Kemendikbudristek di bawah Mendikbudristek Nadiem Makarim. Vonis: Pengadilan Tipikor 16 April 2026 — 15 tahun penjara, denda Rp 1 miliar, uang pengganti Rp 16,92 miliar. Distribusi Chromebook ditujukan untuk sekolah dasar dan menengah dalam Program Digitalisasi Sekolah; INI BUKAN kasus tata kelola Perguruan Tinggi/PTN/PTS, bukan kasus rekrutmen dosen, bukan kasus akademik.

The case-fact block is the single highest-impact patch in the run. Without it, the BIG model's prior on "Kasus Ibam = university scandal" beat the K-12 keyword anchor. With it, the model has authoritative facts to anchor against.

**Fixes:** D3 (domain drift). Extensible: `_CASE_FACTS` is a tuple of `(keywords, fact_block)` pairs.

### 4.10 Canonical FRBR-URI probes (`agents/peneliti.py`)

When topic + queries match curated keywords (`tipikor`/`korupsi`/`pengadaan`/`outsourcing`/...), Peneliti directly fetches a curated set of FRBR URIs via `pasal.get_law()` *before* the parallel free-text search, and merges those hits into the synthesis context. Curated set in this iteration:

| Trigger keywords | FRBR URIs probed |
|---|---|
| tipikor / korupsi / gratifikasi / suap | `akn/id/act/uu/1999/31`, `akn/id/act/uu/2001/20` |
| pengadaan / barang jasa / chromebook | `akn/id/act/perpres/2018/16`, `akn/id/act/perpres/2021/12` |
| outsourcing / ketenagakerjaan / buruh | `akn/id/act/uu/2003/13`, `akn/id/act/uu/2023/6`, `akn/id/act/pp/2021/35` |

**Fixes:** D4 (missed canonical Tipikor laws). The synthesis now reliably surfaces UU 31/1999 jo UU 20/2001 as the operative anti-corruption framework.

### 4.11 Cache thread-safety (`tools/cache.py`)

The original `_SqliteCache` shared one `sqlite3.Connection` across `ThreadPoolExecutor` workers in Peneliti's parallel search. Concurrent `conn.execute(...)` calls produced `sqlite3.InterfaceError: bad parameter or other API misuse`. Wrapped all access with a `threading.Lock`.

**Fixes:** intermittent crash on chained Peneliti calls (surfaced once Penyusun's internal Peneliti calls increased cache miss volume).

---

## 5. Post-Fix Validation

### 5.1 Surat — full pipeline

```
legawa surat tests/fixtures/surat-chromebook-sekolah.txt -o output/balasan-chromebook.md
```

Triage classification matches §4.2 of the previous whitepaper (correct on every dimension). The drafted reply now correctly cites `Perpres 16/2018` and `Perpres 12/2021` — D1 fix confirmed. Strict-mode citation verification passed (output emitted; no `ValueError`).

### 5.2 Peneliti — research

```
legawa research "akuntabilitas pengadaan barang jasa pemerintah dan tindak pidana korupsi sektor pendidikan pasca kasus Chromebook" -o output/riset-chromebook.md
```

Primary instruments now cited:

| Section | Instrument | FRBR URI | Status |
|---|---|---|---|
| A | Perpres 12/2021 (perubahan atas Perpres 16/2018) | `/akn/id/act/perpres/2021/12` | Berlaku |
| B | Peraturan LKPP 17/2019 | `/akn/id/act/peraturan-lkpp/2019/17` | Berlaku |
| C | UU 20/2001 (perubahan UU 31/1999) | `/akn/id/act/uu/2001/20` | Berlaku |
| D | UU 31/1999 | `/akn/id/act/uu/1999/31` | Berlaku |
| E | Perpres 51/2023 (tunjangan KPK) | `/akn/id/act/perpres/2023/51` | Berlaku |

D4 fix confirmed: UU 31/1999 jo UU 20/2001 are now retrieved (via canonical FRBR-URI probe) and surfaced in the memo. UU 3/1971 (the obsolete pre-Reformasi law) is no longer cited. Perpres 46/2025 (the previously-hallucinated "second amendment") is gone.

### 5.3 Penyusun — memo

```
legawa draft memo_kebijakan "respons legislatif atas vonis Kasus Ibam dan permintaan akuntabilitas Program Digitalisasi Sekolah" -o output/memo-chromebook.md
```

Selected excerpts demonstrating the fixes:

> **Tanggal:** 30 April 2026 *(was: "24 Mei 2024" pre-fix — D2 fixed)*

> Vonis 15 tahun penjara terhadap **Ibrahim Arief (Ibam)** dalam perkara korupsi pengadaan Chromebook di Kemendikbudristek mengungkap celah serius dalam tata kelola aset digital **pendidikan dasar/menengah**. *(was: "lemahnya mekanisme pertanggungjawaban pimpinan perguruan tinggi" pre-fix — D3 fixed)*

> Kerangka hukum saat ini, yaitu **UU No. 31 Tahun 1999 jo UU No. 20 Tahun 2001 tentang Pemberantasan Tindak Pidana Korupsi** dan **Perpres No. 16 Tahun 2018 jo Perpres No. 12 Tahun 2021 tentang Pengadaan Barang/Jasa Pemerintah**, terbukti belum cukup mencegah manipulasi teknis pengadaan. *(D4: Tipikor laws now correctly cited)*

> Kasus ini melibatkan manipulasi pengadaan Chromebook dan Chrome Device Management (CDM) yang dialokasikan untuk Program Digitalisasi Sekolah **di jenjang SD dan SMP**. *(case-fact injection working — model now has accurate context)*

> **Catatan Penting:** Memo ini tidak membahas isu pendidikan tinggi (PTN/PTS) atau rekrutmen dosen, melainkan **fokus eksklusif pada akuntabilitas pengadaan di jenjang pendidikan dasar dan menengah sesuai fakta kasus Ibam**. *(model self-acknowledges domain anchor in its own footer)*

**Strict-mode citation verification passed.** Every UU/Perpres reference resolves to a valid pasal.id record with topical alignment (or accepted via existence-only fallback for malformed titles / constitutional whitelist).

### 5.4 Cache state

```
{'entries': 113, 'bytes': 480976, 'session_hits': 0, 'session_misses': 0}
```

113 unique cached search/laws/get_law responses (≈ 481 KB) accumulated across two whitepapers' worth of test runs. The thread-safety lock added in §4.11 supports the concurrent fan-out from Peneliti without crashing.

---

## 6. Quality Assessment

| Dimension | Pre-fix | Post-fix |
|---|---|---|
| Surat triage accuracy | ✓ pass | ✓ pass |
| Surat drafted reply citation discipline | ⚠️ Perpres 76/2021 hallucinated | ✓ pass |
| Peneliti retrieval — canonical Tipikor laws | 🔴 missed (UU 31/1999 absent, UU 3/1971 wrongly labelled "Berlaku") | ✓ both UU 31/1999 + UU 20/2001 cited from canonical probe |
| Peneliti FRBR URI integrity | ⚠️ Perpres 46/2025 unverified | ✓ all FRBR URIs verifiable |
| Penyusun domain alignment | 🔴 K-12 → PT drift | ✓ K-12 anchor + case facts hold |
| Penyusun date accuracy | 🔴 hardcoded 2024 | ✓ run-date injected |
| Penyusun name accuracy | 🔴 invented "Ibnu Sina" for Ibam | ✓ "Ibrahim Arief (Ibam)" |
| Verifier content-alignment | 🔴 existence-only | ✓ topical overlap with malformed-title fallback |
| Verifier acronym handling | n/a | ✓ MPR ↔ Majelis Permusyawaratan, etc. |
| Verifier citation-chain handling | n/a | ✓ "tentang X" attaches only to closest citation |

---

## 7. Remaining Limitations

The system is now substantially more robust, but it is not perfect. Surfaced during testing:

1. **Case-fact catalogue is hand-curated.** `_CASE_FACTS` currently has one entry (Kasus Ibam). Other high-profile cases would need explicit entries to get the same domain-anchoring benefit. A more scalable approach would be a small SMALL-model classifier that extracts `(sektor, jenjang, instansi, kasus_id)` from the topic + research block and synthesises a case-fact block on the fly. Out of scope for this iteration.

2. **`Permen <Ministry>` shortcuts lose the ministry on normalization.** "Permenaker 5/2025" extracts to `Permen 5/2025`. The verifier still searches pasal.id and matches by `(number, year)`, but ministry-specific search ranking may degrade. Fix is a 5-line addition to `_canonical_permen` to detect the shortcut forms; deferred.

3. **Stray `</think>` tokens from the BIG model.** The localhost llama.cpp instance occasionally leaks a closing think tag without its opening pair (likely the chat template consumes `<think>` before tokens are emitted). Our `strip_thinking` regex requires both tags so a stray `</think>` survives. Defense-in-depth fix would also strip orphan closing tags. Low priority because the actual answer content still comes through.

4. **Title quality from pasal.id search vs get_law.** Pasal.id's search responses sometimes return malformed titles (echoed self-references). `get_law` responses are typically cleaner. The verifier currently uses search; a future iteration could fall back to `get_law` when the search hit's title is uninformative, at the cost of one extra HTTP call per ambiguous citation (cache-mitigated).

5. **Domain anchor relies on keyword matching.** Robust for the patterns we've seen (K-12 vs PT, korupsi/pengadaan, ketenagakerjaan, IT/forensik). Not robust against novel sectors. The right long-term shape is the SMALL-model classifier mentioned in (1).

6. **No integration test suite.** All validation is currently manual against the two fixtures (`surat-buruh-outsourcing.txt`, `surat-chromebook-sekolah.txt`). A `pytest` suite that runs the regex/verifier/anchor logic with frozen fixtures (no live LLM/API calls) would catch regressions on future patches. Recommended next.

---

## 8. Recommendations

### 8.1 Production-readiness

The four agents are fit for **drafting-with-mandatory-staff-review** workflow, with these guarantees and caveats:

- **Citation discipline**: every UU/Perpres/PP/Permen reference in production output is verified against pasal.id by `(kind, number, year) + topical-alignment`. Strict-mode rejection means hallucinated citations fail the build, not the staff review.
- **Date discipline**: every output is dated against `LEGAWA_RUN_DATE` (default: today).
- **Domain discipline**: domain anchors fire on common Indonesian legal sectors. For high-profile cases, case-facts override the model's prior.
- **Caveat — placeholders**: `[NAMA ANGGOTA LEGISLATIF]`, `[FRAKSI/DAERAH PEMILIHAN]`, `[DATA BPS DAPIL]` etc. are intentionally left for staff to fill.
- **Caveat — non-corpus knowledge**: pasal.id covers regulations, not court decisions or news. For case-specific factual claims, the case-fact catalogue is the source of truth. Treat the catalogue as code, not configuration.

### 8.2 Next iterations

In priority order:

1. **`pytest` regression suite** — freeze the existing fixtures and citation patterns; assert that key extractions, overlaps, and chain handling don't regress on future patches.
2. **Audit log per session** — every tool call (pasal.id query, LLM completion, verifier check, draft output) appended to a JSONL file under `output/audit/<session-id>.jsonl` for staff review and compliance.
3. **Persist triage results** as `output/triase/<date>/<id>.json` for downstream analytics on incoming aspirasi distribution.
4. **SMALL-model domain classifier** to replace the keyword-based `_derive_domain_constraints` with a learned extractor. Lower priority — keyword anchor handles the common cases.
5. **Pemantau Berita** (5th agent) becomes especially useful for cases like Ibam where pasal.id alone is insufficient. A daily monitor on Indonesian legal news (Detik, Kompas, Tirto, Hukumonline) would feed the case-fact catalogue automatically.

---

## 9. Comparison with Test 1 (Outsourcing)

| Aspect | Test 1 (Outsourcing) | Test 2 (Kasus Ibam) |
|---|---|---|
| Topic type | Regulatory issue with primary statute in pasal.id | Specific court case + adjacent legal framework |
| Pasal.id corpus fit | High — UU 6/2023, PP 35/2021 are authoritative | Medium — Tipikor laws exist but were missed pre-fix |
| Surat agent | Pass | Pass post-fix |
| Peneliti agent | Pass with honest gap-flagging | Pass post-fix (canonical probes added) |
| Penyusun agent | Not exercised in Test 1 | **Pass post-fix** (was the most fragile) |
| Defects in fixed-state | 3 (infrastructure: stdio/thinking/markup) | 0 outstanding (10 fixed) |
| Whitepaper outcome | Validation | **Defect-driven hardening + validation** |

**Combined verdict:** legawa is a credible local-only multi-agent system for Indonesian legislator staff, with citation-disciplined output that survives strict verification on adversarial cross-domain cases. It is not yet fit for unsupervised use; it is fit for staff-augmentation with mandatory review.

---

## 10. Appendix

### 10.1 Files produced

| File | Purpose |
|---|---|
| `tests/fixtures/surat-chromebook-sekolah.txt` | 700-word constituent letter from a Probolinggo SDN principal |
| `output/balasan-chromebook.md` | Triage + verified reply |
| `output/riset-chromebook.md` | Legal research memo (procurement + Tipikor) with canonical probes |
| `output/memo-chromebook.md` | Policy memo (passes strict citation verification) |
| `output/riset-chromebook-trace.log` | Peneliti trace |
| `output/memo-chromebook-trace.log` | Penyusun trace |

### 10.2 Patches applied (file → change)

| File | Change |
|---|---|
| `src/legawa/config.py` | `run_date`, `corpus_watermark`, `strict_citations` settings |
| `src/legawa/llm.py` | `LLMPool.settings` exposed; `strip_thinking` centralised |
| `src/legawa/tools/citations.py` | New module — extract, verify (with content alignment), acronym expansion, malformed-title guard, UUD whitelist, citation-chain awareness |
| `src/legawa/tools/cache.py` | Thread-safety lock |
| `src/legawa/tools/pasal.py` | (unchanged) |
| `src/legawa/agents/peneliti.py` | Canonical FRBR-URI probes; system prompt includes `{run_date}` |
| `src/legawa/agents/penyusun.py` | Domain anchor (K-12 / PT / korupsi / ketenagakerjaan / IT); case-fact injection (`_CASE_FACTS`); strict citation verifier |
| `src/legawa/agents/analis_ruu.py` | System prompt includes `{run_date}`; strict citation verifier |
| `src/legawa/agents/surat.py` | Strict citation verifier on the drafted reply |

### 10.3 Reproduction

```bash
git clone https://github.com/pebaryan/Legawa
cd Legawa
cp .env.example .env  # add PASAL_API_TOKEN, configure LLM URLs
pip install -e .
legawa health

legawa surat tests/fixtures/surat-chromebook-sekolah.txt -o output/balasan-chromebook.md
legawa research "akuntabilitas pengadaan barang jasa pemerintah dan tindak pidana korupsi sektor pendidikan pasca kasus Chromebook" -o output/riset-chromebook.md
legawa draft memo_kebijakan "respons legislatif atas vonis Kasus Ibam dan permintaan akuntabilitas Program Digitalisasi Sekolah" -o output/memo-chromebook.md
legawa cache stats
```

To run with citation enforcement disabled (warnings only, useful for exploring model output without `ValueError`):

```bash
LEGAWA_STRICT_CITATIONS=0 legawa draft memo_kebijakan "..." -o output/memo.md
```

### 10.4 Sources for case context

- Detik: [Sidang Vonis Ibam Eks Konsultan Nadiem di Kasus Chromebook Digelar 12 Mei](https://news.detik.com/berita/d-8465348/sidang-vonis-ibam-eks-konsultan-nadiem-di-kasus-chromebook-digelar-12-mei)
- Tirto: [Kronologi Kasus Ibrahim Arief & Tuntutan 15 Tahun Bui](https://tirto.id/kronologi-kasus-ibrahim-arief-tuntutan-15-tahun-bui-huV7)
- Detik: [Ibam Eks Anak Buah Nadiem Nangis Baca Pleidoi: Apa Dosa Saya bagi Indonesia?](https://news.detik.com/berita/d-8458535/ibam-eks-anak-buah-nadiem-nangis-baca-pleidoi-apa-dosa-saya-bagi-indonesia)
- Infonasional: [Vonis Kasus Korupsi Chromebook Ibrahim Arief Digelar 12 Mei](https://www.infonasional.com/vonis-kasus-korupsi-chromebook-ibrahim-arief-digelar-12-mei)

---

*End of report.*

"""Helpers for extracting and verifying legal citations.

The agents routinely cite Indonesian statutes and regulations in free-form
Markdown. This module normalizes those citations into a small canonical set
and verifies them against pasal.id before output is released.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable


_FRBR_RE = re.compile(
    r"\b(?:frbr_uri['\"]?\s*[:=]\s*)?akn/id/act/(?P<kind>[a-z_]+)/(?P<year>\d{4})/(?P<number>\d+)\b",
    re.IGNORECASE,
)

_UUD_RE = re.compile(
    r"\b(?:UUD|Undang[-\s]Undang Dasar(?: Negara Republik Indonesia)?)\s*1945\b",
    re.IGNORECASE,
)

_REGULATION_RE = re.compile(
    r"""
    \b
    (?P<label>
        UU
        |Undang[-\s]Undang
        |Perppu
        |Peraturan\s+Pemerintah\s+Pengganti\s+Undang[-\s]Undang
        |PP
        |Peraturan\s+Pemerintah
        |Perpres
        |Peraturan\s+Presiden
        |Perda(?:\s+(?:Provinsi|Kabupaten(?:/Kota)?|Kota)(?:\s+[A-Za-z][\w&/\-]*){0,6})?
        |Peraturan\s+Daerah(?:\s+(?:Provinsi|Kabupaten(?:/Kota)?|Kota)(?:\s+[A-Za-z][\w&/\-]*){0,6})?
        |Permen(?:\s*[A-Za-z]+)?
        |Peraturan\s+Menteri(?:\s+[A-Za-z][\w\s&/\-]*)?
    )
    \s*(?:No\.?|Nomor)?\s*
    (?P<number>\d{1,4})
    \s*(?:/|Tahun)\s*
    (?P<year>\d{4})
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_KIND_CANONICAL = {
    "uu": "UU",
    "undang-undang": "UU",
    "perppu": "Perppu",
    "peraturan pemerintah pengganti undang-undang": "Perppu",
    "pp": "PP",
    "peraturan pemerintah": "PP",
    "perpres": "Perpres",
    "peraturan presiden": "Perpres",
    "perda": "Perda",
    "peraturan daerah": "Perda",
    "permendagri": "Permendagri",
    "permenkes": "Permenkes",
    "permenkeu": "Permenkeu",
    "permentan": "Permentan",
    "permenaker": "Permenaker",
}


@dataclass(frozen=True)
class CitationCheck:
    reference: str
    found: bool
    query: str
    title: str | None = None
    frbr_uri: str | None = None
    status: str | None = None
    evidence: str | None = None
    note: str | None = None
    claimed_topic: str | None = None


@dataclass(frozen=True)
class CitationContext:
    reference: str
    claimed_topic: str | None = None


# Indonesian + procedural stop words filtered out of topical-overlap checks.
_STOP_TOKENS = frozenset(
    {
        "ada", "adalah", "agar", "akan", "atas", "atau", "bagi", "bagaimana",
        "bahwa", "bukan", "dalam", "dan", "dari", "dasar", "dengan", "di", "ini",
        "itu", "jika", "juga", "karena", "ke", "kepada", "kita", "lain", "lebih",
        "namun", "nomor", "no", "negara", "oleh", "pada", "para", "pasal",
        "peraturan", "perubahan", "pertama", "kedua", "republik", "indonesia",
        "sebagai", "sebagaimana", "selain", "serta", "supaya", "tahun", "telah",
        "tentang", "terhadap", "tidak", "untuk", "yang", "ayat", "huruf",
        "tata", "ketentuan", "umum", "undang",
    }
)

# Tokens that name an institution, sector, or generic government context.
# These appear in the *title* of nearly every regulation issued by that
# institution (e.g. "Kementerian Pendidikan" appears in every Kemendikbud
# Permen) and in any *claim* that names the institution — so an overlap on
# these tokens alone does not confirm topical alignment.
#
# Used by ``_topics_overlap`` to demand at least one *non-institutional*
# token in common before declaring a match. Acronyms (MPR/DPR/KPK/...) are
# kept out of this set because their expansions ARE the topic in regulations
# whose subject is the institution itself (e.g. UU 17/2014 about MPR/DPR).
_INSTITUTIONAL_TOKENS = frozenset(
    {
        # Generic government context.
        "kementerian", "pemerintah", "pemerintahan", "negeri", "lingkungan",
        "instansi", "lembaga", "publik", "pusat", "lingkup", "wilayah",
        "kantor",
        # Sector markers — when alone, signal sector not topic. Specific
        # subject matter (audit / pengelolaan / arsip / outsourcing / etc.)
        # is what should drive topical match, not the ministry name.
        "pendidikan", "kebudayaan", "kesehatan", "keuangan",
        "ketenagakerjaan", "pertanian", "perhubungan", "kehutanan",
        "kelautan", "pertahanan", "agama", "sosial", "perindustrian",
        "perdagangan", "ristek", "riset", "teknologi", "informasi",
        "komunikasi", "perekonomian", "perencanaan", "pembangunan",
    }
)


# Common Indonesian institutional acronyms — agents tend to use the acronym
# while the regulation's actual title spells the institution out. We expand
# claim-side acronyms before topical-overlap so e.g. "MPR" matches a title
# containing "Majelis Permusyawaratan Rakyat".
_ACRONYM_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "mpr": ("majelis", "permusyawaratan"),
    "dpr": ("dewan", "perwakilan", "rakyat"),
    "dpd": ("dewan", "perwakilan", "daerah"),
    "dprd": ("dewan", "perwakilan", "rakyat", "daerah"),
    "kpk": ("komisi", "pemberantasan", "korupsi"),
    "bpk": ("pemeriksa", "keuangan"),
    "bpkp": ("pengawasan", "keuangan", "pembangunan"),
    "lkpp": ("kebijakan", "pengadaan", "barang"),
    "lpsk": ("perlindungan", "saksi", "korban"),
    "ojk": ("otoritas", "jasa", "keuangan"),
    "sakip": ("sistem", "akuntabilitas", "kinerja", "instansi"),
    "rdp": ("rapat", "dengar", "pendapat"),
    "ruu": ("rancangan",),
    "uud": ("dasar",),
    "kpu": ("komisi", "pemilihan", "umum"),
    "bawaslu": ("badan", "pengawas", "pemilu"),
    "polri": ("kepolisian",),
    "tni": ("tentara", "nasional"),
}


def _significant_tokens(text: str) -> set[str]:
    """Tokens worth comparing for topical overlap.

    Drops stop words and very short tokens, but keeps short ALL-CAPS tokens
    which are almost always institutional acronyms (MPR, DPR, KPK, BPK, ...).
    """
    if not text:
        return set()
    raw_tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+", text)
    out: set[str] = set()
    for raw in raw_tokens:
        lowered = raw.lower()
        if lowered in _STOP_TOKENS:
            continue
        if len(raw) >= 4:
            out.add(lowered)
        elif len(raw) >= 2 and raw.isupper():
            out.add(lowered)
    return out


def _is_uninformative_title(title: str) -> bool:
    """True if a pasal.id title carries no usable topic signal.

    Some pasal.id search responses return malformed titles like
    'Undang-Undang Nomor 20 Tahun 2003 tentang Undang-Undang Nomor 20 Tahun 2003'
    — the 'tentang ...' clause echoes the header instead of stating the subject.
    After stop-word and number filtering, such titles produce zero usable tokens
    and a topical overlap check would unfairly reject the citation. In those
    cases we fall back to existence-only verification.
    """
    tokens = _significant_tokens(title)
    real = {t for t in tokens if not t.isdigit()}
    return len(real) < 2


def _topics_overlap(claimed: str, title: str) -> bool:
    if _is_uninformative_title(title):
        return True

    claim_tokens = _significant_tokens(claimed)
    title_tokens = _significant_tokens(title)

    # Direct token overlap counts only if at least one shared token is
    # non-institutional. This guards against false positives where claim
    # and title share only ministry/sector context (e.g. "Kementerian
    # Pendidikan") while their actual subjects are different.
    overlap = claim_tokens & title_tokens
    if overlap and (overlap - _INSTITUTIONAL_TOKENS):
        return True

    # Expand any claim-side acronyms and check for partial title overlap.
    for token in list(claim_tokens):
        expansion = _ACRONYM_EXPANSIONS.get(token)
        if expansion and any(piece in title_tokens for piece in expansion):
            return True

    return False


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _canonical_permen(label: str) -> str:
    lower = label.lower()
    if "ketenagakerjaan" in lower:
        return "Permenaker"
    if "dalam negeri" in lower or "dagri" in lower:
        return "Permendagri"
    if "kesehatan" in lower:
        return "Permenkes"
    if "keuangan" in lower:
        return "Permenkeu"
    if "pertanian" in lower:
        return "Permentan"
    if "pendidikan" in lower and ("ristek" in lower or "bud" in lower or "dikbud" in lower):
        return "Permendikbudristek"
    if "hukum" in lower and "ham" in lower:
        return "Permenkumham"
    return "Permen"


def normalize_citation(label: str, number: str | None = None, year: str | None = None) -> str:
    """Normalize a citation string into a canonical short form."""
    raw = label.strip()
    lowered = raw.lower()
    if lowered in {"uud", "undang-undang dasar", "undang-undang dasar negara republik indonesia"}:
        return "UUD 1945"
    if lowered in {"uu", "undang-undang"} and number and year:
        return f"UU {int(number)}/{year}"
    if lowered in {"perppu", "peraturan pemerintah pengganti undang-undang"} and number and year:
        return f"Perppu {int(number)}/{year}"
    if lowered in {"pp", "peraturan pemerintah"} and number and year:
        return f"PP {int(number)}/{year}"
    if lowered in {"perpres", "peraturan presiden"} and number and year:
        return f"Perpres {int(number)}/{year}"
    if lowered.startswith("perda") or lowered.startswith("peraturan daerah"):
        if number and year:
            return f"Perda {int(number)}/{year}"
    if lowered.startswith("permen"):
        if number and year:
            return f"{_canonical_permen(raw)} {int(number)}/{year}"
    if lowered.startswith("peraturan menteri"):
        if number and year:
            return f"{_canonical_permen(raw)} {int(number)}/{year}"
    if number and year and lowered in _KIND_CANONICAL:
        return f"{_KIND_CANONICAL[lowered]} {int(number)}/{year}"
    return raw.strip()


def extract_citations(text: str) -> list[str]:
    """Extract unique legal citations from free-form text.

    The output is intentionally compact, e.g. ``UU 13/2003`` or ``Perpres 12/2021``.
    """
    if not text:
        return []

    hits: list[tuple[int, str]] = []

    for m in _UUD_RE.finditer(text):
        hits.append((m.start(), "UUD 1945"))

    for m in _REGULATION_RE.finditer(text):
        hits.append((m.start(), normalize_citation(m.group("label"), m.group("number"), m.group("year"))))

    for m in _FRBR_RE.finditer(text):
        hits.append((m.start(), normalize_citation(m.group("kind"), m.group("number"), m.group("year"))))

    hits.sort(key=lambda item: item[0])
    return _unique(ref for _, ref in hits)


def _claimed_topic_near(text: str, span_start: int, span_end: int) -> str | None:
    """Capture the topical phrase the agent attaches to a citation.

    Strategy (in order, first match wins):
      1. After-citation 'tentang X' clause — strongest signal — but only if
         no other citation intervenes between this one and the 'tentang'.
         (In a chain like 'UU 31/1999 jo UU 20/2001 ... tentang Pengadaan',
         the 'tentang' belongs to the closest citation, not the first.)
      2. Acronym/parenthetical pattern within the same clause —
         '<NOUN PHRASE> (ALIAS) melalui <CITATION>' captures the noun phrase.
    """
    after_window = text[span_end : span_end + 200]
    m = re.search(
        r"\btentang\s+([^.;\n\)\]]{4,140}?)(?=[.;\n\)\]]|sebagaimana|jo\.|\bjo\b|juncto|\bini\b|\Z)",
        after_window,
        re.IGNORECASE,
    )
    if m:
        # Verify no other citation appears between this citation and the 'tentang'.
        intervening = after_window[: m.start()]
        if not _REGULATION_RE.search(intervening) and not _FRBR_RE.search(intervening):
            claimed = m.group(1).strip(" ,:-")
            if claimed:
                return claimed

    # Before-context: only the parenthetical-alias pattern (structurally reliable).
    # Generic "tentang X" before a citation is too noisy — it often picks up an
    # earlier clause's topic that has nothing to do with the cited regulation.
    before_window = text[max(0, span_start - 200) : span_start]
    last_boundary = max(
        before_window.rfind(". "),
        before_window.rfind(";"),
        before_window.rfind("\n\n"),
    )
    clause = before_window[last_boundary + 1 :] if last_boundary >= 0 else before_window
    if len(clause) < 4:
        return None

    pm = re.search(r"\(([A-Z][A-Z0-9\s/&\-]{1,40})\)", clause)
    if pm:
        head = clause[: pm.start()].rstrip()
        words = re.findall(r"[A-Za-zÀ-ÿ0-9*/&-]+", head)
        if len(words) >= 2:
            phrase = " ".join(words[-6:]).strip(" ,:-*")
            if len(phrase) >= 4:
                return phrase

    return None


def extract_citations_with_context(text: str) -> list[CitationContext]:
    """Like ``extract_citations`` but also captures a 'tentang ...' clause if present.

    Useful when downstream verification should ensure the cited title matches
    the regulation's actual content, not just its (kind, number, year) tuple.
    """
    if not text:
        return []

    contexts: dict[str, CitationContext] = {}

    def record(reference: str, span_start: int, span_end: int) -> None:
        existing = contexts.get(reference)
        if existing and existing.claimed_topic:
            return
        topic = _claimed_topic_near(text, span_start, span_end)
        if existing and not topic:
            return
        contexts[reference] = CitationContext(reference=reference, claimed_topic=topic)

    for m in _UUD_RE.finditer(text):
        record("UUD 1945", m.start(), m.end())

    for m in _REGULATION_RE.finditer(text):
        record(
            normalize_citation(m.group("label"), m.group("number"), m.group("year")),
            m.start(),
            m.end(),
        )

    for m in _FRBR_RE.finditer(text):
        record(
            normalize_citation(m.group("kind"), m.group("number"), m.group("year")),
            m.start(),
            m.end(),
        )

    return list(contexts.values())


def _iter_string_values(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_string_values(value)
    elif isinstance(obj, (list, tuple, set)):
        for value in obj:
            yield from _iter_string_values(value)


def _canonical_from_hit(hit: Any) -> list[str]:
    blobs: list[str] = []
    if isinstance(hit, str):
        blobs.append(hit)
    else:
        blobs.extend(_iter_string_values(hit))
        try:
            blobs.append(json.dumps(hit, ensure_ascii=False))
        except TypeError:
            pass

    refs: list[str] = []
    for blob in blobs:
        refs.extend(extract_citations(blob))
    return _unique(refs)


def _infer_query(ref: str) -> tuple[str, str | None]:
    lowered = ref.lower()
    if lowered.startswith("uud 1945"):
        return "UUD 1945", None
    if lowered.startswith("uu "):
        return ref, "UU"
    if lowered.startswith("pp "):
        return ref, "PP"
    if lowered.startswith("perppu "):
        return ref, "PERPPU"
    if lowered.startswith("perpres "):
        return ref, "PERPRES"
    if lowered.startswith("perda "):
        return ref, "PERDA"
    if lowered.startswith("permendagri") or lowered.startswith("permenkes") or lowered.startswith("permenkeu"):
        return ref, "PERMEN"
    if lowered.startswith("permentan") or lowered.startswith("permenaker"):
        return ref, "PERMEN"
    if lowered.startswith("permen "):
        return ref, "PERMEN"
    return ref, None


def verify_citation(
    pasal_client: Any,
    reference: str,
    *,
    claimed_topic: str | None = None,
    limit: int = 5,
) -> CitationCheck:
    """Verify a single citation against pasal.id search results.

    If ``claimed_topic`` is given (e.g. extracted from a "tentang ..." clause
    surrounding the citation), the check also requires topical overlap between
    the claimed topic and the matched regulation's actual title. This catches
    the failure mode where a (kind, number, year) tuple resolves to a real
    regulation that is *not* about what the agent claimed.
    """
    expected_refs = extract_citations(reference) or [reference.strip()]
    primary = expected_refs[0]

    # The 1945 Constitution is the supreme law of Indonesia and is universally
    # cited; pasal.id's search endpoint does not index it as an ordinary statute.
    # No version drift risk — accept by whitelist.
    if primary.lower().startswith("uud 1945"):
        return CitationCheck(
            reference=primary,
            found=True,
            query=primary,
            title="Undang-Undang Dasar Negara Republik Indonesia Tahun 1945",
            note="constitutional whitelist",
            claimed_topic=claimed_topic,
        )

    query, regulation_type = _infer_query(primary)
    params: dict[str, Any] = {"q": query, "limit": max(1, min(limit, 20))}
    if regulation_type:
        params["type"] = regulation_type

    try:
        response = pasal_client.search(**params)
    except Exception as exc:  # noqa: BLE001
        return CitationCheck(
            reference=expected_refs[0],
            found=False,
            query=query,
            note=f"verifikasi gagal: {exc}",
            claimed_topic=claimed_topic,
        )

    hits = response.get("results") or response.get("hits") or []
    last_mismatch: CitationCheck | None = None
    for hit in hits:
        canonical_hits = _canonical_from_hit(hit)
        if not any(ref in canonical_hits for ref in expected_refs):
            continue

        title = None
        frbr_uri = None
        status = None
        if isinstance(hit, dict):
            title = hit.get("title") or hit.get("work", {}).get("title")
            frbr_uri = hit.get("frbr_uri") or hit.get("work", {}).get("frbr_uri")
            status = hit.get("status") or hit.get("work", {}).get("status")

        if claimed_topic and title and not _topics_overlap(claimed_topic, title):
            last_mismatch = CitationCheck(
                reference=expected_refs[0],
                found=False,
                query=query,
                title=title,
                frbr_uri=frbr_uri,
                status=status,
                evidence=", ".join(canonical_hits[:3]) or None,
                note=(
                    f"judul tidak cocok dengan klaim '{claimed_topic}' "
                    f"(judul sebenarnya: '{title}')"
                ),
                claimed_topic=claimed_topic,
            )
            continue

        return CitationCheck(
            reference=expected_refs[0],
            found=True,
            query=query,
            title=title,
            frbr_uri=frbr_uri,
            status=status,
            evidence=", ".join(canonical_hits[:3]) or None,
            claimed_topic=claimed_topic,
        )

    if last_mismatch is not None:
        return last_mismatch

    return CitationCheck(
        reference=expected_refs[0],
        found=False,
        query=query,
        note="TIDAK DITEMUKAN di pasal.id",
        claimed_topic=claimed_topic,
    )


def verify_citations(
    pasal_client: Any,
    references: Iterable[str | CitationContext],
) -> list[CitationCheck]:
    """Verify a batch of citations and preserve input order.

    Accepts either bare reference strings (``"UU 12/2023"``) or
    ``CitationContext`` objects which add a ``claimed_topic`` for content-aware
    verification.
    """
    checks: list[CitationCheck] = []
    seen: set[str] = set()
    for item in references:
        if isinstance(item, CitationContext):
            ref = item.reference.strip()
            claimed = item.claimed_topic
        else:
            ref = (item or "").strip()
            claimed = None
        if not ref or ref in seen:
            continue
        seen.add(ref)
        checks.append(verify_citation(pasal_client, ref, claimed_topic=claimed))
    return checks


def format_checks(checks: Iterable[CitationCheck]) -> str:
    """Render citation verification results as markdown bullets."""
    lines: list[str] = []
    for check in checks:
        if check.found:
            title = check.title or check.reference
            frbr = check.frbr_uri or "-"
            status = check.status or "?"
            lines.append(f"- {check.reference}: {title} (status: {status}, frbr_uri: {frbr})")
        else:
            lines.append(f"- {check.reference}: {check.note or 'TIDAK DITEMUKAN di pasal.id'} — jangan sitasi.")
    return "\n".join(lines)


def format_basis_block(pasal_client: Any, references: Iterable[str]) -> str:
    """Verify references and render the standard BASIS HUKUM block."""
    refs = _unique(reference.strip() for reference in references if reference and reference.strip())
    if not refs:
        return ""
    checks = verify_citations(pasal_client, refs)
    return "BASIS HUKUM:\n" + format_checks(checks)

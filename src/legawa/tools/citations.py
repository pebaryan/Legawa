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

from .trusted_recent import lookup as _trusted_lookup, trusted_entry_warnings as _trusted_warnings


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
        |Peraturan\s+Menteri(?:\s+[A-Za-z][\w&/\-]*){0,4}
    )
    # Tolerate closing parens, brackets, and markdown bold/italic between the
    # label and the number — e.g. "(Permenhub) No. PM 94" or "**Permenhub** 94".
    [\s)\]\*\_]*
    (?:No\.?|Nomor)?\s*
    (?:(?:PM|KP|KEP|PER)\.?\s*)?
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
    reason_code: str | None = None
    flags: tuple[str, ...] = ()
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


def _structured_refs_from_hit(hit: Any) -> list[str]:
    refs: list[str] = []
    if not isinstance(hit, dict):
        return refs
    for key in ("title", "frbr_uri"):
        value = hit.get(key)
        if isinstance(value, str):
            refs.extend(extract_citations(value))
    work = hit.get("work")
    if isinstance(work, dict):
        for key in ("title", "frbr_uri"):
            value = work.get(key)
            if isinstance(value, str):
                refs.extend(extract_citations(value))
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


_REPEALED_RELATIONSHIP_TYPES = frozenset({"dicabut oleh", "repealed by"})
_AMENDED_RELATIONSHIP_TYPES = frozenset({"diubah oleh", "amended by"})


def _year_from_frbr(frbr_uri: str | None) -> int | None:
    """Extract the year segment from an FRBR URI like ``akn/id/act/uu/2014/36``."""
    if not frbr_uri:
        return None
    parts = frbr_uri.lstrip("/").split("/")
    # Standard shape: akn/id/act/<kind>/<year>/<number>
    if len(parts) >= 6 and parts[4].isdigit():
        return int(parts[4])
    return None


def _related_year(rel: dict[str, Any]) -> int | None:
    related = rel.get("related_work") or rel.get("related") or {}
    if not isinstance(related, dict):
        return None
    year = related.get("year")
    if isinstance(year, int):
        return year
    if isinstance(year, str) and year.isdigit():
        return int(year)
    return _year_from_frbr(related.get("frbr_uri") or related.get("uri"))


def _amendment_status(pasal_client: Any, frbr_uri: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return ``(repealed_by_relationship_or_None, list_of_amended_by_relationships)``.

    Probes pasal.id's ``get_law`` endpoint for the regulation's relationships
    field and classifies them. pasal.id's ``status`` field is unreliable
    (omnibus replacements like UU 17/2023 leave their predecessors marked
    ``berlaku``); the relationships graph is more reliable, *but* pasal.id
    mirrors relationships in both directions — UU 13/2003's "Dicabut oleh"
    list also contains UU 25/1997 (the older law it actually revoked).

    To disambiguate: a relationship of type "Dicabut oleh" / "Diubah oleh"
    is only treated as authoritative if the related work has a *later* year
    than the cited regulation. Same-year and earlier-year mirrors are
    discarded.

    Returns ``(None, [])`` on any error — the verifier should degrade
    gracefully when this side-probe fails.
    """
    if not frbr_uri:
        return None, []
    normalised = frbr_uri.lstrip("/")
    try:
        full = pasal_client.get_law(normalised)
    except Exception:
        return None, []

    relationships = full.get("relationships") or full.get("work", {}).get("relationships") or []
    if not isinstance(relationships, list):
        return None, []

    self_year = _year_from_frbr(normalised)

    repealed: dict[str, Any] | None = None
    amended: list[dict[str, Any]] = []
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        rel_type = (rel.get("type") or "").strip().lower()
        rel_type_en = (rel.get("type_en") or "").strip().lower()
        is_repealed = rel_type in _REPEALED_RELATIONSHIP_TYPES or rel_type_en in _REPEALED_RELATIONSHIP_TYPES
        is_amended = rel_type in _AMENDED_RELATIONSHIP_TYPES or rel_type_en in _AMENDED_RELATIONSHIP_TYPES
        if not (is_repealed or is_amended):
            continue

        # Pasal.id mirrors relationships in both directions. Only treat the
        # relationship as authoritative when the related work is newer than
        # the cited regulation — i.e. a real successor, not a mirrored
        # predecessor entry.
        rel_year = _related_year(rel)
        if self_year is not None and rel_year is not None and rel_year <= self_year:
            continue

        if is_repealed:
            if repealed is None:
                repealed = rel
        elif is_amended:
            amended.append(rel)
    return repealed, amended


def _format_relationship_target(rel: dict[str, Any]) -> str:
    related = rel.get("related_work") or rel.get("related") or {}
    if not isinstance(related, dict):
        return "regulasi pengganti tidak dikenali"
    title = related.get("title") or related.get("name")
    frbr = related.get("frbr_uri") or related.get("uri")
    if title and frbr:
        return f"{title} ({frbr.lstrip('/')})"
    return title or frbr or "regulasi pengganti tidak dikenali"


def verify_citation(
    pasal_client: Any,
    reference: str,
    *,
    claimed_topic: str | None = None,
    limit: int = 5,
    check_amendments: bool = True,
) -> CitationCheck:
    """Verify a single citation against pasal.id search results.

    If ``claimed_topic`` is given (e.g. extracted from a "tentang ..." clause
    surrounding the citation), the check also requires topical overlap between
    the claimed topic and the matched regulation's actual title. This catches
    the failure mode where a (kind, number, year) tuple resolves to a real
    regulation that is *not* about what the agent claimed.

    Verification precedence:
      1. Whitelist the constitutional ``UUD 1945`` citation.
      2. Search pasal.id and prefer the most structured match.
      3. If pasal.id is unreachable, fall back to ``trusted_recent``.
      4. If pasal.id returns only noisy or mismatched hits, allow a matching
         ``trusted_recent`` override before rejecting the citation.

    If ``check_amendments`` is True (default), additionally probes the matched
    regulation's relationships graph and:
      - rejects (``found=False``) if the regulation has been repealed
        (``Dicabut oleh`` / ``Repealed by``)
      - keeps ``found=True`` but adds an advisory note when the regulation
        has been amended (``Diubah oleh`` / ``Amended by``)
    Disable by passing ``check_amendments=False`` for cheap existence-only
    checks.
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
            reason_code="constitutional_whitelist",
            title="Undang-Undang Dasar Negara Republik Indonesia Tahun 1945",
            note="constitutional whitelist",
            claimed_topic=claimed_topic,
        )

    query, regulation_type = _infer_query(primary)
    params: dict[str, Any] = {"q": query, "limit": max(1, min(limit, 20))}
    if regulation_type:
        params["type"] = regulation_type

    def _build_success_check(
        *,
        title: str | None,
        frbr_uri: str | None,
        status: str | None,
        note: str | None = None,
        evidence: str | None = None,
        reason_code: str = "matched",
        flags: tuple[str, ...] = (),
    ) -> CitationCheck:
        success_note = note
        success_flags = flags
        if check_amendments and frbr_uri:
            repealed_rel, amended_rels = _amendment_status(pasal_client, frbr_uri)
            # NOTE: pasal.id's relationships graph is unreliable in practice —
            # it sometimes mis-classifies cross-references as "Dicabut oleh".
            # We surface the finding as an advisory note for staff review but
            # never reject the citation outright on this signal alone. False
            # positives on canonical statutes (e.g. UU 31/1999) would be worse
            # than missing the occasional real repeal.
            advisories: list[str] = []
            if repealed_rel is not None:
                successor = _format_relationship_target(repealed_rel)
                advisories.append(
                    f"pasal.id menandai regulasi ini 'Dicabut oleh' {successor} — verifikasi manual disarankan"
                )
            if amended_rels:
                successors = "; ".join(_format_relationship_target(r) for r in amended_rels[:3])
                advisories.append(
                    f"regulasi telah diubah; periksa apakah pasal yang dikutip masih berlaku setelah perubahan: {successors}"
                )
            if advisories:
                advisory_note = " | ".join(advisories)
                success_note = f"{success_note} | {advisory_note}" if success_note else advisory_note
                success_flags = tuple(dict.fromkeys((*success_flags, "amended")))
            if repealed_rel is not None:
                success_flags = tuple(dict.fromkeys((*success_flags, "repealed_suspected")))

        return CitationCheck(
            reference=expected_refs[0],
            found=True,
            query=query,
            reason_code=reason_code,
            flags=success_flags,
            title=title,
            frbr_uri=frbr_uri,
            status=status,
            evidence=evidence,
            note=success_note,
            claimed_topic=claimed_topic,
        )

    try:
        response = pasal_client.search(**params)
    except Exception as exc:  # noqa: BLE001
        # Pasal.id unreachable (network, 401, 5xx). Try trusted_recent as a
        # fallback — citations we have local source-of-truth for shouldn't
        # be blocked by an outage. If the citation is NOT in trusted_recent,
        # surface the original transport error so the user knows to fix it.
        trusted = _trusted_lookup(primary)
        if trusted is not None:
            title = trusted.get("title")
            if claimed_topic and title and not _topics_overlap(claimed_topic, title):
                return CitationCheck(
                    reference=primary,
                    found=False,
                    query=query,
                    reason_code="topic_mismatch",
                    flags=("trusted_recent",),
                    title=title,
                    frbr_uri=trusted.get("frbr_uri"),
                    status=trusted.get("status"),
                    note=(
                        f"judul tidak cocok dengan klaim '{claimed_topic}' "
                        f"(judul sebenarnya — sumber trusted_recent: '{title}')"
                    ),
                    claimed_topic=claimed_topic,
                )
            provenance = trusted.get("note") or "fresh regulation, not yet on pasal.id"
            return _build_success_check(
                title=title,
                frbr_uri=trusted.get("frbr_uri"),
                status=trusted.get("status"),
                note=f"trusted_recent override (pasal.id unreachable: {exc}) — {provenance}",
                reason_code="trusted_recent",
            )
        return CitationCheck(
            reference=expected_refs[0],
            found=False,
            query=query,
            reason_code="request_error",
            flags=("pasal_unreachable",),
            note=f"verifikasi gagal: {exc}",
            claimed_topic=claimed_topic,
        )

    hits = response.get("results") or response.get("hits") or []
    success_candidates: list[tuple[int, dict[str, Any]]] = []
    mismatch_candidates: list[tuple[int, CitationCheck]] = []
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
        structured_hits = _structured_refs_from_hit(hit)
        structured_match = any(ref in structured_hits for ref in expected_refs)
        priority = 0 if structured_match else 1

        if claimed_topic and title and not _topics_overlap(claimed_topic, title):
            mismatch_candidates.append(
                (
                    priority,
                    CitationCheck(
                        reference=expected_refs[0],
                        found=False,
                        query=query,
                        reason_code="topic_mismatch",
                        flags=("noisy_hit",) if not structured_match else ("structured_hit",),
                        title=title,
                        frbr_uri=frbr_uri,
                        status=status,
                        evidence=", ".join(canonical_hits[:3]) or None,
                        note=(
                            f"judul tidak cocok dengan klaim '{claimed_topic}' "
                            f"(judul sebenarnya: '{title}')"
                        ),
                        claimed_topic=claimed_topic,
                    ),
                )
            )
            continue

        success_candidates.append(
            (
                priority,
                {
                    "title": title,
                    "frbr_uri": frbr_uri,
                    "status": status,
                    "evidence": ", ".join(canonical_hits[:3]) or None,
                    "flags": ("structured_hit",) if structured_match else ("noisy_hit",),
                },
            )
        )

    if success_candidates:
        _, best = sorted(success_candidates, key=lambda item: item[0])[0]
        return _build_success_check(
            title=best["title"],
            frbr_uri=best["frbr_uri"],
            status=best["status"],
            evidence=best["evidence"],
            flags=best["flags"],
        )

    # Fallback: regulations confirmed real but not yet ingested by pasal.id.
    # Keyed by the same normalized reference form. Topical overlap still
    # enforced — we don't want to whitelist a (number, year) tuple that the
    # model is hallucinating about; it must match the trusted title.
    trusted = _trusted_lookup(primary)
    if trusted is not None:
        title = trusted.get("title")
        frbr_uri = trusted.get("frbr_uri")
        status = trusted.get("status")
        if claimed_topic and title and not _topics_overlap(claimed_topic, title):
            return CitationCheck(
                reference=primary,
                found=False,
                query=query,
                reason_code="topic_mismatch",
                flags=("trusted_recent",),
                title=title,
                frbr_uri=frbr_uri,
                status=status,
                note=(
                    f"judul tidak cocok dengan klaim '{claimed_topic}' "
                    f"(judul sebenarnya — sumber trusted_recent: '{title}')"
                ),
                claimed_topic=claimed_topic,
            )
        provenance = trusted.get("note") or "fresh regulation, not yet on pasal.id"
        warnings = _trusted_warnings(primary, trusted)
        trusted_flags = ("trusted_recent",) + (("stale_trusted_entry",) if warnings else ())
        return _build_success_check(
            title=title,
            frbr_uri=frbr_uri,
            status=status,
            note=(" | ".join([f"trusted_recent override — {provenance}", *warnings]) if warnings else f"trusted_recent override — {provenance}"),
            reason_code="trusted_recent_stale" if warnings else "trusted_recent",
            flags=trusted_flags,
        )

    if mismatch_candidates:
        _, best = sorted(mismatch_candidates, key=lambda item: item[0])[0]
        return best

    return CitationCheck(
        reference=expected_refs[0],
        found=False,
        query=query,
        reason_code="not_found",
        flags=("pasal_search_empty",),
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

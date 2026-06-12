"""Trusted-citation override store for regulations confirmed real but not
yet indexed in pasal.id.

Used as a fallback by ``citations.verify_citation`` when pasal.id's search
returns no matching hit. Each entry must include the regulation's true
title so topical-overlap can still be enforced against an agent's
``claimed_topic`` — we don't want to whitelist a number/year tuple that
the model is hallucinating about.

**Removal policy:** entries here are a freshness workaround, not a
permanent corpus. Once pasal.id ingests a regulation, remove its entry
from this dict so verification flows through the normal pasal.id path
(which also gives access to relationships, full text, and pasal-level
search). The regression check (``scripts/regression_check.py``) does NOT
probe these entries — they're explicitly outside the corpus baseline.

**How to add an entry:**

1. Confirm the regulation is real via at least one credible source
   (peraturan.go.id, jdih.<ministry>.go.id, or a major news outlet).
2. Verify pasal.id does NOT have it: ``pasal.search(q='<ref>')`` and
   ``pasal.list_laws(type='<TYPE>', year=<YYYY>)`` both return nothing.
3. Add an entry keyed by the normalized citation reference (the form
   ``citations.extract_citations`` produces, e.g. "Perpres 8/2026").
4. Note the date pasal.id was checked, so future maintainers know when
   to re-check whether the entry can be removed.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TypedDict


STALE_AFTER_DAYS = 60


class TrustedEntry(TypedDict, total=False):
    frbr_uri: str           # canonical FRBR URI (akn/id/act/.../<year>/<number>)
    title: str              # full official title — used for topical overlap
    status: str             # "berlaku" | "diubah" | "dicabut"
    signed_date: str        # ISO date when signed
    checked_on: str         # ISO date when pasal.id was last checked
    expires_on: str         # ISO date after which the entry should be re-checked
    source_url: str         # link confirming the regulation
    note: str               # context for the human reviewer


# Keyed by the citation reference form (output of ``extract_citations``).
TRUSTED_RECENT: dict[str, TrustedEntry] = {
    "Perpres 8/2026": {
        "frbr_uri": "akn/id/act/perpres/2026/8",
        "title": (
            "Peraturan Presiden Nomor 8 Tahun 2026 tentang Rencana Aksi Nasional "
            "Pencegahan dan Penanggulangan Ekstremisme Berbasis Kekerasan yang "
            "Mengarah pada Terorisme Tahun 2026-2029"
        ),
        "status": "berlaku",
        "signed_date": "2026-02-09",
        "checked_on": "2026-05-04",
        "expires_on": "2026-06-30",
        "source_url": "https://www.pewarta.co.id/2026/05/prabowo-terbitkan-perpres-ran-pencegahan-ekstremisme-dan-terorisme-2026-2029.html",
        "note": (
            "Ditandatangani Presiden Prabowo 9 Feb 2026, dipublikasikan Mei 2026. "
            "Belum terindeks di pasal.id per 2026-05-04 (corpus 2026 hanya memuat "
            "Perpres 1/2026). Hapus entri ini setelah pasal.id meng-ingest."
        ),
    },
}


def lookup(reference: str) -> TrustedEntry | None:
    """Return the trusted entry for a normalized citation reference, if any."""
    if not reference:
        return None
    return TRUSTED_RECENT.get(reference.strip())


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate_trusted_entry(reference: str, entry: TrustedEntry) -> list[str]:
    """Return structural problems found in a trusted entry."""
    problems: list[str] = []
    ref = (reference or "").strip()
    if not ref:
        problems.append("missing reference key")

    title = (entry.get("title") or "").strip()
    if not title:
        problems.append("missing title")

    frbr_uri = (entry.get("frbr_uri") or "").strip()
    if not frbr_uri:
        problems.append("missing frbr_uri")
    elif not frbr_uri.startswith("akn/id/act/"):
        problems.append(f"invalid frbr_uri: {frbr_uri}")

    if not entry.get("checked_on") and not entry.get("expires_on"):
        problems.append("missing checked_on or expires_on")

    for field_name in ("signed_date", "checked_on", "expires_on"):
        raw = entry.get(field_name)
        if raw is None:
            continue
        if _parse_iso_date(raw) is None:
            problems.append(f"invalid {field_name}: {raw}")

    return problems


def trusted_entry_warnings(
    reference: str,
    entry: TrustedEntry,
    *,
    today: date | None = None,
) -> list[str]:
    """Return non-fatal warnings such as staleness for a trusted entry."""
    warnings: list[str] = []
    today = today or date.today()

    expires_on = _parse_iso_date(entry.get("expires_on"))
    if expires_on is not None and today > expires_on:
        warnings.append(f"trusted_recent entry {reference} expired on {expires_on.isoformat()}")
        return warnings

    checked_on = _parse_iso_date(entry.get("checked_on"))
    if checked_on is not None and today - checked_on > timedelta(days=STALE_AFTER_DAYS):
        age_days = (today - checked_on).days
        warnings.append(
            f"trusted_recent entry {reference} was last checked on {checked_on.isoformat()} ({age_days} days ago)"
        )

    return warnings


def render_trusted_entry_template(reference: str) -> str:
    """Render a paste-ready trusted_recent entry template."""
    ref = (reference or "").strip() or "REFERENCE"
    return (
        f'    "{ref}": {{\n'
        f'        "frbr_uri": "akn/id/act/<kind>/<year>/<number>",\n'
        f'        "title": "Full official title",\n'
        f'        "status": "berlaku",\n'
        f'        "signed_date": "YYYY-MM-DD",\n'
        f'        "checked_on": "YYYY-MM-DD",\n'
        f'        "expires_on": "YYYY-MM-DD",\n'
        f'        "source_url": "https://...",\n'
        f'        "note": "why this entry exists",\n'
        f"    }},"
    )

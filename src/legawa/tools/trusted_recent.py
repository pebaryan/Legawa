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

from typing import TypedDict


class TrustedEntry(TypedDict, total=False):
    frbr_uri: str           # canonical FRBR URI (akn/id/act/.../<year>/<number>)
    title: str              # full official title — used for topical overlap
    status: str             # "berlaku" | "diubah" | "dicabut"
    signed_date: str        # ISO date when signed
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

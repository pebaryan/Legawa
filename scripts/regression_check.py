"""Regression check for legawa's pasal.id corpus dependencies.

Run periodically (suggested 3-week cadence) to detect drift in:
- Canonical probe URIs in agents/peneliti._CANONICAL_PROBES — pasal.id may add
  new "Dicabut oleh" / "Diubah oleh" relationships, change titles, or change
  status as the corpus evolves.
- Fixture-cited regulations across tests/fixtures/*.txt — if a citation in a
  fixture changes, this catches it.

Operational caveat: this script does NOT re-run the live agents (which depend
on the user's local llama.cpp endpoints and the user's pasal.id token). It
only validates the static corpus dependencies the agents rely on. The user
still needs to manually re-run `legawa surat / research / draft` against the
fixtures to validate end-to-end behaviour after any model swap.

Usage:
    python scripts/regression_check.py                    # compare against baseline, exit 1 on drift
    python scripts/regression_check.py --update-baseline  # snapshot current state as the new baseline
    python scripts/regression_check.py --json             # machine-readable output

Environment:
    PASAL_API_TOKEN must be set (loaded via legawa.config.load_settings).

Exit codes:
    0 — no drift
    1 — drift detected (review output, decide if expected; rerun with
        --update-baseline if changes are intentional)
    2 — runtime error (network, missing token, etc.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.agents.peneliti import _CANONICAL_PROBES  # noqa: E402
from legawa.config import load_settings  # noqa: E402
from legawa.tools.cache import CachingPasalClient  # noqa: E402
from legawa.tools.citations import _amendment_status, extract_citations  # noqa: E402
from legawa.tools.pasal import PasalClient  # noqa: E402
from legawa.tools.trusted_recent import (  # noqa: E402
    TRUSTED_RECENT,
    trusted_entry_warnings,
    validate_trusted_entry,
)


BASELINE_PATH = Path(__file__).resolve().parent / "regression_baseline.json"
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def _format_rel(rel: dict[str, Any] | None) -> dict[str, str] | None:
    if not rel:
        return None
    related = rel.get("related_work") or rel.get("related") or {}
    if not isinstance(related, dict):
        return None
    return {
        "title": (related.get("title") or "")[:120],
        "frbr_uri": related.get("frbr_uri") or "?",
    }


def _probe_uri(pasal: Any, uri: str) -> dict[str, Any]:
    try:
        law = pasal.get_law(uri)
    except Exception as exc:  # noqa: BLE001
        return {"uri": uri, "error": str(exc)[:200]}

    work = law.get("work") if isinstance(law, dict) else {}
    title = (law.get("title") if isinstance(law, dict) else None) or (
        work.get("title") if isinstance(work, dict) else None
    )
    status = (law.get("status") if isinstance(law, dict) else None) or (
        work.get("status") if isinstance(work, dict) else None
    )

    repealed, amended = _amendment_status(pasal, uri)
    return {
        "uri": uri,
        "title": (title or "?")[:120],
        "status": status or "?",
        "repealed_by": _format_rel(repealed),
        "amended_by": [_format_rel(r) for r in amended[:5]],
    }


def _collect_canonical_uris() -> list[str]:
    seen: list[str] = []
    for _keywords, uri in _CANONICAL_PROBES:
        if uri not in seen:
            seen.append(uri)
    return seen


def _collect_fixture_citations() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fixture in sorted(FIXTURES_DIR.glob("*.txt")):
        text = fixture.read_text(encoding="utf-8")
        cites = extract_citations(text)
        if cites:
            out[fixture.name] = cites
    return out


def _collect_trusted_recent() -> dict[str, Any]:
    entries: dict[str, Any] = {}
    problems: list[str] = []
    warnings: list[str] = []
    for reference, entry in sorted(TRUSTED_RECENT.items()):
        entry_problems = validate_trusted_entry(reference, entry)
        if entry_problems:
            problems.extend(f"{reference}: {problem}" for problem in entry_problems)
        entry_warnings = trusted_entry_warnings(reference, entry)
        if entry_warnings:
            warnings.extend(f"{reference}: {warning}" for warning in entry_warnings)
        entries[reference] = {
            "title": entry.get("title") or "?",
            "frbr_uri": entry.get("frbr_uri") or "?",
            "status": entry.get("status") or "?",
            "checked_on": entry.get("checked_on") or "?",
            "expires_on": entry.get("expires_on") or "?",
        }
    return {
        "entries": entries,
        "problems": problems,
        "warnings": warnings,
    }


def _build_report(pasal: Any) -> dict[str, Any]:
    uris = _collect_canonical_uris()
    probes = {uri: _probe_uri(pasal, uri) for uri in uris}
    return {
        "schema_version": 1,
        "canonical_probes": probes,
        "fixture_citations": _collect_fixture_citations(),
        "trusted_recent": _collect_trusted_recent(),
    }


def _diff(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    drift: dict[str, Any] = {
        "probe_changes": [],
        "fixture_added": {},
        "fixture_removed": {},
    }

    base_probes = baseline.get("canonical_probes", {})
    cur_probes = current.get("canonical_probes", {})
    for uri in sorted(set(base_probes) | set(cur_probes)):
        before = base_probes.get(uri)
        after = cur_probes.get(uri)
        if before != after:
            drift["probe_changes"].append({"uri": uri, "before": before, "after": after})

    base_fix = baseline.get("fixture_citations", {})
    cur_fix = current.get("fixture_citations", {})
    for name in sorted(set(base_fix) | set(cur_fix)):
        before = set(base_fix.get(name, []))
        after = set(cur_fix.get(name, []))
        added = sorted(after - before)
        removed = sorted(before - after)
        if added:
            drift["fixture_added"][name] = added
        if removed:
            drift["fixture_removed"][name] = removed

    return drift


def _has_drift(d: dict[str, Any]) -> bool:
    return bool(d["probe_changes"] or d["fixture_added"] or d["fixture_removed"])


def main(argv: list[str]) -> int:
    update = "--update-baseline" in argv
    as_json = "--json" in argv

    try:
        settings = load_settings()
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    pasal = CachingPasalClient(PasalClient(settings))
    try:
        report = _build_report(pasal)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: probe error: {exc}", file=sys.stderr)
        return 2
    finally:
        pasal.close()

    if update:
        BASELINE_PATH.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Baseline updated: {BASELINE_PATH.relative_to(ROOT)}")
        print(
            f"  canonical_probes: {len(report['canonical_probes'])}  "
            f"fixture_citations: {sum(len(v) for v in report['fixture_citations'].values())} refs "
            f"across {len(report['fixture_citations'])} fixtures"
        )
        return 0

    if not BASELINE_PATH.exists():
        print(
            f"No baseline at {BASELINE_PATH.relative_to(ROOT)}. "
            "Run with --update-baseline to create one.",
            file=sys.stderr,
        )
        return 2

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    drift = _diff(baseline, report)
    trusted = report.get("trusted_recent", {})
    trusted_problems = trusted.get("problems", [])
    trusted_warnings = trusted.get("warnings", [])

    if as_json:
        print(json.dumps(drift, indent=2, ensure_ascii=False))
    else:
        for warning in trusted_warnings:
            print(f"WARN: {warning}")
        if trusted_problems:
            print("INVALID trusted_recent entries:")
            for problem in trusted_problems:
                print(f"  - {problem}")
        if not _has_drift(drift):
            print(
                f"OK: no drift across {len(report['canonical_probes'])} canonical probes "
                f"and {sum(len(v) for v in report['fixture_citations'].values())} fixture refs."
            )
        else:
            print("DRIFT detected:")
            for change in drift["probe_changes"]:
                print(f"  probe: {change['uri']}")
                print(f"    before: {json.dumps(change['before'], ensure_ascii=False)[:160]}")
                print(f"    after : {json.dumps(change['after'], ensure_ascii=False)[:160]}")
            for fixture, refs in drift["fixture_added"].items():
                print(f"  + {fixture}: added {refs}")
            for fixture, refs in drift["fixture_removed"].items():
                print(f"  - {fixture}: removed {refs}")
            print(
                "\nIf the changes are expected (e.g. you intentionally added a "
                "canonical probe or a fixture citation), regenerate the baseline:\n"
                "    python scripts/regression_check.py --update-baseline"
            )

    if trusted_problems:
        if as_json:
            for problem in trusted_problems:
                print(f"INVALID trusted_recent entry: {problem}", file=sys.stderr)
        return 2
    return 0 if not _has_drift(drift) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

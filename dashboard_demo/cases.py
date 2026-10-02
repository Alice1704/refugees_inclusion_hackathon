"""Read-only access to the case assets that live beside this project.

The dashboard renders two artefacts per case, both produced upstream by the
pipeline:

* ``assets/contexts/record-<id>.json``      - external variables behind the call
* ``assets/outputs/cashy-record-<id>.json`` - Cashy's eligibility and reasoning

Two quirks of the source data are absorbed here so the browser never sees them:

1. Record 004 stores the decision under ``decision``; 324 and 889 use ``target``.
   Both carry the same ``eligibility_target`` / ``eligibility_status`` fields.
2. The scorecard and Cashy can disagree (record 889 is excluded by the
   scorecard's duplicate flag but included by Cashy). This module exposes
   Cashy's output only, which is what the review UI presents.
"""

from __future__ import annotations

import json
from pathlib import Path

# Resolved from this file so the app does not depend on the working directory.
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
CONTEXTS_DIR = ASSETS_DIR / "contexts"
OUTPUTS_DIR = ASSETS_DIR / "outputs"

# Display labels and value kinds for the context checklist. The order here is the
# order rendered, and any key missing from this map is skipped rather than
# rendered unlabelled.
CONTEXT_FIELDS = (
    ("origin_country_conflict", "Origin country in active conflict", "boolean"),
    ("security_exposure", "Security exposure", "text"),
    ("displacement_stage", "Displacement stage", "text"),
    ("sex_or_sexuality_discrimination", "Sex or sexuality discrimination", "boolean"),
    ("activism_exposure", "Activism exposure", "boolean"),
    ("interpretation_available", "Interpreter available", "boolean"),
    ("budget_places_available", "Budget places available", "number"),
    ("budget_places_assigned", "Budget places assigned", "number"),
)


class CaseNotFound(Exception):
    """Raised when no context file exists for the requested record id."""


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _context_path(record_id: int) -> Path:
    return CONTEXTS_DIR / f"record-{record_id:03d}.json"


def _cashy_path(record_id: int) -> Path:
    return OUTPUTS_DIR / f"cashy-record-{record_id:03d}.json"


def available_record_ids() -> list[int]:
    """Record ids that have a context file, ascending."""
    ids = []
    for path in CONTEXTS_DIR.glob("record-*.json"):
        stem = path.stem.removeprefix("record-")
        if stem.isdigit():
            ids.append(int(stem))
    return sorted(ids)


def _build_variables(raw: dict) -> list[dict]:
    variables = []
    for key, label, kind in CONTEXT_FIELDS:
        if key not in raw:
            continue
        variables.append({"key": key, "label": label, "kind": kind, "value": raw[key]})
    return variables


def list_cases() -> list[dict]:
    """Summary rows for the case selector."""
    cases = []
    for record_id in available_record_ids():
        try:
            context = _read_json(_context_path(record_id))
        except (OSError, ValueError):
            continue
        cases.append(
            {
                "record_id": record_id,
                "month": context.get("month"),
                "office": context.get("office"),
            }
        )
    return cases


def load_case(record_id: int) -> dict:
    """Normalised detail payload for one case.

    Raises CaseNotFound when the context file is absent, so the route can
    answer 404 rather than serving a half-populated record.
    """
    context_path = _context_path(record_id)
    if not context_path.is_file():
        raise CaseNotFound(record_id)

    context = _read_json(context_path)

    # Cashy's output carries the eligibility and the reasoning. It is optional:
    # a case can be reviewed on its context alone if the model output is missing.
    eligibility = {"target": None, "status": None}
    analysis = None
    cashy_path = _cashy_path(record_id)
    if cashy_path.is_file():
        cashy = _read_json(cashy_path)
        # `decision` in record 004, `target` in the others.
        decision = cashy.get("decision") or cashy.get("target") or {}
        eligibility = {
            "target": decision.get("eligibility_target"),
            "status": decision.get("eligibility_status"),
        }
        analysis = cashy.get("analysis")

    return {
        "record_id": record_id,
        "month": context.get("month"),
        "office": context.get("office"),
        # Only the external variables are exposed; the free-text case context is
        # deliberately left out of the payload since the review UI does not show it.
        "variables": _build_variables(context.get("external_variables") or {}),
        "eligibility": eligibility,
        "analysis": analysis,
    }

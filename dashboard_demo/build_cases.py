# Regenerate the case assets from the dataset. Run from this directory:
#
#     python build_cases.py
#
# This script was made completely by an AI model

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import marshmallow

from models import context as context_schema
from models import scoreboard as output_schema

ROOT = Path(__file__).resolve().parent.parent


DATASET = ROOT / "assets" / "datasets" / "S8.synthetic_cashy_sample.csv"
OUTPUTS_DIR = ROOT / "assets" / "outputs"
CONTEXTS_DIR = ROOT / "assets" / "contexts"

# How far apart the two texts are, from the rows Elegibilidad. same facts in
# other words, some of the same facts with a hedged conclusion, or the form
# excluding on an administrative flag Cashy never sees and therefore reasons
# from need alone.
LEVELS = {
    "Elegible": "similar",
    "No Elegible": "similar",
    "Elegible por Proceso Acelerado": "partial",
    "Lista de Reserva": "partial",
    "No Elegible por Intenciones": "different",
    "No Elegible por Duplicidad": "different",
}


# Four rows per level, twelve records. a curated subset rather than the whole
# sample: the dashboard is read one case at a time and the set has to keep the
# three levels apart or the calibrated thresholds say nothing. random but seeded,
# same twelve rows every run.
PER_LEVEL = 4
SEED = 0

VULNERABILITY = {
    "Vulnerabilidad Baja": "low",
    "Vulnerabilidad Moderada": "moderate",
    "Vulnerabilidad Elevada": "high",
    "Vulnerabilidad Severa": "severe",
}
# where Cashy reasons from need alone, and what need alone supports
NEED_ALONE = ("Vulnerabilidad Elevada", "Vulnerabilidad Severa")

# the two conclusions per level: what the interviewer lands on, and what Cashy
# lands on when the texts are similar or only partial. None marks the flag hidden
# cases, where Cashy has no conclusion to state from the form.
VERDICTS = {
    "Elegible": (
        "The household meets the criteria and should be included.",
        "Taken together, this supports including the household.",
    ),
    "No Elegible": (
        "The household does not meet the criteria and should be excluded.",
        "Taken together, this does not support including the household.",
    ),
    "Elegible por Proceso Acelerado": (
        "The urgency of the case allows the accelerated process, so the household should be included.",
        "The needs look pressing enough that I would put the household forward for inclusion.",
    ),
    "Lista de Reserva": (
        "No place is left this month, so the household goes on the waiting list.",
        "The household qualifies in principle, but I would hold it on the waiting list until a place opens.",
    ),
    "No Elegible por Intenciones": (
        "An intentions flag was raised on the form, so the household is excluded whatever its needs.",
        None,
    ),
    "No Elegible por Duplicidad": (
        "A duplicate registration was found, so the household is excluded whatever its needs.",
        None,
    ),
}


NEED_VERDICTS = {
    "INCLUSION": "On need alone I would recommend including the household.",
    "EXCLUSION": "On need alone I would not recommend including the household.",
}

# security_exposure / displacement_stage, the only two external variables with a
# closed set, and the two that set how a month reads
EXPOSURE = ("low", "medium", "high")
STAGES = ("recent", "settled", "long_term")


# Dataset


def read_rows(path: Path = DATASET) -> list[dict]:
    # the sheet as shipped. row_number is 1-based, so record 4 is row 4.
    with path.open(encoding="utf-8") as handle:
        rows = []

        for number, row in enumerate(csv.DictReader(handle), start=1):
            row["row_number"] = number
            rows.append(row)
    return rows


def curate(rows: list[dict]) -> list[tuple[str, int]]:
    # (level, row_number) for the seeded sample, ascending by row number
    pools: dict[str, list[int]] = {
        level: [] for level in ("similar", "partial", "different")
    }
    for row in rows:
        if not row["Elegibilidad"] or not row["EligibilityTarget"]:

            continue
        pools[LEVELS[row["Elegibilidad"]]].append(row["row_number"])

    chosen = []
    for level, pool in pools.items():
        take = min(PER_LEVEL, len(pool))
        chosen += [(level, number) for number in random.Random(SEED).sample(pool, take)]
    return sorted(chosen, key=lambda item: item[1])


# The two texts, ported from judgement.ipynb


def clauses(row: dict) -> tuple[dict, dict]:
    # (facts both sides can state, extra points only cashys reasoning makes)
    members = int(row["NumIntegrantes"])
    vuln = VULNERABILITY[row["Vulnerability_Category"]]
    plural = members != 1
    pressure = float(row["NeedsandCoping_Score"])
    shared = {
        "size": (
            f"The household has {members} member{'s' if plural else ''}.",
            f"It is a household of {members} {'people' if plural else 'person'}.",
        ),
        "vulnerability": (
            f"Its vulnerability category is {vuln}, with a final score of {float(row['FinalScore']):.0f}.",
            f"The vulnerability assessment comes out {vuln} and the final score is {float(row['FinalScore']):.0f}.",
        ),
    }
    if row["CuidadorSolo"] == "si":
        shared["carer"] = (
            "A sole carer looks after the household.",
            "One adult carries all the caring responsibilities.",
        )
    if row["FemaleHeadedHousehold"] == "jefatura_femenina":
        shared["head"] = (
            "The household is female-headed.",
            "A woman heads the household.",
        )
    if row["HablaEspanol"] == "espanol_ningun_adulto":
        shared["language"] = (
            "No adult speaks Spanish.",
            "None of the adults can communicate in Spanish.",
        )
    if row["Analfabeta_si"] == "adultos_uno_mas_analfabeta":

        shared["literacy"] = (
            "At least one adult is illiterate.",
            "One or more adults cannot read or write.",
        )
    extras = {
        "needs": f"The pressure from needs and coping is "
        f"{'light' if pressure < 15 else 'moderate' if pressure < 30 else 'heavy'}.",
        "dependency": f"The dependency level in the household is {row['dependencyCategory']}.",
        "housing": f"Housing is {'precarious' if float(row['Needs_and_Coping.Housing']) >= 2 else 'not a pressing problem'}.",
    }
    return shared, extras


def generate_pair(row: dict, number: int) -> dict:
    # the two texts and two decisions of one row. number seeds the choices, so a
    # row always gives the same pair.
    rng = random.Random(number)
    level = LEVELS[row["Elegibilidad"]]
    outcome = row["EligibilityTarget"]
    shared, extras = clauses(row)
    verdict_a, verdict_b = VERDICTS[row["Elegibilidad"]]

    interview_analysis = " ".join([a for a, _ in shared.values()] + [verdict_a])

    cashy_outcome = outcome
    cashy_status = row["Elegibilidad"]
    if level == "similar":  # same facts and conclusion, other words
        parts = [b for _, b in shared.values()] + [verdict_b]
    elif (
        level == "partial"
    ):  # a few shared facts, different emphasis, hedged conclusion

        parts = (
            [b for _, b in list(shared.values())[:2]]
            + rng.sample(list(extras.values()), 2)
            + [verdict_b]
        )
    else:  # the flag is invisible to cashy, it reasons from need alone
        cashy_outcome = (
            "INCLUSION" if row["Vulnerability_Category"] in NEED_ALONE else "EXCLUSION"
        )
        cashy_status = "Elegible"
        parts = list(extras.values()) + [NEED_VERDICTS[cashy_outcome]]

    return {
        "level": level,
        "scorecard": {
            "eligibility_target": outcome,
            "eligibility_status": row["Elegibilidad"],
            "analysis": interview_analysis,
        },
        "cashy": {
            "eligibility_target": cashy_outcome,
            "eligibility_status": cashy_status,
            "analysis": " ".join(parts),
        },
    }


# Records


def _number(row: dict, column: str, default: float = 0.0) -> float:
    value = row[column]
    return float(value) if value not in ("", None) else default


# an administrative flag: a penalty, a zero, or blank meaning not assessed
def _flag(row: dict, column: str) -> int | None:
    value = row[column]
    if value in ("", None):
        return None
    return int(float(value))


def _optional_flag_word(row: dict, column: str, yes: str, no: str) -> bool | None:
    value = row[column]
    if value == yes:
        return True
    if value == no:
        return False

    return None


def record_fields(row: dict) -> dict:
    # the blocks both records share, straight from the row. same values on both
    # sides: these are what the interview form recorded, so neither the
    # interviewer nor the model gets to change them.
    return {
        "record_id": row["row_number"],
        "interview": {
            "month": row["month"],
            "office": row["OficinaACNUR"] or None,
        },
        "household": {
            "size": int(row["NumIntegrantes"]),
            "dependency_category": row["dependencyCategory"],
            "female_headed": _optional_flag_word(
                row, "FemaleHeadedHousehold", "jefatura_femenina", "jefatura_masculina"
            ),
            "sole_carer": _optional_flag_word(row, "CuidadorSolo", "si", "no"),
            "spanish_spoken": row["HablaEspanol"] == "espanol_uno_mas_adultos",
            "adult_illiteracy": row["Analfabeta_si"] == "adultos_uno_mas_analfabeta",
        },
        "demographics": {
            "head_of_household": _number(row, "Demographics.HH.Head"),
            "language_barrier": _number(row, "Demographics.Language"),
            "specific_needs": _number(row, "Demographics.Profiles"),
            "documentation": _number(row, "Demographics.Documentation"),
            "score": _number(row, "Demographics_Score"),
        },
        "needs_and_coping": {
            "basic_needs": _number(row, "Needs_and_Coping.BasicNeeds"),
            "housing": _number(row, "Needs_and_Coping.Housing"),
            "negative_coping": _number(row, "Needs_and_Coping.Neg.mechanism"),
            "dependency": _number(row, "Needs_and_Coping.Dependency"),
            "score": _number(row, "NeedsandCoping_Score"),
        },
        "scores": {
            "final_score": _number(row, "FinalScore"),
            "vulnerability_index": _number(row, "Vulnerability_Score"),
            "vulnerability_category": row["Vulnerability_Category"],
        },
        "administrative_flags": {
            "asylum_procedure": _flag(row, "ScoreCOMAR_PIL"),
            "intentions": int(row["ScoreIntenciones"]),
            "duplicate": int(row["ScoreDuplicidad"]),
        },
    }


def build_records(row: dict) -> tuple[dict, dict, str | None]:
    # the scorecard and cashy records of one row, plus any flag filled in
    pair = generate_pair(row, row["row_number"])
    fields = record_fields(row)
    filled = reconcile_flags(fields, row)
    return (
        {
            **fields,
            "decision": {
                k: pair["scorecard"][k]
                for k in ("eligibility_target", "eligibility_status")
            },
            "analysis": pair["scorecard"]["analysis"],
        },
        {
            **fields,
            "decision": {
                k: pair["cashy"][k]
                for k in ("eligibility_target", "eligibility_status")
            },
            "analysis": pair["cashy"]["analysis"],
        },
        filled,
    )


# Context


def build_context(row: dict) -> dict:
    # the external variables behind one recommendation. none of these is on the
    # dataset, so they are synthesised deterministically from the record id. the
    # description is written from the variables rather than alongside them so
    # the two cant drift: the sentence attribution in the judgement engine reads
    # this text and it only means anything if it says what the variables say.
    record_id = row["row_number"]
    rng = random.Random(record_id)
    available = rng.randint(8, 24)
    assigned = rng.randint(1, available)
    exposure = rng.choice(EXPOSURE)
    stage = rng.choice(STAGES)

    external = {
        "budget_places_available": available,
        "budget_places_assigned": assigned,
        "origin_country_conflict": rng.random() < 0.35,
        "security_exposure": exposure,
        "displacement_stage": stage,
        "sex_or_sexuality_discrimination": rng.random() < 0.25,
        "activism_exposure": rng.random() < 0.15,
        "interpretation_available": rng.random() < 0.6,
    }

    spent = assigned >= available
    sentences = [
        f"{available} places were available in the month and {assigned} had already been assigned"
        + (
            ", which is why a household of this profile ends up on the waiting list rather than served."
            if spent
            else ", so places were still open when the case was processed."
        ),
        (
            "The origin country is in an active conflict area, so the case was treated as urgent."
            if external["origin_country_conflict"]
            else "The origin country is not in an active conflict area, so the case was not treated as urgent."
        ),
        f"Security exposure was recorded as {exposure} and the household was at the {stage} stage of displacement.",
        (
            "A risk of sex or sexuality discrimination was recorded on the file."
            if external["sex_or_sexuality_discrimination"]
            else "No sex or sexuality discrimination risk was recorded on the file."
        ),
        (
            "The household is known for activism, which the month treated as a risk."
            if external["activism_exposure"]
            else "No activism exposure was recorded against the household."
        ),
        (
            "An interpreter was available and used, and the household presented without visible distress."
            if external["interpretation_available"]
            else "No interpreter was available, and the household was seen without one."
        ),
        "The administrative flags are not part of this context: they belong to the scorecard, "
        "which is exactly why the model cannot weigh them.",
        "On this context the household reads as a "
        + (
            "high-urgency case where the budget is the binding constraint."
            if spent and external["origin_country_conflict"]
            else "stable, low-urgency case, and the budget is what actually decides it."
        ),
    ]

    return {
        "record_id": record_id,
        "month": row["month"],
        "office": row["OficinaACNUR"] or None,
        "description": " ".join(sentences),
        "external_variables": external,
    }


# Flag reconciliation


PENALTY = -500  # the datasets own penalty value

# Only the two exclusion labels. a row labelled "No Elegible por ..." states the
# flag was raised, so the penalty belongs on it. the accelerated label is left
# alone, PIL carries +500 as well as -500, so blank there means not assessed
# rather than a penalty the row forgot to apply.
FLAG_FOR_STATUS = {
    "No Elegible por Intenciones": ("ScoreIntenciones", "intentions"),
    "No Elegible por Duplicidad": ("ScoreDuplicidad", "duplicate"),
}


# Fill the penalty a rows own label says it carries. In the dataset only 2 of the
# 90 flag excluded rows apply the penalty their Elegibilidad names, the label and
# the score columns are close to independent. Reproduced as is, a generated record
# contradicts itself inside a single file: the analysis says an intentions flag
# was raised while intentions reads 0. Filled here instead, and the caller prints
# it, so the departure from the raw row is stated rather than hidden.
def reconcile_flags(fields: dict, row: dict) -> str | None:
    expected = FLAG_FOR_STATUS.get(row["Elegibilidad"])
    if expected is None:
        return None
    _, name = expected
    flags = fields["administrative_flags"]
    if flags[name] not in (None, 0):
        return None

    flags[name] = PENALTY

    return f"{name} filled with {PENALTY} (row reads {row[expected[0]] or 'blank'})"


# Write


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build() -> list[tuple[str, int]]:
    every_row = read_rows()

    rows = {row["row_number"]: row for row in every_row}
    chosen = curate(every_row)

    # validate everything before writing anything, so a rejected record cannot
    # leave the assets half updated
    built = []
    for level, number in chosen:
        row = rows[number]
        scorecard, cashy, filled = build_records(row)
        context = build_context(row)
        built.append((level, number, scorecard, cashy, context, filled))

    for level, number, scorecard, cashy, context, _ in built:
        for kind, raw in (("scorecard", scorecard), ("cashy", cashy)):
            try:
                output_schema.load(raw)
            except marshmallow.ValidationError as error:
                raise SystemExit(
                    f"record {number} {kind} does not satisfy the schema: {error.messages}"
                )
        try:
            context_schema.load(context)
        except marshmallow.ValidationError as error:
            raise SystemExit(
                f"context {number} does not satisfy the schema: {error.messages}"
            )

    keep = {number for _, number, _, _, _, _ in built}

    for path in sorted(OUTPUTS_DIR.glob("*-record-*.json")):
        if int(path.stem.rsplit("-", 1)[1]) not in keep:
            path.unlink()
    for path in sorted(CONTEXTS_DIR.glob("record-*.json")):
        if int(path.stem.rsplit("-", 1)[1]) not in keep:
            path.unlink()

    for level, number, scorecard, cashy, context, _ in built:
        write_json(OUTPUTS_DIR / f"scorecard-record-{number:03d}.json", scorecard)
        write_json(OUTPUTS_DIR / f"cashy-record-{number:03d}.json", cashy)
        write_json(CONTEXTS_DIR / f"record-{number:03d}.json", context)

    print(f"{len(built)} records written to {OUTPUTS_DIR} and {CONTEXTS_DIR}")
    for level, number in chosen:
        print(f"  {number:>4}  {level}")
    for _, number, _, _, _, filled in built:
        if filled:
            print(f"adjusted: record {number}: {filled}")
    return [(level, number) for level, number, _, _, _, _ in built]


if __name__ == "__main__":
    build()

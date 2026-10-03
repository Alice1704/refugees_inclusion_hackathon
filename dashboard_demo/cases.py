from __future__ import annotations

import json
from pathlib import Path

# Resolved from this file so the app doesnt depend on the cwd.
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
CONTEXTS_DIR = ASSETS_DIR / "contexts"
OUTPUTS_DIR = ASSETS_DIR/"outputs"

# Display labels + value kinds for the context checklist. This order is the
# render order, and a key missing from the map is skipped rather than shown
# unlabelled.
CONTEXT_FIELDS = (
    ( "origin_country_conflict" ,"Origin country in active conflict" ,"boolean" ) ,
    ("security_exposure","Security exposure" ,"text") ,
    ("displacement_stage", "Displacement stage", "text"),
    ("sex_or_sexuality_discrimination" , "Sex or sexuality discrimination","boolean"),
    ("activism_exposure","Activism exposure","boolean") ,
    ("interpretation_available" ,"Interpreter available","boolean"),
    ("budget_places_available", "Budget places available", "number"),
    ("budget_places_assigned" ,"Budget places assigned","number" ),
)

# How far apart the two texts were built to be, read back off the eligibility
#status the generator wrote. build_cases.py imports this rather than keeping
#its own copy, so a case's level on disk and the level calibration groups it
#under cant drift.
STATUS_LEVELS ={
    "Elegible": "similar",
    "No Elegible": "similar",
    "Elegible por Proceso Acelerado": "partial",
    "Lista de Reserva": "partial",
    "No Elegible por Intenciones": "different",
    "No Elegible por Duplicidad": "different",
}


class CaseNotFound(Exception):


    pass


def _read_json ( path :Path)->dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)



def _context_path ( record_id: int)-> Path :
    return CONTEXTS_DIR / f"record-{record_id:03d}.json"


def _cashy_path ( record_id :int) ->Path :
    return OUTPUTS_DIR/ f"cashy-record-{record_id:03d}.json"


def available_record_ids ()-> list [ int ]:


    # ids that have a context file, ascending
    ids = []
    for path in CONTEXTS_DIR.glob("record-*.json"):
        stem = path.stem.removeprefix("record-")
        if stem.isdigit():
            ids.append (int(stem ) )
    return sorted(ids)



def levels_by_case () -> list[tuple [str ,int ] ]:
    # (level, record_id) per case, ascending. the level is what the pair of texts
    #was generated to be, and the only way to tell if a match percentage is
    #behaving. read off the scorecards status because thats the one that keeps
    #the labels own value. cashys status is useless here, the generator
    # rewrites it to "Elegible" on the flag hidden cases since the model never
    # saw the flag.
    found =[]
    for record_id in available_record_ids():
        path=OUTPUTS_DIR / f"scorecard-record-{record_id:03d}.json"
        if not path.is_file():
            continue
        status = _read_json(path)["decision"].get("eligibility_status" , "")
        level= STATUS_LEVELS.get (status)

        if level :
            found.append((level, record_id))
    return found


def _build_variables (raw :dict )->list [dict]:
    variables= [ ]
    for key, label, kind in CONTEXT_FIELDS:
        if key not in raw :
            continue
        variables.append( { "key" : key,"label" : label,"kind": kind , "value" :raw [key] })
    return variables


def list_cases( ) -> list[ dict] :
    # rows for the case selector
    cases = []
    for record_id in available_record_ids():
        try:
            context =_read_json( _context_path ( record_id ) )
        except(OSError , ValueError ) :
            continue
        cases.append(
            {
                "record_id": record_id,
                "month" :context.get ( "month") ,
                "office" :context.get( "office"),
            }
        )
    return cases


def load_case(record_id: int) -> dict:
    # detail payload for one case. raises CaseNotFound when the context file is
    #absent so the route can 404 rather than serve a half populated record.
    context_path=_context_path (record_id)

    if not context_path.is_file():
        raise CaseNotFound ( record_id )

    context = _read_json(context_path)

    # cashys output carries the eligibility and the reasoning. optional: a case
    # can be reviewed on its context alone if the model output is missing.
    eligibility= {"target" :None ,"status" :None }
    analysis=None
    cashy_path= _cashy_path(record_id )
    if cashy_path.is_file ( ):
        cashy=_read_json(cashy_path)
        eligibility = {
            "target" :cashy[ "decision"].get ( "eligibility_target" ) ,
            "status" : cashy["decision"].get ( "eligibility_status" ),
        }
        analysis= cashy.get( "analysis" )

    return {
        "record_id":record_id,
        "month":context.get("month" ),
        "office" : context.get("office" ) ,
        # only the external variables go out. the free text case context is left
        # out on purpose, the review ui doesnt show it.
        "variables": _build_variables(context.get("external_variables") or {}),
        "eligibility": eligibility,
        "analysis": analysis,
    }

from dataclasses import dataclass
from dataclasses import field
from typing import Optional

import marshmallow_dataclass
import marshmallow.validate as mv

MONTH = mv.Regexp(r"^\d{4}-\d{2}$")
SECURITY_EXPOSURE = ("low", "medium", "high")
DISPLACEMENT_STAGES = ("recent" , "settled" ,"long_term")


@dataclass
class ExternalVariables :


    security_exposure: str =field (metadata={"validate": mv.OneOf(SECURITY_EXPOSURE ) })
    displacement_stage: str = field(
        metadata = {"validate" :mv.OneOf ( DISPLACEMENT_STAGES) }
    )
    budget_places_available :int =0
    budget_places_assigned:int= 0

    origin_country_conflict: bool = False
    sex_or_sexuality_discrimination :bool=False
    activism_exposure:bool= False
    interpretation_available: bool = True


# typed view of assets/contexts/schema.json. the external variables live beside
# the case, not in it: they are what the month looked like when the
# recommendation was reached and none of them is on the interview form, which is
#the whole reason the judgement engine reads this file separately.
#
# Synthesised by build_cases.py, the dataset doesnt carry these fields.
@ dataclass
class Context :


    record_id: int
    month: str = field(metadata={"validate": MONTH})
    #required=True stated explicitly, marshmallow reads Optional[X] as "not
    # required" and allow-none together. the key must be present and may hold
    # null, which is what the dataset leaves on rows with no office.
    office: Optional[str] = field(metadata={"required": True})
    description: str
    external_variables :ExternalVariables


ContextSchema = marshmallow_dataclass.class_schema(Context)()



#parses + validates one context, raises marshmallow.ValidationError
def load(raw):
    return ContextSchema.load( raw )


# back to plain json data
def dump(context ):
    return ContextSchema.dump( context)

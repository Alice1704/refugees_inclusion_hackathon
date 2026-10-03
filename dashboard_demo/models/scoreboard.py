from dataclasses import dataclass
from dataclasses import field
from typing import Optional

import marshmallow_dataclass
import marshmallow.validate as mv

MONTH = mv.Regexp(r"^\d{4}-\d{2}$")
DEPENDENCY_CATEGORIES = ("low", "average", "complete", "high")
VULNERABILITY_CATEGORIES=(
    "Vulnerabilidad Baja",
    "Vulnerabilidad Moderada",
    "Vulnerabilidad Elevada",
    "Vulnerabilidad Severa",
)
ELIGIBILITY_TARGETS = ("INCLUSION", "EXCLUSION" )


ELIGIBILITY_STATUSES = (
    "Elegible" ,
    "Elegible por Proceso Acelerado",
    "Lista de Reserva",
    "No Elegible" ,
    "No Elegible por Intenciones",
    "No Elegible por Duplicidad",
)


@ dataclass
class Interview:
    month: str = field(metadata={"validate": MONTH})
    office: Optional[str] = None



@dataclass
class Household :
    size: int
    dependency_category: str = field(
        metadata={"validate" :mv.OneOf( DEPENDENCY_CATEGORIES) }
    )
    female_headed :Optional[bool]=None
    sole_carer:Optional[bool ]= None


    spanish_spoken:bool=False
    adult_illiteracy:bool =False


@dataclass
class Demographics:
    head_of_household:float =0.0
    language_barrier: float = 0.0
    specific_needs :float=0.0

    documentation: float = 0.0
    score : float =0.0


@dataclass
class NeedsAndCoping:
    basic_needs :float= 0.0
    housing: float = 0.0
    negative_coping: float = 0.0
    dependency:float=0.0
    score: float =0.0



@dataclass
class Scores :
    final_score:float
    vulnerability_index: float
    vulnerability_category : str = field (
        metadata ={"validate" :mv.OneOf (VULNERABILITY_CATEGORIES )}
    )


@dataclass
class AdministrativeFlags:
    asylum_procedure: Optional[int] = None
    intentions : int = 0
    duplicate: int = 0


@dataclass
class Decision:
    eligibility_target: str = field(
        metadata= {"validate":mv.OneOf ( ELIGIBILITY_TARGETS )}
    )
    eligibility_status : str=field (
        metadata={"validate": mv.OneOf(ELIGIBILITY_STATUSES)}
    )


#typed view of assets/outputs/output-schema.json. the json file is the contract,
# so unknown keys are an error rather than being dropped: a silently ignored
#field is exactly the drift this layer is here to catch.
@ dataclass
class Output:
    record_id:int
    interview: Interview
    household : Household
    demographics : Demographics
    needs_and_coping: NeedsAndCoping
    scores:Scores
    administrative_flags:AdministrativeFlags
    decision : Decision

    #required not defaulted, output-schema.json lists analysis in required and
    #an empty default would quietly accept a record the schema rejects.
    analysis:str


#module level because class_schema walks the type tree and is not cheap
ScoreboardSchema= marshmallow_dataclass.class_schema (Output) ( )


# parses + validates one record, raises marshmallow.ValidationError
def load( raw ):
    return ScoreboardSchema.load (raw )


#back to plain json data
def dump( record):
    return ScoreboardSchema.dump(record )

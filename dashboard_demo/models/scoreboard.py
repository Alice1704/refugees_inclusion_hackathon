from dataclasses import dataclass
from dataclasses import NewType
from typing import Optional

import marshmallow_dataclass
import marshmallow.validate as mv


MonthType = NewType("MonthType", str, mv.Regexp(r'^\d{4}-\d{2}$'))

@dataclass
class Properties:
    month: MonthType # type: ignore
    office: Optional[str]

@dataclass
class Household:
    size: int
    dependency_category: str
    female_headed: Optional[bool]
    sole_carer: Optional[bool]
    spanish_spoken: bool
    adult_illiteracy: bool
    pass

@dataclass
class Demographics:
    head_of_household: float
    language_barrier: float
    specific_needs: float
    documentation: float
    score: float
    pass


@dataclass
class Needs_and_coping:
    basic_needs : float
    housing : float
    negative_coping : float
    dependency : float
    score : float

@dataclass
class Scores:
    final_score : float
    vulnerability_index : float
    vulnerability_category : str

@dataclass
class Administrative_flags:
    asylum_procedure : Optional[int]
    intentions : int
    duplicate : int

@dataclass
class Decision:
    eligibility_target: str
    eligibility_status: str


@dataclass
class Scoreboard:
    record_id: int
    properties: Properties
    household: Household
    demographics: Demographics
    needs_and_coping: Needs_and_coping
    scores: Scores
    administrative_flags: Administrative_flags
    decision: Decision

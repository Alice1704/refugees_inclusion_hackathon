from dataclasses import dataclass
from dataclasses import NewType
from typing import Optional

import marshmallow_dataclass
import marshmallow.validate as mv
import scoreboard

@dataclass 
class Scoreboard:
    score : scoreboard.Scoreboard

@dataclass
class Analysis:
    analysis_text : str

@dataclass
class Output:
    scoreboard : Scoreboard
    analysis : Analysis
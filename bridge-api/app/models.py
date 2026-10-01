from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PositiveId = Annotated[int, Field(strict=True, gt=0)]


class NormalizedFighter(BaseModel):
    stage_item_input_id: PositiveId
    team_id: PositiveId
    name: str
    club: None = None


class NormalizedCategory(BaseModel):
    stage_item_id: PositiveId
    name: str


class NormalizedMatch(BaseModel):
    tournament_id: PositiveId
    match_id: PositiveId
    tatami_id: Literal[1] = 1
    fighter_a: NormalizedFighter
    fighter_b: NormalizedFighter
    category: NormalizedCategory
    duration_seconds: PositiveId


class AssignMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tatami_id: Literal[1]
    tournament_id: PositiveId
    match_id: PositiveId

    @field_validator("tatami_id", mode="before")
    @classmethod
    def only_tatami_one(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Only integer tatami_id 1 is supported")
        return value


class AssignMatchResponse(BaseModel):
    status: Literal["normalized"] = "normalized"
    scoreboard_sent: Literal[False] = False
    match: NormalizedMatch

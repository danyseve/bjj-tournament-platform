from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PositiveId = Annotated[int, Field(strict=True, gt=0)]
ResultStatus = Literal["written", "pending_manual", "conflict", "failed"]


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
    status: Literal["assigned", "replayed"]
    scoreboard_sent: Literal[True] = True
    match: NormalizedMatch
    state: dict


class MatchCandidate(BaseModel):
    """Exactly what an operator needs to pick a match, and nothing else.

    Same shape as the assignment payload so a chosen candidate can be sent to
    `POST /tatamis/1/assign-match` without translation.
    """

    tournament_id: PositiveId
    match_id: PositiveId
    fighter_a: NormalizedFighter
    fighter_b: NormalizedFighter
    category: NormalizedCategory
    duration_seconds: PositiveId


class CandidatesResponse(BaseModel):
    tournament_id: PositiveId
    # The match the scoreboard currently holds for this tournament: it is left
    # out of the list, and `scoreboard_read` says whether that could be checked
    # at all. A missing answer never turns into a guessed list.
    active_match_id: PositiveId | None = None
    scoreboard_read: bool
    candidates: list[MatchCandidate]


class ResultRequest(BaseModel):
    """Which fight the caller is asking to publish, and nothing else (P2.4D §10).

    The bridge never accepts points, winner or method from the client: those are
    read from the live scoreboard state. The caller only identifies the fight it
    believes is frozen, and the state must agree.
    """

    model_config = ConfigDict(extra="forbid")

    tournament_id: PositiveId
    match_id: PositiveId
    session_id: str
    expected_revision: PositiveId | None = None

    @field_validator("session_id")
    @classmethod
    def session_id_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_id must not be empty")
        return value


class ResultResponse(BaseModel):
    """Publication outcome. Contains no credential of any kind."""

    tatami_id: Literal[1] = 1
    status: ResultStatus
    reason: str | None = None
    idempotent: bool = False
    fingerprint: str | None = None
    tournament_id: PositiveId | None = None
    match_id: PositiveId | None = None
    session_id: str | None = None
    revision: int | None = None
    winner_team_id: PositiveId | None = None
    scores: dict | None = None
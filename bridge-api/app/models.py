from pydantic import BaseModel


class Fighter(BaseModel):
    name: str
    team: str | None = None


class AssignMatchRequest(BaseModel):
    tatami: int
    match_id: int
    red: Fighter
    blue: Fighter
    category: str | None = None
    duration_seconds: int = 300


class MatchResultRequest(BaseModel):
    tatami: int
    match_id: int
    winner: str
    red_points: int = 0
    blue_points: int = 0
    red_advantages: int = 0
    blue_advantages: int = 0
    method: str | None = None

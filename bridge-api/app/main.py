from fastapi import FastAPI, HTTPException, Response

from app.bracket_client import (BracketClient, BracketError, collect_candidates, locate_match,
                                normalize_match, positive_int)
from app.models import (AssignMatchRequest, AssignMatchResponse, CandidatesResponse,
                        MatchCandidate)
from app.scoreboard_client import ScoreboardClient, ScoreboardError

app = FastAPI(
    title="BJJ Bridge API",
    version="0.1.0",
    description="Integration layer between Bracket and BJJ-Scoreboard",
)

bracket_client = BracketClient()
scoreboard_client = ScoreboardClient()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "bjj-bridge-api",
        "version": "0.1.0",
    }


@app.get("/health/bracket")
async def health_bracket():
    try:
        result = await bracket_client.health()
        return {
            "status": "ok",
            "bracket": result,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Bracket API is not available: {exc}",
        )


@app.post("/tatamis/{tatami_id}/assign-match", response_model=AssignMatchResponse)
async def assign_match(tatami_id: int, payload: AssignMatchRequest, response: Response):
    if tatami_id != payload.tatami_id:
        raise HTTPException(status_code=400, detail="Path and payload tatami_id must both be 1")
    try:
        stages = await bracket_client.fetch_stages(payload.tournament_id)
        match, category = locate_match(stages, payload.tournament_id, payload.match_id)
        normalized = normalize_match(match, category, payload.tournament_id)
    except BracketError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    try:
        delivered = await scoreboard_client.assign_match(tatami_id, normalized.model_dump())
    except ScoreboardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    response.status_code = 201 if delivered["status"] == "assigned" else 200
    return AssignMatchResponse(
        status=delivered["status"],
        scoreboard_sent=True,
        match=normalized,
        state=delivered["state"],
    )


def candidate_view(match) -> MatchCandidate:
    """Explicit field selection: a candidate carries nothing else."""
    return MatchCandidate(
        tournament_id=match.tournament_id,
        match_id=match.match_id,
        fighter_a=match.fighter_a,
        fighter_b=match.fighter_b,
        category=match.category,
        duration_seconds=match.duration_seconds,
    )


@app.get("/tatamis/{tatami_id}/candidates", response_model=CandidatesResponse)
async def list_candidates(tatami_id: int, tournament_id: int):
    """Read-only candidate list for Tatami 1. Listing assigns nothing."""
    if tatami_id != 1:
        raise HTTPException(status_code=400, detail="Only tatami_id 1 is supported")
    try:
        positive_int(tournament_id, "tournament_id")
    except BracketError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        stages = await bracket_client.fetch_stages(tournament_id)
        playable = collect_candidates(stages, tournament_id)
    except BracketError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    scoreboard_read, active_match_id = True, None
    try:
        state = await scoreboard_client.read_state(tatami_id)
        if state is not None and state.get("tournament_id") == tournament_id:
            active_match_id = state.get("match_id")
    except ScoreboardError:
        scoreboard_read = False
    return CandidatesResponse(
        tournament_id=tournament_id,
        active_match_id=active_match_id,
        scoreboard_read=scoreboard_read,
        candidates=[candidate_view(match) for match in playable if match.match_id != active_match_id],
    )


@app.post("/tatamis/{tatami_id}/result")
async def submit_result(tatami_id: int):
    raise HTTPException(status_code=501, detail="Result submission is disabled; no writes are performed")

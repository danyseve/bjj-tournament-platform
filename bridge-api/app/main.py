from fastapi import FastAPI, HTTPException

from app.bracket_client import BracketClient, BracketError, locate_match, normalize_match
from app.models import AssignMatchRequest, AssignMatchResponse

app = FastAPI(
    title="BJJ Bridge API",
    version="0.1.0",
    description="Integration layer between Bracket and BJJ-Scoreboard",
)

bracket_client = BracketClient()


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
async def assign_match(tatami_id: int, payload: AssignMatchRequest):
    if tatami_id != payload.tatami_id:
        raise HTTPException(status_code=400, detail="Path and payload tatami_id must both be 1")
    try:
        stages = await bracket_client.fetch_stages(payload.tournament_id)
        match, category = locate_match(stages, payload.tournament_id, payload.match_id)
        return AssignMatchResponse(match=normalize_match(match, category, payload.tournament_id))
    except BracketError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/tatamis/{tatami_id}/result")
async def submit_result(tatami_id: int):
    raise HTTPException(status_code=501, detail="Result submission is disabled in P2.3A; no writes are performed")

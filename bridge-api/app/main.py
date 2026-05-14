from fastapi import FastAPI, HTTPException

from app.bracket_client import BracketClient
from app.scoreboard_client import ScoreboardClient
from app.models import AssignMatchRequest, MatchResultRequest

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


@app.post("/tatamis/{tatami_id}/assign-match")
async def assign_match(tatami_id: int, payload: AssignMatchRequest):
    if tatami_id != payload.tatami:
        raise HTTPException(
            status_code=400,
            detail="Path tatami_id and payload tatami do not match",
        )

    try:
        result = await scoreboard_client.assign_match(
            tatami=tatami_id,
            payload=payload.model_dump(),
        )
        return {
            "status": "accepted",
            "message": "Match assignment received",
            "result": result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/tatamis/{tatami_id}/result")
async def submit_result(tatami_id: int, payload: MatchResultRequest):
    if tatami_id != payload.tatami:
        raise HTTPException(
            status_code=400,
            detail="Path tatami_id and payload tatami do not match",
        )

    result = await bracket_client.update_match_result(
        match_id=payload.match_id,
        payload=payload.model_dump(),
    )

    return {
        "status": "accepted",
        "message": "Result received",
        "result": result,
    }

from typing import TypeVar

from fastapi import FastAPI, HTTPException, Response

from app.bracket_client import (BracketClient, BracketError, cas_view, collect_candidates,
                                locate_match, match_baseline, match_write_body, normalize_match,
                                positive_int, post_verify)
from app.models import (AssignMatchRequest, AssignMatchResponse, CandidatesResponse,
                        MatchCandidate, ResultRequest, ResultResponse, ResultStatus)
from app.result_gate import (CONFLICT, FAILED, PENDING, REASON_ALREADY_WRITTEN,
                             REASON_BRACKET_CHANGED, REASON_NOT_PRISTINE, REASON_PARTICIPANTS,
                             REASON_WRITE_NOT_CONFIGURED, evaluate)
from app.result_store import FAILED as STORE_FAILED
from app.result_store import WRITING as STORE_WRITING
from app.result_store import WRITTEN as STORE_WRITTEN
from app.result_store import ResultStore
from app.scoreboard_client import ScoreboardClient, ScoreboardError

Value = TypeVar("Value")


def required(value: Value | None, name: str) -> Value:
    """Narrow a gate field the write path cannot proceed without.

    The gate only reaches WRITE with the full frozen identity validated, so a
    None here means the gate and the endpoint disagree: fail loudly instead of
    inventing a value.
    """
    if value is None:
        raise HTTPException(status_code=500, detail=f"Safe-result gate left {name} undefined")
    return value

app = FastAPI(
    title="BJJ Bridge API",
    version="0.1.0",
    description="Integration layer between Bracket and BJJ-Scoreboard",
)

bracket_client = BracketClient()
scoreboard_client = ScoreboardClient()
result_store = ResultStore()


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


def result_response(gate, *, status: ResultStatus, reason: str | None = None, idempotent: bool = False,
                    scores: dict | None = None) -> ResultResponse:
    """Build the response from validated facts only. No credential ever enters it."""
    wanted = (gate.points_a, gate.points_b) if scores is None else scores
    return ResultResponse(
        status=status,
        reason=reason,
        idempotent=idempotent,
        fingerprint=gate.fingerprint,
        tournament_id=gate.tournament_id,
        match_id=gate.match_id,
        session_id=gate.session_id,
        revision=gate.revision,
        winner_team_id=gate.winner_team_id,
        scores={"stage_item_input1_score": wanted[0], "stage_item_input2_score": wanted[1]}
        if wanted[0] is not None else None,
    )


@app.post("/tatamis/{tatami_id}/result", response_model=ResultResponse)
async def submit_result(tatami_id: int, payload: ResultRequest, response: Response):
    """Publish the frozen result of one fight into Bracket (P2.4D, Tatami 1 only).

    Full flow: read the live scoreboard state -> safe-result gate -> fresh read
    of the match -> logical CAS -> PUT -> post-verification. The client states
    which fight it means; it never states points or a winner.
    """
    if tatami_id != 1:
        raise HTTPException(status_code=400, detail="Only tatami_id 1 is supported")
    if not bracket_client.write_configured:
        response.status_code = 503
        return ResultResponse(status=FAILED, reason=REASON_WRITE_NOT_CONFIGURED)

    try:
        state = await scoreboard_client.read_state(tatami_id)
    except ScoreboardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    gate = evaluate(state, payload.model_dump())
    if gate.decision == PENDING:
        return result_response(gate, status=PENDING, reason=gate.reason)
    if gate.decision == CONFLICT:
        response.status_code = 409
        return result_response(gate, status=CONFLICT, reason=gate.reason)
    if gate.decision == FAILED:
        response.status_code = 502
        return result_response(gate, status=FAILED, reason=gate.reason)

    # The gate only reaches WRITE with the whole frozen identity validated: this
    # narrowing is a safety net, not a place where a missing value is invented.
    tournament_id = required(gate.tournament_id, "tournament_id")
    match_id = required(gate.match_id, "match_id")
    fingerprint = required(gate.fingerprint, "fingerprint")
    team_ids = required(gate.team_ids, "team_ids")
    winner_team_id = required(gate.winner_team_id, "winner_team_id")
    points_a = required(gate.points_a, "stage_item_input1_score")
    points_b = required(gate.points_b, "stage_item_input2_score")
    key = (tournament_id, match_id)
    if result_store.is_written(fingerprint):
        # Same frozen result, already published: no second PUT (P2.4D §9).
        return result_response(gate, status=STORE_WRITTEN, idempotent=True)
    if result_store.written_fingerprints(*key) - {fingerprint}:
        # This match already carries a *different* published result: never
        # overwrite it automatically, not even from a new session.
        response.status_code = 409
        return result_response(gate, status=CONFLICT, reason=REASON_ALREADY_WRITTEN)

    try:
        current = match_baseline(await bracket_client.read_match(tournament_id, match_id), tournament_id)
    except BracketError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if (current["input1_team_id"], current["input2_team_id"]) != team_ids:
        response.status_code = 409
        return result_response(gate, status=CONFLICT, reason=REASON_PARTICIPANTS)

    previous = result_store.baseline(*key)
    if previous is not None:
        if cas_view(previous) != cas_view(current):
            response.status_code = 409
            return result_response(gate, status=CONFLICT, reason=REASON_BRACKET_CHANGED)
    elif (current["score1"], current["score2"]) != (0, 0):
        # First publication of a match that already carries scores somebody else
        # entered: adopting them silently is exactly what must not happen.
        response.status_code = 409
        return result_response(gate, status=CONFLICT, reason=REASON_NOT_PRISTINE)

    result_store.set_baseline(*key, current)
    result_store.record(fingerprint, STORE_WRITING, None, key=key,
                        match_id=match_id, tournament_id=tournament_id)
    body = match_write_body(current, points_a, points_b)
    try:
        token = await bracket_client.login()
        await bracket_client.update_match(tournament_id, match_id, body, token)
    except BracketError as exc:
        result_store.record(fingerprint, STORE_FAILED, str(exc), key=key,
                            match_id=match_id, tournament_id=tournament_id)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        verified = match_baseline(await bracket_client.read_match(tournament_id, match_id), tournament_id)
    except BracketError as exc:
        result_store.record(fingerprint, STORE_FAILED, "post_verify_unreadable", key=key,
                            match_id=match_id, tournament_id=tournament_id)
        raise HTTPException(status_code=exc.status_code,
                            detail="Post-verification read failed") from exc

    reason = post_verify(verified, body, winner_team_id)
    if reason is not None:
        # A partial upstream application can be detected here but cannot be
        # reverted safely: no second PUT is attempted (P2.4D §12).
        result_store.record(fingerprint, STORE_FAILED, reason, key=key,
                            match_id=match_id, tournament_id=tournament_id)
        response.status_code = 502
        return result_response(gate, status=FAILED, reason=reason)

    result_store.record(fingerprint, STORE_WRITTEN, None, key=key,
                        match_id=match_id, tournament_id=tournament_id)
    return result_response(gate, status=STORE_WRITTEN)
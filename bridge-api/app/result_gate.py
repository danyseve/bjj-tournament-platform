"""Safe-result gate (P2.4D).

Decides, from the **frozen live state of the scoreboard** and the identifiers
the caller expects, whether the result may be published to Bracket. Only one
mapping is ever written automatically:

    natural points victory, both sides with real, different points, and the
    declared winner being exactly the side with more points.

Everything else is refused with an explicit, non-sensitive reason. Scores are
never invented and never adjusted to force a winner (ADR-001, "regla de oro").

The gate is a pure function: no I/O, no state, no clock. That is what makes the
35 bridge tests able to cover every branch without touching a live service.
"""

from typing import Literal

from pydantic import BaseModel

from app.fingerprint import FingerprintError, fighter_scores, result_fingerprint

SAFE_METHOD = "points"
FINISHED = "finished"

# Decisions the gate can take.
WRITE: Literal["write"] = "write"
PENDING: Literal["pending_manual"] = "pending_manual"
CONFLICT: Literal["conflict"] = "conflict"
FAILED: Literal["failed"] = "failed"

Decision = Literal["write", "pending_manual", "conflict", "failed"]

# Non-sensitive reason codes. Stable names: tests and the README rely on them.
REASON_INVALID_STATE = "invalid_scoreboard_state"
REASON_NO_STATE = "no_scoreboard_state"
REASON_NOT_FINISHED = "scoreboard_not_finished"
REASON_TOURNAMENT_MISMATCH = "tournament_mismatch"
REASON_MATCH_MISMATCH = "match_mismatch"
REASON_SESSION_MISMATCH = "session_mismatch"
REASON_REVISION_MISMATCH = "revision_mismatch"
REASON_INVALID_WINNER = "winner_not_a_participant"
REASON_UNSUPPORTED = "unsupported_result_mapping"
REASON_TIE = "tie_not_writable"
REASON_CONTRADICTS = "winner_contradicts_points"

# Endpoint-level decisions (same stable, non-sensitive naming).
REASON_WRITE_NOT_CONFIGURED = "bracket_write_not_configured"
# P2.5B — the release switch is off: the endpoint refuses before any read or write.
REASON_WRITE_DISABLED = "result_write_disabled"
REASON_PARTICIPANTS = "participants_mismatch"
REASON_BRACKET_CHANGED = "bracket_scores_changed"
REASON_NOT_PRISTINE = "bracket_match_not_pristine"
REASON_ALREADY_WRITTEN = "already_written_different_result"


class GateResult(BaseModel):
    """Outcome of the gate plus the validated facts a write needs."""

    decision: Decision
    reason: str | None = None
    fingerprint: str | None = None
    tournament_id: int | None = None
    match_id: int | None = None
    session_id: str | None = None
    revision: int | None = None
    winner_team_id: int | None = None
    method: str | None = None
    status: str | None = None
    points_a: int | None = None
    points_b: int | None = None
    advantages_a: int | None = None
    advantages_b: int | None = None
    penalties_a: int | None = None
    penalties_b: int | None = None
    team_ids: tuple[int, int] | None = None


def _decision(decision: Decision, reason: str | None = None, **facts) -> GateResult:
    return GateResult(decision=decision, reason=reason, **facts)


def _positive_int(value) -> int | None:
    return value if type(value) is int and value > 0 else None


def evaluate(state: dict | None, expected: dict | None = None) -> GateResult:
    """Apply the safe-result gate.

    ``state`` is the live scoreboard state (``None`` when the tatami is empty);
    ``expected`` carries the identifiers the caller claims (tournament_id,
    match_id, session_id, optional revision).
    """
    if state is None:
        return _decision(PENDING, REASON_NO_STATE)
    if not isinstance(state, dict):
        return _decision(FAILED, REASON_INVALID_STATE)

    # --- identity of the fight -------------------------------------------
    tournament_id = _positive_int(state.get("tournament_id"))
    match_id = _positive_int(state.get("match_id"))
    session_id = state.get("session_id")
    revision = state.get("revision")
    status = state.get("status")
    if (
        tournament_id is None
        or match_id is None
        or not isinstance(session_id, str)
        or not session_id
        or type(revision) is not int
        or not isinstance(status, str)
    ):
        return _decision(FAILED, REASON_INVALID_STATE)

    facts = {"tournament_id": tournament_id, "match_id": match_id, "session_id": session_id,
             "revision": revision, "status": status}

    if expected is not None:
        if tournament_id != expected.get("tournament_id"):
            return _decision(CONFLICT, REASON_TOURNAMENT_MISMATCH, **facts)
        if match_id != expected.get("match_id"):
            return _decision(CONFLICT, REASON_MATCH_MISMATCH, **facts)
        if session_id != expected.get("session_id"):
            return _decision(CONFLICT, REASON_SESSION_MISMATCH, **facts)
        wanted_revision = expected.get("expected_revision")
        if wanted_revision is not None and wanted_revision != revision:
            return _decision(CONFLICT, REASON_REVISION_MISMATCH, **facts)

    # --- frozen result? ---------------------------------------------------
    if status != FINISHED:
        return _decision(PENDING, REASON_NOT_FINISHED, **facts)

    try:
        points_a, advantages_a, penalties_a = fighter_scores(state, "a")
        points_b, advantages_b, penalties_b = fighter_scores(state, "b")
    except FingerprintError:
        return _decision(FAILED, REASON_INVALID_STATE, **facts)

    facts.update({"points_a": points_a, "points_b": points_b,
                  "advantages_a": advantages_a, "advantages_b": advantages_b,
                  "penalties_a": penalties_a, "penalties_b": penalties_b})

    team_a = state["fighter_a"].get("team_id")
    team_b = state["fighter_b"].get("team_id")
    winner_team_id = state.get("winner_team_id")
    method = state.get("method")
    if _positive_int(team_a) is None or _positive_int(team_b) is None or team_a == team_b:
        return _decision(FAILED, REASON_INVALID_STATE, **facts)
    facts.update({"team_ids": (team_a, team_b), "winner_team_id": winner_team_id, "method": method})

    # --- who won, according to what? --------------------------------------
    if winner_team_id not in (team_a, team_b):
        return _decision(CONFLICT, REASON_INVALID_WINNER, **facts)
    if not isinstance(method, str) or not method:
        return _decision(FAILED, REASON_INVALID_STATE, **facts)
    if method != SAFE_METHOD:
        return _decision(PENDING, REASON_UNSUPPORTED, **facts)
    if points_a == points_b:
        return _decision(PENDING, REASON_TIE, **facts)

    natural_winner = team_a if points_a > points_b else team_b
    if winner_team_id != natural_winner:
        return _decision(CONFLICT, REASON_CONTRADICTS, **facts)

    try:
        fingerprint = result_fingerprint(state)
    except FingerprintError:
        return _decision(FAILED, REASON_INVALID_STATE, **facts)

    return _decision(WRITE, None, fingerprint=fingerprint, **facts)

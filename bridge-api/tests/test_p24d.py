"""P2.4D — the only automatic write Bridge -> Bracket: a natural points victory.

Every test here runs against monkeypatched clients; no real service is
contacted (test 35 asserts exactly that, with a booby-trapped httpx client).
"""
import copy

import httpx
import pytest
from pydantic import SecretStr

from app import main
from app.bracket_client import BracketError
from app.config import settings
from app.fingerprint import FINGERPRINT_VERSION, result_fingerprint
from app.result_gate import evaluate
from app.scoreboard_client import ScoreboardError

pytestmark = pytest.mark.anyio
RealAsyncClient = httpx.AsyncClient

TOURNAMENT_ID = 7
MATCH_ID = 40
ITEM_ID = 9
ROUND_ID = 5
TEAM_A = 101
TEAM_B = 102
SESSION = "synthetic-session-p24d"
WRITE_USER = "synthetic-writer"
WRITE_SECRET = "synthetic-write-secret-value"

RESULT_BODY_KEYS = ["court_id", "custom_duration_minutes", "custom_margin_minutes", "round_id",
                    "stage_item_input1_score", "stage_item_input2_score"]


# --------------------------------------------------------------------------- #
# Synthetic fixtures
# --------------------------------------------------------------------------- #
def fighter(team_id, points=0, advantages=0, penalties=0):
    return {"stage_item_input_id": team_id - 100, "team_id": team_id, "name": f"Team {team_id}",
            "club": None, "points": points, "advantages": advantages, "penalties": penalties}


def final_state(points_a=6, points_b=2, winner="a", method="points", status="finished",
                advantages_a=0, advantages_b=0, penalties_a=0, penalties_b=0,
                tournament_id=TOURNAMENT_ID, match_id=MATCH_ID, session_id=SESSION, revision=12):
    winner_team_id = None
    if winner == "a":
        winner_team_id = TEAM_A
    elif winner == "b":
        winner_team_id = TEAM_B
    return {
        "session_id": session_id, "revision": revision, "tatami_id": 1,
        "tournament_id": tournament_id, "match_id": match_id,
        "fighter_a": fighter(TEAM_A, points_a, advantages_a, penalties_a),
        "fighter_b": fighter(TEAM_B, points_b, advantages_b, penalties_b),
        "category": {"stage_item_id": ITEM_ID, "name": "Synthetic Adult"},
        "duration_seconds": 300, "remaining_seconds": 0, "status": status,
        "winner_team_id": winner_team_id, "method": method,
    }


def bracket_match(score1=0, score2=0, court_id=None, custom_duration=None, custom_margin=None,
                  round_id=ROUND_ID, tournament_id=TOURNAMENT_ID, match_id=MATCH_ID):
    def side(side_number, input_id, team_id):
        return {"id": input_id, "slot": side_number, "tournament_id": tournament_id,
                "stage_item_id": ITEM_ID, "team_id": team_id,
                "winner_from_stage_item_id": None, "winner_position": None,
                "team": {"id": team_id, "name": f"Team {team_id}", "tournament_id": tournament_id}}
    input1, input2 = side(1, 1, TEAM_A), side(2, 2, TEAM_B)
    return {
        "id": match_id, "round_id": round_id, "duration_minutes": 5,
        "custom_duration_minutes": custom_duration, "custom_margin_minutes": custom_margin,
        "stage_item_input1_id": input1["id"], "stage_item_input2_id": input2["id"],
        "stage_item_input1": input1, "stage_item_input2": input2,
        "stage_item_input1_score": score1, "stage_item_input2_score": score2,
        "stage_item_input1_conflict": False, "stage_item_input2_conflict": False,
        "stage_item_input1_winner_from_match_id": None, "stage_item_input2_winner_from_match_id": None,
        "court_id": court_id, "position_in_schedule": 1 if court_id else None,
        "start_time": "2026-10-02T10:00:00" if court_id else None,
    }


def stages_payload(match, tournament_id=TOURNAMENT_ID):
    return {"data": [{"id": 1, "tournament_id": tournament_id, "name": "Synthetic Stage",
                      "stage_items": [{"id": ITEM_ID, "stage_id": 1, "name": "Synthetic Adult",
                                       "rounds": [{"id": ROUND_ID, "stage_item_id": ITEM_ID,
                                                   "is_draft": False, "matches": [match]}]}]}]}


class FakeBracket:
    """Records every interaction the endpoint makes with Bracket."""

    write_configured = True

    def __init__(self, match=None, write_error=None, post_match=None, read_error=None,
                 payload_error=None):
        self.match = match if match is not None else bracket_match()
        self.post_match = post_match
        self.write_error = write_error
        self.read_error = read_error
        self.payload_error = payload_error
        self.applied = None
        self.calls = {"read": 0, "login": 0, "put": [], "bodies": [], "tokens": []}

    async def read_match(self, tournament_id, match_id):
        self.calls["read"] += 1
        if self.read_error is not None and self.calls["read"] > 1:
            raise self.read_error
        if self.payload_error is not None:
            raise self.payload_error
        if self.calls["read"] > 1:
            if self.post_match is not None:
                return copy.deepcopy(self.post_match)
            if self.applied is not None:
                return copy.deepcopy(self.applied)
        return copy.deepcopy(self.match)

    async def login(self):
        self.calls["login"] += 1
        return "synthetic-jwt"

    async def update_match(self, tournament_id, match_id, body, token):
        self.calls["put"].append((tournament_id, match_id))
        self.calls["bodies"].append(copy.deepcopy(body))
        self.calls["tokens"].append(token)
        if self.write_error is not None:
            raise self.write_error
        # Bracket aplica el body de verdad: la lectura posterior lo refleja.
        self.applied = copy.deepcopy(self.match)
        self.applied.update({key: body[key] for key in ("round_id", "stage_item_input1_score",
                                                        "stage_item_input2_score", "court_id",
                                                        "custom_duration_minutes",
                                                        "custom_margin_minutes")})


class FakeScoreboard:
    def __init__(self, state, error=None):
        self.state = state
        self.error = error
        self.reads = 0

    async def read_state(self, tatami):
        self.reads += 1
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.state)


def wire(monkeypatch, bracket, scoreboard):
    monkeypatch.setattr(main, "bracket_client", bracket)
    monkeypatch.setattr(main, "scoreboard_client", scoreboard)
    monkeypatch.setattr(settings, "bracket_write_username", WRITE_USER)
    monkeypatch.setattr(settings, "bracket_write_password", SecretStr(WRITE_SECRET))


@pytest.fixture(autouse=True)
def clean_store():
    main.result_store.reset()
    yield
    main.result_store.reset()


async def post_result(state=None, bracket=None, scoreboard_error=None, tatami=1, body=None,
                      bracket_client=None):
    scoreboard = FakeScoreboard(state if state is not None else final_state(),
                                error=scoreboard_error)
    bracket = bracket_client if bracket_client is not None else FakeBracket()
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        response = await client.post(
            f"/tatamis/{tatami}/result",
            json=body if body is not None else {"tournament_id": TOURNAMENT_ID,
                                                "match_id": MATCH_ID, "session_id": SESSION},
        )
    return response, bracket, scoreboard


# --------------------------------------------------------------------------- #
# 1-10: what may and may not be written automatically
# --------------------------------------------------------------------------- #
async def test_1_natural_points_win_by_a_is_written(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "written"
    assert response.json()["reason"] is None
    assert bracket.calls["put"] == [(TOURNAMENT_ID, MATCH_ID)]
    assert bracket.calls["bodies"][0]["stage_item_input1_score"] == 6
    assert bracket.calls["bodies"][0]["stage_item_input2_score"] == 2


async def test_2_natural_points_win_by_b_is_written(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state(2, 7, "b")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "written"
    assert bracket.calls["bodies"][0]["stage_item_input1_score"] == 2
    assert bracket.calls["bodies"][0]["stage_item_input2_score"] == 7


@pytest.mark.parametrize("state,reason", [
    (final_state(4, 4, "a"), "tie_not_writable"),
    (final_state(4, 4, "a", advantages_a=2, advantages_b=1), "tie_not_writable"),
    (final_state(0, 0, "a", method="submission"), "unsupported_result_mapping"),
    (final_state(0, 0, "b", method="decision"), "unsupported_result_mapping"),
    (final_state(0, 0, "a", method="disqualification"), "unsupported_result_mapping"),
    (final_state(0, 0, "a", method="walkover"), "unsupported_result_mapping"),
    (final_state(0, 0, "b", method="referee_stoppage"), "unsupported_result_mapping"),
    (final_state(0, 0, "a", method="other"), "unsupported_result_mapping"),
])
async def test_3_to_10_only_points_win_is_writable(monkeypatch, state, reason):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(state))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending_manual", body
    assert body["reason"] == reason
    assert bracket.calls["put"] == [], "no se escribe nada"
    assert bracket.calls["read"] == 0, "ni siquiera se lee Bracket para escribir"


async def test_11_a_winner_that_contradicts_the_points_is_a_conflict(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state(2, 6, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 409, response.text
    assert response.json()["status"] == "conflict"
    assert response.json()["reason"] == "winner_contradicts_points"
    assert bracket.calls["put"] == []


async def test_11b_a_winner_outside_the_fight_is_a_conflict(monkeypatch):
    state = final_state(6, 2, "a")
    state["winner_team_id"] = 999
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(state))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 409
    assert response.json()["reason"] == "winner_not_a_participant"
    assert bracket.calls["put"] == []


# --------------------------------------------------------------------------- #
# 12-13: identity and lifecycle
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", ["ready", "running", "paused", "awaiting_result"])
async def test_12_a_fight_that_is_not_finished_is_pending(monkeypatch, status):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state(status=status)))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.json()["status"] == "pending_manual"
    assert response.json()["reason"] == "scoreboard_not_finished"
    assert bracket.calls["put"] == []


async def test_12b_an_empty_tatami_is_pending(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(None))
    response, _, _ = await post_result(bracket_client=bracket)
    assert response.json()["status"] == "pending_manual"
    assert response.json()["reason"] == "no_scoreboard_state"


@pytest.mark.parametrize("body,patch,reason", [
    ({"tournament_id": 8, "match_id": MATCH_ID, "session_id": SESSION}, {}, "tournament_mismatch"),
    ({"tournament_id": TOURNAMENT_ID, "match_id": 41, "session_id": SESSION}, {}, "match_mismatch"),
    ({"tournament_id": TOURNAMENT_ID, "match_id": MATCH_ID, "session_id": "other-session"}, {},
     "session_mismatch"),
    ({"tournament_id": TOURNAMENT_ID, "match_id": MATCH_ID, "session_id": SESSION,
      "expected_revision": 11}, {}, "revision_mismatch"),
])
async def test_13_a_wrong_fight_identity_is_a_conflict(monkeypatch, body, patch, reason):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state()))
    response, bracket, _ = await post_result(bracket_client=bracket, body=body)
    assert response.status_code == 409, response.text
    assert response.json()["reason"] == reason
    assert bracket.calls["put"] == []


# --------------------------------------------------------------------------- #
# 14-18: pre-read and preservation
# --------------------------------------------------------------------------- #
async def test_14_the_match_is_read_fresh_before_writing(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state()))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200
    assert bracket.calls["read"] == 2, "una lectura previa y una posterior"
    assert bracket.calls["login"] == 1


async def test_15_to_18_the_write_preserves_round_court_and_customs(monkeypatch):
    bracket = FakeBracket(bracket_match(score1=0, score2=0, court_id=3, custom_duration=8,
                                        custom_margin=2, round_id=77))
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200, response.text
    body = bracket.calls["bodies"][0]
    assert sorted(body.keys()) == RESULT_BODY_KEYS, "solo los seis campos de MatchBody"
    assert body["round_id"] == 77, "round_id actual, no inventado"
    assert body["court_id"] == 3
    assert body["custom_duration_minutes"] == 8
    assert body["custom_margin_minutes"] == 2
    for forbidden in ("winner", "method", "advantages", "penalties", "team_id"):
        assert forbidden not in body


async def test_18b_legitimate_nulls_are_echoed_as_nulls(monkeypatch):
    bracket = FakeBracket(bracket_match(court_id=None, custom_duration=None, custom_margin=None))
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200, response.text
    body = bracket.calls["bodies"][0]
    assert body["court_id"] is None and body["custom_duration_minutes"] is None
    assert body["custom_margin_minutes"] is None


# --------------------------------------------------------------------------- #
# 19-23: logical CAS and post-verification
# --------------------------------------------------------------------------- #
async def test_19_and_20_a_changed_bracket_is_a_conflict_and_no_second_put(monkeypatch):
    bracket = FakeBracket(post_match=bracket_match(score1=2, score2=6),
                          write_error=BracketError("Bracket write timed out", 504))
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    first, bracket, _ = await post_result(bracket_client=bracket)
    assert first.status_code == 504, first.text
    assert len(bracket.calls["put"]) == 1

    # Between the two attempts somebody changed Bracket's scores.
    bracket.match = bracket_match(score1=1, score2=1)
    bracket.write_error = None
    second, bracket, _ = await post_result(bracket_client=bracket)
    assert second.status_code == 409, second.text
    assert second.json()["reason"] == "bracket_scores_changed"
    assert len(bracket.calls["put"]) == 1, "la CAS impide el segundo PUT"


async def test_20b_a_match_that_already_carries_foreign_scores_is_not_overwritten(monkeypatch):
    bracket = FakeBracket(bracket_match(score1=3, score2=0))
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 409, response.text
    assert response.json()["reason"] == "bracket_match_not_pristine"
    assert bracket.calls["put"] == []


async def test_20c_participants_that_no_longer_match_are_a_conflict(monkeypatch):
    other = bracket_match()
    other["stage_item_input1"]["team_id"] = 500
    other["stage_item_input1_id"] = other["stage_item_input1"]["id"]
    bracket = FakeBracket(other)
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 409, response.text
    assert response.json()["reason"] == "participants_mismatch"
    assert bracket.calls["put"] == []


async def test_21_the_write_uses_the_dedicated_bearer_token(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state()))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200
    assert bracket.calls["tokens"] == ["synthetic-jwt"]


async def test_22_a_verified_write_is_written(monkeypatch):
    bracket = FakeBracket(post_match=bracket_match(score1=6, score2=2, court_id=3, custom_duration=8,
                                                  custom_margin=2, round_id=77))
    bracket.match = bracket_match(court_id=3, custom_duration=8, custom_margin=2, round_id=77)
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "written"


@pytest.mark.parametrize("post,reason", [
    (dict(score1=0, score2=0), "post_verify_scores_mismatch"),
    (dict(score1=6, score2=2, round_id=99), "post_verify_round_changed"),
    (dict(score1=6, score2=2, court_id=3), "post_verify_court_changed"),
    (dict(score1=6, score2=2, custom_duration=8), "post_verify_custom_duration_changed"),
    (dict(score1=6, score2=2, custom_margin=2), "post_verify_custom_margin_changed"),
])
async def test_23_a_post_read_that_disagrees_fails_without_a_second_put(monkeypatch, post, reason):
    bracket = FakeBracket(post_match=bracket_match(**post))
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 502, response.text
    assert response.json()["status"] == "failed"
    assert response.json()["reason"] == reason
    assert len(bracket.calls["put"]) == 1, "un HTTP 200 no basta y no se reintenta"


async def test_23b_an_unreadable_post_check_fails(monkeypatch):
    bracket = FakeBracket(read_error=BracketError("Bracket request timed out", 504))
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 504, response.text
    assert len(bracket.calls["put"]) == 1


# --------------------------------------------------------------------------- #
# 24-29: error handling
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("error,expected", [
    (BracketError("Bracket rejected the write token", 502), 502),
    (BracketError("Bracket write is not allowed for this tournament", 502), 502),
    (BracketError("Bracket match not found", 404), 404),
    (BracketError("Bracket write timed out", 504), 504),
    (BracketError("Bracket write returned HTTP 500", 502), 502),
    (BracketError("Bracket rejected the write as a conflict", 409), 409),
])
async def test_24_to_28_upstream_write_failures_are_mapped(monkeypatch, error, expected):
    bracket = FakeBracket(write_error=error)
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == expected, response.text
    assert len(bracket.calls["put"]) == 1
    assert main.result_store.get(result_fingerprint(final_state(6, 2, "a")))["status"] == "failed"


async def test_29_an_invalid_scoreboard_state_fails_closed(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard({"session_id": SESSION, "status": "finished"}))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 502, response.text
    assert response.json()["reason"] == "invalid_scoreboard_state"
    assert bracket.calls == {"read": 0, "login": 0, "put": [], "bodies": [], "tokens": []}


async def test_29b_an_unreadable_bracket_is_mapped(monkeypatch):
    bracket = FakeBracket(payload_error=BracketError("Invalid Bracket JSON response"))
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 502, response.text
    assert bracket.calls["put"] == []


async def test_29c_an_empty_fighter_body_is_refused(monkeypatch):
    state = final_state()
    state["fighter_a"].pop("points")
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(state))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 502
    assert response.json()["reason"] == "invalid_scoreboard_state"
    assert bracket.calls["put"] == []


# --------------------------------------------------------------------------- #
# 30-31: idempotency
# --------------------------------------------------------------------------- #
async def test_30_the_same_frozen_result_is_not_written_twice(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    first, bracket, _ = await post_result(bracket_client=bracket)
    second, bracket, _ = await post_result(bracket_client=bracket)
    assert first.json()["idempotent"] is False and second.json()["idempotent"] is True
    assert second.json()["status"] == "written"
    assert second.json()["fingerprint"] == first.json()["fingerprint"]
    assert len(bracket.calls["put"]) == 1, "ni un PUT mas"


async def test_31_a_different_result_for_the_same_match_never_overwrites(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    first, bracket, _ = await post_result(bracket_client=bracket)
    assert first.json()["status"] == "written"

    # Same match, same session, but a different frozen result.
    bracket.match = bracket_match(score1=6, score2=2)
    wire(monkeypatch, bracket, FakeScoreboard(final_state(9, 0, "a", revision=13)))
    second, bracket, _ = await post_result(bracket_client=bracket)
    assert second.status_code == 409, second.text
    assert second.json()["reason"] == "already_written_different_result"
    assert len(bracket.calls["put"]) == 1


# --------------------------------------------------------------------------- #
# 32-35: exposure, scope and safety nets
# --------------------------------------------------------------------------- #
async def test_32_no_credential_appears_in_the_response_or_the_logs(monkeypatch, caplog):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    with caplog.at_level("DEBUG"):
        response, bracket, _ = await post_result(bracket_client=bracket)
    raw = response.text + caplog.text
    assert WRITE_SECRET not in raw
    assert "synthetic-jwt" not in response.text
    assert WRITE_USER not in raw
    assert "password" not in raw.lower()
    assert "authorization" not in raw.lower()


@pytest.mark.parametrize("tatami", [0, 2, 3, 6])
async def test_33_only_tatami_one_is_served(monkeypatch, tatami):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state()))
    response, bracket, _ = await post_result(bracket_client=bracket, tatami=tatami)
    assert response.status_code == 400, response.text
    assert bracket.calls == {"read": 0, "login": 0, "put": [], "bodies": [], "tokens": []}


async def test_34_an_unreachable_scoreboard_is_reported(monkeypatch):
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(None, error=ScoreboardError("Scoreboard request failed", 502)))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 502, response.text
    assert bracket.calls["put"] == []


async def test_34b_a_missing_scoreboard_token_is_not_bypassed(monkeypatch):
    monkeypatch.setattr(settings, "scoreboard_internal_token", "")
    real_read_state = main.scoreboard_client.read_state
    client = main.ScoreboardClient()
    wire(monkeypatch, FakeBracket(), FakeScoreboard(final_state()))
    with pytest.raises(ScoreboardError):
        await client.read_state(1)
    assert real_read_state is not None


async def test_34c_without_write_credentials_nothing_is_read_or_written(monkeypatch):
    class NoCredentials:
        write_configured = False

        async def read_match(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("no debe leerse Bracket sin credenciales")

        async def login(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("no debe pedirse token sin credenciales")

        async def update_match(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("no debe escribirse sin credenciales")

    scoreboard = FakeScoreboard(final_state())
    monkeypatch.setattr(main, "bracket_client", NoCredentials())
    monkeypatch.setattr(main, "scoreboard_client", scoreboard)
    response, _, _ = await post_result()
    assert response.status_code == 503, response.text
    assert response.json() == {"tatami_id": 1, "status": "failed", "reason": "bracket_write_not_configured",
                               "idempotent": False, "fingerprint": None, "tournament_id": None,
                               "match_id": None, "session_id": None, "revision": None,
                               "winner_team_id": None, "scores": None}


async def test_35_no_test_here_can_reach_a_real_service(monkeypatch):
    """A booby-trapped httpx client: any real request attempt fails the suite."""

    class Bomb:
        def __init__(self, *args, **kwargs):
            raise AssertionError("los tests no deben construir un cliente HTTP real")

    monkeypatch.setattr("app.bracket_client.httpx.AsyncClient", Bomb)
    monkeypatch.setattr("app.scoreboard_client.httpx.AsyncClient", Bomb)
    bracket = FakeBracket()
    wire(monkeypatch, bracket, FakeScoreboard(final_state(6, 2, "a")))
    response, bracket, _ = await post_result(bracket_client=bracket)
    assert response.status_code == 200 and response.json()["status"] == "written"
    assert settings.bracket_api_url.startswith("http://") and "oracle" not in settings.bracket_api_url
    assert bracket.calls["put"] == [(TOURNAMENT_ID, MATCH_ID)]


# --------------------------------------------------------------------------- #
# Fingerprint (P2.4D §4) — pure function, no I/O
# --------------------------------------------------------------------------- #
def test_fingerprint_is_deterministic_and_versioned():
    first, second = result_fingerprint(final_state(6, 2, "a")), result_fingerprint(final_state(6, 2, "a"))
    assert first == second and len(first) == 64
    assert first.startswith  # noqa: B018 - readability only
    assert FINGERPRINT_VERSION == "v1"
    assert result_fingerprint(final_state(6, 2, "a")) != result_fingerprint(final_state(2, 6, "b"))


@pytest.mark.parametrize("mutation", [
    {"points_a": 7}, {"points_b": 3}, {"winner": "b"}, {"method": "decision"},
    {"session_id": "other-session"}, {"revision": 13}, {"advantages_a": 1}, {"advantages_b": 2},
    {"penalties_a": 1}, {"penalties_b": 2}, {"match_id": 41}, {"tournament_id": 8},
])
def test_fingerprint_changes_with_the_result(mutation):
    base = final_state(6, 2, "a")
    changed = final_state(6, 2, "a")
    if "winner" in mutation:
        changed["winner_team_id"] = TEAM_B if mutation["winner"] == "b" else TEAM_A
    for key, value in mutation.items():
        if key == "winner":
            continue
        if key in ("points_a", "points_b", "advantages_a", "advantages_b", "penalties_a", "penalties_b"):
            side = "a" if key.endswith("_a") else "b"
            changed[f"fighter_{side}"][key.rsplit("_", 1)[0]] = value
        else:
            changed[key] = value
    assert result_fingerprint(changed) != result_fingerprint(base)


def test_fingerprint_carries_no_names_or_secrets():
    state = final_state(6, 2, "a")
    state["fighter_a"]["name"] = "Nombre Real De Una Persona"
    state["internal_token"] = "synthetic-internal-token"
    assert result_fingerprint(state) == result_fingerprint(final_state(6, 2, "a"))


def test_the_gate_is_pure_and_never_needs_io():
    gate = evaluate(final_state(6, 2, "a"), {"tournament_id": TOURNAMENT_ID, "match_id": MATCH_ID,
                                             "session_id": SESSION, "expected_revision": None})
    assert gate.decision == "write" and gate.points_a == 6 and gate.points_b == 2
    assert gate.team_ids == (TEAM_A, TEAM_B)

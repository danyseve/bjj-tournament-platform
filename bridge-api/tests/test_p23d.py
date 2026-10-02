import asyncio
import json

import httpx
import pytest

REAL_ASYNC_CLIENT = httpx.AsyncClient
TOKEN = "synthetic-internal-token"


class ApiClient:
    def __init__(self, app):
        self.app = app

    def post(self, path, **kwargs):
        async def request():
            async with REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=self.app),
                                         base_url="http://bridge.test") as client:
                return await client.post(path, **kwargs)
        return asyncio.run(request())


def stages():
    def participant(i, name):
        return {"id": i, "tournament_id": 7, "stage_item_id": 20,
                "team_id": i + 100, "team": {"id": i + 100, "name": name,
                "tournament_id": 7, "players": [{"name": "Never Player"}]}}
    match = {"id": 40, "round_id": 30, "duration_minutes": 5,
             "custom_duration_minutes": None, "margin_minutes": 9,
             "stage_item_input1_id": 1, "stage_item_input2_id": 2,
             "stage_item_input1": participant(1, "Ana"),
             "stage_item_input2": participant(2, "Bea")}
    return {"data": [{"id": 10, "tournament_id": 7, "stage_items": [
        {"id": 20, "stage_id": 10, "name": "Adult / Blue / 70kg", "rounds": [
            {"id": 30, "stage_item_id": 20, "is_draft": False, "matches": [match]}]}]}]}


def normalized():
    from app import bracket_client as bc
    match, category = bc.locate_match(stages(), 7, 40)
    return bc.normalize_match(match, category, 7).model_dump()


SNAPSHOT = {"session_id": "synthetic-session", "revision": 1, "match_id": 40,
            "fighter_a": {"name": "Ana", "points": 0, "advantages": 0, "penalties": 0},
            "fighter_b": {"name": "Bea", "points": 0, "advantages": 0, "penalties": 0},
            "remaining_seconds": 300, "status": "ready"}


def configure(monkeypatch, scoreboard):
    """Wire a two-sided mock transport: GET -> Bracket, PUT -> Scoreboard."""
    from app import main
    seen = []

    def handler(request):
        if request.method == "GET":
            seen.append(request)
            return httpx.Response(200, json=stages())
        seen.append(request)
        return scoreboard(request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: REAL_ASYNC_CLIENT(
        transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(main.scoreboard_client, "token", TOKEN)
    main.scoreboard_client.tatami_urls[1] = "http://scoreboard.test:3000"
    return main, seen


def post_assign(app, tatami=1, **overrides):
    payload = {"tatami_id": tatami, "tournament_id": 7, "match_id": 40}
    payload.update(overrides)
    return ApiClient(app).post(f"/tatamis/{tatami}/assign-match", json=payload)


def test_01_bridge_normalizes_and_sends_real_assignment(monkeypatch):
    main, seen = configure(monkeypatch, lambda r: httpx.Response(201, json={"state": SNAPSHOT}))
    response = post_assign(main.app)
    assert response.status_code == 201
    assert [r.method for r in seen] == ["GET", "PUT"]
    put = seen[1]
    assert str(put.url) == "http://scoreboard.test:3000/internal/tatamis/1/assignment"
    assert put.headers["x-internal-token"] == TOKEN
    assert json.loads(put.content) == normalized()
    body = response.json()
    assert body["status"] == "assigned"
    assert body["scoreboard_sent"] is True
    assert body["match"] == normalized()
    assert body["state"] == SNAPSHOT


def test_02_scoreboard_created_is_real_success(monkeypatch):
    main, _ = configure(monkeypatch, lambda r: httpx.Response(201, json={"state": SNAPSHOT}))
    response = post_assign(main.app)
    assert response.status_code == 201
    assert response.json()["status"] == "assigned" and response.json()["scoreboard_sent"] is True


def test_03_scoreboard_replay_is_real_success(monkeypatch):
    main, _ = configure(monkeypatch, lambda r: httpx.Response(200, json={"state": SNAPSHOT}))
    response = post_assign(main.app)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "replayed" and body["scoreboard_sent"] is True
    assert body["state"] == SNAPSHOT


def test_04_scoreboard_conflict_is_reflected(monkeypatch):
    main, _ = configure(monkeypatch, lambda r: httpx.Response(409, json={"error": "conflict"}))
    response = post_assign(main.app)
    assert response.status_code == 409
    assert "conflict" in response.json()["detail"].lower()
    assert "scoreboard_sent" not in response.text


def test_05_scoreboard_timeout_is_not_success(monkeypatch):
    def scoreboard(request):
        raise httpx.ReadTimeout("timeout", request=request)
    main, _ = configure(monkeypatch, scoreboard)
    response = post_assign(main.app)
    assert response.status_code == 504
    assert "timed out" in response.json()["detail"].lower()


def test_06_scoreboard_connection_failure_is_not_success(monkeypatch):
    def scoreboard(request):
        raise httpx.ConnectError("refused", request=request)
    main, _ = configure(monkeypatch, scoreboard)
    response = post_assign(main.app)
    assert response.status_code == 502


@pytest.mark.parametrize("status", [500, 502, 503])
def test_07_scoreboard_5xx_is_gateway_error(monkeypatch, status):
    main, _ = configure(monkeypatch, lambda r: httpx.Response(status, text="upstream boom"))
    response = post_assign(main.app)
    assert response.status_code == 502
    assert "boom" not in response.text


@pytest.mark.parametrize("scoreboard", [
    lambda r: httpx.Response(200, text="not json"),
    lambda r: httpx.Response(200, json={"state": None}),
    lambda r: httpx.Response(200, json={"state": {}}),
    lambda r: httpx.Response(200, json=["unexpected"]),
])
def test_08_invalid_scoreboard_response_is_rejected(monkeypatch, scoreboard):
    main, _ = configure(monkeypatch, scoreboard)
    response = post_assign(main.app)
    assert response.status_code == 502
    assert "scoreboard_sent" not in response.text


def test_09_internal_token_never_leaks_in_error_or_success(monkeypatch):
    main, _ = configure(monkeypatch, lambda r: httpx.Response(500, text="x"))
    assert TOKEN not in post_assign(main.app).text
    main, _ = configure(monkeypatch, lambda r: httpx.Response(201, json={"state": SNAPSHOT}))
    assert TOKEN not in post_assign(main.app).text


def test_10_missing_token_is_reported_not_disguised(monkeypatch):
    main, seen = configure(monkeypatch, lambda r: httpx.Response(201, json={"state": SNAPSHOT}))
    monkeypatch.setattr(main.scoreboard_client, "token", "")
    response = post_assign(main.app)
    assert response.status_code == 502
    assert [r.method for r in seen] == ["GET"]


def test_11_tatami_other_than_one_is_rejected_without_transport(monkeypatch):
    from app import main
    from app.scoreboard_client import ScoreboardClient, ScoreboardError
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: pytest.fail("No transport"))
    assert post_assign(main.app, tatami=2, tatami_id=1).status_code == 400
    assert post_assign(main.app, tatami=2, tatami_id=2).status_code == 422
    assert post_assign(main.app, tatami=1, tatami_id=2).status_code == 422
    for tatami in (0, 2, 6, -1):
        with pytest.raises(ScoreboardError) as exc:
            asyncio.run(ScoreboardClient().assign_match(tatami, normalized()))
        assert exc.value.status_code == 400


def test_12_result_endpoint_stays_disabled(monkeypatch):
    from app import main
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: pytest.fail("No transport"))
    response = ApiClient(main.app).post("/tatamis/1/result", json={"winner": "red"})
    assert response.status_code == 501
    assert "disabled" in response.json()["detail"].lower()


def test_13_bracket_failure_never_touches_scoreboard(monkeypatch):
    from app import main
    seen = []

    def handler(request):
        seen.append(request.method)
        return httpx.Response(500, text="bracket down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: REAL_ASYNC_CLIENT(
        transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(main.scoreboard_client, "token", TOKEN)
    assert post_assign(main.app).status_code == 502
    assert seen == ["GET"]

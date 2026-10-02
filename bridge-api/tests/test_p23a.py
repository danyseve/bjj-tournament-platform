import asyncio

import httpx
import pytest
from app import bracket_client as bc

REAL_ASYNC_CLIENT = httpx.AsyncClient


class ApiClient:
    """In-process ASGI requests; upstream remains separately mocked."""
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


def test_fetch_uses_configured_api_url_and_public_rounds(monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=stages())
    real_client = httpx.AsyncClient
    monkeypatch.setattr(bc.httpx, "AsyncClient", lambda **kw: real_client(
        transport=httpx.MockTransport(handler), **kw))
    client = bc.BracketClient()
    client.base_url = "https://bracket.invalid/custom/api"
    assert asyncio.run(client.fetch_stages(7)) == stages()
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert str(seen[0].url) == "https://bracket.invalid/custom/api/tournaments/7/stages?no_draft_rounds=true"


def test_locate_and_normalize_resolved_teams():
    match, category = bc.locate_match(stages(), 7, 40)
    result = bc.normalize_match(match, category, 7).model_dump()
    assert result == {"tournament_id": 7, "match_id": 40, "tatami_id": 1,
                      "fighter_a": {"stage_item_input_id": 1, "team_id": 101, "name": "Ana", "club": None},
                      "fighter_b": {"stage_item_input_id": 2, "team_id": 102, "name": "Bea", "club": None},
                      "category": {"stage_item_id": 20, "name": "Adult / Blue / 70kg"},
                      "duration_seconds": 300}


@pytest.mark.parametrize("minutes,expected", [(1, 60), (7, 420)])
def test_custom_duration_precedence(minutes, expected):
    match, category = bc.locate_match(stages(), 7, 40)
    match["custom_duration_minutes"] = minutes
    match["duration_minutes"] = None
    assert bc.normalize_match(match, category, 7).duration_seconds == expected


@pytest.mark.parametrize("field", ["duration_minutes", "custom_duration_minutes"])
@pytest.mark.parametrize("bad", [0, -1, True, False, 2.5, 5.0, "5", None])
def test_invalid_duration_is_rejected(field, bad):
    match, category = bc.locate_match(stages(), 7, 40)
    if field == "custom_duration_minutes" and bad is None:
        match["duration_minutes"] = None
    match[field] = bad
    with pytest.raises(ValueError):
        bc.normalize_match(match, category, 7)


def mutate(payload, path, value):
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


S = ("data", 0)
C = S + ("stage_items", 0)
R = C + ("rounds", 0)
M = R + ("matches", 0)


@pytest.mark.parametrize("side", [1, 2])
@pytest.mark.parametrize("path,value", [
    (S + ("tournament_id",), 8), (C + ("stage_id",), 99),
    (R + ("stage_item_id",), 99), (M + ("round_id",), 99),
    (R + ("is_draft",), True),
    (M + ("stage_item_input1", "tournament_id"), 8),
    (M + ("stage_item_input1", "stage_item_id"), 99),
    (M + ("stage_item_input1", "id"), 99),
    (M + ("stage_item_input1", "team", "id"), 99),
    (M + ("stage_item_input1", "team", "tournament_id"), 8),
    (M + ("stage_item_input1", "team_id"), None),
    (M + ("stage_item_input1", "team"), None),
    (M + ("stage_item_input1",), None),
    (M + ("stage_item_input1", "team", "name"), " "),
    (C + ("name",), ""), (M + ("id",), True),
    (M + ("stage_item_input1", "team_id"), True),
])
def test_rejects_wrong_ownership_unresolved_or_malformed(path, value, side):
    path = tuple(key.replace("input1", "input2") if side == 2 and isinstance(key, str) else key for key in path)
    data = stages()
    mutate(data, path, value)
    with pytest.raises(ValueError):
        match, category = bc.locate_match(data, 7, 40)
        bc.normalize_match(match, category, 7)


def test_rejects_identical_participants():
    data = stages()
    match = data["data"][0]["stage_items"][0]["rounds"][0]["matches"][0]
    match["stage_item_input2"]["team_id"] = 101
    match["stage_item_input2"]["team"]["id"] = 101
    with pytest.raises(ValueError):
        m, c = bc.locate_match(data, 7, 40)
        bc.normalize_match(m, c, 7)


@pytest.mark.parametrize("payload", [None, {}, {"data": None}, {"data": {}},
    {"data": [None]}, {"data": [{"id": 1}]}, {"data": ["bad"]}])
def test_invalid_tree(payload):
    with pytest.raises(ValueError):
        bc.locate_match(payload, 7, 40)


def test_missing_match():
    with pytest.raises(ValueError, match="not found"):
        bc.locate_match(stages(), 7, 999)


def test_assign_api_normalizes_and_delivers_to_scoreboard(monkeypatch):
    from app import main
    seen = []
    match, category = bc.locate_match(stages(), 7, 40)
    normalized = bc.normalize_match(match, category, 7).model_dump()
    snapshot = {"session_id": "synthetic-session", "revision": 1}
    def handler(request):
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=stages())
        return httpx.Response(201, json={"state": snapshot})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(bc.httpx, "AsyncClient", lambda **kw: real_client(
        transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(main.scoreboard_client, "token", "synthetic-internal-token")
    response = ApiClient(main.app).post("/tatamis/1/assign-match",
        json={"tatami_id": 1, "tournament_id": 7, "match_id": 40})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "assigned"
    assert body["scoreboard_sent"] is True
    assert body["match"] == normalized
    assert body["state"] == snapshot
    assert [r.method for r in seen] == ["GET", "PUT"]
    assert seen[1].url.path == "/internal/tatamis/1/assignment"
    assert seen[1].headers["x-internal-token"] == "synthetic-internal-token"


@pytest.mark.parametrize("change", [{"tatami_id": 2}, {"tatami_id": True},
    {"tatami_id": "1"}, {"tatami_id": 1.0}, {"red": {}}, {"blue": {}},
    {"duration_seconds": 100}, {"tournament_id": True}, {"match_id": "40"},
    {"match_id": 0}, {"tournament_id": -1}])
def test_assign_api_forbids_legacy_extra_or_invalid_fields(monkeypatch, change):
    from app import main
    def forbidden(**kw):
        pytest.fail("Invalid request must not contact upstream")
    monkeypatch.setattr(bc.httpx, "AsyncClient", forbidden)
    payload = {"tatami_id": 1, "tournament_id": 7, "match_id": 40, **change}
    assert ApiClient(main.app).post("/tatamis/1/assign-match", json=payload).status_code == 422


def test_assign_rejects_path_tatami_without_transport(monkeypatch):
    from app import main
    monkeypatch.setattr(bc.httpx, "AsyncClient", lambda **kw: pytest.fail("No transport"))
    assert ApiClient(main.app).post("/tatamis/2/assign-match",
        json={"tatami_id": 1, "tournament_id": 7, "match_id": 40}).status_code == 400


@pytest.mark.parametrize("payload", [None, {}, {"tatami": 1, "match_id": 40, "winner": "red"}])
def test_result_is_explicitly_disabled_without_writes(monkeypatch, payload):
    from app import main
    monkeypatch.setattr(bc.httpx, "AsyncClient", lambda **kw: pytest.fail("No transport"))
    response = ApiClient(main.app).post("/tatamis/1/result", json=payload)
    assert response.status_code == 501
    assert "disabled" in response.json()["detail"].lower()


@pytest.mark.parametrize("scenario,expected", [("timeout", 504), ("connect", 502),
    (401, 401), (403, 403), (404, 404), (500, 502), (302, 502),
    ("json", 502), ("shape", 502), ("missing", 404), ("ownership", 502)])
def test_upstream_failures_are_controlled_api_responses(monkeypatch, scenario, expected):
    from app import main
    def handler(request):
        if scenario == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if scenario == "connect":
            raise httpx.ConnectError("unreachable", request=request)
        if type(scenario) is int:
            return httpx.Response(scenario, text="sensitive upstream detail")
        if scenario == "json":
            return httpx.Response(200, text="not json")
        if scenario == "shape":
            return httpx.Response(200, json={"data": None})
        data = stages()
        if scenario == "missing":
            mutate(data, M + ("id",), 41)
        if scenario == "ownership":
            mutate(data, S + ("tournament_id",), 8)
        return httpx.Response(200, json=data)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(bc.httpx, "AsyncClient", lambda **kw: real_client(
        transport=httpx.MockTransport(handler), **kw))
    response = ApiClient(main.app).post("/tatamis/1/assign-match",
        json={"tatami_id": 1, "tournament_id": 7, "match_id": 40})
    assert response.status_code == expected
    assert "sensitive" not in response.text



def test_rejects_same_input_even_with_contradictory_team_objects():
    m, c = bc.locate_match(stages(), 7, 40)
    m["stage_item_input2_id"] = 1
    m["stage_item_input2"]["id"] = 1
    with pytest.raises(ValueError, match="distinct"):
        bc.normalize_match(m, c, 7)


@pytest.mark.parametrize("path,value", [
    (M + ("duration_minutes",), True), (M + ("duration_minutes",), 2.5),
    (M + ("custom_duration_minutes",), 0),
    (M + ("stage_item_input2", "team_id"), None),
    (M + ("stage_item_input2", "team", "tournament_id"), 8),
    (C + ("name",), None), (R + ("matches",), None)])
def test_malformed_match_api_never_sends_scoreboard(monkeypatch, path, value):
    from app import main
    data = stages()
    mutate(data, path, value)
    seen = []
    def handler(request):
        seen.append(request.method)
        return httpx.Response(200, json=data)
    monkeypatch.setattr(bc.httpx, "AsyncClient", lambda **kw: REAL_ASYNC_CLIENT(
        transport=httpx.MockTransport(handler), **kw))
    response = ApiClient(main.app).post("/tatamis/1/assign-match",
        json={"tatami_id": 1, "tournament_id": 7, "match_id": 40})
    assert response.status_code == 502
    assert seen == ["GET"]


@pytest.mark.parametrize("missing", ["tatami_id", "tournament_id", "match_id"])
def test_assign_requires_all_three_fields(monkeypatch, missing):
    from app import main
    monkeypatch.setattr(bc.httpx, "AsyncClient", lambda **kw: pytest.fail("No transport"))
    payload = {"tatami_id": 1, "tournament_id": 7, "match_id": 40}
    del payload[missing]
    assert ApiClient(main.app).post("/tatamis/1/assign-match", json=payload).status_code == 422


def test_duplicate_match_is_ambiguous():
    data = stages()
    matches = data["data"][0]["stage_items"][0]["rounds"][0]["matches"]
    matches.append(matches[0].copy())
    with pytest.raises(ValueError, match="Duplicate"):
        bc.locate_match(data, 7, 40)

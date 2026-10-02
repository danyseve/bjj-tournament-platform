"""P2.4A: the candidate list is read-only, the ordering is Bracket's own and the
assignment stays an explicit operator action."""
import httpx
import pytest

from app import main
from app.bracket_client import BracketClient, collect_candidates
from app.config import settings
from app.scoreboard_client import ScoreboardError

pytestmark = pytest.mark.anyio
RealAsyncClient = httpx.AsyncClient

ITEM_ID = 2
CANDIDATE_KEYS = ["category", "duration_seconds", "fighter_a", "fighter_b", "match_id", "tournament_id"]


def fighter_input(input_id, team_id, tournament_id=1, item_id=ITEM_ID, team_name=None,
                  winner_from_stage_item_id=None):
    return {
        "id": input_id, "slot": 1, "tournament_id": tournament_id, "stage_item_id": item_id,
        "team_id": team_id, "winner_from_stage_item_id": winner_from_stage_item_id, "winner_position": None,
        "team": None if team_id is None else {"id": team_id, "name": team_name or f"Team {team_id}",
                                              "tournament_id": tournament_id},
    }


def match(match_id, input1, input2, duration=10, custom=None, winner_from_match1=None, winner_from_match2=None):
    return {
        "id": match_id, "round_id": None, "duration_minutes": duration, "custom_duration_minutes": custom,
        "stage_item_input1_id": None if input1 is None else input1["id"],
        "stage_item_input2_id": None if input2 is None else input2["id"],
        "stage_item_input1": input1, "stage_item_input2": input2,
        "stage_item_input1_winner_from_match_id": winner_from_match1,
        "stage_item_input2_winner_from_match_id": winner_from_match2,
        "stage_item_input1_conflict": False, "stage_item_input2_conflict": False,
        "stage_item_input1_score": 5, "stage_item_input2_score": 5,
        "court_id": None, "position_in_schedule": None, "start_time": None,
    }


def round_(round_id, matches, draft=False):
    for item in matches:
        item["round_id"] = round_id
    return {"id": round_id, "stage_item_id": ITEM_ID, "is_draft": draft, "matches": matches}


def payload(tournament_id=1):
    """El orden recibido es 9, 4, 5: ni ascendente ni descendente, asi que un sort se nota."""
    return {
        "data": [
            {
                "id": 1, "tournament_id": tournament_id, "name": "Group Stage",
                "stage_items": [
                    {
                        "id": ITEM_ID, "stage_id": 1, "name": "Synthetic Adult",
                        "rounds": [
                            round_(9, [
                                match(9, fighter_input(3, 103, team_name="Ana"), fighter_input(4, 104, team_name="Bea"), custom=7),
                                match(24, fighter_input(5, 105), fighter_input(6, 106), duration=0),
                                match(26, fighter_input(7, 107), fighter_input(8, 107)),
                                match(27, fighter_input(1, 108), fighter_input(1, 109)),
                            ]),
                            round_(5, [
                                match(4, fighter_input(9, 110, winner_from_stage_item_id=1), fighter_input(10, 111, winner_from_stage_item_id=2)),
                                match(5, fighter_input(1, 101, team_name="Cira"), fighter_input(2, 102, team_name="Dani")),
                                match(22, None, None, winner_from_match1=13),
                                match(23, fighter_input(11, 112), fighter_input(12, None)),
                                match(25, fighter_input(13, 113), fighter_input(14, 114), duration="ten"),
                            ]),
                            round_(7, [match(21, fighter_input(15, 115), fighter_input(16, 116))], draft=True),
                        ],
                    }
                ],
            }
        ]
    }


def duplicated_payload():
    """El mismo match_id dos veces: la asignacion no puede resolverlo, asi que no se lista."""
    body = payload()
    rounds = body["data"][0]["stage_items"][0]["rounds"]
    rounds[1]["matches"].append(match(5, fighter_input(19, 119), fighter_input(20, 120)))
    for item in rounds[1]["matches"]:
        item["round_id"] = 5
    return body


def busy_state(match_id, tournament_id=1):
    return {"session_id": "synthetic-session-a", "revision": 3, "tatami_id": 1, "tournament_id": tournament_id,
            "match_id": match_id, "status": "running"}


async def get_candidates(monkeypatch, path="/tatamis/1/candidates?tournament_id=1", body=None, state=None):
    async def fetch_stages(tournament_id):
        return payload() if body is None else body

    async def read_state(tatami):
        return state

    monkeypatch.setattr(main.bracket_client, "fetch_stages", fetch_stages)
    monkeypatch.setattr(main.scoreboard_client, "read_state", read_state)
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        return await client.get(path)


async def test_1_candidates_are_the_playable_matches_in_payload_order(monkeypatch):
    response = await get_candidates(monkeypatch)
    assert response.status_code == 200
    body = response.json()
    assert body["scoreboard_read"] is True and body["active_match_id"] is None
    candidates = body["candidates"]
    assert [item["match_id"] for item in candidates] == [9, 4, 5]
    first = candidates[0]
    assert first["tournament_id"] == 1
    assert first["duration_seconds"] == 420, "custom_duration_minutes manda"
    assert first["fighter_a"] == {"stage_item_input_id": 3, "team_id": 103, "name": "Ana", "club": None}
    assert first["fighter_b"]["team_id"] == 104
    assert first["category"] == {"stage_item_id": ITEM_ID, "name": "Synthetic Adult"}
    # Pases pendientes pero equipo ya resuelto: candidato real, no se infiere nada.
    assert candidates[1]["match_id"] == 4 and candidates[1]["fighter_a"]["team_id"] == 110
    assert candidates[2]["match_id"] == 5 and candidates[2]["duration_seconds"] == 600
    assert candidates[2]["fighter_b"]["name"] == "Dani"


async def test_2_pending_input_is_excluded(monkeypatch):
    body = (await get_candidates(monkeypatch)).json()
    assert 22 not in [item["match_id"] for item in body["candidates"]]


async def test_3_missing_team_is_excluded(monkeypatch):
    body = (await get_candidates(monkeypatch)).json()
    assert 23 not in [item["match_id"] for item in body["candidates"]]


async def test_4_duplicated_identities_are_excluded(monkeypatch):
    body = (await get_candidates(monkeypatch)).json()
    ids = [item["match_id"] for item in body["candidates"]]
    assert 26 not in ids, "mismo team_id en ambos lados"
    assert 27 not in ids, "mismo stage_item_input_id en ambos lados"


async def test_5_invalid_durations_are_excluded(monkeypatch):
    body = (await get_candidates(monkeypatch)).json()
    ids = [item["match_id"] for item in body["candidates"]]
    assert 24 not in ids, "duration_minutes = 0"
    assert 25 not in ids, "duration_minutes no numerica"


async def test_6_draft_rounds_are_excluded(monkeypatch):
    body = (await get_candidates(monkeypatch)).json()
    assert 21 not in [item["match_id"] for item in body["candidates"]]


async def test_7_a_foreign_tournament_stage_is_refused(monkeypatch):
    foreign = payload()
    foreign["data"][0]["tournament_id"] = 9
    response = await get_candidates(monkeypatch, body=foreign)
    assert response.status_code == 502, response.text
    assert response.json()["detail"] == "Bracket ownership mismatch: tournament_id"


async def test_8_order_is_the_received_order_not_sorted_by_id(monkeypatch):
    body = (await get_candidates(monkeypatch)).json()
    ids = [item["match_id"] for item in body["candidates"]]
    assert ids == [9, 4, 5]
    assert ids != sorted(ids, reverse=True), "no se ordena por match_id descendente"
    assert ids != sorted(ids), "no se ordena por match_id ascendente"


async def test_9_the_response_carries_nothing_else(monkeypatch):
    body = (await get_candidates(monkeypatch)).json()
    assert sorted(body.keys()) == ["active_match_id", "candidates", "scoreboard_read", "tournament_id"]
    for item in body["candidates"]:
        assert sorted(item.keys()) == CANDIDATE_KEYS
        assert sorted(item["fighter_a"].keys()) == ["club", "name", "stage_item_input_id", "team_id"]
        assert sorted(item["category"].keys()) == ["name", "stage_item_id"]
    raw = str(body)
    for forbidden in ("stage_item_input1_score", "winner_from", "court", "position_in_schedule", "start_time", "is_draft"):
        assert forbidden not in raw, forbidden


async def test_10_a_busy_tatami_keeps_the_listing_alive_and_hides_the_active_match(monkeypatch):
    body = (await get_candidates(monkeypatch, state=busy_state(5, tournament_id=1))).json()
    assert body["scoreboard_read"] is True and body["active_match_id"] == 5
    assert [item["match_id"] for item in body["candidates"]] == [9, 4]
    other_tournament = (await get_candidates(monkeypatch, state=busy_state(5, tournament_id=9))).json()
    assert other_tournament["active_match_id"] is None, "el match activo de otro torneo no se descuenta"


async def test_10b_an_unreadable_scoreboard_does_not_invent_a_list(monkeypatch):
    async def fetch_stages(tournament_id):
        return payload()

    async def failing_read_state(tatami):
        raise ScoreboardError("Scoreboard request failed", 502)

    monkeypatch.setattr(main.bracket_client, "fetch_stages", fetch_stages)
    monkeypatch.setattr(main.scoreboard_client, "read_state", failing_read_state)
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        response = await client.get("/tatamis/1/candidates?tournament_id=1")
    body = response.json()
    assert response.status_code == 200 and body["scoreboard_read"] is False and body["active_match_id"] is None
    assert [item["match_id"] for item in body["candidates"]] == [9, 4, 5]


async def test_11_assigning_another_match_is_still_409(monkeypatch):
    async def fetch_stages(tournament_id):
        return payload()

    async def refuse(tatami, payload_):
        raise ScoreboardError("Scoreboard rejected the assignment as a conflict", 409)

    monkeypatch.setattr(main.bracket_client, "fetch_stages", fetch_stages)
    monkeypatch.setattr(main.scoreboard_client, "assign_match", refuse)
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        response = await client.post("/tatamis/1/assign-match", json={"tatami_id": 1, "tournament_id": 1, "match_id": 5})
    assert response.status_code == 409


async def test_12_after_a_release_a_new_assignment_is_accepted(monkeypatch):
    async def fetch_stages(tournament_id):
        return payload()

    async def empty_state(tatami):
        return None

    async def deliver(tatami, payload_):
        return {"status": "assigned", "state": {"session_id": "synthetic-session-b", "revision": 1, "match_id": payload_["match_id"]}}

    monkeypatch.setattr(main.bracket_client, "fetch_stages", fetch_stages)
    monkeypatch.setattr(main.scoreboard_client, "read_state", empty_state)
    monkeypatch.setattr(main.scoreboard_client, "assign_match", deliver)
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        listing = await client.get("/tatamis/1/candidates?tournament_id=1")
        assert 5 in [item["match_id"] for item in listing.json()["candidates"]], "el tatami liberado devuelve el match a la lista"
        assigned = await client.post("/tatamis/1/assign-match", json={"tatami_id": 1, "tournament_id": 1, "match_id": 5})
    assert assigned.status_code == 201 and assigned.json()["state"]["session_id"] == "synthetic-session-b"


def recording_client(monkeypatch, bracket_payload):
    """Enruta y registra toda llamada httpx, para poder afirmar 'solo lectura'."""
    bracket_requests, scoreboard_requests = [], []

    def handler(request):
        url = str(request.url)
        if url.startswith(settings.bracket_api_url):
            bracket_requests.append((request.method, url))
            return httpx.Response(200, json=bracket_payload)
        scoreboard_requests.append((request.method, url))
        if request.method == "PUT":
            return httpx.Response(201, json={"tatami_id": 1, "state": {
                "session_id": "synthetic-session-c", "revision": 1, "match_id": 9}})
        return httpx.Response(200, json={"tatami_id": 1, "state": None})

    class Factory:
        def __init__(self, *args, **kwargs):
            self._client = RealAsyncClient(transport=httpx.MockTransport(handler))

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *exc):
            await self._client.aclose()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: Factory())
    monkeypatch.setattr(main, "bracket_client", BracketClient())
    monkeypatch.setattr(main.scoreboard_client, "token", "synthetic-internal-token")
    return bracket_requests, scoreboard_requests


async def test_13_listing_never_writes_to_bracket(monkeypatch):
    bracket_requests, scoreboard_requests = recording_client(monkeypatch, payload())
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        listing = await client.get("/tatamis/1/candidates?tournament_id=1")
        await client.post("/tatamis/1/assign-match", json={"tatami_id": 1, "tournament_id": 1, "match_id": 9})
    assert listing.status_code == 200
    assert bracket_requests, "la lista se construye sobre Bracket READ"
    assert {method for method, _ in bracket_requests} == {"GET"}
    assert {url for _, url in bracket_requests} == {f"{settings.bracket_api_url}/tournaments/1/stages?no_draft_rounds=true"}
    assert all("/result" not in url for _, url in bracket_requests + scoreboard_requests)


async def test_14_the_result_endpoint_is_still_501(monkeypatch):
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        for tatami_id in (1, 2, 6):
            assert (await client.post(f"/tatamis/{tatami_id}/result")).status_code == 501


async def test_15_the_scoreboard_contact_is_read_only_and_legacy_free(monkeypatch):
    bracket_requests, scoreboard_requests = recording_client(monkeypatch, payload())
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        response = await client.get("/tatamis/1/candidates?tournament_id=1")
        await client.post("/tatamis/1/assign-match", json={"tatami_id": 1, "tournament_id": 1, "match_id": 9})
    assert response.status_code == 200
    base = main.scoreboard_client.tatami_urls[main.scoreboard_client.ENABLED_TATAMI]
    assert scoreboard_requests == [
        ("GET", f"{base}/internal/tatamis/1/state"),
        ("PUT", f"{base}/internal/tatamis/1/assignment"),
    ], scoreboard_requests
    assert all("/bjj" not in url for _, url in scoreboard_requests)


async def test_16_a_duplicated_match_id_is_never_listed(monkeypatch):
    body = (await get_candidates(monkeypatch, body=duplicated_payload())).json()
    ids = [item["match_id"] for item in body["candidates"]]
    assert 5 not in ids, "la asignacion no podria resolverlo"
    assert ids == [9, 4]


async def test_17_only_tatami_one_and_a_valid_tournament_are_accepted(monkeypatch):
    assert (await get_candidates(monkeypatch, path="/tatamis/2/candidates?tournament_id=1")).status_code == 400
    assert (await get_candidates(monkeypatch, path="/tatamis/1/candidates?tournament_id=0")).status_code == 400
    assert (await get_candidates(monkeypatch, path="/tatamis/1/candidates?tournament_id=-3")).status_code == 400
    assert (await get_candidates(monkeypatch, path="/tatamis/1/candidates")).status_code == 422


def test_18_the_collector_is_a_pure_reader():
    collected = collect_candidates(payload(), 1)
    assert [item.match_id for item in collected] == [9, 4, 5]
    assert all(item.tatami_id == 1 for item in collected)

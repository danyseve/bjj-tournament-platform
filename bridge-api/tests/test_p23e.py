"""P2.3E guards: the canonical scoreboard never writes results, and the bridge
result endpoint keeps refusing to touch Bracket."""
import httpx
import pytest

from app import main

pytestmark = pytest.mark.anyio


async def test_result_endpoint_refuses_without_touching_bracket(monkeypatch):
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Bracket must not be called for result submission")

    monkeypatch.setattr(main.bracket_client, "health", forbidden)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
        response = await client.post("/tatamis/1/result")
    assert response.status_code in (422, 503), response.status_code
    assert calls == [], "sin identificacion valida no se toca Bracket"


async def test_result_endpoint_serves_only_tatami_1():
    """P2.4D: el 501 se sustituye por una semantica explicita, solo en el tatami 1."""
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
        valid = {"tournament_id": 7, "match_id": 40, "session_id": "synthetic-session"}
        for tatami_id in (2, 6):
            response = await client.post(f"/tatamis/{tatami_id}/result", json=valid)
            assert response.status_code == 400, "fuera del tatami 1 sigue rechazado"
        assert (await client.post("/tatamis/1/result", json=valid)).status_code != 501


def test_scoreboard_contract_has_no_result_write_path():
    """The integrated scoreboard exposes no result endpoint and no outbound call."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "scoreboard-adapter" / "integrated.js").read_text()
    assert "/result" not in source
    assert "bracket" not in source.lower()

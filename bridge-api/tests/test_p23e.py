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
    assert response.status_code == 501
    assert "disabled" in response.json()["detail"]
    assert calls == []


async def test_result_endpoint_is_still_501_for_every_tatami():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
        for tatami_id in (1, 2, 6):
            response = await client.post(f"/tatamis/{tatami_id}/result")
            assert response.status_code == 501


def test_scoreboard_contract_has_no_result_write_path():
    """The integrated scoreboard exposes no result endpoint and no outbound call."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "scoreboard-adapter" / "integrated.js").read_text()
    assert "/result" not in source
    assert "bracket" not in source.lower()

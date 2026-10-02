"""P2.3G guards: releasing a tatami and closing a pending result stay inside the
scoreboard memory. The bridge neither drives nor exposes them."""
import httpx
import pytest

from app import main

pytestmark = pytest.mark.anyio


async def test_result_endpoint_is_still_501_after_the_release_flow():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
        for tatami_id in (1, 2, 6):
            response = await client.post(f"/tatamis/{tatami_id}/result")
            assert response.status_code == 501


def test_bridge_neither_releases_nor_finalizes_a_match():
    """No bridge route, field or scoreboard payload drives finish/clear_match."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    for module in ("main.py", "scoreboard_client.py", "models.py", "config.py"):
        source = (root / module).read_text()
        for forbidden in ("clear_match", "winner_team_id", "expected_revision", "awaiting_result"):
            assert forbidden not in source, (module, forbidden)
    routes = [getattr(route, "path", "") for route in main.app.routes]
    assert not any("clear" in route or "finish" in route for route in routes)
    assert "/tatamis/{tatami_id}/assign-match" in routes

"""P2.3G guards: releasing a tatami and closing a pending result stay inside the
scoreboard memory. The bridge neither drives nor exposes them."""
import httpx
import pytest

from app import main

pytestmark = pytest.mark.anyio


async def test_result_endpoint_after_the_release_flow_is_scoped_to_tatami_1():
    """P2.4D: el endpoint de resultado solo sirve al tatami 1 y ya no es un 501."""
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
        valid = {"tournament_id": 7, "match_id": 40, "session_id": "synthetic-session"}
        for tatami_id in (2, 6):
            response = await client.post(f"/tatamis/{tatami_id}/result", json=valid)
            assert response.status_code == 400, "fuera del tatami 1 sigue rechazado"
        assert (await client.post("/tatamis/1/result", json=valid)).status_code != 501


def test_bridge_neither_releases_nor_finalizes_a_match():
    """No bridge route, field or scoreboard payload drives finish/clear_match."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    # P2.4D: main.py/models.py LEEN winner_team_id, method y revision del estado
    # del scoreboard, pero nada de eso viaja hacia el scoreboard.
    for module in ("scoreboard_client.py", "config.py"):
        source = (root / module).read_text()
        for forbidden in ("clear_match", "winner_team_id", "expected_revision", "awaiting_result"):
            assert forbidden not in source, (module, forbidden)
    from app.models import NormalizedMatch
    outbound = set(NormalizedMatch.model_json_schema()["properties"])
    assert not ({"winner", "winner_team_id", "method", "clear_match", "expected_revision"} & outbound)
    routes = [getattr(route, "path", "") for route in main.app.routes]
    assert not any("clear" in route or "finish" in route for route in routes)
    assert "/tatamis/{tatami_id}/assign-match" in routes

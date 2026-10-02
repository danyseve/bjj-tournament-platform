"""P2.3F guards: finalization lives in the scoreboard memory only. The bridge has
no path, field or payload that carries a winner or a finish method, and the
result endpoint keeps refusing to touch Bracket."""
from pathlib import Path

from app import main


def test_bridge_never_carries_a_winner_or_a_finish_method():
    root = Path(__file__).resolve().parents[2] / "bridge-api" / "app"
    for module in ("main.py", "scoreboard_client.py", "models.py", "config.py"):
        source = (root / module).read_text()
        for forbidden in ("winner", "finish", '"method"', "'method'", "method="):
            assert forbidden not in source, (module, forbidden)


def test_bridge_exposes_no_finish_route_and_result_stays_disabled():
    routes = [getattr(route, "path", "") for route in main.app.routes]
    assert "/tatamis/{tatami_id}/result" in routes
    assert not any("finish" in route for route in routes)

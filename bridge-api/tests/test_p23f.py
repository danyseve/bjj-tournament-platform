"""P2.3F guards: finalization lives in the scoreboard memory only. The bridge has
no path, field or payload that carries a winner or a finish method, and the
result endpoint keeps refusing to touch Bracket."""
from pathlib import Path

from app import main


def test_bridge_never_carries_a_winner_or_a_finish_method():
    """P2.4D: el unico body que el bridge escribe en Bracket son los seis campos de
    MatchBody. El ganador y el metodo se LEEN del scoreboard; jamas viajan en una
    peticion hacia el scoreboard ni hacia Bracket."""
    import json

    from app.bracket_client import match_write_body

    root = Path(__file__).resolve().parents[2] / "bridge-api" / "app"
    body = match_write_body({"round_id": 5, "court_id": None, "custom_duration_minutes": None,
                             "custom_margin_minutes": None}, 6, 2)
    assert sorted(body.keys()) == ["court_id", "custom_duration_minutes", "custom_margin_minutes",
                                   "round_id", "stage_item_input1_score",
                                   "stage_item_input2_score"]
    serialized = json.dumps(body)
    for forbidden in ("winner", "method", "advantages", "penalties"):
        assert forbidden not in serialized, forbidden
    for module in ("scoreboard_client.py", "config.py"):
        source = (root / module).read_text()
        for forbidden in ("winner", "finish", '"method"', "'method'", "method="):
            assert forbidden not in source, (module, forbidden)
    assert "finish" not in (root / "main.py").read_text().replace("finished", "")


def test_bridge_exposes_no_finish_route_and_result_stays_disabled():
    routes = [getattr(route, "path", "") for route in main.app.routes]
    assert "/tatamis/{tatami_id}/result" in routes
    assert not any("finish" in route for route in routes)

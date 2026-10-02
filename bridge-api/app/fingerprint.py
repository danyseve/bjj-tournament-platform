"""Deterministic fingerprint of a finished result (P2.4D).

The fingerprint identifies **the result itself** — what would be written into
Bracket — and nothing about the transport that carried it. Same frozen result
=> same fingerprint; any change in the result => a different fingerprint.

It deliberately contains no token, no cookie and no fighter name: only the
identifiers of the fight, the final revision of the live state, the declared
winner/method and the six numeric scores. Versioned as ``v1`` so a future change
of the composition cannot be confused with an old value.
"""

import hashlib

FINGERPRINT_VERSION = "v1"

SIDES = ("a", "b")
SCORE_FIELDS = ("points", "advantages", "penalties")


class FingerprintError(ValueError):
    """The state does not carry the fields a fingerprint is made of."""


def _int(value, label: str) -> int:
    if type(value) is not int:
        raise FingerprintError(f"{label} must be an integer")
    return value


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FingerprintError(f"{label} must be a non-empty string")
    return value


def fighter_scores(state: dict, side: str) -> tuple[int, int, int]:
    """(points, advantages, penalties) of one side, validated."""
    fighter = state.get(f"fighter_{side}")
    if not isinstance(fighter, dict):
        raise FingerprintError(f"fighter_{side} is missing")
    points, advantages, penalties = (int(_int(fighter.get(field), f"fighter_{side}.{field}")) for field in SCORE_FIELDS)
    return points, advantages, penalties


def result_fingerprint(state: dict) -> str:
    """``sha256(v1|tournament|match|session|revision|winner|method|scores...)``."""
    parts = [FINGERPRINT_VERSION]
    parts.append(str(_int(state.get("tournament_id"), "tournament_id")))
    parts.append(str(_int(state.get("match_id"), "match_id")))
    parts.append(_text(state.get("session_id"), "session_id"))
    parts.append(str(_int(state.get("revision"), "revision")))
    parts.append(str(_int(state.get("winner_team_id"), "winner_team_id")))
    parts.append(_text(state.get("method"), "method"))
    for side in SIDES:
        parts.extend(str(value) for value in fighter_scores(state, side))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

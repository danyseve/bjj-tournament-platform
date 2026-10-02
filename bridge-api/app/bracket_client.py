import httpx

from app.config import settings


class BracketClient:
    def __init__(self):
        self.base_url = settings.bracket_api_url.rstrip("/")

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.base_url}/ping")
            response.raise_for_status()
            return response.json()

    @property
    def write_configured(self) -> bool:
        """Write credentials present? No default value exists, so this is False by default."""
        return settings.bracket_write_configured

    async def fetch_stages(self, tournament_id: int) -> dict:
        """Read public, non-draft stages; never issue upstream writes."""
        positive_int(tournament_id, "tournament_id")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/tournaments/{tournament_id}/stages",
                    params={"no_draft_rounds": "true"},
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise BracketError("Bracket request timed out", 504) from exc
        except httpx.HTTPStatusError as exc:
            upstream_status = exc.response.status_code
            status = upstream_status if upstream_status in (401, 403, 404) else 502
            raise BracketError(f"Bracket returned HTTP {upstream_status}", status) from exc
        except httpx.RequestError as exc:
            raise BracketError("Bracket request failed", 502) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise BracketError("Invalid Bracket JSON response") from exc
        collection(object_value(payload), "data")
        return payload

    async def read_match(self, tournament_id: int, match_id: int) -> dict:
        """Fresh read of one match, right before deciding to write (P2.4D step 5).

        There is no `GET .../matches/{id}` in Bracket, so the match is located
        inside the tournament's own stages payload — the same read the
        assignment path uses. Never trusts a previously cached copy.
        """
        payload = await self.fetch_stages(tournament_id)
        match, _ = locate_match(payload, tournament_id, match_id)
        return match

    async def login(self) -> str:
        """Obtain a Bearer JWT with the dedicated write credentials (P2.4D §13).

        Separate credentials from every other component: the browser token is
        never reused and the value never leaves this method. A rejected
        credential is a bridge-side configuration fault, not a client error, so
        it is reported as a 502 without echoing anything the server said.
        """
        if not self.write_configured:
            raise BracketError("Bracket write credentials are not configured", 503)
        data = {
            "username": settings.bracket_write_username,
            "password": settings.bracket_write_password.get_secret_value(),
        }
        try:
            async with httpx.AsyncClient(timeout=settings.bracket_write_timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/token", data=data)
        except httpx.TimeoutException as exc:
            raise BracketError("Bracket login timed out", 504) from exc
        except httpx.RequestError as exc:
            raise BracketError("Bracket login failed", 502) from exc
        if response.status_code in (401, 403):
            raise BracketError("Bracket rejected the write credentials", 502)
        if response.status_code != 200:
            raise BracketError(f"Bracket login returned HTTP {response.status_code}", 502)
        try:
            token = object_value(response.json()).get("access_token")
        except ValueError as exc:
            raise BracketError("Invalid Bracket login response") from exc
        if not isinstance(token, str) or not token.strip():
            raise BracketError("Invalid Bracket login response")
        return token

    async def update_match(self, tournament_id: int, match_id: int, body: dict, token: str) -> None:
        """PUT the complete match body (P2.4D §7).

        The response body is deliberately not trusted as proof of anything: the
        caller re-reads the match afterwards. Only the transport outcome is
        interpreted here, without ever including the credential in a message.
        """
        positive_int(tournament_id, "tournament_id")
        positive_int(match_id, "match_id")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=settings.bracket_write_timeout_seconds) as client:
                response = await client.put(
                    f"{self.base_url}/tournaments/{tournament_id}/matches/{match_id}",
                    json=body,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise BracketError("Bracket write timed out", 504) from exc
        except httpx.RequestError as exc:
            raise BracketError("Bracket write failed", 502) from exc
        if response.status_code in (200, 201, 204):
            return
        if response.status_code == 401:
            raise BracketError("Bracket rejected the write token", 502)
        if response.status_code == 403:
            raise BracketError("Bracket write is not allowed for this tournament", 502)
        if response.status_code == 404:
            raise BracketError("Bracket match not found", 404)
        if response.status_code == 409:
            raise BracketError("Bracket rejected the write as a conflict", 409)
        raise BracketError(f"Bracket write returned HTTP {response.status_code}", 502)


class BracketError(ValueError):
    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.status_code = status_code


def positive_int(value, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise BracketError(f"{label} must be a positive integer")
    return value


def object_value(value) -> dict:
    if not isinstance(value, dict):
        raise BracketError("Invalid Bracket object")
    return value


def collection(node: dict, key: str) -> list:
    value = node.get(key)
    if not isinstance(value, list):
        raise BracketError(f"Invalid Bracket {key} list")
    return value


def identity(node: dict, key: str, expected: int):
    if positive_int(node.get(key), key) != expected:
        raise BracketError(f"Bracket ownership mismatch: {key}")


def locate_match(payload: dict, tournament_id: int, match_id: int) -> tuple[dict, dict]:
    positive_int(tournament_id, "tournament_id")
    positive_int(match_id, "match_id")
    found = None
    for stage in collection(object_value(payload), "data"):
        stage = object_value(stage)
        stage_id = positive_int(stage.get("id"), "stage_id")
        identity(stage, "tournament_id", tournament_id)
        for item in collection(stage, "stage_items"):
            item = object_value(item)
            item_id = positive_int(item.get("id"), "stage_item_id")
            identity(item, "stage_id", stage_id)
            for round_ in collection(item, "rounds"):
                round_ = object_value(round_)
                round_id = positive_int(round_.get("id"), "round_id")
                identity(round_, "stage_item_id", item_id)
                if type(round_.get("is_draft")) is not bool:
                    raise BracketError("Invalid is_draft")
                for match in collection(round_, "matches"):
                    match = object_value(match)
                    candidate_id = positive_int(match.get("id"), "match_id")
                    identity(match, "round_id", round_id)
                    if candidate_id == match_id:
                        if round_["is_draft"]:
                            raise BracketError("Draft match cannot be assigned", 409)
                        if found is not None:
                            raise BracketError("Duplicate match identity")
                        found = match, item
    if found is None:
        raise BracketError("Match not found in requested tournament", 404)
    return found


def collect_candidates(payload: dict, tournament_id: int) -> list:
    """Playable matches of one tournament, in the exact order Bracket returns them.

    The list is built with the same normalizer the assignment uses, so every
    listed candidate is assignable by construction. A match that does not meet
    the assignment contract (unresolved input, missing team, duplicated
    participants, unusable duration, foreign identity) is skipped, never
    guessed at; a match_id that appears twice is skipped because the assignment
    cannot resolve it. Structural violations of stage, stage_item or round
    identity remain hard errors.

    Order is the received order (stage -> stage_item -> round -> match). It is
    deliberately NOT sorted by match_id: the payload order is the only real
    order Bracket exposes, and ids do not follow it.

    Scores and winner_from_* pointers are intentionally NOT used here: the
    payload cannot tell a finished match from a played one (see README).
    """
    positive_int(tournament_id, "tournament_id")
    playable, occurrences = [], {}
    for stage in collection(object_value(payload), "data"):
        stage = object_value(stage)
        stage_id = positive_int(stage.get("id"), "stage_id")
        identity(stage, "tournament_id", tournament_id)
        for item in collection(stage, "stage_items"):
            item = object_value(item)
            item_id = positive_int(item.get("id"), "stage_item_id")
            identity(item, "stage_id", stage_id)
            for round_ in collection(item, "rounds"):
                round_ = object_value(round_)
                round_id = positive_int(round_.get("id"), "round_id")
                identity(round_, "stage_item_id", item_id)
                if type(round_.get("is_draft")) is not bool:
                    raise BracketError("Invalid is_draft")
                if round_["is_draft"]:
                    continue
                for match in collection(round_, "matches"):
                    match = object_value(match)
                    match_id = positive_int(match.get("id"), "match_id")
                    identity(match, "round_id", round_id)
                    occurrences[match_id] = occurrences.get(match_id, 0) + 1
                    try:
                        playable.append(normalize_match(match, item, tournament_id))
                    except BracketError:
                        continue
    return [match for match in playable if occurrences[match.match_id] == 1]


def nonempty_name(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BracketError(f"Invalid {label}")
    return value


def normalize_match(match: dict, category: dict, tournament_id: int):
    from app.models import NormalizedCategory, NormalizedFighter, NormalizedMatch

    match, category = object_value(match), object_value(category)
    positive_int(tournament_id, "tournament_id")
    category_id = positive_int(category.get("id"), "stage_item_id")

    def fighter(side):
        input_ = object_value(match.get(f"stage_item_input{side}"))
        identity(input_, "id", positive_int(match.get(f"stage_item_input{side}_id"), "input_id"))
        identity(input_, "tournament_id", tournament_id)
        identity(input_, "stage_item_id", category_id)
        team_id = positive_int(input_.get("team_id"), "team_id")
        team = object_value(input_.get("team"))
        identity(team, "id", team_id)
        identity(team, "tournament_id", tournament_id)
        return NormalizedFighter(stage_item_input_id=input_["id"], team_id=team_id,
                                 name=nonempty_name(team.get("name"), "team name"), club=None)

    fighter_a, fighter_b = fighter(1), fighter(2)
    if (fighter_a.team_id == fighter_b.team_id
            or fighter_a.stage_item_input_id == fighter_b.stage_item_input_id):
        raise BracketError("Participants must be distinct", 409)
    minutes = match.get("custom_duration_minutes")
    if minutes is None:
        minutes = match.get("duration_minutes")
    positive_int(minutes, "duration_minutes")
    return NormalizedMatch(
        tournament_id=tournament_id, match_id=positive_int(match.get("id"), "match_id"), tatami_id=1,
        fighter_a=fighter_a, fighter_b=fighter_b,
        category=NormalizedCategory(stage_item_id=category_id, name=nonempty_name(category.get("name"), "category name")),
        duration_seconds=minutes * 60,
    )


def score_value(value, label: str) -> int:
    """A Bracket score must be a real integer; nothing is coerced here."""
    if type(value) is not int or value < 0:
        raise BracketError(f"Invalid Bracket {label}")
    return value


def match_baseline(match: dict, tournament_id: int) -> dict:
    """Everything the bridge must preserve, plus the fields the CAS compares.

    `court_id`, `custom_duration_minutes` and `custom_margin_minutes` are
    preserved (P2.4D §5): whatever the match has right now is echoed back
    unchanged, including legitimate `None` (Bracket >= 47bc129 accepts it).
    """
    match = object_value(match)
    positive_int(tournament_id, "tournament_id")
    input1 = object_value(match.get("stage_item_input1"))
    input2 = object_value(match.get("stage_item_input2"))
    identity(input1, "tournament_id", tournament_id)
    identity(input2, "tournament_id", tournament_id)
    round_id = positive_int(match.get("round_id"), "round_id")
    identity(match, "round_id", round_id)
    input1_id = positive_int(match.get("stage_item_input1_id"), "stage_item_input1_id")
    input2_id = positive_int(match.get("stage_item_input2_id"), "stage_item_input2_id")
    identity(input1, "id", input1_id)
    identity(input2, "id", input2_id)
    return {
        "round_id": round_id,
        "input1_id": input1_id,
        "input2_id": input2_id,
        "input1_team_id": positive_int(input1.get("team_id"), "team_id"),
        "input2_team_id": positive_int(input2.get("team_id"), "team_id"),
        "score1": score_value(match.get("stage_item_input1_score"), "score1"),
        "score2": score_value(match.get("stage_item_input2_score"), "score2"),
        "court_id": court_id_value(match.get("court_id")),
        "custom_duration_minutes": optional_positive_int(match.get("custom_duration_minutes"),
                                                         "custom_duration_minutes"),
        "custom_margin_minutes": optional_positive_int(match.get("custom_margin_minutes"),
                                                       "custom_margin_minutes"),
    }


def court_id_value(value):
    """`court_id` may legitimately be `None` (a match not scheduled on a court)."""
    if value is None:
        return None
    return positive_int(value, "court_id")


def optional_positive_int(value, label: str):
    if value is None:
        return None
    return positive_int(value, label)


def cas_view(baseline: dict) -> dict:
    """The fields a logical CAS compares: identity, participants and scores.

    Court and custom durations are *preserved*, not compared: an operator may
    legitimately reschedule a match between two attempts, and the bridge echoes
    the current values back instead of fighting over them.
    """
    return {key: baseline[key] for key in
            ("round_id", "input1_id", "input2_id", "input1_team_id", "input2_team_id", "score1", "score2")}


def match_write_body(baseline: dict, score1: int, score2: int) -> dict:
    """The complete `MatchBody` (P2.4D §7): six fields, no winner, no method."""
    return {
        "round_id": baseline["round_id"],
        "stage_item_input1_score": score1,
        "stage_item_input2_score": score2,
        "court_id": baseline["court_id"],
        "custom_duration_minutes": baseline["custom_duration_minutes"],
        "custom_margin_minutes": baseline["custom_margin_minutes"],
    }


def post_verify(verified: dict, body: dict, winner_team_id: int) -> str | None:
    """Re-read check (P2.4D §8). Returns a reason code, or None when every
    requirement holds. An HTTP 200 is never accepted as proof on its own."""
    if (verified["score1"], verified["score2"]) != (body["stage_item_input1_score"],
                                                    body["stage_item_input2_score"]):
        return "post_verify_scores_mismatch"
    if verified["round_id"] != body["round_id"]:
        return "post_verify_round_changed"
    if verified["court_id"] != body["court_id"]:
        return "post_verify_court_changed"
    if verified["custom_duration_minutes"] != body["custom_duration_minutes"]:
        return "post_verify_custom_duration_changed"
    if verified["custom_margin_minutes"] != body["custom_margin_minutes"]:
        return "post_verify_custom_margin_changed"
    points1, points2 = verified["score1"], verified["score2"]
    if points1 == points2:
        return "post_verify_tie"
    natural = verified["input1_team_id"] if points1 > points2 else verified["input2_team_id"]
    if natural != winner_team_id:
        return "post_verify_winner_mismatch"
    return None

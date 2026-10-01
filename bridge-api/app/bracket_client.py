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

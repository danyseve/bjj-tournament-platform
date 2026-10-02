import httpx

from app.config import settings


class ScoreboardClient:
    """Real read-only delivery to the integrated scoreboard for Tatami 1.

    Only Tatami 1 is enabled in this phase. Nothing here writes results back to
    Bracket; the scoreboard receives the normalized assignment over HTTP.
    """

    ENABLED_TATAMI = 1

    def __init__(self):
        self.tatami_urls = {
            1: settings.scoreboard_tatami_1_url,
            2: settings.scoreboard_tatami_2_url,
            3: settings.scoreboard_tatami_3_url,
            4: settings.scoreboard_tatami_4_url,
            5: settings.scoreboard_tatami_5_url,
            6: settings.scoreboard_tatami_6_url,
        }
        self.token = settings.scoreboard_internal_token
        self.timeout = settings.scoreboard_timeout_seconds

    def get_scoreboard_url(self, tatami: int) -> str:
        if tatami != self.ENABLED_TATAMI:
            raise ScoreboardError(f"Tatami {tatami} is not enabled", 400)
        return self.tatami_urls[self.ENABLED_TATAMI]

    async def read_state(self, tatami: int) -> dict | None:
        """Read the live state of Tatami 1; None means the tatami is empty.

        Read-only on purpose: the bridge never learns a result from here and
        never writes one back.
        """
        base_url = self.get_scoreboard_url(tatami)
        if not self.token:
            raise ScoreboardError("Scoreboard internal token is not configured", 502)
        url = base_url.rstrip("/") + f"/internal/tatamis/{self.ENABLED_TATAMI}/state"
        headers = {"X-Internal-Token": self.token}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise ScoreboardError("Scoreboard request timed out", 504) from exc
        except httpx.RequestError as exc:
            raise ScoreboardError("Scoreboard request failed", 502) from exc
        if response.status_code != 200:
            raise ScoreboardError(f"Scoreboard returned HTTP {response.status_code}", 502)
        try:
            body = response.json()
        except ValueError as exc:
            raise ScoreboardError("Invalid Scoreboard JSON response", 502) from exc
        if not isinstance(body, dict) or "state" not in body:
            raise ScoreboardError("Invalid Scoreboard response shape", 502)
        state = body["state"]
        if state is None:
            return None
        if not isinstance(state, dict) or not state:
            raise ScoreboardError("Invalid Scoreboard state shape", 502)
        return state

    async def assign_match(self, tatami: int, payload: dict) -> dict:
        base_url = self.get_scoreboard_url(tatami)
        if not self.token:
            raise ScoreboardError("Scoreboard internal token is not configured", 502)
        url = base_url.rstrip("/") + f"/internal/tatamis/{self.ENABLED_TATAMI}/assignment"
        headers = {"X-Internal-Token": self.token, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.put(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ScoreboardError("Scoreboard request timed out", 504) from exc
        except httpx.RequestError as exc:
            raise ScoreboardError("Scoreboard request failed", 502) from exc

        status = response.status_code
        if status == 409:
            raise ScoreboardError("Scoreboard rejected the assignment as a conflict", 409)
        if status == 400:
            raise ScoreboardError("Scoreboard rejected the normalized assignment", 502)
        if status not in (200, 201):
            raise ScoreboardError(f"Scoreboard returned HTTP {status}", 502)

        try:
            body = response.json()
        except ValueError as exc:
            raise ScoreboardError("Invalid Scoreboard JSON response", 502) from exc
        if not isinstance(body, dict) or not isinstance(body.get("state"), dict) or not body["state"]:
            raise ScoreboardError("Invalid Scoreboard response shape", 502)

        return {"status": "assigned" if status == 201 else "replayed", "state": body["state"]}


class ScoreboardError(ValueError):
    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.status_code = status_code

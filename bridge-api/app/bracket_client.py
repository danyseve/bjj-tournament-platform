import httpx

from app.config import settings


class BracketClient:
    def __init__(self):
        self.base_url = settings.bracket_api_url.rstrip("/")

    async def health(self) -> dict:
        url = f"{self.base_url}/ping"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def update_match_result(self, match_id: int, payload: dict) -> dict:
        """
        Pendiente de adaptar al endpoint real de Bracket.
        """
        return {
            "status": "not_implemented",
            "match_id": match_id,
            "payload": payload,
        }

from app.config import settings


class ScoreboardClient:
    def __init__(self):
        self.tatami_urls = {
            1: settings.scoreboard_tatami_1_url,
            2: settings.scoreboard_tatami_2_url,
            3: settings.scoreboard_tatami_3_url,
            4: settings.scoreboard_tatami_4_url,
            5: settings.scoreboard_tatami_5_url,
            6: settings.scoreboard_tatami_6_url,
        }

    def get_scoreboard_url(self, tatami: int) -> str:
        if tatami not in self.tatami_urls:
            raise ValueError(f"Tatami {tatami} is not configured")

        return self.tatami_urls[tatami]

    async def assign_match(self, tatami: int, payload: dict) -> dict:
        """
        Pendiente de adaptar a la API real o WebSocket real de BJJ-Scoreboard.
        Ahora solo devuelve el target calculado.
        """
        scoreboard_url = self.get_scoreboard_url(tatami)

        return {
            "status": "pending_scoreboard_integration",
            "scoreboard_url": scoreboard_url,
            "payload": payload,
        }

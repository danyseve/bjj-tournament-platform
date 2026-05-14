from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bracket_api_url: str = "http://bracket:8400/api"
    scoreboard_tatami_1_url: str = "http://scoreboard-tatami-1:3000"
    scoreboard_tatami_2_url: str = "http://scoreboard-tatami-2:3000"
    scoreboard_tatami_3_url: str = "http://scoreboard-tatami-3:3000"
    scoreboard_tatami_4_url: str = "http://scoreboard-tatami-4:3000"
    scoreboard_tatami_5_url: str = "http://scoreboard-tatami-5:3000"
    scoreboard_tatami_6_url: str = "http://scoreboard-tatami-6:3000"

    class Config:
        env_file = ".env"


settings = Settings()

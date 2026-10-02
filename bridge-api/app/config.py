from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bracket_api_url: str = "http://bracket:8400/api"
    scoreboard_tatami_1_url: str = "http://scoreboard-tatami-1:3000"
    scoreboard_tatami_2_url: str = "http://scoreboard-tatami-2:3000"
    scoreboard_tatami_3_url: str = "http://scoreboard-tatami-3:3000"
    scoreboard_tatami_4_url: str = "http://scoreboard-tatami-4:3000"
    scoreboard_tatami_5_url: str = "http://scoreboard-tatami-5:3000"
    scoreboard_tatami_6_url: str = "http://scoreboard-tatami-6:3000"
    scoreboard_internal_token: str = ""
    scoreboard_timeout_seconds: float = 10.0

    # P2.5B — interruptor de publicacion de resultados. El release arranca con
    # esto en false: el codigo de P2.4D viaja en la imagen, pero el endpoint de
    # resultado responde 503 (result_write_disabled) sin leer el scoreboard ni
    # tocar Bracket. Solo un true explicito en el entorno lo habilita.
    bracket_result_write_enabled: bool = False

    # P2.4D — credenciales SEPARADAS de escritura en Bracket. No se reutiliza
    # ningun token del navegador ni el secreto interno del scoreboard, y no hay
    # valores por defecto: sin ambas variables no se publica nada.
    bracket_write_username: str = ""
    bracket_write_password: SecretStr = SecretStr("")
    bracket_write_timeout_seconds: float = 10.0

    @property
    def bracket_write_configured(self) -> bool:
        """True only when both write credentials are present."""
        return bool(self.bracket_write_username) and bool(
            self.bracket_write_password.get_secret_value()
        )

    class Config:
        env_file = ".env"


settings = Settings()

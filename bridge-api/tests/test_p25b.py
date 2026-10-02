"""P2.5B — the release switch that keeps the write path off in production.

The point of these tests is not that the P2.4D logic works (test_p24d.py covers
that) but that a deployment which forgets to configure anything publishes
nothing: with the switch off the endpoint must answer 503 result_write_disabled
before it reads the scoreboard, asks Bracket for a token, or touches Bracket at
all. Every client here is booby-trapped: any call it receives is recorded and
fails the test.
"""
import httpx
import pytest
from pydantic import SecretStr

from app import main
from app.config import Settings, settings
from app.result_gate import REASON_WRITE_DISABLED, REASON_WRITE_NOT_CONFIGURED

RealAsyncClient = httpx.AsyncClient

TOURNAMENT_ID = 7
MATCH_ID = 40
SESSION = "synthetic-session-p25b"

FLAG = "bracket_result_write_enabled"
POISON = "the write path was reached while the switch was off"


class PoisonedBracket:
    """Fails the test if the endpoint touches Bracket at all."""

    def __init__(self, write_configured=True):
        self.write_configured = write_configured
        self.calls = []

    async def read_match(self, tournament_id, match_id):
        self.calls.append("read_match")
        raise AssertionError(POISON)

    async def login(self):
        self.calls.append("login")
        raise AssertionError(POISON)

    async def update_match(self, tournament_id, match_id, body, token):
        self.calls.append("update_match")
        raise AssertionError(POISON)


class PoisonedScoreboard:
    """Fails the test if the endpoint reads the scoreboard at all."""

    def __init__(self):
        self.calls = []

    async def read_state(self, tatami):
        self.calls.append("read_state")
        raise AssertionError(POISON)


class RecordingScoreboard:
    def __init__(self, state=None):
        self.state = state
        self.reads = 0

    async def read_state(self, tatami):
        self.reads += 1
        return self.state


class NoCredentialsBracket(PoisonedBracket):
    def __init__(self):
        super().__init__(write_configured=False)


async def post_result(tatami=1, body=None):
    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://bridge") as client:
        return await client.post(
            f"/tatamis/{tatami}/result",
            json=body if body is not None else {"tournament_id": TOURNAMENT_ID,
                                                "match_id": MATCH_ID, "session_id": SESSION},
        )


def wire(monkeypatch, bracket, scoreboard):
    monkeypatch.setattr(main, "bracket_client", bracket)
    monkeypatch.setattr(main, "scoreboard_client", scoreboard)


# --------------------------------------------------------------------------- #
# The default itself
# --------------------------------------------------------------------------- #
def test_1_the_switch_is_off_by_default_without_any_configuration(monkeypatch):
    monkeypatch.delenv("BRACKET_RESULT_WRITE_ENABLED", raising=False)
    assert Settings(_env_file=None).bracket_result_write_enabled is False
    # And the running process uses the same default unless the environment says otherwise.
    monkeypatch.setattr(settings, FLAG, Settings(_env_file=None).bracket_result_write_enabled)
    assert settings.bracket_result_write_enabled is False


def test_2_the_environment_can_only_turn_it_on_explicitly(monkeypatch):
    monkeypatch.setenv("BRACKET_RESULT_WRITE_ENABLED", "false")
    assert Settings(_env_file=None).bracket_result_write_enabled is False
    monkeypatch.setenv("BRACKET_RESULT_WRITE_ENABLED", "true")
    assert Settings(_env_file=None).bracket_result_write_enabled is True
    # Anything that is not a boolean is refused at startup, never guessed.
    monkeypatch.setenv("BRACKET_RESULT_WRITE_ENABLED", "yes-please")
    with pytest.raises(Exception):
        Settings(_env_file=None)


# --------------------------------------------------------------------------- #
# Off: 503 and absolutely nothing else happens
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_3_off_answers_503_with_a_clear_reason(monkeypatch):
    monkeypatch.setattr(settings, FLAG, False)
    bracket, scoreboard = PoisonedBracket(), PoisonedScoreboard()
    wire(monkeypatch, bracket, scoreboard)
    response = await post_result()
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["reason"] == REASON_WRITE_DISABLED == "result_write_disabled"
    assert body["idempotent"] is False
    # Nothing was read, contacted or inventoried: the response carries no facts.
    assert body["fingerprint"] is None
    assert body["scores"] is None
    assert body["tournament_id"] is None
    assert body["match_id"] is None


@pytest.mark.anyio
async def test_4_off_makes_zero_upstream_calls(monkeypatch):
    monkeypatch.setattr(settings, FLAG, False)
    bracket, scoreboard = PoisonedBracket(), PoisonedScoreboard()
    wire(monkeypatch, bracket, scoreboard)
    for tatami in (1, 1, 1):
        response = await post_result(tatami=tatami)
        assert response.status_code == 503
    assert scoreboard.calls == []
    assert bracket.calls == []


@pytest.mark.anyio
async def test_5_off_is_not_overridden_by_present_credentials(monkeypatch):
    """Configured write credentials do not re-enable anything by themselves."""
    monkeypatch.setattr(settings, FLAG, False)
    monkeypatch.setattr(settings, "bracket_write_username", "synthetic-writer")
    monkeypatch.setattr(settings, "bracket_write_password", SecretStr("synthetic-secret"))
    bracket, scoreboard = PoisonedBracket(), PoisonedScoreboard()
    wire(monkeypatch, bracket, scoreboard)
    response = await post_result()
    assert response.status_code == 503
    assert response.json()["reason"] == REASON_WRITE_DISABLED
    assert bracket.calls == [] and scoreboard.calls == []


@pytest.mark.anyio
async def test_6_the_tatami_guard_still_comes_first(monkeypatch):
    monkeypatch.setattr(settings, FLAG, False)
    wire(monkeypatch, PoisonedBracket(), PoisonedScoreboard())
    response = await post_result(tatami=2)
    assert response.status_code == 400, response.text


# --------------------------------------------------------------------------- #
# On: the P2.4D logic is still there
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_7_on_reaches_the_scoreboard_read(monkeypatch):
    """With the switch on the endpoint reads the scoreboard again (empty => pending)."""
    monkeypatch.setattr(settings, FLAG, True)
    scoreboard = RecordingScoreboard(state=None)
    wire(monkeypatch, PoisonedBracket(), scoreboard)
    response = await post_result()
    assert scoreboard.reads == 1
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending_manual"
    assert response.json()["reason"] == "no_scoreboard_state"


# --------------------------------------------------------------------------- #
# Credentials are only needed once the switch is on (lazy credentials)
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_8_off_starts_and_answers_without_write_credentials(monkeypatch):
    """A release with no credentials at all must still boot and serve."""
    monkeypatch.setattr(settings, FLAG, False)
    monkeypatch.setattr(settings, "bracket_write_username", "")
    monkeypatch.setattr(settings, "bracket_write_password", SecretStr(""))
    wire(monkeypatch, NoCredentialsBracket(), PoisonedScoreboard())
    response = await post_result()
    assert response.status_code == 503
    # The switch, not the missing credentials, is what refuses: this is the
    # expected answer of a correctly configured release.
    assert response.json()["reason"] == REASON_WRITE_DISABLED


@pytest.mark.anyio
async def test_9_on_without_credentials_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, FLAG, True)
    monkeypatch.setattr(settings, "bracket_write_username", "")
    monkeypatch.setattr(settings, "bracket_write_password", SecretStr(""))
    bracket, scoreboard = NoCredentialsBracket(), PoisonedScoreboard()
    wire(monkeypatch, bracket, scoreboard)
    response = await post_result()
    assert response.status_code == 503
    assert response.json()["reason"] == REASON_WRITE_NOT_CONFIGURED == "bracket_write_not_configured"
    # Fail-closed: it never fell back to the scoreboard or to an anonymous write.
    assert bracket.calls == [] and scoreboard.calls == []

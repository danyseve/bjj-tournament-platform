"""Publication tracking for P2.4D (idempotency + logical CAS).

Scope, stated plainly: this is an **in-memory, process-local** store. It is NOT
durable and it does NOT pretend to be: a restart of the bridge forgets it, and
it is not a copy of the live scoreboard state. It exists only to answer two
questions:

* has *this exact* result already been published? (idempotency), and
* have Bracket's scores changed since the attempt we are extending? (logical CAS)

Because it is process-local, it cannot coordinate two bridge replicas: the
residual race window is documented in `bridge-api/README.md` (section P2.4D) and
in ADR-001. The authoritative state of a fight stays in the scoreboard, and the
authoritative scores of a match stay in Bracket.

States tracked per attempt: ``pending_manual``, ``writing``, ``written``,
``failed``, ``conflict``.
"""

from app.models import ResultStatus

PENDING_MANUAL: ResultStatus = "pending_manual"
WRITING: str = "writing"
WRITTEN: ResultStatus = "written"
FAILED: ResultStatus = "failed"
CONFLICT: ResultStatus = "conflict"

STATES = (PENDING_MANUAL, WRITING, WRITTEN, FAILED, CONFLICT)


def match_key(tournament_id: int, match_id: int) -> tuple[int, int]:
    return tournament_id, match_id


class ResultStore:
    """Attempts by fingerprint, plus the Bracket baseline per match."""

    def __init__(self) -> None:
        self._attempts: dict[str, dict] = {}
        self._baselines: dict[tuple[int, int], dict] = {}

    # --- attempts ---------------------------------------------------------
    def record(self, fingerprint: str, status: str, reason: str | None = None, **extra) -> dict:
        if status not in STATES:
            raise ValueError(f"unknown publication state: {status}")
        record = {"status": status, "reason": reason}
        record.update(extra)
        self._attempts[fingerprint] = record
        return record

    def get(self, fingerprint: str) -> dict | None:
        return self._attempts.get(fingerprint)

    def is_written(self, fingerprint: str) -> bool:
        record = self._attempts.get(fingerprint)
        return bool(record and record["status"] == WRITTEN)

    def written_fingerprints(self, tournament_id: int, match_id: int) -> set[str]:
        key = match_key(tournament_id, match_id)
        return {
            fingerprint
            for fingerprint, record in self._attempts.items()
            if record["status"] == WRITTEN and record.get("key") == key
        }

    # --- logical CAS baseline --------------------------------------------
    def baseline(self, tournament_id: int, match_id: int) -> dict | None:
        return self._baselines.get(match_key(tournament_id, match_id))

    def set_baseline(self, tournament_id: int, match_id: int, baseline: dict) -> None:
        self._baselines[match_key(tournament_id, match_id)] = baseline

    def reset(self) -> None:
        self._attempts.clear()
        self._baselines.clear()
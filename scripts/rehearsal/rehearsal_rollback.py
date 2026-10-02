#!/usr/bin/env python
"""Rollback del ensayo P2.7A (§17) — se ejecuta DENTRO del contenedor ``bracket``.

Borra EXCLUSIVAMENTE el torneo del ensayo y sus objetos dependientes, en orden
de claves foráneas y en una transacción. No toca ningún otro torneo.

    docker exec bracket /app/.venv/bin/python /tmp/rehearsal/rehearsal_rollback.py \\
        --tournament-name "Torneo Interno CREE Masculino — REHEARSAL" [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from bracket.database import database
from bracket.schema import tournaments

BASELINE = {"tournaments": 2, "matches": 25, "teams": 10, "rounds": 16, "stages": 5, "stage_items": 9}

GLOBAL_QUERIES = {
    "tournaments": "SELECT count(*) FROM tournaments",
    "matches": "SELECT count(*) FROM matches",
    "teams": "SELECT count(*) FROM teams",
    "rounds": "SELECT count(*) FROM rounds",
    "stages": "SELECT count(*) FROM stages",
    "stage_items": "SELECT count(*) FROM stage_items",
    "players": "SELECT count(*) FROM players",
    "stage_item_inputs": "SELECT count(*) FROM stage_item_inputs",
}

SETUP_INPUTS = """SELECT id FROM stage_item_inputs WHERE tournament_id = :t"""
SETUP_ROUNDS_DESC = """
    SELECT r.id FROM rounds r
    JOIN stage_items si ON si.id = r.stage_item_id
    JOIN stages s ON s.id = si.stage_id
    WHERE s.tournament_id = :t
    ORDER BY r.id DESC
"""

COUNT_QUERIES: dict[str, str] = {
    "rounds": """
        SELECT count(*) FROM rounds r JOIN stage_items si ON si.id = r.stage_item_id
        JOIN stages s ON s.id = si.stage_id WHERE s.tournament_id = :t
    """,
    "stage_item_inputs": "SELECT count(*) FROM stage_item_inputs WHERE tournament_id = :t",
    "stage_items": """
        SELECT count(*) FROM stage_items si JOIN stages s ON s.id = si.stage_id
        WHERE s.tournament_id = :t
    """,
    "stages": "SELECT count(*) FROM stages WHERE tournament_id = :t",
    "players_x_teams": """
        SELECT count(*) FROM players_x_teams
        WHERE team_id IN (SELECT id FROM teams WHERE tournament_id = :t)
           OR player_id IN (SELECT id FROM players WHERE tournament_id = :t)
    """,
    "teams": "SELECT count(*) FROM teams WHERE tournament_id = :t",
    "players": "SELECT count(*) FROM players WHERE tournament_id = :t",
    "courts": "SELECT count(*) FROM courts WHERE tournament_id = :t",
    "rankings": "SELECT count(*) FROM rankings WHERE tournament_id = :t",
    "tournaments": "SELECT count(*) FROM tournaments WHERE id = :t",
}

STEPS: list[tuple[str, str]] = [
    ("matches", "DELETE FROM matches WHERE round_id = :round_id"),
    ("rounds", """
        DELETE FROM rounds WHERE stage_item_id IN (
            SELECT si.id FROM stage_items si JOIN stages s ON s.id = si.stage_id
            WHERE s.tournament_id = :t)
    """),
    ("stage_item_inputs", "DELETE FROM stage_item_inputs WHERE tournament_id = :t"),
    ("stage_items", """
        DELETE FROM stage_items WHERE stage_id IN (
            SELECT id FROM stages WHERE tournament_id = :t)
    """),
    ("stages", "DELETE FROM stages WHERE tournament_id = :t"),
    ("players_x_teams", """
        DELETE FROM players_x_teams WHERE team_id IN (SELECT id FROM teams WHERE tournament_id = :t)
        OR player_id IN (SELECT id FROM players WHERE tournament_id = :t)
    """),
    ("teams", "DELETE FROM teams WHERE tournament_id = :t"),
    ("players", "DELETE FROM players WHERE tournament_id = :t"),
    ("courts", "DELETE FROM courts WHERE tournament_id = :t"),
    ("rankings", "DELETE FROM rankings WHERE tournament_id = :t"),
    ("tournaments", "DELETE FROM tournaments WHERE id = :t"),
]


async def global_counts() -> dict[str, int]:
    return {
        key: int(await database.fetch_val(query=query) or 0) for key, query in GLOBAL_QUERIES.items()
    }


async def find_tournament(name: str, tournament_id: int) -> dict[str, Any] | None:
    if tournament_id:
        row = await database.fetch_one(
            query=tournaments.select().where(tournaments.c.id == tournament_id)
        )
    else:
        row = await database.fetch_one(query=tournaments.select().where(tournaments.c.name == name))
    return dict(row._mapping) if row else None


async def rollback(tournament_id: int, *, dry_run: bool) -> dict[str, Any]:
    before = await global_counts()
    deleted: dict[str, int] = {}

    if dry_run:
        for label, query in (
            ("stages", "SELECT count(*) FROM stages WHERE tournament_id = :t"),
            ("teams", "SELECT count(*) FROM teams WHERE tournament_id = :t"),
            ("players", "SELECT count(*) FROM players WHERE tournament_id = :t"),
            ("matches", """
                SELECT count(*) FROM matches m JOIN rounds r ON r.id = m.round_id
                JOIN stage_items si ON si.id = r.stage_item_id JOIN stages s ON s.id = si.stage_id
                WHERE s.tournament_id = :t
            """),
        ):
            deleted[label] = int(await database.fetch_val(query=query, values={"t": tournament_id}) or 0)
        return {"dry_run": True, "would_delete": deleted, "before": before}

    async with database.transaction():
        club_id = int(
            await database.fetch_val(
                query="SELECT club_id FROM tournaments WHERE id = :t", values={"t": tournament_id}
            )
            or 0
        )
        round_ids = [
            int(row._mapping["id"])
            for row in await database.fetch_all(query=SETUP_ROUNDS_DESC, values={"t": tournament_id})
        ]
        match_total = int(
            await database.fetch_val(
                query="""
                    SELECT count(*) FROM matches m JOIN rounds r ON r.id = m.round_id
                    JOIN stage_items si ON si.id = r.stage_item_id
                    JOIN stages s ON s.id = si.stage_id WHERE s.tournament_id = :t
                """,
                values={"t": tournament_id},
            )
            or 0
        )
        deleted["matches"] = match_total
        for round_id in round_ids:  # rondas de la última a la primera: respeta el auto-FK de matches
            await database.execute(
                query="DELETE FROM matches WHERE round_id = :round_id", values={"round_id": round_id}
            )

        for label, query in STEPS:
            if label == "matches":
                continue
            deleted[label] = int(
                await database.fetch_val(query=COUNT_QUERIES[label], values={"t": tournament_id}) or 0
            )
            await database.execute(query=query, values={"t": tournament_id})

        # limpieza del club del ensayo: sólo si no le quedan torneos
        remaining = int(
            await database.fetch_val(
                query="SELECT count(*) FROM tournaments WHERE club_id = :c", values={"c": club_id}
            )
            or 0
        )
        if club_id and remaining == 0:
            deleted["users_x_clubs"] = int(
                await database.fetch_val(
                    query="SELECT count(*) FROM users_x_clubs WHERE club_id = :c", values={"c": club_id}
                )
                or 0
            )
            await database.execute(
                query="DELETE FROM users_x_clubs WHERE club_id = :c", values={"c": club_id}
            )
            deleted["clubs"] = 1
            await database.execute(query="DELETE FROM clubs WHERE id = :c", values={"c": club_id})
        else:
            deleted["users_x_clubs"] = 0
            deleted["clubs"] = 0  # el club tiene otros torneos: se conserva

    after = await global_counts()
    return {
        "deleted": deleted,
        "before": before,
        "after": after,
        "baseline_restored": all(after[k] == v for k, v in BASELINE.items()),
    }


async def main_async(args: argparse.Namespace) -> int:
    await database.connect()
    try:
        tournament = await find_tournament(args.tournament_name, args.tournament_id)
        report: dict[str, Any] = {"tournament_name": args.tournament_name}
        if not tournament:
            report["found"] = False
            report["result"] = "nada que borrar (el ensayo no existe)"
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        report["found"] = True
        report["tournament_id"] = int(tournament["id"])
        report["result"] = await rollback(int(tournament["id"]), dry_run=args.dry_run)
    finally:
        await database.disconnect()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        from pathlib import Path

        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback del ensayo P2.7A")
    parser.add_argument("--tournament-name", default="Torneo Interno CREE Masculino — REHEARSAL")
    parser.add_argument("--tournament-id", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

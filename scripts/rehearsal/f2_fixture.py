#!/usr/bin/env python
"""Fixture de validacion P2.8B F2 - se ejecuta DENTRO de un contenedor ``bracket``.

Crea cuadros aislados para 3, 5, 6 y 7 inscritos y valida end-to-end la cadena
completa del motor:

    create stage item -> distribute slots (bye-aware) -> build rounds
    -> structural resolver (P2.8A) -> scheduler

Solo toca los torneos que crea el mismo (prefijo ``F2FIX``) y solo escribe en la
base de datos de test a la que apunte ``PG_DSN``. No imprime PII ni credenciales.

    docker run --rm -e PG_DSN=... -v /ruta/f2_fixture.py:/tmp/f2_fixture.py:ro \\
        danyseve1/bracket-bjj:<sha>-r1 \\
        uv run --no-dev --locked -- python /tmp/f2_fixture.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.planning.matches import schedule_all_unscheduled_matches
from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
)
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.seeding import (
    bracket_size_for_entrant_count,
    distribute_entrants_into_slots,
)
from bracket.logic.scheduling.structural import MatchStructure, get_match_structures
from bracket.models.db.club import ClubInsertable
from bracket.models.db.court import CourtToInsert
from bracket.models.db.player import PlayerToInsert
from bracket.models.db.player_x_team import PlayerXTeamInsertable
from bracket.models.db.ranking import RankingCreateBody
from bracket.models.db.stage import StageInsertable
from bracket.models.db.stage_item import StageItemCreateBody, StageType
from bracket.models.db.team import TeamInsertable
from bracket.models.db.tournament import TournamentBody
from bracket.schema import (
    clubs,
    courts,
    players,
    players_x_teams,
    stage_item_inputs,
    stages,
    teams,
    tournaments,
)
from bracket.sql.rankings import get_default_rankings_in_tournament, sql_create_ranking
from bracket.sql.stage_item_inputs import sql_set_team_id_for_stage_item_input
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_empty_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_create_tournament
from bracket.utils.id_types import ClubId, TournamentId

FIXTURE_PREFIX = "F2FIX"
CLUB_NAME = f"{FIXTURE_PREFIX} - fixture aislado (P2.8B)"
ENTRANT_COUNTS = (3, 5, 6, 7)
COURT_NAME = "Tatami 1"
DURATION_MINUTES = 5
MARGIN_MINUTES = 1


def tournament_name(n: int) -> str:
    return f"{FIXTURE_PREFIX}-{n} (P2.8B F2)"


async def get_or_create_club() -> int:
    row = await database.fetch_one(query=clubs.select().where(clubs.c.name == CLUB_NAME))
    if row:
        return int(row._mapping["id"])
    return int(
        await database.execute(
            query=clubs.insert(),
            values=ClubInsertable(name=CLUB_NAME, created=datetime_utc.now()).model_dump(),
        )
    )


async def delete_tournament(tournament_id: int) -> None:
    """Borra el torneo y sus objetos dependientes, en orden de claves foraneas."""
    async with database.transaction():
        round_ids = [
            int(row._mapping["id"])
            for row in await database.fetch_all(
                query="""
                    SELECT r.id FROM rounds r
                    JOIN stage_items si ON si.id = r.stage_item_id
                    JOIN stages s ON s.id = si.stage_id
                    WHERE s.tournament_id = :t
                    ORDER BY r.id DESC
                """,
                values={"t": tournament_id},
            )
        ]
        for round_id in round_ids:  # de la ultima ronda a la primera: respeta el auto-FK
            await database.execute(
                query="DELETE FROM matches WHERE round_id = :r", values={"r": round_id}
            )
        for query in (
            """DELETE FROM rounds WHERE stage_item_id IN (
                   SELECT si.id FROM stage_items si JOIN stages s ON s.id = si.stage_id
                   WHERE s.tournament_id = :t)""",
            "DELETE FROM stage_item_inputs WHERE tournament_id = :t",
            """DELETE FROM stage_items WHERE stage_id IN (
                   SELECT id FROM stages WHERE tournament_id = :t)""",
            "DELETE FROM stages WHERE tournament_id = :t",
            """DELETE FROM players_x_teams WHERE team_id IN (
                   SELECT id FROM teams WHERE tournament_id = :t)
                   OR player_id IN (SELECT id FROM players WHERE tournament_id = :t)""",
            "DELETE FROM teams WHERE tournament_id = :t",
            "DELETE FROM players WHERE tournament_id = :t",
            "DELETE FROM courts WHERE tournament_id = :t",
            "DELETE FROM rankings WHERE tournament_id = :t",
            "DELETE FROM tournaments WHERE id = :t",
        ):
            await database.execute(query=query, values={"t": tournament_id})


async def read_matches(stage_item_id: int) -> list[dict[str, Any]]:
    rows = await database.fetch_all(
        query="""
            SELECT m.id, m.court_id, m.start_time, m.position_in_schedule,
                   m.stage_item_input1_score, m.stage_item_input2_score
            FROM matches m JOIN rounds r ON r.id = m.round_id
            WHERE r.stage_item_id = :si
            ORDER BY m.id
        """,
        values={"si": stage_item_id},
    )
    return [dict(row._mapping) for row in rows]


async def build_case(n: int, club_id: int) -> dict[str, Any]:
    bracket_size = bracket_size_for_entrant_count(n)
    if bracket_size is None:
        raise ValueError(f"{n} inscritos: no se puede construir un cuadro")

    name = tournament_name(n)
    existing = await database.fetch_one(
        query=tournaments.select().where(tournaments.c.name == name)
    )
    if existing:
        await delete_tournament(int(existing._mapping["id"]))

    tournament_id = TournamentId(
        await sql_create_tournament(
            TournamentBody(
                club_id=ClubId(club_id),
                name=name,
                start_time=datetime_utc.now(),
                dashboard_public=False,
                dashboard_endpoint=None,
                logo_path=None,
                players_can_be_in_multiple_teams=True,
                auto_assign_courts=True,
                duration_minutes=DURATION_MINUTES,
                margin_minutes=MARGIN_MINUTES,
            )
        )
    )
    await sql_create_ranking(tournament_id, RankingCreateBody(), position=0)
    ranking = await get_default_rankings_in_tournament(tournament_id)
    await database.execute(
        query=courts.insert(),
        values=CourtToInsert(
            name=COURT_NAME, created=datetime_utc.now(), tournament_id=tournament_id
        ).model_dump(),
    )
    stage_id = int(
        await database.execute(
            query=stages.insert(),
            values=StageInsertable(
                tournament_id=tournament_id,
                name=name,
                created=datetime_utc.now(),
                is_active=False,
            ).model_dump(),
        )
    )

    # 1) stage item vacio del tamano B + rondas construidas por el motor
    stage_item = await sql_create_stage_item_with_empty_inputs(
        tournament_id,
        StageItemCreateBody(
            stage_id=stage_id,
            name=name,
            type=StageType.SINGLE_ELIMINATION,
            team_count=bracket_size,
            ranking_id=ranking.id,
        ),
    )
    await build_matches_for_stage_item(stage_item, tournament_id)

    # 2) reparto bye-aware de los inscritos sobre los slots del cuadro
    input_rows = await database.fetch_all(
        query=stage_item_inputs.select()
        .where(stage_item_inputs.c.stage_item_id == stage_item.id)
        .order_by(stage_item_inputs.c.slot)
    )
    inputs_by_slot = {int(row._mapping["slot"]): int(row._mapping["id"]) for row in input_rows}
    slots = distribute_entrants_into_slots(list(range(n)), bracket_size)

    for slot_number, entrant in enumerate(slots, start=1):
        if entrant is None:
            continue
        player_id = int(
            await database.execute(
                query=players.insert(),
                values=PlayerToInsert(
                    name=f"{FIXTURE_PREFIX} {n} P{entrant}",
                    active=True,
                    created=datetime_utc.now(),
                    tournament_id=tournament_id,
                    elo_score=0.0,
                    swiss_score=0.0,
                ).model_dump(),
            )
        )
        team_id = int(
            await database.execute(
                query=teams.insert(),
                values=TeamInsertable(
                    name=f"{FIXTURE_PREFIX} {n} T{entrant}",
                    created=datetime_utc.now(),
                    tournament_id=tournament_id,
                    active=True,
                ).model_dump(),
            )
        )
        await database.execute(
            query=players_x_teams.insert(),
            values=PlayerXTeamInsertable(player_id=player_id, team_id=team_id).model_dump(),
        )
        await sql_set_team_id_for_stage_item_input(
            tournament_id, inputs_by_slot[slot_number], team_id
        )

    # 3) resolver estructural (P2.8A): materializa los BYEs
    stage_item_detail = await get_stage_item(tournament_id, stage_item.id)
    await update_inputs_in_complete_elimination_stage_item(stage_item_detail)

    # 4) scheduler
    tournament_stages = await get_full_tournament_details(tournament_id)
    await schedule_all_unscheduled_matches(tournament_id, tournament_stages)

    # 5) lectura y comprobaciones
    stage_item_detail = await get_stage_item(tournament_id, stage_item.id)
    structures = get_match_structures(stage_item_detail)
    dead = [mid for mid, structure in structures.items() if structure is MatchStructure.DEAD]
    byes = [
        mid for mid, structure in structures.items() if structure is MatchStructure.STRUCTURAL_BYE
    ]
    playable = [
        mid for mid, structure in structures.items() if structure is MatchStructure.PLAYABLE
    ]
    rows = await read_matches(int(stage_item.id))
    scheduled = [row["id"] for row in rows if row["court_id"] is not None]
    scores = [row["stage_item_input1_score"] + row["stage_item_input2_score"] for row in rows]

    problems: list[str] = []
    if len(structures) != bracket_size - 1:
        problems.append(f"matches {len(structures)} != {bracket_size - 1}")
    if dead:
        problems.append(f"ghost matches: {sorted(dead)}")
    if len(byes) != bracket_size - n:
        problems.append(f"byes {len(byes)} != {bracket_size - n}")
    if len(playable) != (bracket_size - 1) - (bracket_size - n):
        problems.append("playable != total - byes")
    if sorted(scheduled) != sorted(playable):
        problems.append(f"planificados {sorted(scheduled)} != jugables {sorted(playable)}")
    if any(score != 0 for score in scores):
        problems.append("hay scores ficticios")

    return {
        "entrants": n,
        "bracket_size": bracket_size,
        "tournament_id": int(tournament_id),
        "stage_item_id": int(stage_item.id),
        "matches": len(structures),
        "playable": len(playable),
        "structural_byes": len(byes),
        "ghost_matches": len(dead),
        "scheduled": len(scheduled),
        "scheduled_positions": sorted(
            row["position_in_schedule"] for row in rows if row["position_in_schedule"] is not None
        ),
        "first_round_slots": [str(entry) if entry is not None else None for entry in slots],
        "problems": problems,
        "ok": not problems,
    }


async def main_async(args: argparse.Namespace) -> int:
    await database.connect()
    try:
        club_id = await get_or_create_club()
        counts = args.entrants or list(ENTRANT_COUNTS)
        cases = [await build_case(n, club_id) for n in counts]

        if args.cleanup:
            for case in cases:
                await delete_tournament(case["tournament_id"])

        report = {
            "fixture": "P2.8B F2",
            "cleanup": args.cleanup,
            "cases": cases,
            "ok": all(case["ok"] for case in cases),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    finally:
        await database.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fixture P2.8B F2 (dentro del contenedor bracket)")
    parser.add_argument("--entrants", type=int, nargs="*", default=None)
    parser.add_argument("--cleanup", action="store_true", help="borrar los torneos del fixture")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

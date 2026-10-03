#!/usr/bin/env python
"""Fixture de validacion P2.8B F2C - accion explicita "Generar cuadro".

Se ejecuta DENTRO de un contenedor ``bracket`` apuntando al ``PG_DSN`` de una base de **test**
(se niega a correr contra una base cuyo nombre no contenga ``test``) y llama a la MISMA funcion
que sirve la ruta ``POST .../generate_bracket``. Cubre:

  1. Matriz del invariante ``N -> B`` para 2..9 inscritos (B = menor potencia de 2 >= N):
     tamano de cuadro, pases directos, 0 combates ``vacio/vacio`` y 0 actividad.
  2. El caso exacto del *UI AUTO-SEED GAP*: el stage item se crea con plazas VACIAS, se construyen
     los partidos y despues se asignan los equipos a las primeras plazas (lo que hace la UI); el
     reparto antiguo deja un combate ``vacio/vacio`` y byes concentrados, y la accion explicita lo
     corrige y materializa el avance estructural (P2.8A).
  3. Safety gates: ``HAS_SCORES``, ``PLANNING``, ``NOT_SINGLE_ELIMINATION``, ``TOO_FEW_ENTRANTS``.
  4. Idempotencia: segunda ejecucion -> ``changed=false`` y la estructura no cambia.

Solo toca el torneo que crea el mismo (prefijo ``F2CFIX``) y admite ``--cleanup`` para borrarlo.
No imprime PII ni credenciales.

    docker run --rm -e PG_DSN=... -w /app -e PYTHONPATH=/app \\
        -v /ruta/f2c_fixture.py:/tmp/f2c_fixture.py:ro \\
        danyseve1/bracket-bjj:<sha>-r1 \\
        /app/.venv/bin/python /tmp/f2c_fixture.py

Con ``--cleanup`` solo borra el torneo del fixture.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from heliclockter import datetime_utc

from bracket.database import database
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.scheduling.generation import (
    BracketGenerationBlocker,
    count_entrants,
    get_bracket_generation_blocker,
)
from bracket.logic.scheduling.seeding import bracket_size_for_entrant_count
from bracket.models.db.club import ClubInsertable
from bracket.models.db.ranking import RankingCreateBody
from bracket.models.db.stage import StageInsertable
from bracket.models.db.stage_item import StageItemCreateBody, StageType
from bracket.models.db.team import TeamInsertable
from bracket.models.db.tournament import TournamentBody
from bracket.routes.stage_items import generate_bracket
from bracket.schema import clubs, stages, teams, tournaments
from bracket.sql.rankings import get_default_rankings_in_tournament, sql_create_ranking
from bracket.sql.stage_item_inputs import sql_set_team_id_for_stage_item_input
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_empty_inputs
from bracket.sql.tournaments import sql_create_tournament
from bracket.utils.id_types import ClubId, TournamentId

FIXTURE_PREFIX = "F2CFIX"
CLUB_NAME = f"{FIXTURE_PREFIX} - fixture aislado (P2.8B F2C)"
TOURNAMENT_NAME = f"{FIXTURE_PREFIX} - generar cuadro desde la UI (P2.8B F2C)"
GAP_BRACKET_SIZE = 8
GAP_ENTRANT_COUNT = 6
MATRIX_ENTRANT_COUNTS = (2, 3, 4, 5, 6, 7, 8, 9)


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


async def delete_previous_fixture() -> bool:
    """Borra el torneo del fixture, en orden de claves foraneas."""
    row = await database.fetch_one(
        query=tournaments.select().where(tournaments.c.name == TOURNAMENT_NAME)
    )
    if not row:
        return False
    tournament_id = int(row._mapping["id"])
    async with database.transaction():
        await database.execute(
            query="""DELETE FROM matches WHERE round_id IN (
                       SELECT r.id FROM rounds r
                       JOIN stage_items si ON si.id = r.stage_item_id
                       JOIN stages s ON s.id = si.stage_id WHERE s.tournament_id = :t)""",
            values={"t": tournament_id},
        )
        for query in (
            """DELETE FROM rounds WHERE stage_item_id IN (SELECT si.id FROM stage_items si
                   JOIN stages s ON s.id = si.stage_id WHERE s.tournament_id = :t)""",
            "DELETE FROM stage_item_inputs WHERE tournament_id = :t",
            """DELETE FROM stage_items WHERE stage_id IN
                   (SELECT id FROM stages WHERE tournament_id = :t)""",
            "DELETE FROM stages WHERE tournament_id = :t",
            "DELETE FROM teams WHERE tournament_id = :t",
            "DELETE FROM rankings WHERE tournament_id = :t",
            "DELETE FROM tournaments WHERE id = :t",
        ):
            await database.execute(query=query, values={"t": tournament_id})
    return True


async def create_stage_item(
    tournament_id: int, stage_id: int, ranking_id: int, name: str, team_count: int,
    stage_type: StageType = StageType.SINGLE_ELIMINATION,
) -> Any:
    """Crea el stage item con plazas VACIAS y construye rondas/partidos (lo que hace la UI)."""
    stage_item = await sql_create_stage_item_with_empty_inputs(
        tournament_id,
        StageItemCreateBody(
            stage_id=stage_id,
            name=name,
            type=stage_type,
            team_count=team_count,
            ranking_id=ranking_id,
        ),
    )
    await build_matches_for_stage_item(stage_item, tournament_id)
    return await get_stage_item(tournament_id, stage_item.id)


async def assign_teams(tournament_id: int, stage_item: Any, count: int, label: str) -> list[int]:
    """Asigna ``count`` equipos nuevos a las primeras plazas (lo que hace el PUT de la UI)."""
    team_ids: list[int] = []
    for index in range(1, count + 1):
        team_ids.append(
            int(
                await database.execute(
                    query=teams.insert(),
                    values=TeamInsertable(
                        name=f"{label} - Equipo {index}",
                        active=True,
                        tournament_id=tournament_id,
                        created=datetime_utc.now(),
                    ).model_dump(),
                )
            )
        )
    slots = sorted(stage_item.inputs, key=lambda input_: input_.slot)
    for slot, team_id in zip(slots, team_ids, strict=False):
        await sql_set_team_id_for_stage_item_input(tournament_id, slot.id, team_id)
    return team_ids


def first_round_layout(stage_item: Any) -> dict[str, int]:
    """Resumen de la primera ronda: completos, pases directos (un solo equipo) y vacios."""
    teams_by_input = {input_.id: input_.team_id for input_ in stage_item.inputs}
    layout = {"matches": len(stage_item.rounds[0].matches), "full": 0, "byes": 0, "ghosts": 0}
    for match in stage_item.rounds[0].matches:
        team1 = teams_by_input.get(match.stage_item_input1_id)
        team2 = teams_by_input.get(match.stage_item_input2_id)
        if team1 is not None and team2 is not None:
            layout["full"] += 1
        elif (team1 is None) != (team2 is None):
            layout["byes"] += 1
        else:
            layout["ghosts"] += 1
    return layout


def byes_materialized(stage_item: Any) -> bool:
    """Comprueba que los pases directos de la 1a ronda aparecen en rondas posteriores (P2.8A)."""
    teams_by_input = {input_.id: input_.team_id for input_ in stage_item.inputs}
    later_input_ids = {
        input_id
        for round_ in stage_item.rounds[1:]
        for match in round_.matches
        for input_id in (match.stage_item_input1_id, match.stage_item_input2_id)
        if input_id is not None
    }
    bye_input_ids = {
        match.stage_item_input1_id if teams_by_input.get(match.stage_item_input1_id) is not None
        else match.stage_item_input2_id
        for match in stage_item.rounds[0].matches
        if (teams_by_input.get(match.stage_item_input1_id) is None)
        != (teams_by_input.get(match.stage_item_input2_id) is None)
    }
    return bye_input_ids.issubset(later_input_ids)


async def run_generation(tournament_id: int, stage_item_id: int) -> dict[str, Any]:
    """Ejecuta la accion explicita (misma funcion que sirve la ruta) y devuelve el resultado."""
    stage_item = await get_stage_item(tournament_id, stage_item_id)
    response = await generate_bracket(
        tournament_id=tournament_id,
        stage_item_id=stage_item.id,
        _=None,  # dependencia de autenticacion; no la usa el cuerpo de la ruta
        __=None,  # dependencia de torneo archivado; no la usa el cuerpo de la ruta
        stage_item=stage_item,
    )
    return response.model_dump()


async def count_activity(stage_item_id: int) -> int:
    row = await database.fetch_one(
        query="""SELECT COUNT(*) AS rows_with_activity FROM matches m
                 JOIN rounds r ON r.id = m.round_id
                 WHERE r.stage_item_id = :si
                   AND (m.stage_item_input1_score <> 0 OR m.stage_item_input2_score <> 0
                        OR m.court_id IS NOT NULL OR m.start_time IS NOT NULL
                        OR m.position_in_schedule IS NOT NULL)""",
        values={"si": stage_item_id},
    )
    return int(row._mapping["rows_with_activity"])


async def run_matrix(tournament_id: int, stage_id: int, ranking_id: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for entrants in MATRIX_ENTRANT_COUNTS:
        expected_size = bracket_size_for_entrant_count(entrants)
        stage_item = await create_stage_item(
            tournament_id, stage_id, ranking_id, f"F2C matrix N={entrants}", expected_size
        )
        await assign_teams(tournament_id, stage_item, entrants, f"Matrix N={entrants}")
        stage_item = await get_stage_item(tournament_id, stage_item.id)
        assert count_entrants(stage_item) == entrants, (entrants, count_entrants(stage_item))

        first = await run_generation(tournament_id, stage_item.id)
        stage_item = await get_stage_item(tournament_id, stage_item.id)
        second = await run_generation(tournament_id, stage_item.id)
        stage_item = await get_stage_item(tournament_id, stage_item.id)

        layout = first_round_layout(stage_item)
        expected_byes = expected_size - entrants
        assert first["entrant_count"] == entrants, (entrants, first)
        assert first["bracket_size"] == expected_size, (entrants, first)
        assert first["bye_count"] == expected_byes, (entrants, first)
        assert first["ghost_count"] == 0, (entrants, first)
        # ``changed`` puede ser False cuando el reparto previo (equipos en las primeras plazas) ya
        # coincide con el reparto bye-aware; lo determinante es que el 2o pase sea no-op.
        assert isinstance(first["changed"], bool), (entrants, first)
        assert layout["ghosts"] == 0, (entrants, layout)
        assert layout["byes"] == expected_byes, (entrants, layout)
        assert layout["full"] == (entrants - expected_byes) // 2, (entrants, layout)
        assert layout["matches"] == expected_size // 2, (entrants, layout)
        assert byes_materialized(stage_item), (entrants, "byes no materializados")
        assert second["changed"] is False, (entrants, second)
        assert await count_activity(stage_item.id) == 0, (entrants, "actividad != 0")

        results.append(
            {
                "entrants": entrants,
                "bracket_size": expected_size,
                "bye_count": first["bye_count"],
                "layout": layout,
                "first_run_changed": bool(first["changed"]),
                "second_run_changed": bool(second["changed"]),
            }
        )
    return results


async def run_gap_case(tournament_id: int, stage_id: int, ranking_id: int) -> dict[str, Any]:
    stage_item = await create_stage_item(
        tournament_id, stage_id, ranking_id, "F2C gap UI", GAP_BRACKET_SIZE
    )
    await assign_teams(tournament_id, stage_item, GAP_ENTRANT_COUNT, "Gap")
    stage_item = await get_stage_item(tournament_id, stage_item.id)
    layout_before = first_round_layout(stage_item)

    first = await run_generation(tournament_id, stage_item.id)
    stage_item = await get_stage_item(tournament_id, stage_item.id)
    layout_after = first_round_layout(stage_item)
    materialized = byes_materialized(stage_item)

    second = await run_generation(tournament_id, stage_item.id)
    stage_item = await get_stage_item(tournament_id, stage_item.id)

    assert layout_before["ghosts"] == 1, layout_before
    assert first["bye_count"] == 2, first
    assert first["ghost_count"] == 0, first
    assert layout_after == {"matches": 4, "full": 2, "byes": 2, "ghosts": 0}, layout_after
    assert materialized is True, "pases directos no materializados"
    assert second["changed"] is False, second
    assert await count_activity(stage_item.id) == 0, "actividad != 0"

    return {
        "stage_item_id": int(stage_item.id),
        "layout_before_generating": layout_before,
        "generate_response": first,
        "layout_after_generating": layout_after,
        "structural_byes_materialized": materialized,
        "second_run": second,
    }


async def run_gate_cases(
    tournament_id: int, stage_id: int, ranking_id: int, gap_stage_item_id: int
) -> dict[str, str]:
    gates: dict[str, str] = {}

    # HAS_SCORES
    await database.execute(
        query="""UPDATE matches SET stage_item_input1_score = 1 WHERE id = (
                   SELECT m.id FROM matches m JOIN rounds r ON r.id = m.round_id
                   WHERE r.stage_item_id = :si ORDER BY m.id LIMIT 1)""",
        values={"si": gap_stage_item_id},
    )
    stage_item = await get_stage_item(tournament_id, gap_stage_item_id)
    gates["con_score"] = str(get_bracket_generation_blocker(stage_item))
    await database.execute(
        query="""UPDATE matches SET stage_item_input1_score = 0 WHERE id = (
                   SELECT m.id FROM matches m JOIN rounds r ON r.id = m.round_id
                   WHERE r.stage_item_id = :si ORDER BY m.id LIMIT 1)""",
        values={"si": gap_stage_item_id},
    )

    # PLANNING
    await database.execute(
        query="""UPDATE matches SET position_in_schedule = 99 WHERE id = (
                   SELECT m.id FROM matches m JOIN rounds r ON r.id = m.round_id
                   WHERE r.stage_item_id = :si ORDER BY m.id LIMIT 1)""",
        values={"si": gap_stage_item_id},
    )
    stage_item = await get_stage_item(tournament_id, gap_stage_item_id)
    gates["con_planning"] = str(get_bracket_generation_blocker(stage_item))
    await database.execute(
        query="""UPDATE matches SET position_in_schedule = NULL WHERE id = (
                   SELECT m.id FROM matches m JOIN rounds r ON r.id = m.round_id
                   WHERE r.stage_item_id = :si ORDER BY m.id LIMIT 1)""",
        values={"si": gap_stage_item_id},
    )

    # NOT_SINGLE_ELIMINATION
    round_robin = await create_stage_item(
        tournament_id, stage_id, ranking_id, "F2C gate round robin", 4, StageType.ROUND_ROBIN
    )
    gates["no_single_elimination"] = str(get_bracket_generation_blocker(round_robin))

    # TOO_FEW_ENTRANTS
    empty = await create_stage_item(tournament_id, stage_id, ranking_id, "F2C gate vacio", 4)
    gates["sin_inscritos"] = str(get_bracket_generation_blocker(empty))

    assert gates["con_score"] == str(BracketGenerationBlocker.SCORES), gates
    assert gates["con_planning"] == str(BracketGenerationBlocker.PLANNING), gates
    assert gates["no_single_elimination"] == str(BracketGenerationBlocker.NOT_SINGLE_ELIMINATION), gates
    assert gates["sin_inscritos"] == str(BracketGenerationBlocker.TOO_FEW_ENTRANTS), gates
    assert get_bracket_generation_blocker(await get_stage_item(tournament_id, gap_stage_item_id)) is None
    return gates


async def main() -> None:  # noqa: C901
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="borrar el torneo del fixture y salir")
    args = parser.parse_args()

    await database.connect()
    try:
        database_name = (
            await database.fetch_one(query="SELECT current_database() AS name")
        )._mapping["name"]
        if "test" not in str(database_name):
            raise SystemExit(f"abortado: '{database_name}' no parece una base de test")

        if args.cleanup:
            removed = await delete_previous_fixture()
            print(json.dumps({"cleaned": removed, "database": database_name}, ensure_ascii=False))
            return

        club_id = await get_or_create_club()
        await delete_previous_fixture()

        tournament_id = TournamentId(
            await sql_create_tournament(
                TournamentBody(
                    club_id=ClubId(club_id),
                    name=TOURNAMENT_NAME,
                    start_time=datetime_utc.now(),
                    dashboard_public=False,
                    dashboard_endpoint=None,
                    logo_path=None,
                    players_can_be_in_multiple_teams=True,
                    auto_assign_courts=True,
                    duration_minutes=5,
                    margin_minutes=1,
                )
            )
        )
        await sql_create_ranking(tournament_id, RankingCreateBody(), position=0)
        ranking = await get_default_rankings_in_tournament(tournament_id)
        stage_id = int(
            await database.execute(
                query=stages.insert(),
                values=StageInsertable(
                    tournament_id=tournament_id,
                    name=TOURNAMENT_NAME,
                    created=datetime_utc.now(),
                    is_active=False,
                ).model_dump(),
            )
        )

        matrix = await run_matrix(tournament_id, stage_id, ranking.id)
        gap = await run_gap_case(tournament_id, stage_id, ranking.id)
        gates = await run_gate_cases(tournament_id, stage_id, ranking.id, gap["stage_item_id"])

        report = {
            "database": database_name,
            "tournament_id": int(tournament_id),
            "matrix": matrix,
            "gap_case": gap,
            "gates": gates,
        }
    finally:
        await database.disconnect()

    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print("F2C FIXTURE OK")


if __name__ == "__main__":
    asyncio.run(main())

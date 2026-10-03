#!/usr/bin/env python
"""Importador del ensayo P2.7A / P2.8B-F2 — se ejecuta DENTRO del contenedor ``bracket``.

P2.8B-F2: los equipos se colocan en slots bye-aware con ``distribute_entrants_into_slots`` (la misma
función pura que usa el motor), en lugar de ocupar los primeros slots y dejar los vacíos al final:
así cada bye queda emparejado con un entrant real y no se crean matches ∅/∅.

Usa los modelos del propio Bracket (sin HTTP y sin POST /api/token, §16):
crea club, torneo, ranking, pista, jugadores, equipos, stages y stage_items, y
deja que Bracket genere los cuadros con su propia lógica
(``build_matches_for_stage_item``).

Ejemplo (desde el host):

    docker cp scripts/rehearsal bracket:/tmp/rehearsal
    docker cp /home/ubuntu/private/bjj-rehearsal/dataset.json bracket:/tmp/rehearsal/
    docker exec bracket /app/.venv/bin/python /tmp/rehearsal/rehearsal_import.py \\
        --dataset /tmp/rehearsal/dataset.json --mode anonymized --dry-run

Salida: ids y conteos (nunca PII).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataset import (  # noqa: E402
    CATEGORY_ORDER,
    DatasetError,
    REHEARSAL_TOURNAMENT_NAME,
    build_plan,
    load_dataset,
    pii_free_summary,
    validate,
)
from zoneinfo import ZoneInfo  # noqa: E402

from bracket.database import database  # noqa: E402
from bracket.logic.ranking.elimination import (  # noqa: E402
    update_inputs_in_complete_elimination_stage_item,
)
from bracket.logic.scheduling.builder import build_matches_for_stage_item  # noqa: E402
from bracket.logic.scheduling.seeding import distribute_entrants_into_slots  # noqa: E402
from bracket.models.db.club import ClubInsertable  # noqa: E402
from bracket.models.db.court import CourtToInsert  # noqa: E402
from bracket.models.db.player import PlayerToInsert  # noqa: E402
from bracket.models.db.player_x_team import PlayerXTeamInsertable  # noqa: E402
from bracket.models.db.ranking import RankingCreateBody  # noqa: E402
from bracket.models.db.stage import StageInsertable  # noqa: E402
from bracket.models.db.stage_item import StageItemCreateBody, StageType  # noqa: E402
from bracket.models.db.team import TeamInsertable  # noqa: E402
from bracket.models.db.tournament import TournamentBody  # noqa: E402
from bracket.schema import (  # noqa: E402
    clubs,
    courts,
    players,
    players_x_teams,
    stage_item_inputs,
    stages,
    teams,
    tournaments,
    users_x_clubs,
)
from bracket.sql.players import insert_player  # noqa: E402
from bracket.sql.rankings import get_default_rankings_in_tournament, sql_create_ranking  # noqa: E402
from bracket.sql.stage_item_inputs import sql_set_team_id_for_stage_item_input  # noqa: E402
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_empty_inputs  # noqa: E402
from bracket.sql.tournaments import sql_create_tournament  # noqa: E402
from bracket.utils.id_types import ClubId, TournamentId  # noqa: E402
from heliclockter import datetime_utc  # noqa: E402

DEFAULT_CLUB_NAME = "REHEARSAL — Escuela interna (anonimizada)"
DEFAULT_COURT_NAME = "Tatami 1"
DEFAULT_DURATION_MINUTES = 5
DEFAULT_MARGIN_MINUTES = 1


async def find_existing_tournament(name: str) -> dict[str, Any] | None:
    row = await database.fetch_one(
        query=tournaments.select().where(tournaments.c.name == name)
    )
    return dict(row._mapping) if row else None


async def structure_counts(tournament_id: int) -> dict[str, int]:
    """Conteos reales de la estructura de un torneo (para idempotencia)."""
    queries = {
        "stages": "SELECT count(*) FROM stages WHERE tournament_id = :t",
        "stage_items": (
            "SELECT count(*) FROM stage_items si JOIN stages s ON s.id = si.stage_id "
            "WHERE s.tournament_id = :t"
        ),
        "stage_item_inputs": "SELECT count(*) FROM stage_item_inputs WHERE tournament_id = :t",
        "teams": "SELECT count(*) FROM teams WHERE tournament_id = :t",
        "players": "SELECT count(*) FROM players WHERE tournament_id = :t",
        "rounds": (
            "SELECT count(*) FROM rounds r JOIN stage_items si ON si.id = r.stage_item_id "
            "JOIN stages s ON s.id = si.stage_id WHERE s.tournament_id = :t"
        ),
        "matches": (
            "SELECT count(*) FROM matches m JOIN rounds r ON r.id = m.round_id "
            "JOIN stage_items si ON si.id = r.stage_item_id JOIN stages s ON s.id = si.stage_id "
            "WHERE s.tournament_id = :t"
        ),
        "courts": "SELECT count(*) FROM courts WHERE tournament_id = :t",
    }
    return {
        key: int(await database.fetch_val(query=query, values={"t": tournament_id}) or 0)
        for key, query in queries.items()
    }


async def get_or_create_club(name: str, dry_run: bool) -> int:
    row = await database.fetch_one(query=clubs.select().where(clubs.c.name == name))
    if row:
        return int(row._mapping["id"])
    if dry_run:
        return -1
    return int(
        await database.execute(
            query=clubs.insert(),
            values=ClubInsertable(name=name, created=datetime_utc.now()).model_dump(),
        )
    )


async def link_user_to_club(club_id: int, user_id: int) -> bool:
    existing = await database.fetch_one(
        query=users_x_clubs.select().where(
            (users_x_clubs.c.club_id == club_id) & (users_x_clubs.c.user_id == user_id)
        )
    )
    if existing:
        return False
    await database.execute(
        query=users_x_clubs.insert(),
        values={"club_id": club_id, "user_id": user_id, "relation": "OWNER"},
    )
    return True


def event_start(dataset: Any) -> Any:
    """Fecha del evento (sólo día, 09:00 UTC) — el modelo no tiene 'fecha de evento' aparte."""
    year, month, day = (int(part) for part in dataset.event_date.split("-"))
    return datetime_utc(year, month, day, 9, 0, 0, tzinfo=ZoneInfo("UTC"))


async def import_tournament(args: argparse.Namespace, dataset: Any, plan: Any) -> dict[str, Any]:
    started = time.perf_counter()
    phases: dict[str, float] = {}
    ids: dict[str, Any] = {}
    byes_by_category: dict[str, int] = {}

    club_id = await get_or_create_club(args.club_name, args.dry_run)
    ids["club_id"] = club_id
    if not args.dry_run and args.link_user_id:
        ids["user_linked"] = await link_user_to_club(club_id, args.link_user_id)

    tournament_body = TournamentBody(
        club_id=ClubId(club_id),
        name=args.tournament_name,
        start_time=event_start(dataset),
        dashboard_public=False,
        dashboard_endpoint=None,
        logo_path=None,
        players_can_be_in_multiple_teams=True,
        auto_assign_courts=True,
        duration_minutes=args.duration_minutes,
        margin_minutes=args.margin_minutes,
    )

    async with database.transaction():
        mark = time.perf_counter()
        tournament_id = TournamentId(args.tournament_id or await sql_create_tournament(tournament_body))
        ids["tournament_id"] = int(tournament_id)
        await sql_create_ranking(tournament_id, RankingCreateBody(), position=0)
        ranking = await get_default_rankings_in_tournament(tournament_id)

        ids["court_id"] = int(
            await database.execute(
                query=courts.insert(),
                values=CourtToInsert(
                    name=args.court_name, created=datetime_utc.now(), tournament_id=tournament_id
                ).model_dump(),
            )
        )
        phases["esqueleto"] = time.perf_counter() - mark

        mark = time.perf_counter()
        for category in CATEGORY_ORDER:
            members = plan.categories.get(category)
            if not members:
                continue
            mark_cat = time.perf_counter()

            stage_id = int(
                await database.execute(
                    query=stages.insert(),
                    values=StageInsertable(
                        tournament_id=tournament_id,
                        name=category,
                        created=datetime_utc.now(),
                        is_active=False,
                    ).model_dump(),
                )
            )
            stage_item = await sql_create_stage_item_with_empty_inputs(
                tournament_id,
                StageItemCreateBody(
                    stage_id=stage_id,
                    name=category,
                    type=StageType.SINGLE_ELIMINATION,
                    team_count=plan.bracket_size(category),
                    ranking_id=ranking.id,
                ),
            )
            await build_matches_for_stage_item(stage_item, tournament_id)

            bracket_size = plan.bracket_size(category)
            input_rows = await database.fetch_all(
                query=stage_item_inputs.select()
                .where(stage_item_inputs.c.stage_item_id == stage_item.id)
                .order_by(stage_item_inputs.c.slot)
            )
            if len(input_rows) != bracket_size:
                raise DatasetError(
                    f"{category}: slots creados {len(input_rows)} != cuadro {bracket_size}"
                )

            # P2.8B-F2 — reparto bye-aware: se usa la MISMA función pura que el motor para que cada
            # bye quede emparejado con un entrant real (nunca ∅/∅). El índice i de la lista devuelta
            # es el slot i+1 y los input_rows vienen ordenados por slot, así que el mapeo es directo.
            try:
                distribution = distribute_entrants_into_slots(list(members), bracket_size)
            except ValueError as exc:
                raise DatasetError(f"{category}: reparto bye-aware imposible: {exc}") from exc
            if len(distribution) != len(input_rows):
                raise DatasetError(
                    f"{category}: reparto {len(distribution)} != inputs {len(input_rows)}"
                )
            if sum(competitor is not None for competitor in distribution) != len(members):
                raise DatasetError(
                    f"{category}: el reparto no coloca exactamente {len(members)} entrants"
                )
            byes_by_category[category] = sum(competitor is None for competitor in distribution)

            for input_row, competitor in zip(input_rows, distribution, strict=True):
                if competitor is None:
                    continue
                player_id = int(
                    await database.execute(
                        query=players.insert(),
                        values=PlayerToInsert(
                            name=competitor.name,
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
                            name=competitor.name,
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
                    tournament_id, input_row._mapping["id"], team_id
                )
            # P2.8B-F2 — materialización estructural P2.8A. El cuadro se construyó antes de asignar
            # los equipos, así que la resolución que builder.py:75-79 hace al construir no tenía nada
            # que avanzar; ya colocados los entrants en sus slots, se repite aquí la resolución del
            # motor para que cada bye avance solo, sin ningún resultado ficticio.
            await update_inputs_in_complete_elimination_stage_item(
                await get_stage_item(tournament_id, stage_item.id)
            )
            ids.setdefault("categories", {})[category] = round(time.perf_counter() - mark_cat, 3)
        phases["categorias_y_cuadros"] = time.perf_counter() - mark

    # P2.8B-F2: el reparto bye-aware debe dar exactamente B-N byes por categoría y ningún ghost,
    # lo que exige que ningún cuadro supere el doble de sus entrants (B <= 2N).
    for category, size in plan.bracket_sizes().items():
        entrant_count = len(plan.categories[category])
        if size > 2 * entrant_count:
            raise DatasetError(
                f"{category}: cuadro de {size} para {entrant_count} entrants generaría ghosts"
            )
    if byes_by_category != plan.byes():
        raise DatasetError(f"byes inesperados: {byes_by_category} != {plan.byes()}")

    ids["byes_by_category"] = byes_by_category
    ids["structure"] = await structure_counts(int(ids["tournament_id"]))
    expected_structure = {
        "stages": len(plan.categories),
        "stage_items": len(plan.categories),
        "stage_item_inputs": plan.total_slots(),
        "teams": plan.team_count,
        "players": plan.team_count,
        "courts": 1,
    }
    mismatches = {
        key: {"obtenido": ids["structure"][key], "esperado": value}
        for key, value in expected_structure.items()
        if ids["structure"][key] != value
    }
    if mismatches:
        raise DatasetError(f"conteos inesperados tras el import: {mismatches}")
    ids["expected_structure"] = expected_structure
    ids["phases_seconds"] = phases
    ids["total_seconds"] = round(time.perf_counter() - started, 3)
    return ids


async def main_async(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset, source=args.mode)
    errors, warnings = validate(dataset, args.mode)
    plan = build_plan(dataset)
    summary = pii_free_summary(dataset, args.mode)

    report: dict[str, Any] = {
        "mode": args.mode,
        "tournament_name": args.tournament_name,
        "dataset": summary,
        "warnings": warnings,
    }

    if errors:
        report["errors"] = errors
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("ERRORES: importación abortada")
        return 2

    if args.dry_run:
        report["dry_run"] = True
        report["plan_team_counts"] = plan.team_counts()
        report["expected_structure"] = {
            "stages": len(plan.categories),
            "stage_items": len(plan.categories),
            "stage_item_inputs": plan.total_slots(),
            "teams": plan.team_count,
            "players": plan.team_count,
            "byes": plan.total_byes(),
        }
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    await database.connect()
    try:
        existing = await find_existing_tournament(args.tournament_name)
        if existing:
            counts = await structure_counts(int(existing["id"]))
            report["already_imported"] = True
            report["tournament_id"] = int(existing["id"])
            report["structure"] = counts
            report["idempotent"] = counts["players"] == plan.team_count and counts["teams"] == plan.team_count
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["idempotent"] else 3

        report["import"] = await import_tournament(args, dataset, plan)
    finally:
        await database.disconnect()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Importador del ensayo P2.7A/P2.8B (dentro del contenedor bracket)")
    parser.add_argument("--dataset", required=True, help="ruta al JSON del ensayo")
    parser.add_argument("--mode", choices=["real", "anonymized"], required=True)
    parser.add_argument("--tournament-name", default=REHEARSAL_TOURNAMENT_NAME)
    parser.add_argument("--club-name", default=DEFAULT_CLUB_NAME)
    parser.add_argument("--court-name", default=DEFAULT_COURT_NAME)
    parser.add_argument("--duration-minutes", type=int, default=DEFAULT_DURATION_MINUTES)
    parser.add_argument("--margin-minutes", type=int, default=DEFAULT_MARGIN_MINUTES)
    parser.add_argument("--link-user-id", type=int, default=1, help="usuario al que dar acceso de lectura al torneo (0 = no)")
    parser.add_argument("--tournament-id", type=int, default=0, help="(interno) reutilizar id en lugar de crear")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    try:
        return asyncio.run(main_async(args))
    except DatasetError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

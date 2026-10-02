"""Anonimizador del dataset real → fixture versionable (P2.7A §3/§19).

Reglas:
- ``name``            → ``Competidor NNN`` (orden de entrada, NO derivado del nombre).
- ``team``            → ``Equipo A``/``Equipo B``/... por orden de aparición; **null se conserva**.
- ``category_weight`` → se conserva: es la categoría, no un dato personal.
- ``age``             → null se conserva; si hay valor, se sustituye por uno **sintético**
                        determinista (18..37).
- ``actual_weight``   → null se conserva; si hay valor, se sustituye por uno **sintético**
                        determinista dentro de la categoría.

No se guardan hashes ni el mapeo nombre→seudónimo: el resultado es irreversible.
El anonimizador se niega a escribir si detecta que un nombre real aparece en la salida.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dataset import CATEGORY_ORDER, Dataset, DatasetError, Competitor, load_dataset, null_profile

TEAM_LABELS = "ABCDEFGH"


def _category_limit(category: str) -> float:
    return float(category.split()[0].lstrip("-"))


def anonymize(dataset: Dataset) -> Dataset:
    """Devuelve un Dataset anonimizado equivalente (mismos conteos y mismos nulos)."""
    team_map: dict[str, str] = {}
    competitors: list[Competitor] = []

    for index, competitor in enumerate(dataset.competitors, start=1):
        team = None
        if competitor.team is not None:
            if competitor.team not in team_map:
                if len(team_map) >= len(TEAM_LABELS):
                    raise DatasetError(
                        f"más de {len(TEAM_LABELS)} equipos distintos; amplía TEAM_LABELS"
                    )
                team_map[competitor.team] = f"Equipo {TEAM_LABELS[len(team_map)]}"
            team = team_map[competitor.team]

        age = None if competitor.age is None else 18 + (index % 20)
        weight = None
        if competitor.actual_weight is not None:
            limit = _category_limit(competitor.category)
            weight = round(limit - 0.5 - (index % 4), 1)

        competitors.append(
            Competitor(
                id=f"C{index:03d}",
                name=f"Competidor {index:03d}",
                category=competitor.category,
                team=team,
                age=age,
                actual_weight=weight,
            )
        )

    return Dataset(
        event_name=dataset.event_name,
        event_date=dataset.event_date,
        competitors=competitors,
        source="anonymized",
    )


def to_fixture(dataset: Dataset) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "anonymized",
        "note": (
            "Fixture anonimizado del ensayo P2.7A. Mantiene 25 participantes, la distribución "
            "real por categoría (3/2/6/7/2/5) y el perfil estructural de nulos. "
            "Edad y peso actual son valores sintéticos; en la DB no se importan (§5)."
        ),
        "event": {"name": dataset.event_name, "date": dataset.event_date},
        "categories": [
            {"name": name, "limit_kg": int(_category_limit(name))} for name in CATEGORY_ORDER
        ],
        "competitors": [
            {
                "id": c.id,
                "name": c.name,
                "team": c.team,
                "age": c.age,
                "actual_weight": c.actual_weight,
                "category_weight": _category_limit(c.category),
            }
            for c in dataset.competitors
        ],
    }


def assert_no_real_identity(original: Dataset, anonymized: Dataset) -> None:
    """Guard: ningún nombre ni equipo real puede aparecer en la salida."""
    real_names = {c.name for c in original.competitors}
    real_teams = {c.team for c in original.competitors if c.team}
    payload = json.dumps(to_fixture(anonymized), ensure_ascii=False)
    leaked = sorted(
        token
        for token in real_names | real_teams
        if token and len(token) > 2 and token in payload
    )
    if leaked:
        raise DatasetError(f"la anonimización filtró identidad real: {len(leaked)} valores")


def anonymize_file(
    source_path: str | Path, target_path: str | Path, *, force: bool = False
) -> dict[str, Any]:
    """Anonimiza ``source_path`` y escribe el fixture en ``target_path``."""
    original = load_dataset(source_path, source="real")
    anonymized = anonymize(original)
    assert_no_real_identity(original, anonymized)

    target = Path(target_path)
    if target.exists() and not force:
        raise DatasetError(f"{target} ya existe (usa --force para sobrescribir)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(to_fixture(anonymized), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    target.chmod(0o644)

    return {
        "fixture": str(target),
        "total": len(anonymized.competitors),
        "nulls_original": null_profile(original).as_dict(),
        "nulls_anonymized": null_profile(anonymized).as_dict(),
        "counts_by_category": {
            name: sum(1 for c in anonymized.competitors if c.category == name)
            for name in CATEGORY_ORDER
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Anonimiza el dataset real del ensayo P2.7A")
    parser.add_argument("source", help="dataset real (fuera del repo, 0600)")
    parser.add_argument("target", help="fixture de salida (dentro del repo)")
    parser.add_argument("--force", action="store_true", help="sobrescribir el fixture existente")
    args = parser.parse_args()

    report = anonymize_file(args.source, args.target, force=args.force)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    original = report["nulls_original"]
    anonymized = report["nulls_anonymized"]
    if original != anonymized:
        print("ERROR: el perfil de nulos cambió al anonimizar")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

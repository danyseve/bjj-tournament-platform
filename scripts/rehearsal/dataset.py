"""Carga, validación y planificación del dataset del ensayo (P2.7A).

Módulo PURO: no importa nada de Bracket, así que se puede testear fuera del
contenedor.

Privacidad (P2.7A §2/§3/§19)
----------------------------
- modo ``real``:       el fichero vive FUERA del repo (0700/0600) y no se versiona.
- modo ``anonymized``: fixture versionado con la identidad sustituida.
Los informes usan siempre ids (``C001``...) y conteos: nunca nombres reales.

Política de nulos (§5): el modelo de Bracket NO tiene columnas para ``age``,
``actual_weight`` ni ``category_weight``. Por decisión explícita del operador:
  - la categoría (``category_weight``) se mapea al nombre del stage;
  - ``age`` y ``actual_weight`` NO se importan (no se inventan);
  - ``team`` se descarta en el mapeo individual (1 team = 1 competidor),
    se conserva sólo como procedencia en el fixture.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- Criterios de aceptación del ensayo (P2.7A §2/§9) -----------------------

EVENT_NAME = "Torneo Interno CREE Masculino"
REHEARSAL_TOURNAMENT_NAME = "Torneo Interno CREE Masculino — REHEARSAL"
EVENT_DATE = "2026-10-17"

CATEGORY_ORDER: tuple[str, ...] = ("-62 kg", "-66 kg", "-71 kg", "-77 kg", "-84 kg", "-92 kg")
EXPECTED_COUNTS: dict[str, int] = {
    "-62 kg": 3,
    "-66 kg": 2,
    "-71 kg": 6,
    "-77 kg": 7,
    "-84 kg": 2,
    "-92 kg": 5,
}
TOTAL_COMPETITORS = sum(EXPECTED_COUNTS.values())  # 25

ANONYMIZED_NAME_RE = re.compile(r"^Competidor \d{3}$")
MAX_PLAYER_NAME = 30  # PlayerBody.name: max_length=30 en el modelo de Bracket

DATASET_SCHEMA_VERSION = 1

# Campos del dataset que el modelo de Bracket NO puede representar (§5):
# no se inventan ni se degradan; se documentan y el importador los reporta.
UNREPRESENTABLE_FIELDS: tuple[str, ...] = ("age", "actual_weight", "category_weight")


class DatasetError(Exception):
    """Error de formato o de validación del dataset (aborta el ensayo)."""


# --- Modelo de datos --------------------------------------------------------


@dataclass(frozen=True)
class Competitor:
    """Un participante del torneo, ya normalizado."""

    id: str
    name: str
    category: str
    team: str | None = None
    age: int | None = None
    actual_weight: float | None = None

    @property
    def has_team(self) -> bool:
        return self.team is not None

    @property
    def has_age(self) -> bool:
        return self.age is not None

    @property
    def has_weight(self) -> bool:
        return self.actual_weight is not None


@dataclass(frozen=True)
class Dataset:
    event_name: str
    event_date: str
    competitors: list[Competitor]
    source: str = "unknown"  # "real" | "anonymized"

    @property
    def categories(self) -> list[str]:
        present = {c.category for c in self.competitors}
        return [c for c in CATEGORY_ORDER if c in present]


@dataclass
class NullProfile:
    """Perfil estructural de nulos (se conserva al anonimizar, §3)."""

    team_null: int = 0
    age_null: int = 0
    weight_null: int = 0
    total: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "team_null": self.team_null,
            "age_null": self.age_null,
            "actual_weight_null": self.weight_null,
        }


@dataclass
class Plan:
    """Plan de importación por categoría (sin tocar la DB)."""

    categories: dict[str, list[Competitor]] = field(default_factory=dict)

    @property
    def team_count(self) -> int:
        return sum(len(v) for v in self.categories.values())

    def team_counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.categories.items()}

    def bracket_size(self, category: str) -> int:
        """Tamaño de cuadro que admite Bracket (potencia de 2) para esta categoría."""
        return next_power_of_two(len(self.categories[category]))

    def bracket_sizes(self) -> dict[str, int]:
        return {k: self.bracket_size(k) for k in self.categories}

    def byes(self) -> dict[str, int]:
        """Slots vacíos = byes (Bracket sólo admite cuadros de 2/4/8/16/32)."""
        return {k: self.bracket_size(k) - len(v) for k, v in self.categories.items()}

    def total_slots(self) -> int:
        return sum(self.bracket_sizes().values())

    def total_byes(self) -> int:
        return sum(self.byes().values())


# --- Normalización ----------------------------------------------------------


def next_power_of_two(value: int) -> int:
    """Bracket sólo genera cuadros de eliminación directa de 2/4/8/16/32 equipos."""
    size = 2
    while size < value:
        size *= 2
    return size


def normalize_category(value: Any) -> str:
    """Acepta 62, '62', '-62', '-62 kg', '-62kg' y devuelve '-62 kg'."""
    if value is None:
        raise DatasetError("categoría ausente (category_weight=null)")
    text = str(value).strip().replace("kg", "").strip()
    if not text.startswith("-"):
        text = "-" + text.lstrip("+")
    try:
        number = int(float(text))
    except ValueError as exc:  # pragma: no cover - depende del dataset de entrada
        raise DatasetError(f"categoría no parseable: {value!r}") from exc
    name = f"-{abs(number)} kg"
    if name not in CATEGORY_ORDER:
        raise DatasetError(f"categoría no esperada en el ensayo: {name!r}")
    return name


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# --- Carga ------------------------------------------------------------------


def _extract_records(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        for key in ("competitors", "participants", "participantes", "data", "records"):
            if key in raw and isinstance(raw[key], list):
                return [dict(item) for item in raw[key]]
        raise DatasetError(
            "JSON sin lista de participantes (se esperaba una clave "
            "'competitors'/'participants'/'participantes'/'data')"
        )
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    raise DatasetError("JSON no soportado: se esperaba una lista o un objeto con 'competitors'")


def load_dataset(path: str | Path, source: str = "unknown") -> Dataset:
    """Carga el dataset desde JSON y lo normaliza (no valida contra las cuentas)."""
    file_path = Path(path)
    if not file_path.is_file():
        raise DatasetError(f"dataset no encontrado: {file_path}")
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"JSON inválido en {file_path}: {exc}") from exc

    records = _extract_records(raw)
    if not records:
        raise DatasetError("dataset vacío")

    event_name = EVENT_NAME
    event_date = EVENT_DATE
    if isinstance(raw, dict):
        event = raw.get("event") if isinstance(raw.get("event"), dict) else raw
        event_name = _clean_str(event.get("name")) or event_name
        event_date = _clean_str(event.get("date")) or event_date
        if _clean_str(raw.get("source")):
            source = _clean_str(raw.get("source")) or source

    competitors: list[Competitor] = []
    for index, record in enumerate(records, start=1):
        name = _clean_str(record.get("name")) or _clean_str(record.get("nombre"))
        if not name:
            raise DatasetError(f"participante #{index} sin nombre")
        category = normalize_category(
            record.get("category_weight", record.get("category", record.get("categoria")))
        )
        competitors.append(
            Competitor(
                id=_clean_str(record.get("id")) or f"C{index:03d}",
                name=name,
                category=category,
                team=_clean_str(record.get("team")) or _clean_str(record.get("equipo")),
                age=_as_int(record.get("age", record.get("edad"))),
                actual_weight=_as_float(
                    record.get("actual_weight", record.get("peso_actual", record.get("weight")))
                ),
            )
        )

    return Dataset(
        event_name=event_name, event_date=event_date, competitors=competitors, source=source
    )


# --- Validación -------------------------------------------------------------


def counts_by_category(dataset: Dataset) -> dict[str, int]:
    counts = {name: 0 for name in CATEGORY_ORDER}
    for competitor in dataset.competitors:
        counts[competitor.category] = counts.get(competitor.category, 0) + 1
    return counts


def null_profile(dataset: Dataset) -> NullProfile:
    competitors = dataset.competitors
    return NullProfile(
        team_null=sum(1 for c in competitors if not c.has_team),
        age_null=sum(1 for c in competitors if not c.has_age),
        weight_null=sum(1 for c in competitors if not c.has_weight),
        total=len(competitors),
    )


def validate(dataset: Dataset, mode: str) -> tuple[list[str], list[str]]:
    """Devuelve (errores, avisos). Cualquier error aborta la importación."""
    errors: list[str] = []
    warnings: list[str] = []

    if mode not in {"real", "anonymized"}:
        errors.append(f"modo inválido: {mode!r}")
        return errors, warnings

    total = len(dataset.competitors)
    if total != TOTAL_COMPETITORS:
        errors.append(f"participantes: {total} != esperado {TOTAL_COMPETITORS}")

    counts = counts_by_category(dataset)
    for category in CATEGORY_ORDER:
        expected = EXPECTED_COUNTS[category]
        if counts.get(category, 0) != expected:
            errors.append(
                f"categoría {category}: {counts.get(category, 0)} participantes != esperado {expected}"
            )
    unexpected = {k: v for k, v in counts.items() if k not in EXPECTED_COUNTS and v}
    if unexpected:
        errors.append(f"categorías no esperadas: {sorted(unexpected)}")

    seen_ids: set[str] = set()
    for competitor in dataset.competitors:
        if competitor.id in seen_ids:
            errors.append(f"id duplicado en el dataset: {competitor.id}")
        seen_ids.add(competitor.id)
        if len(competitor.name) > MAX_PLAYER_NAME:
            warnings.append(
                f"{competitor.id}: nombre de {len(competitor.name)} caracteres (>{MAX_PLAYER_NAME}); "
                "se puede insertar, pero la API de edición lo rechazaría"
            )
        if mode == "anonymized" and not ANONYMIZED_NAME_RE.match(competitor.name):
            errors.append(f"{competitor.id}: nombre no anonimizado en modo anonymized")
        if mode == "anonymized" and competitor.team is not None:
            if re.search(r"\b(S\.?A\.?|C\.?B\.?|club|gimnasio)\b", competitor.team, re.IGNORECASE):
                warnings.append(f"{competitor.id}: equipo posiblemente identificable")

    return errors, warnings


def build_plan(dataset: Dataset) -> Plan:
    """Agrupa competidores por categoría respetando el orden de entrada."""
    plan = Plan()
    for category in CATEGORY_ORDER:
        members = [c for c in dataset.competitors if c.category == category]
        if members:
            plan.categories[category] = members
    return plan


def pii_free_summary(dataset: Dataset, mode: str) -> dict[str, Any]:
    """Resumen sin PII (ids y conteos) apto para logs e informes."""
    plan = build_plan(dataset)
    return {
        "mode": mode,
        "event": dataset.event_name,
        "date": dataset.event_date,
        "total": len(dataset.competitors),
        "counts_by_category": counts_by_category(dataset),
        "nulls": null_profile(dataset).as_dict(),
        "plan_team_counts": plan.team_counts(),
        "bracket_sizes": plan.bracket_sizes(),
        "byes": plan.byes(),
        "total_byes": plan.total_byes(),
        "unsupported_metadata": {
            "fields": list(UNREPRESENTABLE_FIELDS),
            "age_present": sum(1 for c in dataset.competitors if c.age is not None),
            "age_null": sum(1 for c in dataset.competitors if c.age is None),
            "actual_weight_present": sum(
                1 for c in dataset.competitors if c.actual_weight is not None
            ),
            "actual_weight_null": sum(1 for c in dataset.competitors if c.actual_weight is None),
            "team_present": sum(1 for c in dataset.competitors if c.team is not None),
            "team_null": sum(1 for c in dataset.competitors if c.team is None),
        },
    }

"""P2.7A — tests del ensayo con torneo real (dataset, política de nulls, anonimización).

Se pueden ejecutar de las dos formas:

    python3 tests/test_rehearsal_dataset.py     # sin dependencias
    pytest tests/test_rehearsal_dataset.py      # si pytest está disponible

No tocan la base de datos ni la red: validan los módulos puros de
``scripts/rehearsal/`` y el fixture versionado.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REHEARSAL_DIR = ROOT / "scripts" / "rehearsal"
FIXTURE = ROOT / "tests" / "fixtures" / "tournament-rehearsal-anonymized.json"
PRIVATE_DATASET = Path("/home/ubuntu/private/bjj-rehearsal/dataset-real.json")

sys.path.insert(0, str(REHEARSAL_DIR))


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, REHEARSAL_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # necesario para los dataclasses del módulo
    spec.loader.exec_module(module)
    return module


dataset_mod = _load("rehearsal_dataset", "dataset.py")
anonymize_mod = _load("rehearsal_anonymize", "anonymize.py")

EXPECTED_COUNTS = {"-62 kg": 3, "-66 kg": 2, "-71 kg": 6, "-77 kg": 7, "-84 kg": 2, "-92 kg": 5}
EXPECTED_BRACKETS = {"-62 kg": 4, "-66 kg": 2, "-71 kg": 8, "-77 kg": 8, "-84 kg": 2, "-92 kg": 8}
EXPECTED_BYES = {"-62 kg": 1, "-66 kg": 0, "-71 kg": 2, "-77 kg": 1, "-84 kg": 0, "-92 kg": 3}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
ANONYM_NAME_RE = re.compile(r"^Competidor \d{3}$")


def _synthetic_dataset(counts: dict[str, int] | None = None) -> Path:
    """Dataset sintético en el modo 'real' (sin PII) para los tests."""
    counts = counts or EXPECTED_COUNTS
    rows = []
    index = 0
    for category, amount in counts.items():
        limit = int(category.replace("-", "").replace(" kg", ""))
        for _ in range(amount):
            index += 1
            rows.append(
                {
                    "name": f"Athlete Real {index:03d}",
                    "team": None if index % 3 == 0 else f"Club Real {index % 4}",
                    "age": None if index % 5 == 0 else 20 + index % 10,
                    "actual_weight": None if index % 4 == 0 else float(limit) - 0.8,
                    "category_weight": limit,
                }
            )
    path = Path(tempfile.mkdtemp(prefix="rehearsal-test-")) / "synthetic-real.json"
    path.write_text(json.dumps({"competitors": rows}, ensure_ascii=False), encoding="utf-8")
    return path


# --- schema import / conteos / nulls ---------------------------------------


def test_schema_y_conteos():
    path = _synthetic_dataset()
    try:
        dataset = dataset_mod.load_dataset(path, source="real")
        errors, _ = dataset_mod.validate(dataset, "real")
        assert errors == [], errors
        assert len(dataset.competitors) == 25
        assert dataset_mod.counts_by_category(dataset) == EXPECTED_COUNTS
    finally:
        path.unlink(missing_ok=True)


def test_politica_de_nulls_se_preserva():
    path = _synthetic_dataset()
    try:
        dataset = dataset_mod.load_dataset(path, source="real")
        profile = dataset_mod.null_profile(dataset).as_dict()
        assert profile["total"] == 25
        assert profile["team_null"] > 0 and profile["age_null"] > 0
        assert profile["actual_weight_null"] > 0
        # el modelo de Bracket no tiene edad/peso/categoría: no se inventan, se documentan
        assert dataset_mod.UNREPRESENTABLE_FIELDS == ("age", "actual_weight", "category_weight")
    finally:
        path.unlink(missing_ok=True)


def test_plan_de_cuadros_con_byes():
    path = _synthetic_dataset()
    try:
        plan = dataset_mod.build_plan(dataset_mod.load_dataset(path, source="real"))
        assert plan.bracket_sizes() == EXPECTED_BRACKETS
        assert plan.byes() == EXPECTED_BYES
        assert plan.total_slots() == 32
        assert plan.team_count == 25
        assert plan.total_byes() == 7
    finally:
        path.unlink(missing_ok=True)


def test_validacion_detecta_distribucion_incorrecta():
    path = _synthetic_dataset({**EXPECTED_COUNTS, "-71 kg": 7})
    try:
        dataset = dataset_mod.load_dataset(path, source="real")
        errors, _ = dataset_mod.validate(dataset, "real")
        assert errors and any("-71 kg" in error for error in errors)
    finally:
        path.unlink(missing_ok=True)


# --- anonimización / no PII -------------------------------------------------


def test_anonimizacion_sustituye_identidad_y_conserva_estructura():
    path = _synthetic_dataset()
    output = path.with_name("_anon_fixture.json")
    try:
        real = dataset_mod.load_dataset(path, source="real")
        anonymous = anonymize_mod.anonymize(real)
        payload = anonymize_mod.to_fixture(anonymous)
        output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        raw = output.read_text(encoding="utf-8")
        original = json.loads(path.read_text(encoding="utf-8"))

        anonymize_mod.assert_no_real_identity(real, anonymous)
        for row in original["competitors"]:
            assert row["name"] not in raw, "nombre real filtrado en el fixture"
            if row["team"]:
                assert row["team"] not in raw, "equipo real filtrado en el fixture"

        anonymous = dataset_mod.load_dataset(output, source="anonymized")
        assert len(anonymous.competitors) == 25
        assert dataset_mod.counts_by_category(anonymous) == EXPECTED_COUNTS
        assert dataset_mod.null_profile(anonymous).as_dict() == dataset_mod.null_profile(
            dataset_mod.load_dataset(path, source="real")
        ).as_dict()
        assert all(ANONYM_NAME_RE.match(c.name) for c in anonymous.competitors)
        assert not EMAIL_RE.search(raw)
    finally:
        path.unlink(missing_ok=True)
        output.unlink(missing_ok=True)


def test_anonimizacion_es_determinista():
    path = _synthetic_dataset()
    try:
        real = dataset_mod.load_dataset(path, source="real")
        first = anonymize_mod.to_fixture(anonymize_mod.anonymize(real))
        second = anonymize_mod.to_fixture(anonymize_mod.anonymize(real))
        assert first == second
    finally:
        path.unlink(missing_ok=True)


# --- fixture versionado -----------------------------------------------------


def test_fixture_versionado_sin_pii():
    assert FIXTURE.exists(), f"falta el fixture anonimizado: {FIXTURE}"
    raw = FIXTURE.read_text(encoding="utf-8")
    assert not EMAIL_RE.search(raw), "el fixture contiene emails"
    dataset = dataset_mod.load_dataset(FIXTURE, source="anonymized")
    errors, _ = dataset_mod.validate(dataset, "anonymized")
    assert errors == [], errors
    assert len(dataset.competitors) == 25
    assert dataset_mod.counts_by_category(dataset) == EXPECTED_COUNTS
    assert all(ANONYM_NAME_RE.match(c.name) for c in dataset.competitors)
    assert dataset_mod.build_plan(dataset).bracket_sizes() == EXPECTED_BRACKETS


def test_fixture_reproduce_los_nulls_del_dataset_real_si_esta_disponible():
    """Sólo se ejecuta en el host donde vive el dataset real (fuera del repo)."""
    if not PRIVATE_DATASET.exists():
        print("(omitido: dataset real no disponible en este host)")
        return
    real = dataset_mod.load_dataset(PRIVATE_DATASET, source="real")
    anonymous = dataset_mod.load_dataset(FIXTURE, source="anonymized")
    assert dataset_mod.null_profile(real).as_dict() == dataset_mod.null_profile(anonymous).as_dict()
    assert dataset_mod.counts_by_category(real) == dataset_mod.counts_by_category(anonymous)


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests OK")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

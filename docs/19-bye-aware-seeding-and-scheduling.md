# 19 — Seeding *bye-aware* y planificación estructural (P2.8B · F2)

Estado: **P2.8B F2 — IMPLEMENTADA Y VALIDADA** (2026-10-03). Cambio **solo de motor + tests + CI** en el
fork `danyseve/bracket` (`master`, HEAD `8ec816b`). Producción **sin migrar**: pin del submódulo
`29b6146`, imagen productiva `danyseve1/bracket-bjj:29b6146-r1`, `tournament_id=6` intacto y
`WRITE=false`. La decisión sobre el ensayo queda abierta (§8).

Continúa a `docs/17-bye-auto-advance.md` (P2.8A: avance **aguas abajo**) y a
`docs/18-bracket-topology-domain-model.md` §2–§4 (diseño **aguas arriba**: reparto de slots y
scheduler). Este documento registra lo implementado, con evidencia `archivo:línea`.

---

## 1. Problema antiguo

Cadena real de construcción (sin cambios respecto a `docs/18` §1.1): el stage item se crea con
`team_count` inputs **vacíos** (`sql/stage_items.py`) y los partidos se construyen **en ese momento**
(`logic/scheduling/builder.py`), antes de conocer la lista final de inscritos. Los equipos se asignan
después a los slots y ocupaban **siempre los primeros**, de modo que los vacíos quedaban al final. La
primera ronda empareja slots consecutivos `(1,2) (3,4) (5,6) (7,8)…`, así que los huecos del final
caían **dos a dos en el mismo combate**.

Dos defectos reales:

1. **Ghost `∅/∅`**: un combate que nadie puede disputar nunca, que aun así recibía tatami, hora y
   posición de planning (y consumía `duration_minutes` de rejilla).
2. **Byes concentrados**: los huecos se apilaban en una zona del cuadro, regalando avances en cadena
   (el avance estructural en sí ya lo resolvía P2.8A).

Evidencia del ensayo (`tournament_id=6`): `6/8 → (1..6) reales · (7,8) ∅/∅` (0 byes, 1 ghost) y
`5/8 → (1..4) reales · (5,6) T/∅ · (7,8) ∅/∅` (1 bye, 1 ghost). En total, primera ronda:
**16 partidos = 11 reales + 3 byes + 2 ghosts**.

Causa secundaria: las filas de `stage_item_inputs` se agregaban con `array_agg` **sin `ORDER BY`**, de
modo que el emparejamiento podía depender del orden físico devuelto por PostgreSQL.

---

## 2. Algoritmo nuevo

Todo el reparto vive en un módulo **puro** (`backend/bracket/logic/scheduling/seeding.py`) y se aplica
**antes** de `determine_matches_first_round`.

### 2.1 Invariante de tamaño

`B = menor potencia de 2 ≥ N` (`seeding.py:20` `bracket_size_for_entrant_count`). No se
sobredimensiona el cuadro. Con `N < 2` no se construye un `SINGLE_ELIMINATION` válido (devuelve
`None`). Consecuencia: `N ≥ B/2`, luego `byes = B − N ≤ B/2 = nº de combates de primera ronda`, que es
justo la condición para poder repartir **a lo sumo un hueco por combate**.

### 2.2 Reparto

- `byes = B − N` slots vacíos se reparten **uno por combate** (`seeding.py:36`
  `bye_aware_bye_pairs`): los pares que reciben bye se eligen con paso uniforme
  `floor((2i + 1) · pairs / (2 · byes))`, `i = 0 … byes−1`, sobre los `pairs = B/2` combates. El paso es
  `pairs/byes ≥ 1`, así que los pares son distintos y están ordenados, y quedan repartidos por **todo**
  el cuadro (no agrupados en una mitad).
- `seeding.py:52` `distribute_entrants_into_slots(entrants, bracket_size)` devuelve la lista de `B`
  posiciones: en un par *bye* el inscrito ocupa el primer slot y el hueco el segundo; en un par normal,
  dos inscritos. Es **determinista** y **preserva el orden recibido** de los inscritos.
- `seeding.py:91` `order_bye_aware(slots, bracket_size)` reordena una lista de slots ya construida
  conservando el orden relativo de inscritos y de huecos. Es **no-op** para un cuadro lleno, vacío o ya
  repartido.
- Guardas: `ValueError` si el tamaño no es potencia de 2, si hay más inscritos que slots o si
  `B > 2N` (reparto imposible sin ghosts: hay que reducir el cuadro, no tolerar ghosts).

### 2.3 Matriz N / B / byes / ghosts

| N | B | byes | ghosts | 1ª ronda |
|---|---|---|---|---|
| 2 | 2 | 0 | 0 | 1 combate real |
| 3 | 4 | 1 | 0 | 1 real + 1 `T/∅` |
| 4 | 4 | 0 | 0 | 2 reales |
| 5 | 8 | 3 | 0 | 1 real + 3 `T/∅` |
| 6 | 8 | 2 | 0 | 2 reales + 2 `T/∅` |
| 7 | 8 | 1 | 0 | 3 reales + 1 `T/∅` |
| 8 | 8 | 0 | 0 | 4 reales |
| 9 | 16 | 7 | 0 | 1 real + 7 `T/∅` |
| 15 | 16 | 1 | 0 | 7 reales + 1 `T/∅` |

### 2.4 Fairness (lo que **no** hace esta fase)

- No hay sorteo, ni semilla, ni cabezas de serie, ni ranking deportivo: **se preserva el orden lógico
  de inscritos recibido**. Reproducible y testeable.
- No se reordena por orden temporal de INSERT ni por el orden físico de la consulta: los slots se leen
  **por `slot`** (`sql/stages.py:81`, `array_agg(sii ORDER BY sii.slot)`; `elimination.py:17` vuelve a
  ordenar por `slot` antes de decidir), y los partidos por `id` (`sql/stages.py:59`).
- La consecuencia deportiva buscada es solo una: **ningún hueco contra hueco** y byes repartidos. El
  seeding "de verdad" (sorteo con semilla) sigue pendiente de una fase posterior.

---

## 3. Clasificación estructural

`backend/bracket/logic/scheduling/structural.py`, derivada **exclusivamente de la topología** que ya
calculaba el resolver de P2.8A (`logic/ranking/elimination.py` `get_dead_slots`), sin columna ni
migración nueva:

| Estado | Definición | Planning |
|---|---|---|
| `PLAYABLE` | dos slots pueden recibir inscrito (equipo real, input tentativo o ganador de una rama viva) | recibe tatami/hora/posición |
| `STRUCTURAL_BYE` | un solo slot posible: bye directo o walkover sobre una rama muerta | **no** recibe planning |
| `DEAD` | ningún slot posible (`∅/∅`) | **no** recibe planning |

`structural.py:25` `MatchStructure`, `:31` `_classify`, `:39` `get_match_structures`, `:52`
`get_playable_match_ids`. **PENDING no es un estado aparte**: un combate futuro cuyos dos feeders están
vivos es `PLAYABLE` (es un combate futuro planificable); si un feeder está muerto, el combate pasa a
`STRUCTURAL_BYE` o `DEAD` por la propia topología.

---

## 4. Scheduler

`logic/planning/matches.py:24` `get_matches_to_schedule` filtra el cuadro y devuelve, en orden de
ronda, **solo** los combates `PLAYABLE`; `:66` es el único recorrido del bucle de
`schedule_all_unscheduled_matches`. Consecuencias:

- un bye o un ghost **no** recibe `court_id`, `start_time` ni `position_in_schedule`;
- **no avanza la rejilla**: no consume `duration_minutes`, así que los combates siguientes arrancan
  antes (la programación se compacta);
- un cuadro completo (sin huecos) conserva el comportamiento anterior exacto, porque todos sus
  partidos son `PLAYABLE`;
- no se borra planning ya existente: el cambio solo decide a quién se le **asigna** (cuadros
  existentes intactos).

---

## 5. Tests

Nuevos, puros y derivados de la topología (sin números mágicos):

- `tests/unit_tests/seeding_test.py` — 17 tests: invariante `B`, matriz N/B/byes/ghosts de §2.3,
  determinismo, conservación (cada inscrito exactamente una vez), guardas de tamaño y no-op de
  `order_bye_aware`.
- `tests/unit_tests/structural_scheduling_test.py` — 9 tests: árboles construidos con los **propios**
  constructores del motor (`determine_matches_first_round` / `determine_matches_subsequent_round`), 0
  partidos `DEAD` para 2/3/4/5/6/7/8/9/15, `STRUCTURAL_BYE == B − N`, cuadro completo preservado y solo
  `PLAYABLE` entregados al planner.

`tests/unit_tests/elimination_structural_test.py` (P2.8A) **no se toca**: sus topologías están escritas
a mano y documentan el comportamiento del resolver, no el reparto. Sigue en verde.

Validación local en `oracle-jiujitsu` (host sin `node`, `uv`), con el **comando exacto del CI**
(`ENVIRONMENT=CI uv run pytest --cov --cov-report=xml .`, contra Postgres 16 en `:5532`): `pytest`
**170 pasan / 0 fallos** · `mypy` **Success: no issues found in 171 source files** · `pyrefly`
**0 errores** · `pylint` **10.00/10** · `ruff format --check` limpio · `ruff check` limpio ·
`vulture` solo avisos preexistentes (`unused attribute` / `unused variable`), **ningún** `unused
function/class/method`, así que el gate del CI (`! uv run vulture | grep "unused function\|unused
class\|unused method"` → exit 0) queda verde. Sin cambio de API/UI, así que el frontend no se toca
(su gate `test:unit` 17/17 ya está en el CI desde PRE-F2).

CI real del fork sobre el HEAD `8ec816b` — **los 4 jobs verdes**:

| job | resultado | run |
|---|---|---|
| backend | success | [37131093342](https://github.com/danyseve/bracket/actions/runs/37131093342) |
| docker build | success | [37131093521](https://github.com/danyseve/bracket/actions/runs/37131093521) |
| docs test | success | [37131093364](https://github.com/danyseve/bracket/actions/runs/37131093364) |
| frontend (`test:unit` 17/17 ejecutados) | success | [37131093393](https://github.com/danyseve/bracket/actions/runs/37131093393) |

### 5bis. Validación end-to-end en `bracket_test` (§12)

Fixture `scripts/rehearsal/f2_fixture.py`, ejecutado **dentro del contenedor de la imagen nueva**
(`danyseve1/bracket-bjj:8ec816b-r1`, `PG_DSN` → `bracket_test`), recorriendo por cada caso la cadena
completa: `create stage item` (B slots vacíos) → `distribute_entrants_into_slots` → inscritos
asignados a los slots → `build_matches_for_stage_item` → resolver estructural P2.8A
(`update_inputs_in_complete_elimination_stage_item`) → `schedule_all_unscheduled_matches`.

| caso | B | matches | `PLAYABLE` | `STRUCTURAL_BYE` | `DEAD`(ghosts) | planificados | scores |
|---|---|---|---|---|---|---|---|
| 3/4 | 4 | 3 | 2 | 1 | **0** | 2 | 0 |
| 5/8 | 8 | 7 | 4 | 3 | **0** | 4 | 0 |
| 6/8 | 8 | 7 | 5 | 2 | **0** | 5 | 0 |
| 7/8 | 8 | 7 | 6 | 1 | **0** | 6 | 0 |

Resultado: `ok: true` en los 4 casos (`FIXTURE_EXIT=0`, informe JSON con `problems: []`), **0
partidos `∅/∅`**, `STRUCTURAL_BYE == B − N`, los byes estructurales **sin** `court_id`,
`start_time` ni `position_in_schedule`, y **solo** los jugables planificados (posiciones
`0…n−1` contiguas). Cero scores ficticios. Los torneos `F2FIX-*` (ids 3–6 de `bracket_test`) quedan
como evidencia y el fixture es idempotente (se borran y recrean solo esos torneos).

---

## 6. Compatibilidad

- El reparto corre **solo al construir** un cuadro nuevo; no hay re-seeding de cuadros existentes ni
  backfill. `order_bye_aware` es no-op si el cuadro está lleno, vacío o ya repartido.
- El **resolver estructural de P2.8A no cambia** y sigue siendo la red de seguridad: aunque un cuadro
  llegue con huecos mal repartidos (p. ej. creado por la UI eligiendo slots a mano), los byes y
  walkovers se siguen resolviendo.
- Sin cambios de esquema, `alembic`, contrato de API ni frontend. `is_playable` **no** se expone en la
  API: el Bridge ya filtra por "ambos `team_id` presentes" y no se ha tocado (§9 de la fase).
- `tournament_id` 1, 2 y 6 quedan **sin tocar** (0 scores, 0 planning, 26 matches, 6 stages).

---

## 7. Ficheros y puntos de anclaje

| Fichero | Cambio |
|---|---|
| `backend/bracket/logic/scheduling/seeding.py` | **nuevo** — invariante, reparto y reordenación puros |
| `backend/bracket/logic/scheduling/structural.py` | **nuevo** — `MatchStructure` y predicados |
| `backend/bracket/logic/scheduling/elimination.py:17,40` | `get_first_round_inputs` + uso antes del emparejamiento |
| `backend/bracket/logic/planning/matches.py:24,66` | solo `PLAYABLE` al planner |
| `backend/bracket/sql/stages.py:59,81` | orden estable (`ORDER BY m.id`, `ORDER BY sii.slot`) |
| `backend/tests/unit_tests/seeding_test.py` | **nuevo** — 17 tests |
| `backend/tests/unit_tests/structural_scheduling_test.py` | **nuevo** — 9 tests |
| `scripts/rehearsal/f2_fixture.py` (repo principal) | **nuevo** — fixture end-to-end en `bracket_test` (§12) |

Imagen validada: `danyseve1/bracket-bjj:8ec816b-r1` (id `97f7f0d89ce7`, label
`BRACKET_UPSTREAM_COMMIT=8ec816b16814198dbc5e58007d895471ad3c178e`, `RECIPE_REVISION=r1`, locks
`uv.lock` `24f99c8e…` y `pnpm-lock.yaml` `001f9b8e…` verificados por el propio build). **No** se ha
re-etiquetado `latest` ni tocado `29b6146-r1`.

---

## 8. Migración del ensayo (`tournament_id=6`) — DECISIÓN PENDIENTE

El ensayo se construyó con el reparto antiguo (3 byes directos + 2 ghosts). **No se ha re-seedeado
nada.** Opciones, para decidir tras validar la lógica nueva:

- **A — Dejarlo como evidencia histórica de P2.8A.** Coste 0; el cuadro conserva 2 ghosts (que ya no
  consumirán planning si algún día se planifica, gracias a §4).
- **B — Recrear solo los `stage_item_inputs` del ensayo** (backup completo previo, validación fila a
  fila, manteniendo participantes/categorías). Deja el ensayo "bonito" pero reescribe datos ya
  auditados y exige re-resolver el árbol.
- **C — Crear un ensayo P2.8B nuevo y separado** (3/5/6/7 inscritos) y dejar el 6 intacto. Compara
  viejo vs nuevo sin tocar evidencia.

Recomendación: **C** para la demostración y **A** para el histórico. No se ejecuta nada sin
autorización.

---

## 9. No hacer (sigue fuera de alcance)

Modelo de dominio Club/Competitor/Team/Entrant, labels contextuales, branding, Tatami 2–6, `WRITE`,
Access/DNS/Tunnel, doble eliminación. Y en esta fase: **no** se bumpea el pin del submódulo, **no** se
reconstruye la imagen productiva, **no** se despliega y **no** se toca `tournament_id=6`.

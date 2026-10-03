# 18 - Topología de cuadro, modelo de dominio y UX para BJJ (P2.8B - diseño)

Estado: **P2.8B - DESIGN READY ✅** · **F1 (UX/copy) IMPLEMENTADA, DESPLEGADA Y VALIDADA** (2026-10-03, ver §13) · **F2 (topología/seeding/scheduler) = ENGINE + REHEARSAL VALIDATED ✅** en el fork `danyseve/bracket` @ `8ec816b`, **desplegada** (pin `8ec816b`, imagen `8ec816b-r1`, rollback `29b6146-r1`): detalle y evidencia real del ensayo en `docs/19-bye-aware-seeding-and-scheduling.md` §5ter y §14. Deuda funcional **UI AUTO-SEED GAP**: **RESOLVED ✅** en la fase **F2C** (§15 y
`docs/20-generate-bracket-ui.md`): fork `8ec816b` → `886ff13`, imagen `danyseve1/bracket-bjj:886ff13-r1`
(rollback `cbab68a-r1`), acción UI explícita «Generar cuadro», endpoint con *safety gates* e idempotencia,
y ensayo real `tournament_id=10` validado por SQL read-only y visualmente. Las fases 3–4 (§10) siguen
siendo **propuesta**: sin implementar.

Alcance de esta fase (deliberadamente solo análisis y diseño): separar (A) topología/seeding del cuadro,
(B) modelo de dominio y (C) UX para BJJ, sin introducir todavía ninguna remodelación de modelo ni
migración de base de datos. Ver §11 "No hacer".

Base sobre la que se apoya: `docs/17-bye-auto-advance.md` (P2.8A resolvió el **avance estructural**
aguas abajo; este documento trata el **reparto estructural** aguas arriba).

---

## 0. Resumen de propuestas (para decisión)

| # | Propuesta | Fase |
|---|---|---|
| D1 | Elegir el tamaño de cuadro `B` = menor potencia de 2 ≥ nº de inscritos (hoy lo fija el organizador y suele sobredimensionarse) | 2 |
| D2 | Reparto *bye-aware* de slots: un slot vacío por combate, espaciados simétricamente → 0 ghosts cuando `N ≥ B/2` | 2 |
| D3 | Orden de entrada por **sorteo con semilla guardada** (no por orden de inscripción) | 2 |
| D4 | Predicado único `is_playable`/`is_structural` expuesto en la API; ghost = nodo interno oculto, no tarjeta de combate | 2 |
| D5 | Scheduler: solo combates reales reciben cancha/hora/posición; estructurales no consumen ranura | 2 |
| D6 | Nombres de ronda calculados por tamaño de cuadro en la UI (sin migración) | 1 |
| D7 | `Cancha → Tatami` (solo copy; `courts`/`court_id`/API/DB intactos) | 1 |
| D8 | Labels contextuales por tipo de torneo (`Competidores` / `Equipos` / neutral) | 1 |
| D9 | Club: `club_id` en el competidor + **snapshot** en la inscripción (opción C) | 3 |
| D10 | `Entrant` explícito solo si tras la fase 3 sigue haciendo falta | 4 |

---

## 1. Topología actual (§2)

### 1.1 Cadena real de construcción (evidencia)

| Paso | Fichero:línea | Qué hace |
|---|---|---|
| Crear el stage item | `bracket/sql/stage_items.py:54` `sql_create_stage_item_with_empty_inputs` | Crea `team_count` **inputs vacíos** con `slot = 1..team_count` |
| Asignar inscritos | UI de equipos → `sql_set_team_id_for_stage_item_input` | Los equipos ocupan los primeros slots libres, en orden |
| Construir cuadro | `bracket/logic/scheduling/builder.py:54` `build_matches_for_stage_item` (llamado desde `routes/stage_items.py:97`) | Crea rondas y partidos **al crear el stage item**, antes de conocer la lista final |
| Nº de rondas | `bracket/logic/scheduling/elimination.py:88` | Exige `team_count ∈ {2,4,8,16,32}`; otro valor → HTTP 400 |
| Nombres de ronda | `bracket/sql/rounds.py:60` | `f"Round {n:02d}"` (genérico, no localizado) |
| 1ª ronda | `bracket/logic/scheduling/elimination.py:13` `determine_matches_first_round` | Empareja **slots consecutivos**: (1,2), (3,4), (5,6), (7,8)… |
| Rondas siguientes | `.../elimination.py:39` `determine_matches_subsequent_round` | Empareja partidos consecutivos → árbol binario clásico |
| Avance estructural | `.../builder.py:73-79` → `bracket/logic/ranking/elimination.py:167` | P2.8A: resuelve byes/walkovers tras construir |

Consecuencia de diseño: **el emparejamiento se decide en el momento de crear el stage item**, con los
slots en el orden en que se dieron de alta los equipos. Como los inputs vacíos se crean del 1 al
`team_count` y los equipos se asignan desde el primero, **los vacíos quedan siempre al final**.

### 1.2 Evidencia real (ensayo `tournament_id=6`, datos anonimizados)

Cuadros del ensayo: `3/4`, `2/2`, `6/8`, `7/8`, `2/2`, `5/8`. Primera ronda por categoría:

| Cuadro | Reparto (por slots) | Byes directos `T/∅` | Ghosts `∅/∅` |
|---|---|---|---|
| 3 / 4 | (1,2) real · (3,4) `T/∅` | 1 | 0 |
| 2 / 2 | (1,2) real | 0 | 0 |
| 6 / 8 | (1..6) reales · (7,8) `∅/∅` | **0** | **1** |
| 7 / 8 | (1..6) reales · (7,8) `T/∅` | 1 | 0 |
| 2 / 2 | (1,2) real | 0 | 0 |
| 5 / 8 | (1..4) reales · (5,6) `T/∅` · (7,8) `∅/∅` | **1** | **1** |

Total primera ronda del ensayo: **16 partidos = 11 reales + 3 byes + 2 ghosts** (7 slots vacíos: la
formulación anterior de "7 BYEs" era imprecisa; ver `docs/17` §8).

### 1.3 Por qué aparecen las tres clases

1. **BYE directo `T/∅`**: en un par hay un inscrito y un slot vacío. Ocurre cuando el número de slots
   vacíos es **impar** en la frontera donde empiezan los huecos (5/8, 3/4, 7/8).
2. **Ghost `∅/∅`**: dos slots vacíos consecutivos caen en el mismo par, siempre al final del cuadro.
   Ocurre cuando el hueco empieza en un slot **par** (6/8) o hay ≥2 vacíos consecutivos (5/8).
3. **Walkover estructural posterior**: el ganador de un bye o de un ghost alimenta una ronda
   siguiente; si esa rama está muerta, el superviviente avanza sin combatir (resuelto en P2.8A).

Los tres se derivan de un único hecho: **el orden de reparto de slots no tiene en cuenta el tamaño del
cuadro**. Hoy los huecos son un subproducto del alta de inscritos, no una decisión de diseño.

---

## 2. Seeding BJJ: diseño propuesto (§3)

### 2.1 Principio

Con `B` slots y `N` inscritos, `byes = B − N`. Si `B` es la **menor potencia de 2 ≥ N**, entonces
`N ≥ B/2` y **es posible repartir los slots vacíos uno por combate**: `ghosts = 0`. Los ghosts solo son
inevitables si el cuadro se sobredimensiona (`N ≤ B/2`), y en ese caso la respuesta correcta no es
"tolerar ghosts" sino **reducir el tamaño del cuadro**.

### 2.2 Opciones comparadas

| Criterio | (a) Secuencial (hoy) | (b) Simétrica / espejo | (c) Seeding estándar de eliminación | (d) Byes según seeds |
|---|---|---|---|---|
| Reparto | slots 1..N + huecos al final | par `i` con `B+1−i` | tabla de posiciones estándar, byes a las cabezas | byes a los mejores seeds |
| Ghosts con `N ≥ B/2` | **Sí** (1–2 por cuadro) | No | No | No |
| Equidad deportiva | Mala: los huecos se concentran en una zona y regalan avances | Buena para combates, no resuelve el reparto de byes | Buena y **estándar** (cabeza 1 y 2 solo se ven en la final) | Buena, requiere seeds reales |
| Reproducibilidad | Alta (orden de inscripción) | Alta | Alta (con lista ordenada) | Alta |
| Compatibilidad `stage_item_inputs` | — | Cambia solo el `slot` | Cambia solo el `slot` | Igual |
| Cuadros existentes | — | Sin efecto | Sin efecto | Sin efecto |
| Impacto en tests | — | Medio | Medio | Medio |

Las opciones (b)/(c)/(d) son variantes de **una misma operación**: decidir qué inscrito ocupa qué
`slot` antes de que `determine_matches_first_round` empareje consecutivos.

Semántica deportiva correcta (y la que recomiendo): **(c) con reparto de byes explícito**. El "espejo"
(b) por sí solo no garantiza el reparto uniforme de byes.

### 2.3 SEEDING DESIGN (propuesta)

1. **Tamaño del cuadro**: `B = menor potencia de 2 ≥ N`. Si el organizador declara un `team_count` con
   `N ≤ B/2`, avisar y proponer reducir a `B/2` (o mantener, aceptando ~100 % de byes).
2. **Reparto de byes *bye-aware***: repartir los `B − N` slots vacíos **uno por combate de primera
   ronda**, espaciados uniformemente y simétricos respecto a las dos mitades del cuadro; el resto de
   combates, `real/real`. Regla de reparto: los combates que reciben bye se eligen con paso
   `B/2 ÷ byes` sobre el orden de combates, empezando por el primero de cada bloque simétrico.
   Garantía: `0` ghosts con `N ≥ B/2`, y **nunca dos huecos en el mismo combate**.
3. **Orden de entrada**: el orden relativo de los inscritos lo decide el organizador. Opciones:
   sorteo con **semilla guardada** (recomendado por defecto, reproducible y deportivamente neutral),
   ranking del club, o cabezas de serie explícitas (cuando existan).
4. **Posición de cada inscrito**: colocación en las posiciones estándar (`1` vs `B`, `2` vs `B−1`, …)
   según ese orden, de modo que los "mejores" solo puedan cruzarse en rondas finales.
5. **Implementación mínima propuesta** (fase 2, sin migración): función pura
   `distribute_entrants_into_slots(n_entrants, bracket_size, ordered_entrants) -> dict[slot, entrant]`
   invocada **antes** de `determine_matches_first_round`; el árbol de `matches` y el resolver P2.8A
   quedan intactos (son agnósticos al orden de los slots).

### 2.4 Resultado esperado (hoy vs propuesto)

| Caso | Hoy (secuencial) | Propuesto |
|---|---|---|
| 3 / 4 | 1 bye · 0 ghost | 1 bye · 0 ghost |
| 4 / 8 | 0 byes · 2 ghosts | `B=4` → 0 byes · 0 ghosts |
| 5 / 8 | 1 bye · 1 ghost | **3 byes · 0 ghosts** |
| 6 / 8 | 0 byes · 1 ghost | **2 byes · 0 ghosts** |
| 7 / 8 | 1 bye · 0 ghost | 1 bye · 0 ghost |
| 9 / 16 | 1 bye · 3 ghosts (mismo patrón) | **7 byes · 0 ghosts** |

### 2.5 Impacto

- **Cuadros existentes**: ninguno. Solo cambia la construcción de cuadros nuevos; `tournament_id` 1, 2 y
  6 quedan intactos.
- **Compatibilidad**: no toca esquema ni API; el cambio es local a la construcción del cuadro.
- **Tests a actualizar** (esperado): `tests/unit_tests/elimination_structural_test.py`
  (`test_six_entrants_bracket_of_eight_respects_current_seeding`, `test_five_entrants_bracket_of_eight`
  fijan el reparto actual), `tests/unit_tests/elimination_test.py` (mocks con orden de inputs) y los
  tests estructurales de `stage_items_test.py` / `matches_test.py`. El resolver estructural de P2.8A
  **no** cambia.

---

## 3. Ghost matches: estrategia (§4)

Decisión propuesta: **nodo interno + oculto en UI + excluido de la operativa**, visible solo como
estructura del cuadro.

| Ámbito | Hoy | Propuesta |
|---|---|---|
| Backend | El nodo existe y es un partido más (sin bandera) | Mantener el nodo (el árbol debe ser válido) y derivar un predicado único: `is_structural(match)` = algún slot estructuralmente vacío / ambos; exponer `is_playable` en la respuesta de la API |
| UI | Se pinta como tarjeta normal con dos "Lugar vacío" (`components/utils/match.tsx:47,65`) | Ghost: placeholder "sin combate" (sin badge de tatami/hora, sin marcador); bye: "pasa directo" con el nombre del que avanza |
| Scheduler | Se planifica igual que un combate | Excluido (ver §4) |
| Candidates (Tatami) | Ya queda fuera: el Bridge descarta lo que no cumple el contrato de asignación (`bridge-api/app/bracket_client.py` `collect_candidates`) | Mantener, pero consumiendo la bandera de la API en vez de re-derivarla del payload |

Sin migración: el predicado se deriva hoy de `stage_item_input1_id/2_id` + `team_id`. Si en fase 2 se
quiere filtrar en SQL, añadir una columna explícita es una migración trivial y compatible.

---

## 4. Scheduler: estrategia futura (§5)

### 4.1 Auditoría

- `bracket/logic/planning/matches.py:23` `schedule_all_unscheduled_matches`, invocado desde
  `bracket/routes/matches.py:136`. Recorre **todas** las etapas, stage items, rondas y partidos y
  planifica cualquier partido con `start_time` y `position_in_schedule` nulos.
- **No distingue competitivo de estructural**: un bye o un ghost recibe `court_id`, `start_time` y
  `position_in_schedule` exactamente igual que un combate, y consume `duration_minutes` de ranura.
- Asigna **una cancha por stage item** (`courts[min(i, len(courts)-1)]`, ordenado por nombre) y
  planifica **todo el cuadro de golpe**, incluidas rondas que aún no se han alcanzado.
- Evidencia del ensayo: `tournament_id=6` no tiene nada planificado (`con_court=0`, `con_hora=0`), por
  lo que los 5 nodos estructurales aún no han consumido ranura de tatami — el coste aparece en cuanto
  el organizador use la planificación automática.

### 4.2 Criterio futuro

Solo un combate **que pueda llegar a disputarse** recibe `court`, `start_time` y `position_in_schedule`.
Un nodo estructural (bye directo o ghost) **no** recibe tatami, ni hora, ni posición operativa: se le
asigna tiempo 0 y no avanza la rejilla (el hueco se cierra, la programación se compacta).

Decisiones abiertas para fase 2: (a) compactar posiciones al excluir estructurales (recomendado);
(b) marcar visualmente en la UI por qué un partido no está programado; (c) al crecer a varios tatamis,
repartir los combates de una misma categoría entre tatamis (hoy toda la categoría va a una cancha
secuencialmente).

---

## 5. Modelo de dominio actual (§6)

Evidencia de esquema (PostgreSQL del entorno, 15 tablas: `alembic_version, clubs, courts, matches,
players, players_x_teams, rankings, rounds, stage_item_inputs, stage_items, stages, teams, tournaments,
users, users_x_clubs`).

| Entidad | Tabla | Ámbito | Significado hoy |
|---|---|---|---|
| Club | `clubs` (`name`, `created`) | **Global** | Entidad deportiva/academia. Hoy solo se enlaza con **usuarios** (`users_x_clubs`, vacía en este entorno) para permisos multi-club. **No** se enlaza con competidores ni equipos. |
| Club del torneo | `tournaments.club_id` | Torneo | El torneo ya pertenece a un club (t1→1, t2→2, t6→6) |
| Jugador | `players` (`name`, `tournament_id`, elo/wins…) | **Torneo** | Persona que compite, pero **identidad local al torneo**: la misma persona en 3 torneos son 3 filas. Sin club, sin historial global |
| Equipo | `teams` (`name`, `tournament_id`, `logo_path`, ranking) | **Torneo** | Contenedor-inscripción del cuadro, con N jugadores vía `players_x_teams` (M2M, sin unicidad; `tournaments.players_can_be_in_multiple_teams`) |
| Entrante | `stage_item_inputs` (`slot`, `team_id` **o** `winner_from_stage_item_id`+`winner_position`, + puntos/wins/draws/losses) | Stage item | **La unidad que entra al cuadro** y la que se clasifica |
| Estructura | `stages`, `stage_items`, `rounds`, `matches` | Torneo | Árbol: `matches` referencia inputs (1ª ronda) o ganadores de partidos previos |
| Tatami | `courts` (`name`, `tournament_id`) | Torneo | 1 tatami hoy |

Restricciones relevantes: `stage_item_inputs (stage_item_id, team_id)` UNIQUE (un equipo no puede
repetirse en la misma categoría); `players_x_teams` sin unicidad (duplicados posibles).

**Confirmaciones pedidas:**

1. En torneo individual, hoy **1 competidor = 1 `player` + 1 `team`** que lo representa: en el ensayo,
   25 equipos con **exactamente 1 jugador** cada uno.
2. El **`team` interno NO equivale a club/academia**: `team` es un contenedor de un torneo concreto
   (nombre, logo, ranking propio) y `club` es una entidad global distinta, sin relación con él.
3. No existe ninguna tabla de **inscripciones**: "inscribir" hoy = crear `player` + `team` + asignar
   `team_id` a un `stage_item_inputs.slot`.

---

## 6. Modelo conceptual BJJ (§7)

| Concepto | Definición | Hoy | Falta |
|---|---|---|---|
| **Club** | Entidad deportiva/academia | `clubs` (global) + `tournaments.club_id` | Relación con competidores y equipos |
| **Competitor** | Persona que compite | `players`, pero **con ámbito torneo** | Identidad estable entre torneos + club |
| **Team** | Grupo de varios competidores (modalidades por equipos) | `teams` + `players_x_teams` (ya soporta N jugadores) | Etiquetado/UX, semántica de resultados por equipo |
| **Entrant** | Unidad que entra al cuadro: un competidor **o** un equipo | **`stage_item_inputs` ya es el entrant** | Nada estructural: está infra-representado, no ausente |
| **Registration** | Inscripción: competidor/equipo + club en ese torneo | **No existe** | Entidad o snapshot (ver §7) |

Relaciones objetivo: `Club 1—N Competitors`, `Club 1—N Teams`, `Team N—M Competitors`,
`Entrant → Competitor | Team`, `Registration → (competitor|team) + club (snapshot)`.

Lectura clave del diseño: **el modelo actual ya tiene el entrante** (`stage_item_inputs`) y el
contenedor de equipo (`teams`). Lo que no tiene es la **persona global** ni la **afiliación a club**.
Por eso la propuesta es **ascender** entidades existentes (competidor global, club) en lugar de crear
tablas nuevas, y posponer un `Entrant` explícito a la fase 4 (probablemente innecesario).

---

## 7. Club affiliation: opciones (§8)

Requisito: un competidor debe poder estar asociado a un club, pero **puede cambiar de club en el
tiempo** (y el historial debe conservarse).

| Opción | Descripción | Pros | Contras |
|---|---|---|---|
| **A** `players.club_id` | Club actual en la fila del competidor | Trivial de leer y mostrar | Sobrescribe: se pierde con qué club compitió en cada torneo; un competidor solo puede tener un club "actual" |
| **B** `registration.club_id` | Club en la inscripción del torneo | Historial exacto por torneo | Requiere introducir la inscripción (hoy no existe); sin "club actual" para la ficha del competidor |
| **C** Ambos: `competitor.club_id` (actual) + snapshot de club en la inscripción | Club actual + foto histórica | Historial fiel y ficha simple; soporta traspasos y "compitiendo por" | Dos puntos que mantener sincronizados; la UI debe dejar claro cuál es cuál |

**Recomendación: C**, con matices de alcance:

- El "club actual" debe vivir en la entidad competidor **global** (que hoy no existe: `players` es por
  torneo). Sin ese ascenso, A y C no tienen dónde vivir de forma coherente.
- El snapshot puede materializarse **sin crear la inscripción completa** en una primera iteración:
  añadir `teams.club_id` (o un `club_id` nullable en el input) como *club con el que compite este
  entrante en este torneo*, y mostrarlo bajo el nombre en el cuadro. Es una columna, no un modelo nuevo.
- Nada de esto toca el cuadro ni el resolver estructural: el bracket seguiría usando `team_id`.

---

## 8. Team competition (§9)

Escenario conceptual: `Team A = {c1, c2, c3}` vs `Team B = {c4, c5}`.

- **Ya soportado hoy**: un entrante puede ser un equipo con N competidores (`players_x_teams`), y el
  cuadro es idéntico (el motor solo ve `team_id`). En el torneo 1 (datos de ejemplo) existen equipos
  con 2 jugadores, así que la mecánica ya está probada en el modelo.
- **Falta**: (a) presentación y labels (§9); (b) resultados por competidor dentro de un combate de
  equipo (hoy el score es del `match`); (c) clasificación agregada por equipo/club a través de
  categorías (hoy `rankings` es por stage item); (d) UX de creación de plantillas.
- **Riesgo**: el caso individual no debe degradarse. La vía segura es **no tocar** el modelo del
  cuadro y resolver (b)/(c) como capas nuevas encima.

---

## 9. UX BJJ (§10-§13)

### 9.1 Labels contextuales (§10)

Regla acordada: **no** reemplazar "Equipos" por "Competidores" globalmente.

| Contexto | Label propuesto |
|---|---|
| Torneo individual | Competidores |
| Torneo por equipos | Equipos |
| Administración genérica / ambiguo | Participantes (o "Entrants" si se quiere ser explícito) |

Superficie medida: 295 claves de traducción en 12 idiomas; 23 claves con `team*`, 27 valores en ES con
"Equipo"/"equipo". La contextualización debe hacerse por **tipo de competición del torneo** (una
preferencia por torneo), no por reemplazo textual.

### 9.2 Cancha → Tatami (§11)

- Confirmado: es **puro copy/UI**. No cambia `courts`, `court_id`, API ni DB. Los nombres de tatami que
  escribe el usuario viven en `courts.name` y no se tocan.
- Superficie: **13 claves** de traducción (`add_court_title`, `courts_title`, `create_court_button`,
  `court_name_input_placeholder`, `no_courts_*`, `active_next_round_modal_title`,
  `all_matches_scheduled_description`, `auto_assign_courts_label`, `courts_filled_badge`,
  `delete_court_button`, `go_to_courts_page`) y **3 ficheros** de UI que las consumen.
- Reemplazos: `Cancha → Tatami`, `Canchas → Tatamis`, `Añadir Cancha → Añadir Tatami`,
  `Crear Cancha → Crear Tatami`, `Eliminar Cancha → Eliminar Tatami`, `Mejor Cancha → Tatami 1`.
- **Evaluación**: cambio seguro y barato → **apto para la release de P2.8B (fase 1)**, con plan de
  traducción para los 12 idiomas (o limitarlo a `es` + `en` dejando el resto con el término actual).

### 9.3 Nombres de ronda (§12)

Hoy: `f"Round {n:02d}"` (`bracket/sql/rounds.py:60`), no localizado y sin relación con el tamaño.

| Tamaño de cuadro | Rondas (de primera a última) |
|---|---|
| 2 | Final |
| 4 | Semifinal · Final |
| 8 | Cuartos · Semifinal · Final |
| 16 | Octavos · Cuartos · Semifinal · Final |
| 32 | Dieciseisavos · Octavos · Cuartos · Semifinal · Final |

| Opción | Pros | Contras |
|---|---|---|
| (a) Renombrar en BD al construir | Simple | Rompe i18n (nombre único en 12 idiomas) y pierde el renombrado manual |
| (b) **Etiqueta calculada en la UI** por (posición, total de rondas del stage item) | Sin migración, i18n en el front, mantiene nombres editables (se pueden mostrar como sufijo) | Requiere que la UI conozca el total de rondas (ya lo tiene) |
| (c) `round_code` enum en BD (`ROUND_OF_16`…) | Robusto, estable, filtrable | Migración + backfill; fase 2 |

**Recomendación: (b) ahora** (fase 1, sin migración) y (c) cuando se toque el modelo (fase 4).

### 9.4 Bracket visual (§13)

Estado actual (evidencia en `frontend/src/components/brackets/`):

- Rondas como **columnas** de 400px (`round.tsx:98`), partidos apilados dentro de cada columna y
  ordenados por nombre de tatami (`round.tsx:26-29`); separación `Group align="top"` (`brackets.tsx:194`).
- Tarjeta de partido: badge superior `tatami | hora` (oculto si no hay cancha), dos filas
  (nombre + marcador) y ganador en verde por comparación de marcadores (`match.tsx:16-92`).
- **Sin alineación vertical entre rondas** (no hay conectores ni centrado respecto a los dos partidos
  que alimentan cada uno), y los nodos alimentados muestran el texto **hardcodeado en inglés**
  `Winner of match X - Y` (`components/utils/match.tsx:52,70`), también sin traducir.
- Los slots vacíos se muestran como "Lugar vacío" (`empty_slot`), de modo que un ghost aparece como un
  combate normal con dos huecos.

Propuesta (sin rediseño grande en esta fase):

1. **Alineación**: cada partido centrado verticalmente respecto a la media de sus dos partidos
   alimentadores, con conectores simples entre columnas.
2. **BYE**: no se pinta como combate; se indica "pasa directo" y la línea de avance sube directamente a
   la ronda siguiente.
3. **Ghost**: nodo estructural atenuado (o no renderizado, conservando el hueco para la alineación);
   nunca con badge de tatami ni marcador.
4. **Club bajo el nombre del competidor** (y logo cuando exista) → depende de §7.
5. **Branding**: futura fase (ver `docs/17` §11, prioridad registrada).

---

## 10. Roadmap de migración (§14)

| Fase | Contenido | Migración DB | Riesgo |
|---|---|---|---|
| **1 — UX/copy seguro** | Tatami (§9.2), nombres de ronda por tamaño (§9.3 opción b), labels contextuales (§9.1) | No | Bajo |
| **2 — Topología** | Tamaño de cuadro (§2.1), reparto *bye-aware* (§2.3), orden por sorteo con semilla, `is_playable` en API (§3), scheduler solo de combates reales (§4) | No (opcional: columna `is_structural`/semilla) | Medio: cambia la construcción del cuadro y varios tests |
| **3 — Club affiliation** | Competidor global + `club_id` actual + snapshot de club por inscripción (§7) | Sí | Medio-alto: toca el núcleo del modelo |
| **4 — Entrant explícito** | Solo si tras la fase 3 sigue haciendo falta separar `Entrant` de `stage_item_inputs`; incluye `round_code` (§9.3 c) y team competition avanzada (§8) | Sí | Alto |

Criterio de entrada de cada fase: la anterior cerrada y validada, con `WRITE=false`, sin tocar
`tournament_id` 1/2/6 salvo ensayo explícito.

---

## 11. No hacer todavía (§16)

Nada de lo listado se ha hecho ni se hará sin autorización explícita: migraciones de base de datos;
tabla `Entrant`; `players.club_id`; crear Tatami 2–6;
branding; habilitar `WRITE`; publicar resultados; tocar Access/DNS/Tunnel.

## 11bis. Ya hecho en F2 (§16)

El seeding bye-aware y el scheduler estructural **dejaron de ser propuesta** en F2 (fork `8ec816b`, CI
verde, imagen `8ec816b-r1`) y están **desplegados en producción** (pin del submódulo `8ec816b`, recreado
solo el servicio `bracket`; rollback documentado → `29b6146-r1`). Validados de punta a punta en un ensayo
**nuevo y separado** (`tournament_id=9`: 25 entrants, categorías 3/2/6/7/2/5, 7 direct BYEs, 0 ghosts,
resolver idempotente, 0 scores/ganadores ficticios, 10 candidatos reales en el marcador, 19 combates
schedulable planificados y 7 `STRUCTURAL_BYE` sin planning). `tournament_id=6` queda **intacto** como
*P2.8A historical rehearsal*. Detalle completo, terminología (`READY` / `PENDING_COMPETITIVE` /
`STRUCTURAL_BYE` / `DEAD`, `SCHEDULABLE = READY + PENDING_COMPETITIVE`) y evidencia en
`docs/19-bye-aware-seeding-and-scheduling.md` §3.1, §5ter y §8.

Deuda funcional **UI AUTO-SEED GAP ⚠️** — el seeding bye-aware solo corría cuando los inscritos existían
al construir el cuadro (importador / create-with-inputs); la UI estándar crea el `stage_item` con inputs
vacíos y asigna equipos después, así que no disparaba `distribute_entrants_into_slots`. Opciones y
recomendación (C: acción UI explícita `Generate bracket`) en `docs/19` §6bis →
**RESOLVED ✅ en F2C** (§15): endpoint explícito con *safety gates* e idempotencia, acción «Generar cuadro»
en la UI estándar, ensayo real `tournament_id=10` y cierre documental en
`docs/20-generate-bracket-ui.md`.

## 12. Evidencia y artefactos

- Auditoría de código: `bracket/logic/scheduling/elimination.py`, `builder.py`,
  `bracket/logic/planning/matches.py`, `bracket/sql/stage_items.py`, `bracket/sql/rounds.py`,
  `bracket/models/db/*`, `frontend/src/components/brackets/*`, `frontend/src/components/utils/match.tsx`,
  `bridge-api/app/bracket_client.py`.
- Evidencia de datos (solo lectura, sin PII): topología de primera ronda por categoría y reparto de
  slots del ensayo; esquema de las tablas en `information_schema`; estado del scheduler (`con_court=0`).
- Observación de mantenimiento (no funcional): `bracket/logic/scheduling/builder.py:26` importa
  `tests.integration_tests.mocks.MOCK_NOW` desde código de producción; conviene eliminarlo en fase 1/2.

## 13. F1 — UX / copy seguro (implementado)

Estado: **implementado, desplegado y validado** (2026-10-03). Sin migración ni cambios de modelo,
esquema, API, seeding, scheduler o lógica de torneo. Fork `danyseve/bracket` @ `29b6146`; imagen
`danyseve1/bracket-bjj:29b6146-r1`; se recreó únicamente el servicio `bracket`.

### 13.1 Cancha → Tatami (solo copy en español)

Reescritos los **13 valores** de `frontend/public/locales/es/common.json` que mencionaban "cancha":
`active_next_round_modal_title`, `add_court_title`, `all_matches_scheduled_description`,
`auto_assign_courts_label`, `court_name_input_placeholder`, `courts_filled_badge`, `courts_title`,
`create_court_button`, `delete_court_button`, `go_to_courts_page`, `no_courts_description`,
`no_courts_description_swiss`, `no_courts_title`. No se han tocado claves técnicas (`courts`,
`court_id`), endpoints, modelos, SQL ni contrato de API; el resto de idiomas conserva su redacción.

### 13.2 Nombres de ronda (solo presentación)

Módulo puro nuevo `frontend/src/components/utils/round.ts` (`getRoundLabelKey` y
`getRoundDisplayName`), consumido en `brackets/round.tsx` y `modals/round_modal.tsx`. `Round.name` en
base de datos y `sql/rounds.py` quedan intactos (el organizador sigue pudiendo renombrar la ronda).
Mapeo por número de rondas del cuadro: 1 Final · 2 Semifinal/Final · 3 Cuartos/Semifinal/Final ·
4 Octavos/… · 5 Dieciseisavos/…. Claves `round_label_*` añadidas a `es` y `en` (el resto de idiomas
cae al inglés por `fallbackLng: "en"`). Fallback al nombre almacenado cuando el stage item no es
`SINGLE_ELIMINATION`, no se localiza la ronda, el cuadro excede 5 rondas o la clave no está traducida.

### 13.3 Labels contextuales individual/equipos — APLAZADO (sin señal fiable)

No existe hoy ninguna señal persistente de modalidad: `tournaments` no tiene campo de tipo/modalidad,
el formulario de alta/edición de torneo no lo pregunta, `players_can_be_in_multiple_teams` es una regla
de plantillas y el `type` del stage item describe el formato de competición
(`SINGLE_ELIMINATION`/`ROUND_ROBIN`/`SWISS`), no individual vs equipos. "Todos los equipos con un
jugador" depende de datos editables durante el torneo y no se acepta como criterio. Se resolverá junto al modelo de dominio (F3/F4); en esta fase no
se introduce ningún campo de modalidad (`tournament_type`, `competition_mode`) ni heurística alguna.

### 13.4 Tests y validación

`frontend/tests/` con el runner `node:test` (sin dependencias nuevas): etiquetas de ronda y sus
fallbacks, y presencia/valor de las claves de copy en `es`/`en`. Ejecutado en el mismo node/pnpm de la
receta: `pnpm test:unit` (17/17), `tsc` (0 errores), prettier (gate del CI: 0 diferencias),
`vite build` (ok) y `pnpm install --frozen-lockfile` (ok). ESLint no es ejecutable en el fork
(`.eslintrc.js` legacy frente a ESLint 9, sin script `lint`) y no forma parte del CI.

### 13.5 CI del fork (completo en verde)

Los dos workflows rojos (frontend y docs) fallaban por la versión de pnpm que elegía Corepack: ambos
hacían `corepack enable` sin fijar versión y el proyecto no declara `packageManager`, así que Corepack
resolvía su versión por defecto — **pnpm 12.8.1** en node 22.23.3, según el propio log del CI
("Corepack is about to download … pnpm-12.8.1.tgz") y la reproducción local. Desde pnpm 10 los scripts
de build de las dependencias están bloqueados y `pnpm install` aborta con `ERR_PNPM_IGNORED_BUILDS`
(frontend: `esbuild@0.27.7`; docs: `sharp@0.34.5`, `unrs-resolver@1.11.1`).

Arreglo (solo workflow; sin tocar dependencias ni lockfiles): fijar en ambos workflows el pnpm de la
receta de build antes de instalar (`corepack prepare pnpm@9.15.9 --activate`). No se desactivan scripts
de build, no se ignora el error, no se usa `--ignore-scripts` y no se relaja ninguna comprobación.
Lockfiles intactos al instalar en local (`frontend` `001f9b8e…`, `docs` `8594f1ad…`), igual que los
asserts de la receta. Resultado: `backend`, `docker build`, `docs test` y `frontend` **GREEN** en el
mismo SHA (`8a9a482`), con `Done in 10.7s using pnpm v9.15.9` en los logs.

### 13.6 Comprobación de no-regresión de datos

Tras el despliegue, `matches`, `rounds`, `stage_items`, `stage_item_inputs`, `courts`, `players`,
`teams` y `clubs` se compararon fila a fila contra el snapshot `backups/bracket_20261003_054342.sql`
(previo al backfill de P2.8A): todas idénticas salvo las **4 filas del backfill autorizado de P2.8A**
(`M80`, `M94`, `M102`, `M103`), que ya estaban en el estado esperado. Sin marcador, sin tatami asignado
y sin hora en el ensayo; `active_match_id` nulo; `WRITE` deshabilitado.

Nota de método: los "md5 invariantes" anotados en fases anteriores no son reproducibles hoy (se
generaron con expresiones ad-hoc distintas y sobre estados anteriores al backfill). La verificación
fiable es la comparación fila a fila contra el snapshot, que es la que se ha usado.

### 13.7 Publicación de la imagen (`29b6146-r1`)

Publicada sin reconstruir y sin tocar `latest`:

- image ID local = `sha256:24b9f0da355ec122bebe1fbb4d2e82c37b3f70b58708c8fceac019bced8763f1`
- manifest digest remoto = `sha256:0b7672fe8b321852682af5168b403d2a7d87e017cb43a8c7c30388ee7606f950` (3663 B)
- config digest remoto == image ID local; blob de config (14146 B) re-hasheado == image ID
- `rootfs.diff_ids`: 16 locales == 16 remotos (idénticos)
- labels: `revision=29b6146c4a3a1fd577e1fff48eec2c4a5dde5168`, `recipe_revision=r1`,
  `pnpm_version=9.15.9`, `pnpm_lock_sha256=001f9b8e…`
- `latest` con el mismo digest antes y después del push; el contenedor productivo no se ha recreado
  (sigue ejecutando la misma imagen).

## 14. F2 — cierre (ENGINE + REHEARSAL VALIDATED ✅)

Estado: **implementado, desplegado y validado** (2026-10-03). Detalle completo, terminología y
evidencia en `docs/19-bye-aware-seeding-and-scheduling.md`.

- Motor: fork `danyseve/bracket` `master` @ `8ec816b` (seeding bye-aware + scheduler estructural),
  CI del fork **4/4 jobs en verde**, 170 tests / `mypy` 171 ficheros / `pylint` 10.00.
- Entrega: pin del submódulo `8ec816b` en el repo principal e imagen
  `danyseve1/bracket-bjj:8ec816b-r1` en producción (rollback documentado → `29b6146-r1`); recreado
  **solo** el servicio `bracket` (postgres, bridge, scoreboard, nginx y wireguard sin reinicio).
- Validación real (ensayo nuevo `tournament_id=9`, 25 entrants, categorías `3/2/6/7/2/5`, cuadros
  `4/2/8/8/2/8`): **7 direct BYEs, 0 ghosts, 0 scores y 0 ganadores ficticios**; resolver estructural
  P2.8A materializado e idempotente; marcador: 10 candidatos reales, `assign → ready (0-0, reloj sin
  iniciar) → cancel → state null`, `POST result` → `503 result_write_disabled`; scheduler:
  **19 planificados (10 `READY` + 9 `PENDING_COMPETITIVE`) y 7 `STRUCTURAL_BYE` sin planning**,
  posiciones `0…18` contiguas, intervalos de 6 min, una sola pista (`Tatami 1`).
- `tournament_id=6` **intacto** como *P2.8A historical rehearsal* (3 byes directos + 2 ghosts, 0 scores,
  0 planning); torneos 1 y 2 intactos; `WRITE=false`; Tatami 1 `state=null`.
- Semántica del scheduler aceptada por el operador: `READY` → planificado · `PENDING_COMPETITIVE` →
  planificado · `STRUCTURAL_BYE` → **no** planificado · `DEAD`/ghost → **no** planificado.
- Deuda **UI AUTO-SEED GAP**: **RESOLVED ✅** en F2C (§11bis y §15, `docs/20-generate-bracket-ui.md`).
  F3 no iniciada.

## 15. F2C — acción UI «Generar cuadro» (UI AUTO-SEED GAP RESOLVED ✅)

Fase **F2C** (2026-10-03): fork `danyseve/bracket` @ **`886ff13`** (desde `8ec816b`), imagen
`danyseve1/bracket-bjj:886ff13-r1` (rollback `cbab68a-r1`), pin del submódulo del repo principal
`8ec816b` → `886ff13`, recreado **solo** el servicio `bracket`. Implementa la opción **C** de §11bis: una
acción **explícita** «Generar cuadro» (`POST .../stage_items/{si}/generate_bracket`) con *safety gates*,
idempotente y **sin** auto-reseed, que aplica el seeding bye-aware de F2 al cuadro ya creado desde la UI
estándar (el caso que F2 no cubría).

- Reutiliza el motor de F2 (`distribute_entrants_into_slots`) y el resolver P2.8A; invariante `N → B`
  sin sobredimensionar; escritura en una transacción con rollback total.
- Gates 409 `generate_bracket_blocked:<code>` (`scores`, `winner`, `planning`, `tentative_inputs`,
  `not_single_elimination`, `too_few_entrants`, `bracket_too_large`, `inconsistent_slots`); archivado →
  400. Nada se borra ni se resetea; ninguna heurística oculta dispara la generación.
- Ensayo real `tournament_id=10` «Torneo De pruebas REHEARSAL F2C» (`stage_item_id=49`, 8 plazas, 6
  equipos en slots 1,2,3,5,6,7; vacíos 4 y 8): **2 cruces + 2 pases directos + 0 combates vacíos**, 0
  ghosts, resolver P2.8A materializado, 0 scores / 0 planning / 0 court / 0 drafts y `changed=false` en
  la segunda ejecución. Torneos 1, 2, 6 y 9 **intactos**; `WRITE=false`; Tatami 1 `state=null`.
- Incidencia i18n detectada y cerrada durante la validación visual (§14): tipo de cambio en
  `frontend/i18n_options.ts` (locales versionados, commit `886ff13`) y causa raíz documentada como
  frescura/caché del SPA en el navegador.
- CI del fork `886ff13`: **4/4 GREEN**. Documento de fase: `docs/20-generate-bracket-ui.md`; resumen en
  `docs/19` §6bis y §10. F3 sigue **no iniciada**.

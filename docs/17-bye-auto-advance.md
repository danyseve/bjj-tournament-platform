# 17 - Avance estructural de BYEs en el cuadro (P2.8A)

Estado: **P2.8A - STRUCTURAL BYE ADVANCEMENT VALIDATED ✅** (2026-10-03).

Objetivo: resolver **en el motor de Bracket** el avance estructural cuando un match no puede recibir un
segundo participante, de forma determinista, **sin puntuación ficticia, sin ganador artificial, sin
intervención humana y de forma idempotente**.

Resultado: el hueco documentado en `docs/16` §11 ("los BYEs no avanzan el cuadro") queda **cerrado en el
motor de Bracket** y validado sobre el `tournament_id=6` del ensayo, con la escritura de resultados hacia
Bracket todavía **deshabilitada** (`BRACKET_RESULT_WRITE_ENABLED=false`), el marcador al final en
`state=null` y los torneos `1` y `2` intactos.

Fases relacionadas: `docs/16-tournament-operation-rehearsal.md` (§11), `docs/15-real-tournament-rehearsal.md`,
`docs/10-plan-release-tatami1.md`, `docs/07-plan-imagen-reproducible.md`.

Alcance deliberadamente estrecho:

- **SÍ**: avance estructural en el motor de Bracket (una pasada completa tras construir
  `SINGLE_ELIMINATION`).
- **NO** (fases siguientes): cambio de seeding, redistribución de slots vacíos, exclusión de matches
  estructurales del scheduler, cambios en Bridge/Scoreboard, cambios de UX.

---

## 1. El hueco (P2.7B §11)

La topología del ensayo tiene **7 slots estructuralmente vacíos**, que no son 7 BYEs:

| Patrón | Matches | Slots vacíos |
|---|---|---|
| `T/∅` (un competidor real + slot vacío) | `M79`, `M92`, `M99` | 3 |
| `∅/∅` (rama ghost, sin ningún competidor) | `M85`, `M100` | 4 |
| **Total** | **5 matches** | **7 slots** |

Sin resolver esto, el cuadro no avanza: los slots alimentados por esos matches se quedaban en
`pending` indefinidamente, y los matches `∅/∅` eran pseudo-combates que nunca podían disputarse.

---

## 2. Regla estructural implementada

| Slot 1 | Slot 2 | Resultado |
|---|---|---|
| determinado (`T`) | vacío/dead (`∅`) | el entrante determinado **avanza** (BYE directo) |
| vacío/dead (`∅`) | vacío/dead (`∅`) | **rama muerta**: no produce entrante |
| determinado | dead | **walkover estructural**: avanza el determinado |
| pendiente | dead | **espera** (no se adelanta nada) |
| determinado | pendiente | **espera** (no hay auto-avance) |
| real | real | combate normal (sin cambios) |

Sin score ficticio, sin `winner` artificial, sin Tatami y sin intervención humana. El avance solo se
escribe **si es determinable**; los casos `pendiente/*` se resuelven cuando el combate real del que
dependen tenga resultado (scheduler, fase P2.8B).

---

## 3. Implementación

- `bracket/logic/ranking/elimination.py`: helpers puros `get_dead_slots()`, `get_advancing_input()` y
  `get_inputs_to_update_in_subsequent_elimination_rounds()` (+96/-9).
- `bracket/logic/scheduling/builder.py`: la pasada completa se dispara tras construir el cuadro
  (+9), y devuelve **solo los matches modificados** (corrige un bug preexistente: la pasada devolvía
  todos los matches y el wrapper reescribía snapshots de ids).
- `bracket/tests/unit_tests/elimination_structural_test.py`: **nuevo**, 14 tests (+466) que cubren la
  matriz completa, la idempotencia, la no reescritura de matches no tocados y que los matches
  estructurales no son competitivos.
- **Sin migración de base de datos** y **sin tocar** `Match.get_winner()`.

Publicado en el fork `danyseve/bracket` (rama `master`), desde `041fc6c` hasta `9bc58b3`:

```
9bc58b3 chore(lint): fix remaining long line in tournament scoping test
ebb6d05 chore(lint): clear preexisting pylint findings
929946b chore(lint): align preexisting files with ruff
4e7c3be test(admin): fix static typing in admin user tests
eed014b fix(bracket): resolve structural bye advancement     <-- cambio funcional
8f49771 test(auth): align user expectations with active field
```

Los commits `chore(lint)` / `test(admin)` / `test(auth)` no son semánticos: desbloquean deuda de CI
**preexistente** (`041fc6c`, `47bc129`) que el fork nunca había ejecutado (ruff format, ruff, pylint,
mypy, pyrefly, vulture). Diff gate aplicado: `SEMANTIC CHANGE = NONE` verificado por AST.

---

## 4. Verificación automática (CI)

Workflow `backend` (`.github/workflows/backend.yml`) lanzado con `workflow_dispatch` sobre el head
exacto `9bc58b3`:

| Paso | Resultado |
|---|---|
| Run tests | ✅ |
| Upload coverage (Codecov) | ✅ |
| Run mypy | ✅ |
| Run pyrefly | ✅ |
| Run pylint | ✅ |
| Run ruff format | ✅ |
| Run ruff | ✅ |
| Run vulture | ✅ |

Run `37100285606`, conclusion `success`. Antes de este ciclo la CI del fork estaba **roja** por deuda
preexistente nunca ejecutada (mypy en tests de admin, pylint W0621/C0301); se corrigió en commits
separados y estrictamente no semánticos.

---

## 5. Imagen

Construida con la receta reproducible del repo (`docker/bracket-bjj/Dockerfile`) y los pines de lockfile
vigentes:

```
docker build -f docker/bracket-bjj/Dockerfile \
  --build-arg BRACKET_UPSTREAM_COMMIT=9bc58b36cdefe54e82f5cbc031337ca30a4f9f4e \
  --build-arg RECIPE_REVISION=r1 \
  -t danyseve1/bracket-bjj:9bc58b3-r1 .
```

| Comprobación | Valor |
|---|---|
| Tag | `danyseve1/bracket-bjj:9bc58b3-r1` (nunca `latest`) |
| Image ID | `sha256:344d907dacba33ede99c74437587c6662364c47a675b5dbbd278872ed206544f` |
| Labels | `revision=9bc58b36cdefe54e82f5cbc031337ca30a4f9f4e`, `recipe_revision=r1` |
| Arquitectura / usuario | `linux/arm64`, `bracket` (no root), healthcheck presente |
| Guardas de la receta | bundle sin `http://localhost:8400/api`, `uv.lock` sin cambios, 0 ficheros world-writable |
| Código dentro | `sha256` de `elimination.py` idéntico al repo; helpers presentes |
| Migraciones | 22 ficheros, head `8f2b1c7d4a90` = head de la base de datos (**ninguna nueva**) |
| Publicación | **no** subida al registro: build local (el despliegue usa la imagen local del host) |

Validación previa a sustituir producción, en contenedor desechable **contra la DB de test aislada
`bracket_test`** (nunca la de producción), sin tocar puertos públicos: `healthy` en 6 s, `/api/ping`
`200 "ping"`, frontend `200`, `/api/tournaments` `401` (auth), 0 errores en logs. Con la DB de
producción intacta: `bracket_dev=4` conexiones (sin ninguna de la validación), `bracket_test=10`.

---

## 6. Despliegue

- `docker-compose.yml`: imagen de `bracket` de `danyseve1/bracket-bjj:041fc6c-r1` a
  `danyseve1/bracket-bjj:9bc58b3-r1`.
- Recreado **únicamente** el servicio `bracket` (`docker compose up -d --no-deps bracket`);
  `bracket-postgres`, `bjj-nginx`, `bjj-bridge-api`, `scoreboard-tatami-1` y `wireguard` mantienen los
  mismos IDs y `StartedAt`.
- `bracket` = `healthy`, `restarts=0`. Ruta pública: `bracket.opsforge.cc` → `/api/ping` `200`.
- **Rollback**: volver la línea del compose a `041fc6c-r1` y recrear el servicio; la imagen anterior
  sigue en el host (`58ae3cfc4944`).

---

## 7. Backfill controlado de `tournament_id=6`

- Snapshot previo: `backups/bracket_20261003_054342.sql` (52 KB, 1813 líneas).
- Ejecutado con la **imagen desplegada**, en contenedor dedicado, contra `bracket_dev` con assert
  explícito de DB objetivo, y **una sola pasada** de
  `update_inputs_in_complete_elimination_stage_item` (mismo camino que el builder). Sin scheduler, sin
  scores, sin ganadores.

| Match | Cambio aplicado | Origen estructural |
|---|---|---|
| `M80` | `slot2 ← input 98` (equipo 63) | BYE directo de `M79` (`98 / ∅`) |
| `M94` | `slot2 ← input 116` (equipo 78) | BYE directo de `M92` (`116 / ∅`) |
| `M102` | `slot1 ← input 124` (equipo 85) | BYE directo de `M99` (`124 / ∅`) |
| `M103` | `slot2 ← input 124` (equipo 85) | walkover propagado vía `M102` (rama muerta de `M100`) |

**4 avances exactos**, idénticos a la proyección read-only previa a la escritura. Segunda pasada de
comprobación: **0 cambios** (idempotencia). Ningún score, ningún `court_id`, ningún ganador escrito.

---

## 8. Validación estructural

| Criterio | Resultado |
|---|---|
| BYEs estructurales directos (`T/∅`) | **3** correctos (`M79`, `M92`, `M99`) |
| Ramas ghost (`∅/∅`) modeladas como muertas | **2** (`M85`, `M100`) |
| Walkovers posteriores propagados | **2** niveles en la misma pasada (`M99` → `M102` → `M103`) |
| Pendientes que **esperan** (no se adelantan) | `M86`, `M87`, `M88`, `M93`, `M95`, `M101` (+ `M103` slot1) |
| Pseudo-combates enviados a Tatami | **0** |
| Scores / ganadores ficticios | **0** (`con_score=0`, `con_court=0`) |
| Idempotencia | ✅ 0 cambios en la segunda pasada |
| Duplicados | **0** |

Nota de terminología: el criterio **no** es "7 BYEs resueltos" sino "3 BYEs directos + 2 ramas ghost",
que son los 7 slots vacíos.

---

## 9. Tatami 1 (Bridge + marcador)

- `GET /tatamis/1/candidates?tournament_id=6` → **10 candidatos, todos combates real/real**
  (`81, 82, 83, 84, 89, 90, 91, 96, 97, 98`). Quedan fuera los 3 byes directos, los 2 ghosts y todos los
  matches pendientes de feed: **0 pseudo-combates**.
- `assign-match` de `M78` → `status=ready`, `revision=1`, `duration=300`, con los dos competidores
  correctos y su categoría.
- `cancel_assignment` por el mismo camino que la UI de control (socket.io, con credencial de control)
  → `ok:true`, `revision=2` y `state=null` en el marcador y en su fichero de estado.
- `POST /tatamis/1/result` con `WRITE=false` → **503 `result_write_disabled`** sin leer el marcador ni
  escribir en Bracket.

---

## 10. Invariantes finales

| Invariante | Valor |
|---|---|
| `BRACKET_RESULT_WRITE_ENABLED` | `false` |
| Tatami 1 | `state=null` (y `command_history=[]`) |
| `tournament_id=6` | 26 matches, 32 inputs, 13 rounds; md5 `abe473da…` (sin cambios tras §6) |
| `tournament_id 1` y `2` | md5 `29dc5ec3…` idéntico al baseline |
| Servicios | Bracket, Bridge, Postgres, scoreboard y WireGuard `healthy`, `restarts=0` |
| Cloudflare Access (read-only) | `OK=4`, `UNSAFE=0`, `WARNING=0` (`bjjvetusta`/`bracket`/`docs` `open-otp` 24 h; `tatami1` `restricted` 8 h; `tatami2..6` `NOT_CREATED`) |
| Git | sin amend, sin force, `main` intacto |

---

## 11. Deuda pendiente / siguiente fase

- **P2.8B** (candidatos, fuera de alcance aquí): cambio de seeding, modelado explícito de ghost matches,
  exclusión de matches estructurales del scheduler y propagación automática de walkovers cuando el
  combate real del que dependen se resuelva (`M86`..`M88`, `M93`, `M95`, `M101`).
- **TATAMI BRANDING - P2.8 PRIORITY**: branding de tatamis pendiente; el póster Asturkon **no** debe
  recortarse ni usarse como logo temporal.

---

## 12. Rollback

1. `docker-compose.yml` → `danyseve1/bracket-bjj:041fc6c-r1` + `docker compose up -d --no-deps bracket`.
2. Restaurar el snapshot de Postgres si el backfill debiera revertirse
   (`backups/bracket_<timestamp>.sql`); el backfill **solo** añadió 4 `stage_item_input*_id`.
3. El submodule `services/bracket` vuelve a su gitlink anterior en el repo principal.

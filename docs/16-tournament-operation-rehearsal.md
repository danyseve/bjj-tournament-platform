# 16 - Operación real controlada del torneo (P2.7B)

Estado: **P2.7B - CLOSED WITH BYE GAP ⚠️** (2026-10-03).

Objetivo: convertir el ensayo de `docs/15-real-tournament-rehearsal.md` en una demostración operativa
realista del flujo de torneo completo (**categoría activa → planificación → Tatami 1 → combate
asignado → marcador en vivo → recuperación**) sobre el `tournament_id=6`, **sin rediseñar la
aplicación** y **sin habilitar** la escritura de resultados hacia Bracket de principio a fin.

Resultado: el flujo queda validado de punta a punta. Queda **un hueco conocido y no resuelto**: los
BYEs no avanzan el cuadro (ver §11), documentado como requisito de P2.8.

Fases relacionadas: `docs/15-real-tournament-rehearsal.md`, `docs/10-plan-release-tatami1.md`,
`docs/06-modelo-multitatami.md`, `docs/03-operacion.md`, `docs/02-roadmap-fases.md`.

Nota de método: los pasos que la aplicación protege con sesión de usuario (activación de etapa y
planificación) **solo se ejecutan por la UI autenticada**; este documento registra qué se hizo a mano,
qué se verificó por lectura y qué se revirtió. No hay automatización de escritura: es deliberado.

---

## 1. Precheck (P2.7B §1 = PASS)

Estado de partida del ensayo, verificado contra Postgres, los contenedores y el marcador:

| Comprobación | Valor |
|---|---|
| Torneo | `6` - "Torneo Interno CREE Masculino — REHEARSAL" (club anonimizado) |
| Stages | 6 (`19..24` = -62/-66/-71/-77/-84/-92) |
| Stage items | 6 (uno por etapa) |
| Slots / competidores | 32 / 25 |
| BYEs | 7 |
| Matches / rounds | 26 / 13 |
| Court | 1 solo: `id 8` = "Tatami 1" (resuelto por `name` + `tournament_id`, **nunca asumido**) |
| Tatami | `state = null` |
| Escritura | `BRACKET_RESULT_WRITE_ENABLED=false` |
| Servicios | Bracket, Bridge, Postgres, scoreboard y WireGuard `healthy`, `restarts=0` |
| Access (solo lectura) | `OK=4  UNSAFE=0  WARNING=0` |

Mapping operativo: court Bracket "Tatami 1" (`id 8`) → Bridge `tatami_id=1` → scoreboard `tatami1`.

---

## 2. Limpieza de variables de escritura vacías (P2.7B §2)

Situación: el Compose declaraba en el entorno del Bridge las credenciales de escritura contra Bracket
con valor por defecto vacío.

- `BRACKET_WRITE_USERNAME` / `BRACKET_WRITE_PASSWORD` eran **opcionales a propósito**; el código las
  lee con default vacío (`bridge-api/app/config.py`, pydantic `Settings`) y **solo** en la ruta de
  escritura. Con `WRITE=true` su ausencia falla **en cerrado** (`503 bracket_write_not_configured`)
  sin escribir nada; con `WRITE=false` no se necesitan.
- Cambio aplicado (mínimo, con backup previo del fichero): se retiran del entorno del Bridge y queda
  un comentario explicando que su ausencia es deliberada.
- Verificado: `docker compose config` válido; **solo** el Bridge recreado (ID nuevo, `restarts=0`,
  healthy, entorno sin `BRACKET_WRITE_*`); el resto de contenedores con ID y `StartedAt` idénticos.

No se añadió ninguna credencial y la escritura siguió bloqueada.

---

## 3. Activación de categoría (paso humano soportado)

Mecanismo real, comprobado en el código y en la API:

- `POST /api/tournaments/{tournament_id}/stages/activate` con `{"direction": "next"|"previous"}`.
  **Nunca** acepta `stage_id`: es un recorrido **lineal** (activa la siguiente etapa inactiva) y hace
  que **solo una** quede activa (`SET is_active = (id = :new_active_stage_id)`).
- Exige usuario autenticado (`OAuth2PasswordBearer`): probado sin sesión → **HTTP 401**.
- Efecto en la categoría activada: `update_matches_in_activated_stage` solo promueve inputs de tipo
  *Tentative*; en `-62 kg` (sin inputs tentativos) es **no-op** sobre los combates.
- No existe endpoint de desactivación: devolver el torneo a "todo `is_active=false`" exigiría un
  `UPDATE` directo, que **no se hizo** (fuera de la vía soportada).

Ejecutado por el operador en la UI (una sola vez, "Etapa siguiente"). Verificado después por lectura:
`19 (-62 kg) = true`, `20..24 = false`.

---

## 4. Planificación (paso humano soportado) y comportamiento del scheduler

- Ruta real: `POST /api/tournaments/{tournament_id}/schedule_matches` ("Schedule Matches", sin cuerpo).
  Exige `OAuth2PasswordBearer` → **HTTP 401 sin sesión**; el `cli.py` del contenedor **no** tiene
  comando de scheduling. Por tanto se ejecutó **por la UI autenticada** (vista *Scheduling*).
- Comportamiento del scheduler (verificado en código y en los datos): es **global por torneo**.
  Recorre **todos** los stages del torneo y asigna `courts[min(i, len(courts)-1)]`. Con un único
  court, **todos** los combates de todas las categorías se secuencian en **Tatami 1**.
- Evidencia medida tras la acción (26 combinaciones posibles de 6 categorías):
  - 26/26 matches con `court_id = 8` (un único court distinto);
  - `position_in_schedule` = **0..25**, 26 posiciones distintas;
  - `start_time` presente en los 26: `2026-10-17 09:00 → 11:30 UTC`;
  - `scores = 0` en los 26 y **0 ganadores** derivados;
  - torneos 1 y 2 sin cambios (0 planificados).
- **Limitación documentada**: por la vía soportada actual **no existe** planificación acotada por
  categoría. Un `PUT` por combate permite fijar `court_id`, pero deja `start_time` y
  `position_in_schedule` nulos, y la vista de Planning solo muestra combates con `start_time != null`
  → un combate sin hora **no aparece** en Planning. El drag&drop solo reordena combates ya
  planificados (no hay "desplanificar" en la UI).
- Validación de Planning: la vista/API correspondiente está tras autenticación; lo comprobado por
  lectura es el dato que consume (los 26 con `start_time`), no una captura de pantalla.

---

## 5. Rollback de planificación (ejecutado)

Rollback **limitado al torneo 6** (lista explícita de ids `78..103`) con guardarraíl que aborta si el
recuento de matches del torneo no es exactamente 26:

```sql
update matches
   set court_id = null, position_in_schedule = null, start_time = null
 where id in (78,79,...,103);
```

Resultado medido: `UPDATE 26` → `26 | 0 | 0 | 0` (total | con court | con posición | con hora);
0 combates planificados en todo el torneo 6; **scores intactos** (0 con marcador); la activación de
`-62 kg` se conserva (`true`, resto `false`).

---

## 6. Candidatos y asignación de combate al Tatami

- `GET .../tatamis/1/candidates`: cantera por categoría (11 candidatos en el ensayo) que **excluye
  automáticamente** los combates con un solo entrante (los BYEs nunca llegan al Tatami).
- `POST .../tatamis/1/assign-match` con `{tournament_id, match_id, tatami_id}` → **HTTP 201**,
  `scoreboard_sent=true`, estado del marcador `ready`, `revision 1`, 300 s, 0-0.
- La asignación se persiste de inmediato en el marcador.

---

## 7. Operación del marcador en vivo

- Control: la cookie del cliente de control se obtiene de la página `/control`; la ruta interna
  (`/internal/*`) exige token interno (**401** sin él) y un cliente sin cookie **no** puede emitir
  comandos (`unauthorized`).
- Comandos soportados y ejercitados: `set_running` (start/pause/resume), `score_delta`
  (points/advantages/penalties, incluido delta negativo para corregir), `reset`, `cancel_assignment`.
  `finish` **no** se usó: es la ruta de publicación de resultado.
- Difusión: cada cambio aceptado se emite a **todos** los clientes (`tatami:state`). Verificado con
  dos clientes simultáneos: pantalla (viewer) y control recibieron **los mismos 20 estados** con
  revisiones coherentes y monótonas.
- Sin publicación: 0 resultados escritos en Bracket en toda la sesión.

---

## 8. Persistencia del marcador

`state.json` es un **bind mount** (`/state`). Reiniciando **solo** el contenedor del marcador
(mismo ID de contenedor, `restarts=0`, healthy), el estado se conservó **bit a bit**:
`session_id`, `revision`, `status`, `remaining_seconds` y marcador idénticos. Bridge, Bracket,
Postgres y WireGuard **no** se reiniciaron. El Bridge siguió viendo el combate asignado.

---

## 9. Recuperación (devolver el marcador a estado seguro)

- `cancel_assignment` solo procede con el combate **pristine** (reloj completo, todo a cero, sin
  ganador). Tras haber manipulado marcador, es necesario un `reset` previo: así se hizo.
- `cancel_assignment` → `{ok:true, revision+1}` → `state = null`; los candidatos vuelven a incluir el
  combate y `active_match_id` queda vacío.
- Bracket **sin cambios**: el combate vuelve a `0-0`, sin court, sin hora y sin ganador.

---

## 10. WRITE gate (escritura de resultados bloqueada)

- `BRACKET_RESULT_WRITE_ENABLED=false` en el runtime del Bridge.
- `POST .../tatamis/1/result` (cuerpo válido) → **HTTP 503 `result_write_disabled`**.
- 0 publicaciones a Bracket: en la ventana analizada **no** hay ningún `POST /api/token` (el Bridge
  nunca pide token) y las escrituras a la API de Bracket registradas corresponden al **navegador del
  operador**, no al Bridge.

---

## 11. BYE GAP ⚠️ (requisito de P2.8, no implementado)

- Un combate con **un solo entrante** no tiene marca ni acción soportada: en el backend de Bracket no
  existe walkover/bye/forfeit/abandono (0 apariciones en el código).
- El avance del cuadro se resuelve con `elimination.get_winner()`, que a 0-0 devuelve `None`: sin
  resultado **nada avanza**. Tampoco hay auto-avance por input vacío en ningún punto del código.
- Comportamiento deseado (P2.8), sin implementar:
  **un único entrante en un match → auto-advance al siguiente match → sin enviar combate al Tatami →
  sin score ficticio → sin ganador manual inventado.**
- Hasta que se resuelva, un torneo con BYEs no puede considerarse "completable" de forma autónoma.
  Esto es lo que separa a P2.7B de un cierre limpio.

---

## 12. Deuda UX (documentada, sin cambios)

- "Cancha" → **Tatami**; "Equipos" → **Competidores / Entrantes**; "Round 01/02/03" → **cuartos /
  semifinal / final** según corresponda.
- Es deuda de **presentación**: el modelo interno (`courts` / `teams` / `rounds`) se mantiene intacto
  para no romper Bracket ni la API.

---

## 13. Branding del marcador - pendiente

`TATAMI BRANDING — P2.8 PRIORITY`

- El marcador sirve todavía un activo de **branding ajeno**:
  `/app/public/images/TEAM360_logos-09-256x256.png`, renderizado en la cabecera de
  `views/index.pug` y `views/control2.pug`, más el `name`/`short_name` del `manifest.json`.
- Sustitución viable **sin rebuild** (bind mount de fichero, patrón ya usado en `/state`), y la
  proporción no se rompe porque el CSS fija solo la altura (`height: 120px`, ancho automático).
- Requisito: **asset limpio del escudo** (PNG con transparencia o SVG, preferiblemente 256-512 px o
  vector). Un póster promocional localizado en el host se conserva **solo como referencia** y **no**
  se usa como logo del marcador.

---

## 14. Estado final del ensayo (P2.7B)

- `-62 kg` única etapa activa; resto inactivas.
- Baseline restaurado: 6 stages · 6 stage_items · **26 matches** · 13 rounds · 32 inputs · 7 BYEs.
- **0** combates planificados (sin court, sin posición, sin hora), **0** scores, **0** ganadores.
- 1 solo court: "Tatami 1". Marcador con `state = null`.
- `BRACKET_RESULT_WRITE_ENABLED=false`; **0** resultados publicados.
- Torneos 1 y 2 intactos; Access intacto; contenedores healthy.

---

## 15. Repetición rápida

Verificación del baseline y del estado de planificación (solo lectura, dentro del contenedor de
Postgres del stack):

```sql
-- invariantes del ensayo
select (select count(*) from stages where tournament_id=6) as stages;
-- planificación: 0 filas tras el rollback
select count(*) from matches m
  join rounds r on m.round_id=r.id
  join stage_items si on r.stage_item_id=si.id
  join stages s on si.stage_id=s.id
 where s.tournament_id=6
   and (m.court_id is not null or m.position_in_schedule is not null or m.start_time is not null);
```

Pasos que exigen UI autenticada (no automatizables hoy): activar etapa, planificar (Schedule
matches). Pasos automatizables y ya probados: candidatos, asignar combate, operar el marcador,
reset, cancelar asignación y reiniciar el marcador comprobando persistencia.

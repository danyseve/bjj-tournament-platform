# 15 - Ensayo de torneo con datos reales (P2.7A)

Estado: **P2.7A - TECHNICALLY CLOSED ✅ / HUMAN UI VALIDATION PENDING** (2026-10-02).

Objetivo: recorrer el flujo completo de un torneo real (import -> cuadros -> Tatami -> rollback)
con la **forma** de un torneo de produccion, usando un dataset privado que **nunca** entra en Git,
demostrando idempotencia, persistencia y rollback exacto, y con la escritura de resultados
**desactivada** de principio a fin.

Fases relacionadas: `docs/02-roadmap-fases.md`, `docs/10-plan-release-tatami1.md`,
`docs/11-demo-externa-cloudflare.md`, `docs/06-modelo-multitatami.md`.

## 1. Dataset privado

- 25 competidores, 6 categorias de peso: `-62` 3, `-66` 2, `-71` 6, `-77` 7, `-84` 2, `-92` 5.
- Nulls preservados tal cual llegan: `team` 3, `age` 19, `actual_weight` 3. **No se inventa nada**:
  un campo ausente se importa como ausente y se reporta.
- IDs `C001`..`C025`, nombres no vacios, ningun peso por encima del limite de su categoria.
- El fichero vive **fuera del repositorio**, con permisos `0600` y directorio contenedor `0700`.
  No se versiona, no se copia dentro del repo, no se imprime su contenido ni identidades en informes.
- `.gitignore` cubre `.env`, `.env.*`, `__pycache__/`, `*.py[cod]`, `private/`, `*.private.json`,
  `dataset-real.json`, `*dataset-real*.json`, `rehearsal-real.json`, `*rehearsal-real*.json`.
  Verificado: `git ls-files --error-unmatch .env` -> no trackeado.

## 2. Fixture anonimizado versionado

- `tests/fixtures/tournament-rehearsal-anonymized.json`: misma forma (25 registros, mismas
  categorias, mismos nulls), identidades sustituidas (`Competidor NNN`, `Equipo X`).
- Verificacion automatica de no-fuga: ninguna identidad real del dataset privado aparece en el
  fixture, y el fixture se reproduce de forma determinista. Cubierto por la suite del importador.
- Versionar el fixture (y no el dataset) permite que los tests y esta documentacion sean
  reproducibles sin exponer datos personales.

## 3. Mapping a Bracket

| dato del dataset | destino en Bracket |
| --- | --- |
| `category_weight` | nombre del stage (`-62 kg` ... `-92 kg`) |
| competidor | 1 `player` + 1 `team`/entrant |
| `team` (afiliacion del dataset) | **no** se mapea a `teams` de Bracket: es metadata |
| `age`, `actual_weight` | sin columna en el modelo: no se importan |

Campos sin representacion en el modelo (se reportan como `unsupported_metadata`, nunca se
degradan ni se inventan): `age` (6 presentes / 19 nulos), `actual_weight` (22 / 3) y
`category_weight` (va al nombre del stage).

## 4. Byes

Bracket solo admite cuadros de 2/4/8/16/32; el importador calcula la potencia de 2 inmediata
superior y los huecos quedan como byes nativos (no se inventan emparejamientos):

| categoria | participantes | slots | byes |
| --- | --- | --- | --- |
| -62 kg | 3 | 4 | 1 |
| -66 kg | 2 | 2 | 0 |
| -71 kg | 6 | 8 | 2 |
| -77 kg | 7 | 8 | 1 |
| -84 kg | 2 | 2 | 0 |
| -92 kg | 5 | 8 | 3 |
| **total** | **25** | **32** | **7** |

## 5. Import

- Se ejecuta **dentro del contenedor** `bracket`, en una sola transaccion, contra el torneo
  `Torneo Interno CREE Masculino - REHEARSAL`, separado de los torneos de produccion.
- Delta medido por import: +1 torneo, +1 club del ensayo, +6 stages, +6 stage_items,
  +32 stage_item_inputs, +25 teams, +25 players, +13 rounds, +26 matches, +1 court.
- Idempotencia: una segunda ejecucion responde `already_imported: true` / `idempotent: true`,
  **0 filas nuevas** y **0 duplicados** (25 players / 25 nombres distintos, 25 teams / 25).
- Baseline de produccion intacto durante todo el ensayo (torneos 1 y 2).

## 6. Tatami 1 (asignacion y cancelacion)

Flujo validado con WRITE desactivado y sin autenticar contra Bracket:

    candidates -> assign -> state=ready -> marcador 0-0 -> reloj NO iniciado
    -> viewer/control -> cancel_assignment -> state=null -> el combate vuelve a candidates

- `candidates` del puente: 11 combates jugables, `scoreboard_read=true`.
- `assign-match`: `201 assigned`, `scoreboard_sent=true`, `status=ready`, `remaining=300/300`
  (reloj sin iniciar), marcador 0-0-0.
- El estado del scoreboard coincide con el del puente (misma `session_id`, `revision=1`).
- Control: la pagina de control entrega su cookie de control; la vista de display no la entrega.
- `cancel_assignment` (por el socket de control, comando exacto de 6 claves): `ok=true`,
  `revision=2`, broadcast `tatami:state -> null`, y el combate vuelve a `candidates`
  (`active_match_id` de nuevo `null`).
- Nunca se uso: `start`, puntos, ventajas, penalizaciones, `winner`, `finish` ni publicacion
  de resultado.

### Requisito descubierto: `tournaments.dashboard_public`

El puente lee Bracket **sin autenticacion** (`app/bracket_client.py: fetch_stages` ->
`GET /api/tournaments/{id}/stages`). Esa ruta esta protegida por
`bracket/routes/auth.py: user_authenticated_or_public_dashboard`, que responde `401` salvo JWT con
acceso al torneo **o** `tournaments.dashboard_public = true`. Por eso el torneo del ensayo se
marca con ese flag (`UPDATE tournaments SET dashboard_public = true WHERE id = <rehearsal>`),
igual que el torneo 1. Sin ese flag, `candidates` devuelve `401 Bracket returned HTTP 401`.

La alternativa (dar credenciales al puente) se descarto: obligaria al flujo Tatami a autenticar
contra Bracket (`POST /api/token`), que es justo lo que el diseno evita.

## 7. Persistencia

Durante `ready` se reinicio **solo** el scoreboard (`docker restart scoreboard-tatami-1`):
disponible de nuevo en 11 s y el estado se recupero **identico** (`status=ready`, `revision=1`,
misma `session_id`, `remaining=300/300`, marcador 0-0). Bridge, Bracket, PostgreSQL y WireGuard
no se reiniciaron ni se tocaron.

## 8. Interruptor de escritura (WRITE gate)

- `BRACKET_RESULT_WRITE_ENABLED=false` en el entorno del puente; credenciales de escritura
  ausentes (longitud 0).
- `POST /tatamis/1/result` -> **503 `result_write_disabled`**, sin leer el scoreboard ni escribir
  en Bracket.
- Flujo Tatami: **0** `POST /api/token`, **0** `PUT` de resultado en Bracket. (La autenticacion
  administrativa usada fuera de este flujo es otra cosa y no participa aqui.)

## 9. Rollback

- Backup previo de la base de datos (`pg_dump`, permisos `0600`) antes de borrar nada.
- Rollback **exclusivamente** por `rehearsal_tournament_id`, en una transaccion (`--dry-run`
  primero y luego ejecucion real).
- Baseline restaurado **exactamente**: torneos 2, matches 25, teams 10, players 17, rounds 16,
  stages 5, stage_items 9, stage_item_inputs 28; clubes de vuelta a 3. **0 restos** del ensayo.
- Despues se recreo el torneo del ensayo (mismo import, id nuevo) para reutilizarlo en P2.7B:
  6 stages, 32 slots, 7 byes, 25 players/25 teams y `dashboard_public = true`, con el Tatami en
  `state=null`.

## 10. Rendimiento (medido, sin benchmark agresivo)

| paso | tiempo |
| --- | --- |
| carga + validacion + plan del dataset | 0.04 s |
| import (trabajo del importador) | ~0.1-0.24 s |
| `docker exec` + arranque del interprete (envoltorio) | ~2.8-3.1 s |
| `candidates` | 90 ms |
| `assign-match` (Bracket -> puente -> scoreboard) | 69 ms |
| lectura de estado en el scoreboard | 5 ms |
| `cancel_assignment` (emit -> ack) | 11-14 ms |
| reinicio del scoreboard + recuperacion de estado | 11 s |
| rollback completo (transaccional) | < 2 s |

## 11. Limitaciones y pendientes

- El modelo de Bracket no tiene `age` ni `actual_weight`: el ensayo los reporta pero no los
  conserva. La afiliacion del dataset no es `teams` de Bracket.
- `stage_items` exige `ranking_id`; los cuadros solo admiten tamanos potencia de 2 (de ahi los byes).
- El puente requiere `dashboard_public = true` en el torneo (ver §6).
- Validacion visual humana de la UI de Bracket pendiente (`HUMAN UI VALIDATION PENDING`): el
  asistente no maneja OTP ni dispone de navegador en el entorno de origen.
- Este documento y el fixture son las unicas piezas versionadas del ensayo: nunca el dataset real.

## Estado final

- Torneo del ensayo **creado y conservado** (para P2.7B), separado de los torneos de produccion.
- Tatami 1 en `state=null`, `BRACKET_RESULT_WRITE_ENABLED=false`, Cloudflare Access sin cambios.
- Dataset privado unicamente en su ruta privada; ninguna identidad real en Git.

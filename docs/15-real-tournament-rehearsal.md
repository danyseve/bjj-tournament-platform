# 15 - Ensayo de torneo con datos reales (P2.7A)

Estado: **P2.7A - HUMAN UI VALIDATED ✅ / TATAMI 1 COURT VALIDATED ✅** (2026-10-02).

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
- Validacion visual humana de la UI de Bracket **completada** (seccion 12): el asistente sigue sin
  manejar OTP; la revision la hizo el usuario en su navegador.
- Este documento y el fixture son las unicas piezas versionadas del ensayo: nunca el dataset real.

## 12. Validacion visual humana

- Revisada por el usuario en la UI real (`https://bracket.opsforge.cc`, Access `open-otp` 24h, **sin
  cambios**): torneo del ensayo visible, participantes correctos, 6 categorias visibles
  (`-62`/`-66`/`-71`/`-77`/`-84`/`-92`), distribucion coherente, byes/huecos donde corresponden y
  listado de jugadores correcto.
- Evidencia externa: capturas humanas (fuera del repositorio; no se versionan).
- Alcance: revision de estructura y lectura. No se probo interaccion de resultados, que sigue
  deshabilitada por diseno (seccion 17).

## 13. Modelo `team`/entrant: por que "Equipos" muestra personas

Decision documentada; **no se remodela la base de datos**:

- `teams` en Bracket es el **entrant** (el participante de un cuadro), no el club ni la academia.
- En BJJ individual: 1 competidor -> 1 fila en `players` + 1 fila en `teams` + 1 enlace en
  `players_x_teams` (ver `scripts/rehearsal/rehearsal_import.py`). `stage_item_inputs.team_id`
  apunta a ese entrant.
- El club del deportista es otra entidad (`clubs`, `tournaments.club_id`) y nunca se usa para
  emparejar. La afiliacion del dataset no se importa como `teams`.
- Por tanto, ver personas en la seccion "Equipos" de un torneo individual es coherente con el
  modelo, no un fallo de importacion. No se migran `teams` ni se cambian emparejamientos.
- Deuda UX (no ejecutar ahora): cambiar **solo la presentacion** en torneos individuales,
  "Equipos" -> "Competidores / Entrantes", sin tocar el modelo interno. Claves candidatas:
  `teams_title`, `teams_spotlight_description`, `no_teams_title` en
  `frontend/public/locales/es/common.json`.

## 14. Court <-> Tatami: mapeo operativo oficial

| Bracket court | Bridge | Scoreboard |
| --- | --- | --- |
| `Tatami 1` (court del rehearsal, `tournament_id=6`) | `tatami_id=1` | `tatami1.opsforge.cc` |

- El mapeo es por **posicion/nombre**, no por el id interno de la fila: el `id` del court cambia si se
  borra y se vuelve a crear, y no interviene en el mapeo.
- Los torneos de produccion 1 y 2 conservan sus propios courts (`Court 1`, `Court 2`).
- No se toca arquitectura: el Bridge sigue siendo el unico que lee de Bracket y escribe en el
  scoreboard.

## 15. Tatami 1 validado en Planning/Courts

- `GET /api/tournaments/6/courts` -> **200** con exactamente un court: `Tatami 1` (`tournament_id=6`).
- Verificado en la base de datos: courts del ensayo = **1**; `Tatami 2..6` = **0**. El importador lo crea; si se borra desde la UI se
  recrea con el mismo nombre (el `id` interno es irrelevante para el mapeo).
- El court es el destino de un combate en el modelo de planificacion (`matches.court_id` +
  `position_in_schedule`, ver `routes/courts.py` y `routes/matches.py`). La comprobacion fue de
  **solo lectura**: no se planifico ni se reasigno nada en Bracket.

- Regla operativa: el ensayo debe tener **exactamente un** court llamado `Tatami 1`. Lo crea el
  importador, pero tambien se puede crear/borrar desde la UI (`Añadir Cancha` / `Eliminar Cancha`);
  si se borra desde la UI hay que **recrearlo con el mismo nombre** antes de operar el tatami, y
  comprobar que no queda ninguno de mas.

## 16. Flujo Bracket -> Tatami y cancelacion (evidencia)

- `GET /tatamis/1/candidates?tournament_id=6` -> **11** candidatos; elegido un combate con los dos
  slots ocupados (`-62 kg`, `300 s`), con equipos y slots distintos.
- `POST /tatamis/1/assign-match` -> **201 `assigned`**, `scoreboard_sent=true`, mismo combate,
  categoria y duracion.
- Estado del scoreboard -> `ready`, `revision=1`, `remaining=300/300`, reloj **sin iniciar**,
  marcador **0-0** (`points`/`advantages`/`penalties` = 0, `winner_team_id = null`).
- Candidatos 11 -> 10 con `active_match_id` = el asignado (deja de ofrecerse).
- `cancel_assignment` por el socket de control -> `ok=true`, `revision=2`, broadcast
  `tatami:state -> null`. Estado final `null`; candidatos de vuelta a 11; el court sigue existiendo
  como `Tatami 1`.
- Bracket **nunca** se modifico: `court_id`, `stage_item_input*_score` y `winner_from_match_id`
  siguen `NULL`/`0`.

## 17. Interruptor de escritura (WRITE gate) verificado

- `POST /tatamis/1/result` con payload valido -> **503 `result_write_disabled`** (el gate corta antes
  de mirar la sesion).
- `BRACKET_RESULT_WRITE_ENABLED=false`, sin cambios.
- Registro del puente durante la prueba: solo `candidates` (x3), `assign-match` (201) y el `result`
  de comprobacion. **0 `POST /api/token`** y **0 POST/PUT a Bracket** en la ventana del flujo. Los
  unicos `POST /api/token` del dia son inicios de sesion del navegador humano en la UI.

## 18. Roadmap de 6 tatamis (no ejecutado)

Siguiente expansion, tras validar `Tatami 1` (esta fase):

    Tatami 1 -> tatami1.opsforge.cc
    Tatami 2 -> tatami2.opsforge.cc
    Tatami 3 -> tatami3.opsforge.cc
    Tatami 4 -> tatami4.opsforge.cc
    Tatami 5 -> tatami5.opsforge.cc
    Tatami 6 -> tatami6.opsforge.cc

- Cada tatami exige: court en Bracket, servicio de scoreboard, hostname con app de Access
  (`restricted`, allow-list, sesion 8h) e ingress del tunel.
- **No se crean Tatami 2-6 en esta fase.**

## 19. Deuda UX/visual y branding (registrada, no ejecutada)

- **Etiqueta "Equipos"** en torneos individuales (seccion 13).
- **UI de construccion del bracket**: funcional pero limitada para BJJ (layout rigido, poco margen
  para mover/alinear cuadros visualmente, estetica generica). No se cambia ahora. Objetivo futuro:
  eliminatorias claramente alineadas, byes visibles, avance de rondas claro y branding del
  club/torneo.
- **Branding Asturkon**: usar el logo oficial en portal, Bracket/torneo, documentacion y,
  potencialmente, Tatami. Requisito previo: obtener el asset propio (PNG de buena calidad o SVG) y
  versionarlo/autorizarlo en los assets del proyecto. **No** vale el hotlink a un recurso externo
  como solucion productiva.

## 20. Motor de cuadros: que genera hoy Bracket (analisis read-only)

Pregunta: puede Bracket montar solo el cuadro de eliminacion simple por categoria, con sus rondas,
byes y avance de ganador?

Respuesta corta: **si, con dos condiciones** — (a) el elemento de etapa debe declararse con un
`team_count` potencia de dos, y (b) el avance del ganador solo se materializa al guardar resultados.

Evidencia (codigo y datos):

1. **Generacion automatica del cuadro completo.** El endpoint de creacion
   (`routes/stage_items.py:96-97`) hace los inputs vacios y llama a `build_matches_for_stage_item`
   (`logic/scheduling/builder.py:53`), que crea **todas** las rondas de golpe
   (`create_rounds_for_new_stage_item`, `builder.py:28`) y despues los combates:
   `determine_matches_first_round` empareja los inputs dos a dos y
   `determine_matches_subsequent_round` crea las rondas siguientes enlazando
   `stage_item_input{1,2}_winner_from_match_id` al combate anterior
   (`logic/scheduling/elimination.py:19-77`).
2. **Rondas esperables por tamano.** `get_number_of_rounds_to_create_single_elimination`
   (`elimination.py:112-127`) solo acepta **{2, 4, 8, 16, 32}** y devuelve 1/2/3/4/5 rondas; cualquier
   otro valor responde HTTP 400. Es decir: 2 -> final directa; 4 -> semifinal + final; 8 -> cuartos +
   semifinal + final. Confirmado en el ensayo: `-66` y `-84` tienen 1 ronda y 1 combate; `-62` tiene
   2 rondas y 3 combates; `-71`/`-77`/`-92` tienen 3 rondas y 7 combates.
3. **Las rondas futuras existen desde el principio y aparecen vacias.** En el ensayo, los combates de
   las rondas 02/03 existen con los dos huecos vacios (10 combates sin ningun input) y el frontend los
   muestra como pendientes: no hay que crearlos a mano.
4. **Avance del ganador: si, lo resuelve el motor.** Los enlaces se crean al generar el cuadro y, al
   guardar un resultado, `routes/matches.py:189-190` llama a
   `update_inputs_in_subsequent_elimination_rounds` (`logic/ranking/elimination.py:75-86`), que
   resuelve el ganador (`Match.get_winner`, `models/db/match.py:46`) y escribe los inputs en el
   combate siguiente (`sql_set_input_ids_for_match`). En el ensayo hay 10 enlaces en el lado 1 y 10 en
   el lado 2.
5. **Los byes son un hueco, no un concepto.** No hay logica de "bye" en el backend (grep vacio): un
   bye es un input sin equipo. `get_winner` decide **solo por marcador** (`match.py:46-52`), asi que
   un combate con un unico competidor **no avanza solo**: hay que resolverlo desde la UI (marcar el
   resultado/pase). En el ensayo: `-62` 1 bye, `-71` 2, `-77` 1, `-92` 3.
6. **Nombres genericos.** `get_next_round_name` (`sql/rounds.py`) numera "Round 01/02/03": no existen
   "Semifinal"/"Final". En la UI los textos son "Añadir Etapa" / "elemento de etapa" / "objeto de
   Etapa", y el modal de creacion (`components/modals/create_stage_item.tsx`) arranca en
   `ROUND_ROBIN` y solo valida `>= 2` equipos, por lo que puede ofrecer un numero que el backend
   rechaza con 400.
7. **Otros formatos:** `SWISS` no genera ningun combate (`builder.py:53-70`: `return None`).

Consecuencia practica para BJJ: el cuadro de cada categoria se puede montar hoy sin trabajo manual de
rondas ni de enlaces, pero (a) el `team_count` debe ser la potencia de dos inmediata superior al
numero de inscritos, (b) los byes hay que resolverlos en la UI y (c) la presentacion es generica.

## 21. Terminologia: "Tatami" (no "cancha")

- En la UI en espanol el termino visible es "cancha"/"canchas": **13 cadenas**, todas en
  `frontend/public/locales/es/common.json` (`add_court_title`, `courts_title`, `create_court_button`,
  `delete_court_button`, `no_courts_title`, `all_matches_scheduled_description`, ...).
- Fuera de ese fichero no hay ninguna ocurrencia: **es solo copy**. El modelo, las rutas
  (`/tournaments/{id}/courts`), los tipos (`court_id`) y la tabla `courts` no se tocan.
- Termino correcto de cara al usuario en BJJ: **"Tatami"** (plural "Tatamis").
- **Cambio no aplicado**: el frontend se sirve desde la propia imagen de Bracket
  (`SERVE_FRONTEND: "true"` en `docker-compose.yml`), asi que tocar el copy obliga a reconstruir la
  imagen y recrear el contenedor; no es un cambio de fichero aislado. Queda como deuda de bajo riesgo
  con el cambio ya identificado: `"Añadir Cancha" -> "Añadir Tatami"`, `"canchas" -> "tatamis"`,
  manteniendo `courts` en el interior.

## 22. Presentacion del cuadro y branding (deuda)

- Hoy el cuadro es funcional pero generico: rondas "Round NN", cajas uniformes, byes como huecos sin
  etiqueta y sin distincion visual entre cuartos, semifinal y final.
- Objetivo futuro (no ahora): cuadro con aspecto de bracket de BJJ — alineacion por rondas, bye
  explicito, avance claro, nombres de ronda legibles — **sin** doble eliminacion y **sin** tocar el
  motor de emparejamientos ni el modelo de `teams`.
- Branding: logo oficial de Asturkon (PNG de calidad o SVG propio versionado en los assets; nunca un
  hotlink externo) en portal, Bracket/torneo, documentacion y, potencialmente, Tatami.
- Siguiente paso operativo tras validar `Tatami 1`: replicar el patron a `Tatami 2..6`, uno a uno,
  cada uno con su court, su scoreboard, su hostname y su app de Access (`restricted`, 8h).

## Estado final

- Torneo del ensayo **creado y conservado** (para P2.7B), separado de los torneos de produccion.
- Tatami 1 en `state=null`, `BRACKET_RESULT_WRITE_ENABLED=false`, Cloudflare Access sin cambios.
- Dataset privado unicamente en su ruta privada; ninguna identidad real en Git.
- **Validacion humana completada** (seccion 12) y **`Tatami 1` validado como court** (secciones 15-16).
- Deudas registradas, no ejecutadas: etiqueta "Equipos", UI del bracket, branding Asturkon y roadmap
  de Tatami 2-6 (secciones 18-19).
- Analisis read-only del **motor de cuadros** (seccion 20) y verificacion de que "cancha" es **solo
  copy** (`frontend/public/locales/es/common.json`), con el cambio propuesto sin aplicar
  (secciones 21-22).

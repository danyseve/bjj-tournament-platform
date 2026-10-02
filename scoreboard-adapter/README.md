# Scoreboard adapter — P2.4B

Wrapper del repositorio principal; no modifica el submódulo. Documenta el
contrato integrado de Tatami 1: el Bridge lo alimenta por la API interna y el
servidor integrated es la fuente autoritativa del combate en vivo (P2.3A-P2.4B).

## Modos y límite de seguridad

El CMD de la imagen ejecuta `node scoreboard-adapter/launcher.js`. Sin
`SCOREBOARD_MODE=integrated` carga `/app/app.js` original (modo standalone),
con sus rutas, relays y arranque intactos; no registra los endpoints internos.
Integrated es opt-in explícito: construye Express y Socket.IO reutilizando
`/app/routes`, `/app/views` y `/app/public`, sin cargar el servidor original.
No cambia UI, Compose, env, nginx, PostgreSQL ni producción.

Esta API exige un secreto compartido en los endpoints `/internal/*`: la cabecera
`X-Internal-Token` debe coincidir con `SCOREBOARD_INTERNAL_TOKEN`. El valor viene
del entorno, **no está hardcodeado** y no se registra en logs (comparación en
tiempo constante). Sin secreto configurado, `/internal/*` responde **401**
(fail-closed). El navegador/UI nunca envía ni conoce ese token: la presentación
llega por el socket `tatami:state`. No publicar `/internal/` ni el puerto
integrated en Internet, y no añadir credenciales fuera de ese secreto.

## Contrato integrado

`PUT /internal/tatamis/1/assignment`, JSON exacto:

```json
{
  "tournament_id": 7,
  "match_id": 40,
  "tatami_id": 1,
  "fighter_a": {"stage_item_input_id": 1, "team_id": 101, "name": "Ana", "club": null},
  "fighter_b": {"stage_item_input_id": 2, "team_id": 102, "name": "Bea", "club": null},
  "category": {"stage_item_id": 9, "name": "Adult"},
  "duration_seconds": 300
}
```

Todos los campos son obligatorios. Claves extra se rechazan en cada nivel.
Identificadores y duración son números enteros positivos seguros de JS
(`Number.isSafeInteger`); no se convierten strings/booleans. `tatami_id` es
literal numérico 1. Los inputs y equipos de ambos luchadores deben ser distintos.
Los nombres son strings sin normalizar; ambos `club` deben ser null.

- Primera asignación: HTTP **201**, `{ "state": <snapshot> }`.
- Replay estructural idéntico (orden de claves irrelevante): **200**, mismo
  snapshot/session, sin reinicialización de puntuación, tiempo o revisión.
- Cualquier otra asignación válida mientras haya estado: **409**, no cambia nada;
  también si es otro match. Un cuerpo inválido siempre devuelve **400**.
- JSON inválido: **400**. Otras rutas de tatami no están implementadas (**404**).

`GET /internal/tatamis/1/state` devuelve **200** con `{ "state": null }` antes
 de asignar y `{ "state": <snapshot> }` después. El snapshot contiene exactamente
los campos de la asignación, añade a cada fighter `points`, `advantages` y
`penalties` inicialmente 0; y añade:

```json
{
  "remaining_seconds": 300,
  "status": "ready",
  "winner_team_id": null,
  "method": null,
  "session_id": "UUID v4 generado por el servidor",
  "revision": 1
}
```

Cada instancia acepta una única asignación; no hay transición al siguiente
match ni API pública HTTP de mutación: el estado vivo cambia solo por comandos
canónicos del socket (ver *Marcador canónico*). Reiniciar el proceso pierde el
estado en memoria. Cada nueva asignación en una instancia vacía genera UUID.
Payload aceptado, respuesta y lecturas son copias profundas independientes.

## Marcador canónico (P2.3E)

El servidor integrated es la única fuente de verdad del combate en vivo (estado
canónico, scoring y reloj). El Bridge solo adapta y la UI solo presenta
snapshots: el navegador no mantiene contabilidad autoritativa.

`tatami:update` (Socket.IO cliente → servidor) con ack. Ejemplo:

```json
{
  "session_id": "UUID del snapshot",
  "command_id": "UUID del cliente",
  "expected_revision": 7,
  "tatami_id": 1,
  "match_id": 40,
  "operation": "score_delta",
  "fighter": "a",
  "field": "points",
  "delta": 2
}
```

Operaciones implementadas (`reset` usa solo las seis claves base; el conjunto de
claves por operación es exacto, así que un campo desconocido o faltante rechaza
el comando):

- `score_delta`: `fighter` `a|b`, `field` `points|advantages|penalties`, `delta`
  entero distinto de 0 y `|delta| <= 100`. El resultado nunca queda negativo ni
  supera 1000: se **rechaza**, nunca se recorta en silencio.
- `set_running`: `running` booleano explícito (no es un toggle). Idempotente:
  repetir el estado actual no cambia nada. Arranca desde `ready` o `paused`;
  pedir arranque de un combate `finished` se rechaza.
- `reset`: detiene el reloj, restaura `remaining_seconds = duration_seconds`,
  pone scoring a 0, conserva combate, asignación, participantes y `session_id`,
  e incrementa `revision`.
- `finish`: cierra el resultado (ver *Finalización local*).
- `clear_match`: abandona el combate cerrado y deja el tatami vacío (ver
  *Tiempo agotado y liberación del tatami*). Sin otras claves que las base.
- `cancel_assignment`: libera una asignación equivocada que nunca ha arrancado
  (ver *Cancelación de una asignación en `ready`*). Sin otras claves que las base.

Ack de éxito `{ "ok": true, "command_id": "...", "revision": 7 }`; de error
`{ "ok": false, "code": "stale_revision", "revision": 8 }`. Códigos:
`invalid_command` (forma, claves o tipos), `invalid_operation` (operación no
implementada o valor no permitido), `wrong_session`, `wrong_match`,
`stale_revision`, `unauthorized`, `already_finished` (resultado cerrado y
congelado), `awaiting_result` (reloj agotado y resultado pendiente),
`not_finished` (`clear_match` sobre un resultado todavía abierto),
`not_ready` (`cancel_assignment` fuera de un combate `ready`),
`not_clean` (`cancel_assignment` con el marcador ya tocado),
`invalid_winner`, `invalid_method`.

Idempotencia: cada `command_id` aceptado se recuerda (memoria acotada a 256
comandos por sesión, se vacía al asignar). Un replay devuelve el ack original y
**no** reaplica la operación, aunque llegue con revisión antigua; solo se
registran comandos aceptados, de modo que un comando rechazado puede
reintentarse. Todo comando aceptado que cambia estado incrementa `revision += 1`
y un `expected_revision` distinto se rechaza sin mutar (`stale_revision`).

Reloj autoritativo: `remaining_seconds` es el valor congelado y el reloj guarda
un ancla monotónica (`performance.now()`) al arrancar; cada snapshot calcula el
restante real y al pausar se congela el calculado. No hay decremento por segundo
como fuente temporal, no se admiten valores negativos y al llegar a 0 el estado
pasa a `awaiting_result` con `remaining_seconds = 0` (el tiempo agotado **no**
cierra el resultado: ver *Tiempo agotado y liberación del tatami*). No hay
persistencia: reiniciar el proceso pierde el estado.

## Finalización local (P2.3F)

`finish` finaliza el combate **solo en memoria**: el resultado no se persiste en
disco ni en base de datos y no se escribe nada en Bracket. No hay recuperación
tras reiniciar el proceso.

Payload: los campos base (`session_id`, `command_id`, `expected_revision`,
`tatami_id`, `match_id`, `operation`) más `winner_team_id` y `method`, sin campos
extra. `winner_team_id` debe ser el `team_id` de uno de los dos luchadores
asignados (`invalid_winner` en caso contrario). `method` debe pertenecer al enum
**propio del dominio BJJ local** — `points`, `submission`, `decision`,
`disqualification`, `walkover`, `referee_stoppage`, `other` — que todavía **no se
traduce al modelo de Bracket** (`invalid_method` en caso contrario).

Al aceptar: el reloj se congela en el valor calculado en ese instante, `status`
pasa a `finished`, se registran ganador y método, se conserva el scoring final y
`session_id`, `revision` sube exactamente una vez y se emite el snapshot completo.
Un combate `finished` queda congelado: `score_delta`, `set_running`, `reset` y un
`finish` distinto se rechazan con `already_finished` sin mutar nada, y solo el
replay del mismo `command_id` devuelve el ack original. `finish` es válido desde
`ready`, `running`, `paused` y `awaiting_result`; desde `awaiting_result` conserva
`remaining_seconds = 0` y conserva el scoring.

En `/control` y `/control2` hay un panel mínimo de finalización: seleccionar
ganador y método, pulsar *Finalizar…* y confirmar en un segundo paso explícito
(armar nunca emite). Tras finalizar, los controles de puntuación y reloj quedan
bloqueados —y sus manejadores comprueban la autorización, no solo el aspecto— y
se muestra el resultado. La pantalla `/` refleja el resultado final y sigue sin
construir ningún control.

## Tiempo agotado y liberación del tatami (P2.3G)

Agotar el reloj y cerrar el resultado son hechos distintos, y el estado lo
refleja con dos estados separados:

```json
{
  "status": "awaiting_result",
  "remaining_seconds": 0,
  "winner_team_id": null,
  "method": null
}
```

`awaiting_result` significa *el tiempo terminó y el resultado sigue abierto*: el
reloj queda parado en 0, el scoring queda congelado y no se inventa ganador. En
ese estado solo se acepta `finish`; `score_delta`, `set_running` (`true` y
`false`) y `reset` se rechazan con `awaiting_result` sin mutar nada. El `finish`
que resuelve ese estado valida ganador y método igual que cualquier otro, cambia
`awaiting_result → finished`, mantiene `remaining_seconds = 0`, conserva el
scoring, sube `revision` exactamente una vez y emite el snapshot completo.

`finished` sigue siendo el resultado **cerrado y congelado**: no admite ninguna
mutación y solo responde al replay del mismo `command_id`. Para abandonar un
combate cerrado existe una operación propia, separada de `reset`:

- `clear_match`: solo válida sobre `finished` (en `ready`, `running`, `paused` o
  `awaiting_result` se rechaza con `not_finished`). Al aceptarla se elimina el
  estado activo, desaparece el `session_id` y su memoria de idempotencia, el
  tatami queda vacío y se emite un `tatami:state` con payload `null` que
  representa explícitamente *sin combate*. No se carga ningún match: la
  asignación del siguiente combate es un acto aparte del Bridge.

Requisito de orden: **primero `finish`, después `clear_match`**. Mientras haya un
estado activo, `PUT /internal/tatamis/1/assignment` con otro match sigue
devolviendo **409**; tras `clear_match` vuelve a aceptar (**201**) un combate
distinto, con `session_id` nuevo, `revision` inicial 1, scoring a 0 y
`status: "ready"`. `GET /internal/tatamis/1/state` devuelve `{ "state": null }`
mientras el tatami esté libre.

`clear_match` usa las seis claves base (sin ganador ni método) y exige la misma
credencial de control que el resto de `tatami:update`: la pantalla `/` no puede
liberar el tatami. En `/control` y `/control2` la liberación es un panel propio
con dos pasos (pulsar *Liberar Tatami* y confirmar en un segundo acto explícito,
que avisa de que el resultado en memoria se perderá); nunca se combina con
finalizar en un solo botón y solo se habilita con el resultado ya cerrado. Con el
tiempo agotado la UI bloquea scoring y reloj, muestra *Tiempo finalizado —
pendiente de resultado* y deja el panel de finalización habilitado; `/` anuncia
el tiempo agotado sin inventar ganador y sigue siendo solo lectura.

### Cancelación de una asignación en `ready` (P2.6A.1)

`clear_match` no cubre el caso de un combate asignado por error y todavía sin
empezar: `ready` no es `finished`, de modo que la liberación se rechaza. Para ese
caso existe una operación propia, deliberadamente separada de `clear_match`:

- `cancel_assignment`: solo válida sobre un combate activo `ready` con el reloj
  intacto (`remaining_seconds === duration_seconds`), el marcador a cero y sin
  ganador ni método. El resto de estados se rechaza sin mutar: `running`,
  `paused`, `awaiting_result` y `finished` con `not_ready`, y un `ready` con
  puntos, ventajas o penalizaciones con `not_clean`. No cierra combates ni
  reabre resultados: no es un atajo de `finish`.
- Efecto: el mismo vaciado que `clear_match` —desaparecen el estado activo, el
  `session_id`, el reloj y el historial de comandos; se persiste `state: null` y
  se difunde `tatami:state` con `null`—, pero sin haber tenido nunca un resultado
  que perder.
- Idempotencia: repetir el mismo `command_id` responde exactamente el mismo ack y
  no vuelve a mutar. La memoria del reintento vive en proceso y solo cubre el
  tatami ya vacío por esa cancelación; tras un reinicio no hay nada que cancelar
  y el reintento se rechaza con `wrong_session`, también sin efecto.
- Autorización y superficie: las seis claves base, la misma credencial de control
  que `clear_match` y **solo por Socket.IO**; no se añade ninguna ruta HTTP. En
  `/control` y `/control2` es un panel propio de dos pasos (*Cancelar asignación*
  y confirmación en un segundo acto) que solo se muestra con un combate `ready`
  intacto y que nunca se mezcla con *Liberar Tatami*, la liberación posterior a
  `finish`.
- Después de cancelar, la siguiente asignación vuelve a ser un
  `PUT /internal/tatamis/1/assignment` normal: **201**, `session_id` nuevo,
  `revision` inicial 1, scoring a 0 y `status: "ready"`.

Limitación: el estado vive en memoria y, en el modo integrado, en el fichero
`SCOREBOARD_STATE_FILE` (ver *Persistencia y recuperación del estado vivo*); el
adapter no escribe nada en Bracket en ningún caso. Sin fichero de estado
configurado, reiniciar el proceso pierde el estado —incluido un combate liberado
o un resultado cerrado.

## Control autorizado

`tatami:update` exige credencial de control: `SCOREBOARD_CONTROL_TOKEN` (entorno,
distinto del token interno del Bridge, nunca hardcodeado, nunca en query string,
nunca en logs). Las páginas `/control` y `/control2` la reciben como cookie
`HttpOnly` + `SameSite=Strict` (`scoreboard_control`), que el navegador envía en
el handshake; el servidor la compara en tiempo constante. Sin secreto
configurado o sin cookie válida, todo `tatami:update` responde `unauthorized` y
el estado no cambia (fail-closed). La pantalla `/` no recibe credencial y sigue
recibiendo `tatami:state`. Ningún script de la página lee la cookie y el token
interno del Bridge no se expone al navegador. Modelo de confianza: abrir una
página de control en la red interna concede autoridad de control; la
autenticación por operador queda fuera de esta fase.

En la UI integrada los controles legacy se mapean a operaciones canónicas
(scoring → `score_delta`; iniciar/pausar → `set_running` con el booleano derivado
del `status` del servidor; reset → `reset`), y los controles sin operación
canónica (nombres y ±minuto) siguen bloqueados. La UI integrada no emite eventos
legacy; standalone sigue usando el sistema legacy intacto.

## Socket.IO y compatibilidad

`tatami:state` lleva el snapshot directamente (no el envelope HTTP), se envía a
cada nueva conexión cuando existe estado y se difunde a todos tras 201, replay
200, cada comando aceptado y una vez por segundo mientras el reloj corre. No se
emite si el estado está vacío ni tras error.

Los cuatro relays originales permanecen:
`bjj:score`, `bjj:restart`, `bjj:start` usan `io.sockets.emit` e incluyen emisor;
`bjj:name` usa `socket.broadcast.emit` y excluye emisor. Ninguno altera el estado
integrado. `/`, `/control`, `/control2`, recursos estáticos y cliente Socket.IO
permanecen disponibles.

## Tests sin instalar globalmente

Node 22.23.3 ARM64 y dependencias quedan aislados en
`/home/ubuntu/.cache/scoreboard-p23b` (jsdom, para la suite de UI, en
`/home/ubuntu/.cache/scoreboard-p23c`). `npm ci --omit=dev --no-audit --no-fund`
usa copias del package.json y lock originales del scoreboard (sin cambios).

```sh
cd /home/ubuntu/projects/bjj-tournament-platform
NODE_PATH=/home/ubuntu/.cache/scoreboard-p23b/node_modules:/home/ubuntu/.cache/scoreboard-p23c/node_modules \
 /home/ubuntu/.cache/scoreboard-p23b/node-v22.23.3-linux-arm64/bin/node \
 --test scoreboard-adapter/tests/adapter.test.js scoreboard-adapter/tests/ui.test.js scoreboard-adapter/tests/tatami.test.js scoreboard-adapter/tests/persistence.test.js
```

123 casos con `node:test` (18 `adapter.test.js`, 24 `ui.test.js` con jsdom, 55
`tatami.test.js` del marcador canónico, finalización y liberación, 26
`persistence.test.js` de persistencia y recuperación con filesystem temporal),
HTTP real y Engine.IO/Socket.IO polling
sin cliente adicional. Los tests de reloj inyectan un reloj monotónico falso, sin
sleeps. El test de no-reset instrumenta el módulo en un VM únicamente en
pruebas; no añade exports/endpoints de mutación al runtime. Evidencias verticales
red/green por caso en el cache para el hito P2.3B (`01-red.tap` … `15-green.tap`);
los casos posteriores usan la suite completa anterior.

Después de pasar tests, build manual con contexto raíz:

```sh
docker build -f docker/scoreboard/Dockerfile -t bjj-scoreboard:p2.4b-test .
```

## Persistencia y recuperación del estado vivo (P2.4B)

Opt-in por variable de entorno, sin ruta productiva hardcodeada:

```sh
SCOREBOARD_STATE_FILE=/ruta/al/state.json
```

- sin la variable: comportamiento idéntico al anterior (todo en memoria) y el
  modo standalone intacto;
- con la variable: cada mutación aceptada se escribe **antes** de su ack.

El I/O de disco vive solo en `state-store.js`; `state.js` construye y valida el
documento y llama al sink inyectado, así que la lógica del marcador no conoce el
sistema de ficheros.

### Documento versionado

```json
{"schema_version": 1, "saved_at": "2026-10-02T10:00:00.000Z", "clock": {"wall_anchor": 1759400000000},
 "state": {}, "command_history": [{"command_id": "...", "ack": {}}]}
```

- `state`: exactamente el marcador canónico (session_id, revision, tatami_id,
  tournament_id, match_id, luchadores con scoring, categoría, duración, restante,
  status, ganador y método) o `null` si el tatami está vacío;
- `clock.wall_anchor`: instante de pared en ms al que corresponde
  `state.remaining_seconds` mientras el combate corre; `null` con el reloj parado;
- `command_history`: memoria de idempotencia acotada (256 entradas, solo comandos
  aceptados).

Nunca se persisten tokens, cookies, sockets, configuración ni nada del resultado
en Bracket. Los datos de los tests son sintéticos.

### Escritura atómica

Temporal en el mismo directorio, `write` + `fsync`, `rename` sobre el fichero
final, permisos `0600` y fsync best-effort del directorio. Nunca se escribe el
fichero final a medias y no se generan backups ilimitados: un `rename` fallido
deja intacto el documento anterior y limpia el temporal.

### Orden y política de fallo

`estado nuevo -> persistir -> publicar/ack`. Si la escritura falla, el comando se
revierte en memoria (scoring, revision, historial y ancla vuelven al valor
anterior) y la operación responde `persist_failed`; un assignment nuevo responde
**503** y no se emite nada por el socket. Nunca se finge éxito.

### clear_match

Persiste `state: null` explícito y vacía `command_history`; el fichero se conserva
(no se borra), lo que distingue "nunca inicializado" (sin fichero) de
"explícitamente vacío" (`state: null`) y de "corrupto" (arranque fallido).

### Recovery al arranque (integrated + SCOREBOARD_STATE_FILE)

Antes de escuchar:

- fichero inexistente -> tatami vacío normal;
- documento válido -> estado recuperado (misma session_id, misma revision,
  scoring, ganador y método);
- `state: null` -> tatami vacío;
- JSON corrupto, `schema_version` desconocida o estructura inválida -> **no
  arranca**: `launcher.js` registra el motivo y sale con código 1, y el fichero
  se deja tal cual estaba (jamás se sobrescribe con un estado vacío).

### Recuperación del reloj

`performance.now()` no sobrevive a un reinicio: el documento guarda
`remaining_seconds` y el `wall_anchor` del mismo instante.

```text
elapsed   = Date.now() - wall_anchor
remaining = max(0, remaining_seconds - elapsed)
```

Después se crea un ancla monotónica nueva, que vuelve a mandar. Si
`remaining <= 0` al restaurar, el combate se restaura como `awaiting_result` con
el reloj parado, nunca como `running`, y `finish` sigue siendo la única salida.
La expiración del reloj en vivo (ticker) no se persiste: se recalcula idéntica en
el siguiente arranque y se escribe con el siguiente comando aceptado.

### Idempotencia entre reinicios

El historial acotado de `command_id` aceptados se persiste, así que un replay
posterior al reinicio devuelve el mismo ack (`changed: false`) sin reaplicar
scoring, `finish` ni `reset`. Los comandos rechazados no se persisten. Tras un
reinicio el mismo assignment sigue siendo **200** y otro combate sigue siendo
**409**: la ocupación del tatami no se pierde.

### Socket.IO y UI

El estado recuperado viaja por el mismo contrato `tatami:state`, así que un
cliente que conecte después del reinicio recibe el snapshot sin saber que hubo
reinicio y la UI no necesita cambios.

## Próximos pasos (no implementados)

- Carga automática del siguiente combate: `clear_match` vacía el tatami, pero
  quién elige y asigna el siguiente match sigue fuera del alcance.
- Política de traducción del resultado BJJ hacia Bracket (P2.4C): decidir y
  documentar cómo se traduce `winner_team_id`/`method` al modelo de Bracket antes
  de implementar ninguna escritura.
- Mapeo del enum de métodos y del resultado hacia el modelo de Bracket: la
  política de escritura de resultados **no** está resuelta ni decidida aquí.

Solo los cinco archivos JS del adapter entran en el contexto/runtime de la imagen;
tests, docs y scripts de validación no se copian. El smoke test Python stdlib
`tests/runtime_smoke.py` se ejecuta desde host contra el contenedor temporal,
administra su red propia y hace cleanup en finally. Su evidencia JSON queda en
el cache, no en el repo. No se ejecuta contra producción.

# Scoreboard adapter — P2.3G

Wrapper del repositorio principal; no modifica el submódulo. Documenta el
contrato integrado de Tatami 1: el Bridge lo alimenta por la API interna y el
servidor integrated es la fuente autoritativa del combate en vivo (P2.3A-P2.3G).

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

Ack de éxito `{ "ok": true, "command_id": "...", "revision": 7 }`; de error
`{ "ok": false, "code": "stale_revision", "revision": 8 }`. Códigos:
`invalid_command` (forma, claves o tipos), `invalid_operation` (operación no
implementada o valor no permitido), `wrong_session`, `wrong_match`,
`stale_revision`, `unauthorized`, `already_finished` (resultado cerrado y
congelado), `awaiting_result` (reloj agotado y resultado pendiente),
`not_finished` (`clear_match` sobre un resultado todavía abierto),
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

Limitación: todo sigue **en memoria**. No hay persistencia en disco ni en base de
datos, no se escribe nada en Bracket y reiniciar el proceso pierde el estado —
incluido un combate liberado o un resultado cerrado.

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
 --test scoreboard-adapter/tests/adapter.test.js scoreboard-adapter/tests/ui.test.js scoreboard-adapter/tests/tatami.test.js
```

97 casos con `node:test` (18 `adapter.test.js`, 24 `ui.test.js` con jsdom, 55
`tatami.test.js` del marcador canónico, finalización y liberación), HTTP real y Engine.IO/Socket.IO polling
sin cliente adicional. Los tests de reloj inyectan un reloj monotónico falso, sin
sleeps. El test de no-reset instrumenta el módulo en un VM únicamente en
pruebas; no añade exports/endpoints de mutación al runtime. Evidencias verticales
red/green por caso en el cache para el hito P2.3B (`01-red.tap` … `15-green.tap`);
los casos posteriores usan la suite completa anterior.

Después de pasar tests, build manual con contexto raíz:

```sh
docker build -f docker/scoreboard/Dockerfile -t bjj-scoreboard:p2.3g-test .
```

## Próximos pasos (no implementados)

- Carga automática del siguiente combate: `clear_match` vacía el tatami, pero
  quién elige y asigna el siguiente match sigue fuera del alcance.
- Persistencia y recuperación tras reinicio del proceso: hoy un reinicio pierde
  el estado completo, incluido el resultado pendiente o cerrado.
- Mapeo del enum de métodos y del resultado hacia el modelo de Bracket: la
  política de escritura de resultados **no** está resuelta ni decidida aquí.

Solo los cuatro archivos JS del adapter entran en el contexto/runtime de la imagen;
tests, docs y scripts de validación no se copian. El smoke test Python stdlib
`tests/runtime_smoke.py` se ejecuta desde host contra el contenedor temporal,
administra su red propia y hace cleanup en finally. Su evidencia JSON queda en
el cache, no en el repo. No se ejecuta contra producción.

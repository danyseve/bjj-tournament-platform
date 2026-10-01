# Scoreboard adapter — P2.3B

Wrapper del repositorio principal; no cambia el submódulo ni conecta Bridge.

## Modos y límite de seguridad

El CMD de la imagen ejecuta `node scoreboard-adapter/launcher.js`. Sin
`SCOREBOARD_MODE=integrated` carga `/app/app.js` original (modo standalone),
con sus rutas, relays y arranque intactos; no registra los endpoints internos.
Integrated es opt-in explícito: construye Express y Socket.IO reutilizando
`/app/routes`, `/app/views` y `/app/public`, sin cargar el servidor original.
No cambia UI, Compose, env, nginx, PostgreSQL ni producción.

Esta API **no tiene autenticación**: solo para una red interna de confianza.
No publicar `/internal/` ni el puerto integrated en Internet. No se añaden
credenciales ni secretos. La prueba aislada publica exclusivamente
`127.0.0.1:39000`, sin red `bjj-net` ni volúmenes.

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
match, reset, reloj ni API pública de mutación. Reiniciar el proceso pierde el
estado en memoria. Cada nueva asignación en una instancia vacía genera UUID.
Payload aceptado, respuesta y lecturas son copias profundas independientes.

## Socket.IO y compatibilidad

`tatami:state` lleva el snapshot directamente (no el envelope HTTP), se envía a
cada nueva conexión cuando existe estado y se difunde a todos tras 201 o replay
200. No se emite si el estado está vacío ni tras error. No existe `tatami:update`.

Los cuatro relays originales permanecen:
`bjj:score`, `bjj:restart`, `bjj:start` usan `io.sockets.emit` e incluyen emisor;
`bjj:name` usa `socket.broadcast.emit` y excluye emisor. Ninguno altera el estado
integrado. `/`, `/control`, `/control2`, recursos estáticos y cliente Socket.IO
permanecen disponibles.

## Tests sin instalar globalmente

Node 22.23.3 ARM64 y dependencias quedan aislados en
`/home/ubuntu/.cache/scoreboard-p23b`. `npm ci --omit=dev --no-audit --no-fund`
usa copias del package.json y lock originales del scoreboard (sin cambios).

```sh
cd /home/ubuntu/projects/bjj-tournament-platform
NODE_PATH=/home/ubuntu/.cache/scoreboard-p23b/node_modules \
 /home/ubuntu/.cache/scoreboard-p23b/node-v22.23.3-linux-arm64/bin/node \
 --test scoreboard-adapter/tests/adapter.test.js
```

15 casos con `node:test`, HTTP real y Engine.IO/Socket.IO polling sin cliente
adicional. El test de no-reset instrumenta el módulo en un VM únicamente en
pruebas; no añade exports/endpoints de mutación al runtime. Evidencias verticales
red/green por caso en el cache (`01-red.tap` … `15-green.tap`).

Después de pasar tests, build manual con contexto raíz:

```sh
docker build -f docker/scoreboard/Dockerfile -t bjj-scoreboard:p2.3b-test .
```

Solo los tres archivos JS del adapter entran en el contexto/runtime de la imagen;
tests, docs y scripts de validación no se copian. El smoke test Python stdlib
`tests/runtime_smoke.py` se ejecuta desde host contra el contenedor temporal,
administra su red propia y hace cleanup en finally. Su evidencia JSON queda en
el cache, no en el repo. No se ejecuta contra producción.

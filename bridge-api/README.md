# BJJ Bridge API — P2.3A / P2.4A / P2.4D

Capa de lectura y normalización entre Bracket y BJJ-Scoreboard. Desde P2.3D
entrega además la asignación normalizada al scoreboard integrado del **Tatami 1**
por HTTP. Desde P2.4A puede además **listar los combates candidatos** de un torneo
(`GET /tatamis/1/candidates`), pero **elegir y asignar sigue siendo un acto
explícito del operador**: no existe autoavance ni asignación silenciosa.

Desde P2.4D puede **publicar en Bracket un resultado cerrado**, pero solo el único
que es representable sin falsear datos: **victoria natural por puntos**. Todo lo
demás se bloquea con `pending_manual`/`conflict` y no se escribe. La escritura va
por credenciales propias del Bridge (nunca las del navegador), con lectura previa,
CAS lógico y verificación posterior. **Implementado, no desplegado**: mientras
producción no ejecute un Bracket >= `47bc129`, la escritura no puede habilitarse
(ver *Publicación de resultados*).

## Configuración de la URL

`BRACKET_API_URL` es la base completa configurada. El valor por defecto del
código es `http://bracket:8400/api` e incluye `/api`. El cliente usa esa base
(sin la barra final) y añade únicamente `/ping` o
`/tournaments/{tournament_id}/stages`; **nunca añade otro prefijo `/api`**.
No se cambia ninguna configuración de producción como parte de P2.3A.

La consulta de stages envía `no_draft_rounds=true`, tiene timeout de 10 segundos,
no sigue redirecciones y no intenta autenticarse. Un torneo no público puede
responder 401/403. A Bracket solo se realizan solicitudes GET.

## Scoreboard (Tatami 1)

`SCOREBOARD_TATAMI_1_URL` es la base del scoreboard del Tatami 1
(`http://scoreboard-tatami-1:3000` por defecto). En P2.3D solo está habilitado
el Tatami 1: cualquier otro tatami se rechaza con 400 y **la URL nunca la envía
el cliente**.

La entrega usa `PUT {base}/internal/tatamis/1/assignment` con la cabecera
`X-Internal-Token`. El secreto se toma de `SCOREBOARD_INTERNAL_TOKEN`: **no está
hardcodeado, no viaja al navegador y no se registra en logs**. Si no está
configurado, la entrega devuelve error en vez de simular éxito.

## Endpoints

```text
GET  /health
GET  /health/bracket
GET  /tatamis/{tatami_id}/candidates?tournament_id=...
POST /tatamis/{tatami_id}/assign-match
POST /tatamis/{tatami_id}/result
```

### Normalizar y entregar un combate

`POST /tatamis/1/assign-match` acepta **solo** estos tres campos:

```json
{"tatami_id": 1, "tournament_id": 7, "match_id": 40}
```

Los identificadores deben ser enteros positivos estrictos: no booleanos,
strings ni números decimales. Solo está permitido `tatami_id=1` y debe
coincidir con la ruta. Los campos adicionales (incluidos `red`, `blue`,
`category`, `duration_seconds` o el antiguo `tatami`) se rechazan.

La respuesta confirma la entrega real (identificadores/nombres ilustrativos).
Primera asignación: HTTP 201 con `status=assigned`. Replay idempotente: HTTP 200
con `status=replayed`. `state` es el snapshot devuelto por el scoreboard.

```json
{
  "status": "assigned",
  "scoreboard_sent": true,
  "match": {
    "tournament_id": 7,
    "match_id": 40,
    "tatami_id": 1,
    "fighter_a": {"stage_item_input_id": 1, "team_id": 101, "name": "Ana", "club": null},
    "fighter_b": {"stage_item_input_id": 2, "team_id": 102, "name": "Bea", "club": null},
    "category": {"stage_item_id": 20, "name": "Adult / Blue / 70kg"},
    "duration_seconds": 300
  },
  "state": {
    "session_id": "…",
    "revision": 1,
    "remaining_seconds": 300,
    "fighter_a": {"name": "Ana", "points": 0, "advantages": 0, "penalties": 0},
    "fighter_b": {"name": "Bea", "points": 0, "advantages": 0, "penalties": 0}
  }
}
```

`fighter_a` corresponde a input1 y `fighter_b` a input2. `stage_item_input_id`
conserva la identidad del input y `team_id` la del **Team** resuelto. El nombre
es el del Team; nunca se escoge un Player. Team es el competidor,
no la academia: `club` es siempre null. La categoría conserva `stage_item_id`
y el nombre del stage item.
Se valida la pertenencia al torneo y la cadena stage → stage item → round →
match, además de la identidad y pertenencia de ambos inputs y Teams. Los
participantes y los inputs deben ser distintos. No se admiten inputs vacíos,
pendientes, inconsistentes o rondas draft.

La duración usa `custom_duration_minutes` si no es null; en otro caso usa
`duration_minutes`. El valor elegido debe ser un entero positivo estricto.
Un custom de cero es inválido: no se sustituye por el valor base. Se convierte
a segundos multiplicando por 60, **sin margen ni valor por defecto inventado**.

Errores de asignación:
- 400: ruta y tatami del body no coinciden.
- 422: body inválido, extras o identificadores no admitidos.
- 401/403/404 de Bracket: se conservan; combate ausente también devuelve 404.
- 409: combate draft, mismo competidor o mismo input; también se refleja el 409
  del scoreboard.
- 502: fallo de transporte, otro error HTTP, JSON/estructura inválida,
  pertenencia inconsistente, input sin resolver o duración inválida. Incluye
  conexión rechazada, 5xx y respuesta inválida del scoreboard, y el token interno
  sin configurar. Nunca se disfraza de éxito.
- 504: timeout de Bracket o del scoreboard.

### Candidatos (solo lectura)

`GET /tatamis/1/candidates?tournament_id=7` devuelve una lista **técnica y plana**
de combates jugables, sin asignar nada. Solo está permitido `tatami_id=1` (otro
valor: 400) y el `tournament_id` debe ser un entero positivo estricto (400 si no
lo es; 422 si falta o no es un entero).

```json
{
  "tournament_id": 7,
  "active_match_id": 40,
  "scoreboard_read": true,
  "candidates": [
    {
      "tournament_id": 7,
      "match_id": 41,
      "fighter_a": {"stage_item_input_id": 11, "team_id": 101, "name": "Ana", "club": null},
      "fighter_b": {"stage_item_input_id": 12, "team_id": 102, "name": "Bea", "club": null},
      "category": {"stage_item_id": 2, "name": "Adulto -70"},
      "duration_seconds": 420
    }
  ]
}
```

Sin datos innecesarios: cada candidato lleva solo esos seis campos (ni scores, ni
`winner_from_*`, ni `court_id`, ni `position_in_schedule`, ni `is_draft`).

**Orden.** Se respeta exactamente el orden que devuelve Bracket
(`data[] → stage_items[] → rounds[] → matches[]`). **No se reordena por
`match_id`**: el payload real del torneo 1 lo demuestra — los combates de la ronda
4 (ids 7 y 8) llegan antes que los de la ronda 1 (ids 1 y 2), así que ordenar por
id rompería el orden del propio Bracket. Tampoco se reasigna `court_id` ni se toca
`position_in_schedule`.

**Reglas de candidatura.** Se listan los combates que cumplen el contrato de
asignación, construidos con **el mismo normalizador** que usa `assign-match`, de
modo que todo candidato listado es asignable por construcción. Se omiten:

- combates de rondas `is_draft=true`;
- combates con un pase sin resolver (sin `stage_item_inputN_id`, sin objeto de
  input o alimentado por un `winner_from_match_id` pendiente);
- combates con equipo ausente, `team_id` no positivo o conflicto marcado;
- combates con identidades repetidas (mismo `team_id` o mismo
  `stage_item_input_id` en ambos lados);
- combates sin duración utilizable (`custom_duration_minutes` y, si es `null`,
  `duration_minutes`, deben ser enteros positivos);
- combates de otro torneo (pertenencia inconsistente ⇒ 502, no lista silenciosa);
- un `match_id` que aparezca dos veces en el payload: la asignación no podría
  resolverlo, así que no se lista.

**Match ya jugado: no se puede saber, y no se adivina.** El payload de Bracket
expone `stage_item_inputN_score` pero **ninguna bandera fiable de "terminado"**: en
el torneo 1 real todos los combates traen scores distintos de cero (p. ej. 5-5 o
10-7) sin que eso signifique nada. Por eso **no se filtra por score** y un combate
dudoso se incluye antes que inferir un estado incorrecto. Un pase pendiente sí se
descarta porque es un hecho del dato (no hay equipo), no una inferencia.

**Tatami ocupado.** `candidates` se puede consultar igualmente mientras el Tatami 1
tiene un combate activo: el match activo del **mismo torneo** se excluye de la
lista y se anuncia en `active_match_id`; el de otro torneo no se descuenta (los
`match_id` no son únicos entre torneos). `scoreboard_read` indica si el estado del
scoreboard se pudo leer: si no, la lista se devuelve igual y **no se inventa** ni
se omite nada por esa razón.

**Cómo asigna el operador** (dos llamadas separadas, nunca una sola que liste y
asigne):

```sh
curl -s 'http://bridge:8500/tatamis/1/candidates?tournament_id=7'
curl -s -X POST http://bridge:8500/tatamis/1/assign-match \
     -H 'Content-Type: application/json' \
     -d '{"tatami_id": 1, "tournament_id": 7, "match_id": 41}'
```

Si el tatami ya tiene combate, `assign-match` de **otro** match sigue devolviendo
**409** hasta que el scoreboard reciba `clear_match` (P2.3G); tras liberar, el
combate vuelve a la lista y `assign-match` vuelve a aceptar con una `session_id`
nueva. La selección sigue siendo del operador: la lista no asigna nada.

Nota de alcance: la lista es un `GET` sin estado; el estado vivo del Tatami 1 sigue
viviendo en memoria del scoreboard en el despliegue actual. La persistencia existe
desde P2.4B pero es **opt-in** (`SCOREBOARD_STATE_FILE`, ver
`scoreboard-adapter/README.md`) y **no** está activada en el Compose desplegado.

## Resultado del combate (P2.4D)

`POST /tatamis/{tatami_id}/result` publica en Bracket el resultado **cerrado** del
combate que el cliente identifica. Solo el Tatami 1: cualquier otro se rechaza con
400. El body identifica el combate, **no** lleva puntos ni ganador:

```json
{"tournament_id": 1, "match_id": 9001, "session_id": "…", "expected_revision": 4}
```

`expected_revision` es opcional. El Bridge lee el estado vivo del scoreboard, aplica
la puerta de resultado seguro, relee el combate en Bracket, y solo entonces escribe.
Respuestas:

- `200` con `status: "written"` (y `idempotent: true` si era un reintento del mismo
  resultado) — escrito y verificado.
- `200` con `status: "pending_manual"` — representable sin falsear datos no: no se
  escribió nada. `reason` indica por qué (`unsupported_result_mapping`,
  `tie_not_writable`, `not_finished`, `no_state`, …).
- `409` con `status: "conflict"` — otro operador cambió el combate, o ya hay otro
  resultado publicado, o la identidad no coincide. **No** se sobrescribe.
- `502` con `status: "failed"` — la escritura no se pudo verificar después; no se
  reintenta automáticamente.
- `400` tatami ≠ 1 · `503` sin credenciales de escritura configuradas · `401/403/404`
  propagados de Bracket (traducidos a error del Bridge cuando son de credencial).

## Publicación de resultados (P2.4D)

Implementación del **único** caso automático del ADR-001 (sección 14): victoria
natural por puntos. Archivos: `app/result_gate.py` (puerta),
`app/fingerprint.py` (huella), `app/result_store.py` (seguimiento en memoria),
`app/bracket_client.py` (`login`, `read_match`, `update_match`, `match_baseline`,
`match_write_body`, `post_verify`) y `app/main.py` (endpoint).

Puerta de resultado seguro — escribe **solo** si se cumple todo: hay estado, el
combate pertenece al torneo, `status == "finished"`, `winner_team_id` es uno de los
dos luchadores, `method == "points"`, los puntos difieren y el ganador es
naturalmente el lado con más puntos. Nunca se escriben `advantages`, `penalties`,
`method` ni un ganador artificial: el body del `PUT` son los seis campos de
`MatchBody` con los **puntos reales**.

`result_fingerprint` = `sha256("v1|tournament_id|match_id|session_id|revision|
winner_team_id|method|points_a|points_b|advantages_a|advantages_b|penalties_a|
penalties_b")`: determinista, sin tokens, sin secretos y sin nombres. Mismo
resultado ⇒ misma huella; cualquier cambio ⇒ huella distinta (y por tanto
`conflict`, nunca sobrescritura silenciosa).

Antes del `PUT` se relee el combate (`GET /stages`, `no_draft_rounds`) y se
preservan `round_id`, `court_id`, `custom_duration_minutes` y
`custom_margin_minutes`; se comprueba que los participantes siguen siendo los del
combate. Como Bracket no ofrece `ETag`/`If-Match`, el CAS es **lógico**: se compara
contra la línea base del intento anterior del mismo combate. Después del `PUT` se
vuelve a leer y se verifica marcador, ganador derivado y campos preservados: **un
200 no basta**.

Limitaciones declaradas (no se finge durabilidad):

- El seguimiento de intentos vive en **memoria del proceso** del Bridge: no es
  durable, no coordina réplicas y no sustituye al estado del scoreboard.
- Ventana de carrera entre la relectura y el `PUT`: otro escritor podría colarse
  (Bracket no es transaccional, DEF-03). La verificación posterior lo detecta, pero
  no puede revertirlo.
- La primera publicación **exige un combate sin marcador previo**; si ya hay
  puntuación ajena, responde `conflict` (`bracket_match_not_pristine`).

Credenciales: `BRACKET_WRITE_USERNAME` y `BRACKET_WRITE_PASSWORD` (separadas de las
del navegador). El Bridge canjea un JWT con `POST /token` y lo usa como `Bearer`
durante la escritura; **el token no se registra ni se devuelve**. Sin credenciales
el endpoint responde 503 y no intenta escribir. Las pruebas usan secretos
sintéticos.

## Traducción de resultados a Bracket (P2.4C)

Política documentada y justificada con el código real de Bracket en
`docs/adr/ADR-001-politica-traduccion-resultados-bjj.md`. El diseño preveía cuatro
opciones (A: escribir solo si el ganador declarado coincide con el lado de más
puntos; B: ampliar Bracket con ganador/método/ventajas/penalizaciones; C: scores
genéricos con metadata externa; D: score artificial, descartada). **P2.4D implementa
solo la opción A** (ver arriba); B, C y D siguen sin implementarse.

Nota de P2.4C.1 (hardening previo): en el submódulo Bracket (`47bc129`, publicado en
el fork propio) quedan corregidos **DEF-01** (alcance por torneo en las dependencias
de recurso) y **DEF-02** (`None` legítimos en el `UPDATE`). **DEF-03** (PUT no
transaccional) sigue pendiente. La imagen en producción todavía no incluye el
arreglo, así que la escritura de P2.4D **no puede habilitarse** allí.

Resumen operativo:

- Bracket solo representa **dos enteros**; el ganador es
  `score1 > score2` y un empate deja el árbol bloqueado (la ronda siguiente se
  queda sin rivales). No hay campo de método, ventajas, penalizaciones ni ganador
  explícito.
- Por eso **solo la victoria por puntos es traducible sin falsear datos**. Los
  casos de submission, decision, disqualification, walkover, referee_stoppage,
  empate con ventaja/penalización decisiva y `other` quedan en
  `pending_manual` y **no se escriben**. El caso de DQ es además peligroso:
  escribir los puntos reales declararía ganador al rival.
- El `PUT` reenvía `round_id`, `court_id`, `custom_duration_minutes` y
  `custom_margin_minutes` leídos del match actual: el body es un reemplazo completo.
  Con la imagen >= `47bc129` los `null` legítimos ya no rompen el `UPDATE` (DEF-02);
  con la imagen en producción (basada en `e6abd7d`) provocarían un `StatementError`.
- Idempotencia implementada en P2.4D: `result_fingerprint` derivado de
  `session_id`/`revision`/ganador/método/puntos/ventajas/penalizaciones, con estados
  `pending_manual | writing | written | failed | conflict`, y lectura previa del
  match para detectar cambios de otro operador antes de escribir.
- Los dos defectos del Bracket que bloqueaban la escritura están corregidos en
  `47bc129` (filtro de torneo que se perdía en las dependencias por un `and` de
  Python en `routes/util.py`, y el `StatementError` con `court_id`/`custom_*` a
  `null`), pero **no desplegados**: mientras producción no ejecute ese Bracket, la
  escritura automática no se habilita.

## Pruebas aisladas

Desde `bridge-api`, en un venv temporal fuera del repositorio:

```sh
python -m pip install -r requirements-dev.txt
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
```

La suite utiliza `httpx.MockTransport` para Bracket y `httpx.ASGITransport` para
la API en memoria. No necesita producción, servicios, contenedores ni builds.
`tests/test_p24d.py` añade 70 casos de la publicación de resultados: victoria A y B
por puntos, empate (con y sin ventajas), submission/decision/DQ/walkover/referee
stoppage/other, ganador que contradice los puntos, identidad equivocada, CAS con
marcador cambiado, idempotencia, verificación posterior, 401/403/404/timeout/5xx,
token fuera de los logs y de las respuestas, tatami ≠ 1, scoreboard inalcanzable y
una comprobación explícita de que **ningún transporte real se construye** durante
las pruebas (huella de que producción no se contacta).

El E2E de P2.4D se ejecutó aparte, fuera de la suite, contra una imagen de Bracket
construida **desde `47bc129`** (`bjj-bracket:p2.4d-test`), con PostgreSQL temporal,
red temporal y el scoreboard integrado en modo local: victoria 6–2 publicada y
verificada, reintento idempotente sin segundo `PUT`, submission/empate bloqueados,
marcador ajeno no sobrescrito, `PUT` a un combate de otro torneo con 404 y `null` en
`court_id`/`custom_*` aceptados. Nada de eso tocó producción.

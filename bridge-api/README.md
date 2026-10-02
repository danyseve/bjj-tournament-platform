# BJJ Bridge API — P2.3A / P2.3D

Capa de lectura y normalización entre Bracket y BJJ-Scoreboard. Desde P2.3D
entrega además la asignación normalizada al scoreboard integrado del **Tatami 1**
por HTTP; **sigue sin escribir resultados en Bracket**, al que solo hace `GET`.

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

### Resultados deshabilitados

`POST /tatamis/{tatami_id}/result` devuelve explícitamente **HTTP 501**, incluso
sin body o con el body legado. No invoca ningún transporte ni realiza escrituras.

## Pruebas aisladas

Desde `bridge-api`, en un venv temporal fuera del repositorio:

```sh
python -m pip install -r requirements-dev.txt
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
```

La suite utiliza `httpx.MockTransport` para Bracket y `httpx.ASGITransport` para
la API en memoria. No necesita producción, servicios, contenedores ni builds.

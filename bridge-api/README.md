# BJJ Bridge API — P2.3A

Capa de lectura y normalización entre Bracket y BJJ-Scoreboard. **No envía
combates al scoreboard ni escribe resultados en Bracket en esta fase.**

## Configuración de la URL

`BRACKET_API_URL` es la base completa configurada. El valor por defecto del
código es `http://bracket:8400/api` e incluye `/api`. El cliente usa esa base
(sin la barra final) y añade únicamente `/ping` o
`/tournaments/{tournament_id}/stages`; **nunca añade otro prefijo `/api`**.
No se cambia ninguna configuración de producción como parte de P2.3A.

La consulta de stages envía `no_draft_rounds=true`, tiene timeout de 10 segundos,
no sigue redirecciones y no intenta autenticarse. Un torneo no público puede
responder 401/403. Solo se realizan solicitudes GET.

## Endpoints

```text
GET  /health
GET  /health/bracket
POST /tatamis/{tatami_id}/assign-match
POST /tatamis/{tatami_id}/result
```

### Normalizar un combate

`POST /tatamis/1/assign-match` acepta **solo** estos tres campos:

```json
{"tatami_id": 1, "tournament_id": 7, "match_id": 40}
```

Los identificadores deben ser enteros positivos estrictos: no booleanos,
strings ni números decimales. Solo está permitido `tatami_id=1` y debe
coincidir con la ruta. Los campos adicionales (incluidos `red`, `blue`,
`category`, `duration_seconds` o el antiguo `tatami`) se rechazan.

Ejemplo de respuesta normalizada (identificadores/nombres ilustrativos):

```json
{
  "status": "normalized",
  "scoreboard_sent": false,
  "match": {
    "tournament_id": 7,
    "match_id": 40,
    "tatami_id": 1,
    "fighter_a": {"stage_item_input_id": 1, "team_id": 101, "name": "Ana", "club": null},
    "fighter_b": {"stage_item_input_id": 2, "team_id": 102, "name": "Bea", "club": null},
    "category": {"stage_item_id": 20, "name": "Adult / Blue / 70kg"},
    "duration_seconds": 300
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
- 409: combate draft, mismo competidor o mismo input.
- 502: fallo de transporte, otro error HTTP, JSON/estructura inválida,
  pertenencia inconsistente, input sin resolver o duración inválida.
- 504: timeout de Bracket.

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

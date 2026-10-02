# ADR-001 — Política de traducción de resultados BJJ hacia Bracket

- Estado: **propuesta** (recomendación técnica; la elección final tiene un punto de
  decisión de producto que se marca en la sección 13)
- Fecha: 2026-10-02
- Fase: **P2.4C** (diseño) → **P2.4D** (implementación del único caso automático,
  sin desplegar).
- Base: repo principal `1d981673b5eccc1c7eac82ba0f3198bdfec4480f`; submódulo
  `services/bracket` en `e6abd7d282850f9d13d9122494767d4dbcb139ef`.
- Alcance: documentación de diseño. No se escribe en Bracket, no se toca PostgreSQL,
  Compose, `.env`, nginx ni WireGuard, y no se añade ningún `PUT` de resultados.
- Actualización **P2.4C.1** (2026-10-02): **DEF-01 y DEF-02 corregidos** en el
  submódulo (`47bc129d467a9544edd835aacbd49b5879e8adf6`), publicados en el fork
  propio. DEF-03 y DEF-04 siguen abiertos. La corrección **no está desplegada**:
  la imagen en producción sigue construida sobre `e6abd7d`. Sigue **sin existir**
  escritura desde el Bridge.
- Actualización **P2.4D** (2026-10-02): **implementado** el primer flujo de escritura
  Bridge → Bracket, limitado al **caso A** (victoria natural por puntos). Gate,
  fingerprint, CAS lógico, verificación posterior, idempotencia y pruebas están en
  la sección 14. **No desplegado**: producción sigue ejecutando la imagen basada en
  `e6abd7d` y el Bridge nuevo no está publicado.

## 1. Contexto

El scoreboard integrado del Tatami 1 ya sabe cerrar un combate (P2.3F/P2.3G) y
sobrevivir a un reinicio (P2.4B). Bracket es la fuente de verdad del torneo:
calendario, árbol de rondas y clasificaciones. Falta decidir **si** y **cómo** un
resultado BJJ puede llegar a Bracket sin falsear datos.

El endpoint de escritura del Bridge ya no está deshabilitado: desde P2.4D,
`POST /tatamis/{id}/result` publica **únicamente** el caso A (sección 14) y responde
`pending_manual` o `conflict`, sin escribir, para todo lo demás.

## 2. Modelo real de Bracket (evidencia en código)

Ficheros citados bajo `services/bracket/backend/bracket/` y
`services/bracket/frontend/src/`.

**Endpoint de actualización de Match**

- `routes/matches.py:156` — `PUT /tournaments/{tournament_id}/matches/{match_id}`.
- Handler `routes/matches.py:157-185`, en este orden estricto:
  1. `user_authenticated_for_tournament` (JWT + acceso al club) — `routes/matches.py:161`.
  2. `disallow_archived_tournament` — torneo archivado ⇒ **400**.
  3. `match_dependency` — carga el match por id (`routes/util.py:62-75`).
  4. `check_foreign_keys_belong_to_tournament(match_body, tournament_id)`
     (`routes/matches.py:165`) — valida `round_id` y `court_id`.
  5. `sql_update_match(match_id, match_body, tournament)` (`:168`).
  6. `get_round_by_id` → `get_stage_item` → `recalculate_ranking_for_stage_item`
     (`:170-172`).
  7. Si cambió la duración/margen personalizados: `reorder_matches_for_court` (`:174-180`).
  8. Si el stage item es `SINGLE_ELIMINATION`: propagación de ganador (`:182-183`).
- **No hay transacción de request**: `sql_update_match` ejecuta su `UPDATE` sin
  `database.transaction()` y el handler tampoco lo abre, así que cada sentencia
  autocommitea. Un fallo en los pasos 6-8 deja la escritura ya aplicada
  (aplicación parcial).

**Campos aceptados (`MatchBody`)**

`models/db/match.py:89-95` — el body tiene **exactamente 6 campos**:

| campo | tipo | obligatorio |
|---|---|---|
| `round_id` | `RoundId` | sí |
| `stage_item_input1_score` | `int` | no (default 0) |
| `stage_item_input2_score` | `int` | no (default 0) |
| `court_id` | `CourtId \| None` | no (default `None`) |
| `custom_duration_minutes` | `int \| None` | no (default `None`) |
| `custom_margin_minutes` | `int \| None` | no (default `None`) |

No existe campo de ganador, ni de método, ni de ventajas/penalizaciones. El body
se aplica como **reemplazo completo** de esos campos, no como parche:
`sql/matches.py:85-118` fija en el `SET` `round_id`, ambos scores, `court_id`,
`custom_duration_minutes`, `custom_margin_minutes` y recalcula
`duration_minutes`/`margin_minutes` (desde el torneo si el valor personalizado es
`None`).

**Cómo determina Bracket el ganador**

`models/db/match.py:46-52` — `Match.get_winner()` devuelve el input ganador solo si
`stage_item_input1_score > stage_item_input2_score` (o el inverso); **empate ⇒
`None`, no hay ganador**.

La UI usa la misma regla: `frontend/src/components/brackets/match.tsx:66`,
`pages/tournaments/[id]/dashboard/index.tsx:32` y `results.tsx:46`.

**Cuándo se propaga a la ronda siguiente**

`routes/matches.py:182-183` — solo si `stage_item.type == SINGLE_ELIMINATION`, vía
`logic/ranking/elimination.py:75-86` → `get_inputs_to_update_in_subsequent_elimination_rounds`
(`:13-72`), que recorre las rondas con `id` mayor (`:30`) y coloca
`get_winner()` en `stage_item_input1_id`/`stage_item_input2_id` de los matches que
declaran `stage_item_inputN_winner_from_match_id`. Si el ganador es `None`
(empate), el input se pone a `NULL` (`:56`) y **el árbol se queda bloqueado**.

**Cómo recalcula ranking/estadísticas**

`logic/ranking/calculation.py:102-121` → `determine_ranking_for_stage_item`
(`:63-91`): recorre los matches **no borrador** de tipo definitivo y, por cada
lado (`:18-60`), cuenta victoria/empate/derrota comparando **los scores**
(`:27-41`). Con `add_score_points` el score crudo se suma a los puntos
(`:43-46`); en SWISS se ajusta un ELO con `K=32` (`:14`, `:53-57`). Es decir: **todo
el histórico, la clasificación y el ELO derivan del par de enteros**.

**Autorización**

`routes/auth.py:101-113` — `user_authenticated_for_tournament`: JWT válido
(HS256, `config.py:39`) **y** el usuario pertenece a un club dueño del torneo
(`sql/users.py:13-21`, `users_x_clubs ⋈ tournaments`). Si falla: **401**.
`routes/util.py:110-119` — `disallow_archived_tournament`: estado `ARCHIVED` ⇒ **400**
(`"Can't update archived tournament"`).

**Pertenencia al torneo**

`sql/validation.py:108-126` — `check_foreign_keys_belong_to_tournament` valida
cada id tipado del body contra el torneo de la ruta: `RoundId` ⇒
`check_round_belongs_to_tournament` (`:60-94`), `CourtId` ⇒
`check_court_belongs_to_tournament` (`:97+`). Con `MatchBody` esto cubre `round_id`
y `court_id`.

**Restricciones del propio endpoint que condicionan un futuro PUT**

- El `SET` nombra `:court_id`, `:custom_duration_minutes`, `:custom_margin_minutes`
  mientras los valores salen de `**match.model_dump()`
  (`sql/matches.py:115-118`), y `BaseModelORM.model_dump` fuerza
  `exclude_none=True` (`models/db/shared.py:9-11`). Si esos tres campos van a
  `None`, **la sentencia revienta** con
  `StatementError: A value is required for bind parameter 'court_id'` ⇒ **500**.
  Verificado de forma sintética (sección 11, DEF-02).
- Consecuencia: para escribir hay que enviar siempre `court_id`,
  `custom_duration_minutes` y `custom_margin_minutes` con valor no nulo. Un match
  **sin pista asignada no se puede actualizar** por esta vía.

## 3. Resultado canónico BJJ (entrada, sin cambios)

`{match_id, tournament_id, fighter_a/b, points, advantages, penalties,
winner_team_id, method}` con
`method ∈ {points, submission, decision, disqualification, walkover,
referee_stoppage, other}`.

Bracket solo puede representar **dos enteros** (y `round_id`/`court_id`). Ventajas,
penalizaciones, método y ganador explícito **no tienen sitio** en el modelo actual.

## 4. Matriz de casos

`s1 > s2` significa "el ganador que sale de Bracket coincide con `winner_team_id`
si se escriben los puntos como scores".

| # | Caso | Scoreboard sabe | Bracket puede representar | Bracket NO puede | ¿win == s1>s2? | ¿Score artificial? | Riesgo | Clasificación |
|---|---|---|---|---|---|---|---|---|
| A | Victoria por puntos | points distintos, ganador por puntos | sí: scores = puntos, orden real | vantajas/penalizaciones | sí | no | bajo (los scores dejan de ser "genéricos" y pasan a ser puntos BJJ) | **segura** |
| B | Empate en puntos + ventaja decisiva | empate a puntos, ganador por ventajas | nada fiel: scores iguales ⇒ sin ganador y árbol bloqueado | la ventaja como criterio | no | sí (p.ej. 1-0) | alto: score falso + propagación forzada | **ambigua** (segura solo con dato artificial) |
| C | Empate en puntos + penalización decisiva | empate a puntos, ganador por penalizaciones | igual que B | el criterio de penalizaciones | no | sí | alto, idéntico a B | **ambigua** |
| D | Submission | ganador por sumisión, típicamente 0-0 | nada fiel: sin diferencia de puntos | el método, la sumisión | no | sí (1-0 convencional) | alto: el histórico dirá "ganó 1-0", sin método | **imposible sin alterar** |
| E | Decision | ganador por decisión arbitral, a menudo empate | nada fiel | el método y el criterio | no | sí | alto | **imposible sin alterar** |
| F | Disqualification | ganador puede tener **menos** puntos | representable solo invirtiendo el marcador real | el método y la causa | **no, al revés** | sí | **crítico**: Bracket declararía ganador al rival | **imposible y peligrosa** |
| G | Walkover | combate no disputado | no hay combate que escribir; el modelo no describe un "pase directo" | el walkover | n/a | sí (combate ficticio) | alto: crea un combate que no existió | **imposible sin alterar** |
| H | Referee_stoppage | ganador por parada médica/arbitral | nada fiel | el método | no | sí | alto | **imposible sin alterar** |
| I | Other | método no tipado | nada | todo | desconocido | — | indeterminado | **bloqueado por definición** |

Lectura de la matriz: **solo el caso A es traducible sin tocar datos**. Los casos
B/C necesitan un desempate que Bracket no entiende; D/E/F/G/H/I no son
representables porque el modelo solo compara enteros, y F además **invertiría** el
ganador si se escribieran los puntos reales.

## 5. Regla de oro

> No se falsea una puntuación para forzar un ganador salvo decisión explícita,
> documentada y reversible.

Efectos concretos de falsear (todos verificables en el código):

- **Histórico / UI**: la pantalla de resultados muestra el marcador como si fuera
  el resultado real (`frontend/src/components/brackets/match.tsx:66`). Un
  submission "1-0" queda como un combate ganado 1-0 para siempre.
- **Clasificación y estadísticas**: `determine_ranking_for_stage_item`
  (`logic/ranking/calculation.py:63-91`) cuenta victorias y puntos desde los
  scores, y `add_score_points` (`:43-46`) suma el score crudo. Un score inventado
  contamina clasificación y desempates.
- **ELO SWISS**: `:53-57` calcula la expectativa con los ELO y el resultado real;
  un ganador forzado desplaza el ELO de todos los implicados.
- **Estructura del árbol**: un empate deja `get_winner()` en `None`, y la
  propagación vacía el input de la ronda siguiente
  (`logic/ranking/elimination.py:46-56`): la ronda siguiente queda sin rivales
  hasta que alguien lo arregle a mano.
- **Futuras integraciones**: cualquier consumidor del API (pantallas, exportaciones,
  estadísticas externas, una futura app móvil) hereda el dato falso sin poder
  distinguirlo, porque **Bracket no tiene ningún campo donde marcar "score
  sintético"**.
- **Auditoría**: sin campo de marca ni historial de cambios, la manipulación es
  indistinguible del resultado real. Revertirla exige reconstruir el resultado
  desde las notas del operador.

Casos de manipulación evaluados expresamente: `submission 0-0 → 1-0`,
`decision con score empatado → +1`, `DQ con el ganador por debajo en puntos →
invertir`, `ventaja como punto ficticio → +1`. Los cuatro falsean el histórico; el
de DQ, además, produce el ganador contrario.

## 6. Opciones de política

| | Opción A: escribir solo cuando el ganador coincide con `s1 > s2` | Opción B: ampliar Bracket (winner/method/advantages/penalties) | Opción C: Bracket con scores genéricos + metadata BJJ externa | Opción D: codificar el ganador con score artificial |
|---|---|---|---|---|
| Qué implica | PUT solo en el caso A; el resto queda pendiente/manual | fork del submódulo: body nuevo, migración de esquema, propagación, UI | Bracket recibe solo lo que sabe representar (o nada); el Bridge guarda el resultado BJJ y su estado | scores inventados según convención |
| Complejidad | baja (un endpoint + validación + lectura previa) | alta (modelo + migración + frontend + pruebas de Bracket) | media (almacén de mapeo + estados + operación manual) | baja |
| Riesgo de dato falso | **nulo** | nulo | nulo | **alto y permanente** |
| Consistencia con Bracket | total (la UI y el árbol ya funcionan así) | total, y además fiel | parcial: la UI puede mostrar el combate sin marcador | aparente, falsa |
| Reversibilidad | trivial (borrar el mapeo) | media (migración inversa) | trivial | muy costosa (dato ya mezclado con el real) |
| Impacto en Bracket | nulo | alto, y hay que mantener el fork | nulo | nulo en código, grave en datos |
| Impacto en UI/histórico | la UI muestra el marcador real de puntos | UI puede mostrar método/ventajas | la UI sigue sin mostrar el resultado BJJ | UI muestra datos inventados |
| Cobertura | solo victorias por puntos | completa | completa en el Bridge, parcial en Bracket | completa en apariencia |

## 7. Seguridad del PUT (para una fase futura)

Payload conceptual, **no enviado**: el body debe replicar el contrato completo de
`MatchBody` porque es un reemplazo, no un parche.

Campos a **leer antes** y reenviar tal cual para no destruirlos:

- `round_id` (obligatorio; sale del match actual — `routes/matches.py:170` ya usa
  `match.round_id`, así que debe ser el mismo).
- `court_id` — admite `None` desde P2.4C.1 (DEF-02 corregido): `None` ⇒ SQL NULL,
  así que se puede reenviar el valor actual del match sin inventar pistas.
- `custom_duration_minutes` y `custom_margin_minutes` — admiten `None` desde
  P2.4C.1: `None` ⇒ SQL NULL, que es el significado real "sin duración
  personalizada"; el match pasa a usar la duración/margen del torneo
  (`sql/matches.py:100-109`).
- Los scores actuales (para detectar cambios de terceros antes de escribir).

No hace falta reenviar `position_in_schedule`, `start_time`, `created` ni
`stage_item_inputN_id`: no están en el `SET`. Ojo: la propagación de eliminación sí
puede **tocar** `stage_item_input1_id/2_id` de rondas posteriores
(`logic/ranking/elimination.py:83-86`); es el comportamiento esperado.

Campos extra en el body **no** rompen la petición (pydantic los ignora:
`BaseModelORM` no declara `extra="forbid"`).

## 8. Autorización y prefijo

- Prefijo efectivo: `API_PREFIX=/api` ⇒ `PUT /api/tournaments/{tid}/matches/{mid}`.
- Login: `POST /api/token` (`routes/auth.py:170`), `OAuth2PasswordRequestForm`
  (`username`/`password`) ⇒ `{access_token, token_type, user_id}`. JWT HS256 con
  `JWT_SECRET`, `exp` a 7 días, clave `user` = email (`routes/auth.py:25-26,65-69`).
- Para escribir: `Authorization: Bearer <jwt>` **y** el usuario en un club dueño
  del torneo (`routes/auth.py:101-113`) ⇒ si no, 401.
- Torneo archivado ⇒ 400 (`routes/util.py:110-119`).
- Lecturas: existen endpoints públicos con `user_authenticated_or_public_dashboard`
  (`routes/stages.py:41-51`), que es lo que usa hoy el Bridge
  (`bridge-api/app/bracket_client.py:16-39`, sin cabecera de autorización).

## 9. Idempotencia (diseñada aquí; implementada en P2.4D, sección 14)

Clave interna implementada en P2.4D, idéntica a la propuesta, derivada del estado
ya persistido en P2.4B:

```
result_fingerprint = sha256(
  "v1|{tournament_id}|{match_id}|{session_id}|{revision}|"
  "{winner_team_id}|{method}|{points_a}|{points_b}|{advantages_a}|{advantages_b}|"
  "{penalties_a}|{penalties_b}"
)
```

Se guarda un registro de mapeo por `match_id` con estados
`none → pending_manual | writing | written | failed | conflict`, más
`fingerprint`, `attempted_at`, `written_at` y la respuesta upstream. Reglas:

- Un `fingerprint` ya en estado `written` **no se reescribe** (replay ⇒ no-op).
- Si el resultado final cambia (debería ser imposible tras `finished`, pero el
  `clear_match` y una nueva asignación pueden reabrir el combate), el fingerprint
  cambia y el registro pasa a `pending_manual`: nada se sobrescribe solo.
- Antes de escribir: leer el match y comparar con los scores esperados
  (compare-and-swap lógico, porque Bracket no ofrece `ETag`/`If-Match`).
  Si no coinciden ⇒ `conflict`, sin escribir.

## 10. Errores y rollback (diseñados aquí; implementados en P2.4D, sección 14)

Principio: **un fallo upstream nunca se convierte en éxito local**. El scoreboard
conserva su estado `finished`; lo que cambia es el estado del mapeo.

| Respuesta upstream | Significado | Acción |
|---|---|---|
| 401 / 403 | token o permisos | no reintentar; `failed` + aviso operativo (token/rol a revisar) |
| 400 | torneo archivado | `failed`; requiere desarchivar o decidir no escribir |
| 404 | match o ruta inexistente | `failed`; el mapeo quedó obsoleto, revisión manual |
| 409 | no existe en este PUT; el conflicto solo se detecta por lectura previa | `conflict`, no escribir |
| 422 | body inválido | `failed`; error de programación, no reintentar en bucle |
| 5xx | estado **desconocido** (el `UPDATE` pudo haber commiteado antes de fallar) | leer de vuelta; si el marcador es el esperado ⇒ `written`, si no ⇒ un reintento y luego `failed` |
| Timeout | estado desconocido | igual que 5xx |
| Respuesta inválida (no JSON / forma inesperada) | estado desconocido | igual que 5xx; nunca asumir éxito |

Nunca auto-"reparar" hacia atrás (por ejemplo, "deshacer" con un segundo PUT con
los scores antiguos): un PUT a ciegas puede pisar el trabajo de otro operador.

## 11. Defectos conocidos

- **DEF-01 — `and` de Python en las dependencias (heredado de upstream,
  `f03bf6c` "Various bugfixes (#77)"). CORREGIDO en P2.4C.1** (submódulo
  `47bc129`): `round_dependency` y `match_dependency` acotan por la cadena
  `rounds.stage_item_id → stage_items.stage_id → stages.tournament_id` (ni
  `matches` ni `rounds` tienen columna `tournament_id`) y `team_dependency` por
  `teams.tournament_id`, con `&` en lugar de `and`. Análisis original (estado
  previo al arreglo):
  `routes/util.py:24` (`rounds.c.id == round_id and matches.c.tournament_id ==
  tournament_id`), `:67` (`match_dependency`) y `:84` (`team_dependency`). La
  evaluación de SQLAlchemy hace que `bool(<clause>)` sea `False`, así que `A and B`
  devuelve **A**: el filtro de torneo se descarta en silencio. Verificado con un
  test sintético usando SQLAlchemy 2.0.44 (la versión de `pyproject.toml:26`):

  ```
  A match_dependency con and  -> SELECT matches.id, matches.tournament_id FROM matches WHERE matches.id = :id_1
  B match_dependency con &    -> SELECT ... WHERE matches.id = :id_1 AND matches.tournament_id = :tournament_id_1
  C round_dependency con and  -> SELECT rounds.id, rounds.tournament_id FROM rounds WHERE rounds.id = :id_1
  D team_dependency con and   -> SELECT teams.id, teams.tournament_id FROM teams WHERE teams.id = :id_1
  E bool(clausula) -> False
  ```

  - **Alcance real**: la búsqueda del recurso pierde el filtro de torneo, pero
    **no provoca error** (la referencia a `matches.c.tournament_id` desaparece
    antes de compilar) ni rompe el PUT.
  - **¿Afecta al PUT de match?** Sí, en el alcance: `match_dependency` puede
    devolver un match de otro torneo con el mismo id de ruta. La escritura va
    después por `WHERE matches.id = :match_id` (`sql/matches.py:96`) y sin filtro
    de torneo, así que el PUT de `{tid}` podría modificar un match de otro torneo.
  - **¿Invalida la comprobación de pertenencia/autorización?** No destruye la
    autorización (JWT + club es independiente, `routes/auth.py:101`), ni la
    validación de `round_id`/`court_id` (`sql/validation.py:108`). Lo que se pierde
    es el **alcance por torneo del recurso**, no el control de acceso. Aun así,
    es un motivo fuerte para arreglarlo (o para re-validar el `tournament_id` del
    match en el Bridge) antes de habilitar escrituras.
- **DEF-02 — `StatementError` si `court_id`/`custom_*` van a `None`. CORREGIDO en
  P2.4C.1** (submódulo `47bc129`): `sql_update_match` declara los parámetros de
  bind de forma explícita, así que `None` llega como SQL NULL sin inventar ceros.
  Análisis original:
  `models/db/shared.py:9-11` (exclude_none) + `sql/matches.py:85-118` (SET con
  bind params nombrados). Verificado:
  `model_dump() con court_id=None -> ['round_id', 'stage_item_input1_score',
  'stage_item_input2_score']` y al ejecutar la sentencia con esos valores:
  `StatementError: A value is required for bind parameter 'court_id'`. ⇒ 500 y
  ningún match sin pista puede actualizarse por esta vía.
- **DEF-03 — el PUT no es transaccional. SIGUE PENDIENTE tras P2.4C.1** (el
  alcance de esa fase no lo requería). La actualización commitea antes de
  recalcular la clasificación y de propagar el ganador (`routes/matches.py:168-183`,
  sin `database.transaction()`): un fallo posterior deja marcador escrito y
  clasificación/árbol sin actualizar.
- **DEF-04 — el modelo no admite ganador explícito ni método** (sección 2): es la
  causa raíz de los casos imposibles de la matriz.

## 12. Recomendación técnica

1. **Automatizar solo el caso A** (victoria por puntos con `s1 != s2` y
   `winner_team_id` igual al lado con más puntos), con relectura previa
   (compare-and-swap) y verificación posterior del marcador. **HECHO en P2.4D**
   (sección 14), sin desplegar.
2. **Bloquear explícitamente** B, C, D, E, F, G, H e I: el Bridge debe responder
   `pending_manual` con motivo, y **no** escribir nada. Con especial énfasis en F
   (riesgo de invertir el ganador). **HECHO en P2.4D** (sección 14).
3. **Ampliar Bracket solo si el producto lo exige** (opción B, fork del submódulo):
   es la única vía para representar método, ventajas, penalizaciones y ganador
   explícito con fidelidad. Antes de eso, la metadata BJJ vive fuera de Bracket
   (opción C), en el Bridge.
4. **Descartar la opción D** mientras no exista un campo donde marcar el dato como
   sintético: hoy un score artificial es indistinguible del real.
5. ~~Arreglar DEF-01 y DEF-02 antes de habilitar cualquier escritura~~ **HECHO en
   P2.4C.1** (submódulo `47bc129`, publicado en el fork propio): el PUT acepta ya
   `None` legítimos y el recurso queda acotado al torneo de la ruta. La corrección
   **no está desplegada** (la imagen en producción sigue en `e6abd7d`), así que no
   debe habilitarse una escritura real desde el Bridge hasta reconstruir la imagen.
6. **Prerrequisitos operativos** para P2.4D: el combate debe estar `finished` con
   `winner_team_id` y método; debe tener `court_id` asignado; el PUT debe ir con
   `round_id`, `court_id`, `custom_duration_minutes` y `custom_margin_minutes`
   leídos del match actual.

## 13. Decisión pendiente de producto

La recomendación anterior es técnica, pero dos puntos son de producto y **no se
deciden en este ADR**:

1. **¿Se acepta que el marcador de Bracket sea el marcador BJJ de puntos**, con la
   pérdida de ventajas/penalizaciones/método en la vista pública? (Afecta a lo que
   el público ve del torneo.)
2. **¿Se amplía Bracket (fork) para representar el resultado completo?** Implica
   mantener un fork, migración de esquema y cambios de UI.

Hasta que esas dos preguntas tengan respuesta, la política por defecto es la más
conservadora: **solo caso A automático, el resto manual y bloqueado**.

Estado tras P2.4C.1: el gate de hardening queda cerrado (DEF-01 y DEF-02
corregidos y publicados).

Estado tras P2.4D: **implementado** el flujo del caso A —publicación automática de
una victoria natural por puntos, con gate de resultado seguro, fingerprint
versionado, relectura previa con compare-and-swap lógico, verificación posterior e
idempotencia— y **sigue sin desplegarse**: la imagen de Bracket en producción es la
construida sobre `e6abd7d` (sin DEF-01/DEF-02), el Bridge nuevo no está publicado y
no se ha escrito nada contra el Bracket productivo. Mientras producción no ejecute
un Bracket >= `47bc129`, la escritura no puede habilitarse.

## 14. Implementación P2.4D (caso A, sin desplegar)

Alcance: solo `bridge-api` (repo principal). No se toca el submódulo Bracket, ni
Compose, ni `.env`, ni nginx, ni WireGuard, ni el scoreboard, ni el modelo BJJ.

### 14.1 Automático vs manual

| Resultado BJJ | Decisión | Motivo devuelto |
|---|---|---|
| Victoria por puntos, `points_a != points_b`, ganador = lado con más puntos | **escribe** | — |
| Empate en puntos (con o sin ventajas) | `pending_manual` | `tie_not_writable` |
| `method` distinto de `points` | `pending_manual` | `unsupported_result_mapping` |
| Ganador declarado que contradice los puntos | `conflict` | `winner_contradicts_points` |
| `winner_team_id` que no es uno de los dos participantes | `conflict` | `invalid_winner` |
| Scoreboard no `finished` | `pending_manual` | `not_finished` |
| Sin estado de scoreboard | `pending_manual` | `no_state` |
| Identidad distinta de la esperada | `conflict` | `tournament_mismatch` / `match_mismatch` / `session_mismatch` / `revision_mismatch` |
| Bracket ya tiene marcador ajeno en el combate | `conflict` | `bracket_match_not_pristine` |
| Bracket cambió desde el intento anterior | `conflict` | `bracket_scores_changed` |
| Ese combate ya tiene otro resultado publicado | `conflict` | `already_written_different_result` |
| Participantes de Bracket ≠ luchadores del combate | `conflict` | `participants_mismatch` |
| Scoreboard ilegible / estado inválido | `failed` | `invalid_scoreboard_state` |
| Verificación posterior con diferencias | `failed` | `post_verify_*` |

Nunca se escriben `advantages`, `penalties`, `method` ni un `winner` artificial: el
body del PUT son los seis campos de `MatchBody` y los scores son los puntos reales.

### 14.2 Fingerprint

`sha256("v1|tournament_id|match_id|session_id|revision|winner_team_id|method|points_a|points_b|advantages_a|advantages_b|penalties_a|penalties_b")`.
Determinista, sin tokens, sin secretos y sin nombres: mismo resultado ⇒ mismo
fingerprint; cualquier cambio ⇒ fingerprint distinto.

### 14.3 Lectura previa y CAS lógico

Antes del PUT se relee el combate desde Bracket (vía `GET /stages`, `no_draft_rounds`)
y se conservan `round_id`, `court_id`, `custom_duration_minutes`,
`custom_margin_minutes` y los participantes. Bracket **no** ofrece `ETag`/`If-Match`,
así que el CAS es lógico: se compara el marcador contra la línea base registrada en
el intento anterior del mismo combate. Ventana de carrera residual: entre la
relectura y el PUT otro escritor podría cambiar el marcador; el PUT lo sobrescribiría
sin detectarlo (Bracket no es transaccional — DEF-03). La verificación posterior sí
detectaría un resultado distinto al esperado.

### 14.4 Verificación posterior

Un HTTP 200 no basta: tras el PUT se vuelve a leer y se comprueba marcador,
ganador derivado, `round_id`, `court_id` y duraciones/márgenes. Si algo no cuadra se
devuelve `failed` con motivo `post_verify_*` y **no** se reintenta el PUT.

### 14.5 Idempotencia

Mismo fingerprint ya `written` ⇒ se devuelve éxito idempotente (`idempotent: true`) y
**no** hay segundo PUT. Mismo combate con fingerprint distinto ⇒ `conflict`
(`already_written_different_result`): nunca se sobrescribe un resultado anterior de
forma automática, ni siquiera desde una sesión nueva.

### 14.6 Estado de publicación

El seguimiento (`pending_manual`, `writing`, `written`, `failed`, `conflict`) vive en
**memoria del proceso** del Bridge: es deliberado y está documentado en
`bridge-api/README.md`. No sustituye al estado vivo del scoreboard, no es durable y
no coordina dos réplicas.

### 14.7 DEF-03

Sigue sin arreglarse (fuera de alcance de P2.4D). Riesgo: el UPDATE de Bracket puede
aplicarse en parte; la verificación posterior lo detecta pero no puede revertirlo de
forma segura, así que se marca `failed` y no se hace un segundo PUT automático.

### 14.8 Pruebas

70 casos en `bridge-api/tests/test_p24d.py` (victoria A/B, empates, métodos no
soportados, contradicción de ganador, identidad equivocada, CAS, idempotencia,
verificación posterior, 401/403/404/timeout/5xx, token fuera de logs y respuestas,
tatami ≠ 1, scoreboard inalcanzable y "nunca se contacta producción"), más un E2E
aislado contra una imagen de Bracket **construida desde `47bc129`**, con PostgreSQL
temporal, red temporal y el scoreboard integrado. Nada de eso toca producción.

### 14.9 Habilitación

La escritura automática requiere: (1) producción ejecutando un Bracket >= `47bc129`,
(2) el Bridge desplegado con credenciales de escritura propias, y (3) la decisión de
producto de la sección 13 resuelta. Ninguna de las tres se ha ejecutado aquí.

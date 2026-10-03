# 20 — Acción UI «Generar cuadro» (P2.8B · F2C)

Estado: **P2.8B F2C — UI BRACKET GENERATION VALIDATED ✅** (2026-10-03). La deuda funcional
**UI AUTO-SEED GAP ⚠️** documentada en `docs/19-bye-aware-seeding-and-scheduling.md` §6bis queda
**RESOLVED**: existe una acción **explícita** en la UI estándar (`Generate bracket` / «Generar cuadro»)
que aplica el seeding *bye-aware* de F2 (`distribute_entrants_into_slots`) al cuadro ya creado, sin
efectos laterales automáticos y sin re-seedear nada a espaldas del operador.

- Fork `danyseve/bracket` (`master`): HEAD **`886ff13`** (`8ec816b` → `924db61` → `c6458d0` → `cbab68a` → `886ff13`).
- Imagen productiva: `danyseve1/bracket-bjj:886ff13-r1` (id `sha256:2f074072…`, label
  `BRACKET_UPSTREAM_COMMIT=886ff13ad402f05b350dfdc3aa68b401da63cce6`, `RECIPE_REVISION=r1`).
  Rollback: `cbab68a-r1` (F2C sin microfix i18n) y `8ec816b-r1` (F2 pre-F2C). **`latest` intacto.**
- Desplegado **solo** el servicio `bracket`; `WRITE=false`; Tatami 1 `state=null`.
- Ensayo real de cierre: `tournament_id=10` («Torneo De pruebas REHEARSAL F2C»), `stage_item_id=49`
  (§10), validado por SQL read-only **y** visualmente por el operador (§11).
- Fuera de alcance: **F3 no iniciada** (§15).

Continúa a `docs/19` (§6bis, deuda ahora resuelta) y a `docs/18-bracket-topology-domain-model.md`
(§11 y §14bis). Registra lo implementado con evidencia `archivo:línea`.

---

## 1. Problema original — UI AUTO-SEED GAP ⚠️

El reparto *bye-aware* de F2 (`docs/19` §2) corre **solo cuando los inscritos existen al construir el
cuadro**. Dos caminos de alta reales:

| Camino | Comportamiento antes de F2C |
|---|---|
| Importador / *create-with-inputs* | ✅ el cuadro se construye con los inscritos ya repartidos → el seeding bye-aware se aplica solo |
| **UI estándar** | ⚠️ crea el `stage_item` con inputs **vacíos** (`routes/stage_items.py`, `utils/db_init.py`) y los equipos se asignan **después** (`routes/stage_item_inputs.py`) |

En el camino de UI estándar, la primera ronda empareja slots **consecutivos** en el momento de construir
(`logic/scheduling/elimination.py`, `determine_matches_first_round`), de modo que los huecos acababan
**dos a dos en el mismo combate**: byes concentrados y combates *ghost* `∅/∅`. El resolver estructural
de P2.8A seguía salvando el avance (ningún equipo quedaba bloqueado), pero **el reparto no era el nuevo**.

`docs/19` §6bis dejó tres opciones: **(A)** endpoint implícito `Seed bracket`, **(B)** auto-seed al
completar las inscripciones, **(C)** acción UI explícita `Generate bracket`. El operador eligió **C**.

---

## 2. Decisión: acción explícita, sin auto-reseed

**C**. Motivos de diseño, no negociables:

- **Explícita**: la dispara el operador; nada la ejecuta sola.
- **Reproducible**: misma entrada → mismo resultado (reutiliza el motor puro de F2, determinista).
- **Sin heurísticas ocultas**: añadir/editar/quitar un equipo o abrir la página **no** genera nada
  (`NO AUTO-RESEED`). No hay *trigger* por estado "cuadro completo".
- **Sin efectos silenciosos**: si el cuadro ya tiene actividad (scores, ganador, planning) la acción se
  **rechaza** con un gate (§5) en lugar de reescribir.
- **No borra ni resetea** nada: solo reasigna `team_id` de slots (y libera los que quedan vacíos).

---

## 3. Ciclo de vida: antes vs. ahora

| Evento | Antes de F2C | Con F2C |
|---|---|---|
| Crear `stage_item` (UI) | inputs vacíos, partidos construidos ya | igual (sin cambio) |
| Añadir/quitar equipo | reasigna el slot, no reordena | igual: **no** dispara nada |
| Editar un entrant | no dispara nada | igual: **no** dispara nada |
| Abrir la página del cuadro | no dispara nada | igual: **no** dispara nada |
| **Pulsar «Generar cuadro»** | — | reparte los inscritos *bye-aware* (2ª ejecución → `changed=false`) |

---

## 4. Endpoint `Generate bracket`

```
POST /tournaments/{tournament_id}/stage_items/{stage_item_id}/generate_bracket
```

- Ruta: `backend/bracket/routes/stage_items.py:248`; dependencias `user_authenticated_for_tournament`
  y `disallow_archived_tournament` (torneo archivado → **400**).
- Respuesta: `GenerateBracketResponse` (`backend/bracket/routes/models.py:117`):

```json
{"stage_item_id": 49, "entrant_count": 6, "bracket_size": 8, "bye_count": 2, "ghost_count": 0, "changed": true}
```

**Lógica pura reutilizada, sin duplicar el motor** (`backend/bracket/logic/scheduling/generation.py`):

| Símbolo | Línea | Papel |
|---|---|---|
| `BracketGenerationBlocker` | `:41` | códigos de gate (§5) |
| `BracketGenerationPlan` | `:55` | plan inmutable (`entrant_count`, `bracket_size`, `ghost_count`, `changes`, `.changed`) |
| `count_entrants` | `:138` | nº de inscritos reales del stage item |
| `plan_bracket_generation` | `:143` | **puro**: calcula el plan, no escribe |
| `generate_bracket_for_stage_item` | `:181` | aplica el plan en **una transacción con rollback total** |

- Reutiliza `distribute_entrants_into_slots` (`logic/scheduling/seeding.py`, F2) y vuelve a ejecutar el
  resolver estructural P2.8A.
- **Invariante respetada** (F2 §2): `N` inscritos → `B` = menor potencia de 2 ≥ `N`
  (2→2, 3→4, 4→4, 5→8, 6→8, 7→8, 8→8, 9→16). **No se sobredimensiona** el cuadro.
- Escritura en **dos fases** (primero liberar los slots que cambian, luego asignar) porque
  `UNIQUE(stage_item_id, team_id)` impide el intercambio directo de dos slots.
- `ghost_count` se reporta y es **0** tras el reparto correcto (no quedan combates `∅/∅`).

---

## 5. Safety gates

Con actividad en el cuadro la acción **no escribe**: responde **409** `generate_bracket_blocked: <code>`:

| Código | Condición |
|---|---|
| `scores` | algún combate con marcador ≠ 0 |
| `winner` | algún combate con ganador decidido |
| `planning` | algún combate con tatami/hora/posición asignados |
| `tentative_inputs` | inputs provisionales/tentativos |
| `not_single_elimination` | el `stage_item` no es eliminación directa |
| `too_few_entrants` | menos de 2 inscritos |
| `bracket_too_large` | el cuadro excedería el tamaño declarado |
| `inconsistent_slots` | los slots no son coherentes con `team_count` |

Torneo **archivado** → 400 (no entra al gate). Nada de esto borra, resetea ni re-seedea datos.

---

## 6. Idempotencia

`plan_bracket_generation` es **puro** y compara el reparto actual con el objetivo: si coinciden,
`changes` está vacío y `.changed` es `false`; la ruta no escribe nada.

- Ensayo t10 (§10): `changed=false`, `changes=0`, `ghost_count=0`, blocker `null`.
- Casos cubiertos por tests (§8) y por el fixture (§9).

---

## 7. UI

| Elemento | Fichero |
|---|---|
| Cliente API `generateBracket` | `frontend/src/services/stage_item.tsx:35` |
| Utilidad de plan/estado del botón | `frontend/src/components/utils/generate_bracket.ts:34-96` |
| Modal | `frontend/src/components/modals/generate_bracket_modal.tsx` |
| Botón en el builder | `frontend/src/components/builder/builder.tsx:303` |

- Copy ES: «Generar cuadro», «Se distribuirán los participantes en el cuadro y se aplicarán los pases
  directos necesarios.», «Participantes actuales», «Tamaño del cuadro», «Pases directos previstos»,
  «Regenerar cuadro», «Esto cambiará la distribución actual del cuadro.», «Cerrar».
- Resultado: «Cuadro generado» · «6 participantes» · «Cuadro de 8» · «2 pases directos» ·
  «0 cruces vacíos»; 2ª ejecución → «El cuadro ya estaba correcto: no ha cambiado nada.».
- La UI **no** usa el término *ghost* (queda como término técnico interno); el modal no expone códigos
  internos.

---

## 8. Tests

| Suite | Fichero | Estado |
|---|---|---|
| Unit (backend) | `backend/tests/unit_tests/generate_bracket_test.py` | **23 casos** ✅ |
| Integración (API) | `backend/tests/integration_tests/api/generate_bracket_test.py` | **15 casos** ✅ |
| Frontend | `frontend/tests/generate_bracket.test.ts` | **8 casos** ✅ |
| Frontend i18n | `frontend/tests/i18n_locales.test.ts` | **7 casos** ✅ |
| Runner frontend | `node --test tests/*.test.ts` (no vitest) | **32/32** ✅ (incluye `bjj_terminology` y `round_labels`) |
| Suite backend completa | `pytest tests` | **208 casos** ✅ |

CI del fork en `886ff13`: **4/4 GREEN** (run completo, backend + frontend + lint + build).

---

## 9. Fixture en `bracket_test`

`scripts/rehearsal/f2c_fixture.py` (repo principal) valida el motor **sin tocar producción**: se ejecuta
en un contenedor `bracket` con `PG_DSN` apuntando a una base de **test** (se niega a arrancar si el nombre
de la base no contiene `test`), crea un torneo aislado con prefijo `F2CFIX` y lo borra con `--cleanup`.
Comprueba:

1. **Invariante `N → B`** para 2…9 inscritos: tamaño de cuadro, pases directos, 0 combates `∅/∅`, 0
   actividad (marcador/tatami/hora/posición) e idempotencia (2ª ejecución → `changed=false`).
2. **Caso del *UI AUTO-SEED GAP***: stage item de 8 plazas creado con inputs **vacíos**, partidos
   construidos y equipos asignados **después** (lo que hace la UI) → el reparto previo deja **1 combate
   `∅/∅`**; tras la acción explícita quedan **2 cruces + 2 pases directos + 0 vacíos**, con los pases
   **materializados** en semifinales (resolver P2.8A).
3. **Safety gates** (función pura `get_bracket_generation_blocker`): `scores`, `planning`,
   `not_single_elimination`, `too_few_entrants`. El mapeo a HTTP 409/400 (incluidos `winner`,
   `tentative_inputs` y torneo archivado) está cubierto por los tests de integración.

Ejecución real (2026-10-03, base `bracket_test`, imagen `886ff13-r1`): `F2C FIXTURE OK` (exit 0):

| N | B | pases | 1ª ronda (cruces/pases/vacíos) | 1ª ejecución | 2ª ejecución |
|---|---|---|---|---|---|
| 2 | 2 | 0 | 1/0/0 | no-op | `changed=false` |
| 3 | 4 | 1 | 1/1/0 | no-op | `changed=false` |
| 4 | 4 | 0 | 2/0/0 | no-op | `changed=false` |
| 5 | 8 | 3 | 1/3/0 | `changed=true` | `changed=false` |
| 6 | 8 | 2 | 2/2/0 | `changed=true` | `changed=false` |
| 7 | 8 | 1 | 3/1/0 | `changed=true` | `changed=false` |
| 8 | 8 | 0 | 4/0/0 | no-op | `changed=false` |
| 9 | 16 | 7 | 1/7/0 | `changed=true` | `changed=false` |

(*no-op* = el reparto previo ya coincidía con el objetivo, así que la acción no escribe nada). Caso del
gap (6 inscritos en 8 plazas, creado como lo hace la UI): **antes** `3 cruces + 0 pases + 1 vacío`;
**después** `2 + 2 + 0` con `bye_count=2`, `ghost_count=0`, `changed=true`, pases materializados ✅ y 2ª
ejecución `changed=false`. El torneo del fixture se eliminó al terminar (0 filas `F2CFIX%` en
`bracket_test`).

Invocación (dentro del contenedor `bracket` en ejecución, con el `PG_DSN` de la base de test):

```
docker cp f2c_fixture.py bracket:/tmp/f2c_fixture.py
docker exec -e PG_DSN=<dsn_bracket_test> -w /app -e PYTHONPATH=/app bracket \
    .venv/bin/python /tmp/f2c_fixture.py            # y al terminar: --cleanup
```

---

## 10. Ensayo real `tournament_id=10` — validación SQL read-only

Torneo **`tournament_id=10`** «Torneo De pruebas REHEARSAL F2C», `stage_id=43`, `stage_item_id=49`
(`SINGLE_ELIMINATION`, `team_count=8` declarado). Validación **de solo lectura** sobre `bracket_dev`
(contenedor `bracket-postgres`), más el plan puro calculado en proceso sobre la misma base:

| Criterio | Esperado | Real |
|---|---|---|
| slots | 8 inputs | `in228…in235` (slot 1…8) ✅ |
| equipos | 6 | teams `161…166` (Team 1…6) ✅ |
| slots vacíos | 2 | slot **4** y slot **8** ✅ |
| 1ª ronda | 2 cruces + 2 pases directos + **0 vacíos** | `m184` T1-T2 · `m185` T3-∅ · `m186` T4-T5 · `m187` T6-∅ ✅ |
| pases directos | 2 estructurales | T3 y T6 pasan a semifinales esperando al ganador ✅ |
| resolver P2.8A | materializado | `m188` wf(184)+T3 · `m189` wf(186)+T6 · `m190` wf(188)+wf(189) ✅ |
| ghosts / dead | 0 | 0 combates sin inputs; `ghost_count=0` ✅ |
| scores | 0 | `scores_no_cero=0` ✅ |
| ganadores ficticios | 0 | 0 ✅ |
| planning | 0 | `planning_no_null=0` (0 court / 0 start_time / 0 posición) ✅ |
| rondas draft | 0 | 3 rondas, 0 draft ✅ |
| idempotencia | 2ª generación sin mutación | `plan_changes=0`, `plan_changed=false`, `blocker=null` ✅ |
| Tatami | `state=null` | `GET /internal/tatamis/1/state` → `{"state":null}` ✅ |

Detalle del cableado real (primera ronda con 6 de 8 plazas):

```
in228 slot=1 team=161   in229 slot=2 team=162   in230 slot=3 team=163   in231 slot=4 team=null
in232 slot=5 team=164   in233 slot=6 team=165   in234 slot=7 team=166   in235 slot=8 team=null

m184 r97 in1=228 in2=229         m185 r97 in1=230 in2=231
m186 r97 in1=232 in2=233         m187 r97 in1=234 in2=235
m188 r98 wf1=m184  in2=230       m189 r98 wf1=m186  in2=234
m190 r99 wf1=m188  wf2=m189
```

Los dos slots vacíos (4 y 8) quedan **sin equipo y sin origen** (2 = `STRUCTURAL_BYE`), no consumen
tatami ni tiempo de rejilla, y la segunda ejecución del endpoint no mutó nada. `tournament_id` 1, 2, 6
y 9 quedaron **intactos** (§14bis de `docs/18`).

---

## 11. Evidencia visual humana (§14)

Prueba del operador sobre `tournament_id=10`, `si=49` (8 plazas, 6 equipos) en el navegador real
(Chrome, tras Access):

Modal «Generar cuadro» correctamente traducido y con datos reales:

```
Generar cuadro
Se distribuirán los participantes en el cuadro y se aplicarán los pases directos necesarios.
Participantes actuales: 6
Tamaño del cuadro: 8
Pases directos previstos: 2
Esto cambiará la distribución actual del cuadro.
Cerrar
Regenerar cuadro
```

- Segunda ejecución → **«El cuadro ya estaba correcto: no ha cambiado nada.»** (`changed=false` esperado ✅).
- **0 claves visibles**: ninguna aparición de `generate_bracket_*`, `regenerate_bracket_*` ni `close_button`.

---

## 12. Incidencia i18n detectada durante §14 (cerrada)

**Síntoma.** En la primera pasada de §14 la funcionalidad era correcta pero el modal mostraba **claves
crudas** (`generate_bracket_modal_title`, `generate_bracket_no_change`, `regenerate_bracket_button`,
`close_button`, …). El problema se abordó en dos rondas, con prohibición expresa de aplicar fixes sin
causa raíz demostrada.

**Ronda 1 — versionado de locales (fix aplicado).** Auditoría: una sola instancia i18next
(`frontend/i18n.ts`), un solo `I18nextProvider`, `defaultNS='common'` correcto y las claves presentes en
`public/locales/{es,en}/common.json`. Se atribuyó a caché de locale (`loadPath` sin versión y origen sin
`Cache-Control`) y se aplicó el fix mínimo:

- `frontend/i18n_options.ts` (**nuevo**): config compartida app/tests con
  `LOCALES_REVISION = 774e67cc8391` (sha256 de `public/locales/*/common.json`),
  `loadPath: /locales/{{lng}}/{{ns}}.json?v=<rev>` y `requestOptions: { cache: 'no-cache' }`.
- `frontend/i18n.ts` consume esa config.
- Commit `886ff13` «fix(i18n): versiona los locales para no servir traducciones cacheadas».

**Ronda 2 — causa raíz y cierre.** El operador refutó la hipótesis de caché de locale como única causa:
el navegador **sí** pedía las URLs versionadas (`translation.json?v=774e67cc8391`,
`common.json?v=774e67cc8391`, 200) y seguía mostrando claves crudas. Auditoría dirigida, con evidencia:

- El log de nginx del origen registra que **el propio Chrome del operador** recibió
  `/locales/es/common.json?v=774e67cc8391` → **200, 20103 B** (el JSON desplegado, con las 13 claves)
  y `/locales/en/common.json?v=…` → 200, 18660 B. Descartados origen, túnel y caché de edge.
- `translation.json` lo pide el **core de i18next** (`i18n.options.ns = ["translation","common"]`), no
  el código de la app; la ruta no existe y el estático responde **200 + `index.html`** (751 B) → error de
  parseo inofensivo. Ningún componente consulta ese namespace.
- Namespace real del componente: `react-i18next` `useTranslation()` sin argumentos resuelve
  `defaultNS='common'`; en el bundle desplegado las claves se invocan sin `ns`.
- Sondas de runtime con las **mismas** librerías (i18next 26.0.3, react-i18next 17.0.1), la **misma**
  config y el **mismo** HTTP del contenedor desplegado: resolución correcta con `lng=es` **y** con
  `lng=es-ES`, incluido un render React (SSR) con `useTranslation()` + `I18nextProvider`:

```
ready=true | Generar cuadro | Participantes actuales: 6 | Tamaño del cuadro: 8 |
Pases directos previstos: 2 | Esto cambiará la distribución actual del cuadro. |
Regenerar cuadro | El cuadro ya estaba correcto: no ha cambiado nada. | Cerrar | tatamis
```

Por tanto el defecto **no** estaba en el namespace, la instancia, el idioma, el wiring, el JSON, el
artefacto ni en lo que el origen entregaba: era un problema de **frescura/caché del SPA en el navegador**
(documento/bundle antiguo servido al cliente). Con la shell y el bundle nuevos, los locales versionados
llegan y el runtime resuelve; el operador lo confirmó visualmente (§11) y con la consola del navegador:

```
fetch('/locales/es/common.json?v=774e67cc8391') → len 19933, has true
```

(`len` son **caracteres**; el fichero son 20103 **bytes** por los acentos en UTF-8: misma respuesta.)

**Comportamiento final:** 0 claves crudas en la UI; locales versionados que no se sirven cacheados.

**Residual documentado (⚠️ pendiente de autorización, no aplicado):** el SPA se sirve **sin
`Cache-Control`** (`/`, `/index.html`, `/assets/*`, `/locales/*` solo con `etag`/`last-modified`), lo que
permite que un navegador reutilice una shell antigua. Fix propuesto y **no ejecutado**: `no-cache,
must-revalidate` para la shell y los locales, `immutable, max-age=31536000` para `/assets/*` (nombres con
hash) y **404 real** para rutas inexistentes bajo `/locales/`.

---

## 13. Ficheros y puntos de anclaje

Diff del fork `8ec816b..886ff13` (16 ficheros, +1805/−14):

| Fichero | Cambio |
|---|---|
| `backend/bracket/logic/scheduling/generation.py` | **nuevo** (+217) — plan puro, gates y aplicación |
| `backend/bracket/routes/models.py` | +11 — `GenerateBracketResponse` |
| `backend/bracket/routes/stage_items.py` | +35/−14 — ruta `generate_bracket` (`:248`) |
| `backend/openapi/openapi.json` | +96 — contrato regenerado |
| `backend/tests/integration_tests/api/generate_bracket_test.py` | **nuevo** (476 líneas) |
| `backend/tests/unit_tests/generate_bracket_test.py` | **nuevo** (279 líneas) |
| `frontend/src/components/utils/generate_bracket.ts` | **nuevo** (102) |
| `frontend/src/components/modals/generate_bracket_modal.tsx` | **nuevo** (171) |
| `frontend/src/components/builder/builder.tsx` | +10 — botón (`:303`) |
| `frontend/src/services/stage_item.tsx` | +10 — cliente API (`:35`) |
| `frontend/i18n.ts`, `frontend/i18n_options.ts` | config compartida + locales versionados |
| `frontend/public/locales/{es,en}/common.json` | +27/−… — copy del modal |
| `frontend/tests/generate_bracket.test.ts`, `frontend/tests/i18n_locales.test.ts` | **nuevos** |
| `scripts/rehearsal/f2c_fixture.py` (repo principal) | **nuevo** — fixture en `bracket_test` (§9) |

---

## 14. Release y despliegue

- Fork `danyseve/bracket` @ `886ff13` (CI **4/4 GREEN**); submódulo del repo principal fijado a `886ff13`.
- Imagen `danyseve1/bracket-bjj:886ff13-r1`; **sin** re-etiquetar `latest`; rollback `cbab68a-r1`
  (y `8ec816b-r1` como pre-F2C).
- Recreado **solo** el servicio `bracket`; `postgres`, `bridge`, `scoreboard`, `nginx` y `wireguard` sin
  reinicio. `RestartCount=0`.
- `WRITE=false`; `POST /tatamis/1/result` → `503 result_write_disabled`; Tatami 1 `state=null`.

---

## 15. No hacer (fuera de alcance, sigue vigente)

Modelo de dominio Club / Competitor / Team / Entrant, branding, Tatami 2–6, Access/DNS/Tunnel, `WRITE`,
doble eliminación. **No** se re-seedea ningún cuadro existente, **no** hay auto-reseed ni heurísticas
ocultas, **no** se tocan `tournament_id=6` ni `tournament_id=9` y **F3 no está iniciada**.

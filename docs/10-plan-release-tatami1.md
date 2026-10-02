# 10 - Plan de release controlado del Tatami 1 (P2.5A) — prerrequisitos P2.5B

Estado: **artefactos de release listos, sin desplegar**. P2.5A dejó el plan escrito; P2.5B (§19)
implementa los prerrequisitos técnicos: interruptor de escritura en el Bridge (default `false`),
dependencias pinadas, Dockerfiles de release, servicios `bridge-api` y `scoreboard-tatami-1` bajo el
perfil `tatami1` del Compose, healthchecks reales y contrato de secretos. Sigue **sin construir imagen
publicada, sin publicar, sin tocar `.env` productivo, nginx, WireGuard, PostgreSQL ni el Bracket
productivo**, y sin habilitar la escritura de resultados.

Objetivo: desplegar en Oracle las versiones ya validadas de **Bracket corregido**, **Bridge API**,
**scoreboard del Tatami 1 integrado** y su **persistencia**, con orden secuencial, rollback por
componente y la escritura de resultados **desactivada** al terminar.

Fases relacionadas: `docs/06-imagen-custom-bracket.md`, `docs/07-plan-imagen-reproducible.md`,
`docs/decisions/ADR-004-bracket-image-reproducibility.md`, `docs/adr/ADR-001-politica-traduccion-resultados-bjj.md`.

Nota de numeración: se pidió `docs/06-release-tatami1.md`; el prefijo `06-` ya está ocupado dos veces
(`06-imagen-custom-bracket.md`, `06-modelo-multitatami.md`), así que este plan se numera `10-` para no
colisionar. Es el único cambio respecto a la preferencia indicada.

---

## 1. PRECHECK (leído, no modificado)

Repo `/home/ubuntu/projects/bjj-tournament-platform`, rama `develop`:

| Comprobación | Resultado |
|---|---|
| `git status --porcelain` | vacío (limpio) |
| `HEAD` | `3b3ed630e528fbf006413a4141ab3a5552f7f19a` |
| `origin/develop` | `3b3ed630e528fbf006413a4141ab3a5552f7f19a` (coincide) |
| Submódulo `services/bracket` | `47bc129d467a9544edd835aacbd49b5879e8adf6`, limpio, `master`, remote `https://github.com/danyseve/bracket.git` (fork propio) |
| Submódulo `services/scoreboard` | `c49df6d6a0deb731573a1030dc68b9f46d791642`, limpio |
| `docker compose config --quiet` | OK (exit 0) |
| Servicios en el Compose | `wireguard`, `bracket-postgres`, `bracket`, `nginx` (los perfiles `multitatami` no cuentan por defecto) |

Producción en ejecución (inmutable durante P2.5A):

| Contenedor | ID | StartedAt | Restarts | Imagen |
|---|---|---|---|---|
| `/bracket` | `d5e9e340ac454707ebe1cc182bee00d35562505ce05a481d03aab96a41ecf165` | 2026-10-01T18:43:48Z | 0 | `danyseve1/bracket-bjj@sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8` |
| `/bracket-postgres` | `0283c07f4d4b…` | — | 0 | `postgres@sha256:bffa6baeb307…` |
| `/bjj-nginx` | `4d8d8390fcab…` | — | 0 | `nginx@sha256:65645c7bb6a0…` |
| `/wireguard` | `c749d6966735…` | — | 0 | `ghcr.io/linuxserver/wireguard:latest` |

- `bracket` es el único con **healthcheck** (`wget -q -O - http://127.0.0.1:8400/api/ping`, 30s/5s/3/20s) y está `healthy`.
- La imagen de `bracket` lleva el tag `danyseve1/bracket-bjj:e6abd7d-r3` y la etiqueta
  `org.opencontainers.image.revision = e6abd7d282850f9d13d9122494767d4dbcb139ef`.
- **Producción sigue ejecutando el Bracket basado en `e6abd7d` y NO el `47bc129`** (confirmado por la
  etiqueta de la imagen en ejecución, no por suposición).
- **PostgreSQL**: 16.14 (`postgres (PostgreSQL) 16.14 (Debian 16.14-1.pgdg13+1)`).
- **Alembic actual**: `c1ab44651e79`.
- **Volumen**: `bjj-tournament-platform_bracket_postgres_data` (único volumen Docker del proyecto).
- **Conteos de referencia (para comparar después)**: 2 torneos, 25 matches, 10 equipos, 16 rondas,
  15 tablas en `public`.
- **Ficheros de Compose**: `docker-compose.yml` (5.562 B, el que usan los 4 contenedores productivos,
  según sus etiquetas `com.docker.compose.project.config_files`) y `docker-compose.prod.yml` (247 B, no
  es el que corre). `.env`: 1.623 B, modo `600`, `ubuntu:ubuntu`.
- Nombres de variables presentes hoy en `.env` (nunca valores): las de infraestructura
  (`POSTGRES_*`, `JWT_SECRET`, `NGINX_HTTP_PORT`, `BRACKET_PORT`, `BRIDGE_PORT`,
  `SCOREBOARD_TATAMI_1..6_PORT`, `WG_*`, `PUID/PGID/TZ`, `PROJECT_NAME`, `ENVIRONMENT`,
  `BRACKET_API_URL`, `BRACKET_IMAGE`, `BRACKET_PUBLIC_BASE_URL`, `BRIDGE_API_KEY`).
  **Ausentes**: `SCOREBOARD_INTERNAL_TOKEN`, `SCOREBOARD_CONTROL_TOKEN`, `SCOREBOARD_STATE_FILE`,
  `BRACKET_RESULT_WRITE_ENABLED`, `BRACKET_WRITE_USERNAME`, `BRACKET_WRITE_PASSWORD`.
- Trampa latente ya detectada: `BRACKET_IMAGE` está definida en `.env` pero **el Compose no la usa**
  (fija la imagen de Bracket por digest en el propio `docker-compose.yml`). No debe usarse para el
  release ni confiarse a ella.

---

## 2. INVENTARIO DE CAMBIOS A DESPLEGAR

| COMPONENTE | VERSIÓN PRODUCCIÓN ACTUAL | VERSIÓN OBJETIVO | CAMBIO | RIESGO | REQUIERE RECREATE |
|---|---|---|---|---|---|
| **bracket** | `danyseve1/bracket-bjj@sha256:e07ec8b4…8df8` (label `revision=e6abd7d`) | `<TBD>` = digest publicado de la imagen construida desde `47bc129`, tag `danyseve1/bracket-bjj:47bc129-r3` | **cambio de imagen** (una línea del Compose) | medio (es el único servicio existente que se recrea; DB intacta) | **SÍ** |
| **bridge-api** | no existe en producción (`profiles: ["multitatami"]`, servicio en `build:`) | digest publicado de la imagen release del Bridge (HEAD principal) | **servicio nuevo** | bajo (nuevo, sin estado, sin puertos públicos) | SÍ (creación) |
| **scoreboard-tatami-1** | no existe en producción (perfil `multitatami`, servicio en `build:`) | digest publicado de la imagen release del scoreboard (adapter + submódulo) | **servicio nuevo** + persistencia | medio (introduce estado en disco) | SÍ (creación) |
| **nginx** | `nginx@sha256:65645c7bb6a0…`, `8080:80`, `./nginx/conf.d` | **idéntico** | **sin cambio** (ver §8: el bloque de acceso al Tatami 1 es un requisito de despliegue, no de P2.5A) | — | **NO** |
| **PostgreSQL** | `postgres@sha256:bffa6baeb307…`, 16.14, volumen `bjj-tournament-platform_bracket_postgres_data`, alembic `c1ab44651e79` | **idéntico** | **sin cambio**; no se ejecuta ninguna migración | — | **NO** |
| **WireGuard** | `ghcr.io/linuxserver/wireguard:latest` | **idéntico** | **FUERA DE CAMBIO** | — | **NO** |

Coincide con lo esperado: nginx sin cambio, PostgreSQL sin cambio, WireGuard fuera, Bracket cambio de
imagen, Bridge y scoreboard-tatami-1 servicios nuevos.

P2.5B deja los tres artefactos **construidos en local y sin publicar** (IDs en §19): la imagen release
del Bracket desde `47bc129`, la del Bridge y la del scoreboard. Ninguno se ha subido a registro alguno,
así que en §2 la columna "VERSIÓN OBJETIVO" sigue sin digest real que pinear: eso es exactamente lo que
cierra P2.5C.

---

## 3. BRACKET RELEASE IMAGE

Receta: **el `docker/bracket-bjj/Dockerfile` actual, sin modificar** (reutilización explícita). Todo lo
que distingue una build de otra entra por argumentos:

```
docker build --no-cache \
  -f docker/bracket-bjj/Dockerfile \
  --build-arg BRACKET_UPSTREAM_COMMIT=47bc129d467a9544edd835aacbd49b5879e8adf6 \
  --build-arg RECIPE_REVISION=r3 \
  -t danyseve1/bracket-bjj:47bc129-r3 .
```

| Dato | Valor |
|---|---|
| Tag release propuesto | `danyseve1/bracket-bjj:47bc129-r3` (convención `<sha7>-r<n>` de `docs/07`, sin `latest`) |
| `org.opencontainers.image.revision` | `47bc129d467a9544edd835aacbd49b5879e8adf6` (viene del `ARG`, no del tag) |
| `RECIPE_REVISION` | `r3` (receta sin cambios) |
| Arquitectura | `linux/arm64` (variant v8), builder nativo, **sin QEMU** |
| Usuario | `bracket` (no root) |
| Healthcheck | `wget -q -O - http://127.0.0.1:8400/api/ping | grep -q '"ping"'` (definido **en la imagen**) |
| Puerto | `8400` (expuesto por la imagen; el Compose lo publica con `${BRACKET_PORT:-8400}`) |
| Migraciones | `AUTO_RUN_MIGRATIONS=false` en el Compose; el arranque **no** migra (evidencia: `services/bracket/backend/bracket/app.py:48` solo migra si `config.auto_run_migrations`, `config.py:40`) |
| Digest esperado tras build | **No es predecible**: se obtiene del build/push y se registra aquí. Mientras no exista, la línea del Compose queda con el digest productivo y **no se despliega** |
| Imagen local construida en P2.5B | `danyseve1/bracket-bjj:47bc129-r3` → Image ID `sha256:59944e01606c1e7db4f1e06b9476313db82b804f883ae1cbaa749653ae93743b` (arm64, `user=bracket`, `revision=47bc129d467a9544edd835aacbd49b5879e8adf6`, healthcheck `/api/ping`, 330 MB). **Sin publicar**: no hay RepoDigest |
| Digest del test P2.4D | `sha256:9b1a6c96f3e820511f7c23f446f622e549e09f790eda0c1bb279c488c8dcd8d0` — **NO es el digest de release**: se construyó con `RECIPE_REVISION=r3-p24d-test`, y esa etiqueta distinta cambia el `config` y por tanto el digest |

Validación estática de la receta ya disponible (sin construir nada nuevo en P2.5A):

- La build P2.4D se ejecutó con este mismo Dockerfile y **este mismo commit** (`47bc129…`) y terminó
  exit 0, con las comprobaciones internas en verde: `sha256sum -c` de `uv.lock` (antes y después de
  `uv sync`), `sha256sum -c` de `pnpm-lock.yaml`, y «0 ficheros reales world-writable bajo /app».
- La imagen resultante declaró `arch=arm64`, `user=bracket` y `revision=47bc129…` (justo lo que exige
  este plan).
- Bases pinadas por digest dentro del Dockerfile (`node:24-alpine`, `python:3.14-alpine3.22`,
  `ghcr.io/astral-sh/uv:0.9.19`) y hashes de lockfiles por `ARG`: nada depende de tags móviles.
- El código que se empaqueta sale del **árbol de trabajo** del submódulo (el Dockerfile hace
  `COPY services/bracket/backend/ ./`): por eso el `ARG` es solo etiqueta y el requisito duro es que
  el submódulo esté en `47bc129` antes de construir (§11 paso 1).

---

## 4. BRIDGE RELEASE

Base: `bridge-api/Dockerfile`, contexto `./bridge-api`, HEAD del repo principal en el momento del build.

**Implementado en P2.5B** (`bridge-api/Dockerfile`):

1. Base `python:3.12-slim@sha256:18d23907c5d7ef2ca1b0ea8b4a73fe4a6ae47114c257a1afed8bc66c3886f8cb`
   (digest de `linux/arm64`, resuelto del manifiesto y fijado en el `FROM`).
2. Usuario no-root `bridge` (uid 10002 fijo) y `USER bridge` antes del `CMD`.
3. `requirements.txt` **pinado** (directas + transitivas, §19) y `requirements-dev.txt` aparte, que
   **no** entra en la imagen. Instalación en su propia capa y comprobación de import tras instalar.
4. `HEALTHCHECK` contra `GET /health` con el intérprete de la imagen:
   `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/health', timeout=4)"`.
5. `EXPOSE 8500` documental; **sin publicar el puerto al host** (§7).
6. Check de imagen: falla la build si queda algún fichero world-writable bajo `/app`.

Imagen de validación construida: `bjj-bridge-api:p2.5b-test` →
`sha256:c2080cc69aad…` (arm64, `user=bridge`, `8500/tcp`, healthcheck de `/health`, sin `pytest`/`mypy`/
`ruff` dentro). **No publicada**: en P2.5C se publica y se pinea por digest con el tag
`danyseve1/bjj-bridge-api:<sha7-del-commit-principal>-r1`.

Variables (solo nombres; clasificación por obligatoriedad/opcionalidad/sensibilidad):

| Variable | Obligatoria | Sensible | Nota |
|---|---|---|---|
| `BRACKET_API_URL` | sí | no | valor operativo `http://bracket:8400/api` |
| `SCOREBOARD_TATAMI_1_URL` | sí | no | `http://scoreboard-tatami-1:3000`; el código trae default, pero debe fijarse explícitamente |
| `SCOREBOARD_INTERNAL_TOKEN` | **sí** | **SÍ** | el mismo valor que recibe el scoreboard; sin él los endpoints internos responden fail-closed |
| `BRACKET_RESULT_WRITE_ENABLED` | sí (con valor `false`) | no | **implementado en P2.5B** (§19): default `false`, y con `false` el endpoint de resultado responde 503 `result_write_disabled` sin leer el scoreboard ni llamar a Bracket |
| `BRACKET_WRITE_USERNAME` | **no en el primer release** | **SÍ** | dejarla **ausente** es parte del diseño: sin credencial el endpoint de escritura responde 503 aunque alguien active el flag por error |
| `BRACKET_WRITE_PASSWORD` | **no en el primer release** | **SÍ** | ídem |
| `SCOREBOARD_TATAMI_2_URL` … `_6_URL` | no | no | se mantienen como están; Tatami 2–6 no se habilitan |
| `SCOREBOARD_TIMEOUT_SECONDS` | no | no | default 10.0 |
| `BRACKET_WRITE_TIMEOUT_SECONDS` | no | no | default 10.0 (solo aplica si algún día se activa la escritura) |
| `PORT` | no | no | el `CMD` fija 8500 |

---

## 5. SCOREBOARD TATAMI 1 RELEASE

Base: `docker/scoreboard/Dockerfile` (contexto = raíz del repo), que ya es razonablemente estricto:
base `node:22.23.3-bookworm-slim` pinada por digest, `USER node`, `PORT=3000`, `npm ci --omit=dev`
con hash de `package-lock.json` verificado antes y después, y `node --check` de los ficheros del
adapter. Sin `HEALTHCHECK`.

Modo requerido: **`SCOREBOARD_MODE=integrated`** (sin él, `launcher.js` no arranca el modo integrado).

Variables/configuración:

| Variable | Obligatoria | Sensible | Nota |
|---|---|---|---|
| `SCOREBOARD_MODE` | sí | no | valor `integrated` |
| `SCOREBOARD_INTERNAL_TOKEN` | sí | **SÍ** | protege `/internal/tatamis/1/state` y `/internal/tatamis/1/assignment`; mismo valor que en el Bridge |
| `SCOREBOARD_CONTROL_TOKEN` | sí (para la UI/endpoints de control del operador) | **SÍ** | distinto del interno |
| `SCOREBOARD_STATE_FILE` | sí (si se quiere persistencia) | no | opt-in de P2.4B; sin ella el estado solo vive en memoria |
| `PORT` | no | no | default 3000 |

Requisitos de la imagen release — **implementados en P2.5B**: `HEALTHCHECK` real contra `GET /health`
en modo integrado (en standalone, que sigue funcionando, sondea `/`), directorio `/state` creado con
ownership del usuario `node`, y `docker/scoreboard/Dockerfile` sin más cambios. Imagen de validación:
`bjj-scoreboard:p2.5b-test` → `sha256:5b1a2a5fd238…` (arm64, `user=node`, `3000/tcp`).

`GET /health` (nuevo, sin token, sin secretos y sin contenido del estado) devuelve
`{"status":"ok","service":"bjj-scoreboard","mode":"integrated","state_store":{"enabled":true,"ready":true}}`,
y responde **503** si la persistencia está activada pero no es escribible (fail-closed).

### Persistencia productiva (diseño)

| Decisión | Valor |
|---|---|
| Ruta host propuesta | `/home/ubuntu/data/bjj-tournament-platform/tatami-1/` (**no existe hoy**, no se crea en P2.5A) |
| Alternativa descartada | `./data/tatami-1` dentro del repo (precedente de WireGuard): el árbol es un checkout git y `data/` está en `.gitignore`; se descarta para no mezclar estado de servicio con el repo y para que `git clean`/reclonados no puedan tocarlo |
| Mount | `-v /home/ubuntu/data/bjj-tournament-platform/tatami-1:/state` (ruta de contenedor `/state`, fijada por el release P2.5B; sustituye a la propuesta inicial `/var/lib/bjj/tatami-1`) |
| Fichero | `state.json` (una sola ruta; `SCOREBOARD_STATE_FILE=/state/state.json`) |
| Ownership | `1000:1000`. **Atención**: el usuario `node` de la imagen es uid 1000, pero `ubuntu` en `oracle-jiujitsu` es **uid 1001**, así que crear el directorio como `ubuntu` **no basta**: el release exige `sudo mkdir -p` + `sudo chown 1000:1000` + `chmod 700`. Verificado en aislado: con el directorio en 1001 el scoreboard **refusa arrancar** (EACCES) y `GET /health` responde 503 (`state_store.ready=false`) |
| Permisos | directorio `0700`; el fichero lo fija el propio adapter a `0600` (`state-store.js`: `fchmodSync(handle, 0o600)`) |
| Escritura | atómica: fichero temporal + `fsync` + `rename` sobre la ruta final + `fsync` del directorio (best effort). El fichero final nunca queda a medias |
| Backup | copia de `state.json` (con `sha256sum` registrado) antes de cualquier cambio y en el preflight de cada ventana; el estado **no** está en PostgreSQL |
| Recovery: fichero ausente | arranque limpio (`state: null`); es el caso del primer release |
| Recovery: fichero corrupto/JSON inválido | `state-store.js` **lanza y no sobrescribe**: el servicio no arranca y conserva el fichero. Acción: copiar el corrupto a `state.json.corrupt-<ts>` y restaurar del backup, nunca dejar que la app lo pise |
| Recovery: permisos mal | fallo fail-closed al guardar; corregir ownership del directorio antes de reintentar |
| Alcance | **solo Tatami 1**; Tatami 2–6 no se habilitan ni se les diseña ruta |

---

## 6. COMPOSE TARGET (aplicado al fichero; **no ejecutado**)

### Profile: ¿mantener `multitatami` o pasar a servicio explícito?

| Opción | Consecuencia operativa | Veredicto |
|---|---|---|
| (a) Mantener `profiles: ["multitatami"]` | `docker compose up -d` sigue levantando **solo** los 4 contenedores estables; Tatami 1 y el Bridge se arrancan con `--profile multitatami`, que **también** habilitaría los Tatamis 2–6 si algún día se listan en el mismo comando | No: el mismo perfil mezcla "enciendo el Tatami 1" con "enciendo los seis" |
| (b) Quitar el `profiles` de los dos servicios nuevos | `docker compose up -d` los arranca **siempre**, sin ningún flag explícito; el estado de producción pasa a ser "5 contenedores por defecto" y cualquier `up -d` futuro (o un `down`/`up` rutinario) los recrea aunque nadie lo pretenda; el rollback exige volver a meter el perfil | No: activación implícita, contraria a "primer release" |
| (c) **Perfil propio `tatami1` para los dos servicios nuevos** y `multitatami` intacto para 2–6 | `docker compose up -d` (sin perfil) **no cambia** el conjunto de producción; el release se enciende con `docker compose --profile tatami1 up -d`, un flag explícito y reversible; no es posible encender por accidente el 2–6; el rollback es volver a parar los dos servicios y, si se quiere, dejar de usar el perfil | **Elegida** |

Consecuencia adicional de (c): como `docker compose --profile tatami1 up -d` evalúa también los
servicios sin perfil, ese mismo comando es el que aplica el cambio de digest de `bracket` — que es
exactamente lo previsto en el orden de despliegue (§11), y también el comando que ejecuta el rollback
de Bracket tras revertir la línea del digest.

No se decide "por comodidad": la opción (b) es más cómoda de operar y por eso se descarta — el
primer release debe fallar del lado de "no se enciende solo".

Otros detalles del target:
- `SCOREBOARD_TATAMI_1_PORT` (y sus hermanas) quedan sin uso al retirar los `ports:`; se conservan en
  `.env` sin efecto (documentarlo, no borrarlas en este release).
- No se toca `wireguard`, `bracket-postgres` ni `nginx`.
- No se toca `docker-compose.prod.yml` (no es el fichero en uso; se decide aparte si algún día se
  unifica).

---

## 7. RED

Todo el tráfico nuevo es **interno a `bjj-net`** (bridge `172.30.0.0/24`, gateway `172.30.0.1`):

| Origen | Destino | Cómo |
|---|---|---|
| Bridge | Bracket | `http://bracket:8400/api` (nombre de servicio en `bjj-net`) |
| Bridge | scoreboard-tatami-1 | `http://scoreboard-tatami-1:3000` |
| nginx | Bracket | `http://bracket:8400` (sin cambios) |
| Operador (navegador) | scoreboard-tatami-1 | **pendiente**, §8 (hoy no hay camino) |

Puertos host:

| Puerto propuesto históricamente | ¿Se necesita en el host? | Decisión |
|---|---|---|
| `8500` (Bridge) | No: nadie fuera de la red Docker lo consulta en este release (el operador no usa la API del Bridge y nginx no la expone) | **No publicar** |
| `3001` (scoreboard Tatami 1) | No desde el host en sentido estricto: se resuelve con el acceso del operador (§8). Publicar 3001 abriría el marcador a cualquiera que alcance el host | **No publicar**; el acceso se diseña en §8 |

Sin `ports:` en ninguno de los dos servicios nuevos: la superficie expuesta no crece ni un puerto.
El Bridge y el scoreboard quedan alcanzables solo desde `bjj-net` (y, cuando se autorice, desde
nginx/WireGuard).

`bracket` conserva su `ports: ${BRACKET_PORT:-8400}:8400` tal como está hoy (no se cambia en este
release); su reducción es una mejora posterior, no un requisito.

---

## 8. NGINX / ACCESO

Hoy `nginx/conf.d/bjj.conf` es un único `server` (`bjj.local`, puerto 80) que proxya `location /` y
`location /api/` a `http://bracket:8400`. **No se toca nginx en P2.5A.**

Separación pedida:

**REQUERIDO PARA EL RELEASE** (a resolver con autorización explícita antes de dar el release por
operativo, en P2.5B o en la ventana de despliegue):

- Un camino **interno** para que el operador abra la UI del Tatami 1. Sin él, el marcador arranca pero
  nadie puede usarlo: hoy no existe ni puerto host ni bloque nginx.
- Opción recomendada: **bloque `server` dedicado para el Tatami 1** (p. ej. `tatami1.bjj.local` o un
  `listen 8081`), accesible solo desde WireGuard, con `proxy_pass http://scoreboard-tatami-1:3000` y
  las cabeceras de WebSocket (`Upgrade`/`Connection`) porque el marcador usa Socket.IO — junto con
  `proxy_buffering off` para no romper el flujo de eventos.
- Motivo técnico por el que **se descarta `/tatami/1/` como prefijo de ruta**: la UI integrada sirve
  activos en rutas **absolutas** (`app.get('/js/main.js', …)`, estáticos de `/public`, Socket.IO en
  `/socket.io/`) y no está preparada para montarse bajo un subpath; un prefijo rompería los activos y
  el socket salvo que se reescribieran las rutas. Esto no se improvisa en el release.
- Alternativa admitida solo como excepción y de forma temporal: un `ports:` acotado a una dirección
  concreta del host. Se descarta en favor de nginx porque deja el marcador expuesto fuera de la VPN.

**MEJORA POSTERIOR** (no bloquea el release):

- `tatami/1/` como ruta limpia bajo el dominio actual (exigiría reescribir rutas o montar la UI con
  `base` configurable).
- `tatami/1/control` (panel de control del operador separado del marcador público).
- API administrativa del Bridge expuesta de forma separada y autenticada.
- Reducir/retirar la publicación de `8400` de Bracket.

Regla explícita: **no se abre ninguna interfaz de control al público**; todo acceso nuevo es interno
(WireGuard) y, si nginx lo expone, solo a través de la VPN.

---

## 9. SECRETS

Secretos nuevos: `SCOREBOARD_INTERNAL_TOKEN`, `SCOREBOARD_CONTROL_TOKEN` y (solo para una fase
posterior) la credencial de escritura en Bracket (`BRACKET_WRITE_USERNAME`/`BRACKET_WRITE_PASSWORD`).
No secretos, pero obligatorios para renderizar el Compose: `BRACKET_API_URL`, `SCOREBOARD_TATAMI_1_URL`
y `BRACKET_RESULT_WRITE_ENABLED`.

**Contrato de nombres publicado en `.env.example` (P2.5B)**, sin valores reales y con placeholders
obvios:

| Nombre | Estado en el `.env` productivo | Nota |
|---|---|---|
| `SCOREBOARD_INTERNAL_TOKEN` | **ausente** | token interno del scoreboard (header `X-Internal-Token`), compartido con el Bridge |
| `SCOREBOARD_CONTROL_TOKEN` | **ausente** | token de control del scoreboard |
| `BRACKET_RESULT_WRITE_ENABLED` | **ausente** | no es secreto; valor `false` en el primer release |
| `SCOREBOARD_TATAMI_1_URL` | **ausente** | no es secreto |
| `BRACKET_API_URL` | presente | no es secreto |
| `BRACKET_WRITE_USERNAME` / `BRACKET_WRITE_PASSWORD` | ausentes | **a propósito**: no se configuran en el primer release |

| Dónde viven | Dónde NO deben estar |
|---|---|
| `.env` del repo en el host (`0600`, `ubuntu`), que Compose ya carga por defecto | Git (nada versionado) |
| Interpolados en el Compose como `${VAR:?requerido}` (referencia, nunca literal) | Literales en `docker-compose.yml` |
| En el entorno de cada contenedor, solo los que cada servicio necesita | Logs (el Bridge no registra el token; los tests lo comprueban) |
| Copia de seguridad del `.env` en el backup del despliegue (§15) | Imágenes (nunca `ARG`/`ENV` con secretos) |

Procedimiento (diseño; **no se ejecutan ahora**):

1. Generar cada token con `openssl rand -hex 32` **redirigido al fichero**, sin imprimirlo en la
   terminal ni en el chat: `umask 077` y una línea por token en `.env`.
2. Añadir además `BRACKET_RESULT_WRITE_ENABLED=false` (no es secreto) y dejar fuera, a propósito,
   `BRACKET_WRITE_USERNAME`/`BRACKET_WRITE_PASSWORD`.
3. `chmod 600 .env` y `chown ubuntu:ubuntu .env` (ya se cumple hoy).
4. Comprobar sin revelar valores: `grep -c '^SCOREBOARD_INTERNAL_TOKEN=' .env` (debe dar 1) y
   `stat -c %a .env`.
5. Reiniciar **juntos** los dos consumidores del token interno (`scoreboard-tatami-1` y `bridge-api`)
   para que compartan valor; un token distinto entre ambos deja los endpoints internos en 401.
6. Rotación: mismo procedimiento + reinicio simultáneo de los dos servicios; rollback = restaurar el
   `.env` del backup y reiniciar ambos.

Nota de diseño: en el primer release **no se configuran** las credenciales de escritura, de modo que
la escritura queda impedida por dos motivos independientes (flag `false` y credencial ausente).

---

## 10. BRACKET WRITE GATE

Objetivo: que el primer despliegue **no** habilite la escritura automática hacia Bracket, aunque la
imagen del Bridge ya contenga P2.4D.

- Flag: `BRACKET_RESULT_WRITE_ENABLED`, booleana, **default `false`** — **implementada en P2.5B**
  (`bridge-api/app/config.py`: `bracket_result_write_enabled: bool = False`).
- Con `false`, `POST /tatamis/1/result` responde **503** con `status="failed"` y
  `reason="result_write_disabled"` (`result_gate.REASON_WRITE_DISABLED`) **antes de tocar nada**: el
  chequeo de la flag es anterior a la comprobación de credenciales y a la lectura del scoreboard, así
  que con la escritura desactivada **no hay lectura de scoreboard, ni login, ni GET/PUT a Bracket**.
  Evidencia: `bridge-api/tests/test_p25b.py` (test 3) usa dobles envenenados que fallan si se les llama,
  y en la pila aislada de §19 el Bracket registró **0 GET/PUT a `/matches` y 0 `POST /api/token`**
  mientras el endpoint devolvía 503.
- Los caminos de lectura (`/health`, `/health/bracket`, `/tatamis/1/candidates`,
  `/tatamis/1/assign-match`) no se ven afectados: el release arranca en modo lectura/asignación.
- Credenciales perezosas: con `WRITE=false` el Bridge arranca sin `BRACKET_WRITE_USERNAME/PASSWORD`
  (verificado en la pila aislada, sin esas variables). Con `WRITE=true` y sin credenciales responde
  503 `bracket_write_not_configured` **sin leer ni escribir** (tests 7 y 8 de `test_p25b.py`).
- Doble cerrojo del primer release: `BRACKET_RESULT_WRITE_ENABLED=false` **y** credenciales de
  escritura ausentes (§9). Con cualquiera de los dos, no hay PUT posible.
- Habilitación futura (fase separada, fuera de este plan): cambiar la variable a `true`, añadir las
  credenciales de escritura, reiniciar el Bridge y validar con un combate de prueba. Requiere además
  que el Bracket desplegado sea `>= 47bc129` (lo será tras este release) y decisión de producto.

---

## 11. ORDEN DE DESPLIEGUE (runbook; **no ejecutado**)

Cada paso indica su comprobación y su condición de parada. Nada de esto se ejecuta en P2.5A.

| # | Paso | Comando (conceptual) | Verificación | Parada |
|---|---|---|---|---|
| 1 | Preflight | §1 de este documento + `git -C services/bracket rev-parse HEAD` | HEAD == `develop` == origin, submódulo en `47bc129`, Compose válido, producción sana | cualquier desviación |
| 2 | Backup PostgreSQL | `docker exec bracket-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > pre-p25-<ts>.dump` + `sha256sum` | dump no vacío, sha registrado | error de dump |
| 3 | Backup Compose/`.env` | `cp -p docker-compose.yml docker-compose.yml.pre-p25-<ts>` y `cp -p .env .env.pre-p25-<ts>` + `sha256sum` | ambos ficheros copiados, permisos preservados | — |
| 4 | Almacenamiento del scoreboard | `install -d -m 0700 -o 1000 -g 1000 /home/ubuntu/data/bjj-tournament-platform/tatami-1` | existe, `0700`, `1000:1000` | no se puede crear con ese ownership |
| 5 | Secretos | §9 (generar, escribir en `.env`, verificar sin revelar) | 1 ocurrencia por nombre, `.env` 600 | falta algún nombre |
| 6 | Desplegar nuevo Bracket | editar la línea del digest + `docker compose --profile tatami1 up -d bracket` (arranca solo Bracket en ese instante) | contenedor `healthy`, `docker image inspect` → `revision=47bc129…` | healthcheck no llega a healthy |
| 7 | Validar Bracket READ | `curl -s http://127.0.0.1:8400/api/ping`; `GET /api/tournaments/1/stages?no_draft_rounds=true`; `GET /api/tournaments/2/stages` → 401 | ping OK, stages del torneo 1 OK, torneo 2 rechazado | 5xx o fuga entre torneos |
| 8 | Desplegar scoreboard Tatami 1 | `docker compose --profile tatami1 up -d scoreboard-tatami-1` | `healthy`; `GET /internal/tatamis/1/state` con token → `{"state":null}`; sin token → 401 | responde sin token o no arranca |
| 9 | Validar scoreboard integrado | UI del Tatami 1 por su acceso interno (§8) + `GET /internal/tatamis/1/state` | UI carga, socket conecta, estado `null` | UI rota / socket no conecta |
| 10 | Desplegar Bridge | `docker compose --profile tatami1 up -d bridge-api` | `healthy`, `GET /health` = ok | no healthy |
| 11 | Validar Bridge | `GET /health/bracket` (Bracket alcanzable por nombre interno) | `ok` | error de red/nombre |
| 12 | Bracket READ → Bridge → scoreboard | `GET /tatamis/1/candidates?tournament_id=1`, luego `POST /tatamis/1/assign-match` de un combate real y `clear` | candidatos listados; asignación aplicada en el scoreboard y visible en la UI; **Bracket sin cambios** | asignación falla o el scoreboard queda inconsistente |
| 13 | UI del operador | flujo completo de un combate de prueba dentro del acceso de §8 (marcar, pausar, reanudar, sin cerrar resultado) | UI y socket estables | fallos de socket |
| 14 | Mantener WRITE deshabilitado | `POST /tatamis/1/result` con un combate cerrado | 503 `result_write_disabled`; y `docker logs` del Bracket sin `PUT` | cualquier PUT registrado ⇒ parar y revertir |
| 15 | Observación | `docker compose ps`, healthchecks, logs de los 5 contenedores durante la ventana acordada | sin reinicios inesperados ni errores | restart loop o errores nuevos |
| 16 | **Gate humano** | decisión explícita del operador antes de habilitar la escritura de resultados (fase separada) | — | no hay gate automático |

---

## 12. IMPACTO DEL BRACKET RECREATE

Al recrear **solo** el servicio `bracket`:

| Aspecto | Efecto |
|---|---|
| Base de datos | **Permanece**: `bracket-postgres` no se recrea ni se toca; el volumen `bjj-tournament-platform_bracket_postgres_data` no se modifica |
| Migraciones | **Ninguna automática**: el Compose fija `AUTO_RUN_MIGRATIONS=false` y el arranque solo migra si ese flag es verdadero (`bracket/app.py:48`). Alembic debe seguir en `c1ab44651e79` después del cambio |
| nginx | **Sin impacto**: `bracket` conserva su IP estática `172.30.0.20` en `bjj-net`, así que nginx (que resolvió el nombre al arrancar) sigue apuntando al mismo destino; nginx no se recrea ni se reinicia |
| Datos de aplicación | Ninguno en el contenedor de Bracket: todo el estado persistente está en PostgreSQL |
| Downtime | El hueco entre parar el contenedor viejo y arrancar el nuevo es **de segundos** (imagen ya presente por digest en el host, sin descarga ni build). **No se da una cifra inventada**: se mide en la ventana y se anota |
| Healthcheck | `start_period: 20s`, `interval: 30s`, `timeout: 5s`, `retries: 3`: el estado `healthy` tarda unos ciclos en aparecer; eso no es un fallo |
| Puertos | El mapeo `${BRACKET_PORT:-8400}:8400` no cambia |
| Consecuencia en el árbol | La recreación no deja residuos: no se crean volúmenes ni redes nuevas |

---

## 13. ROLLBACK

Por componente, con criterios de disparo concretos. La base de datos **no** se revierte salvo
necesidad demostrada: el release no ejecuta migraciones.

### Bracket
- Acción: restaurar la línea del digest anterior (`…@sha256:e07ec8b4…8df8`, tag `e6abd7d-r3`, presente
  en el host) y `docker compose --profile tatami1 up -d bracket`.
- Requisito previo: **no borrar ninguna imagen** (ni `e6abd7d-r1/r2/r3` ni la legacy).
- Disparo: Bracket no llega a `healthy`; `/api/ping` o `/api/tournaments/1/stages` fallan; aparece una
  fuga entre torneos o un `StatementError` nuevo; el árbol de rondas cambia sin escritura.

### Bridge
- Acción: `docker compose --profile tatami1 stop bridge-api` (y retirar el bloque del servicio del
  Compose con el backup de §15 si el rollback es definitivo).
- Disparo: `/health` no responde; `/health/bracket` falla con el Bracket sano; el Bridge crea carga
  anómala sobre Bracket o el scoreboard.

### Scoreboard Tatami 1
- Acción: `docker compose --profile tatami1 stop scoreboard-tatami-1` **conservando
  `/home/ubuntu/data/bjj-tournament-platform/tatami-1/state.json`** (nunca `down -v`; nunca borrar la
  ruta).
- Disparo: UI/socket inutilizables; el estado no persiste o el arranque falla por `state.json`
  corrupto (en ese caso: copiar el fichero a `state.json.corrupt-<ts>` y restaurar del backup).

### Compose
- Acción: restaurar `docker-compose.yml.pre-p25-<ts>` (y `.env.pre-p25-<ts>` si el rollback incluye
  secretos) y aplicar `docker compose up -d` para dejar producción exactamente como estaba.
- Disparo: cualquier rollback que deba ser definitivo o cualquier edición que resulte inválida.

### PostgreSQL
- **No hay rollback de base de datos previsto** (sin migraciones). Solo si aparece corrupción o una
  pérdida demostrada se restauraría el dump `pre-p25-<ts>`, y eso sería una operación aparte con su
  propia autorización y su propio procedimiento (`docs/04-backup-restore.md`).

---

## 14. VALIDACIÓN POST-DEPLOY (checklist; **no ejecutada**)

| Comprobación | Cómo | Resultado esperado |
|---|---|---|
| Contenedores healthy | `docker compose ps` | `bracket`, `bridge-api`, `scoreboard-tatami-1` `healthy`; `bracket-postgres`, `nginx`, `wireguard` `running` |
| IDs/restarts | `docker inspect -f '{{.Name}} {{.Id}} {{.State.StartedAt}} {{.RestartCount}}' …` | `bracket` con ID nuevo y `restarts=0`; `bracket-postgres`, `nginx`, `wireguard` con **los mismos IDs que antes** |
| Etiqueta de la imagen | `docker image inspect <digest> --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'` | `47bc129d467a9544edd835aacbd49b5879e8adf6` |
| Bracket `/api/ping` | `curl` directo a 8400 | responde `ping` |
| nginx `/` | `curl -H 'Host: bjj.local' http://127.0.0.1:8080/` | sirve el frontend |
| nginx `/api/ping` | `curl -H 'Host: bjj.local' http://127.0.0.1:8080/api/ping` | responde `ping` (el proxy no se rompió con la recreación) |
| PostgreSQL | `docker exec bracket-postgres postgres --version` + conteos | 16.14; 2/25/10/16/15 iguales |
| Alembic | `select version_num from alembic_version` | `c1ab44651e79` **sin cambios** |
| Conteos | torneos/matches/equipos/rondas/tablas | idénticos al precheck |
| Candidates | `GET /tatamis/1/candidates?tournament_id=1` | lista coherente; `tournament_id=2` → 401 |
| Assignment Tatami 1 | `POST /tatamis/1/assign-match` + `GET /internal/tatamis/1/state` | la asignación aparece en el scoreboard; Bracket **sin cambios** |
| Estado del scoreboard | `GET /internal/tatamis/1/state` con token / sin token | 200 con token, **401 sin token** |
| UI | abrir el acceso interno de §8 | carga, socket conecta, marcador operable |
| Persistencia | asignar estado → `docker restart scoreboard-tatami-1` → releer estado | el estado se recupera de `state.json` (y el fichero queda `0600`) |
| WRITE flag | `POST /tatamis/1/result` + revisar logs de Bracket | 503 `result_write_disabled` y **cero PUT** |
| Rollback listo | confirmar que el digest anterior sigue presente | tag `e6abd7d-r3` y su digest en el host |

---

## 15. BACKUPS REQUERIDOS ANTES DEL CAMBIO

Se definen aquí; **no se crean en P2.5A** porque son específicos del momento del despliegue.

| Elemento | Contenido | Nombre propuesto |
|---|---|---|
| PostgreSQL | `pg_dump` formato custom + `sha256sum` | `pre-p25-<UTC>.dump` (+ `.sha256`) |
| Compose | copia de `docker-compose.yml` | `docker-compose.yml.pre-p25-<UTC>` |
| `.env` | copia **sin leer valores** (`cp -p`, solo `sha256sum` y `stat`) | `.env.pre-p25-<UTC>` |
| Estado del Tatami | copia de `state.json` si existe | `state.json.pre-p25-<UTC>` (en el primer release no existirá) |
| Evidencia de imágenes | `docker image inspect` de las imágenes actuales (IDs, digests, etiquetas `revision`) | `images-pre-p25-<UTC>.txt` |
| Evidencia de contenedores | IDs, `StartedAt`, `restarts` de los 4 productivos | `containers-pre-p25-<UTC>.txt` |

Nombres y ruta de backups coherentes con el precedente `pre-deploy-r3-20261001T184323Z` documentado en
`docs/06-imagen-custom-bracket.md` y `docs/04-backup-restore.md`.

---

## 16. GO / NO-GO

GO **solo** si todo lo siguiente es verdadero (checklist binaria):

- [ ] Bracket release reproducible: receta sin cambios, tag `47bc129-r3`, build desde un árbol con el submódulo en `47bc129`, digest publicado y verificado por tres vías (salida del `docker push`, `docker image inspect`, `docker buildx imagetools inspect` / `docker manifest inspect -v`)
- [ ] Bridge release reproducible: base pinada, `requirements.txt` pinado, no-root, healthcheck, tag+digest publicados
- [ ] Scoreboard release reproducible: tag+digest publicados, healthcheck, etiqueta con el commit del repo principal
- [ ] Secretos listos en `.env` (`0600`), referenciados con `${VAR:?}`, ausentes de Git/logs/imágenes
- [ ] Backups listos (§15) y verificados (tamaño, sha256)
- [ ] Rollback documentado **y probado** (al menos el de Bracket y el de los servicios nuevos en un entorno no productivo)
- [ ] `BRACKET_RESULT_WRITE_ENABLED=false` presente en el Compose y credenciales de escritura ausentes
- [ ] Producción sana antes del cambio (4 contenedores, `restarts=0`, healthcheck de Bracket OK)
- [ ] Acceso interno del operador al Tatami 1 resuelto (§8) o decisión explícita de validarlo por otro medio
- [ ] Ventana acordada y gate humano identificado para §11 paso 16

NO-GO si falla cualquiera de los anteriores.

---

## 17. DOCUMENTACIÓN

Este documento es el plan de release. Además (en el mismo commit): entrada breve en
`docs/02-roadmap-fases.md` que referencia P2.5A y el plan, sin describir nada ya desplegado.
No se modifica ningún documento de runtime ni de operación.

---

## 18. GIT

- Commit único, solo documentación: `docs(release): plan tatami 1 production rollout`
- Push a `develop` por el remote HTTPS existente.
- Sin `amend`, sin `force-push`, sin tocar `main`, sin mover submódulos.

---

## 19. EVIDENCIA DE LA VALIDACIÓN P2.5B (2026-10-02)

Esta sección registra lo **realmente ejecutado** al preparar los artefactos. Nada de esto se desplegó.

### 19.1 Imágenes release construidas (locales, no publicadas)

| Imagen | Image ID | Arq | Usuario | Puerto | Healthcheck | Tamaño |
| --- | --- | --- | --- | --- | --- | --- |
| `danyseve1/bracket-bjj:47bc129-r3` | `sha256:59944e01606c1e7db4f1e06b9476313db82b804f883ae1cbaa749653ae93743b` | arm64 | `bracket` | 8400 | `wget /api/ping` | 331 MB |
| `bjj-bridge-api:p2.5b-test` | `sha256:c2080cc69aad4daa1bca125b06579e33de90428346d1a8e0e01f5907af0bcc02` | arm64 | `bridge` | 8500 | `python /health` | 195 MB |
| `bjj-scoreboard:p2.5b-test` | `sha256:5b1a2a5fd2380688c5c1d74608486e0344f4ab2dcee37b61a3869aaf084011c8` | arm64 | `node` | 3000 | `node /health` (integrado) o `/` (standalone) | 264 MB |

Bracket conserva las etiquetas del build reproducible (`revision=47bc129…`, `recipe_revision=r3`,
base `python:3.14-alpine3.22`). Bridge: `WORKDIR=/app`, sin `pytest/mypy/ruff` dentro, 0 ficheros
world-writable bajo `/app`, 0 referencias a marcadores de secreto en el historial de capas.
`BRACKET_RESULT_WRITE_ENABLED` viaja a `false` por defecto y no hay credenciales de escritura en la imagen.
**Ninguna imagen se ha publicado**: los digests de release se capturarán en P2.5C.

### 19.2 Pila aislada de punta a punta (no productiva)

Red `bjj-p25b-dbg` (172.32.0.0/24) + volumen `bjj-p25b-dbgpg` propios; puertos 18400 (Bracket),
13001 (scoreboard) y 18500 (Bridge) ligados solo a 127.0.0.1; PostgreSQL temporal con esquema en
Alembic `c1ab44651e79 (head)`, idéntico al productivo; datos sintéticos (sin datos de personas).
Resultado (`SCRIPT_RC=0`):

1. salud: Bracket `/api/ping` → `"ping"`; scoreboard `{"status":"ok","mode":"integrated","state_store":{"enabled":true,"ready":true}}`; Bridge `{"status":"ok","version":"0.1.0"}`.
2. candidatos: `GET /tatamis/1/candidates?tournament_id=1` → **200**, `count=6`, `scoreboard_read=true`.
3. UI integrada servida por el adapter → **200**, HTML real (1319 bytes).
4. asignación: `POST /tatamis/1/assign-match` → **201**, `match_id=9007`.
5. combate cerrado: `status=finished`, `points_a=2`, `points_b=1`, ganador `101`, `method=points`, `revision=5`.
6. **WRITE desactivado**: `POST /tatamis/1/result` → **503** con `{"status":"failed","reason":"result_write_disabled"}` y ningún dato de combate en el cuerpo; el reenvío vuelve a dar **503**.
7. persistencia: reinicio real del contenedor del scoreboard → `state.json` (0600) releído y estado idéntico (`match_id`, `session_id`, `status`, `revision`).
8. idempotencia: reasignar el mismo combate → **200** conservando sesión, estado y revisión; asignar **otro** combate → **409** sin tocar el estado.
9. cierre: `clear_match` aceptado (revisión 6, estado `null`); el reintento del mismo comando se **rechaza** (`wrong_session`, la memoria de idempotencia desaparece con la sesión) y el estado sigue `null`; los candidatos vuelven a incluir el combate.
10. **cero publicación**: la fila del combate 9007 en el Bracket sigue con `puntos 0-0` y `start_time=NULL` mientras el scoreboard cerró 2-1; 0 escrituras (`PUT matches` / `POST token`) vistas por el Bracket.
11. teardown limpio: 0 contenedores, 0 redes y 0 volúmenes `bjj-p25b*`; las imágenes de prueba se conservan.

### 19.3 Hallazgo de la fase: 500 del Bracket con columnas de duración nulas

El primer intento del E2E aislado falló con `GET /tatamis/1/candidates` → **502**. Diagnóstico: el
Bracket devolvía **500** en `GET /api/tournaments/1/stages?no_draft_rounds=true` por un error de
validación de la respuesta (`duration_minutes` y `margin_minutes` = `None` en `matches`), y el Bridge
traducía el 5xx del upstream a 502 — comportamiento correcto. La causa estaba en el **fixture** de
pruebas heredado de P2.4C.1, que inserta `matches` sin `duration_minutes`/`margin_minutes` (columnas
no nulas en el modelo de respuesta) para ejercitar escenarios SQL de DEF-02. Red, DNS, puerto y prefijo
`/api` eran correctos (verificado: resolución del nombre, TCP a 8400, `/api/ping` a través del Bridge).

Corrección aplicada **solo al harness aislado** (el código de producto no se tocó): el script de la
pila rellena esas dos columnas con `COALESCE` antes del E2E. Comprobación de impacto real: en la base
de producción, `matches` tiene **0** filas con `duration_minutes` o `margin_minutes` nulos (7 combates),
así que el release no puede provocar ese 500 con los datos actuales.

### 19.4 Suite de tests reejecutada

- `pytest bridge-api/tests`: **225 passed**, 1 aviso (`class Config` deprecado de pydantic-settings).
- `node --test scoreboard-adapter/tests/*.test.js` (con `NODE_PATH` a los `node_modules` del cache):
  **128 tests, 128 passed, 0 fail**.
- `docker compose config` sin perfil: `bracket`, `bracket-postgres`, `nginx`, `wireguard`.
- `docker compose config --profile tatami1`: los 4 anteriores + `bridge-api` + `scoreboard-tatami-1`.
- Puertos publicados al host en los servicios del perfil `tatami1`: **ninguno**.
- Variables obligatorias (`:?`) en el Compose: `BRACKET_API_URL`, `SCOREBOARD_TATAMI_1_URL`,
  `SCOREBOARD_CONTROL_TOKEN`, `SCOREBOARD_INTERNAL_TOKEN`, `BRACKET_RESULT_WRITE_ENABLED`.
- `git diff --check`: sin problemas.

### 19.5 Producción (antes y después, sin cambios)

| Contenedor | ID | StartedAt (UTC) | restarts |
| --- | --- | --- | --- |
| `bracket` | `d5e9e340ac454707ebe1cc182bee00d35562505ce05a481d03aab96a41ecf165` | 2026-10-01T18:43:48Z | 0 |
| `bracket-postgres` | `0283c07f4d4b48b46579465ad399d6e60e8d902063b8cee215c292bd9ad615e8` | 2026-10-01T15:03:21Z | 0 |
| `bjj-nginx` | `4d8d8390fcab8e92708d174731cd458d0a60111dffe288ba4e28b17775fa984e` | 2026-10-01T15:03:21Z | 0 |
| `wireguard` | `c749d6966735416cf1a11aca975f134a08e799fc3a0925d872fbf6bd4a10d87e` | 2026-10-01T15:03:21Z | 0 |

El Bracket productivo sigue ejecutando la imagen por digest `sha256:e07ec8b4…8df8` con etiqueta
`revision=e6abd7d…`. No se ejecutó `docker compose up`, ni `pull`, ni se tocó `.env`, nginx, WireGuard
ni PostgreSQL.

### 19.6 Git

Commit `feat(release): prepare tatami 1 deployment artifacts` sobre `develop`
(HEAD previo `331f03b…`, el commit de P2.5A) con los artefactos y la documentación de esta fase.
Sin `amend`, sin `force-push`, sin tocar `main`, sin mover submódulos.

---

## 20. P2.5C — Pre-despliegue final y GO/NO-GO (2026-10-02)

Resultado: `P2.5C — GO ✅ (ready to deploy, nothing recreated)`.
Todo preparado para P2.5D; **nada desplegado**: no se ejecutó `docker compose up`, ni `pull`
seguido de `up`, ni `recreate`, ni reinicio alguno, ni cambios en nginx, WireGuard o PostgreSQL.

### 20.1 Imágenes release publicadas (registry bajo control propio)

| Imagen | Tag | Image ID local | RepoDigest publicado | Arch | User |
| --- | --- | --- | --- | --- | --- |
| Bracket | `danyseve1/bracket-bjj:47bc129-r3` | `sha256:59944e01606c…43743b` | `sha256:8e9f2ca217c45637f5ffbc0b69c43bd6862ec04cda6a1400a46c22438155e9e1` | arm64/linux (v8) | `bracket` |
| Bridge | `danyseve1/bjj-bridge-api:92d52df-r1` | `sha256:c2080cc69aad…bcc02` | `sha256:6b6d5327118f98b2bed3fe5ac88ec0109216bf3d7f6f04942eeaaac8b1b437f6` | arm64/linux | `bridge` |
| Scoreboard | `danyseve1/bjj-scoreboard:92d52df-r1` | `sha256:5b1a2a5fd238…011c8` | `sha256:024f0d5bf14c0891b0a2e3f3766d74381768379bd6e8a1f055d99a3f3e33074e` | arm64/linux | `node` |

- El Bracket se reconstruyó desde `47bc129d467a9544edd835aacbd49b5879e8adf6` con la receta `r3` y
  produjo **el mismo Image ID** que la build de P2.5B (build reproducible). Etiqueta
  `org.opencontainers.image.revision=47bc129…`, `recipe_revision=r3`. Healthcheck `/api/ping`.
- La imagen productiva `danyseve1/bracket-bjj:e6abd7d-r3` **no se ha reetiquetado ni sobrescrito**.
- Los tres digests se resolvieron de nuevo contra el registry (`docker manifest inspect -v`):
  `arm64/linux` en los tres, `MediaType: application/vnd.docker.distribution.manifest.v2+json`.
- Validaciones de las imágenes release: Bridge `User=bridge`, `WorkDir=/app`, puerto 8500,
  `HEALTHCHECK /health`, sin `pytest`/`mypy`/`ruff` en la imagen y `requirements.txt` pinado;
  Scoreboard `User=node`, puerto 3000, `HEALTHCHECK /health` (modo integrado con persistencia).

### 20.2 Compose fijado por digest

| Servicio | Antes | Después |
| --- | --- | --- |
| `bracket` | `danyseve1/bracket-bjj@sha256:e07ec8b4…8df8` | `danyseve1/bracket-bjj@sha256:8e9f2ca2…e9e1` |
| `bridge-api` | `build: context: ./bridge-api` | `danyseve1/bjj-bridge-api@sha256:6b6d5327…37f6` |
| `scoreboard-tatami-1` | `build: context: ./services/scoreboard` | `danyseve1/bjj-scoreboard@sha256:024f0d5b…074e` |

Sin tags flotantes en los tres. El render base (sin perfil) es **idéntico** al anterior salvo
`bracket.image` (`bracket-postgres`, `nginx` y `wireguard` sin cambios; las diferencias de rutas
que aparecen al comparar contra el backup son un artefacto de resolver rutas relativas desde el
directorio del backup, no un cambio real).

**Consecuencia operativa (nueva respecto a P2.5B):** como el Bracket ya apunta al digest release,
un `docker compose up -d` **sin perfil** también recrea el Bracket — es el primer paso deliberado
de P2.5D. `--profile tatami1` es el comando que aplica el resto del release. P2.5C **no ejecuta
Compose** (solo `config`).

### 20.3 Secretos (.env productivo, modo 600; valores nunca registrados)

Añadidas (nombres; los valores no se imprimen ni se documentan):

- `SCOREBOARD_INTERNAL_TOKEN` — 64 hex, generado en el host con `openssl rand -hex 32`
- `SCOREBOARD_CONTROL_TOKEN` — 64 hex, distinto del anterior (verificado)
- `BRACKET_RESULT_WRITE_ENABLED=false`
- `SCOREBOARD_TATAMI_1_URL=http://scoreboard-tatami-1:3000`

No configuradas **a propósito** en el primer release: `BRACKET_WRITE_USERNAME`, `BRACKET_WRITE_PASSWORD`
(el Bridge arranca y funciona con `write=false` sin ellas). `SCOREBOARD_STATE_FILE=/state/state.json`
lo fija el propio Compose. El Bridge **no** recibe `SCOREBOARD_CONTROL_TOKEN` (no lo necesita);
el scoreboard recibe ambos tokens.

### 20.4 Directorio de estado

`/home/ubuntu/data/bjj-tournament-platform/tatami-1` → `owner 1000:1000`, modo `0700`, montado en
`/state`. El contenedor corre como `node` (uid 1000) y el propio Dockerfile hace `chown node:node /state`.
La escritura real del adapter en un directorio equivalente (uid 1000, `drwx------`) ya quedó
demostrada de punta a punta en el E2E aislado de P2.5B. **No se creó `state.json` a mano.**

### 20.5 Backups pre-despliegue

- **PostgreSQL** (sistema existente, `pre-p25d-20261002T101652Z`):
  `/home/ubuntu/backups/bjj-tournament-platform/postgres/pre-p25d-20261002T101652Z/`
  con `MANIFEST.txt`, `SHA256SUMS`, `bracket_dev.dump` (55 256 B, formato custom), `globals.sql`,
  `restore-list.txt`. Validación: `sha256sum -c SHA256SUMS` OK; `pg_restore -l` lista el archivo
  (167 entradas TOC; 15 `TABLE DATA`, coherente con las 15 tablas). Retención: **0 backups borrados**.
- **Compose y `.env`**: `/home/ubuntu/backups/bjj-tournament-platform/pre-p25d-20261002T101752Z/`
  con `docker-compose.yml.pre-p25d-…`, `.env.pre-p25d-…` (modo 600) y
  `evidence-pre-p25d-….txt` (snapshot textual sin secretos: contenedores, imágenes, digests, hashes,
  revisiones, conteos de BD y revisión Alembic).

### 20.6 Baseline de BD (solo lectura)

PostgreSQL **16.14** · Alembic **c1ab44651e79** · **2** torneos · **25** matches · **10** equipos ·
**16** rondas · **15** tablas → idéntico al baseline esperado. Sin escrituras ni migraciones.

### 20.7 WRITE gate

`BRACKET_RESULT_WRITE_ENABLED=false` (valor renderizado, verificado en `bridge-api`). El gate está
en `bridge-api/app/main.py:166`, **antes** de pedir credenciales o leer scoreboard/Bracket; el motivo
es `result_write_disabled` (`bridge-api/app/result_gate.py:50`) y el default de código es `False`
(`bridge-api/app/config.py:20`). Evidencia: **225 tests passed** en `bridge-api/tests` (incluye los
casos de la fase) y el E2E aislado de P2.5B (503 ×2, cero `PUT` al Bracket). La imagen release tiene
el mismo Image ID que la validada (`c2080cc6…`). No se ha tocado producción para comprobarlo.

### 20.8 Rollback (comandos preparados, NO ejecutados)

```sh
cd /home/ubuntu/projects/bjj-tournament-platform
B=/home/ubuntu/backups/bjj-tournament-platform/pre-p25d-20261002T101752Z

# 1) Bracket → digest productivo anterior (e07ec8b4…), retirando también los pines release
cp "$B/docker-compose.yml.pre-p25d-20261002T101752Z" docker-compose.yml
docker compose up -d bracket

# 2) Bridge y scoreboard: parar y retirar los servicios nuevos conservando el estado
docker compose --profile tatami1 stop bridge-api scoreboard-tatami-1
docker compose --profile tatami1 rm -f bridge-api scoreboard-tatami-1   # NO borra el bind mount /state

# 3) .env
cp "$B/.env.pre-p25d-20261002T101752Z" .env && chmod 600 .env
```

El digest de rollback del Bracket sigue disponible **en local** (`danyseve1/bracket-bjj:e6abd7d-r3`,
Image ID `09b19930bde2…`) y **en el registry** (`sha256:e07ec8b4…8df8` resuelve). El backup de
PostgreSQL se restauraría con el runbook existente (`docs/04-backup-restore.md`).

### 20.9 Checklist GO/NO-GO

| # | Criterio | Resultado |
| --- | --- | --- |
| 1 | Git limpio (`develop` == `origin/develop`, `92d52df`) | YES |
| 2 | Imágenes release publicadas | YES |
| 3 | Digests fijados en Compose | YES |
| 4 | arm64 validado (registry, los tres) | YES |
| 5 | Healthchecks validados (bracket `/api/ping`, bridge `/health`, scoreboard `/health`) | YES |
| 6 | Secretos preparados (`.env` 600, nombres verificados) | YES |
| 7 | `BRACKET_RESULT_WRITE_ENABLED=false` | YES |
| 8 | Directorio de estado preparado (1000:1000, 0700) | YES |
| 9 | Backup PostgreSQL válido | YES |
| 10 | Backups Compose/`.env` válidos | YES |
| 11 | Rollback exacto disponible | YES |
| 12 | Baseline de BD sano (2/25/10/16/15) | YES |
| 13 | Render de Compose correcto | YES |
| 14 | Producción sana | YES |
| 15 | Ninguna migración pendiente (`AUTO_RUN_MIGRATIONS=false`, Alembic en head) | YES |
| 16 | Ningún puerto público nuevo | YES |
| 17 | Tatami 2–6 fuera del render | YES |
| 18 | WireGuard fuera de cambio | YES |

### 20.10 Estado final

Producción intacta: los cuatro contenedores conservan **mismos IDs y `StartedAt`** y `restarts=0`; el
Bracket en ejecución sigue siendo la imagen `sha256:e07ec8b4…8df8` (`revision=e6abd7d…`). No se ejecutó
`docker compose up`, ni `recreate`, ni `restart`, ni `pull` seguido de `up`, ni cambios en nginx.
P2.5C termina **antes** del despliegue.

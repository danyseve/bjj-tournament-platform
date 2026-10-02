# 10 - Plan de release controlado del Tatami 1 (P2.5A)

Estado: **plan aprobable, sin ejecutar**. No se ha construido ninguna imagen de release, no se ha
publicado nada, no se ha tocado Compose, `.env`, nginx, WireGuard, PostgreSQL ni el Bracket productivo.

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
| Digest esperado tras build | **No es predecible**: se obtiene del build/push y se registra aquí. Mientras no exista, la línea del Compose queda con marcador `<TBD>` y **no se despliega** |
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

Estado actual del Dockerfile (revisado, sin modificar): `FROM python:3.12-slim`, `pip install -r
requirements.txt`, `COPY app ./app`, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8500`. Sin fijar
la base por digest, **sin usuario no-root**, sin `HEALTHCHECK`, sin check de dependencias.

Requisitos de la imagen release (a implementar en P2.5B, no en P2.5A):

1. Base `python:3.12-slim` **pinada por digest** (arm64).
2. Usuario no-root (mismo criterio que Bracket/scoreboard).
3. **`requirements.txt` pinado**: hoy son 5 líneas sin versión (`fastapi`, `uvicorn[standard]`,
   `httpx`, `pydantic`, `pydantic-settings`). Sin versiones fijas la imagen **no es reproducible**;
   es un prerrequisito de release (fijar versiones y, si se quiere, hash de las mismas).
4. `HEALTHCHECK` contra `GET /health` (existe y no pide token).
   Nota técnica: la imagen no instala `curl`/`wget` en sus propias capas y las bases `-slim` los purgan,
   así que el probe debe usar el intérprete ya presente, p. ej.
   `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8500/health').status==200 else 1)"`.
   El probe exacto se valida al implementarlo.
5. `EXPOSE 8500` documental; **sin publicar el puerto al host** (§7).

Tag propuesto: `danyseve1/bjj-bridge-api:<sha7-del-commit-principal>-r1` (el `sha7` concreto es el HEAD
en el momento del build; hoy sería `3b3ed63`, pero cambiará si P2.5B añade el flag y el healthcheck).

Variables (solo nombres; clasificación por obligatoriedad/opcionalidad/sensibilidad):

| Variable | Obligatoria | Sensible | Nota |
|---|---|---|---|
| `BRACKET_API_URL` | sí | no | valor operativo `http://bracket:8400/api` |
| `SCOREBOARD_TATAMI_1_URL` | sí | no | `http://scoreboard-tatami-1:3000`; el código trae default, pero debe fijarse explícitamente |
| `SCOREBOARD_INTERNAL_TOKEN` | **sí** | **SÍ** | el mismo valor que recibe el scoreboard; sin él los endpoints internos responden fail-closed |
| `BRACKET_RESULT_WRITE_ENABLED` | sí (con valor `false`) | no | **no existe en el código todavía** ⇒ prerrequisito PRE-DEPLOY (§10) |
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

Requisitos de la imagen release (P2.5B): tag/digest propio, `HEALTHCHECK` y etiqueta que registre
también el commit del repo principal (hoy solo etiqueta el submódulo `c49df6d…`).

### Persistencia productiva (diseño)

| Decisión | Valor |
|---|---|
| Ruta host propuesta | `/home/ubuntu/data/bjj-tournament-platform/tatami-1/` (**no existe hoy**, no se crea en P2.5A) |
| Alternativa descartada | `./data/tatami-1` dentro del repo (precedente de WireGuard): el árbol es un checkout git y `data/` está en `.gitignore`; se descarta para no mezclar estado de servicio con el repo y para que `git clean`/reclonados no puedan tocarlo |
| Mount | `-v /home/ubuntu/data/bjj-tournament-platform/tatami-1:/var/lib/bjj/tatami-1` |
| Fichero | `state.json` (una sola ruta; `SCOREBOARD_STATE_FILE=/var/lib/bjj/tatami-1/state.json`) |
| Ownership | `1000:1000` (usuario `node` de la imagen oficial; se valida funcionalmente con la prueba de persistencia de §14, sin contenedores desechables) |
| Permisos | directorio `0700`; el fichero lo fija el propio adapter a `0600` (`state-store.js`: `fchmodSync(handle, 0o600)`) |
| Escritura | atómica: fichero temporal + `fsync` + `rename` sobre la ruta final + `fsync` del directorio (best effort). El fichero final nunca queda a medias |
| Backup | copia de `state.json` (con `sha256sum` registrado) antes de cualquier cambio y en el preflight de cada ventana; el estado **no** está en PostgreSQL |
| Recovery: fichero ausente | arranque limpio (`state: null`); es el caso del primer release |
| Recovery: fichero corrupto/JSON inválido | `state-store.js` **lanza y no sobrescribe**: el servicio no arranca y conserva el fichero. Acción: copiar el corrupto a `state.json.corrupt-<ts>` y restaurar del backup, nunca dejar que la app lo pise |
| Recovery: permisos mal | fallo fail-closed al guardar; corregir ownership del directorio antes de reintentar |
| Alcance | **solo Tatami 1**; Tatami 2–6 no se habilitan ni se les diseña ruta |

---

## 6. COMPOSE TARGET (diseño; **no aplicado**)

Fichero: `docker-compose.yml` (el que realmente usan los contenedores productivos). Cambio mínimo,
Tatami 1 solamente.

```yaml
  bracket:
    # ÚNICA línea que cambia en un servicio existente:
    image: danyseve1/bracket-bjj@sha256:<TBD-DIGEST-RELEASE-47BC129>   # antes: …@sha256:e07ec8b4…8df8
    # el resto (healthcheck, depends_on, ports, environment, red, restart) se mantiene igual

  bridge-api:
    image: danyseve1/bjj-bridge-api@sha256:<TBD-DIGEST-RELEASE-BRIDGE>  # antes: build: ./bridge-api
    container_name: bjj-bridge-api
    profiles: ["tatami1"]                    # antes: ["multitatami"]
    depends_on:
      - bracket
      - scoreboard-tatami-1
    # ports: ELIMINADO (sin publicación al host, §7)
    environment:
      BRACKET_API_URL: http://bracket:8400/api
      SCOREBOARD_TATAMI_1_URL: http://scoreboard-tatami-1:3000
      SCOREBOARD_INTERNAL_TOKEN: ${SCOREBOARD_INTERNAL_TOKEN:?requerido}
      BRACKET_RESULT_WRITE_ENABLED: "false"   # §10: arranque en modo lectura
      # sin BRACKET_WRITE_USERNAME/PASSWORD: la escritura queda doblemente impedida
    healthcheck:                              # NUEVO
      test: ['CMD-SHELL', 'python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen(\"http://127.0.0.1:8500/health\").status==200 else 1)"']
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    networks:
      - bjj-net
    restart: unless-stopped

  scoreboard-tatami-1:
    image: danyseve1/bjj-scoreboard@sha256:<TBD-DIGEST-RELEASE-SCOREBOARD>  # antes: build: ./services/scoreboard
    container_name: scoreboard-tatami-1
    profiles: ["tatami1"]                     # antes: ["multitatami"]
    # ports: ELIMINADO (sin publicación al host, §7)
    environment:
      SCOREBOARD_MODE: integrated
      SCOREBOARD_INTERNAL_TOKEN: ${SCOREBOARD_INTERNAL_TOKEN:?requerido}
      SCOREBOARD_CONTROL_TOKEN: ${SCOREBOARD_CONTROL_TOKEN:?requerido}
      SCOREBOARD_STATE_FILE: /var/lib/bjj/tatami-1/state.json
    volumes:                                  # NUEVO
      - /home/ubuntu/data/bjj-tournament-platform/tatami-1:/var/lib/bjj/tatami-1
    healthcheck:                              # NUEVO (la imagen no trae curl/wget; se usa node)
      test: ['CMD', 'node', '-e', 'fetch("http://127.0.0.1:3000/").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))']
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    networks:
      - bjj-net
    restart: unless-stopped

  # scoreboard-tatami-2 … -6 : SIN CAMBIOS (siguen en `profiles: ["multitatami"]`, sin habilitar)
```

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

- Flag propuesta: `BRACKET_RESULT_WRITE_ENABLED`, booleana, **default `false`**.
- **Estado en el código a día de hoy: no existe** (`bridge-api/app/config.py` no la define). Por tanto
  es un **requisito PRE-DEPLOY** y **no se implementa en P2.5A** (§10 lo pide así explícitamente).
- Comportamiento a implementar en P2.5B: leída en `config.py`, con `false` por defecto; si está
  desactivada, `POST /tatamis/{id}/result` responde 503 con un motivo explícito
  (`result_write_disabled`) **sin leer el scoreboard y sin tocar Bracket**. Los caminos de lectura
  (`/health`, `/health/bracket`, `/tatamis/1/candidates`, `/tatamis/1/assign-match`) no se ven
  afectados: el release arranca en modo lectura/asignación.
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

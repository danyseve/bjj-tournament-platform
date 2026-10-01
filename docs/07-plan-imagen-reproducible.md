# 07 — Plan de imagen Bracket reproducible (P1.2b)

Estado: **receta construida, validada y publicada (release candidate `r3`, digest
`sha256:e07ec8b4…8df8`); pendiente de desplegar**.
Este documento acompaña a `docker/bracket-bjj/Dockerfile` (receta propia, revision `r3`) y a
`docker/bracket-bjj/Dockerfile.dockerignore`. Producción sigue intacta: la imagen validada
**no** se ha desplegado (ver sección 14).

Referencias: `docker/bracket-bjj/Dockerfile.legacy` (receta histórica parchada),
`docs/06-imagen-custom-bracket.md` (qué se desplegó y por qué), y
`docs/decisions/ADR-004-bracket-image-reproducibility.md` (decisión de estrategia).

---

## Validation status: RELEASE CANDIDATE

Candidata final: **`danyseve1/bracket-bjj:e6abd7d-r3`** (revisión de receta `r3`),
construida y validada el 2026-10-01 sobre una pila sombra con PostgreSQL restaurado
(`127.0.0.1:18400`), sin tocar producción.

| Comprobación | Estado |
|---|---|
| ARM64 | ✅ `linux/arm64` (builder nativo, sin QEMU) |
| non-root | ✅ `User=bracket` (uid 100 / gid 101, usuario de sistema) |
| healthcheck real | ✅ `/api/ping` (`--interval=30s --timeout=5s --retries=3 --start-period=20s`), `healthy` |
| frontend `/api` | ✅ bundle sin `http://localhost:8400/api` (0 ocurrencias, verificado también servido) |
| PostgreSQL shadow restore | ✅ dump `pre-p12b-20261001T180912Z` restaurado (15 tablas, 178 entradas TOC) |
| API functional comparison | ✅ equivalencia funcional con producción (torneos, jugadores, combates, rounds/standings) |
| schema drift = 0 | ✅ `pg_dump --schema-only` idéntico antes/después; alembic `c1ab44651e79` |
| production untouched | ✅ los 4 contenedores con los mismos IDs, `StartedAt` y `restarts=0` |

Detalle de permisos: **0 ficheros/directorios reales world-writable bajo `/app`** en build y
en runtime; `/app/.venv/.lock` en `0640`; caché de uv en `/tmp/uv-cache` (modo `0700`,
`bracket:bracket`) con su lock dinámico en `/tmp/uv-cache/.lock`; `BRACKET_PUBLIC_BASE_URL`
eliminado definitivamente y `BASE_URL` **no** configurado (el campo no tiene consumidores
funcionales en el código: única aparición, su definición en `config.py`).

---

## 1. Objetivo

Sustituir la imagen legacy (`danyseve1/bracket-bjj:0.1.0`, root, parcheada con `sed`
sobre el bundle y sobre `config.py`) por una imagen propia construida desde el código
fuente del submódulo, con:

- instalación reproducible (lockfiles verificados por SHA256 en el propio build);
- `VITE_API_BASE_URL=/api` inlineado en compilación, sin `sed`;
- usuario no root y permisos mínimos (sin `chmod 777`);
- bases de imagen y `uv` fijadas por **digest**;
- healthcheck real sobre `/api/ping`.

---

## 2. Estado de partida (verificado el 2026-10-01)

| Elemento | Valor |
|---|---|
| Rama | `develop` @ `f4645f9` (árbol limpio, = `origin/develop`) |
| Submódulo `services/bracket` | `e6abd7d282850f9d13d9122494767d4dbcb139ef` (gitlink en `develop`) |
| Imagen en uso | `danyseve1/bracket-bjj:0.1.0` = `a773917e9c4b…`, `User=root`, `HOME=/app`, `UV_CACHE_DIR=/tmp/uv-cache` |
| Base upstream de la legacy | `ghcr.io/evroon/bracket@sha256:0a5b9ea1…`, contenido del commit `1522734d2c71e1ed0f41c71c55b1d6b5a4a3662d` (label `version=v3.0.0-rc1`) |
| Runtime | 4 contenedores (`bracket`, `bracket-postgres`, `bjj-nginx`, `wireguard`), `restarts=0`, `bracket` healthy |
| PostgreSQL | 16.14, alembic `c1ab44651e79` |
| Host | `robledo01` (oracle-jiujitsu), Ubuntu 22.04, **aarch64**, 2 vCPU / 11 GiB, Docker 29.8.2, Compose v5.5.1, BuildKit v0.33.1, buildx v0.37.1 |
| Parche que se elimina | `grep -RIl "http://localhost:8400/api" /app/frontend-dist \| xargs sed -i …` + `sed -i "s#http://localhost:8400#${BRACKET_PUBLIC_BASE_URL}#g" /app/bracket/config.py` + `chmod -R 777 /app/.cache /tmp/uv-cache` |

---

## 3. Decisión de fuente: construir desde `e6abd7d` (opción B)

Comparación medida entre `1522734d` (contenido de la imagen desplegada) y `e6abd7d`
(estado del submódulo en `develop`): **164 commits**, del 2025-12-29 al 2026-05-11,
todos de autoría GitHub (dependabot + PRs upstream: **no hay commits propios** del fork
en el rango ⇒ el submódulo es espejo de `upstream/master`).

| Dimensión | Resultado |
|---|---|
| Migraciones alembic | **0 ficheros cambiados**, head idéntico `c1ab44651e79` = la versión ya aplicada en producción ⇒ **sin cambio de esquema** |
| Código backend | 3 ficheros, +7/−8 líneas (`routes/auth.py`, `routes/tournaments.py`, `utils/starlette.py`) |
| Código frontend | 1 fichero, 2 líneas (`src/components/utils/types.tsx`) + `vite.config.ts` (−1 `@ts-ignore`) |
| `config.py` | **idéntico** en ambos commits y su `base_url` **no se usa** en ningún sitio del backend ⇒ el `sed` de la legacy era un **no-op** |
| Dependencias backend | starlette 0.49.1 → **1.0.0**, fastapi 0.128.0 → 0.135.3, gunicorn 23 → 25.3.0, uvicorn 0.40 → 0.44.0, alembic 1.17.1 → 1.18.0, pyjwt, python-multipart, sentry-sdk, aiohttp… |
| Dependencias frontend | i18next 25 → **26**, @mantine/form 8.3.7 → **9.0.1**, @hcaptcha 1.17 → **2.0.2**, @vitejs/plugin-react 5.1 → **6.0.1**, react-i18next 16.5 → 17, axios 1.13 → 1.15 |
| Dockerfiles upstream | node 24 → 25 y `corepack enable` → `apk add pnpm` (sin versión). El resto igual |
| Metadata de versión | El submódulo **no tiene tags** (`git describe` falla) y `pyproject` dice `version = "0.0.1"` ⇒ no hay versión semántica utilizable |

**Se construye desde `e6abd7d` porque:**

1. No hay riesgo de datos: **cero migraciones** y mismo head ⇒ la equivalencia que
   buscaba la opción A no cubre ningún riesgo real de esquema.
2. El delta de código es mínimo (1 línea de negocio en backend, 2 en frontend).
3. Construir desde `1522734d` produciría una imagen cuya fuente **no** coincide con el
   gitlink de `develop`: justo el problema (imagen no reproducible desde el repo
   versionado) que P1.2b existe para resolver.
4. `1522734d` congelaría dependencias ya obsoletas (se perderían los bumps de
   seguridad del rango: urllib3, python-multipart, aiohttp, sentry-sdk, axios…).
5. La equivalencia que importa es **funcional**, y el despliegue actual ya no es el
   build upstream limpio (su bundle va parcheado con `sed`): ni A ni B reproducen ese
   bundle al byte.

**Contingencia documentada (no ejecutada):** si la validación funcional falla por las
dependencias nuevas, se aplica la **misma receta** sobre un `git worktree` del
submódulo en `1522734d` (sin cambiar el gitlink), en una revisión de receta aparte
(`e6abd7d-c1`; no se usa `r*`, reservado para las revisiones de nuestra receta).

---

## 4. Pines exactos (verificados read-only, sin construir)

Consulta de manifiestos (`docker manifest inspect`, solo metadatos, sin descargar capas):

| Elemento | Pin | Notas |
|---|---|---|
| Node (frontend) | `node:24-alpine@sha256:38a36422dc7de80f3ced964270f23b3b17f73af816728d21a5fbbf84bf8be46f` | digest de `linux/arm64/v8`; el `amd64` es `83f1c388…`. **24 y no 25**: `frontend/.nvmrc` = `v24.3.0`, el CI usa node 22, y node 25 **elimina corepack** (por eso upstream pasó a `apk add pnpm`) |
| Python (runtime) | `python:3.14-alpine3.22@sha256:27b691f87878a079100a3d8fafcd66b3c54d931598f307bcb54617c395f5b43c` | digest de `linux/arm64/v8`; coincide con la base de la imagen que hoy corre (Python 3.14.2) |
| uv | `ghcr.io/astral-sh/uv:0.9.19@sha256:d1581c59da88776d0fc36f03e251cb4516b15cf3e40144388f87a3b95221f7ec` | digest de `linux/arm64` del **tag exacto 0.9.19** (el `amd64` es `ec93073f…`). **Nunca `latest`.** La versión sale de la propia imagen en producción: `uv --version` = 0.9.19 |
| pnpm | **9.15.9** (`corepack prepare pnpm@9.15.9 --activate`) | ver justificación abajo |
| `uv.lock` | `sha256:24f99c8ebd6ea33363e2edaa971246c82af6e371eba3ad167c338333351df242` | comprobado **antes y después** de `uv sync` |
| `pnpm-lock.yaml` | `sha256:001f9b8ee4b410e82dc9f2296605469196b878306810c74e7f4f0bf87e4984af` | comprobado **antes y después** de `pnpm install` |
| Código | submódulo `e6abd7d282850f9d13d9122494767d4dbcb139ef` (`package.json` `4d40d44b…`, `pyproject.toml` `220af672…`) | fijado por el gitlink de `develop` |

**¿Por qué pnpm 9.15.9 y no otro?**

- El `pnpm-lock.yaml` del repo declara `lockfileVersion: '9.0'`, formato **introducido y
  escrito por la rama 9.x** de pnpm.
- El proyecto **no declara** `packageManager` en `package.json` (no existe hoy ni existió
  nunca: `git log -S'packageManager' -- frontend/package.json` no devuelve nada) y no hay
  `.npmrc` ni `pnpm-workspace.yaml`, así que la versión no viene fijada por el repo.
- El CI del upstream (`frontend.yml`, `docs-build.yml`) hace `corepack enable` sobre node
  22 sin versión explícita; la receta Dockerfile de la etapa 1 original también usaba
  corepack. `9.15.9` es el último release de la rama 9.x (`dist-tags.latest-9` en el
  registro npm, publicado el 2025-03-10), es decir, el cierre estable de la rama cuyo
  formato usa el lockfile.
- No se usa `pnpm@9.x.y` ni `apk add pnpm` (paquete sin versión, cambia con la versión de
  Alpine). pnpm 10.x también acepta `lockfileVersion 9.0`, pero es un salto de
  comportamiento que en esta receta no es necesario: se evita.
- Validación en el primer build: las dos comprobaciones SHA256 del lockfile (antes y
  después de `pnpm install --frozen-lockfile`) demuestran que el lockfile **no** se
  reescribe.

Todas las variables usadas en el Dockerfile están declaradas con `ARG` y valor por
defecto; el propio hash va como valor por defecto (no hay placeholders):

```
PNPM_VERSION=9.15.9
PNPM_LOCK_SHA256=001f9b8e…84af
UV_LOCK_SHA256=24f99c8e…f242
VITE_API_BASE_URL=/api
BRACKET_UPSTREAM_COMMIT=e6abd7d282850f9d13d9122494767d4dbcb139ef
RECIPE_REVISION=r3
```

---

## 5. Arquitectura ARM64

Confirmado sin construir, por tres vías:

1. Los manifiestos de `node:24-alpine`, `python:3.14-alpine3.22` y `ghcr.io/astral-sh/uv:0.9.19`
   publican `linux/arm64` (`node`/`python` como `arm64/v8`) — digests en la tabla anterior.
2. El builder del host es **nativo arm64** (`linux/arm64`, BuildKit v0.33.1): no hace falta
   QEMU ni emulación para construir.
3. La imagen que hoy corre es `arm64` y está construida sobre esas mismas familias de base.

No hay ninguna dependencia solo-amd64: `uv.lock` resuelve ruedas para aarch64 y los
binarios de esbuild/rollup que usa `pnpm-lock.yaml` publican arm64. **Se publica solo
arm64**; el único consumidor es este host.

---

## 6. Receta (`docker/bracket-bjj/Dockerfile`)

Dos etapas, contexto = raíz del repo:

```
docker build -f docker/bracket-bjj/Dockerfile -t danyseve1/bracket-bjj:e6abd7d-r3 .
```

Revisiones de la receta (mismo commit de submódulo, `RECIPE_REVISION` en el `ARG`):

| Revisión | Cambio |
|---|---|
| `r1` | receta multi-etapa propia: pines por digest, SHA256 de lockfiles, usuario no root, healthcheck real, bundle sin `sed` |
| `r2` | elimina el único fichero real world-writable horneado (`/app/.venv/.lock`, `0666`) con `chmod 640` y una guardia que **falla el build** si aparece un conjunto inesperado de entradas reales world-writable bajo `/app` |
| `r3` | mueve la caché de uv a `/tmp/uv-cache` (`0700`, `bracket:bracket`): el `.lock` que `uv run` crea al arrancar deja de aparecer bajo `/app` (era el único world-writable en runtime) |

Etapa 1 — frontend (`node:24-alpine` por digest):
- `corepack enable` + `corepack prepare pnpm@9.15.9 --activate`;
- copia `package.json` + `pnpm-lock.yaml`, verifica SHA256, `pnpm install --frozen-lockfile`,
  vuelve a verificar SHA256 (prueba de que el lockfile no se reescribe);
- copia el resto del frontend y compila con `VITE_API_BASE_URL=/api` (variable de **build**);
- **el build falla** si aparece `http://localhost:8400/api` en `dist` (sin `sed`).
- (El `NODE_ENV=production` del upstream se activa **después** de `pnpm install`: con pnpm 9.15.9
  antes de instalar, pnpm omitiría las devDependencies y `vite` no existiría → `vite: not found`.)

Etapa 2 — runtime (`python:3.14-alpine3.22` por digest, `uv 0.9.19` por digest):
- `uv sync --no-dev --locked --no-install-project` (dependencias) y después
  `uv sync --no-dev --locked` (con el código); SHA256 de `uv.lock` verificado antes y después;
- **sin** parche de `config.py`, **sin** `BRACKET_PUBLIC_BASE_URL` (era un ARG de la receta
  legacy con efecto nulo) y **sin** `BASE_URL` (el campo no tiene consumidores funcionales);
- `dist` copiado a `/app/frontend-dist` (ruta que espera `app.py`);
- usuario de sistema `bracket`, `HOME=/app`, `UV_CACHE_DIR=/tmp/uv-cache` (`r3`) con modo `0700`
  y propietario `bracket:bracket`; `/app/.venv/.lock` en `0640`; ninguna ruta con permisos 777;
  guardia de world-writables en el build; cachés de compilación vía `--mount=type=cache`
  (no entran en la imagen);
- `EXPOSE 8400`; `HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s`
  sobre `wget -q -O - http://127.0.0.1:8400/api/ping | grep -q '"ping"'`;
- `CMD` equivalente al actual: `uv run --no-dev --locked -- gunicorn -k uvicorn.workers.UvicornWorker bracket.app:app --bind 0.0.0.0:8400 --workers 1`;
- etiquetas OCI + propias (`com.danyseve.bracket.*`) con commit upstream, revisión de receta,
  versión de pnpm y hashes de ambos lockfiles.

`docker/bracket-bjj/Dockerfile.dockerignore` protege el contexto (que es la raíz, donde vive
`.env`) frente a: `.env` / `.env.*` / `**/.env*`, `.git` / `.gitmodules`, `backups/**`,
volcados (`*.dump`, `*.sql*`, `*.tar*`, `*.bak`), `data/**`, `**/node_modules`, `**/.venv`,
`**/__pycache__`, `**/*.py[cod]`, cachés (`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.cache`),
`services/scoreboard/**`, `bridge-api/**`, `nginx/**`, `wireguard/**`, `scripts/**`,
`docker-compose*.yml` y documentación. **No excluye** los paths que el build necesita
(`services/bracket/frontend/**`, `services/bracket/backend/**`), salvo dotfiles concretos y
artefactos.
Nota: excluye `services/bracket/frontend/.env.development` (fichero versionado del upstream con
claves públicas de analytics/hcaptcha); es deliberado y no altera el bundle, porque
`vite build` en modo production solo lee `.env` y `.env.production`.
Tampoco se excluye ningún `.gitignore` del árbol: mantener `backend/static/.gitignore` en el
contexto garantiza que exista `/app/static` en la imagen, igual que hoy (`app.py:155` monta
`StaticFiles(directory="static")`; el propio Dockerfile añade `mkdir -p /app/static` como
defensa en profundidad).

---

## 7. Estrategia de tags

```
danyseve1/bracket-bjj:e6abd7d-r3   <- tag final validado (release candidate)
                 └──────┘ └┘
      commit del submódulo (7)  revisión propia de la receta
```

- `e6abd7d` = commit del submódulo con el que se construyó; `r3` = revisión actual de
  **nuestra** receta/ajustes (`r1` → receta inicial, `r2` → world-writable horneado, `r3` →
  caché de uv fuera de `/app`). Sube a `r4`, `r5`… si cambia el Dockerfile, los pines o los
  args **sin** cambiar el commit del submódulo.
- No hay versión semántica upstream utilizable (sin tags, `pyproject` dice `0.0.1`, el
  `v3.0.0-rc1` es un label viejo de la base) ⇒ el SHA es la referencia honesta. Si algún
  día existe tag upstream, el formato pasaría a `vX.Y.Z-<sha7>-r<n>`.
- **Nunca `latest` para desplegar**: el Compose usa el tag explícito y, tras publicar, el
  **digest** inmutable. `latest`, si se publica, es solo conveniencia y apunta a la última
  build validada.
- Se publica **solo arm64**; queda documentado en el registro para que nadie lo baje en amd64.
- Registro: **Docker Hub `danyseve1/bracket-bjj`** (ya tiene credenciales en el host), para
  no depender del PAT de GitHub que está aparcado hasta el final del proyecto. GHCR queda
  como opción futura.

---

## 8. Compose futuro (propuesta; **no aplicada**)

```yaml
  bracket:
    image: danyseve1/bracket-bjj:e6abd7d-r3     # tras publicar -> @sha256:<digest> (ver sección 14)
    build:
      context: .
      dockerfile: docker/bracket-bjj/Dockerfile
      args:
        VITE_API_BASE_URL: /api
    healthcheck:
      test: ['CMD-SHELL', 'wget -q -O - http://127.0.0.1:8400/api/ping | grep -q "\"ping\""']
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    environment:
      ENVIRONMENT: "PRODUCTION"
      PG_DSN: postgresql://${POSTGRES_USER}:***@bracket-postgres:5432/${POSTGRES_DB:-bracket_dev}
      JWT_SECRET: ${JWT_SECRET}
      CORS_ORIGINS: "…"
      SERVE_FRONTEND: "true"
      API_PREFIX: "/api"
      # VITE_API_BASE_URL: ELIMINADA del runtime (es variable de build)
      # BRACKET_PUBLIC_BASE_URL: no existe (era ARG del Dockerfile legacy)
```

- `build:` + `image:` juntos permiten construir en el host y etiquetar con el nombre del
  registro. Cuando la imagen esté publicada, el despliegue debe usar la del registro
  (`pull_policy: missing`) y el bloque `build:` puede retirarse.
- `BRACKET_IMAGE` **no existe hoy** en el Compose (la imagen está fija en la línea 35). Para
  el cambio recomendado: editar esa línea (versionado y revisable) en lugar de introducir una
  variable nueva en `.env` (requeriría autorización aparte).
- Variables que siguen siendo runtime (las lee `pydantic-settings`): `ENVIRONMENT`, `PG_DSN`,
  `JWT_SECRET`, `CORS_ORIGINS`, `SERVE_FRONTEND` (sin ella no se monta el SPA), `API_PREFIX=/api`.
  Opcionales no usadas hoy: `SENTRY_DSN`, `CAPTCHA_SECRET`, `ALLOW_USER_REGISTRATION`,
  `ADMIN_EMAIL`/`ADMIN_PASSWORD` (solo bootstrap inicial).

---

## 9. Sandbox de validación (PostgreSQL restaurado) y prohibición de usar producción

**Prohibido**: arrancar la candidata con el `PG_DSN` de producción, unirla a la red
`bjj-net` o apuntarla al volumen `bracket_postgres_data`. Motivo: `config.py` trae
`auto_run_migrations = True` y `app.py` ejecuta alembic al arrancar; hoy no habría delta,
pero es el accidente que hay que hacer imposible por diseño.

**Ejecutado el 2026-10-01** (pila sombra aislada; red y volumen propios, **nunca** los de
producción):
1. Red `bjj-p12b-test` y volumen nuevo `bjj-p12b-pgdata`.
2. `postgres:16` como `bracket-p12b-postgres` (sin puerto publicado, credenciales de prueba
   distintas de las de producción, guardadas fuera del repo en `/home/ubuntu/p12b-shadow/`),
   con el dump del backup `pre-p12b-20261001T180912Z` restaurado (`pg_restore`, 178 entradas
   TOC, 15 tablas). Los datos son una **copia**.
3. Candidata como `bracket-p12b` con `PG_DSN` del postgres de prueba,
   **`AUTO_RUN_MIGRATIONS=false`**, `SERVE_FRONTEND=true`, `API_PREFIX=/api`, `JWT_SECRET` de
   prueba, y puerto publicado **solo en loopback**: `127.0.0.1:18400:8400`.
4. Con `AUTO_RUN_MIGRATIONS=false`, la candidata no puede tocar esquema ni datos ajenos. La
   prueba del camino de migración se hizo comprobando `alembic_version` en la **copia**
   (head ya `c1ab44651e79`) y el `--schema-only` antes/después.
5. La pila sombra **se conserva** hasta cerrar el despliegue (contenedores, volumen, red y
   logs en `/home/ubuntu/p12b-shadow/`); al final se eliminarán **solo** los recursos
   `*-p12b*`. El proyecto `bjj-tournament-platform` no se toca y nunca se usa `down -v`.
6. Resultados: usuario de PRUEBA creado y usado para el login (nunca credenciales
   productivas); producción intacta en todo momento (mismos IDs, `StartedAt` y `restarts=0`).

---

## 10. Checklist funcional (candidata vs. actual, antes de desplegar)

Baseline `127.0.0.1:8400`; candidata `127.0.0.1:18400`. **Ejecutado el 2026-10-01** contra la
pila sombra (sección 9); producción solo se consultó (lecturas), nunca se modificó.

| # | Comprobación | Criterio |
|---|---|---|
| 1 | `GET /` | 200 `text/html`, SPA con `#root` |
| 2 | `GET /api/ping` | 200 JSON `"ping"` en ambas |
| 3 | `GET /api/openapi.json` | diff contra el actual y contra `backend/openapi/openapi.json`: sin rutas/campos eliminados |
| 4 | Login | 200 + token con un **usuario creado en la BD de prueba** (nunca credenciales productivas); `401` con token inválido |
| 5 | Torneos | mismos IDs/campos/conteos que el baseline |
| 6 | Jugadores | 16 jugadores, mismos campos |
| 7 | Combates | 15 combates + rounds/standings con estructura idéntica |
| 8 | PostgreSQL / Alembic | `alembic current` = `c1ab44651e79`; `pg_dump --schema-only` idéntico antes y después de arrancar (prueba de que no hubo DDL) |
| 9 | Assets | `/assets/*.js|css` 200; `grep -rl "http://localhost:8400/api" /app/frontend-dist` **vacío** |
| 10 | Healthcheck | `healthy` en ~60 s, `FailingStreak=0` |
| 11 | Usuario | `docker inspect --format '{{.Config.User}}'` = `bracket`; `id -u` ≠ 0 |
| 12 | Permisos | sin modos 777: `find /app -perm -0002` vacío (0 entradas reales, en imagen y en runtime); caché uv `/tmp/uv-cache` `0700` de `bracket:bracket`; `.venv/.lock` `0640` |
| 13 | Logs | sin tracebacks ni 500; 1 worker, bind `0.0.0.0:8400` |
| 14 | Recursos | RSS del mismo orden que el actual (±20 %) |
| 15 | nginx | nginx de prueba → candidata: `/` 200 y `/api/ping` 200; tras desplegar, con el nginx productivo (`Host: bjj.local`) |
| 16 | WireGuard | tras desplegar, desde el cliente por el túnel: `http://bjj.local:8080/` y `/api/ping` 200 |
| 17 | Rollback | probado en la pila de prueba (ver sección 11) |

Diferencias en 1–9 son bloqueantes.

Resultado de la ejecución (candidata r3 vs producción; checks 1–14 ejecutados sin diferencias
bloqueantes; 15–17 pendientes del despliegue):

| # | Resultado |
|---|---|
| 1–3 | `/` 200 (SPA), `/api/ping` 200 `"ping"`, `/openapi.json` 200 (80.672 B) — iguales a producción |
| 4 | login con el usuario **de prueba** de la sombra OK; 401 con credenciales inválidas |
| 5–7 | torneos 1, jugadores 16, equipos 8, stages 2 / stage_items 3 / rounds 8 / matches 15 == BD sombra == BD producción |
| 8 | alembic `c1ab44651e79` en sombra y producción; `--schema-only` idéntico antes/después (15 tablas) |
| 9 | assets 200 (bundle 1.156.506 B); `grep` de `http://localhost:8400/api` en el bundle servido: **0** |
| 10 | healthcheck `healthy` |
| 11–12 | `User=bracket`, `id -u` = 100; **0 entradas reales world-writable** bajo `/app` en imagen y en runtime; `/app/.venv/.lock` `0640`; caché uv en `/tmp/uv-cache` (`0700`) |
| 13–14 | logs sin tracebacks ni 500; RSS 125,3 MiB (candidata) vs 180,2 MiB (producción) |
| 15–16 | **no probados** (requieren el nginx productivo / túnel WireGuard; se harán tras el despliegue) |
| 17 | rollback: pendiente de probar en el despliegue |

---

## 11. Rollback

1. **Runtime**: `image:` vuelve a `danyseve1/bracket-bjj:0.1.0` (o al digest registrado) y
   `docker compose up -d --no-deps --force-recreate bracket`. La imagen legacy sigue en el
   host (`a773917e9c4b`, 4 tags) y no se borra.
2. **Git**: el cambio de Compose es de una línea; revert del commit correspondiente.
3. **Datos**: backup `pre-*` previo al cambio; como no hay migraciones, la restauración no
   debería ser necesaria. En caso extremo: `pg_restore` del dump `pre-*` con los
   procedimientos de `04-backup-restore.md`.
4. **Nunca** `docker compose down -v` (destruiría `bracket_postgres_data`).

---

## 12. Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| `auto_run_migrations=True` al arrancar (mecanismo idéntico al de la imagen actual) | Sandbox con copia y `AUTO_RUN_MIGRATIONS=false`; backup `pre-*` antes de desplegar; valorar fijarlo a `false` en producción (cambio aparte) |
| Bumps de dependencias (starlette 1.0.0, fastapi 0.135; i18next 26, @mantine/form 9, @hcaptcha 2, @vitejs/plugin-react 6) | Es el delta real y va ejercitado por el CI upstream; validación funcional 3–7 en sandbox (superada); contingencia `e6abd7d-c1` desde `1522734d` |
| `pnpm 9.15.9` frente a un lockfile mantenido por pnpm 10 en el upstream | Doble comprobación SHA256 del lockfile en el build; si fallara, se sube el pin (cambio de receta → nueva revisión `r4`) |
| node 25 (upstream) vs node 24 (nosotros) | 24 coincide con `.nvmrc` v24.3.0 y mantiene corepack; sin impacto funcional esperado |
| Permisos no root: `uv run` o el SPA pueden necesitar escribir en `HOME`/caché | `HOME=/app`; caché de uv en `/tmp/uv-cache` (`0700`, `bracket:bracket`), fuera de `/app`; `uv` crea ahí su `.lock`; checks 11–12 |
| Caches de compilación | `--mount=type=cache` (no entran en la imagen); ninguna ruta con 777 |
| Publicación arm64-only | Documentado; el único consumidor es arm64 |
| Deriva entre nuestra receta y el upstream | La doble verificación de hashes hace **fallar el build** si el submódulo cambia sin revisar la receta |
| Contexto de build con secretos | `Dockerfile.dockerignore` excluye `.env*`, `.git` y backups; nunca `COPY .` |

---

## 13. Próximos pasos (cada uno con autorización y parada)

1. ~~Build local (sin publicar)~~ **hecho**: `r1` → `4c19b86e2c46`, `r2` → `cb314de72c47`,
   `r3` → `09b19930bde2` (esta última es la candidata).
2. ~~Inspección de la imagen~~ **hecho** (Usuario, healthcheck, CMD, etiquetas, permisos,
   bundle y guardia de world-writables).
3. ~~Sandbox con PostgreSQL restaurado + checklist funcional~~ **hecho** (secciones 9–10).
4. ~~Publicación en Docker Hub~~ **hecho**: `danyseve1/bracket-bjj:e6abd7d-r3` + digest
   registrado (sección 14).
5. ~~Cambio del Compose **por digest** con backup `pre-*` y rollback listo~~ **hecho**
   (2026-10-01T18:43:47Z; recreado **solo** `bracket`; cadena nginx → bracket → PostgreSQL validada).
6. ~~Merge de la rama a `develop` por fast-forward y actualización de
   `docs/06-imagen-custom-bracket.md`~~ **hecho** (`develop` = `ebd1215`).

Estado final y retirada del sandbox: sección 15.

---

## 14. Publicación y despliegue

**Estado** (histórico de esta sección): **publicada** en Docker Hub el 2026-10-01 18:35–18:36 UTC.
El despliegue en producción y el cierre de P1.2 se registran en la sección 15.

Registro: `danyseve1/bracket-bjj` (Docker Hub, cuenta `danyseve1`; credenciales ya
configuradas en el host, nunca en el repo).

```bash
docker push danyseve1/bracket-bjj:e6abd7d-r3
# -> digest del manifest (se anota abajo)
```

| Campo | Valor |
|---|---|
| Tag publicado | `danyseve1/bracket-bjj:e6abd7d-r3` |
| RepoDigest | `danyseve1/bracket-bjj@sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8` |
| Fecha UTC de publicación | 2026-10-01T18:35:38Z → 18:36:00Z (`docker push` exit 0) |
| Arquitectura | `linux/arm64` (variant v8), manifest *single-platform* `application/vnd.docker.distribution.manifest.v2+json`, 16 capas, 3662 B de manifest, 331 MB |
| Image ID local | `sha256:09b19930bde296aeb2d84851d67d91c61153599f166c92dfb68577c623e712df` (= digest del *config* del manifest remoto: verificación de que lo publicado es exactamente lo validado) |
| Commit de la receta | `4107d4a1289615c0c268a73e095240c86d230936` (rama `chore/bracket-image-reproducible`); el presente documento se actualiza en `b902049cdda54152819f4509dbe8a5730f7ed591` y en el commit que añade este digest |
| Upstream (submódulo) | `e6abd7d282850f9d13d9122494767d4dbcb139ef` |
| Recipe revision | `r3` |

Verificación del digest por tres vías coincidentes:
1. salida de `docker push`: `e6abd7d-r3: digest: sha256:e07ec8b4…8df8 size: 3662`;
2. `docker image inspect … --format '{{json .RepoDigests}}'` →
   `["danyseve1/bracket-bjj@sha256:e07ec8b4…8df8"]`;
3. `docker buildx imagetools inspect` y `docker manifest inspect -v` (remoto) → mismo digest,
   `platform: linux/arm64/v8`, `config.digest = sha256:09b19930bde2…` (el Image ID local).

El tag `latest` del repositorio **no** lo hemos tocado: sigue apuntando a
`sha256:38569b93ab2ab72af4b3cb98b8b49d1509facdedda6cfabf70bf1b712fed6bfc` (imagen legacy,
pre-existente). No se han publicado `r1`, `r2` ni `0.1.0`.

Regla: el tag `e6abd7d-r3` es el que se validó; el Compose deberá fijar
`danyseve1/bracket-bjj@sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8`
(no el tag móvil).

---

## 15. Cierre de P1.2 (estado final)

**P1.2 — CLOSED** (2026-10-01). La sección 8 (Compose por digest) quedó **aplicada** y la sección 13
quedó **completada**.

- **Imagen validada**: `danyseve1/bracket-bjj:e6abd7d-r3`, digest
  `sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8`
  (Image ID local `sha256:09b19930bde2…`, upstream `e6abd7d…`, recipe revision `r3`).
- **Despliegue en producción** el **2026-10-01T18:43:47Z → 18:43:48Z UTC**, fijando el **digest** en
  `docker-compose.yml` y recreando **solo** el servicio `bracket` (PostgreSQL, nginx y WireGuard
  intactos). Cadena `nginx → bracket → PostgreSQL` validada.
- **Merge a `develop`** por *fast-forward*: `develop` = `origin/develop` = `ebd1215`.
- **Pila sombra retirada correctamente** el **2026-10-01T19:00:36Z → 19:01:01Z UTC**:
  parados y eliminados `bracket-p12b` y `bracket-p12b-postgres`, red `bjj-p12b-test`,
  volumen `bjj-p12b-pgdata`, las credenciales efímeras (`pg.env`, `app.env`, `test-user.env`) y el
  directorio `/home/ubuntu/p12b-shadow/`. No se tocó nada más: en particular se conservan el volumen
  productivo `bjj-tournament-platform_bracket_postgres_data` y sus datos.
- **Producción continuó estable**: sin incidencias desde el despliegue, mismos contenedores, `healthy`,
  `restarts=0`.
- **Evidencia conservada** (no sensible) en
  **`/home/ubuntu/backups/bjj-tournament-platform/p12b-evidence/`** con `SHA256SUMS`: logs de la
  candidata y del PostgreSQL del sandbox, prueba A/B de `BASE_URL`, volcados de esquema (solo DDL, sin
  datos), `schema-drift-check.txt` (deriva 0) y el resumen `P12B-SHADOW-VALIDATION.md`.
- Se conservan las imágenes `e6abd7d-r1`, `e6abd7d-r2` y la legacy `0.1.0`/`latest` para rollback y
  comparación; los backups PostgreSQL `pre-*` quedan intactos.


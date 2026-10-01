# 07 — Plan de imagen Bracket reproducible (P1.2b)

Estado: **diseño + receta versionada, sin construir**. Este documento acompaña a
`docker/bracket-bjj/Dockerfile` (receta propia, revision `r1`) y a
`docker/bracket-bjj/Dockerfile.dockerignore`. No se ha ejecutado ningún `docker build`,
`docker pull` ni cambio de runtime.

Referencias: `docker/bracket-bjj/Dockerfile.legacy` (receta histórica parchada),
`docs/06-imagen-custom-bracket.md` (qué se desplegó y por qué), y
`docs/decisions/ADR-004-bracket-image-reproducibility.md` (decisión de estrategia).

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
submódulo en `1522734d` (sin cambiar el gitlink), como revisión `r2` de contingencia.

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
  comportamiento que en `r1` no es necesario: se evita.
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
RECIPE_REVISION=r1
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
docker build -f docker/bracket-bjj/Dockerfile -t danyseve1/bracket-bjj:e6abd7d-r1 .
```

Etapa 1 — frontend (`node:24-alpine` por digest):
- `corepack enable` + `corepack prepare pnpm@9.15.9 --activate`;
- copia `package.json` + `pnpm-lock.yaml`, verifica SHA256, `pnpm install --frozen-lockfile`,
  vuelve a verificar SHA256 (prueba de que el lockfile no se reescribe);
- copia el resto del frontend y compila con `VITE_API_BASE_URL=/api` (variable de **build**);
- **el build falla** si aparece `http://localhost:8400/api` en `dist` (sin `sed`).

Etapa 2 — runtime (`python:3.14-alpine3.22` por digest, `uv 0.9.19` por digest):
- `uv sync --no-dev --locked --no-install-project` (dependencias) y después
  `uv sync --no-dev --locked` (con el código); SHA256 de `uv.lock` verificado antes y después;
- **sin** parche de `config.py` y **sin** `BRACKET_PUBLIC_BASE_URL` (su motivo era un no-op);
- `dist` copiado a `/app/frontend-dist` (ruta que espera `app.py`);
- usuario de sistema `bracket`, `HOME=/app`, `UV_CACHE_DIR=/app/.cache/uv` con modo 750;
  ninguna ruta con permisos 777; cachés de compilación vía `--mount=type=cache` (no entran
  en la imagen);
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
danyseve1/bracket-bjj:e6abd7d-r1
                 └──────┘ └┘
      commit del submódulo (7)  revisión propia de la receta
```

- `e6abd7d` = commit del submódulo con el que se construyó; `r1` = primera revisión de
  **nuestra** receta/ajustes. Sube a `r2`, `r3`… si cambia el Dockerfile, los pines o los
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
    image: danyseve1/bracket-bjj:e6abd7d-r1      # tras publicar y validar -> @sha256:<digest>
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

Pila de prueba (efímera, red y volumen propios, **nunca** los de producción):
1. Red `bjj-p12b-test` y volumen nuevo `p12b_pgdata`.
2. `postgres:16` (por digest) con `POSTGRES_*` de prueba; restaurar ahí el dump del backup
   (`pg_restore` del último `20261001T151041Z` o de uno nuevo `pre-p12b`). Los datos son
   una **copia**.
3. Candidata como `bracket-p12b` con `PG_DSN` del postgres de prueba,
   **`AUTO_RUN_MIGRATIONS=false`**, `SERVE_FRONTEND=true`, `API_PREFIX=/api`, `JWT_SECRET` de
   prueba, y puerto publicado **solo en loopback**: `127.0.0.1:18400:8400`.
4. Con `AUTO_RUN_MIGRATIONS=false`, la candidata no puede tocar esquema ni datos ajenos. Si
   se quiere probar el camino de migración, se ejecuta a mano `alembic upgrade head` **contra
   la copia** y se comprueba que no aplica nada (head ya es `c1ab44651e79`).
5. Al terminar, eliminar **solo** los recursos `*-p12b*`. El proyecto `bjj-tournament-platform`
   no se toca.
6. Requisitos previos: backup `pre-p12b` protegido, imagen legacy conservada localmente
   (`a773917e9c4b`, 4 tags) y autorización explícita (la prueba crea contenedores).

---

## 10. Checklist funcional (candidata vs. actual, antes de desplegar)

Baseline `127.0.0.1:8400`; candidata `127.0.0.1:18400`.

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
| 12 | Permisos | sin modos 777: `find /app -perm -0002` vacío; `/app/.cache/uv` de `bracket` |
| 13 | Logs | sin tracebacks ni 500; 1 worker, bind `0.0.0.0:8400` |
| 14 | Recursos | RSS del mismo orden que el actual (±20 %) |
| 15 | nginx | nginx de prueba → candidata: `/` 200 y `/api/ping` 200; tras desplegar, con el nginx productivo (`Host: bjj.local`) |
| 16 | WireGuard | tras desplegar, desde el cliente por el túnel: `http://bjj.local:8080/` y `/api/ping` 200 |
| 17 | Rollback | probado en la pila de prueba (ver sección 11) |

Diferencias en 1–9 son bloqueantes.

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
| Bumps de dependencias (starlette 1.0.0, fastapi 0.135; i18next 26, @mantine/form 9, @hcaptcha 2, @vitejs/plugin-react 6) | Es el delta real y va ejercitado por el CI upstream; validación funcional 3–7 en sandbox; contingencia `r2` desde `1522734d` |
| `pnpm 9.15.9` frente a un lockfile mantenido por pnpm 10 en el upstream | Doble comprobación SHA256 del lockfile en el build; si fallara, se sube el pin (cambio de receta → `r2`) |
| node 25 (upstream) vs node 24 (nosotros) | 24 coincide con `.nvmrc` v24.3.0 y mantiene corepack; sin impacto funcional esperado |
| Permisos no root: `uv run` o el SPA pueden necesitar escribir en `HOME`/caché | `HOME=/app` y `UV_CACHE_DIR=/app/.cache/uv` de `bracket` con 750; checks 11–12 |
| Caches de compilación | `--mount=type=cache` (no entran en la imagen); ninguna ruta con 777 |
| Publicación arm64-only | Documentado; el único consumidor es arm64 |
| Deriva entre nuestra receta y el upstream | La doble verificación de hashes hace **fallar el build** si el submódulo cambia sin revisar la receta |
| Contexto de build con secretos | `Dockerfile.dockerignore` excluye `.env*`, `.git` y backups; nunca `COPY .` |

---

## 13. Próximos pasos (cada uno con autorización y parada)

1. **Build local** (sin publicar): `docker build -f docker/bracket-bjj/Dockerfile -t danyseve1/bracket-bjj:e6abd7d-r1 .`
   (requiere red para npm registry y PyPI/uv; el builder arm64 es nativo).
2. Inspección de la imagen construida: `User`, `HEALTHCHECK`, `docker history`, etiquetas y
   verificación del bundle dentro de la imagen.
3. Publicación en Docker Hub + registro del digest.
4. Sandbox con PostgreSQL restaurado + checklist funcional (sección 10).
5. Cambio del Compose (una línea + retirada de `VITE_API_BASE_URL`) con backup `pre-*` y
   rollback listo.
6. Merge de la rama a `develop` por fast-forward y actualización de
   `docs/06-imagen-custom-bracket.md` con el digest publicado.

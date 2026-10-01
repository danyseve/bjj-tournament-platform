# 06 - Imagen custom de Bracket (receta propia y estado actual)

Estado: actualizado el 2026-10-01 (P1.2b cerrado). Esta ficha distingue dos cosas:

- **ESTADO ACTUAL**: la imagen **r3**, construida desde el codigo fuente con receta propia y
  desplegada en produccion por **digest**. Es lo que corre hoy.
- **LEGACY (historico)**: la imagen `0.1.0`, un parche por `sed` sobre una imagen prehecha de un
  tercero. Ya **no esta desplegada**, pero se conserva documentada como contexto y para rollback.

Receta y plan completos: **`docs/07-plan-imagen-reproducible.md`**. Decision: `docs/decisions/ADR-004-bracket-image-reproducibility.md`.

---

## 1. Imagen actualmente desplegada (r3)

| Dato | Valor |
|---|---|
| Referencia en Compose | `danyseve1/bracket-bjj@sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8` (servicio `bracket`) |
| Tag publicado | `danyseve1/bracket-bjj:e6abd7d-r3` |
| RepoDigest | `danyseve1/bracket-bjj@sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8` |
| Image ID local | `sha256:09b19930bde296aeb2d84851d67d91c61153599f166c92dfb68577c623e712df` |
| Revision upstream (submodulo `services/bracket`) | `e6abd7d282850f9d13d9122494767d4dbcb139ef` |
| Recipe revision | `r3` (label `com.danyseve.bracket.recipe_revision`) |
| Arquitectura | `linux/arm64/v8` (build nativo en el A1.Flex) |
| Workdir / Usuario | `/app` / **`bracket`** (no-root) |
| Cmd | `uv run --no-dev --locked -- gunicorn -k uvicorn.workers.UvicornWorker bracket.app:app --bind 0.0.0.0:8400 --workers 1` |
| Healthcheck (imagen) | `wget -q -O - http://127.0.0.1:8400/api/ping \| grep -q '"ping"'` (interval 30s, timeout 5s, retries 3, start-period 20s) |
| Entorno runtime | `UV_CACHE_DIR=/tmp/uv-cache`, `HOME=/app`, `UV_LINK_MODE=copy`, `UV_COMPILE_BYTECODE=1` |
| Migraciones | `AUTO_RUN_MIGRATIONS: "false"` en el `environment:` del Compose |
| Tamano / capas | 330.734.011 B (331 MB) / 16 capas |
| Publicacion en Docker Hub | 2026-10-01T18:35:38Z -> 18:36:00Z UTC |
| Despliegue en produccion | 2026-10-01T18:43:47Z -> 18:43:48Z UTC (contenedor `d5e9e340ac45`) |
| Commits | receta `4107d4a`; docs `b902049`, `2390895`; despliegue `bc19276` |
| Esquema | Alembic `c1ab44651e79`, sin drift |

`docker push` y la verificacion del digest por tres vias (salida del push, `docker image inspect`,
`docker buildx imagetools inspect` / `docker manifest inspect -v`) coinciden, y el
`config.digest` del manifest remoto es exactamente el Image ID local: lo publicado es lo validado.

## 2. Construccion reproducible desde source

- Receta propia y versionada: **`docker/bracket-bjj/Dockerfile`** (+ `docker/bracket-bjj/Dockerfile.dockerignore`).
- Build **desde el codigo del submodulo** (`services/bracket` @ `e6abd7d`), multi-stage:
  `pnpm build` del frontend y `uv sync --no-dev --locked` del backend.
- Bases pinadas por digest: `node:24-alpine`, `python:3.14-alpine3.22`, `ghcr.io/astral-sh/uv:0.9.19`.
- Lockfiles respetados y hasheados en labels: `uv.lock` `24f99c8e...df242`, `pnpm-lock.yaml` `001f9b8e...984af`;
  `pnpm` 9.15.9.
- **Sin parcheo posterior de artefactos**: han desaparecido definitivamente las `sed` sobre el bundle,
  el `config.py.bak` y los `chmod -R 777` del legacy.
- Permisos: `/tmp/uv-cache` `0700 bracket:bracket`; `/app/.venv/.lock` `0640`; **0 entradas reales
  world-writable bajo `/app`** en build y en runtime (el lock dinamico de uv vive en `/tmp/uv-cache`).

## 3. Variables de entorno: build-time vs runtime

- `VITE_API_BASE_URL=/api` es **build-time**: Vite la inlinea en el bundle durante `pnpm build`. En
  **runtime no tiene efecto**, por eso ya **no figura** en el `environment:` del Compose (se elimino en
  el cierre de P1.2). El bundle compilado contiene `getBaseApiUrl(){return"/api"}`.
- `BRACKET_PUBLIC_BASE_URL` esta **eliminado definitivamente** (no existe en el Compose ni en la receta).
- `BASE_URL` **no se configura actualmente** porque en esta revision **no tiene consumidores funcionales**
  (su unica aparicion es su definicion por defecto). No anadir al Compose mientras no exista un uso real.
- `AUTO_RUN_MIGRATIONS=false` evita que el arranque del contenedor ejecute migraciones Alembic.

## 4. Validacion y equivalencia funcional

Probado en una **pila sombra aislada** (red, PostgreSQL y volumen propios, sin relacion con produccion) y
despues en produccion: `arm64`, `healthy` con healthcheck real, SPA servida, `/api/ping` 200 `"ping"`,
`/openapi.json` 200, lectura de torneos/equipos/plantillas, login de prueba, Alembic sin cambios y
**schema drift = 0**; la pila sombra permanece intacta como evidencia.

## 5. Rollback y backups

- **Rollback de imagen**: volver a `image: danyseve1/bracket-bjj:0.1.0` (imagen local
  `sha256:a773917e9c4b...`, 173 MB, conservada) y recrear **solo** `bracket`
  (`docker compose up -d --no-deps --force-recreate bracket`). Nunca `docker compose down -v`.
- **Backups pre-cambio** (retencion `pre-*`, nunca se borran):
  `pre-deploy-r3-20261001T184323Z` (dump sha256 `94d61553bdbb...`) y
  `pre-p12b-20261001T180912Z` (dump sha256 `797d1dc9bf37...`), ambos con `SHA256SUMS`,
  `pg_restore --list` (178 entradas TOC) y `MANIFEST.txt` validados.
- Restaurar la base solo ante evidencia real de cambio de datos/esquema; con
  `AUTO_RUN_MIGRATIONS=false` no hay migraciones en el arranque.

---

## 6. LEGACY historico: imagen `0.1.0` (parche sobre imagen de tercero)

> Contexto historico. **Ya no esta desplegada** desde el 2026-10-01T18:43:48Z. No debe evolucionar:
> cualquier mejora va a la receta nueva (`docker/bracket-bjj/Dockerfile`).

### 6.1 Imagen

| Dato | Valor |
|---|---|
| Referencia usada entonces en Compose | `danyseve1/bracket-bjj:0.1.0` |
| Image ID | `sha256:a773917e9c4b5c5c7fde372185b3a75dc2690e6999a7d2037a2da5c115d4e2d7` |
| RepoDigest | `danyseve1/bracket-bjj@sha256:38569b93ab2ab72af4b3cb98b8b49d1509facdedda6cfabf70bf1b712fed6bfc` |
| Arquitectura | `arm64/linux` (nativo en el A1.Flex) |
| Creada | 2026-05-21T11:22:55Z |
| Tamano | 173.402.020 B (173 MB) |
| Tags locales con el MISMO ID | `danyseve1/bracket-bjj:latest`, `ghcr.io/danyseve/bracket-bjj:0.1.0`, `ghcr.io/danyseve/bracket-bjj:latest` |
| Entrypoint / Cmd | `null` / `uv run --no-dev --locked -- gunicorn -k uvicorn.workers.UvicornWorker bracket.app:app --bind 0.0.0.0:8400 --workers 1` |
| Workdir / User | `/app` / **`root`** (ver riesgos) |
| Healthcheck de la imagen | `wget -O /dev/null http://0.0.0.0:8400/ping` (interval 3s, timeout 5s, retries 10) - **falso positivo**, sustituido en Compose |
| Healthcheck efectivo (entonces) | definido en `docker-compose.yml` (valida `/api/ping`); prevalece sobre el de la imagen |
| Registry del tag | Docker Hub (`danyseve1/bracket-bjj`, **publico**) |

El tag no estaba fijado por digest en Compose: riesgo de tag mutable que el estado actual ya no tiene.
El RepoDigest identifica el contenido exacto validado en P1.1. `latest` remoto sigue apuntando a este
legacy (`sha256:38569b93...`); no se ha repuntado.

### 6.2 Base upstream

- `FROM ghcr.io/evroon/bracket:latest` (tag flotante en el momento del build).
- Digest de la base usada: `ghcr.io/evroon/bracket@sha256:0a5b9ea1d2ae2ed2eaf5e8647f64bcfdae998f873a6bf26a55cc9761b54cfb91`
  (verificado en P1.2: era el mismo digest que servia `:latest` entonces; **no se puede asumir que siga asi**).
- Commit upstream real del contenido base: `1522734d2c71e1ed0f41c71c55b1d6b5a4a3662d`
  (label `org.opencontainers.image.revision`, version `v3.0.0-rc1`, creada 2025-12-29T19:57:26Z).
- El arbol base coincidia con el fork `services/bracket` en ese commit: `backend/uv.lock` de la imagen
  tenia el mismo sha256 que `git show 1522734d:backend/uv.lock`, y distinto del de `e6abd7d` (164 commits
  por delante, que es la revision del estado actual).

### 6.3 Por que hizo falta el parche del frontend

1. Vite **inlinea** `VITE_API_BASE_URL` en el bundle en **build time**; no hay lectura en runtime.
2. La base upstream se compilo con `VITE_API_BASE_URL=http://localhost:8400/api` (absoluto), asi que
   `getBaseApiUrl()` (`frontend/src/services/adapter.tsx`) devolvia esa URL: inservible desde otro navegador.
3. El servicio `bracket` del Compose pasaba `VITE_API_BASE_URL=/api`, pero eso es **runtime**: no modifica
   un bundle ya compilado. Esa confusion fue el origen del parche manual.
4. Parche aplicado (por `sed`, no rebuild):
   - bundle: `http://localhost:8400/api` -> `/api` y resto de `http://localhost:8400` -> cadena vacia,
     sobre `/app/frontend-dist`;
   - backend: default `base_url` de `/app/bracket/config.py` -> `http://bjj-bracket.local:8400`
     (no-op funcional: `base_url` no se usa en el codigo de esa revision).
   Resultado verificado en P1.2: el bundle legacy contenia `getBaseApiUrl(){return"/api"}` y no quedaba
   ninguna referencia `localhost:8400` salvo el respaldo `config.py.bak`.

### 6.4 Dockerfile historico

- Fichero conservado: **`docker/bracket-bjj/Dockerfile.legacy`**
  (copia fiel de `docker/bracket-bjj/Dockerfile` en `feature/wireguard-vpn-oracle@afecee6`,
  sha256 original `faa2ae659e4af86a9dcf0690ad17275b378e45f0eadea1bd23d9e2e5843f5c6d`,
  con un unico cambio: el `FROM` fijado por digest).
- Capas que anadia sobre la base: `USER root` -> `ARG BRACKET_PUBLIC_BASE_URL` -> `RUN` de parcheo ->
  `ENV HOME=/app` -> `ENV UV_CACHE_DIR=/tmp/uv-cache`.
- El `RUN` de parcheo ejecutaba las 3 `sed`, copiaba `config.py` a `config.py.bak`, ajustaba permisos
  (`chmod -R 777`) y validaba con `grep localhost:8400`.

### 6.5 Comando de build historico (conceptual)

```
docker build --no-cache \
  --build-arg BRACKET_PUBLIC_BASE_URL=http://bjj-bracket.local:8400 \
  -t danyseve1/bracket-bjj:0.1.0 \
  -f docker/bracket-bjj/Dockerfile.legacy docker/bracket-bjj
```

- El contexto de build era irrelevante: no habia `COPY` del contexto, todo el trabajo era sobre ficheros
  ya presentes en la imagen base.
- **No ejecutar sin autorizacion explicita**: no es necesario y un rebuild con la base por digest
  produciria una imagen equivalente, no necesariamente el mismo Image ID.
- Se uso una seccion `build:` temporal en el Compose que ya **no existe**.

### 6.6 Riesgos que motivaron la sustitucion

1. **`sed` sobre bundle minificado**: sustitucion de cadenas sobre un artefacto compilado; un cambio de
   base o de minificador puede romperlo sin error visible.
2. **`USER root`**: la imagen derivada terminaba como root (la base ejecutaba como `bracket`).
3. **`chmod -R 777`** en `/app/.cache` y `/tmp/uv-cache`: permisos excesivos dentro de la imagen.
4. **`/app/bracket/config.py.bak`**: resto de `localhost:8400` dentro de la imagen (suciedad, no secreto).
5. **Tag mutable**: `:0.1.0` y `:latest` pueden repuntarse; nada fijaba el digest validado.
6. **Drift respecto al source**: la imagen correspondia al commit `1522734d`; el submodulo iba 164 commits
   por delante. Los ficheros de aplicacion (`app.py`, `routes/internals.py`) eran identicos, las
   dependencias (`uv.lock`, `pnpm-lock.yaml`) no.
7. **Credenciales**: el login original se hizo con `echo <TOKEN> | docker login ghcr.io --password-stdin`,
   dejando el token en el historial de shell. Para logins futuros: entrada interactiva o gestor de secretos.

## 7. No-objetivos de esta ficha

- No se reconstruye ninguna imagen ni se recrea `bracket` por documentar.
- No se modifica `.env`.
- No se borran la imagen legacy `0.1.0`, `latest`, `r1` ni `r2` (se conservan para rollback y evidencia).
- No se retira todavia la pila sombra.

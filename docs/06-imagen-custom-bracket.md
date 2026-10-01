# 06 - Imagen custom de Bracket (receta historica documentada)

Estado: documentado el 2026-10-01 (P1.2a). Esta ficha describe **que imagen esta corriendo hoy**,
**como se construyo** y **por que su receta no es reproducible desde el codigo fuente todavia**.
No sustituye a una estrategia de build desde source: la prepara (ver ADR-004).

## 1. Imagen actualmente desplegada

| Dato | Valor |
|---|---|
| Referencia en Compose | `danyseve1/bracket-bjj:0.1.0` (`docker-compose.yml`, servicio `bracket`) |
| Image ID | `sha256:a773917e9c4b5c5c7fde372185b3a75dc2690e6999a7d2037a2da5c115d4e2d7` |
| RepoDigest | `danyseve1/bracket-bjj@sha256:38569b93ab2ab72af4b3cb98b8b49d1509facdedda6cfabf70bf1b712fed6bfc` |
| Arquitectura | `arm64/linux` (nativo en el A1.Flex) |
| Creada | 2026-05-21T11:22:55Z |
| Tamano | 173.402.020 B (173 MB) |
| Tags locales con el MISMO ID | `danyseve1/bracket-bjj:latest`, `ghcr.io/danyseve/bracket-bjj:0.1.0`, `ghcr.io/danyseve/bracket-bjj:latest` |
| Entrypoint / Cmd | `null` / `uv run --no-dev --locked -- gunicorn -k uvicorn.workers.UvicornWorker bracket.app:app --bind 0.0.0.0:8400 --workers 1` |
| Workdir / User | `/app` / **`root`** (ver riesgos) |
| Healthcheck de la imagen | `wget -O /dev/null http://0.0.0.0:8400/ping` (interval 3s, timeout 5s, retries 10) - **falso positivo**, sustituido en Compose |
| Healthcheck efectivo | definido en `docker-compose.yml` (valida `/api/ping`); prevalece sobre el de la imagen |
| Registry del tag | Docker Hub (`danyseve1/bracket-bjj`, **publico**) |

Nota: el tag NO esta fijado por digest en Compose. El `RepoDigest` de arriba identifica el
contenido exacto que se valido en P1.1; fijarlo por digest eliminaria el riesgo de tag mutable.

## 2. Base upstream

- `FROM ghcr.io/evroon/bracket:latest` (tag flotante en el momento del build).
- Digest de la base usada: `ghcr.io/evroon/bracket@sha256:0a5b9ea1d2ae2ed2eaf5e8647f64bcfdae998f873a6bf26a55cc9761b54cfb91`
  (verificado en P1.2: es el mismo digest que sirve hoy `:latest`, es decir el tag no se ha movido
  desde el build; **no se puede asumir que siga asi**).
- Commit upstream real del contenido base: `1522734d2c71e1ed0f41c71c55b1d6b5a4a3662d`
  (label `org.opencontainers.image.revision`, version `v3.0.0-rc1`, creada 2025-12-29T19:57:26Z).
- El arbol base coincide con el fork `services/bracket` en ese commit: `backend/uv.lock` de la imagen
  tiene el mismo sha256 que `git show 1522734d:backend/uv.lock`, y distinto del de `e6abd7d` (HEAD del
  submodulo actual, 164 commits por delante).

## 3. Por que hizo falta el parche del frontend

1. El frontend se compila con **Vite**, que **inlinea** `VITE_API_BASE_URL` dentro del bundle en
   **build time**. No existe lectura de esa variable en runtime.
2. La imagen base upstream se compilo con `VITE_API_BASE_URL=http://localhost:8400/api`
   (valor **absoluto**), por lo que `getBaseApiUrl()` (`frontend/src/services/adapter.tsx`) devolvia
   esa URL: inservible para cualquier navegador que no sea el propio host.
3. El servicio `bracket` del Compose si pasa `VITE_API_BASE_URL=/api` como variable de entorno,
   pero eso es **entorno de runtime**: no modifica un bundle ya compilado. Esa confusion es el origen
   del parche manual.
4. Parche aplicado (por `sed` sobre la imagen base, no rebuild):
   - bundle: `http://localhost:8400/api` -> `/api` (relativo, mismo origen) y resto de
     `http://localhost:8400` -> cadena vacia, sobre `/app/frontend-dist`;
   - backend: el default `base_url` de `/app/bracket/config.py` -> `http://bjj-bracket.local:8400`
     (no-op funcional: `base_url` no se usa en el codigo de esta revision).
   Resultado verificado en P1.2: el bundle desplegado contiene `getBaseApiUrl(){return"/api"}` y no
   queda ninguna referencia `localhost:8400` salvo el respaldo `config.py.bak`.

## 4. Dockerfile historico

- Fichero recuperado y versionado: **`docker/bracket-bjj/Dockerfile.legacy`**
  (copia fiel de `docker/bracket-bjj/Dockerfile` en `feature/wireguard-vpn-oracle@afecee6`,
   sha256 original `faa2ae659e4af86a9dcf0690ad17275b378e45f0eadea1bd23d9e2e5843f5c6d`,
   con un unico cambio: el `FROM` fijado por digest).
- Capas que el Dockerfile anade sobre la base (coinciden con `docker history --no-trunc` de la imagen):
  `USER root` -> `ARG BRACKET_PUBLIC_BASE_URL` -> `RUN` de parcheo -> `ENV HOME=/app` ->
  `ENV UV_CACHE_DIR=/tmp/uv-cache`.
- El `RUN` de parcheo ejecuta las 3 `sed`, copia `config.py` a `config.py.bak`, ajusta permisos de
  cache (`chmod -R 777`) y termina con una validacion (`grep localhost:8400`).

## 5. Comando de build (historico y conceptual)

Historico (lo que se ejecuto, reconstruido de `~/.bash_history` y del commit `afecee6`):

```
docker build --no-cache \
  --build-arg BRACKET_PUBLIC_BASE_URL=http://bjj-bracket.local:8400 \
  -t danyseve1/bracket-bjj:0.1.0 \
  -f docker/bracket-bjj/Dockerfile.legacy docker/bracket-bjj
```

- El contexto de build es irrelevante: el Dockerfile no hace `COPY` del contexto, todo su trabajo es
  sobre ficheros que ya estan en la imagen base.
- `docker compose build bracket` se uso en el momento del build con una seccion `build:` temporal que
  ya no existe en `docker-compose.yml`; por eso la receta queda documentada aqui y en el Dockerfile.
- **No ejecutar sin autorizacion explicita**: reconstruir no es necesario hoy (el runtime no se toca en
  P1.2a) y un rebuild con la base por digest produciria una imagen equivalente, no necesariamente el
  mismo Image ID.

## 6. Por que se marca como legacy

- No es un build desde el codigo fuente: es un parche sobre una imagen prehecha de un tercero.
- No hay trazabilidad del binario desplegado mas alla de un tag mutable y un digest.
- El parcheo por `sed` degrada el determinismo y puede romperse en silencio con otra base.
- Se conserva como **referencia fiel de lo que hoy esta en produccion** y como base de comparacion
  para la estrategia futura (ADR-004). No debe evolucionar: cualquier mejora va a la receta nueva.

## 7. Riesgos conocidos

1. **`sed` sobre bundle minificado**: sustitucion de cadenas sobre un artefacto compilado. Hoy funciona
   (verificado), pero un cambio de base o de minificador puede hacerlo fallar sin error visible.
2. **`USER root`**: la imagen derivada termina como root (la base ejecutaba como usuario `bracket`).
   El contenedor `bracket` corre como root. No es necesario para el parche.
3. **`chmod -R 777`** en `/app/.cache` y `/tmp/uv-cache`: permisos excesivos dentro de la imagen.
4. **`/app/bracket/config.py.bak`** queda dentro de la imagen y es el unico resto de `localhost:8400`:
   suciedad y fuga de detalle de implementacion, no un secreto.
5. **Tag mutable**: `:0.1.0` (y `:latest`) pueden repuntarse; nada en Compose fija el digest validado.
6. **Drift respecto al source**: la imagen corresponde al commit `1522734d`; el submodulo esta 164
   commits por delante. Los ficheros de aplicacion (`app.py`, `routes/internals.py`) son identicos,
   pero las dependencias (`uv.lock`, `pnpm-lock.yaml`) no.
7. **Credenciales**: el login original se hizo con `echo <TOKEN> | docker login ghcr.io --password-stdin`,
   que deja el token en el historial de shell. Para cualquier login futuro, usar entrada interactiva o
   un gestor de secretos; nunca `echo` con el valor en la linea de comandos.

## 8. Estrategia futura recomendada

Build **desde source** del submodulo (`services/bracket`), en una receta propia y versionada en este
repositorio, con:

- `VITE_API_BASE_URL=/api` como **build arg** (o `ENV` en la etapa builder) antes de `pnpm build`;
- bases pinadas por digest (`node`, `python`, `uv`) y lockfiles respetados
  (`pnpm install --frozen-lockfile`, `uv sync --no-dev --locked`);
- healthcheck correcto en la imagen (`/api/ping`) y ejecucion como usuario **no root**;
- sin parcheo posterior de artefactos.

Validacion de equivalencia (funcional, no bit a bit): healthcheck `healthy`; `/api/ping` -> 200 JSON
`"ping"` directo y via Nginx; SPA servida correctamente; base de API compilada igual a `/api`;
mismos hashes en los ficheros de aplicacion que en la imagen actual. Detalle y plan en
`docs/decisions/ADR-004-bracket-image-reproducibility.md`.

## 9. No-objetivos

- No se reconstruye la imagen ni se recrea `bracket` en este cambio.
- No se modifica `.env` ni el tag/digest que usa Compose.

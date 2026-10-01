# syntax=docker/dockerfile:1.7
#
# Bracket — imagen propia reproducible (P1.2b, revision r1)
# =============================================================================
# Receta propia que sustituye a la imagen legacy parcheada con `sed`
# (ver docker/bracket-bjj/Dockerfile.legacy y docs/06-imagen-custom-bracket.md).
#
# Contexto de build: RAIZ del repositorio bjj-tournament-platform
#   docker build -f docker/bracket-bjj/Dockerfile -t danyseve1/bracket-bjj:e6abd7d-r1 .
#
# NO construida todavia en r1: este fichero se versiona sin ejecutar build.
# Las exclusiones del contexto estan en docker/bracket-bjj/Dockerfile.dockerignore
# (requiere BuildKit; el builder clasico no lee ese fichero).
#
# Pines verificados en esta revision (linux/arm64):
#   node            24-alpine  sha256:38a36422dc7de80f3ced964270f23b3b17f73af816728d21a5fbbf84bf8be46f
#   python          3.14-alpine3.22  sha256:27b691f87878a079100a3d8fafcd66b3c54d931598f307bcb54617c395f5b43c
#   ghcr.io/astral-sh/uv  0.9.19  sha256:d1581c59da88776d0fc36f03e251cb4516b15cf3e40144388f87a3b95221f7ec
#   pnpm            9.15.9 (via corepack)
#   uv.lock         sha256:24f99c8ebd6ea33363e2edaa971246c82af6e371eba3ad167c338333351df242
#   pnpm-lock.yaml  sha256:001f9b8ee4b410e82dc9f2296605469196b878306810c74e7f4f0bf87e4984af
# =============================================================================

# -----------------------------------------------------------------------------
# Etapa 1 — FRONTEND (Vite -> dist estatico)
# -----------------------------------------------------------------------------
FROM node:24-alpine@sha256:38a36422dc7de80f3ced964270f23b3b17f73af816728d21a5fbbf84bf8be46f AS frontend

WORKDIR /app
# NODE_ENV=production NO se define aqui a proposito: pnpm 9.x omite las
# devDependencies cuando NODE_ENV=production, y `vite` (que ejecuta el script
# `build`) es una devDependency -> el primer build fallo con `sh: vite: not found`.
# Se activa mas abajo, despues de `pnpm install`, antes de `pnpm build`.
ENV CI=true

# pnpm fijado de forma explicita: el proyecto NO declara `packageManager`.
# Version elegida: 9.15.9 (ultima de la rama 9.x), que es la rama que escribe y
# consume `lockfileVersion: '9.0'` tal y como esta en el repo.
ARG PNPM_VERSION=9.15.9
# Hash del lockfile validado; el build falla si el lockfile no es el esperado
# (antes y despues de instalar, para probar que --frozen-lockfile no lo reescribe).
ARG PNPM_LOCK_SHA256=001f9b8ee4b410e82dc9f2296605469196b878306810c74e7f4f0bf87e4984af
# Variable de BUILD (Vite la inlinea en el bundle). Nunca de runtime.
ARG VITE_API_BASE_URL=/api

RUN corepack enable \
 && corepack prepare "pnpm@${PNPM_VERSION}" --activate \
 && pnpm --version

COPY services/bracket/frontend/package.json services/bracket/frontend/pnpm-lock.yaml ./

RUN echo "${PNPM_LOCK_SHA256}  pnpm-lock.yaml" | sha256sum -c -

RUN --mount=type=cache,id=bracket-pnpm-store,target=/pnpm-store \
    pnpm config set store-dir /pnpm-store \
 && pnpm install --frozen-lockfile

# Modo production activado DESPUES de instalar: asi pnpm ha instalado tambien
# las devDependencies y `pnpm build` (vite) puede ejecutarse en modo production.
ENV NODE_ENV=production

RUN echo "${PNPM_LOCK_SHA256}  pnpm-lock.yaml" | sha256sum -c - \
 && echo "OK: pnpm no ha reescrito el lockfile"

COPY services/bracket/frontend/ ./

# VITE_API_BASE_URL queda inlineado por Vite: el SPA llamara a /api (relativo).
# Sin `sed` sobre el bundle. El build falla si reaparece el literal de localhost.
RUN pnpm build \
 && if grep -rl "http://localhost:8400/api" dist >/dev/null 2>&1; then \
      echo "ERROR: el bundle contiene http://localhost:8400/api" >&2; \
      grep -rl "http://localhost:8400/api" dist >&2; \
      exit 1; \
    fi \
 && echo "OK: bundle sin http://localhost:8400/api"

# -----------------------------------------------------------------------------
# Etapa 2 — RUNTIME (backend + frontend estatico, usuario no root)
# -----------------------------------------------------------------------------
FROM python:3.14-alpine3.22@sha256:27b691f87878a079100a3d8fafcd66b3c54d931598f307bcb54617c395f5b43c

# uv fijado por version + digest de linux/arm64 (nunca `latest`)
COPY --from=ghcr.io/astral-sh/uv:0.9.19@sha256:d1581c59da88776d0fc36f03e251cb4516b15cf3e40144388f87a3b95221f7ec /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Usuario de sistema sin privilegios (la imagen legacy corria como root)
RUN addgroup -S bracket \
 && adduser -S -G bracket -h /app bracket

# ARG re-declaradas para esta etapa (las de la etapa 1 no se heredan);
# se usan en las comprobaciones de integridad y en las etiquetas finales.
ARG UV_LOCK_SHA256=24f99c8ebd6ea33363e2edaa971246c82af6e371eba3ad167c338333351df242
ARG PNPM_LOCK_SHA256=001f9b8ee4b410e82dc9f2296605469196b878306810c74e7f4f0bf87e4984af
ARG PNPM_VERSION=9.15.9
ARG BRACKET_UPSTREAM_COMMIT=e6abd7d282850f9d13d9122494767d4dbcb139ef
ARG RECIPE_REVISION=r2

# Dependencias primero (cacheable), codigo despues.
COPY services/bracket/backend/uv.lock services/bracket/backend/pyproject.toml ./

RUN echo "${UV_LOCK_SHA256}  uv.lock" | sha256sum -c -

RUN --mount=type=cache,id=bracket-uv-cache,target=/root/.cache/uv \
    uv sync --no-dev --locked --no-install-project

COPY services/bracket/backend/ ./

RUN --mount=type=cache,id=bracket-uv-cache,target=/root/.cache/uv \
    uv sync --no-dev --locked

# El lockfile sigue intacto tras sincronizar
RUN echo "${UV_LOCK_SHA256}  uv.lock" | sha256sum -c - \
 && echo "OK: uv no ha reescrito uv.lock"

# Frontend ya compilado, en la ruta que espera app.py (frontend-dist relativo a WORKDIR)
COPY --from=frontend /app/dist ./frontend-dist

# HOME y cache de runtime con permisos minimos (nada de chmod 777)
ENV HOME=/app \
    UV_CACHE_DIR=/app/.cache/uv

# `app.py` monta StaticFiles(directory="static") al arrancar: el directorio debe
# existir (la imagen legacy tambien lo tiene). `mkdir` lo garantiza aunque el
# contexto de build no aporte ningun fichero en esa carpeta.
RUN mkdir -p /app/static /app/.cache/uv \
 && chown -R bracket:bracket /app \
 && chmod 750 /app /app/.cache /app/.cache/uv

# --- r2: entradas world-writable REALES bajo /app ---------------------------
# `uv sync` crea `/app/.venv/.lock` con modo 0666. Los symlinks del venv tienen
# modo 777, que es el estandar para symlinks y que el kernel ignora: no se tocan
# y quedan excluidos de la comprobacion (`-type f -o -type d`).
# Operacion explicita sobre ese unico fichero + guardia que falla el build si
# aparece cualquier conjunto inesperado de entradas reales world-writable.
# Sin chmod recursivo y sin cambios de propietario.
RUN set -eu; \
    expected="/app/.venv/.lock"; \
    ww="$(find /app -xdev \( -type f -o -type d \) -perm -0002)"; \
    unexpected="$(printf '%s\n' "$ww" | grep -vx "$expected" | grep -v '^$' || true)"; \
    if [ -n "$unexpected" ]; then \
        echo "ERROR: conjunto inesperado de entradas reales world-writable bajo /app:" >&2; \
        printf '%s\n' "$unexpected" | sed 's/^/  /' >&2; \
        exit 1; \
    fi; \
    if [ -e "$expected" ]; then chmod 640 "$expected"; fi; \
    rest="$(find /app -xdev \( -type f -o -type d \) -perm -0002)"; \
    if [ -n "$rest" ]; then \
        echo "ERROR: siguen quedando entradas reales world-writable bajo /app:" >&2; \
        printf '%s\n' "$rest" | sed 's/^/  /' >&2; \
        exit 1; \
    fi; \
    echo "OK r2: 0 ficheros reales world-writable bajo /app (symlinks 777 excluidos)"

LABEL org.opencontainers.image.title="bracket-bjj" \
      org.opencontainers.image.description="Bracket propio (backend+frontend) construido desde source" \
      org.opencontainers.image.source="https://github.com/danyseve/bjj-tournament-platform" \
      org.opencontainers.image.revision="${BRACKET_UPSTREAM_COMMIT}" \
      org.opencontainers.image.base.name="python:3.14-alpine3.22" \
      com.danyseve.bracket.recipe_revision="${RECIPE_REVISION}" \
      com.danyseve.bracket.pnpm_version="${PNPM_VERSION}" \
      com.danyseve.bracket.uv_lock_sha256="${UV_LOCK_SHA256}" \
      com.danyseve.bracket.pnpm_lock_sha256="${PNPM_LOCK_SHA256}"

USER bracket

EXPOSE 8400

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD wget -q -O - http://127.0.0.1:8400/api/ping | grep -q '"ping"'

# Comando equivalente al de la imagen en produccion (gunicorn + uvicorn worker)
CMD ["uv", "run", "--no-dev", "--locked", "--", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "bracket.app:app", "--bind", "0.0.0.0:8400", "--workers", "1"]

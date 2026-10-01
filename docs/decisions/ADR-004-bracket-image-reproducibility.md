# ADR-004 - Reproducibilidad de la imagen de Bracket

- Fecha: 2026-10-01
- Estado: **Accepted / Implemented** (decisión temporal de P1.2a; su estrategia futura se ejecutó en P1.2b el
  2026-10-01 — ver *Estado de implementación*)
- Contexto tecnico: P1.2a. Detalle de la imagen y de la receta en `docs/06-imagen-custom-bracket.md`.

## Contexto

El servicio `bracket` corre la imagen `danyseve1/bracket-bjj:0.1.0`
(Image ID `sha256:a773917e9c4b...d4e2d7`, RepoDigest `danyseve1/bracket-bjj@sha256:38569b93...f6bfc`),
construida el 2026-05-21 como **parche sobre la imagen prehecha** `ghcr.io/evroon/bracket:latest`
(`@sha256:0a5b9ea1...cfb91`, contenido upstream `1522734d2c71...`, 2025-12-29).

La inspeccion read-only de P1.2 concluyo:

1. La imagen **no es reconstruible desde `develop`**: su Dockerfile (22 lineas, `sed` sobre el bundle
   compilado) solo existia en `feature/wireguard-vpn-oracle@afecee6`, y el documento que lo describia
   estaba truncado (12 lineas).
2. El despliegue tampoco proviene del codebase actual: el Compose fija un tag mutable sin digest y el
   `VITE_API_BASE_URL` que inyecta como variable de runtime **no surte efecto** (Vite inlinea esa
   variable en build time).
3. La imagen va 164 commits por detras del submodulo `services/bracket` (dependencias distintas,
   aplicacion identica en los ficheros comprobados).

## Decision temporal

1. **Versionar la receta historica tal cual**, sin reconstruirla, en `docker/bracket-bjj/Dockerfile.legacy`,
   con el unico cambio de fijar la base por digest
   (`ghcr.io/evroon/bracket@sha256:0a5b9ea1...cfb91`) en lugar del tag flotante `:latest`.
2. **Documentar** imagen, base, digest, commit upstream, motivo del parche de frontend, comando de
   build y riesgos en `docs/06-imagen-custom-bracket.md`.
3. **No tocar el runtime**: ni `docker build`, ni `docker pull`, ni recrear `bracket`, ni cambiar el
   tag/digest del servicio en Compose en este cambio.

Se elige esto porque el objetivo inmediato es reducir riesgo de operacion (que el artefacto desplegado
sea identificable y su receta recuperable), no cambiar el artefacto. Un rebuild introduce una ventana
de mantenimiento y un artefacto nuevo que hoy no hace falta.

## Consecuencias

Positivas:

- La receta que produjo la imagen en produccion queda versionada, auditable y en `develop`.
- La base queda fijada por digest: un futuro rebuild con ese Dockerfile no dependera de donde apunte
  `:latest`.
- Queda escrito el diagnostico del falso positivo del healthcheck de imagen y de la inutilidad del
  `VITE_API_BASE_URL` de runtime, para no repetir el error.

Negativas / deuda asumida:

- La imagen desplegada sigue siendo un **parche sobre una imagen de terceros**: no hay build desde
  source, el binario depende de un registro externo (Docker Hub, publico) y el tag puede repuntarse.
- El Dockerfile legacy conserva los defectos conocidos: `sed` sobre bundle minificado, `USER root`,
  `chmod -R 777`, `config.py.bak` dentro de la imagen y un parche de backend no-op.
- Sigue existiendo drift imagen <-> source (dependencias), no resuelto por este ADR.
- El Dockerfile legacy **no debe evolucionar**: cualquier mejora va a la receta nueva (estrategia futura).

## Estrategia futura

Sustituir la imagen derivada por un **build desde source** del submodulo, con receta propia versionada:

1. Nueva receta multi-etapa en el repositorio (p. ej. `docker/bracket/Dockerfile`) que construya
   frontend y backend del commit fijado del submodulo.
2. `VITE_API_BASE_URL=/api` como **build arg** en la etapa builder; `pnpm install --frozen-lockfile`
   y `uv sync --no-dev --locked`.
3. Bases pinadas por digest (`node`, `python`, `uv`) y healthcheck correcto (`/api/ping`) en la
   propia imagen; ejecucion como usuario no root; sin parcheo de artefactos.
4. Cambio de Compose al nuevo tag (idealmente fijado por digest) **con autorizacion explicita** y
   recreando solo `bracket`.
5. Validacion de equivalencia funcional: `healthy`; `/api/ping` -> 200 JSON `"ping"` directo y via
   Nginx; SPA servida; base de API compilada = `/api`; mismos hashes en los ficheros de aplicacion.
6. Alternativa a evaluar si se necesita divergir de upstream o construir en CI con procedencia:
   fork propio construido en CI.

> Contexto histórico (P1.2a): los puntos 1–5 se describen aquí como plan. **Se ejecutaron** en P1.2b
> (2026-10-01) con la receta `docker/bracket-bjj/Dockerfile` (revisión `r3`); ver *Estado de
> implementación*.

## Estado de implementación

**Implementada** el **2026-10-01** (P1.2b): receta propia construida, validada en pila sombra y
**desplegada en producción** por digest. P1.2 **CLOSED ✅**.

| Dato | Valor |
|---|---|
| Upstream (submódulo `services/bracket`) | `e6abd7d282850f9d13d9122494767d4dbcb139ef` |
| Recipe revision | `r3` |
| Tag legible | `danyseve1/bracket-bjj:e6abd7d-r3` |
| RepoDigest | `sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8` |
| Image ID | `sha256:09b19930bde296aeb2d84851d67d91c61153599f166c92dfb68577c623e712df` |
| Plataforma | `linux/arm64/v8` |
| Usuario | **no-root** (`bracket`) |
| Migraciones | `AUTO_RUN_MIGRATIONS=false` |
| Caché de runtime | `UV_CACHE_DIR=/tmp/uv-cache` (`0700`) |
| Parcheo de artefactos | **sin** `sed` (ni `config.py.bak`) y **sin** `chmod -R 777` (0 world-writables reales bajo `/app`) |

- **Receta**: `docker/bracket-bjj/Dockerfile` multi-etapa (bases y lockfiles fijados; `VITE_API_BASE_URL=/api`
  en build time); `Dockerfile.dockerignore` propio.
- **Validación**: pila sombra aislada (red y volumen propios, PostgreSQL restaurado desde backup, usuario
  de prueba) sin tocar producción — equivalencia funcional, Alembic `c1ab44651e79` y deriva de esquema 0.
- **Producción**: `bracket` desplegado **por digest**; `healthy`, `restarts=0` y el resto de servicios
  con sus mismos IDs; backup `pre-deploy-r3-20261001T184323Z` previo.
- **Rollback conservado**: imagen legacy `danyseve1/bracket-bjj:0.1.0` (no se elimina).
- **Detalle**: `docs/06-imagen-custom-bracket.md`, `docs/07-plan-imagen-reproducible.md`; operación y
  despliegue en `docs/03-operacion.md`, `docs/04-backup-restore.md`, `docs/05-despliegue-oracle.md`.

## Rollback / no-impacto sobre runtime

- Este cambio es **solo documentacion + Dockerfile legacy**: no altera imagenes, contenedores,
  volumenes, red, `.env` ni el `docker-compose.yml`.
- No requiere reinicio ni recreacion: el runtime sigue con los mismos container IDs, `StartedAt` y
  `restarts=0`.
- Rollback: `git revert` del commit de documentacion (o borrar la rama) devuelve el repositorio al
  estado anterior. No hay nada que deshacer en el host.
- Si en el futuro se ejecuta el build documentado, el rollback seria seguir usando el tag/digest
  actuales de la imagen, que no se eliminan.

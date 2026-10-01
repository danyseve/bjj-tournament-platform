# 05 — Despliegue en Oracle Cloud (oracle-jiujitsu)

Runbook de despliegue de la plataforma BJJ. Principio general: **cambios pequeños, verificables y
reversibles**, con prechecks, validación posterior y rollback definido.

> Nota de nomenclatura: en `docs/` existen ficheros antiguos y **vacíos** con numeración que solapa
> (`03-despliegue-local.md`, `04-despliegue-oracle-cloud.md`, `05-integracion-bridge-api.md`). Este
> runbook es el vigente para despliegue en Oracle; la limpieza de esos ficheros queda pendiente y no se
> hace en este cambio.

Convenciones: **[READ-ONLY]** solo consulta · **[CAMBIO DE ESTADO]** requiere autorización explícita.

Relacionado: [03-operacion](03-operacion.md) · [04-backup-restore](04-backup-restore.md) ·
[06-imagen-custom-bracket](06-imagen-custom-bracket.md) · [07-plan-imagen-reproducible](07-plan-imagen-reproducible.md) ·
[ADR-004](decisions/ADR-004-bracket-image-reproducibility.md).

---

## 1. Acceso

| Dato | Valor |
|---|---|
| SSH | `ssh oracle-jiujitsu` (usuario `ubuntu`) |
| Host | `robledo01`, Oracle Cloud `eu-madrid-1`, `VM.Standard.A1.Flex` **aarch64/ARM64** |
| Repo | `/home/ubuntu/projects/bjj-tournament-platform` |
| Rama operativa | `develop` (**nunca** trabajar sobre `main`) |
| Compose | `docker-compose.yml` (servicios reales en ejecución: `bracket`, `bracket-postgres`, `nginx`, `wireguard`) |
| Backups | `/home/ubuntu/backups/bjj-tournament-platform/postgres/` |

```bash
ssh oracle-jiujitsu
cd /home/ubuntu/projects/bjj-tournament-platform
```

---

## 2. Prechecks **[READ-ONLY]**

```bash
git fetch origin --prune
git status --porcelain            # debe estar vacío (árbol limpio)
git rev-parse --abbrev-ref HEAD   # develop
git rev-parse HEAD origin/develop # deben coincidir
docker compose config --quiet     # la configuración renderiza sin errores
docker compose ps                 # 4 contenedores Up; bracket (healthy)
grep -n 'bracket-bjj@sha256' docker-compose.yml   # imagen fijada por DIGEST
```

Antes de cualquier cambio en producción:

1. Comprobar el estado real con [03-operacion](03-operacion.md) (salud, restarts, `/api/ping`, Alembic, counts).
2. Anotar los **IDs y `StartedAt`** de los 4 contenedores: serán la referencia para verificar que solo
   cambia el servicio que se va a recrear.
3. Crear **backup protegido** del estado actual:
   `/usr/local/bin/bjj-postgres-backup.sh pre-deploy-<motivo>` y validar `sha256sum -c SHA256SUMS`
   ([04-backup-restore](04-backup-restore.md) §6).
4. Confirmar que la imagen objetivo existe **localmente** (sin descargas inesperadas):
   `docker image inspect danyseve1/bracket-bjj@sha256:<digest> --format '{{.Id}}'`.

Si algo de lo anterior no cuadra → **parar** y plantear la desviación antes de continuar.

---

## 3. Política de imágenes

| Regla | Detalle |
|---|---|
| Producción se despliega **por digest** | `image: danyseve1/bracket-bjj@sha256:…` en `docker-compose.yml` |
| **No** usar tags móviles en producción | `latest` y tags sin digest están prohibidos para el servicio `bracket` |
| El tag legible es solo documentación | `danyseve1/bracket-bjj:e6abd7d-r3` es la etiqueta legible del digest desplegado |
| Naming de la receta | `danyseve1/bracket-bjj:<upstream>-<revision>` (p. ej. `e6abd7d-r3`) |
| Procedencia | receta propia reproducible en `docker/bracket-bjj/Dockerfile`; upstream `e6abd7d` ([ADR-004](decisions/ADR-004-bracket-image-reproducibility.md)) |

Imagen actualmente desplegada:

| Dato | Valor |
|---|---|
| Referencia en Compose | `danyseve1/bracket-bjj@sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8` |
| Tag legible | `danyseve1/bracket-bjj:e6abd7d-r3` |
| Image ID local | `sha256:09b19930bde296aeb2d84851d67d91c61153599f166c92dfb68577c623e712df` |
| Upstream / revisión | `e6abd7d282850f9d13d9122494767d4dbcb139ef` · recipe revision `r3` |
| Plataforma / usuario | `linux/arm64/v8` · usuario **no-root** `bracket` |
| Rollback conocido | `danyseve1/bracket-bjj:0.1.0` (imagen legacy conservada en el host) |

Comprobar el digest **efectivo** de lo que corre (no el del fichero):

```bash
docker inspect --format '{{.Config.Image}}' bracket
docker image inspect "$(docker inspect --format '{{.Image}}' bracket)" --format '{{index .RepoDigests 0}}'
```

---

## 4. Despliegue seguro de `bracket`

**[CAMBIO DE ESTADO — autorización explícita obligatoria]**

Patrón:

```bash
cd /home/ubuntu/projects/bjj-tournament-platform
docker compose config --quiet                        # CHECK
docker compose up -d --no-deps --force-recreate bracket   # ACTION
```

Por qué exactamente este comando:

- `--no-deps` → **no** toca dependencias: `bracket-postgres` no se recrea.
- `--force-recreate` → garantiza que el contenedor nuevo usa la imagen/configuración del fichero.
- Servicio único `bracket` → `nginx` y `wireguard` quedan fuera de la operación por completo.
- Sin `--build` (no se construye nada) y sin `up` genérico (no se levantan otros servicios ni perfiles).

Antes de ejecutarlo: backup `pre-deploy-*` (precheck 3) y anotar los IDs actuales.

---

## 5. Validación posterior

```bash
docker compose ps
docker inspect --format '{{.Name}} {{slice .Id 0 12}} started={{.State.StartedAt}} restarts={{.RestartCount}}{{if .State.Health}} health={{.State.Health.Status}}{{end}}' bracket bracket-postgres bjj-nginx wireguard
```

Criterios:

| Comprobación | Criterio |
|---|---|
| `bracket` | **ID nuevo**, `healthy`, `restarts=0` |
| `bracket-postgres`, `bjj-nginx`, `wireguard` | **mismos ID y `StartedAt`** que antes del despliegue |
| Imagen efectiva | el digest esperado (`docker inspect --format '{{.Config.Image}}' bracket`) |
| SPA | `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8400/` → `200` |
| API directa | `curl -s http://127.0.0.1:8400/api/ping` → `"ping"` |
| Vía nginx | `curl -s -H 'Host: bjj.local' http://127.0.0.1:8080/api/ping` → `"ping"` |
| Endpoint de negocio | `curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: bjj.local' http://127.0.0.1:8080/api/openapi.json` → `200` (los endpoints de datos requieren sesión: `401` sin token es correcto) |
| Alembic | `docker exec bracket-postgres psql -U bracket_dev -d bracket_dev -tAc 'select version_num from alembic_version;'` → `c1ab44651e79` |
| Counts | players 16 · teams 8 · tournaments 1 · matches 15 · rounds 8 |
| Logs | `docker logs --tail=100 bracket` sin `Traceback`/`ERROR`/`500` |
| Recursos | `docker stats --no-stream` (bracket ~125 MiB RSS) |

Si algún criterio falla → **parar** y aplicar rollback (sección 7) antes de seguir tocando nada.

---

## 6. Migraciones

`docker-compose.yml` fija **`AUTO_RUN_MIGRATIONS: "false"`** en el `environment:` de `bracket`.

Principio: **desplegar la aplicación ≠ migrar la base de datos.** El contenedor no debe aplicar DDL al
arrancar: una migración se decide, se ensaya (sandbox, [04-backup-restore](04-backup-restore.md) §7.1) y
se ejecuta de forma explícita, con backup previo y validación posterior. Verificar que sigue en `false`:

```bash
docker exec bracket printenv AUTO_RUN_MIGRATIONS     # -> false
grep -n AUTO_RUN_MIGRATIONS docker-compose.yml
```

Si hubiera migraciones pendientes: se validan con la imagen candidata en un **sandbox** (red y volumen
propios, nunca los de producción) y su resultado se revisa antes de tocar producción. Referencia del
procedimiento en [07-plan-imagen-reproducible](07-plan-imagen-reproducible.md) §9.

---

## 7. Rollback

**[CAMBIO DE ESTADO — autorización explícita]** Rollback **sin** restaurar la base de datos (salvo
evidencia real de cambio de esquema/datos).

1. Fijar en `docker-compose.yml` la imagen anterior conocida — de preferencia el **digest** previo; la
   imagen legacy está conservada para esto: `danyseve1/bracket-bjj:0.1.0` (Image ID `a773917e9c4b`).
2. `docker compose config --quiet` (CHECK) y `docker compose up -d --no-deps --force-recreate bracket` (ACTION).
3. Validar como en la sección 5 (`healthy`, `/api/ping` directo y vía nginx, Alembic, counts, logs) y
   confirmar que `bracket-postgres`, `nginx` y `wireguard` conservan sus IDs.
4. No restaurar PostgreSQL: si el esquema no cambió, restaurar solo añade riesgo. Si hubo migración
   real, el rollback de datos se hace con [04-backup-restore](04-backup-restore.md) §7.

Reglas: nunca `docker compose down` ni `down -v`, nunca borrar volúmenes, nunca recrear más de un
servicio a la vez.

---

## 8. Git

```bash
git switch develop
# ... cambios en ficheros, revisión...
git status --porcelain && git diff              # revisar antes de commitear
git add <ficheros>
git commit -m "<tipo>(<ámbito>): <descripción>"
git push origin develop
```

- Cambios siempre en rama (`develop` o `chore/*`, `fix/*`), nunca directamente en `main`.
- Para integrar una rama: **fast-forward** a `develop` (`git merge --ff-only <rama>`) y push; sin merge
  commit, sin rebase, sin `--amend`, sin force-push.
- `main` solo se toca en una fase explícita del proyecto y con autorización.
- El repositorio se publica por SSH dedicado; nunca se pegan tokens ni credenciales en la línea de
  comandos ni se desactiva la verificación TLS.
- Rama remota de referencia histórica tras un cierre: `origin/chore/bracket-image-reproducible` (no borrar).

---

## 9. Referencias

- Operación diaria, healthchecks y diagnóstico: [03-operacion](03-operacion.md)
- Backups, restauración y sandbox de restore: [04-backup-restore](04-backup-restore.md)
- Imagen desplegada y rollback legacy: [06-imagen-custom-bracket](06-imagen-custom-bracket.md)
- Plan de imagen reproducible (recetas r1→r3, digest, validaciones): [07-plan-imagen-reproducible](07-plan-imagen-reproducible.md)
- Decisión histórica sobre la imagen: [ADR-004](decisions/ADR-004-bracket-image-reproducibility.md)

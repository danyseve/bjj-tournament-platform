# 03 — Operación diaria

Runbook de operación de la plataforma en `oracle-jiujitsu` (`/home/ubuntu/projects/bjj-tournament-platform`).
Todo lo de este documento se ejecuta como el usuario `ubuntu`, desde la raíz del repositorio.

Convenciones:

- **[READ-ONLY]** — solo consulta, no cambia nada.
- **[CAMBIO DE ESTADO]** — modifica contenedores, datos o configuración: **requiere autorización explícita**.
- Los comandos usan los nombres reales: proyecto Compose `bjj-tournament-platform`, servicio `bracket`
  (contenedor `bracket`), servicio `nginx` (contenedor `bjj-nginx`), `bracket-postgres`, `wireguard`.

Documentos relacionados: [04-backup-restore](04-backup-restore.md) · [05-despliegue-oracle](05-despliegue-oracle.md) ·
[06-imagen-custom-bracket](06-imagen-custom-bracket.md) · [07-plan-imagen-reproducible](07-plan-imagen-reproducible.md) ·
[ADR-004](decisions/ADR-004-bracket-image-reproducibility.md).

---

## 1. Estado rápido

```bash
cd /home/ubuntu/projects/bjj-tournament-platform
```

| Qué | Comando | Criterio |
|---|---|---|
| Contenedores | `docker compose ps` | 4 en `Up`; `bracket` con `(healthy)` |
| Salud y reinicios | `docker inspect --format '{{.Name}} {{.State.Status}} restarts={{.RestartCount}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' bracket bracket-postgres bjj-nginx wireguard` | `restarts=0`, `healthy` |
| Logs recientes | `docker compose logs --tail=50` | sin `ERROR`/`Traceback` |
| CPU / memoria | `docker stats --no-stream` | valores estables (bracket ~125 MiB RSS) |
| Disco | `df -h /` | deja margen libre (hoy ~45 % usado) |
| Backups (timer) | `systemctl list-timers bjj-postgres-backup.timer` | próxima ejecución y último `LAST` |

Todo lo del bloque es **[READ-ONLY]**. Para las mismas comprobaciones sin `docker compose` (útil si el
Compose no está a mano): `docker ps --format '{{.Names}}\t{{.Status}}'`.

---

## 2. Servicios actuales

| Servicio Compose | Contenedor | Imagen | IP en `bjj-net` | Puertos | Healthcheck |
|---|---|---|---|---|---|
| `bracket-postgres` | `bracket-postgres` | `postgres:16` | `172.30.0.10` | `5432` **solo interno** | no tiene |
| `bracket` | `bracket` | `danyseve1/bracket-bjj@sha256:e07ec8b4…8df8` (legible `:e6abd7d-r3`) | `172.30.0.20` | `8400` → host | `wget http://127.0.0.1:8400/api/ping` + `grep "ping"` |
| `nginx` | `bjj-nginx` | `nginx:1.27-alpine` | `172.30.0.100` | `8080` → 80 | no tiene |
| `wireguard` | `wireguard` | `ghcr.io/linuxserver/wireguard:latest` | `172.30.0.2` | `51820/udp` | no tiene |

En `docker compose ps` los servicios del perfil `multitatami` (`bridge-api`, `scoreboard-tatami-1..6`)
**no** aparecen: están definidos pero no desplegados.

---

## 3. Flujo real

```text
Cliente (iMac / navegador)
        │  VPN
        v
wireguard (51820/udp, contenedor wireguard)
        │
        v
bjj-nginx  ────  host 0.0.0.0:8080 → :80   (server_name bjj.local)
        │
        v
bracket :8400   (SPA + API; API bajo /api)
        │
        v
bracket-postgres :5432   (red interna bjj-net, 172.30.0.0/24; sin puerto en el host)
```

Comprobaciones del camino completo **[READ-ONLY]**:

```bash
curl -s -o /dev/null -w 'bracket directo /api/ping  -> %{http_code}\n' http://127.0.0.1:8400/api/ping
curl -s -o /dev/null -w 'nginx /         -> %{http_code}\n' -H 'Host: bjj.local' http://127.0.0.1:8080/
curl -s        -w 'nginx /api/ping -> %{http_code}\n'        -H 'Host: bjj.local' http://127.0.0.1:8080/api/ping
```

El último debe imprimir `"ping"` (JSON) y `200`: si responde texto de nginx (`502`, HTML de error), el
problema está entre nginx y bracket, no en el cliente ni en WireGuard.

---

## 4. Healthchecks

| Objetivo | Comando | Esperado |
|---|---|---|
| `bracket` (el del Compose) | `docker inspect --format '{{.State.Health.Status}} failing={{.State.Health.FailingStreak}}' bracket` | `healthy`, `failing=0` |
| `bracket` (API directa) | `curl -s http://127.0.0.1:8400/api/ping` | `"ping"` |
| `bracket` (último resultado) | `docker inspect --format '{{range .State.Health.Log}}{{.ExitCode}} {{end}}' bracket` | `0` |
| `nginx` `/` | `curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: bjj.local' http://127.0.0.1:8080/` | `200` |
| `nginx` `/api/ping` | `curl -s -H 'Host: bjj.local' http://127.0.0.1:8080/api/ping` | `"ping"` |
| `nginx` salud de la API | `curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: bjj.local' http://127.0.0.1:8080/api/openapi.json` | `200` |

`nginx` y `bracket-postgres` **no** tienen healthcheck: su estado se evalúa con `docker compose ps`
(`Up`) y con las comprobaciones funcionales de arriba.

Para los endpoints de negocio (`/api/tournaments`, …) hace falta sesión: sin token responden `401`, y eso
es **correcto**, no un fallo.

---

## 5. PostgreSQL (checks read-only)

```bash
docker exec bracket-postgres psql -U bracket_dev -d bracket_dev -tAc 'select 1;'                       # conectividad
docker exec bracket-postgres psql -U bracket_dev -d bracket_dev -tAc 'select version_num from alembic_version;'
docker exec bracket-postgres psql -U bracket_dev -d bracket_dev -tAc 'select count(*) from players;'
docker exec bracket-postgres psql -U bracket_dev -d bracket_dev -tAc 'select count(*) from matches;'
docker exec bracket-postgres psql -U bracket_dev -d bracket_dev -tAc 'select pg_size_pretty(pg_database_size(current_database()));'
```

Valores de referencia (2026-10-01, versión `c1ab44651e79`): players 16 · teams 8 · tournaments 1 ·
matches 15 · rounds 8 · users 2.

Referencia completa por tabla: el `MANIFEST.txt` del último backup (ver
[04-backup-restore](04-backup-restore.md)). Nunca se usa la contraseña de `.env` en la línea de
comandos: el acceso es por socket dentro del contenedor.

**[CAMBIO DE ESTADO]** cualquier `psql` que no sea `SELECT`/`\d`, y cualquier restauración: ver
[04-backup-restore](04-backup-restore.md).

---

## 6. Logs

| Servicio | Últimas líneas | Seguir en vivo |
|---|---|---|
| `bracket` | `docker logs --tail=100 bracket` | `docker logs -f --tail=20 bracket` |
| `bracket-postgres` | `docker logs --tail=100 bracket-postgres` | `docker logs -f --tail=20 bracket-postgres` |
| `bjj-nginx` | `docker logs --tail=100 bjj-nginx` | `docker logs -f --tail=20 bjj-nginx` |
| `wireguard` | `docker logs --tail=100 wireguard` | `docker logs -f --tail=20 wireguard` |
| backups | `journalctl -u bjj-postgres-backup.service -n 50 --no-pager` | `journalctl -u bjj-postgres-backup.service -f` |

Búsqueda de errores (exit code `1` sin coincidencias = **bueno**):

```bash
docker logs --tail=500 bracket 2>&1 | grep -iE 'error|traceback|exception|500 ' || echo 'sin errores en las últimas 500 líneas'
docker logs --tail=200 bjj-nginx 2>&1 | grep -iE '\[error\]|\[emerg\]' || echo 'sin errores en nginx'
```

Los logs pueden contener rutas y datos de torneo: **no** se copian a notas, tickets ni repositorios.

---

## 7. Diagnóstico rápido

En todos los casos: primero **comprobar** (read-only), después decidir. Nunca recrear ni reiniciar como
primera reacción.

### 7.1 `bracket` no está `healthy`

1. Comprobar: `docker inspect --format '{{.State.Status}} {{.State.Health.Status}} {{.State.Health.FailingStreak}}' bracket`
   y `docker logs --tail=100 bracket`.
2. Read-only: `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8400/api/ping` (directo) y
   `docker exec bracket-postgres psql -U bracket_dev -d bracket_dev -tAc 'select 1;'`.
3. Interpretar: si la API directa responde y el contenedor está `Up`, puede ser un fallo transitorio del
   healthcheck (arranque); si la API no responde, revisar el log de `bracket` y la conectividad a PostgreSQL.
4. **No hacer todavía**: `docker compose restart`, `docker compose up`, recrear el contenedor ni `--force-recreate`.
   Si hay que recrear, se hace solo `bracket` y con autorización ([05-despliegue-oracle](05-despliegue-oracle.md)).

### 7.2 `nginx` devuelve 502

1. Comprobar: `docker compose ps` (¿`bracket` está `Up`?) y `docker logs --tail=50 bjj-nginx`.
2. Read-only: `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8400/api/ping` — si esto
   responde 200, el problema es el proxy/`server_name`; si no responde, el problema es `bracket`.
3. Comprobar que la petición usa el nombre correcto: `curl -H 'Host: bjj.local' http://127.0.0.1:8080/`
   (sin `Host`, nginx responde con su server por defecto).
4. **No hacer todavía**: recargar/reiniciar nginx ni editar `nginx/conf.d` (los cambios de configuración
   no son una operación de diagnóstico).

### 7.3 La API devuelve 500

1. Comprobar: `docker logs --tail=200 bracket | grep -iE 'traceback|error'`.
2. Read-only: `curl -s -H 'Host: bjj.local' http://127.0.0.1:8080/api/openapi.json -o /dev/null -w '%{http_code}\n'`
   (si la API está viva pero un endpoint concreto falla, es un problema de datos/lógica, no de despliegue).
3. Comprobar PostgreSQL: conectividad y `alembic_version` (sección 5) — un 500 sistemático tras un cambio
   de esquema apunta a migraciones.
4. **No hacer todavía**: aplicar migraciones a mano, restaurar la base ni recrear el contenedor.

### 7.4 PostgreSQL no accesible

1. Comprobar: `docker compose ps bracket-postgres` y `docker logs --tail=100 bracket-postgres`.
2. Read-only: `docker exec bracket-postgres pg_isready -U bracket_dev`,
   `docker inspect --format '{{.State.Status}} {{.RestartCount}}' bracket-postgres`.
3. Comprobar el volumen: `docker volume inspect bjj-tournament-platform_bracket_postgres_data` (que exista
   y esté montado).
4. **No hacer todavía**: borrar o recrear el volumen, `docker compose down -v`, ni `pg_resetwal`/reparaciones
   sobre los datos. Si hay corrupción, la vía es restaurar desde backup
   ([04-backup-restore](04-backup-restore.md)) con autorización.

### 7.5 Sin acceso desde el cliente (WireGuard)

1. Comprobar desde dentro: `curl -s -H 'Host: bjj.local' http://127.0.0.1:8080/api/ping` — si funciona en
   el host, el fallo está en el túnel o en el cliente, no en la aplicación.
2. Comprobar el contenedor: `docker compose ps wireguard` y `docker logs --tail=50 wireguard`.
3. Comprobar los peers configurados: `docker exec wireguard wg show` (solo lectura).
4. **No hacer todavía**: tocar `data/wireguard/config`, regenerar claves/peers, ni cambiar reglas de
   firewall o de la Security List de Oracle.

---

## 8. Operaciones peligrosas — **NO ejecutar sin autorización explícita**

| Operación | Por qué está prohibida por defecto |
|---|---|
| `docker compose down -v` | elimina el volumen `bracket_postgres_data`: **pérdida total de datos** |
| `docker compose down` | tumba los 4 servicios a la vez (y WireGuard); corta el acceso y la API |
| Borrar el volumen `bjj-tournament-platform_bracket_postgres_data` | destruye la base; los backups no sustituyen un volumen vivo sin procedimiento |
| Recrear **todos** los servicios (`docker compose up -d --force-recreate`) | ventana de corte innecesaria y riesgo de recrear PostgreSQL |
| `docker system prune` / `docker image prune` | puede borrar imágenes necesarias (incluida la de rollback y la legacy) |
| Migraciones automáticas o manuales (`AUTO_RUN_MIGRATIONS=true`, `alembic upgrade`) | cambian el esquema; el despliegue de aplicación no implica migrar |
| Cambios de firewall (`iptables`, ufw) o de la Security List de OCI | pueden cortar el acceso remoto (22/51820) |
| Cambios en WireGuard (peers, claves, `SERVERURL`) | cortan el túnel de todos los clientes |
| Editar `.env` o `docker-compose.yml` sin autorización | cambia credenciales, puertos, red o la imagen desplegada |
| `docker compose build` / `docker build` | consume recursos y puede dejar artefactos nuevos sin aprobar |

Regla operativa: **cualquier** comando que no sea `ps`, `inspect`, `logs`, `stats`, `curl`, `df` o
`psql`-de-lectura se considera cambio de estado y se para para pedir autorización.

---

## 9. Referencias

- Despliegue y rollback: [05-despliegue-oracle](05-despliegue-oracle.md)
- Backups y restauración: [04-backup-restore](04-backup-restore.md)
- Imagen desplegada (r3 por digest): [06-imagen-custom-bracket](06-imagen-custom-bracket.md)
- Plan de imagen reproducible y validaciones: [07-plan-imagen-reproducible](07-plan-imagen-reproducible.md)
- Decisión histórica sobre la imagen legacy: [ADR-004](decisions/ADR-004-bracket-image-reproducibility.md)
- Arquitectura y nginx interno: `docs/01-arquitectura.md`, `docs/08-nginx-frontal-interno.md`
- Backups (detalle del sistema): `/home/ubuntu/backups/bjj-tournament-platform/README-backups.md`

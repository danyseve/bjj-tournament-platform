# 04 — Backup y restauración de PostgreSQL

Sistema **real y ya validado** de copias de seguridad de la base `bracket_dev` (contenedor
`bracket-postgres`), más el procedimiento de restauración.

Convenciones: **[READ-ONLY]** solo consulta · **[CAMBIO DE ESTADO]** requiere autorización explícita.
Todo el sistema vive en el host `oracle-jiujitsu`:

| Elemento | Ruta |
|---|---|
| Script | `/usr/local/bin/bjj-postgres-backup.sh` (`root:root`, 755) |
| Units systemd | `/etc/systemd/system/bjj-postgres-backup.service` y `.timer` |
| Backups | `/home/ubuntu/backups/bjj-tournament-platform/postgres/<TS>/` |
| Documentación del sistema | `/home/ubuntu/backups/bjj-tournament-platform/README-backups.md` |
| Logs | `journalctl -u bjj-postgres-backup.service` |

Relacionado: [03-operacion](03-operacion.md) · [05-despliegue-oracle](05-despliegue-oracle.md) ·
[07-plan-imagen-reproducible](07-plan-imagen-reproducible.md) (sandbox de validación, sección 9).

---

## 1. Script

`/usr/local/bin/bjj-postgres-backup.sh` — crea un directorio por ejecución y **solo** usa `docker exec`
en modo lectura (`pg_dump`) más `docker cp` para extraer el fichero: **no** reinicia, recrea ni modifica
contenedores ni datos.

| Uso | Efecto |
|---|---|
| `bjj-postgres-backup.sh` | backup normal + retención |
| `bjj-postgres-backup.sh pre-<motivo>` | backup **protegido** (`pre-<motivo>-<TS>/`), nunca se borra |
| `bjj-postgres-backup.sh --retention-dry-run` | **[READ-ONLY]** muestra qué borraría la retención |

Parámetros internos relevantes: `BASE_DIR=/home/ubuntu/backups/bjj-tournament-platform/postgres`,
`CONTAINER=bracket-postgres`, `DB_USER=bracket_dev`, `DB_NAME=bracket_dev`, retención
`7 diarios / 4 semanales / 6 mensuales`, `MIN_DUMP_BYTES=1024`. Hay un `flock` que impide ejecuciones
simultáneas (si ya hay una en curso, la segunda sale sin error).

**[CAMBIO DE ESTADO]** ejecutar el script crea ficheros y, si la retención aplica, **borra** backups
antiguos: se ejecuta en ventanas acordadas. El script protege `pre-*`, `PROTECTED` y nombres no
reconocidos.

---

## 2. Timer

```bash
systemctl list-timers bjj-postgres-backup.timer     # [READ-ONLY] próxima y última ejecución
systemctl status bjj-postgres-backup.timer          # [READ-ONLY]
systemctl cat bjj-postgres-backup.service bjj-postgres-backup.timer   # [READ-ONLY] definición completa
```

| Dato | Valor |
|---|---|
| Calendario | `OnCalendar=*-*-* 03:30:00 Europe/Madrid` (**01:30 UTC** en verano, **02:30 UTC** en invierno) |
| Persistencia | `Persistent=true` (si el host estaba apagado, la ejecución se recupera al arrancar) |
| `TimeoutStartSec` | `15min` |
| Usuario | `User=ubuntu`, `Group=ubuntu`, `NoNewPrivileges=true`, `PrivateTmp=true` |
| Dependencia | `After=docker.service`, `Requires=docker.service` |

Reversión de la automatización (sin borrar backups) — **[CAMBIO DE ESTADO]**, solo con autorización:

```bash
sudo systemctl disable --now bjj-postgres-backup.timer
sudo rm /etc/systemd/system/bjj-postgres-backup.timer /etc/systemd/system/bjj-postgres-backup.service
sudo rm /usr/local/bin/bjj-postgres-backup.sh
sudo systemctl daemon-reload
```

---

## 3. Contenido de cada backup

Ruta `postgres/<YYYYMMDDTHHMMSSZ>/` (permisos `700`; ficheros `600`):

| Fichero | Contenido |
|---|---|
| `bracket_dev.dump` | `pg_dump --format=custom` de `bracket_dev` (snapshot consistente) |
| `globals.sql` | `pg_dumpall --globals-only` (roles y privilegios) |
| `SHA256SUMS` | hashes de `bracket_dev.dump` y `globals.sql` |
| `restore-list.txt` | índice del dump (`pg_restore --list`) |
| `MANIFEST.txt` | metadatos: fecha UTC, contenedor, **imagen**, versión de PostgreSQL y de `pg_dump`, base, rol, `alembic_version`, tamaño de la base, bytes/sha256 del dump, entradas TOC, tablas con datos y **counts exactos por tabla** |
| `errors.log` | solo si hubo salida por stderr; si existe, revisarla |
| `FAILED` | solo si el backup falló; los artefactos se conservan para diagnóstico y **no** se aplica retención |

Nunca se guardan contraseñas: la conexión se hace por socket dentro del contenedor.

---

## 4. Validaciones

**Automáticas** (si alguna falla, el backup se marca `FAILED` y no se aplica retención): `sha256sum -c`,
`pg_restore --list`, tamaño mínimo (`>1 KiB`), TOC no vacío e integridad `sha256`+tamaño contenedor↔host.

**Manuales [READ-ONLY]** sobre un backup concreto (`B=/home/ubuntu/backups/bjj-tournament-platform/postgres/<TS>`):

```bash
cd "$B"
sha256sum -c SHA256SUMS                                  # hashes OK
head -5 MANIFEST.txt                                     # estado, fecha, alembic_version
grep -c ';' restore-list.txt                             # entradas TOC
grep -c 'TABLE DATA' restore-list.txt                    # tablas con datos
docker exec -i bracket-postgres pg_restore --list < bracket_dev.dump | head   # dump legible
```

Comparar además los `counts` del `MANIFEST.txt` con la base viva (sección 5 de
[03-operacion](03-operacion.md)): una diferencia no es un error por sí sola (el backup es una foto),
pero debe explicarse.

---

## 5. Retención

| Regla | Valor |
|---|---|
| Diarios | 7 (los más recientes) |
| Semanales | 4 (el backup más reciente de cada semana ISO) |
| Mensuales | 6 (el backup más reciente de cada mes) |
| `pre-*` | **nunca** se borran (backup manual previo a un cambio) |
| Fichero `PROTECTED` dentro del directorio | **nunca** se borra |
| Nombre que no sea exactamente `YYYYMMDDTHHMMSSZ` | se ignora: **no se toca nunca** |

Previsualización sin borrar **[READ-ONLY]**:

```bash
/usr/local/bin/bjj-postgres-backup.sh --retention-dry-run
```

Antes de borrar, el script revalida cada nombre (`name_is_ts`), descarta `pre-*` y comprueba que la ruta
sea hija de `BASE_DIR`.

---

## 6. Backup manual antes de un cambio

**[CAMBIO DE ESTADO — autorizado por rutina antes de cualquier cambio en producción]**

```bash
/usr/local/bin/bjj-postgres-backup.sh pre-deploy-r3
# crea /home/ubuntu/backups/bjj-tournament-platform/postgres/pre-deploy-r3-<TS>/  (excluido de la limpieza)
```

Validación del backup recién creado:

```bash
B=/home/ubuntu/backups/bjj-tournament-platform/postgres/pre-deploy-r3-<TS>
ls -la "$B" && (cd "$B" && sha256sum -c SHA256SUMS)
grep -E '^(estado|fecha_utc|alembic_version|dump_bytes|toc_entradas|toc_tablas_con_datos)=' "$B/MANIFEST.txt"
```

---

## 7. Restauración

**Principio: nunca se restaura primero sobre producción.** El orden es siempre *sandbox → decisión →
producción*, y cada paso con autorización.

### 7.1 Restaurar en un sandbox (**vía preferente**)

Se usó en P1.2b y se retiró al cerrar: red y volumen **propios**, PostgreSQL **sin puerto publicado**,
credenciales de prueba distintas de las de producción y guardadas fuera del repo. Patrón:

```bash
# [CAMBIO DE ESTADO] recursos aislados, nunca los de producción
docker network create bjj-restore-test
docker volume  create bjj-restore-pgdata
docker run -d --name bracket-restore-postgres --network bjj-restore-test \
  --env-file "$HOME/restore-env/pg.env" \
  -v bjj-restore-pgdata:/var/lib/postgresql/data postgres:16
```

`$HOME/restore-env/pg.env` (permisos `600`, credenciales **temporales** de prueba, nunca las de
producción, nunca en el repo) define `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD` para el
sandbox. El contenedor de prueba **no** publica puertos: se accede con `docker exec`.

Después: restaurar (7.3), validar (7.4) **en el sandbox**, y solo entonces decidir. Reglas del sandbox:
no unirlo a `bjj-net`, no apuntar al volumen `bracket_postgres_data` ni usar el `PG_DSN` de producción;
al terminar, eliminar **solo** los recursos `*-restore-*`.

### 7.2 Restaurar en producción

Solo si hay evidencia de cambio real de datos/esquema y con autorización explícita. **Obligatorio** crear
antes un backup `pre-restore` del estado actual.

### 7.3 Procedimiento (pasos)

1. **Elegir el backup** y verlo: `ls -la /home/ubuntu/backups/bjj-tournament-platform/postgres/`
   (los `pre-*` son los protegidos).
2. **Validar checksums**: `cd "$B" && sha256sum -c SHA256SUMS`.
3. **Validar el TOC**: `grep -c ';' restore-list.txt` y
   `docker exec -i <pg> pg_restore --list < bracket_dev.dump | head`.
4. **Red de seguridad**: `bjj-postgres-backup.sh pre-restore` (backup del estado actual **antes** de tocar nada).
5. **Destino seguro**: sandbox (7.1) o, en producción, parar la aplicación —
   `docker compose stop bracket` (**nunca** `down`, **nunca** `down -v`).
6. **Restaurar**:
   - En un destino **nuevo**, primero los roles: `docker exec -i <pg> psql -U <rol> -d postgres < globals.sql`.
   - Datos: `docker exec -i <pg> pg_restore -U <rol> -d <db> --clean --if-exists --single-transaction --verbose < bracket_dev.dump`.
7. **Validar esquema**: `select version_num from alembic_version;` → debe coincidir con el
   `alembic_version` del `MANIFEST.txt`.
8. **Validar datos**: comparar `counts` del `MANIFEST.txt` con la base restaurada (players 16 · teams 8 ·
   tournaments 1 · matches 15 · rounds 8 · users 2 en la referencia de 2026-10-01).
9. **Validar aplicación**: `docker compose up -d bracket` (solo `bracket`), `healthy`, `/api/ping` 200
   directo y vía nginx, y un endpoint de negocio autenticado.
10. **Cerrar**: si era sandbox, eliminar los recursos `*-restore-*`; anotar el resultado (qué backup,
    `alembic_version`, counts, fecha UTC).

### 7.4 Rollback de una restauración

Si la restauración sale mal en producción: **no** se improvisa. Parar `bracket`, restaurar el backup
`pre-restore` creado en el paso 4 (mismo procedimiento), validar (pasos 7–9) y, si procede, volver a la
imagen/digest anterior de `bracket` siguiendo [05-despliegue-oracle](05-despliegue-oracle.md) §7.

---

## 8. Prohibiciones

| Prohibido | Motivo |
|---|---|
| Borrar el volumen `bjj-tournament-platform_bracket_postgres_data` | destruye la base; los backups no justifican un borrado manual |
| `docker compose down -v` | elimina volúmenes (pérdida de datos) |
| Restaurar **sin** backup `pre-restore` | elimina la red de seguridad |
| Sobrescribir producción como primera opción | primero sandbox; producción solo con evidencia y autorización |
| Restaurar con la aplicación escribiendo (`bracket` en marcha) | escrituras concurrentes durante `--clean` |
| Modificar a mano el contenido de un directorio de backup (`MANIFEST.txt`, `SHA256SUMS`, `PROTECTED`) | rompe la trazabilidad y las validaciones |
| Usar credenciales de producción en un sandbox | los datos de prueba deben quedar aislados |

---

## 9. Referencias

- Operación diaria y diagnóstico: [03-operacion](03-operacion.md)
- Despliegue, prechecks y rollback de imagen: [05-despliegue-oracle](05-despliegue-oracle.md)
- Sandbox de validación usado en P1.2b y su retirada: [07-plan-imagen-reproducible](07-plan-imagen-reproducible.md)
- Documentación del sistema de backups en el host: `/home/ubuntu/backups/bjj-tournament-platform/README-backups.md`

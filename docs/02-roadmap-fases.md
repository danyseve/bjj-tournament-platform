# 02 - Roadmap por fases

## Portal operativo BJJ Vetusta y Bracket en hostname propio — P2.6B (CLOSED ✅, 2026-10-02)

Commit `feat(portal): publish BJJ Vetusta operations hub`. `bjjvetusta.opsforge.cc` deja de ser
Bracket y pasa a ser el **portal estático** del equipo (Tatami 1–6, Bracket, manuales, GitHub);
Bracket se publica en su **hostname propio** `bracket.opsforge.cc`. Migración sin corte (primero
Access → DNS → ingress → nginx → validación de `bracket.`, después el cambio de `bjjvetusta`).
Sin tocar `opsforge.cc`/landing, sin WRITE, sin tocar PostgreSQL ni WireGuard, cero puertos
nuevos. Detalle: `docs/11-demo-externa-cloudflare.md` §21.

Pendiente de esta línea: **P2.6C** — hardening de accesos (la app de `bjjvetusta` sigue con OTP
abierto: cualquier email verificado entra) y mejoras de UX del portal.

## Centro de documentación OpsForge `docs.opsforge.cc` — P2.6A.3 (CLOSED ✅, 2026-10-02)

Commit `feat(docs): publish BJJ documentation center`. Documentación operativa de BJJ
Vetusta/Asturkon publicada en su propio hostname (`docs.opsforge.cc`), con una sola fuente
Markdown que genera el sitio HTML y los PDF, detrás de Cloudflare Access.

- Estructura fuente en `docs-site/` (`content/`, `assets/`, `build.py`, `deploy.sh`) con la
  salida versionada en `nginx/conf.d/docs-site/`; el frontal la sirve desde el bind mount que
  ya existía, así que **no se recreó ningún contenedor** y no hubo downtime.
- Primera entrega: **Manual del Tatami / Árbitro v0.1** (21 secciones), **guía rápida A4 de 1
  página** para imprimir/plastificar, **esqueleto del Manual de Bracket** y estructura del
  Manual del Organizador. PDF descargables generados desde la misma fuente.
- Access: app propia `OpsForge Documentation` (`docs.opsforge.cc`), OTP, sesión 7 días,
  *deny by default*, allow-list explícita de una identidad **copiada de la app de Tatami 1**
  sin que ningún correo pase por la línea de comandos ni por la salida.
- DNS: CNAME `docs.opsforge.cc` proxied al túnel `opsforge-oracle`; ingress con la regla nueva
  preservando `bjjvetusta`, `tatami1`, el catch-all y `warp-routing`.
- Cero puertos inbound nuevos, cero cambios en Bracket/PostgreSQL/WireGuard/scoreboard,
  `WRITE=false` intacto y `bjjvetusta`/`tatami1` sin regresión.
- Detalle completo: `docs/14-documentation-center.md`.

## Publicación externa del Tatami 1 tras Cloudflare Access — P2.6A.2 (CLOSED ✅, 2026-10-02)

Commit `feat(demo): publish tatami 1 behind cloudflare access`. Tatami 1 publicado en
`tatami1.opsforge.cc` detrás de Cloudflare Access, en el orden Access → DNS → ingress → prueba
externa, sin abrir puertos inbound y sin tocar Bracket, PostgreSQL, la configuración de nginx ya
preparada, WireGuard ni la app de Access de BJJ. App de Access propia por hostname
(`OpsForge Tatami 1`, self-hosted, OTP, 8 h, *deny by default*, allow-list explícita de **una** sola
identidad, sin `Everyone` y sin wildcard); `CNAME` proxied de `tatami1` al túnel `opsforge-oracle`
(zona 9 → 10 registros, resto intacto); ingress `tatami1.opsforge.cc → http://127.0.0.1:8080`
añadido preservando `bjjvetusta.opsforge.cc` y el catch-all `http_status:404` (hash
`2fd58df84be29e3d` → `7cb2d62465fe892a`). Los permisos de escritura se verificaron con escrituras
reales y read-back, no por scopes declarados.

Validación de punta a punta: anónimo interceptado por Access (`302`) en `/`, `/control`,
`/manifest.json` y el handshake de Socket.IO, sin servir contenido; OTP y navegación reales
confirmados por el usuario; viewer y `/control` con assets servidos por HTTPS; Socket.IO con upgrade
WebSocket `101`, `tatami:state` recibido, ping/pong y reconexión con `sid` nuevo; asignación de prueba
(match 7 → `ready` con 0–0 y reloj sin arrancar) cancelada por `cancel_assignment` (ack
`{ok:true, revision:2}`, estado `null` y match de vuelta a candidatos); gate de escritura cerrado
(`503 result_write_disabled` con sesión viva, **0 `PUT`** y **0 `POST /api/token`** en Bracket);
regresión de `bjjvetusta` sin cambios; kill switch por retirada del ingress (solo Tatami) probado y
restaurado. Logs sin `5xx`, sin errores de WebSocket, sin bucles de reconexión y sin secretos ni OTP.
Detalle: `docs/11-demo-externa-cloudflare.md` §19.

Siguiente: **P2.6A.3 — centro de documentación `docs.opsforge.cc`** (manual del Tatami online, PDF
descargable, guía rápida A4, estructura para el manual de Bracket y enlaces futuros desde el portal
BJJ). **No ejecutado.**

## Publicación segura de la demo externa — P2.6A (preparado, NO publicado · 2026-10-02)

Documento: **`docs/11-demo-externa-cloudflare.md`**. Diseño y validación de la publicación de la
demo del Tatami 1 mediante Cloudflare Tunnel + allow-list por email, sin abrir puertos inbound en
Robledo ni exponer servicios internos. `cloudflared 2026.9.3` (arm64) instalado desde el repositorio
oficial de Cloudflare; origen `http://127.0.0.1:8080` con nginx como único gateway; rutas del Tatami 1
diseñadas y validadas con `nginx -t` **sin aplicar** (plantillas versionadas en `deploy/demo-tatami1/`,
fuera del bind mount de nginx). Exposición externa medida con sondas independientes: sólo 22/SSH
abierto; 8080, 8400, 8500, 3000 y 5432 filtrados → `new inbound ports opened = 0`.
`BRACKET_RESULT_WRITE_ENABLED=false` intacto (503 `result_write_disabled`, cero PUT al Bracket).

Pendiente para publicar: cuenta/dominio Cloudflare (túnel gestionado) o autorización de correos
reales (Quick Tunnel con `--allowed-mail`) y aplicar el cambio de nginx. El match 1 residual en
estado `ready` ya **no** es un pendiente: lo resolvió P2.6A.1.

## Operación administrativa `cancel_assignment` — P2.6A.1 (CLOSED ✅, 2026-10-02)

Commit `375e26c` `feat(scoreboard): allow safe ready assignment cancellation`. Nueva operación
administrativa que libera un combate asignado por error que nunca ha arrancado, sin forzar la máquina
de estados ni servir de atajo a `finish`: sólo se acepta sobre un match `ready` intacto (reloj
completo, marcador a cero, sin resultado) y rechaza `running`, `paused`, `awaiting_result` y
`finished` (`not_ready`) y cualquier `ready` con marcador (`not_clean`). Viaja **sólo por Socket.IO**
con la credencial de control (sin rutas HTTP nuevas) y el reintento del mismo `command_id` responde el
mismo ack sin volver a mutar. `/control` añade la acción separada "Cancelar asignación" en dos pasos,
independiente de "Liberar Tatami" (post-`finish`). 16 tests nuevos → 144/144 verdes.

Desplegado en producción sólo `scoreboard-tatami-1` con la imagen release
`danyseve1/bjj-scoreboard@sha256:6fe745874fffd1a83ede55c3716307e6829f2d51d6e385f8a4b5e3836b4c1c71`
(tag `375e26c-r1`, Compose pinneado por digest); Bracket, Bridge, PostgreSQL, nginx y WireGuard
intactos (mismos IDs, sin reinicios). Match 1 liberado por el flujo soportado (estado `null`,
`tatami:state null` difundido, persistido y conservado tras reinicio), candidatos del torneo 1 = 12
con match 1 de nuevo incluido, cero escrituras a Bracket y DB sin cambios. Detalle:
`docs/11-demo-externa-cloudflare.md` §17.

Pendiente para la demo externa (P2.6A.2, **no ejecutado**): aplicar el cambio de rutas de nginx y
publicar el Quick Tunnel autenticado por email/OTP.


## Cierre operativo P1.4 — CLOSED ✅ (2026-10-01)

Estado de configuración tras `91760f08e751acfa7597dcf9770e81fe1afb3bb9`:

| Servicio | Versión efectiva | Referencia Compose | Estado |
|---|---|---|---|
| Bracket | r3 (`e6abd7d-r3`) | `danyseve1/bracket-bjj@sha256:e07ec8b49ad8274229422c40a87331b285785a0b80120bb3111d05bb911e8df8` | sin cambios en P1.4; `AUTO_RUN_MIGRATIONS=false` |
| nginx | 1.27.5 | `nginx@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10` | P1.4.1 CLOSED ✅ (`a77d0e8`); runtime no recreado durante el pin |
| PostgreSQL | 16.14 | `postgres@sha256:bffa6baeb307a531d731bf3ef9835dc396afaeddf81944337b8f990b2109ffca` | P1.4.2 CLOSED ✅ (`91760f0`); sin upgrade ni recreación |

PostgreSQL conserva Image ID `sha256:88777d7cb0db2e0160fcf36277608f42920e517409316e2dbeafe6c844cb08ca`,
contenedor `0283c07f4d4b`, StartedAt `2026-10-01T15:03:21.749058926Z`, restarts=0,
volumen `bjj-tournament-platform_bracket_postgres_data` intacto y Alembic `c1ab44651e79`.
En la consulta del registro previa al pin, el tag remoto `postgres:16` ya apuntaba a **16.15**
(digest `sha256:1a6ab3f5345eb6dbe04a1349529caabdb0ab09293a09590fad07b2246bfa4b54`):
**NO se hizo upgrade**; se fijó el RepoDigest exacto de la 16.14 local ya en ejecución.
El pin fue exclusivamente declarativo, sin pull ni `compose up`; no cambia volumen, red, IP, env ni restart.
La referencia de creación del contenedor puede conservar el tag anterior: no implica deriva de imagen.

WireGuard: **FUERA DE CAMBIO — imagen funcional, no se modifica ni recrea en P1.4 por decisión operativa.**
`ghcr.io/linuxserver/wireguard:latest` sigue siendo un tag mutable: riesgo aceptado, no tarea inmediata.
`bridge-api` y `scoreboard-tatami-1..6` (perfil `multitatami`) quedan fuera de P1.4; se tratarán en P2.
Siguiente bloque del roadmap: **P1.5 — TLS interno de nginx**, pendiente de autorización y diseño.

## Plan de release del Tatami 1 — P2.5A (plan, sin ejecutar)

Documento: **`docs/10-plan-release-tatami1.md`**. Define, sin tocar producción, cómo desplegar de forma
controlada el Bracket corregido (`47bc129`), el Bridge API y el scoreboard integrado del Tatami 1 con
persistencia: inventario de cambios, imagen release de cada componente, target mínimo de Compose
(perfil propio `tatami1`, servicios nuevos sin publicar al host), red interna, secretos, orden
secuencial con gate humano, impacto del recreate de Bracket, rollback por componente, checklist de
validación y GO/NO-GO.

Estado de producción al planificar (sin cambios desde P1.4): Bracket `e6abd7d-r3` por digest, 4
contenedores con `restarts=0`, PostgreSQL 16.14 con Alembic `c1ab44651e79`, WireGuard fuera de cambio.
La escritura de resultados hacia Bracket sigue **desactivada por diseño**: el primer release arranca en
modo lectura (`BRACKET_RESULT_WRITE_ENABLED=false`, requisito previo a implementar) y sin credenciales
de escritura.

## Despliegue controlado de Tatami 1 — P2.5D (CLOSED ✅, 2026-10-02)

Tatami 1 desplegado en producción en tres pasos, cada uno validado antes del siguiente y sin tocar
PostgreSQL, nginx ni WireGuard: Bracket recreado con el digest release `8e9f2ca2…e9e1`
(`revision=47bc129d…`, `AUTO_RUN_MIGRATIONS=false`, `healthy`, `restarts=0`); `scoreboard-tatami-1`
arrancado en modo integrado con persistencia (`state_store {enabled,ready} = true`, `state.json` 0600
uid 1000, sin puertos publicados); `bjj-bridge-api` arrancado sin puertos publicados, con DNS interno
resuelto hacia `bracket` y `scoreboard-tatami-1`. Gate de escritura demostrado en producción:
`POST /tatamis/1/result` → **503 `result_write_disabled`** sin auth, sin lectura y sin `PUT` hacia
Bracket (set de rutas de `/api/metrics` idéntico antes/después). Candidates 200 coherente con la BD
(12 de grupo; knockout sin luchadores no son candidatos); `assign-match` 201 con estado `ready` y
recuperación correcta tras reiniciar solo el scoreboard. Postcheck de BD sin cambios y con el hash
SHA256 de `matches` idéntico al del backup pre-despliegue: cero modificaciones de datos. Rollback
preparado y no utilizado. Evidencia en §21 de `docs/10-plan-release-tatami1.md`.

## Pre-despliegue final y GO/NO-GO — P2.5C (GO, sin desplegar)

Publicadas las tres imágenes release (`danyseve1/bracket-bjj:47bc129-r3`,
`danyseve1/bjj-bridge-api:92d52df-r1`, `danyseve1/bjj-scoreboard:92d52df-r1`), arm64 y con sus
RepoDigests registrados; Compose fijado por digest para las tres (sin tags flotantes, sin `build:` en
Bridge ni scoreboard); secretos del contrato preparados en el `.env` productivo (modo 600, valores no
registrados, `BRACKET_RESULT_WRITE_ENABLED=false` y credenciales de escritura fuera); directorio de
estado `/home/ubuntu/data/bjj-tournament-platform/tatami-1` (1000:1000, 0700); backups pre-despliegue
de PostgreSQL, Compose y `.env` con evidencia sin secretos; baseline de BD verificado (2 torneos /
25 matches / 10 equipos / 16 rondas / 15 tablas, Alembic `c1ab44651e79`); render de Compose validado
(sin perfil los 4 servicios de siempre; con `--profile tatami1` + Bridge + `scoreboard-tatami-1`, sin
puertos nuevos) y comandos de rollback preparados. Checklist GO/NO-GO 18/18 YES, evidencia en §20 de
`docs/10-plan-release-tatami1.md`. Producción intacta: no se ejecutó `docker compose up` ni se recreó
nada.

## Prerrequisitos de release del Tatami 1 — P2.5B (artefactos listos, sin desplegar)

Implementados los prerrequisitos técnicos del plan `docs/10-plan-release-tatami1.md` sin desplegar nada:
flag `BRACKET_RESULT_WRITE_ENABLED` (por defecto `false`, fail-closed: `POST /tatamis/1/result`
responde 503 `result_write_disabled` sin leer el scoreboard ni llamar a Bracket), dependencias del
Bridge con versiones exactas, Dockerfile release (base por digest, no-root, healthcheck), healthcheck
real del scoreboard (`GET /health` en modo integrado), imágenes release de Bracket (`47bc129-r3`),
Bridge y scoreboard construidas y verificadas, y target de Compose `--profile tatami1` (servicios
nuevos sin publicar al host). Validación de punta a punta en una pila aislada con PostgreSQL temporal,
incluido el reinicio real del scoreboard (persistencia) y la comprobación de **cero** publicación de
resultados en Bracket. Evidencia en §19 de `docs/10-plan-release-tatami1.md`. Producción intacta;
commit `feat(release): prepare tatami 1 deployment artifacts`.

## Plan de fases de producto (referencia; no describe lo ya desplegado)

Las fases siguientes conservan el plan original. Su numeración no equivale a los gates operativos P0/P1/P2.

## Fase 0 - Repositorio limpio

Objetivo: preparar una base colaborativa.

Tareas:

- crear repositorio principal;
- crear estructura documental;
- añadir .env.example;
- añadir .gitignore;
- preparar README;
- crear carpetas base;
- definir estrategia de ramas.

## Fase 1 - Laboratorio local

Objetivo: levantar los servicios principales en local.

Tareas:

- desplegar Bracket;
- desplegar PostgreSQL;
- desplegar una instancia de BJJ-Scoreboard;
- validar login/API de Bracket;
- documentar puertos y accesos.

## Fase 2 - Multi-tatami

Objetivo: levantar 6 scoreboards simultáneos.

Tareas:

- crear servicios scoreboard-tatami-1 a scoreboard-tatami-6;
- exponer puertos 3001 a 3006;
- documentar URL de pantalla y control;
- validar acceso desde móvil/tablet;
- probar concurrencia básica.

## Fase 3 - Bridge API básico

Objetivo: crear la API propia de integración.

Tareas:

- crear servicio FastAPI;
- endpoint /health;
- endpoint para asignar combate a tatami;
- modelo de datos básico;
- logs;
- Dockerfile.

## Fase 4 - Integración Bracket -> Scoreboard

Objetivo: cargar combates desde Bracket hacia el marcador.

Tareas:

- consultar combates desde Bracket API;
- seleccionar combate pendiente;
- enviar datos al scoreboard;
- mapear luchador rojo/azul;
- registrar evento de asignación.

## Fase 5 - Resultado automático

Objetivo: cerrar el ciclo de competición.

Tareas:

- recibir resultado desde scoreboard;
- validar ganador;
- actualizar resultado en Bracket;
- evitar doble envío;
- auditar resultado.

## Fase 6 - Oracle Cloud A1

Objetivo: desplegar el entorno en cloud.

Tareas:

- preparar docker-compose.prod.yml;
- configurar Nginx;
- configurar WireGuard;
- restringir accesos;
- configurar backups de PostgreSQL;
- documentar operación.

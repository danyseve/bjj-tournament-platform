# 02 - Roadmap por fases

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

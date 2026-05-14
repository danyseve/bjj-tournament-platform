# 02 - Roadmap por fases

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

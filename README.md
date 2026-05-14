# BJJ Tournament Platform

Plataforma experimental para gestionar torneos de Brazilian Jiu-Jitsu con múltiples tatamis.

## Objetivo

El objetivo del proyecto es integrar un sistema de gestión de torneos basado en Bracket con múltiples instancias de BJJ-Scoreboard, permitiendo gestionar participantes, combates, tatamis y resultados desde una arquitectura self-hosted.

## Componentes principales

- **Bracket**: gestión de torneos, participantes, brackets, combates y resultados.
- **BJJ-Scoreboard**: marcador visual y panel de control para cada tatami.
- **Bridge API**: componente propio para sincronizar Bracket con los scoreboards.
- **PostgreSQL**: base de datos principal de Bracket.
- **Docker Compose**: despliegue local y cloud.
- **Nginx/WireGuard**: acceso seguro en despliegue remoto.

## Arquitectura objetivo

```text
VPN WireGuard
     |
Nginx Reverse Proxy
     |
------------------------------------------------
|                    |                         |
Bracket           Bridge API             Scoreboards
Tournament        Integration            Tatami 1-6
Management        Layer
     |
PostgreSQL
```
# 00 - Visión del proyecto

## Resumen

BJJ Tournament Platform es una plataforma experimental para gestionar torneos de Brazilian Jiu-Jitsu con múltiples tatamis funcionando en paralelo.

El objetivo es construir una solución self-hosted, basada en software open source, que permita a clubes pequeños o medianos organizar eventos sin depender de plataformas externas complejas o costosas.

## Problema que resuelve

En un torneo real puede haber varios tatamis funcionando simultáneamente. Cada tatami necesita:

- visualizar el marcador;
- controlar puntos, ventajas y penalizaciones;
- identificar correctamente a los competidores;
- registrar el resultado;
- avanzar el cuadro del torneo.

Actualmente Bracket puede cubrir la gestión del torneo y BJJ-Scoreboard puede cubrir el marcador, pero falta una capa de integración entre ambos.

## Solución propuesta

Crear una arquitectura compuesta por:

- Bracket como sistema central de torneo.
- PostgreSQL como base de datos.
- Una instancia de BJJ-Scoreboard por tatami.
- Bridge API como capa de integración.
- Docker Compose como sistema de despliegue.
- WireGuard/Nginx para acceso seguro en cloud.

## Objetivo MVP

El MVP debe permitir:

1. crear un torneo en Bracket;
2. levantar 6 scoreboards, uno por tatami;
3. asignar combates a cada tatami;
4. mostrar los nombres de los competidores en el scoreboard;
5. registrar resultados;
6. sincronizar resultados con Bracket en una fase posterior.


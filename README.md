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

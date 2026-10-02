---
title: Centro de documentación OpsForge
slug: index
short: Inicio
version: v0.1
date: 2026-10-02
project: OpsForge · BJJ Vetusta / Asturkon
state: Draft
order: 0
---

# Centro de documentación OpsForge

Documentación operativa del sistema de competición de **BJJ Vetusta / Asturkon**:
tatamis, cuadro del torneo y organización del evento.

## Manuales

| Manual | Contenido | Estado |
|---|---|---|
| [Manual del Tatami / Árbitro](/bjj/tatami/) | Mesa del tatami: acceso, marcador, reloj, puntos, ventajas, penalizaciones, finalizar, liberar y cancelar | Draft v0.1 |
| [Guía rápida — Árbitro (A4)](/bjj/guia-rapida/) | Una página para imprimir y plastificar | Draft v0.1 |
| [Manual de Bracket (estructura)](/bjj/bracket/) | Torneo, categorías, competidores, equipos, stages, cuadro, combates y resultados | Draft v0.1 |
| [Manual del Organizador (estructura)](/bjj/organizador/) | Preparación, día de torneo y cierre | Draft v0.1 |

## Descargas

- [Manual del Tatami / Árbitro v0.1 (PDF)](/manual-arbitro-tatami-v0.1.pdf)
- [Guía rápida — Árbitro Tatami v0.1 (PDF, A4)](/guia-rapida-arbitro-tatami-v0.1.pdf)
- [Manual de Bracket v0.1 (PDF, estructura)](/manual-bracket-v0.1.pdf)

Los PDF se generan desde la misma fuente Markdown que las páginas HTML
(`docs-site/build.py`); no se editan a mano.

## Estado de la documentación

- **Draft**: en uso interno, pendiente de validación por un árbitro y de revisión operativa.
- **Validated**: contenido revisado contra el sistema en producción.
- **Published**: entregado a los usuarios finales del torneo.

Los manuales pendientes (write-back del resultado a Bracket, roles internos de árbitro, portal
del operador) se marcan de forma explícita en cada documento.

## Aviso

El resultado del tatami **no se escribe** hoy en Bracket
(`BRACKET_RESULT_WRITE_ENABLED=false`): el árbitro debe **anotar el acta** antes de liberar el
tatami.

## Enlaces

- Tatami 1: `https://tatami1.opsforge.cc` (viewer) y `https://tatami1.opsforge.cc/control` (mesa)
- Bracket: `https://bjjvetusta.opsforge.cc`
- Repositorio: `https://github.com/danyseve/bjj-tournament-platform` (privado)

*Manual operativo del árbitro pendiente; antes de entregar `/control` a usuarios finales se
publicará documentación online y PDF.*

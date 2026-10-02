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
| [Quick Start — Acceso a BJJ Vetusta / OpsForge](/bjj/quick-start/) | Cómo se entra a cada herramienta: matriz de acceso, flujo y gestión de árbitros (referencia permanente de la política de acceso) | Validated v0.1 |
| [Manual del Tatami / Árbitro](/bjj/tatami/) | Mesa del tatami: acceso, marcador, reloj, puntos, ventajas, penalizaciones, finalizar, liberar y cancelar | Draft v0.1 |
| [Guía rápida — Árbitro (A4)](/bjj/guia-rapida/) | Una página para imprimir y plastificar | Draft v0.1 |
| [Manual de Bracket (estructura)](/bjj/bracket/) | Torneo, categorías, competidores, equipos, stages, cuadro, combates y resultados | Draft v0.1 |
| [Manual del Organizador (estructura)](/bjj/organizador/) | Preparación, día de torneo y cierre | Draft v0.1 |

## Descargas

- [Quick Start — Acceso a BJJ Vetusta / OpsForge v0.1 (PDF)](/quick-start-acceso-opsforge-v0.1.pdf)
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

- Portal del torneo: `https://bjjvetusta.opsforge.cc` (Tatami 1–6, Bracket, manuales, GitHub)
- Tatami 1: `https://tatami1.opsforge.cc` (viewer) y `https://tatami1.opsforge.cc/control` (mesa)
- Bracket: `https://bracket.opsforge.cc`
- Repositorio: `https://github.com/danyseve/bjj-tournament-platform` (privado)

## Portal del torneo (P2.6B, 2026-10-02)

El **portal BJJ Vetusta / Asturkon** vive en `bjjvetusta.opsforge.cc` y es la puerta de entrada
del equipo: tarjetas de Tatami 1–6 (Tatami 2–6 marcados PRÓXIMAMENTE, sin botón activo),
Bracket (`bracket.opsforge.cc`) y el repositorio. Cada tarjeta enlaza también a su manual y a
su PDF en este centro. El portal sirve estado **estático**: no consulta APIs internas.

Pendientes (mini-tareas atómicas, no bloquean el cierre):

- La pantalla de `/control` del tatami llevará un enlace `? Manual` a `/bjj/tatami/` (implica
  reconstruir la imagen del marcador; no se ha tocado su UI).
- Capturas reales (hoy solo esquemas anotados; ver `CAPTURAS.md`).

*Este centro de documentación se mantiene desde el repositorio
(`docs-site/`, una sola fuente Markdown para HTML y PDF).*

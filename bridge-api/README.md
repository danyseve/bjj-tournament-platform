# BJJ Bridge API

API de integración entre Bracket y BJJ-Scoreboard.

## Objetivo

Este servicio permite coordinar combates entre el sistema central de torneo y los marcadores de cada tatami.

## Funciones previstas

- Consultar disponibilidad de Bracket.
- Asignar combate a un tatami.
- Enviar datos del combate al scoreboard correspondiente.
- Recibir resultado del combate.
- Actualizar resultado en Bracket.

## Endpoints iniciales

```text
GET  /health
GET  /health/bracket
POST /tatamis/{tatami_id}/assign-match
POST /tatamis/{tatami_id}/result

# 01 - Arquitectura

## Componentes

```text
Usuario / Organización
        |
        v
Bracket UI
        |
        v
Bracket API ---- PostgreSQL
        |
        v
Bridge API
        |
        +--> Scoreboard Tatami 1
        +--> Scoreboard Tatami 2
        +--> Scoreboard Tatami 3
        +--> Scoreboard Tatami 4
        +--> Scoreboard Tatami 5
        +--> Scoreboard Tatami 6

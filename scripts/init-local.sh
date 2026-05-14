#!/usr/bin/env bash

set -e

echo "Inicializando entorno local BJJ Tournament Platform..."

if [ ! -f .env ]; then
  echo "No existe .env. Creando desde .env.example..."
  cp .env.example .env
fi

echo "Construyendo servicios..."
docker compose build

echo "Levantando servicios..."
docker compose up -d

echo "Estado de contenedores:"
docker compose ps

echo "Entorno local iniciado."
echo "Bracket: http://localhost:8400"
echo "Bridge API: http://localhost:8500/health"
echo "Scoreboard Tatami 1: http://localhost:3001"
echo "Scoreboard Tatami 2: http://localhost:3002"
echo "Scoreboard Tatami 3: http://localhost:3003"
echo "Scoreboard Tatami 4: http://localhost:3004"
echo "Scoreboard Tatami 5: http://localhost:3005"
echo "Scoreboard Tatami 6: http://localhost:3006"

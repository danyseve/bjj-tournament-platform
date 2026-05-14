#!/usr/bin/env bash

set -e

echo "ATENCIÓN: esto eliminará contenedores y volumen de PostgreSQL del laboratorio."
read -p "¿Continuar? Escribe YES: " CONFIRM

if [ "$CONFIRM" != "YES" ]; then
  echo "Operación cancelada."
  exit 0
fi

docker compose down -v

echo "Entorno reseteado."
echo "Puedes iniciar de nuevo con: ./scripts/init-local.sh"

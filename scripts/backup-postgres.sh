#!/usr/bin/env bash

set -e

BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/bracket_${TIMESTAMP}.sql"

mkdir -p "${BACKUP_DIR}"

echo "Creando backup PostgreSQL en ${BACKUP_FILE}..."

docker exec bracket-postgres pg_dump \
  -U "${POSTGRES_USER:-bracket_dev}" \
  "${POSTGRES_DB:-bracket_dev}" > "${BACKUP_FILE}"

echo "Backup completado: ${BACKUP_FILE}"

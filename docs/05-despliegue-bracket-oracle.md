# 05 - Despliegue de Bracket en Oracle Cloud A1

## Incidencia detectada: migraciones Alembic en base limpia

Durante el despliegue de Bracket con PostgreSQL limpio, el servicio fallaba en el arranque al ejecutar migraciones Alembic.

Error detectado:

```text
psycopg2.errors.UndefinedObject: index "ix_users_email" does not exist

[SQL:
DROP INDEX ix_users_email]```

El script conflictivo estaba en:

/app/alembic/versions/274385f2a757_add_on_delete_cascade_to_users_x_clubs.py

La migración intentaba borrar el índice ix_users_email, pero en una base PostgreSQL limpia dicho índice todavía no existía.

Solución aplicada para laboratorio

Se ejecutó el comando de inicialización de base de datos en modo DEVELOPMENT:

docker compose run --rm --entrypoint "" \
  -e ENVIRONMENT=DEVELOPMENT \
  bracket uv run --no-dev ./cli.py create-dev-db



Resultado

El comando creó correctamente las tablas iniciales:

alembic_version
clubs
courts
matches
players
players_x_teams
rankings
rounds
stage_item_inputs
stage_items
stages
teams
tournaments
users
users_x_clubs

Después de inicializar la base, Bracket arrancó correctamente en modo PRODUCTION.

Validación
docker compose up -d bracket

docker ps -a

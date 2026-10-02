#!/usr/bin/env sh
# Construye el Centro de Documentacion y recarga nginx SIN recrear el contenedor.
#
# Por que asi: el frontal bjj-nginx solo monta nginx/conf.d, asi que la salida del
# build vive en nginx/conf.d/docs-site (versionada en git) y se sirve directamente.
# La recarga es graceful: no hay caida de servicio ni cambio de contenedor.
#
# Uso:  ./deploy.sh            (construye + valida + recarga)
#       ./deploy.sh --quiet    (sin detalle)
#       NO_BUILD=1 ./deploy.sh (solo valida y recarga)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
VENV=${DOCS_VENV:-/home/ubuntu/.cache/docs-build/venv}
NGINX_CT=${DOCS_NGINX_CT:-bjj-nginx}

if [ "${NO_BUILD:-0}" != "1" ]; then
  if [ ! -x "$VENV/bin/python" ]; then
    echo "ERROR: no existe el venv de build en $VENV" >&2
    echo "  crealo con: python3 -m venv --without-pip $VENV" >&2
    echo "              curl -sS https://bootstrap.pypa.io/get-pip.py | $VENV/bin/python" >&2
    echo "              $VENV/bin/pip install -r $HERE/requirements.txt" >&2
    exit 1
  fi
  "$VENV/bin/python" "$HERE/build.py" "$@"
fi

docker exec "$NGINX_CT" nginx -t
docker exec "$NGINX_CT" nginx -s reload
echo "OK: docs desplegadas y nginx recargado (sin recrear el contenedor)"

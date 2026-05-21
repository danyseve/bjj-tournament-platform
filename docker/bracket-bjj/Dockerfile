FROM ghcr.io/evroon/bracket:latest

USER root

ARG BRACKET_PUBLIC_BASE_URL=http://bjj-bracket.local:8400

RUN echo "Patching Bracket frontend localhost API references..." && \
    grep -RIl "http://localhost:8400/api" /app/frontend-dist 2>/dev/null | \
      xargs -r sed -i "s#http://localhost:8400/api#/api#g" && \
    grep -RIl "http://localhost:8400" /app/frontend-dist 2>/dev/null | \
      xargs -r sed -i "s#http://localhost:8400##g" && \
    echo "Patching Bracket backend base_url..." && \
    cp -f /app/bracket/config.py /app/bracket/config.py.bak && \
    sed -i "s#http://localhost:8400#${BRACKET_PUBLIC_BASE_URL}#g" /app/bracket/config.py && \
    mkdir -p /app/.cache/uv /tmp/uv-cache && \
    chmod -R 777 /app/.cache /tmp/uv-cache && \
    echo "Patch validation:" && \
    grep -R "localhost:8400" -n /app 2>/dev/null | grep -v ".bak" || true

ENV HOME=/app
ENV UV_CACHE_DIR=/tmp/uv-cache

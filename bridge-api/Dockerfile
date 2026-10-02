# Bridge API — release image (P2.5B).
#
# Deterministic by construction: the base image is pinned by digest (linux/arm64)
# and every dependency by exact version, so the same inputs produce the same
# image. The service runs unprivileged and carries no build or test tooling.
FROM python:3.12-slim@sha256:18d23907c5d7ef2ca1b0ea8b4a73fe4a6ae47114c257a1afed8bc66c3886f8cb

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer only changes when requirements.txt changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && python -c "import fastapi, uvicorn, httpx, pydantic, pydantic_settings"

# Only the application package: no tests, no dev requirements, no repository copy.
COPY app ./app

# Unprivileged runtime user with a fixed id, so ownership of anything the service
# ever needs to write from the host side is predictable.
RUN useradd --system --uid 10002 --shell /usr/sbin/nologin bridge

# No real world-writable entry is expected inside the image (same probe as the
# Bracket recipe: real files/directories only, nothing chmod'ed).
RUN set -eu; \
    ww="$(find /app -xdev \( -type f -o -type d \) -perm -0002)"; \
    if [ -n "$ww" ]; then \
        echo "ERROR: world-writable entry under /app:" >&2; \
        printf '%s\n' "$ww" | sed 's/^/  /' >&2; \
        exit 1; \
    fi

USER bridge

EXPOSE 8500

# Real probe against the service's own health endpoint. python is the interpreter
# the image is built around, so liveness is checked without installing curl/wget;
# a non-200 answer or a connection error exits non-zero and the container is
# reported unhealthy instead of "running".
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/health', timeout=4)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8500"]

# Build context: repository root.
# Source: services/scoreboard @ c49df6d6a0deb731573a1030dc68b9f46d791642.
# Base pinned for linux/arm64/v8; Node 22 LTS, Debian bookworm.
FROM node:22.23.3-bookworm-slim@sha256:a0ddbc73510e98f5e824fd64266ffe1c2c343ba9cf260d95ca2985ad632a3f3e

LABEL org.opencontainers.image.title="BJJ Scoreboard" \
      org.opencontainers.image.revision="c49df6d6a0deb731573a1030dc68b9f46d791642"

ENV NODE_ENV=production \
    PORT=3000
WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node services/scoreboard/package.json services/scoreboard/package-lock.json ./
RUN printf '%s  package-lock.json\n' 'd72d7904955d643be5043ab49c088deb32df96399fdd6ffebb2fedf5363f62ea' | sha256sum -c - \
    && npm ci --omit=dev --no-audit --no-fund \
    && printf '%s  package-lock.json\n' 'd72d7904955d643be5043ab49c088deb32df96399fdd6ffebb2fedf5363f62ea' | sha256sum -c - \
    && npm cache clean --force

COPY --chown=node:node services/scoreboard/app.js ./app.js
COPY --chown=node:node services/scoreboard/routes/ ./routes/
COPY --chown=node:node services/scoreboard/views/ ./views/
COPY --chown=node:node services/scoreboard/public/ ./public/
RUN node --check app.js && node --check routes/index.js && node --check public/js/main.js

EXPOSE 3000
CMD ["npm", "start"]

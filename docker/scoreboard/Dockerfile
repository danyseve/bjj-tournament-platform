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

# Persistence mount point (P2.5B): the release points SCOREBOARD_STATE_FILE here
# and mounts the host directory over it. Created with the runtime user's ownership
# so the service can write without privileges; a bind mount owned by anybody else
# makes /health report the state store as not ready instead of failing silently.
# Created while still root: / is not writable by the runtime user by design.
RUN mkdir -p /state && chown node:node /state
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
COPY --chown=node:node scoreboard-adapter/launcher.js scoreboard-adapter/integrated.js scoreboard-adapter/state.js scoreboard-adapter/state-store.js scoreboard-adapter/integrated-ui.js ./scoreboard-adapter/
RUN node --check scoreboard-adapter/launcher.js && node --check scoreboard-adapter/integrated.js && node --check scoreboard-adapter/state.js && node --check scoreboard-adapter/state-store.js && node --check scoreboard-adapter/integrated-ui.js
RUN node --check app.js && node --check routes/index.js && node --check public/js/main.js

EXPOSE 3000

# Real HTTP probe: integrated mode answers /health itself (state store readiness
# included), the legacy standalone app keeps serving / exactly as before. A status
# outside 2xx/3xx, a timeout or a connection error marks the container unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "const http=require('node:http');const target=process.env.SCOREBOARD_MODE==='integrated'?'/health':'/';const req=http.get({host:'127.0.0.1',port:process.env.PORT||3000,path:target,timeout:4000},res=>{res.resume();process.exit(res.statusCode>=200&&res.statusCode<400?0:1);});req.on('timeout',()=>{req.destroy();process.exit(1);});req.on('error',()=>process.exit(1));"]

CMD ["node", "scoreboard-adapter/launcher.js"]

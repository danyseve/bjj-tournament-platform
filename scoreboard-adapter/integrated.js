'use strict';
const express = require('express');
const path = require('node:path');
const http = require('node:http');
const cookieParser = require('cookie-parser');
const crypto = require('node:crypto');
const logger = require('morgan');
const createError = require('http-errors');
const {Server} = require('socket.io');
const {createStore} = require('./state');
const {createStateFile} = require('./state-store');

// Control credential cookie: a separate secret from the Bridge internal token.
// It is delivered only to the control pages as HttpOnly (page scripts never
// read it), never placed in a query string and never logged. Unset => every
// tatami:update is refused (fail-closed). The display page never gets it.
const CONTROL_COOKIE = 'scoreboard_control';
const CONTROL_ROUTES = ['/control', '/control2'];
const CLOCK_TICK_MS = 1000;

function sameSecret(provided, expected) {
 return typeof expected === 'string' && expected.length > 0 && typeof provided === 'string'
  && provided.length === expected.length && crypto.timingSafeEqual(Buffer.from(provided), Buffer.from(expected));
}
function cookieValue(header, name) {
 if (typeof header !== 'string') return undefined;
 for (const part of header.split(';')) {
  const index = part.indexOf('=');
  if (index === -1) continue;
  if (part.slice(0, index).trim() === name) return decodeURIComponent(part.slice(index + 1).trim());
 }
 return undefined;
}

// Reuse legacy modules without importing app.js (which starts its own server).
function createServer(legacyRoot = '/app') {
 const app = express();
 // Optional persistence. Without SCOREBOARD_STATE_FILE the integrated server keeps
 // behaving exactly as before (memory only) and the standalone app is untouched.
 const statePath = process.env.SCOREBOARD_STATE_FILE || '';
 const stateFile = statePath.length > 0 ? createStateFile({file: statePath}) : null;
 const store = createStore({persist: stateFile === null ? undefined : document => stateFile.save(document)});
 if (stateFile !== null) {
  // Recovery happens before the server listens: an unreadable, corrupt or
  // unexpected document aborts startup instead of booting an empty tatami over
  // a real one, and the bad file is left exactly as it was found.
  const stored = stateFile.load();
  if (stored !== undefined) store.restore(stored);
 }
 // Internal API is fail-closed: without a configured token every /internal request is refused.
 // The browser/UI never receives this token; only the Bridge uses it.
 const internalToken = process.env.SCOREBOARD_INTERNAL_TOKEN || '';
 const controlToken = process.env.SCOREBOARD_CONTROL_TOKEN || '';
 const requireInternalToken = (req, res, next) => {
  const provided = req.get('x-internal-token');
  if (typeof internalToken !== 'string' || internalToken.length === 0 || typeof provided !== 'string'
   || provided.length !== internalToken.length
   || !crypto.timingSafeEqual(Buffer.from(provided), Buffer.from(internalToken))) {
   return res.status(401).json({error: 'Internal token required'});
  }
  next();
 };
 app.set('views', path.join(legacyRoot, 'views'));
 app.set('view engine', 'pug');
 app.use(logger('dev'));
 app.use(express.json());
 app.use(express.urlencoded({extended: false}));
 app.use(cookieParser());
 app.get('/js/main.js', (req, res) => res.sendFile(path.join(__dirname, 'integrated-ui.js')));
 app.use(express.static(path.join(legacyRoot, 'public')));
 // Only the control pages receive the control credential; the display never does.
 for (const route of CONTROL_ROUTES) {
  app.get(route, (req, res, next) => {
   if (controlToken.length > 0) res.cookie(CONTROL_COOKIE, controlToken, {httpOnly: true, sameSite: 'strict', path: '/'});
   next();
  });
 }
 const server = http.createServer(app);
 const io = new Server(server);
 io.use((socket, next) => {
  socket.data.control = sameSecret(cookieValue(socket.handshake.headers.cookie, CONTROL_COOKIE), controlToken);
  next();
 });
 io.on('connection', socket => {
  socket.on('bjj:score', data => io.sockets.emit('bjj:score', data));
  socket.on('bjj:restart', data => io.sockets.emit('bjj:restart', data));
  socket.on('bjj:start', data => io.sockets.emit('bjj:start', data));
  socket.on('bjj:name', data => socket.broadcast.emit('bjj:name', data));
  // Canonical commands: the server applies them and answers with an explicit ack.
  socket.on('tatami:update', (command, ack) => {
   const respond = typeof ack === 'function' ? ack : () => {};
   if (socket.data.control !== true) {
    const current = store.snapshot();
    return respond({ok: false, code: 'unauthorized', revision: current === null ? 0 : current.revision});
   }
   const result = store.apply(command);
   if (result.ok === true) {
    // Every accepted change is broadcast to every client, including the sender.
    if (result.changed === true) io.emit('tatami:state', result.state);
    return respond({ok: true, command_id: result.command_id, revision: result.revision});
   }
   respond({ok: false, code: result.code, revision: result.revision});
  });
  const snapshot = store.snapshot();
  if (snapshot !== null) socket.emit('tatami:state', snapshot);
 });
 // Authoritative clock: while running, every client receives the recomputed
 // remaining time taken from the server's monotonic clock.
 const ticker = setInterval(() => {
  if (store.running() === true) io.emit('tatami:state', store.snapshot());
 }, CLOCK_TICK_MS);
 ticker.unref();
 server.on('close', () => clearInterval(ticker));
 // Read-only health probe (P2.5B). Deliberately unauthenticated so a container
 // healthcheck does not need the internal token, and deliberately silent about
 // everything else: no state contents, no fight identity, no secret. It reports
 // the mode it runs in and whether the optional state file could be written,
 // which is the part of readiness a process that is merely "up" does not prove.
 // A configured store that cannot be written is a failure, not a warning: the
 // answer is 503 so the container is reported unhealthy instead of quietly
 // scoring a tatami whose result would be lost on restart.
 app.get('/health', (req, res) => {
  const enabled = stateFile !== null;
  const ready = enabled && stateFile.ready();
  res.status(enabled && !ready ? 503 : 200).json({
   status: enabled && !ready ? 'degraded' : 'ok',
   service: 'bjj-scoreboard',
   mode: 'integrated',
   state_store: {enabled, ready}
  });
 });
 app.get('/internal/tatamis/1/state', requireInternalToken, (req, res) => res.json({state: store.snapshot()}));
 app.put('/internal/tatamis/1/assignment', requireInternalToken, (req, res) => {
  const result = store.assign(req.body);
  if (result.status === 400) return res.status(400).json({error: 'Invalid normalized assignment'});
  if (result.status === 409) return res.status(409).json({error: 'Tatami already has an active assignment'});
  // 503: the assignment could not be persisted, so it was rolled back and is not
  // announced as delivered (nothing is emitted to the clients either).
  if (result.status === 503) return res.status(503).json({error: 'State could not be persisted'});
  io.emit('tatami:state', store.snapshot());
  res.status(result.status).json({state: result.state});
 });
 app.use('/', require(path.join(legacyRoot, 'routes')));
 app.use((req, res, next) => next(createError(404)));
 app.use((err, req, res, next) => {
  if (req.path.startsWith('/internal/')) return res.status(err.status || 500).json({error: err.status === 400 ? 'Invalid JSON body' : 'Request failed'});
  res.locals.message = err.message;
  res.locals.error = req.app.get('env') === 'development' ? err : {};
  res.status(err.status || 500).render('error');
 });
 return {app, server, io};
}
module.exports = {createServer};

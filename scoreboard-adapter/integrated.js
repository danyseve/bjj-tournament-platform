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

// Reuse legacy modules without importing app.js (which starts its own server).
function createServer(legacyRoot = '/app') {
 const app = express();
 const store = createStore();
 // Internal API is fail-closed: without a configured token every /internal request is refused.
 // The browser/UI never receives this token; only the Bridge uses it.
 const internalToken = process.env.SCOREBOARD_INTERNAL_TOKEN || '';
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
 const server = http.createServer(app);
 const io = new Server(server);
 io.on('connection', socket => {
  socket.on('bjj:score', data => io.sockets.emit('bjj:score', data));
  socket.on('bjj:restart', data => io.sockets.emit('bjj:restart', data));
  socket.on('bjj:start', data => io.sockets.emit('bjj:start', data));
  socket.on('bjj:name', data => socket.broadcast.emit('bjj:name', data));
  const snapshot = store.snapshot();
  if (snapshot !== null) socket.emit('tatami:state', snapshot);
 });
 app.get('/internal/tatamis/1/state', requireInternalToken, (req, res) => res.json({state: store.snapshot()}));
 app.put('/internal/tatamis/1/assignment', requireInternalToken, (req, res) => {
  const result = store.assign(req.body);
  if (result.status === 400) return res.status(400).json({error: 'Invalid normalized assignment'});
  if (result.status === 409) return res.status(409).json({error: 'Tatami already has an active assignment'});
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

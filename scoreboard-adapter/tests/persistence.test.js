'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const {createStore, validateDocument, InvalidStateError} = require('../state');
const {createStateFile, StateFileError} = require('../state-store');

const ADAPTER = path.join(__dirname, '..');
const LEGACY_ROOT = path.join(ADAPTER, '..', 'services', 'scoreboard');

function workspace(label) {
 const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'bjj-state-' + label + '-'));
 const file = path.join(directory, 'state.json');
 return {
  directory, file,
  read: () => JSON.parse(fs.readFileSync(file, 'utf8')),
  raw: () => fs.readFileSync(file, 'utf8'),
  entries: () => fs.readdirSync(directory),
  cleanup: () => fs.rmSync(directory, {recursive: true, force: true}),
 };
}
function normalized(match_id = 42, duration_seconds = 600) {
 return {
  tournament_id: 1, match_id, tatami_id: 1,
  fighter_a: {stage_item_input_id: 21, team_id: 101, name: 'Ana', club: null},
  fighter_b: {stage_item_input_id: 22, team_id: 102, name: 'Bea', club: null},
  category: {stage_item_id: 2, name: 'Adulto -70'},
  duration_seconds,
 };
}
// Fake wall and monotonic clocks: no test ever sleeps.
function clock(monotonic = 1000, wall = 1700000000000) {
 const time = {monotonic, wall};
 return {
  now: () => time.monotonic, wallNow: () => time.wall,
  advance(ms) {time.monotonic += ms; time.wall += ms;},
  peek: () => ({...time}),
 };
}
function setup(options = {}) {
 const space = workspace(options.label || 'p');
 const time = options.time || clock();
 const files = createStateFile({file: space.file, fs: options.fs});
 const store = createStore({persist: document => files.save(document), now: time.now, wallNow: time.wallNow});
 return {space, time, files, store};
}
// A second store reading the same file, exactly like a restart would.
function revive(space, time = clock()) {
 const files = createStateFile({file: space.file});
 const store = createStore({persist: document => files.save(document), now: time.now, wallNow: time.wallNow});
 const stored = files.load();
 const snapshot = stored === undefined ? null : store.restore(stored);
 return {files, store, stored, snapshot};
}
function command(state, operation, extra = {}) {
 return {session_id: state.session_id, command_id: extra.command_id || randomUUID(), expected_revision: state.revision,
  tatami_id: 1, match_id: state.match_id, operation, ...extra};
}
function run(store, operation, extra = {}) {
 return store.apply(command(store.snapshot(), operation, extra));
}
function finishedMatch(store, time) {
 store.assign(normalized(42, 600));
 run(store, 'set_running', {running: true});
 time.advance(60_000);
 return run(store, 'finish', {winner_team_id: 101, method: 'points'});
}

// --- escritura -----------------------------------------------------------
test('01 — el assignment nuevo se persiste', t => {
 const {space, store} = setup({label: 'assign'});
 t.after(() => space.cleanup());
 const created = store.assign(normalized(42, 600));
 assert.equal(created.status, 201);
 const stored = space.read();
 assert.deepEqual(Object.keys(stored), ['schema_version', 'saved_at', 'clock', 'state', 'command_history']);
 assert.equal(stored.schema_version, 1);
 assert.equal(stored.state.session_id, created.state.session_id);
 assert.equal(stored.state.revision, 1);
 assert.equal(stored.state.status, 'ready');
 assert.equal(stored.state.remaining_seconds, 600);
 assert.equal(stored.clock.wall_anchor, null);
 assert.deepEqual(stored.command_history, []);
});

test('02 — el scoring se persiste con su revision y su command_id', t => {
 const {space, store} = setup({label: 'score'});
 t.after(() => space.cleanup());
 store.assign(normalized());
 const ack = run(store, 'score_delta', {fighter: 'a', field: 'points', delta: 2});
 assert.equal(ack.ok, true);
 const stored = space.read();
 assert.equal(stored.state.fighter_a.points, 2);
 assert.equal(stored.state.revision, 2);
 assert.equal(stored.command_history.length, 1);
 assert.equal(stored.command_history[0].command_id, ack.command_id);
 assert.deepEqual(stored.command_history[0].ack, {ok: true, command_id: ack.command_id, revision: 2, changed: false});
});

test('03 — la pausa se persiste con el tiempo congelado', t => {
 const time = clock();
 const {space, store} = setup({label: 'pause', time});
 t.after(() => space.cleanup());
 store.assign(normalized(42, 600));
 run(store, 'set_running', {running: true});
 time.advance(30_000);
 assert.equal(run(store, 'set_running', {running: false}).ok, true);
 const stored = space.read();
 assert.equal(stored.state.status, 'paused');
 assert.equal(stored.state.remaining_seconds, 570);
 assert.equal(stored.clock.wall_anchor, null);
});

test('04 — el finish se persiste con ganador, metodo y reloj parado', t => {
 const time = clock();
 const {space, store} = setup({label: 'finish', time});
 t.after(() => space.cleanup());
 assert.equal(finishedMatch(store, time).ok, true);
 const stored = space.read();
 assert.equal(stored.state.status, 'finished');
 assert.equal(stored.state.winner_team_id, 101);
 assert.equal(stored.state.method, 'points');
 assert.equal(stored.state.remaining_seconds, 540);
 assert.equal(stored.clock.wall_anchor, null);
});

test('05 — clear_match persiste state:null explicito y limpia el historial', t => {
 const time = clock();
 const {space, store} = setup({label: 'clear', time});
 t.after(() => space.cleanup());
 finishedMatch(store, time);
 assert.equal(run(store, 'clear_match').ok, true);
 const stored = space.read();
 assert.equal(stored.state, null);
 assert.deepEqual(stored.command_history, []);
 assert.equal(stored.clock.wall_anchor, null);
 assert.deepEqual(space.entries(), ['state.json'], 'el fichero se conserva con null explicito, no se borra');
});

// --- recovery ------------------------------------------------------------
test('06 — recovery de un combate ready', t => {
 const {space, store, time} = setup({label: 'ready'});
 t.after(() => space.cleanup());
 store.assign(normalized(42, 600));
 const revived = revive(space, time);
 const snapshot = revived.store.snapshot();
 assert.equal(snapshot.status, 'ready');
 assert.equal(snapshot.remaining_seconds, 600, 'la duracion completa sigue ahi');
 assert.equal(snapshot.revision, 1);
 assert.equal(revived.store.running(), false);
});

test('07 — recovery de un combate paused con el tiempo congelado', t => {
 const time = clock();
 const {space, store} = setup({label: 'paused', time});
 t.after(() => space.cleanup());
 store.assign(normalized(42, 600));
 run(store, 'set_running', {running: true});
 time.advance(30_000);
 run(store, 'set_running', {running: false});
 const revived = revive(space, time);
 assert.equal(revived.store.snapshot().status, 'paused');
 assert.equal(revived.store.snapshot().remaining_seconds, 570);
 assert.equal(revived.store.running(), false, 'pausado sigue congelado');
 time.advance(120_000);
 assert.equal(revived.store.snapshot().remaining_seconds, 570, 'el tiempo no corre en pausa');
});

test('08 — recovery de un combate awaiting_result', t => {
 const time = clock();
 const {space, store} = setup({label: 'awaiting', time});
 t.after(() => space.cleanup());
 store.assign(normalized(42, 4));
 run(store, 'set_running', {running: true});
 time.advance(5_000);
 assert.equal(store.snapshot().status, 'awaiting_result');
 const revived = revive(space, time);
 const snapshot = revived.store.snapshot();
 assert.equal(snapshot.status, 'awaiting_result');
 assert.equal(snapshot.remaining_seconds, 0);
 assert.equal(snapshot.winner_team_id, null);
 assert.equal(revived.store.running(), false);
 assert.equal(run(revived.store, 'score_delta', {fighter: 'a', field: 'points', delta: 1}).code, 'awaiting_result');
 assert.equal(run(revived.store, 'finish', {winner_team_id: 101, method: 'decision'}).ok, true, 'finish sigue siendo la unica salida');
});

test('09 — recovery de un combate finished congelado', t => {
 const time = clock();
 const {space, store} = setup({label: 'finished', time});
 t.after(() => space.cleanup());
 finishedMatch(store, time);
 const revived = revive(space, time);
 const snapshot = revived.store.snapshot();
 assert.equal(snapshot.status, 'finished');
 assert.equal(snapshot.winner_team_id, 101);
 assert.equal(snapshot.method, 'points');
 assert.equal(snapshot.remaining_seconds, 540);
 time.advance(600_000);
 assert.equal(revived.store.snapshot().remaining_seconds, 540, 'el reloj de un combate cerrado no corre');
 const refused = run(revived.store, 'score_delta', {fighter: 'a', field: 'points', delta: 1});
 assert.equal(refused.code, 'already_finished');
});

test('10 — recovery de un combate running descuenta el tiempo transcurrido', t => {
 const time = clock();
 const {space, store} = setup({label: 'running', time});
 t.after(() => space.cleanup());
 store.assign(normalized(42, 600));
 run(store, 'set_running', {running: true});
 time.advance(100_000);
 run(store, 'score_delta', {fighter: 'a', field: 'points', delta: 2});
 const stored = space.read();
 assert.equal(stored.state.remaining_seconds, 500);
 assert.equal(stored.clock.wall_anchor, time.peek().wall);
 time.advance(90_000);
 const revived = revive(space, time);
 const snapshot = revived.store.snapshot();
 assert.equal(snapshot.status, 'running');
 assert.equal(snapshot.remaining_seconds, 410, '500 - 90 s transcurridos');
 assert.equal(revived.store.running(), true);
 time.advance(5_000);
 assert.equal(revived.store.snapshot().remaining_seconds, 405, 'la nueva ancla monotona sigue contando');
});

test('11 — recovery de un running con el reloj agotado pasa a awaiting_result', t => {
 const time = clock();
 const {space, store} = setup({label: 'expired', time});
 t.after(() => space.cleanup());
 store.assign(normalized(42, 600));
 run(store, 'set_running', {running: true});
 time.advance(700_000);
 const revived = revive(space, time);
 const snapshot = revived.store.snapshot();
 assert.equal(snapshot.status, 'awaiting_result');
 assert.equal(snapshot.remaining_seconds, 0);
 assert.equal(revived.store.running(), false, 'no se restaura como running');
 assert.equal(run(revived.store, 'set_running', {running: true}).code, 'awaiting_result');
});

test('12/13/14/15 — session_id, revision, scoring y resultado sobreviven', t => {
 const time = clock();
 const {space, store} = setup({label: 'survive', time});
 t.after(() => space.cleanup());
 const created = store.assign(normalized(42, 600)).state;
 run(store, 'score_delta', {fighter: 'a', field: 'points', delta: 2});
 run(store, 'score_delta', {fighter: 'b', field: 'advantages', delta: 1});
 run(store, 'score_delta', {fighter: 'a', field: 'penalties', delta: 1});
 run(store, 'set_running', {running: true});
 time.advance(60_000);
 run(store, 'finish', {winner_team_id: 102, method: 'submission'});
 const before = store.snapshot();
 const revived = revive(space, time);
 const after = revived.store.snapshot();
 assert.equal(after.session_id, created.session_id, '12 session_id');
 assert.equal(after.session_id, before.session_id);
 assert.equal(after.revision, before.revision, '13 revision');
 assert.equal(after.revision, 6);
 assert.ok(after.revision > 1, 'no se reinicia la revision');
 assert.equal(after.fighter_a.points, 2);
 assert.deepEqual({points: after.fighter_a.points, advantages: after.fighter_b.advantages, penalties: after.fighter_a.penalties},
  {points: 2, advantages: 1, penalties: 1}, '14 scoring');
 assert.equal(after.winner_team_id, 102, '15 winner');
 assert.equal(after.method, 'submission', '15 method');
});

test('16/17 — el replay de un command_id tras el reinicio no reaplica nada', t => {
 const time = clock();
 const {space, store} = setup({label: 'replay', time});
 t.after(() => space.cleanup());
 const created = store.assign(normalized()).state;
 const applied = command(created, 'score_delta', {fighter: 'a', field: 'points', delta: 2});
 const original = store.apply(applied);
 const revived = revive(space, time);
 const replay = revived.store.apply(applied);
 assert.deepEqual(replay, {ok: true, command_id: applied.command_id, revision: original.revision, changed: false});
 const snapshot = revived.store.snapshot();
 assert.equal(snapshot.fighter_a.points, 2, '17 el scoring no se duplica');
 assert.equal(snapshot.revision, original.revision, '17 la revision no se mueve');
});

test('extra — el assignment repetido sigue siendo 200 y otro match sigue 409 tras el reinicio', t => {
 const time = clock();
 const {space, store} = setup({label: 'assign-replay', time});
 t.after(() => space.cleanup());
 store.assign(normalized(42, 600));
 const revived = revive(space, time);
 assert.equal(revived.store.assign(normalized(42, 600)).status, 200, 'mismo payload: replay idempotente');
 assert.equal(revived.store.assign(normalized(43, 600)).status, 409, 'otro combate: el tatami sigue ocupado');
});

test('extra — el historial persistido queda acotado a 256 entradas', t => {
 const {space, store} = setup({label: 'bounded'});
 t.after(() => space.cleanup());
 store.assign(normalized());
 for (let index = 0; index < 300; index += 1) {
  const ack = run(store, 'score_delta', {fighter: 'a', field: 'penalties', delta: 1});
  assert.equal(ack.ok, true);
 }
 const stored = space.read();
 assert.equal(stored.command_history.length, 256);
 assert.equal(stored.state.revision, 301);
 const revived = revive(space);
 assert.equal(revived.store.document().command_history.length, 256);
});

// --- fail-closed ---------------------------------------------------------
test('18 — JSON corrupto: load falla y el fichero corrupto no se toca', t => {
 const {space, files, store} = setup({label: 'corrupt'});
 t.after(() => space.cleanup());
 store.assign(normalized());
 fs.writeFileSync(space.file, '{esto no es json', {mode: 0o600});
 const corrupted = space.raw();
 assert.throws(() => files.load(), StateFileError);
 assert.equal(space.raw(), corrupted, 'nunca se sobrescribe un fichero corrupto');
 assert.throws(() => {
  const target = createStore({persist: document => files.save(document)});
  const loaded = files.load();
  target.restore(loaded);
 }, StateFileError, 'el arranque no puede continuar en silencio');
 assert.equal(space.raw(), corrupted);
});

test('19 — schema_version desconocida: fail-closed sin tocar el fichero', t => {
 const {space, store} = setup({label: 'schema'});
 t.after(() => space.cleanup());
 store.assign(normalized());
 const stored = space.read();
 stored.schema_version = 2;
 fs.writeFileSync(space.file, JSON.stringify(stored), {mode: 0o600});
 const before = space.raw();
 const files = createStateFile({file: space.file});
 assert.throws(() => createStore().restore(files.load()), error => error instanceof InvalidStateError
  && /unsupported schema_version/.test(error.message));
 assert.throws(() => {
  const target = createStore({persist: document => files.save(document)});
  target.restore(files.load());
 }, InvalidStateError, 'el arranque no puede seguir con un esquema que no entiende');
 assert.equal(space.raw(), before, 'el fichero con esquema desconocido no se toca');
});

test('20 — estructura invalida: fail-closed en todas sus formas', t => {
 const {space, store} = setup({label: 'structure'});
 t.after(() => space.cleanup());
 store.assign(normalized(42, 600));
 run(store, 'set_running', {running: true});
 const base = space.read();
 const variants = {
  'clave de mas en el documento': document => {document.extra = true;},
  'clave de menos en el estado': document => {delete document.state.match_id;},
  'status desconocido': document => {document.state.status = 'invented';},
  'finished sin ganador': document => {document.state.status = 'finished'; document.state.winner_team_id = null;},
  'finished con metodo invalido': document => {
   document.state.status = 'finished'; document.state.winner_team_id = 101; document.state.method = 'sumo';
  },
  'ready con tiempo parcial': document => {document.state.status = 'ready';},
  'awaiting_result con tiempo': document => {document.state.status = 'awaiting_result';},
  'wall_anchor en una pausa': document => {document.state.status = 'paused';},
  'revision cero': document => {document.state.revision = 0;},
  'remaining fuera de rango': document => {document.state.remaining_seconds = document.state.duration_seconds + 1;},
  'luchadores repetidos': document => {document.state.fighter_b.team_id = document.state.fighter_a.team_id;},
  'scoring negativo': document => {document.state.fighter_a.points = -1;},
  'historial con un rechazo': document => {document.command_history = [{command_id: 'x', ack: {ok: false, command_id: 'x', revision: 1, changed: false}}];},
  'historial con ack cambiado': document => {document.command_history = [{command_id: 'x', ack: {ok: true, command_id: 'x', revision: 1, changed: true}}];},
  'historial duplicado': document => {document.command_history = [
   {command_id: 'x', ack: {ok: true, command_id: 'x', revision: 1, changed: false}},
   {command_id: 'x', ack: {ok: true, command_id: 'x', revision: 1, changed: false}}];},
  'historial con revision futura': document => {document.command_history = [{command_id: 'y', ack: {ok: true, command_id: 'y', revision: 99, changed: false}}];},
  'tatami vacio con historial': document => {document.state = null; document.command_history = [{command_id: 'z', ack: {ok: true, command_id: 'z', revision: 1, changed: false}}];},
  'saved_at no textual': document => {document.saved_at = 5;},
  'clock incompleto': document => {document.clock = {};},
 };
 for (const [label, mutate] of Object.entries(variants)) {
  const document = JSON.parse(JSON.stringify(base));
  mutate(document);
  assert.throws(() => createStore().restore(document), InvalidStateError, label);
 }
 assert.equal(JSON.stringify(space.read()), JSON.stringify(base), 'el fichero sigue intacto');
});

test('21 — fichero inexistente: estado vacio sin inventar nada', t => {
 const {space, files} = setup({label: 'missing'});
 t.after(() => space.cleanup());
 assert.equal(files.load(), undefined);
 assert.deepEqual(space.entries(), [], 'no se crea fichero antes de la primera mutacion');
 const revived = revive(space);
 assert.equal(revived.snapshot, null);
 assert.equal(revived.store.snapshot(), null);
 assert.equal(revived.store.running(), false);
 assert.equal(revived.store.assign(normalized()).status, 201, 'un tatami virgen acepta su primer combate');
 assert.deepEqual(space.entries(), ['state.json']);
});

test('22 — el fichero de estado queda en 0600', t => {
 const {space, store} = setup({label: 'mode'});
 t.after(() => space.cleanup());
 store.assign(normalized());
 assert.equal(fs.statSync(space.file).mode & 0o777, 0o600);
 run(store, 'score_delta', {fighter: 'a', field: 'points', delta: 1});
 assert.equal(fs.statSync(space.file).mode & 0o777, 0o600);
});

test('23 — la escritura es atomica: sin temporales y sin fichero parcial', t => {
 const {space, store} = setup({label: 'atomic'});
 t.after(() => space.cleanup());
 store.assign(normalized());
 for (let index = 0; index < 5; index += 1) run(store, 'score_delta', {fighter: 'a', field: 'points', delta: 1});
 assert.deepEqual(space.entries(), ['state.json'], 'no quedan ficheros temporales');
 assert.equal(space.read().state.fighter_a.points, 5);
 const broken = Object.create(fs);
 broken.renameSync = () => {throw new Error('simulated crash before rename');};
 const files = createStateFile({file: space.file, fs: broken});
 const previous = space.raw();
 assert.throws(() => files.save(store.document()), StateFileError);
 assert.equal(space.raw(), previous, 'el rename fallido deja el fichero anterior intacto');
 assert.deepEqual(space.entries(), ['state.json'], 'el temporal se limpia');
});

test('24 — un fallo de persistencia no devuelve exito y revierte el cambio', t => {
 const {space} = setup({label: 'failure'});
 t.after(() => space.cleanup());
 let failing = false;
 const files = createStateFile({file: space.file});
 const guarded = createStore({persist: document => {
  if (failing) throw new Error('disk full');
  files.save(document);
 }});
 assert.equal(guarded.assign(normalized()).status, 201);
 const before = guarded.snapshot();
 failing = true;
 const refused = run(guarded, 'score_delta', {fighter: 'a', field: 'points', delta: 2});
 assert.equal(refused.ok, false);
 assert.equal(refused.code, 'persist_failed');
 assert.equal(refused.revision, before.revision, 'la revision vuelve a la anterior');
 assert.deepEqual(guarded.snapshot(), before, 'la memoria se revierte');
 assert.equal(space.read().state.fighter_a.points, 0, 'el disco tampoco se movio');
 assert.equal(run(guarded, 'finish', {winner_team_id: 101, method: 'points'}).code, 'persist_failed');
 assert.equal(guarded.snapshot().status, 'ready');
 const empty = createStore({persist: () => {throw new Error('disk full');}});
 assert.equal(empty.assign(normalized()).status, 503, 'sin persistencia no hay assignment aceptado');
 assert.equal(empty.snapshot(), null, 'el tatami no queda ocupado');
 assert.equal(empty.persistenceEnabled(), true);
});

// --- alcance -------------------------------------------------------------
test('25 — sin descriptor de persistencia nada toca el disco (standalone intacto)', t => {
 const space = workspace('memory');
 t.after(() => space.cleanup());
 const store = createStore();
 assert.equal(store.persistenceEnabled(), false);
 const created = store.assign(normalized());
 assert.equal(created.status, 201);
 assert.equal(run(store, 'score_delta', {fighter: 'a', field: 'points', delta: 2}).ok, true);
 assert.equal(store.snapshot().fighter_a.points, 2);
 assert.deepEqual(space.entries(), [], 'ningun fichero');
 const launcher = fs.readFileSync(path.join(ADAPTER, 'launcher.js'), 'utf8');
 assert.match(launcher, /require\(path\.join\(legacyRoot, 'app\.js'\)\)/, 'el modo standalone sigue arrancando la app legacy');
});

test('26 — sin SCOREBOARD_STATE_FILE el servidor integrado arranca en memoria', t => {
 const space = workspace('envless');
 try {
  const script = [
   "const {createServer} = require(process.env.P24B_INTEGRATED);",
   "const {server} = createServer(process.env.P24B_LEGACY);",
   "server.listen(0, async () => {",
   " const response = await fetch('http://127.0.0.1:' + server.address().port + '/internal/tatamis/1/state',",
   "  {headers: {'x-internal-token': process.env.SCOREBOARD_INTERNAL_TOKEN}});",
   " console.log('RESULT ' + JSON.stringify(await response.json()));",
   " server.close();",
   "});",
  ].join('\n');
  const output = childProcess.execFileSync(process.execPath, ['-e', script], {encoding: 'utf8', timeout: 30_000, env: {
   ...process.env, SCOREBOARD_MODE: 'integrated', SCOREBOARD_INTERNAL_TOKEN: 'synthetic-internal',
   SCOREBOARD_CONTROL_TOKEN: 'synthetic-control', SCOREBOARD_STATE_FILE: '',
   P24B_INTEGRATED: path.join(ADAPTER, 'integrated.js'), P24B_LEGACY: LEGACY_ROOT,
   NODE_PATH: process.env.NODE_PATH || '/home/ubuntu/.cache/scoreboard-p23b/node_modules',
  }});
  const line = output.split('\n').find(entry => entry.startsWith('RESULT '));
  assert.ok(line, 'el servidor debe responder: ' + output);
  assert.deepEqual(JSON.parse(line.slice('RESULT '.length)), {state: null});
  assert.deepEqual(space.entries(), [], 'sin SCOREBOARD_STATE_FILE no se escribe nada');
 } finally {
  space.cleanup();
 }
});

test('27 — el documento no lleva tokens, cookies ni secretos', t => {
 const {space, store} = setup({label: 'secrets'});
 t.after(() => space.cleanup());
 store.assign(normalized());
 run(store, 'set_running', {running: true});
 const raw = space.raw();
 assert.deepEqual(Object.keys(space.read()), ['schema_version', 'saved_at', 'clock', 'state', 'command_history']);
 for (const forbidden of ['token', 'secret', 'cookie', 'socket', 'password', 'Authorization', 'bracket', 'http']) {
  assert.equal(raw.toLowerCase().includes(forbidden.toLowerCase()), false, 'no aparece: ' + forbidden);
 }
});

test('28/29 — el adapter no tiene cliente HTTP saliente ni nocion de Bracket', () => {
 for (const name of ['state.js', 'state-store.js']) {
  const source = fs.readFileSync(path.join(ADAPTER, name), 'utf8');
  for (const forbidden of ["require('node:http')", "require('node:https')", 'axios', 'fetch(', 'XMLHttpRequest', 'bracket']) {
   assert.equal(source.includes(forbidden), false, name + ' no debe contener ' + forbidden);
  }
 }
 const integrated = fs.readFileSync(path.join(ADAPTER, 'integrated.js'), 'utf8');
 for (const forbidden of ['http.request', 'https.request', 'axios', 'fetch(', 'bracket']) {
  assert.equal(integrated.includes(forbidden), false, 'integrated.js no debe contener ' + forbidden);
 }
});

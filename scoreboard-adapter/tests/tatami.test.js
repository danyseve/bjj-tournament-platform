'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const INTERNAL = 'synthetic-internal-token';
const CONTROL = 'synthetic-control-token';
process.env.SCOREBOARD_INTERNAL_TOKEN = INTERNAL;
process.env.SCOREBOARD_CONTROL_TOKEN = CONTROL;
const legacyRoot = path.resolve(__dirname, '../../services/scoreboard');
const fixture = () => ({tournament_id:7,match_id:40,tatami_id:1,fighter_a:{stage_item_input_id:1,team_id:101,name:'Ana',club:null},fighter_b:{stage_item_input_id:2,team_id:102,name:'Bea',club:null},category:{stage_item_id:9,name:'Adult'},duration_seconds:300});
// Monotonic test clock: clock tests never sleep.
const clock = {value: 0};
const store = () => require('../state').createStore({now: () => clock.value});
let sequence = 0;
function assigned(duration = 300) {
 clock.value = 0;
 const s = store();
 assert.equal(s.assign({...fixture(), duration_seconds: duration}).status, 201);
 return s;
}
const base = state => ({session_id: state.session_id, command_id: 'synthetic-command-' + (++sequence),
 expected_revision: state.revision, tatami_id: state.tatami_id, match_id: state.match_id});
const score = (s, fighter, field, delta) => s.apply({...base(s.snapshot()), operation: 'score_delta', fighter, field, delta});
const running = (s, value) => s.apply({...base(s.snapshot()), operation: 'set_running', running: value});

test('01 score_delta adiciona puntos al luchador A y sube revision', () => {
 const s = assigned(), before = s.snapshot(), r = score(s, 'a', 'points', 2);
 assert.equal(r.ok, true); assert.equal(r.changed, true); assert.equal(r.revision, before.revision + 1);
 const after = s.snapshot();
 assert.equal(after.fighter_a.points, 2); assert.equal(after.fighter_b.points, 0); assert.equal(after.revision, before.revision + 1);
 assert.equal(after.status, 'ready'); assert.equal(after.remaining_seconds, 300);
});
test('02 decremento explicito resta los puntos indicados', () => {
 const s = assigned(); score(s, 'a', 'points', 4); const r = score(s, 'a', 'points', -2);
 assert.equal(r.ok, true); assert.equal(s.snapshot().fighter_a.points, 2);
});
test('03 el resultado nunca queda negativo y el rechazo no muta el estado', () => {
 const s = assigned(); const before = s.snapshot(), r = score(s, 'b', 'points', -1);
 assert.equal(r.ok, false); assert.equal(r.code, 'invalid_operation'); assert.equal(r.revision, before.revision);
 assert.deepEqual(s.snapshot(), before);
});
test('04 ventajas se acumulan por luchador', () => {
 const s = assigned(); assert.equal(score(s, 'b', 'advantages', 1).ok, true); assert.equal(score(s, 'b', 'advantages', 1).ok, true);
 assert.equal(score(s, 'a', 'advantages', 1).ok, true); const a = s.snapshot();
 assert.equal(a.fighter_b.advantages, 2); assert.equal(a.fighter_a.advantages, 1);
});
test('05 penalizaciones se acumulan y se pueden corregir', () => {
 const s = assigned(); score(s, 'a', 'penalties', 1); score(s, 'a', 'penalties', 1); const r = score(s, 'a', 'penalties', -1);
 assert.equal(r.ok, true); assert.equal(s.snapshot().fighter_a.penalties, 1);
});
test('06 sesion incorrecta es rechazada sin mutar', () => {
 const s = assigned(); const before = s.snapshot();
 const r = s.apply({...base(before), session_id: 'synthetic-session-other', operation: 'score_delta', fighter: 'a', field: 'points', delta: 2});
 assert.equal(r.ok, false); assert.equal(r.code, 'wrong_session'); assert.deepEqual(s.snapshot(), before);
});
test('07 combate incorrecto es rechazado sin mutar', () => {
 const s = assigned(); const before = s.snapshot();
 const r = s.apply({...base(before), match_id: before.match_id + 1, operation: 'score_delta', fighter: 'a', field: 'points', delta: 2});
 assert.equal(r.ok, false); assert.equal(r.code, 'wrong_match'); assert.deepEqual(s.snapshot(), before);
});
test('08 revision esperada no coincidente es rechazada devolviendo la actual', () => {
 const s = assigned(); const before = s.snapshot();
 for (const expected of [before.revision - 1, before.revision + 1, 0]) {
  const r = s.apply({...base(before), expected_revision: expected, operation: 'score_delta', fighter: 'a', field: 'points', delta: 2});
  assert.equal(r.ok, false); assert.equal(r.code, 'stale_revision'); assert.equal(r.revision, before.revision);
 }
 assert.deepEqual(s.snapshot(), before);
});
test('09 command_id duplicado no reaplica la operacion', () => {
 const s = assigned(); const command = {...base(s.snapshot()), operation: 'score_delta', fighter: 'a', field: 'points', delta: 2};
 const first = s.apply(command), second = s.apply({...command});
 assert.equal(first.ok, true); assert.equal(second.ok, true);
 assert.equal(second.revision, first.revision); assert.equal(second.changed, false);
 assert.equal(s.snapshot().fighter_a.points, 2); assert.equal(s.snapshot().revision, first.revision);
});
test('10 replay tardio tras otros comandos sigue devolviendo el ack original y no duplica puntos', () => {
 const s = assigned(); const command = {...base(s.snapshot()), operation: 'score_delta', fighter: 'a', field: 'points', delta: 2};
 const first = s.apply(command); score(s, 'b', 'points', 3); const points = s.snapshot().fighter_a.points, revision = s.snapshot().revision;
 const replay = s.apply({...command});
 assert.equal(replay.ok, true); assert.equal(replay.revision, first.revision); assert.equal(replay.changed, false);
 assert.equal(s.snapshot().fighter_a.points, points); assert.equal(s.snapshot().revision, revision);
});
test('11 set_running true arranca el reloj de forma explicita', () => {
 const s = assigned(); const r = running(s, true);
 assert.equal(r.ok, true); assert.equal(r.changed, true); assert.equal(s.snapshot().status, 'running');
});
test('12 set_running true repetido es idempotente y no sube revision', () => {
 const s = assigned(); const first = running(s, true), second = running(s, true);
 assert.equal(second.ok, true); assert.equal(second.changed, false); assert.equal(second.revision, first.revision);
 assert.equal(s.snapshot().status, 'running');
});
test('13 pausa congela el tiempo restante calculado', () => {
 const s = assigned(); running(s, true); clock.value += 5000;
 const paused = running(s, false); assert.equal(paused.ok, true); assert.equal(s.snapshot().status, 'paused'); assert.equal(s.snapshot().remaining_seconds, 295);
 clock.value += 60000; assert.equal(s.snapshot().remaining_seconds, 295, 'paused clock must not advance');
});
test('14 reanudar continua desde el tiempo congelado', () => {
 const s = assigned(); running(s, true); clock.value += 5000; running(s, false); clock.value += 60000; running(s, true);
 clock.value += 4000; assert.equal(s.snapshot().remaining_seconds, 291); assert.equal(s.snapshot().status, 'running');
});
test('15 el reloj del servidor disminuye con el tiempo monotono', () => {
 const s = assigned(); running(s, true);
 assert.equal(s.snapshot().remaining_seconds, 300);
 clock.value += 1000; assert.equal(s.snapshot().remaining_seconds, 299);
 clock.value += 99000; assert.equal(s.snapshot().remaining_seconds, 200);
});
test('16 el reloj nunca es negativo', () => {
 const s = assigned(); running(s, true); clock.value += 10 * 60 * 1000;
 assert.equal(s.snapshot().remaining_seconds, 0);
});
test('17 al llegar a cero el reloj deja de correr y el estado no es running', () => {
 const s = assigned(); running(s, true); clock.value += 300000;
 const state = s.snapshot();
 assert.equal(state.remaining_seconds, 0); assert.equal(state.status, 'finished'); assert.notEqual(state.status, 'running');
 clock.value += 60000; assert.equal(s.snapshot().remaining_seconds, 0); assert.equal(s.snapshot().status, 'finished');
});
test('18 reset detiene el reloj, restaura duracion y scoring conservando sesion y participantes', () => {
 const s = assigned(); const session = s.snapshot().session_id;
 score(s, 'a', 'points', 4); score(s, 'b', 'advantages', 2); score(s, 'b', 'penalties', 1); running(s, true); clock.value += 5000;
 const r = s.apply({...base(s.snapshot()), operation: 'reset'});
 assert.equal(r.ok, true);
 const state = s.snapshot();
 assert.equal(state.session_id, session); assert.equal(state.status, 'ready'); assert.equal(state.remaining_seconds, 300);
 assert.equal(state.fighter_a.points, 0); assert.equal(state.fighter_b.advantages, 0); assert.equal(state.fighter_b.penalties, 0);
 assert.equal(state.fighter_a.name, 'Ana'); assert.equal(state.fighter_b.name, 'Bea'); assert.equal(state.match_id, 40);
 clock.value += 5000; assert.equal(s.snapshot().remaining_seconds, 300, 'reset leaves the clock stopped');
});
test('19 el registro de comandos sobrevive al reset: un replay no resucita puntos', () => {
 const s = assigned(); const command = {...base(s.snapshot()), operation: 'score_delta', fighter: 'a', field: 'points', delta: 2};
 const first = s.apply(command); assert.equal(s.snapshot().fighter_a.points, 2);
 const reset = s.apply({...base(s.snapshot()), operation: 'reset'});
 assert.equal(reset.ok, true); assert.equal(s.snapshot().fighter_a.points, 0);
 const replay = s.apply({...command});
 assert.equal(replay.ok, true); assert.equal(replay.changed, false); assert.equal(replay.revision, first.revision);
 assert.equal(s.snapshot().fighter_a.points, 0, 'un replay tras reset no puede resucitar puntos');
});
test('20 payloads invalidos, operaciones y campos desconocidos son rechazados', () => {
 const s = assigned(), before = s.snapshot();
 const cases = [
  [null, 'invalid_command'], ['x', 'invalid_command'], [[], 'invalid_command'],
  [{...base(before), operation: 'finish'}, 'invalid_operation'],
  [{...base(before), operation: 'score_delta', fighter: 'a', field: 'points'}, 'invalid_command'],
  [{...base(before), operation: 'score_delta', fighter: 'a', field: 'points', delta: 2, extra: 1}, 'invalid_command'],
  [{...base(before), operation: 'reset', extra: true}, 'invalid_command'],
  [{...base(before), operation: 'score_delta', fighter: 'c', field: 'points', delta: 2}, 'invalid_operation'],
  [{...base(before), operation: 'score_delta', fighter: 'a', field: 'time', delta: 2}, 'invalid_operation'],
  [{...base(before), operation: 'score_delta', fighter: 'a', field: 'points', delta: 0}, 'invalid_operation'],
  [{...base(before), operation: 'score_delta', fighter: 'a', field: 'points', delta: 1.5}, 'invalid_operation'],
  [{...base(before), operation: 'score_delta', fighter: 'a', field: 'points', delta: 101}, 'invalid_operation'],
  [{...base(before), operation: 'set_running', running: 'yes'}, 'invalid_operation'],
  [{...base(before), operation: 'reset', command_id: ''}, 'invalid_command'],
  [{...base(before), operation: 'reset', expected_revision: -1}, 'invalid_command'],
  [{...base(before), operation: 'reset', tatami_id: 2}, 'invalid_command'],
 ];
 for (const [command, code] of cases) {
  const r = s.apply(command);
  assert.equal(r.ok, false, JSON.stringify(command)); assert.equal(r.code, code, JSON.stringify(command));
 }
 assert.deepEqual(s.snapshot(), before);
});
test('21 acumulaciones absurdas y arranque tras finalizar son rechazados', () => {
 const s = assigned();
 for (let i = 0; i < 10; i += 1) assert.equal(score(s, 'a', 'points', 100).ok, true);
 assert.equal(s.snapshot().fighter_a.points, 1000);
 const overflow = score(s, 'a', 'points', 1);
 assert.equal(overflow.ok, false); assert.equal(overflow.code, 'invalid_operation'); assert.equal(s.snapshot().fighter_a.points, 1000);
 running(s, true); clock.value += 300000; assert.equal(s.snapshot().status, 'finished');
 const resume = running(s, true);
 assert.equal(resume.ok, false); assert.equal(resume.code, 'invalid_operation'); assert.equal(s.snapshot().status, 'finished');
});
async function server(t) {
 const a = require('../integrated').createServer(legacyRoot);
 await new Promise(r => a.server.listen(0, '127.0.0.1', r));
 t.after(() => new Promise(r => a.io.close(r)));
 return {...a, url: 'http://127.0.0.1:' + a.server.address().port};
}
async function connect(url, cookie) {
 const headers = cookie === undefined ? {} : {cookie};
 const opening = await (await fetch(url + '/socket.io/?EIO=4&transport=polling', {headers})).text();
 const sid = JSON.parse(opening.slice(1)).sid, endpoint = url + '/socket.io/?EIO=4&transport=polling&sid=' + sid;
 await fetch(endpoint, {method: 'POST', body: '40', headers});
 return {
  poll: async () => (await (await fetch(endpoint, {headers, signal: AbortSignal.timeout(1000)})).text()).split('\x1e'),
  // Socket.IO v4 carries the ack id outside the event array: 42<id>[...]
  send: (event, data, ack) => fetch(endpoint, {method: 'POST', headers, body: '42' + (ack === undefined ? '' : String(ack)) + JSON.stringify([event, data])}),
  close: () => fetch(endpoint, {method: 'POST', headers, body: '41'}),
 };
}
const events = packets => packets.filter(p => p.startsWith('42')).map(p => JSON.parse(p.slice(2)));
const acks = packets => new Map(packets.map(p => /^43(\d+)(.*)$/.exec(p)).filter(Boolean).map(m => [Number(m[1]), JSON.parse(m[2])[0]]));
const cookie = value => 'scoreboard_control=' + value;
const assign = async (url, payload = fixture()) => {
 const res = await fetch(url + '/internal/tatamis/1/assignment', {method: 'PUT', headers: {'content-type': 'application/json', 'x-internal-token': INTERNAL}, body: JSON.stringify(payload)});
 assert.equal(res.status, 201); return (await res.json()).state;
};
test('22 sin credencial de control tatami:update es rechazado y el estado no cambia', async t => {
 const {url} = await server(t), state = await assign(url), a = await connect(url);
 await a.poll(); // drain the connection snapshot
 const command = {...base(state), operation: 'score_delta', fighter: 'a', field: 'points', delta: 2};
 await a.send('tatami:update', command, 1);
 const packets = await a.poll();
 assert.deepEqual(acks(packets).get(1), {ok: false, code: 'unauthorized', revision: 1});
 assert.deepEqual(events(packets), [], 'no state is broadcast for a refused command');
 assert.deepEqual((await (await fetch(url + '/internal/tatamis/1/state', {headers: {'x-internal-token': INTERNAL}})).json()).state, state);
 await a.close();
});
test('23 credencial de control incorrecta o vacia tambien es rechazada', async t => {
 const {url} = await server(t), state = await assign(url);
 for (const value of ['synthetic-control-tokeX', '', 'short']) {
  const a = await connect(url, cookie(value));
  await a.send('tatami:update', {...base(state), operation: 'reset'}, 1);
  assert.deepEqual(acks(await a.poll()).get(1), {ok: false, code: 'unauthorized', revision: 1}, value);
  await a.close();
 }
});
test('24 credencial de control correcta aplica el comando y emite snapshot a todos los clientes', async t => {
 const {url} = await server(t), state = await assign(url);
 const controller = await connect(url, cookie(CONTROL)), display = await connect(url);
 assert.deepEqual(events(await controller.poll()), [['tatami:state', state]]);
 assert.deepEqual(events(await display.poll()), [['tatami:state', state]]);
 const command = {...base(state), operation: 'score_delta', fighter: 'a', field: 'points', delta: 2};
 await controller.send('tatami:update', command, 7);
 const ack = acks(await controller.poll()).get(7);
 assert.deepEqual(ack, {ok: true, command_id: command.command_id, revision: 2});
 const broadcast = events(await display.poll());
 assert.equal(broadcast.length, 1); assert.equal(broadcast[0][0], 'tatami:state');
 assert.equal(broadcast[0][1].fighter_a.points, 2); assert.equal(broadcast[0][1].revision, 2);
 await controller.send('tatami:update', {...command}, 8);
 assert.deepEqual(acks(await controller.poll()).get(8), ack);
 // Un replay idempotente no vuelve a emitir estado a nadie.
 await assert.rejects(controller.poll(), error => error.name === 'TimeoutError');
 await assert.rejects(display.poll(), error => error.name === 'TimeoutError');
 await controller.close(); await display.close();
});
test('25 el reloj corre en el servidor y se emite a los clientes conectados', async t => {
 const {url} = await server(t), state = await assign(url, {...fixture(), duration_seconds: 3});
 const controller = await connect(url, cookie(CONTROL)), display = await connect(url);
 await controller.poll(); await display.poll();
 const start = {...base(state), operation: 'set_running', running: true};
 await controller.send('tatami:update', start, 3);
 const ack = acks(await controller.poll()).get(3);
 assert.deepEqual(ack, {ok: true, command_id: start.command_id, revision: 2});
 const ticks = events(await display.poll());
 assert.equal(ticks.length, 1); assert.equal(ticks[0][1].status, 'running');
 await controller.close(); await display.close();
});
test('26 el marcador canonico no escribe resultados ni llama a Bracket', () => {
 // Guard test: no outbound call and no result endpoint exist in the scoreboard.
 const source = require('node:fs').readFileSync(path.join(__dirname, '../integrated.js'), 'utf8');
 for (const outbound of ['fetch(', 'axios', 'http.request', 'https.request', 'undici', 'got(']) {
  assert.ok(source.includes(outbound) === false, 'sin llamada saliente: ' + outbound);
 }
 assert.ok(/['"]\/result/.test(source) === false, 'no se expone ningun endpoint de resultados');
 assert.ok(/\bwinner_team_id\s*=/.test(source) === false, 'el marcador nunca asigna ganador');
});

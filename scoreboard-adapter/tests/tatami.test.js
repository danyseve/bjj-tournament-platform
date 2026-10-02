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
test('17 al llegar a cero el reloj se detiene y el combate espera resultado', () => {
 const s = assigned(); running(s, true); clock.value += 300000;
 const state = s.snapshot();
 assert.equal(state.remaining_seconds, 0); assert.equal(state.status, 'awaiting_result'); assert.notEqual(state.status, 'running');
 assert.equal(state.winner_team_id, null); assert.equal(state.method, null, 'el tiempo agotado no decide ganador');
 assert.equal(s.running(), false, 'el reloj autoritativo queda parado');
 clock.value += 60000; assert.equal(s.snapshot().remaining_seconds, 0); assert.equal(s.snapshot().status, 'awaiting_result');
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
  [{...base(before), operation: 'finish'}, 'invalid_command'],
  [{...base(before), operation: 'finish', winner_team_id: 101}, 'invalid_command'],
  [{...base(before), operation: 'finish', method: 'points', extra: 1}, 'invalid_command'],
  [{...base(before), operation: 'finish', winner_team_id: '101', method: 'points'}, 'invalid_winner'],
  [{...base(before), operation: 'finish', winner_team_id: 999, method: 'points'}, 'invalid_winner'],
  [{...base(before), operation: 'finish', winner_team_id: 101, method: 'ko'}, 'invalid_method'],
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
test('21 acumulaciones absurdas y arranque con el tiempo agotado son rechazados', () => {
 const s = assigned();
 for (let i = 0; i < 10; i += 1) assert.equal(score(s, 'a', 'points', 100).ok, true);
 assert.equal(s.snapshot().fighter_a.points, 1000);
 const overflow = score(s, 'a', 'points', 1);
 assert.equal(overflow.ok, false); assert.equal(overflow.code, 'invalid_operation'); assert.equal(s.snapshot().fighter_a.points, 1000);
 running(s, true); clock.value += 300000; assert.equal(s.snapshot().status, 'awaiting_result');
 const resume = running(s, true);
 assert.equal(resume.ok, false); assert.equal(resume.code, 'awaiting_result'); assert.equal(s.snapshot().status, 'awaiting_result');
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
 // The winner is recorded in memory only (state.js); no adapter file may talk to
 // Bracket or to any other service.
 for (const file of ['../integrated.js', '../state.js', '../integrated-ui.js', '../launcher.js']) {
  const source = require('node:fs').readFileSync(path.join(__dirname, file), 'utf8');
  for (const outbound of ['fetch(', 'axios', 'http.request', 'https.request', 'undici', 'got(']) {
   assert.ok(source.includes(outbound) === false, file + ' sin llamada saliente: ' + outbound);
  }
  assert.ok(/['"]\/result/.test(source) === false, file + ' no expone ningun endpoint de resultados');
  // Sin destino de red no puede haber escritura en Bracket: ni URL, ni ruta de
  // su API, ni cliente HTTP (lo anterior). Las menciones en comentarios no son
  // alcance: aqui se comprueba que no exista ningun destino.
  assert.ok(/https?:\/\//.test(source) === false, file + ' sin URL de red');
  assert.ok(source.includes('/api/') === false, file + ' sin ruta de la API de Bracket');
 }
});

const finish = (s, winner, method) => s.apply({...base(s.snapshot()), operation: 'finish', winner_team_id: winner, method});
const finalState = (s, winner, method) => {const r = finish(s, winner, method); assert.equal(r.ok, true, JSON.stringify(r)); return s.snapshot();};

test('27 finish valido del luchador A congela el combate y sube revision una vez', () => {
 const s = assigned(); const session = s.snapshot().session_id;
 score(s, 'a', 'points', 4); score(s, 'a', 'advantages', 1); score(s, 'b', 'penalties', 2);
 const revision = s.snapshot().revision, r = finish(s, 101, 'submission');
 assert.equal(r.ok, true); assert.equal(r.changed, true); assert.equal(r.revision, revision + 1);
 const state = s.snapshot();
 assert.equal(state.status, 'finished'); assert.equal(state.winner_team_id, 101); assert.equal(state.method, 'submission');
 assert.equal(state.revision, revision + 1); assert.equal(state.session_id, session);
 assert.equal(state.revision, revision + 1, 'la revision sube exactamente una vez');
 assert.deepEqual([state.fighter_a.points, state.fighter_a.advantages, state.fighter_b.penalties], [4, 1, 2]);
});

test('28 finish valido del luchador B por decision', () => {
 const s = assigned(); const state = finalState(s, 102, 'decision');
 assert.equal(state.winner_team_id, 102); assert.equal(state.method, 'decision'); assert.equal(state.status, 'finished');
});

test('29 un ganador que no participa en el combate es rechazado sin mutar', () => {
 const s = assigned(); const before = s.snapshot();
 for (const winner of [1, 999, 0, -101, '101', null, 101.5, true]) {
  const r = finish(s, winner, 'points');
  assert.equal(r.ok, false, String(winner)); assert.equal(r.code, 'invalid_winner', String(winner));
 }
 assert.deepEqual(s.snapshot(), before);
});

test('30 el metodo de finalizacion debe pertenecer al enum explicito', () => {
 const s = assigned(); const before = s.snapshot();
 for (const method of ['SUB', 'submission ', 'ko', '', 7, null, 'other ', 'submision']) {
  const r = finish(s, 101, method);
  assert.equal(r.ok, false, String(method)); assert.equal(r.code, 'invalid_method', String(method));
 }
 assert.deepEqual(s.snapshot(), before);
 for (const method of require('../state').METHODS) {
  assert.equal(finalState(assigned(), 101, method).method, method, method);
 }
});

test('31 finish con revision obsoleta es rechazado devolviendo la actual', () => {
 const s = assigned(); score(s, 'a', 'points', 2); const before = s.snapshot();
 for (const expected of [before.revision - 1, before.revision + 1, 0]) {
  const r = s.apply({...base(before), expected_revision: expected, operation: 'finish', winner_team_id: 101, method: 'points'});
  assert.equal(r.ok, false); assert.equal(r.code, 'stale_revision'); assert.equal(r.revision, before.revision);
 }
 assert.deepEqual(s.snapshot(), before);
});

test('32 finish con sesion incorrecta es rechazado sin mutar', () => {
 const s = assigned(); const before = s.snapshot();
 const r = s.apply({...base(before), session_id: 'synthetic-session-other', operation: 'finish', winner_team_id: 101, method: 'points'});
 assert.equal(r.ok, false); assert.equal(r.code, 'wrong_session'); assert.deepEqual(s.snapshot(), before);
});

test('33 finish con combate incorrecto es rechazado sin mutar', () => {
 const s = assigned(); const before = s.snapshot();
 const r = s.apply({...base(before), match_id: before.match_id + 1, operation: 'finish', winner_team_id: 101, method: 'points'});
 assert.equal(r.ok, false); assert.equal(r.code, 'wrong_match'); assert.deepEqual(s.snapshot(), before);
});

test('34 finish congela el reloj en el valor actual', () => {
 const s = assigned(); running(s, true); clock.value += 5000;
 assert.equal(s.snapshot().remaining_seconds, 295);
 const state = finalState(s, 101, 'points');
 assert.equal(state.remaining_seconds, 295); assert.equal(state.status, 'finished');
 clock.value += 120000;
 assert.equal(s.snapshot().remaining_seconds, 295, 'el reloj de un combate finalizado no avanza');
 assert.equal(s.running(), false, 'el reloj autoritativo queda parado');
});

test('35 finish desde ready congela la duracion completa', () => {
 const s = assigned(); const state = finalState(s, 102, 'walkover');
 assert.equal(state.remaining_seconds, 300); assert.equal(state.method, 'walkover');
});

test('36 el replay del mismo finish no duplica ni sube revision', () => {
 const s = assigned();
 const command = {...base(s.snapshot()), operation: 'finish', winner_team_id: 101, method: 'points'};
 const first = s.apply(command); const frozen = s.snapshot();
 const replay = s.apply({...command});
 assert.equal(replay.ok, true); assert.equal(replay.changed, false); assert.equal(replay.revision, first.revision);
 assert.deepEqual(s.snapshot(), frozen);
});

test('37 un segundo finish distinto es rechazado y no altera el resultado congelado', () => {
 const s = assigned(); const frozen = finalState(s, 101, 'points');
 for (const [winner, method] of [[102, 'submission'], [101, 'decision']]) {
  const r = finish(s, winner, method);
  assert.equal(r.ok, false); assert.equal(r.code, 'already_finished'); assert.equal(r.revision, frozen.revision);
 }
 assert.deepEqual(s.snapshot(), frozen);
});

test('38 tras finalizar el scoring, el reloj y el reset son rechazados', () => {
 const s = assigned(); score(s, 'a', 'points', 2); const frozen = finalState(s, 101, 'submission');
 const rejected = [score(s, 'a', 'points', 2), score(s, 'b', 'advantages', 1), score(s, 'b', 'penalties', -1),
  running(s, true), running(s, false), s.apply({...base(frozen), operation: 'reset'})];
 for (const r of rejected) {assert.equal(r.ok, false, JSON.stringify(r)); assert.equal(r.code, 'already_finished');}
 assert.deepEqual(s.snapshot(), frozen);
});

test('39 el tiempo agotado deja el resultado abierto y admite finish', () => {
 const s = assigned(); running(s, true); clock.value += 300000;
 const expired = s.snapshot();
 assert.equal(expired.status, 'awaiting_result'); assert.equal(expired.winner_team_id, null); assert.equal(expired.method, null);
 const r = finish(s, 101, 'points');
 assert.equal(r.ok, true, JSON.stringify(r));
 const state = s.snapshot();
 assert.equal(state.status, 'finished'); assert.equal(state.winner_team_id, 101); assert.equal(state.method, 'points');
 assert.equal(state.remaining_seconds, 0, 'el resultado llega con el reloj ya agotado');
 assert.equal(state.revision, expired.revision + 1, 'la revision sube una sola vez');
});

test('40 el enum de metodos del cliente coincide con el del servidor', () => {
 const {METHODS} = require('../state');
 const source = require('node:fs').readFileSync(path.join(__dirname, '../integrated-ui.js'), 'utf8');
 const match = /const METHODS = (\[[^\]]*\]);/.exec(source);
 assert.ok(match !== null, 'el cliente declara el enum de metodos');
 assert.deepEqual(JSON.parse(match[1].replace(/'/g, '"')), METHODS);
});

test('41 finish por socket emite el snapshot final y el ticker no lo modifica', async t => {
 const {url} = await server(t), state = await assign(url);
 const controller = await connect(url, cookie(CONTROL)), display = await connect(url);
 await controller.poll(); await display.poll();
 await controller.send('tatami:update', {...base(state), operation: 'set_running', running: true}, 1);
 assert.equal(acks(await controller.poll()).get(1).ok, true);
 const command = {...base({...state, revision: state.revision + 1}), operation: 'finish', winner_team_id: 102, method: 'referee_stoppage'};
 await controller.send('tatami:update', command, 2);
 assert.deepEqual(acks(await controller.poll()).get(2), {ok: true, command_id: command.command_id, revision: state.revision + 2});
 const packets = await display.poll();
 const final = events(packets).map(payload => payload[1]).filter(snapshot => snapshot.status === 'finished').pop();
 assert.ok(final, 'el snapshot final llega a los clientes conectados');
 assert.equal(final.winner_team_id, 102); assert.equal(final.method, 'referee_stoppage');
 assert.equal(final.remaining_seconds, 300, 'el reloj se congela en el valor observable al finalizar');
 // El ticker ya no corre: ningún snapshot posterior.
 await assert.rejects(controller.poll(), error => error.name === 'TimeoutError');
 await assert.rejects(display.poll(), error => error.name === 'TimeoutError');
 const internal = (await (await fetch(url + '/internal/tatamis/1/state', {headers: {'x-internal-token': INTERNAL}})).json()).state;
 assert.deepEqual(internal, final, 'el estado interno es exactamente el snapshot emitido');
 await controller.close(); await display.close();
});

test('42 una UI que se reconecta tras finalizar recibe el resultado final congelado', async t => {
 const {url} = await server(t), state = await assign(url);
 const controller = await connect(url, cookie(CONTROL));
 await controller.poll();
 const command = {...base(state), operation: 'finish', winner_team_id: 101, method: 'other'};
 await controller.send('tatami:update', command, 1);
 await controller.poll();
 const later = await connect(url), snapshot = events(await later.poll()).find(([event]) => event === 'tatami:state')[1];
 assert.equal(snapshot.status, 'finished'); assert.equal(snapshot.winner_team_id, 101); assert.equal(snapshot.method, 'other');
 assert.equal(snapshot.revision, 2); assert.equal(snapshot.session_id, state.session_id);
 assert.equal(snapshot.remaining_seconds, 300); assert.equal(snapshot.fighter_a.points, 0);
 await controller.close(); await later.close();
});

const cleared = (s, state) => s.apply({...base(state === undefined ? s.snapshot() : state), operation: 'clear_match'});
const expiredStore = () => {const s = assigned(); running(s, true); clock.value += 300000; return s;};
const otherFixture = () => ({...fixture(), match_id: 41,
 fighter_a: {...fixture().fighter_a, stage_item_input_id: 3, team_id: 201, name: 'Otra Ana'},
 fighter_b: {...fixture().fighter_b, stage_item_input_id: 4, team_id: 202, name: 'Otra Bea'}});

test('43 el tiempo agotado abre awaiting_result sin cerrar el resultado ni tocar el scoring', () => {
 const s = assigned();
 score(s, 'a', 'points', 6); score(s, 'b', 'advantages', 2); running(s, true);
 const before = s.snapshot(); clock.value += 300000;
 const state = s.snapshot();
 assert.equal(state.status, 'awaiting_result'); assert.equal(state.remaining_seconds, 0);
 assert.equal(state.winner_team_id, null); assert.equal(state.method, null);
 assert.deepEqual([state.fighter_a.points, state.fighter_b.advantages], [6, 2], 'el scoring queda congelado y no se pierde');
 assert.equal(state.revision, before.revision, 'agotar el tiempo no es una mutacion de comando');
 assert.equal(s.running(), false, 'el reloj autoritativo queda parado');
});

test('44 con el tiempo agotado solo finish esta permitido', () => {
 const s = assigned(); score(s, 'a', 'points', 1); running(s, true); clock.value += 300000;
 const expired = s.snapshot();
 const rejected = [score(s, 'a', 'points', 2), score(s, 'b', 'penalties', 1), running(s, true), running(s, false),
  s.apply({...base(expired), operation: 'reset'})];
 for (const r of rejected) {assert.equal(r.ok, false, JSON.stringify(r)); assert.equal(r.code, 'awaiting_result');}
 assert.deepEqual(s.snapshot(), expired, 'ninguna mutacion toca un combate con el tiempo agotado');
});

test('45 finish resuelve awaiting_result conservando scoring y el reloj en cero', () => {
 const s = assigned(); score(s, 'a', 'points', 3); score(s, 'b', 'penalties', 1); running(s, true); clock.value += 300000;
 const expired = s.snapshot();
 const r = s.apply({...base(expired), operation: 'finish', winner_team_id: 102, method: 'decision'});
 assert.equal(r.ok, true); assert.equal(r.changed, true); assert.equal(r.revision, expired.revision + 1);
 assert.equal(r.state.status, 'finished');
 const state = s.snapshot();
 assert.equal(state.status, 'finished'); assert.equal(state.winner_team_id, 102); assert.equal(state.method, 'decision');
 assert.equal(state.remaining_seconds, 0); assert.equal(state.duration_seconds, 300);
 assert.deepEqual([state.fighter_a.points, state.fighter_b.penalties], [3, 1]);
 assert.equal(score(s, 'a', 'points', 1).code, 'already_finished', 'resuelto el resultado queda congelado');
 assert.equal(s.apply({...base(state), operation: 'reset'}).code, 'already_finished');
});

test('46 finish desde awaiting_result valida ganador y metodo y no muta al rechazar', () => {
 const s = expiredStore(); const expired = s.snapshot();
 for (const winner of [1, 999, null, '101', 101.5, true]) {
  const r = s.apply({...base(expired), operation: 'finish', winner_team_id: winner, method: 'points'});
  assert.equal(r.ok, false, String(winner)); assert.equal(r.code, 'invalid_winner', String(winner));
 }
 for (const method of ['ko', '', 'SUB', null, 'submission ']) {
  const r = s.apply({...base(expired), operation: 'finish', winner_team_id: 101, method});
  assert.equal(r.ok, false, String(method)); assert.equal(r.code, 'invalid_method', String(method));
 }
 assert.deepEqual(s.snapshot(), expired);
 assert.equal(finalState(s, 101, 'submission').status, 'finished');
});

test('47 el replay de finish no duplica ni reabre el combate agotado', () => {
 const s = expiredStore();
 const command = {...base(s.snapshot()), operation: 'finish', winner_team_id: 101, method: 'submission'};
 const first = s.apply(command); const frozen = s.snapshot();
 const replay = s.apply({...command});
 assert.equal(replay.ok, true); assert.equal(replay.changed, false); assert.equal(replay.revision, first.revision);
 assert.deepEqual(s.snapshot(), frozen);
});

test('48 clear_match no es valido mientras el resultado siga abierto', () => {
 const ready = assigned();
 const running1 = assigned(); score(running1, 'a', 'points', 2); running(running1, true);
 const paused = assigned(); running(paused, true); running(paused, false);
 const awaiting = expiredStore();
 for (const [label, store] of [['ready', ready], ['running', running1], ['paused', paused], ['awaiting_result', awaiting]]) {
  const before = store.snapshot();
  const r = cleared(store, before);
  assert.equal(r.ok, false, label); assert.equal(r.code, 'not_finished', label);
  assert.deepEqual(store.snapshot(), before, label + ' no se toca');
 }
});

test('49 clear_match tras finish vacia el tatami, sube una revision y emite estado vacio', () => {
 const s = assigned(); const session = s.snapshot().session_id;
 score(s, 'a', 'points', 5); const frozen = finalState(s, 101, 'submission');
 const r = cleared(s, frozen);
 assert.equal(r.ok, true); assert.equal(r.changed, true); assert.equal(r.revision, frozen.revision + 1);
 assert.equal(r.state, null, 'el snapshot emitido es explicitamente vacio');
 assert.equal(s.snapshot(), null); assert.equal(s.running(), false);
 assert.equal(s.apply({...base(frozen), operation: 'reset'}).code, 'wrong_session', 'ya no hay sesion activa');
 assert.equal(typeof session, 'string');
});

test('50 el registro de comandos desaparece con la sesion liberada', () => {
 const s = assigned();
 const scored = {...base(s.snapshot()), operation: 'score_delta', fighter: 'a', field: 'points', delta: 2};
 s.apply(scored);
 const frozen = finalState(s, 101, 'points');
 const clear = {...base(frozen), operation: 'clear_match'};
 assert.equal(s.apply(clear).ok, true);
 for (const command of [scored, {...clear}]) {
  const r = s.apply({...command});
  assert.equal(r.ok, false); assert.equal(r.code, 'wrong_session');
 }
 assert.equal(s.snapshot(), null);
});

test('51 tras clear_match una asignacion nueva abre una sesion distinta y limpia', () => {
 const s = assigned(); const first = s.snapshot();
 score(s, 'a', 'points', 7); finalState(s, 102, 'walkover');
 assert.equal(cleared(s).ok, true);
 assert.equal(s.snapshot(), null);
 const result = s.assign(otherFixture());
 assert.equal(result.status, 201);
 const state = s.snapshot();
 assert.equal(state.match_id, 41); assert.equal(state.status, 'ready'); assert.equal(state.revision, 1);
 assert.equal(state.remaining_seconds, state.duration_seconds);
 assert.deepEqual([state.fighter_a.points, state.fighter_a.advantages, state.fighter_a.penalties], [0, 0, 0]);
 assert.equal(state.winner_team_id, null); assert.equal(state.method, null);
 assert.notEqual(state.session_id, first.session_id, 'sesion nueva');
 assert.notEqual(state.fighter_a.team_id, first.fighter_a.team_id);
});

test('52 con la sesion abierta un combate distinto sigue dando 409 y la misma asignacion es replay', () => {
 const s = assigned(); const payload = fixture();
 assert.equal(s.assign(otherFixture()).status, 409, 'otro combate no puede entrar sin liberar');
 assert.equal(s.assign({...payload}).status, 200, 'la misma asignacion es un replay idempotente');
 assert.equal(s.snapshot().revision, 1);
 assert.equal(s.assign({...otherFixture()}).status, 409);
});

test('53 clear_match exige el conjunto exacto de campos y datos coherentes', () => {
 const s = assigned(); const frozen = finalState(s, 101, 'points');
 const invalid = [
  {...base(frozen), operation: 'clear_match', extra: 1},
  {...base(frozen), operation: 'clear_match', tatami_id: 2},
  {...base(frozen), operation: 'clear_match', match_id: frozen.match_id + 1},
  {...base(frozen), operation: 'clear_match', session_id: 'otra-sesion'},
 ];
 for (const command of invalid) {const r = s.apply(command); assert.equal(r.ok, false, JSON.stringify(r));}
 assert.equal(s.snapshot().revision, frozen.revision, 'ninguna variante invalida muta el combate');
 assert.equal(cleared(s, frozen).ok, true);
});

test('54 clear_match por socket emite estado vacio y luego admite otro combate', async t => {
 const {url} = await server(t), state = await assign(url);
 const controller = await connect(url, cookie(CONTROL)), display = await connect(url);
 await controller.poll(); await display.poll();
 const finish = {...base(state), operation: 'finish', winner_team_id: 101, method: 'points'};
 await controller.send('tatami:update', finish, 1);
 assert.equal(acks(await controller.poll()).get(1).ok, true);
 const conflict = await fetch(url + '/internal/tatamis/1/assignment', {method: 'PUT',
  headers: {'content-type': 'application/json', 'x-internal-token': INTERNAL}, body: JSON.stringify(otherFixture())});
 assert.equal(conflict.status, 409, 'sin liberar el tatami otro combate no entra');
 const clear = {...base({...state, revision: 2}), operation: 'clear_match'};
 await controller.send('tatami:update', clear, 2);
 assert.deepEqual(acks(await controller.poll()).get(2), {ok: true, command_id: clear.command_id, revision: 3});
 const broadcast = events(await display.poll()).filter(([event]) => event === 'tatami:state');
 assert.deepEqual(broadcast.at(-1), ['tatami:state', null], 'el estado vacio se emite de forma explicita');
 assert.equal((await (await fetch(url + '/internal/tatamis/1/state', {headers: {'x-internal-token': INTERNAL}})).json()).state, null);
 const next = await assign(url, otherFixture());
 assert.equal(next.status, 'ready'); assert.notEqual(next.session_id, state.session_id);
 const ready = await display.poll();
 const latest = events(ready).filter(([event]) => event === 'tatami:state').at(-1);
 assert.equal(latest[1].match_id, 41); assert.equal(latest[1].revision, 1);
 await controller.close(); await display.close();
});

test('55 clear_match exige credencial de control y no se puede disparar desde la pantalla', async t => {
 const {url} = await server(t), state = await assign(url);
 const controller = await connect(url, cookie(CONTROL)), display = await connect(url);
 await controller.poll(); await display.poll();
 const finish = {...base(state), operation: 'finish', winner_team_id: 102, method: 'other'};
 await controller.send('tatami:update', finish, 1); await controller.poll();
 const clear = {...base({...state, revision: 2}), operation: 'clear_match'};
 await display.send('tatami:update', clear, 1);
 assert.deepEqual(acks(await display.poll()).get(1), {ok: false, code: 'unauthorized', revision: 2});
 assert.equal((await (await fetch(url + '/internal/tatamis/1/state', {headers: {'x-internal-token': INTERNAL}})).json()).state.status, 'finished');
 await controller.close(); await display.close();
});

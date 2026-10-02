'use strict';
const {isDeepStrictEqual} = require('node:util');
const {randomUUID} = require('node:crypto');
const {performance} = require('node:perf_hooks');

// ---------------------------------------------------------------------------
// Canonical tatami 1 state.
// The integrated server owns the single source of truth of the live match:
// fighters, scoring, status and the authoritative clock. Browsers only render
// snapshots and send explicit commands; they never keep authoritative score.
// ---------------------------------------------------------------------------

const COMMAND_HISTORY = 256;  // bounded idempotency memory per active session
const MAX_DELTA = 100;        // absurd scoring jumps are refused, never clamped
const MAX_FIELD_VALUE = 1000; // ceiling for any accumulator
const FIELDS = ['points', 'advantages', 'penalties'];
const COMMAND_KEYS = ['session_id', 'command_id', 'expected_revision', 'tatami_id', 'match_id', 'operation'];
const OPERATIONS = {
 score_delta: [...COMMAND_KEYS, 'fighter', 'field', 'delta'],
 set_running: [...COMMAND_KEYS, 'running'],
 reset: [...COMMAND_KEYS],
};
function exact(value, keys) {
 return value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
const positive = value => Number.isSafeInteger(value) && value > 0;
const identifier = value => typeof value === 'string' && value.length > 0 && value.length <= 128;
function valid(p) {
 return exact(p, ['tournament_id','match_id','tatami_id','fighter_a','fighter_b','category','duration_seconds'])
  && exact(p.fighter_a, ['stage_item_input_id','team_id','name','club'])
  && exact(p.fighter_b, ['stage_item_input_id','team_id','name','club'])
  && exact(p.category, ['stage_item_id','name'])
  && [p.tournament_id,p.match_id,p.fighter_a.stage_item_input_id,p.fighter_b.stage_item_input_id,
   p.fighter_a.team_id,p.fighter_b.team_id,p.category.stage_item_id].every(positive)
  && p.tatami_id === 1
  && p.fighter_a.team_id !== p.fighter_b.team_id
  && p.fighter_a.stage_item_input_id !== p.fighter_b.stage_item_input_id
  && positive(p.duration_seconds)
  && [p.fighter_a.name,p.fighter_b.name,p.category.name].every(name => typeof name === 'string')
  && p.fighter_a.club === null && p.fighter_b.club === null;
}
function createStore(options = {}) {
 // Monotonic millisecond source, injectable so clock tests never sleep.
 const now = typeof options.now === 'function' ? options.now : () => performance.now();
 let active = null;
 let assignment = null;
 let commands = new Map();
 // Running clock anchor: the remaining seconds observed at a monotonic instant.
 // null while the clock is stopped, in which case active.remaining_seconds is
 // the frozen truth. remaining_seconds is never decremented tick by tick.
 let anchor = null;

 function running() {return anchor !== null;}
 function remaining() {
  if (anchor === null) return active.remaining_seconds;
  return Math.max(0, Math.ceil(anchor.seconds - (now() - anchor.at) / 1000));
 }
 // Expiry is derived from the monotonic clock, never from a per-second decrement.
 function advance() {
  if (active === null || anchor === null || remaining() > 0) return;
  active.remaining_seconds = 0;
  active.status = 'finished';
  anchor = null;
 }
 function snapshot() {
  advance();
  // Materialize the computed remaining time so every snapshot is self-contained.
  if (anchor !== null) active.remaining_seconds = remaining();
  return structuredClone(active);
 }
 function revision() {return active === null ? 0 : active.revision;}
 function refuse(code) {return {ok: false, code, revision: revision()};}
 function apply(command) {
  if (command === null || typeof command !== 'object' || Array.isArray(command)) return refuse('invalid_command');
  if (typeof command.operation !== 'string' || !Object.hasOwn(OPERATIONS, command.operation)) return refuse('invalid_operation');
  // Exact key sets: unknown or missing fields are rejected, never ignored.
  if (!exact(command, OPERATIONS[command.operation])) return refuse('invalid_command');
  if (!identifier(command.session_id) || !identifier(command.command_id)) return refuse('invalid_command');
  if (!Number.isSafeInteger(command.expected_revision) || command.expected_revision < 0) return refuse('invalid_command');
  if (command.tatami_id !== 1 || !positive(command.match_id)) return refuse('invalid_command');
  if (active === null || command.session_id !== active.session_id) return refuse('wrong_session');
  if (command.match_id !== active.match_id) return refuse('wrong_match');
  // Idempotency is checked before the revision: a retry of an accepted command
  // always returns the original ack and is never applied twice.
  const previous = commands.get(command.command_id);
  if (previous !== undefined) return {...previous};
  if (command.expected_revision !== active.revision) return refuse('stale_revision');
  let changed = false;
  if (command.operation === 'score_delta') {
   if (command.fighter !== 'a' && command.fighter !== 'b') return refuse('invalid_operation');
   if (!FIELDS.includes(command.field)) return refuse('invalid_operation');
   if (!Number.isSafeInteger(command.delta) || command.delta === 0 || Math.abs(command.delta) > MAX_DELTA) return refuse('invalid_operation');
   const fighter = command.fighter === 'a' ? active.fighter_a : active.fighter_b;
   const next = fighter[command.field] + command.delta;
   // Scoring never goes negative and absurd accumulations are refused, not clamped.
   if (next < 0 || next > MAX_FIELD_VALUE) return refuse('invalid_operation');
   fighter[command.field] = next;
   changed = true;
  } else if (command.operation === 'set_running') {
   if (typeof command.running !== 'boolean') return refuse('invalid_operation');
   if (command.running === true) {
    if (active.status === 'finished') return refuse('invalid_operation');
    if (active.status !== 'running') {
     anchor = {at: now(), seconds: active.remaining_seconds};
     active.status = 'running';
     changed = true;
    }
   } else if (active.status === 'running') {
    active.remaining_seconds = remaining();
    anchor = null;
    active.status = 'paused';
    changed = true;
   }
   // Requesting the state the match is already in is an idempotent no-op.
  } else {
   anchor = null;
   active.remaining_seconds = active.duration_seconds;
   active.status = 'ready';
   for (const side of ['fighter_a', 'fighter_b']) for (const field of FIELDS) active[side][field] = 0;
   active.winner_team_id = null;
   active.method = null;
   changed = true;
  }
  if (changed) active.revision += 1;
  const ack = {ok: true, command_id: command.command_id, revision: active.revision, changed};
  commands.set(command.command_id, {...ack, changed: false});
  while (commands.size > COMMAND_HISTORY) commands.delete(commands.keys().next().value);
  return changed === true ? {...ack, state: snapshot()} : ack;
 }
 return {
  snapshot: () => snapshot(),
  apply: command => apply(command),
  running: () => running(),
  assign(payload) {
   if (!valid(payload)) return {status: 400};
   if (assignment && isDeepStrictEqual(assignment, payload)) return {status: 200, state: snapshot()};
   if (assignment) return {status: 409};
   assignment = structuredClone(payload);
   commands = new Map();
   anchor = null;
   active = {...structuredClone(payload),
    fighter_a: {...payload.fighter_a, points: 0, advantages: 0, penalties: 0},
    fighter_b: {...payload.fighter_b, points: 0, advantages: 0, penalties: 0},
    remaining_seconds: payload.duration_seconds, status: 'ready', winner_team_id: null,
    method: null, session_id: randomUUID(), revision: 1};
   return {status: 201, state: snapshot()};
  }
 };
}
module.exports = {createStore};

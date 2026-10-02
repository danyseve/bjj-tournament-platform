'use strict';
const {isDeepStrictEqual} = require('node:util');
const {randomUUID} = require('node:crypto');
const {performance} = require('node:perf_hooks');

// ---------------------------------------------------------------------------
// Canonical tatami 1 state.
// The integrated server owns the single source of truth of the live match:
// fighters, scoring, status and the authoritative clock. Browsers only render
// snapshots and send explicit commands; they never keep authoritative score.
//
// Status machine: ready -> running <-> paused -> awaiting_result -> finished.
// awaiting_result means the clock ran out while the result is still open (no
// winner recorded yet); finished means the result is closed and frozen. An
// explicit clear_match empties the tatami, and only a finished match may be
// cleared. The state lives in memory and, when the integrated server hands in a
// persistence sink, is mirrored to a versioned local document after every
// accepted command (document()/save() below). Recovery (restore()) rebuilds the
// monotonic clock anchor from wall time exactly once, on startup.
// ---------------------------------------------------------------------------

const COMMAND_HISTORY = 256;  // bounded idempotency memory per active session
const MAX_DELTA = 100;        // absurd scoring jumps are refused, never clamped
const MAX_FIELD_VALUE = 1000; // ceiling for any accumulator
const FIELDS = ['points', 'advantages', 'penalties'];
// Local BJJ domain enum for the finish method. It is intentionally not mapped to
// the Bracket model yet: finalization stays in memory and nothing is persisted.
const METHODS = ['points', 'submission', 'decision', 'disqualification', 'walkover', 'referee_stoppage', 'other'];
const COMMAND_KEYS = ['session_id', 'command_id', 'expected_revision', 'tatami_id', 'match_id', 'operation'];
// Persisted contract. The document holds the live state, the wall anchor of a
// running clock and the bounded idempotency memory: never tokens, cookies,
// sockets or configuration.
const SCHEMA_VERSION = 1;
const STATUSES = ['ready', 'running', 'paused', 'awaiting_result', 'finished'];
const STATE_KEYS = ['session_id', 'revision', 'tatami_id', 'tournament_id', 'match_id', 'fighter_a', 'fighter_b',
 'category', 'duration_seconds', 'remaining_seconds', 'status', 'winner_team_id', 'method'];
const FIGHTER_KEYS = ['stage_item_input_id', 'team_id', 'name', 'club', 'points', 'advantages', 'penalties'];
const DOCUMENT_KEYS = ['schema_version', 'saved_at', 'clock', 'state', 'command_history'];
const ACK_KEYS = ['ok', 'command_id', 'revision', 'changed'];
class InvalidStateError extends Error {
 constructor(message) {
  super(message);
  this.name = 'InvalidStateError';
 }
}
const OPERATIONS = {
 score_delta: [...COMMAND_KEYS, 'fighter', 'field', 'delta'],
 set_running: [...COMMAND_KEYS, 'running'],
 reset: [...COMMAND_KEYS],
 finish: [...COMMAND_KEYS, 'winner_team_id', 'method'],
 clear_match: [...COMMAND_KEYS],
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
// The original normalized assignment is rebuilt from the canonical state, so an
// idempotent replay of the same PUT still answers 200 after a restart and a
// different match still answers 409.
function assignmentFromState(state) {
 return {
  tournament_id: state.tournament_id, match_id: state.match_id, tatami_id: state.tatami_id,
  fighter_a: {stage_item_input_id: state.fighter_a.stage_item_input_id, team_id: state.fighter_a.team_id,
   name: state.fighter_a.name, club: state.fighter_a.club},
  fighter_b: {stage_item_input_id: state.fighter_b.stage_item_input_id, team_id: state.fighter_b.team_id,
   name: state.fighter_b.name, club: state.fighter_b.club},
  category: {stage_item_id: state.category.stage_item_id, name: state.category.name},
  duration_seconds: state.duration_seconds,
 };
}
// A persisted document is either accepted whole or refused whole: a partial or
// surprising document is never half-loaded.
function validateDocument(document) {
 const fail = message => {throw new InvalidStateError(message);};
 if (document === null || typeof document !== 'object' || Array.isArray(document)) fail('document must be an object');
 if (!exact(document, DOCUMENT_KEYS)) fail('document keys are not the persisted contract');
 if (document.schema_version !== SCHEMA_VERSION) fail('unsupported schema_version: ' + String(document.schema_version));
 if (typeof document.saved_at !== 'string') fail('saved_at must be a string');
 if (!exact(document.clock, ['wall_anchor'])) fail('clock keys are not the persisted contract');
 if (document.clock.wall_anchor !== null && !Number.isSafeInteger(document.clock.wall_anchor)) fail('wall_anchor must be null or an integer');
 if (!Array.isArray(document.command_history)) fail('command_history must be an array');
 if (document.command_history.length > COMMAND_HISTORY) fail('command_history is longer than the bounded history');
 const state = document.state;
 if (state === null) {
  if (document.command_history.length > 0) fail('an empty tatami cannot keep a command history');
  if (document.clock.wall_anchor !== null) fail('an empty tatami cannot keep a wall anchor');
  return {state: null, history: []};
 }
 if (typeof state !== 'object' || Array.isArray(state) || !exact(state, STATE_KEYS)) fail('state keys are not the canonical contract');
 if (!identifier(state.session_id)) fail('session_id is not an identifier');
 if (!Number.isSafeInteger(state.revision) || state.revision < 1) fail('revision must be a positive integer');
 if (state.tatami_id !== 1) fail('only tatami 1 is persisted');
 if (![state.tournament_id, state.match_id, state.duration_seconds].every(positive)) fail('identifiers must be positive integers');
 if (STATUSES.includes(state.status) === false) fail('unknown status: ' + String(state.status));
 if (!Number.isSafeInteger(state.remaining_seconds) || state.remaining_seconds < 0 || state.remaining_seconds > state.duration_seconds) fail('remaining_seconds is out of range');
 if (state.status === 'ready' && state.remaining_seconds !== state.duration_seconds) fail('a ready match must hold the full duration');
 if (state.status === 'awaiting_result' && state.remaining_seconds !== 0) fail('a match awaiting result must hold zero remaining time');
 if (state.status === 'running' && state.remaining_seconds < 1) fail('a running match must hold remaining time');
 if (!valid(assignmentFromState(state))) fail('the persisted fighters are not a valid assignment');
 for (const side of ['fighter_a', 'fighter_b']) {
  const fighter = state[side];
  if (!exact(fighter, FIGHTER_KEYS)) fail(side + ' keys are not the persisted contract');
  if (![fighter.points, fighter.advantages, fighter.penalties].every(value => Number.isSafeInteger(value) && value >= 0)) {
   fail(side + ' scoring must be non-negative integers');
  }
 }
 if (state.status === 'finished') {
  if (state.winner_team_id !== state.fighter_a.team_id && state.winner_team_id !== state.fighter_b.team_id) fail('a finished match must name one of its fighters');
  if (METHODS.includes(state.method) === false) fail('a finished match must carry a known method');
 } else if (state.winner_team_id !== null || state.method !== null) {
  fail('only a finished match may carry a result');
 }
 if (state.status !== 'running' && document.clock.wall_anchor !== null) fail('a stopped clock cannot carry a wall anchor');
 const seen = new Set();
 const history = document.command_history.map(entry => {
  if (!exact(entry, ['command_id', 'ack'])) fail('history entries hold exactly command_id and ack');
  if (!identifier(entry.command_id)) fail('a history command_id is not an identifier');
  if (seen.has(entry.command_id)) fail('duplicate command_id in history');
  seen.add(entry.command_id);
  if (!exact(entry.ack, ACK_KEYS)) fail('a history ack is not the persisted contract');
  if (entry.ack.ok !== true || entry.ack.changed !== false) fail('only accepted, unchanged commands are remembered');
  if (entry.ack.command_id !== entry.command_id) fail('a history ack must answer its own command_id');
  if (!Number.isSafeInteger(entry.ack.revision) || entry.ack.revision < 1 || entry.ack.revision > state.revision) {
   fail('a history revision is outside the current revision');
  }
  return [entry.command_id, {...entry.ack}];
 });
 return {state: structuredClone(state), history};
}
function createStore(options = {}) {
 // Monotonic millisecond source, injectable so clock tests never sleep.
 const now = typeof options.now === 'function' ? options.now : () => performance.now();
 // Wall time stamps the persisted document and drives recovery only: it is never
 // the authoritative clock while the match runs.
 const wallNow = typeof options.wallNow === 'function' ? options.wallNow : () => Date.now();
 // Persistence sink. When present, the new state is written before its ack and a
 // failed write rolls the command back (fail-closed, never a fake success).
 const persist = typeof options.persist === 'function' ? options.persist : null;
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
 // Reaching zero is not a closed result: the match waits for an explicit finish,
 // so a winner can still be recorded afterwards.
 function advance() {
  if (active === null || anchor === null || remaining() > 0) return;
  active.remaining_seconds = 0;
  active.status = 'awaiting_result';
  anchor = null;
 }
 function snapshot() {
  advance();
  // Materialize the computed remaining time so every snapshot is self-contained.
  if (anchor !== null) active.remaining_seconds = remaining();
  return structuredClone(active);
 }
 function revision() {return active === null ? 0 : active.revision;}
 function remember() {
  return {active: active === null ? null : structuredClone(active),
   assignment: assignment === null ? null : structuredClone(assignment),
   commands: new Map(commands), anchor: anchor === null ? null : {...anchor}};
 }
 function restoreMemory(previous) {
  active = previous.active;
  assignment = previous.assignment;
  commands = previous.commands;
  anchor = previous.anchor;
 }
 // The persisted document: canonical state, the wall anchor of a running clock
 // and the bounded idempotency memory of the current session. No secrets.
 function document() {
  const state = snapshot();
  return {
   schema_version: SCHEMA_VERSION,
   saved_at: new Date(wallNow()).toISOString(),
   clock: {wall_anchor: state !== null && state.status === 'running' ? wallNow() : null},
   state,
   command_history: [...commands].map(([command_id, ack]) => ({command_id, ack: {...ack}})),
  };
 }
 function save() {
  if (persist !== null) persist(document());
  return true;
 }
 // Startup recovery. The persisted remaining time and its wall stamp describe the
 // same instant: elapsed wall time is subtracted once and a fresh monotonic
 // anchor takes over from there.
 function restore(input) {
  const restored = validateDocument(input);
  active = restored.state;
  assignment = active === null ? null : assignmentFromState(active);
  commands = new Map(restored.history);
  anchor = null;
  if (active !== null && active.status === 'running') {
   const elapsed = Math.max(0, wallNow() - input.clock.wall_anchor);
   const left = Math.max(0, Math.ceil(active.remaining_seconds - elapsed / 1000));
   active.remaining_seconds = left;
   if (left <= 0) {
    // The clock ran out while the process was down: time up, result still open.
    active.remaining_seconds = 0;
    active.status = 'awaiting_result';
   } else {
    anchor = {at: now(), seconds: left};
   }
  }
  return snapshot();
 }
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
  // From here on the canonical state is mutated: keep a rollback copy so a
  // failed persistence never leaves memory ahead of the stored document.
  const before = remember();
  // clear_match is the only way to leave a match behind, and it is valid only on
  // a closed result: abandoning an open fight is refused.
  if (command.operation === 'clear_match') {
   if (active.status !== 'finished') return refuse('not_finished');
   // The tatami goes empty: session, clock and the idempotency memory of that
   // session disappear together, and no match is loaded automatically.
   const revision = active.revision + 1;
   active = null;
   assignment = null;
   commands = new Map();
   anchor = null;
   // The tatami is emptied explicitly (state: null), never by deleting the file,
   // and the idempotency memory of the finished session goes with it.
   try {
    save();
   } catch (error) {
    restoreMemory(before);
    return refuse('persist_failed');
   }
   return {ok: true, command_id: command.command_id, revision, changed: true, state: null};
  }
  // A finished match is frozen: no scoring, clock, reset or second finish may
  // touch it. Only a replay of an already accepted command answers (above).
  if (active.status === 'finished') return refuse('already_finished');
  // Time is up but the result is still open: only finish may resolve it.
  if (active.status === 'awaiting_result' && command.operation !== 'finish') return refuse('awaiting_result');
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
  } else if (command.operation === 'finish') {
   if (command.winner_team_id !== active.fighter_a.team_id
    && command.winner_team_id !== active.fighter_b.team_id) return refuse('invalid_winner');
   if (METHODS.includes(command.method) === false) return refuse('invalid_method');
   // Freeze the authoritative clock at the value observed right now, keep the
   // final scoring and record the result in memory only.
   active.remaining_seconds = remaining();
   anchor = null;
   active.status = 'finished';
   active.winner_team_id = command.winner_team_id;
   active.method = command.method;
   changed = true;
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
  // Durable before acknowledged: the new state and the accepted command id are
  // written first, and a write failure rolls the whole command back.
  try {
   save();
  } catch (error) {
   restoreMemory(before);
   return refuse('persist_failed');
  }
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
   const before = remember();
   assignment = structuredClone(payload);
   commands = new Map();
   anchor = null;
   active = {...structuredClone(payload),
    fighter_a: {...payload.fighter_a, points: 0, advantages: 0, penalties: 0},
    fighter_b: {...payload.fighter_b, points: 0, advantages: 0, penalties: 0},
    remaining_seconds: payload.duration_seconds, status: 'ready', winner_team_id: null,
    method: null, session_id: randomUUID(), revision: 1};
   try {
    save();
   } catch (error) {
    // No assignment is acknowledged when the new state cannot be persisted.
    restoreMemory(before);
    return {status: 503};
   }
   return {status: 201, state: snapshot()};
  },
  restore: input => restore(input),
  document: () => document(),
  persistenceEnabled: () => persist !== null,
 };
}
module.exports = {createStore, METHODS, validateDocument, InvalidStateError, SCHEMA_VERSION};

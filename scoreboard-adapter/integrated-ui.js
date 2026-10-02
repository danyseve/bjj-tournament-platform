'use strict';
// Integrated presentation and control. The standalone legacy asset is never modified.
// The server is the single source of truth: this client only renders snapshots and,
// on the control pages, sends explicit canonical commands. It never keeps
// authoritative scoring and never emits the legacy standalone events.
(() => {
 const badge = document.createElement('div');
 badge.id = 'integrated-mode';
 badge.setAttribute('role', 'status');
 badge.style.cssText = 'position:fixed;top:0;left:0;z-index:1000;background:#222;color:#fff;padding:4px 8px;font:14px sans-serif';
 document.body.appendChild(badge);

 // Legacy visual controls mapped to canonical score_delta operations.
 const SCORING = {
  add4f1: {fighter: 'a', field: 'points', delta: 4}, sub4f1: {fighter: 'a', field: 'points', delta: -4},
  add3f1: {fighter: 'a', field: 'points', delta: 3}, sub3f1: {fighter: 'a', field: 'points', delta: -3},
  add2f1: {fighter: 'a', field: 'points', delta: 2}, sub2f1: {fighter: 'a', field: 'points', delta: -2},
  addadvf1: {fighter: 'a', field: 'advantages', delta: 1}, subadvf1: {fighter: 'a', field: 'advantages', delta: -1},
  addpenalf1: {fighter: 'a', field: 'penalties', delta: 1}, subpenalf1: {fighter: 'a', field: 'penalties', delta: -1},
  add4f2: {fighter: 'b', field: 'points', delta: 4}, sub4f2: {fighter: 'b', field: 'points', delta: -4},
  add3f2: {fighter: 'b', field: 'points', delta: 3}, sub3f2: {fighter: 'b', field: 'points', delta: -3},
  add2f2: {fighter: 'b', field: 'points', delta: 2}, sub2f2: {fighter: 'b', field: 'points', delta: -2},
  addadvf2: {fighter: 'b', field: 'advantages', delta: 1}, subadvf2: {fighter: 'b', field: 'advantages', delta: -1},
  addpenalf2: {fighter: 'b', field: 'penalties', delta: 1}, subpenalf2: {fighter: 'b', field: 'penalties', delta: -1},
 };
 const LOCKABLE = 'input,button,#start,#restart,[id^="add"],[id^="sub"]';
 // A control page owns the legacy scoring surface; the display page never does.
 const control = document.querySelector('#add4f1') !== null;
 const socket = io();
 let state = null;
 let revision = -1;
 let remaining = null;
 let sequence = 0;

 function commandId() {
  const source = typeof globalThis.crypto === 'object' && globalThis.crypto !== null ? globalThis.crypto : null;
  if (source !== null && typeof source.randomUUID === 'function') return source.randomUUID();
  sequence += 1;
  return 'cmd-' + Date.now().toString(36) + '-' + sequence.toString(36) + '-' + Math.random().toString(36).slice(2, 10);
 }
 function active(id) {return control === true && state !== null && (Object.hasOwn(SCORING, id) || id === 'start' || id === 'restart');}
 function paint() {
  document.querySelectorAll(LOCKABLE).forEach(node => {
   if (active(node.id) === true) {
    node.disabled = false;
    node.removeAttribute('disabled');
    node.removeAttribute('aria-disabled');
    node.removeAttribute('tabindex');
    node.style.pointerEvents = '';
    node.style.opacity = '';
    return;
   }
   node.setAttribute('aria-disabled', 'true');
   node.setAttribute('tabindex', '-1');
   if (node.matches('input,button')) node.disabled = true;
   else node.setAttribute('disabled', '');
   node.style.pointerEvents = 'none';
   node.style.opacity = '0.5';
  });
  const start = document.querySelector('#start');
  if (start !== null && state !== null) {
   const running = state.status === 'running';
   start.setAttribute('class', running === true ? 'fas fa-pause-circle' : 'fas fa-play-circle');
   if (start.tagName === 'BUTTON') start.textContent = running === true ? 'Pausa' : 'Iniciar';
  }
 }
 function waiting() {
  state = null;
  revision = -1;
  remaining = null;
  document.querySelectorAll('.fighter-1-score,.fighter-2-score,.fighter-1-adv,.fighter-2-adv,.fighter-1-penal,.fighter-2-penal').forEach(node => {node.textContent = '0';});
  document.querySelectorAll('.points-score').forEach(node => {node.textContent = '—';});
  badge.textContent = 'Integrated · Waiting for assignment · ' + (control === true ? 'Control' : 'Read-only');
  document.querySelectorAll('input[id^="fighter-"]').forEach(input => {input.value = ''; input.placeholder = '';});
  document.querySelectorAll('.timer').forEach(node => {node.textContent = '--:--';});
  paint();
 }
 function present() {
  badge.textContent = 'Integrated · ' + state.status + ' · ' + (control === true ? 'Control' : 'Read-only');
  const seconds = state.remaining_seconds;
  const time = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0');
  document.querySelectorAll('.timer').forEach(node => {node.textContent = time;});
  [state.fighter_a, state.fighter_b].forEach((fighter, index) => {
   const number = index + 1;
   document.querySelector('#fighter-' + number + '-name').value = fighter.name;
   [['score', 'points'], ['adv', 'advantages'], ['penal', 'penalties']].forEach(([css, key]) => {
    document.querySelectorAll('.fighter-' + number + '-' + css).forEach(node => {node.textContent = fighter[key];});
   });
  });
  paint();
 }
 // Explicit non-toggle commands: the payload always states the intended state.
 function send(operation, fields) {
  if (control !== true || state === null) return;
  if (typeof state.tatami_id !== 'number' || typeof state.match_id !== 'number') return;
  const payload = {session_id: state.session_id, command_id: commandId(), expected_revision: state.revision,
   tatami_id: state.tatami_id, match_id: state.match_id, operation, ...fields};
  socket.emit('tatami:update', payload, response => {
   // Refusals carry the current server revision so the next command is not stale.
   if (response && response.ok === false && Number.isSafeInteger(response.revision) === true
    && state !== null && response.revision > state.revision) state.revision = response.revision;
  });
 }
 waiting();

 socket.on('tatami:state', next => {
  if (!next) {waiting(); return;}
  if (state === null || next.session_id !== state.session_id) {
   revision = -1;
   remaining = null;
   document.querySelectorAll('.points-score').forEach(node => {node.textContent = '—';});
  }
  if (next.revision < revision) return;
  // A same-revision snapshot is only a clock tick: it may never run time backwards.
  if (next.revision === revision && next.remaining_seconds > remaining) return;
  state = next;
  revision = next.revision;
  remaining = next.remaining_seconds;
  present();
 });

 if (control === true) {
  for (const id of Object.keys(SCORING)) {
   const node = document.querySelector('#' + id);
   if (node !== null) node.addEventListener('click', () => send('score_delta', SCORING[id]));
  }
  const start = document.querySelector('#start');
  if (start !== null) start.addEventListener('click', () => send('set_running', {running: state !== null && state.status === 'running' ? false : true}));
  const restart = document.querySelector('#restart');
  if (restart !== null) restart.addEventListener('click', () => send('reset'));
 }
})();

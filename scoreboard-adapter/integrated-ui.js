'use strict';
// Integrated presentation and control. The standalone legacy asset is never modified.
// The server is the single source of truth: this client only renders snapshots and,
// on the control pages, sends explicit canonical commands. It never keeps
// authoritative scoring and never emits the legacy standalone events.
(() => {
 // Operational documentation lives in the docs centre; the link is static data,
 // never fetched, so the UI keeps working with no network dependency.
 const MANUAL_URL = 'https://docs.opsforge.cc/bjj/tatami/';
 const badge = document.createElement('div');
 badge.id = 'integrated-mode';
 badge.setAttribute('role', 'status');
 badge.style.cssText = 'position:fixed;top:0;left:0;z-index:1000;background:#222;color:#fff;padding:4px 8px;font:14px sans-serif;display:flex;align-items:center;gap:8px;white-space:nowrap';
 // The chip text lives in its own span: repainting a state must never wipe the link.
 const badgeText = document.createElement('span');
 badgeText.id = 'integrated-mode-text';
 badge.appendChild(badgeText);
 const separator = document.createElement('span');
 separator.setAttribute('aria-hidden', 'true');
 separator.textContent = '|';
 separator.style.cssText = 'opacity:0.6';
 badge.appendChild(separator);
 // Static reference to the Tatami manual: navigation only, integrated in the status
 // bar the operator already sees, and never a scoring control, a socket or a state
 // mutation. Keeping it inside the chip means page layout cannot hide it.
 const manualLink = document.createElement('a');
 manualLink.id = 'integrated-manual';
 manualLink.href = MANUAL_URL;
 manualLink.target = '_blank';
 manualLink.rel = 'noopener noreferrer';
 manualLink.textContent = '? Manual';
 manualLink.setAttribute('aria-label', 'Abrir el manual del Tatami en una pestaña nueva');
 manualLink.style.cssText = 'color:#fff;background:transparent;text-decoration:underline;font:inherit';
 badge.appendChild(manualLink);
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
 // Local BJJ domain enum mirrored from the server (state.js METHODS). A test
 // keeps both lists identical. Values are not mapped to Bracket and no result
 // leaves this process: finalization only lives in the server memory.
 const METHODS = ['points', 'submission', 'decision', 'disqualification', 'walkover', 'referee_stoppage', 'other'];
 const METHOD_LABELS = {points: 'Puntos', submission: 'Sumisión', decision: 'Decisión', disqualification: 'Descalificación',
  walkover: 'Walkover', referee_stoppage: 'Parada del árbitro', other: 'Otro'};
 const LOCKABLE = 'input,button,#start,#restart,[id^="add"],[id^="sub"]';
 // Only an open fight accepts scoring or clock commands. With the time up the
 // result is still pending, and after finish it is closed and frozen.
 const LIVE = ['ready', 'running', 'paused'];
 const PENDING = 'Tiempo finalizado — pendiente de resultado';
 // A control page owns the legacy scoring surface; the display page never does.
 const control = document.querySelector('#add4f1') !== null;
 const socket = io();
 let state = null;
 let revision = -1;
 let remaining = null;
 let sequence = 0;
 let armed = false;
 let clearArmed = false;
 let cancelArmed = false;
 const panel = control === true ? buildFinishPanel() : null;
 const clearPanel = control === true ? buildClearPanel() : null;
 const cancelPanel = control === true ? buildCancelPanel() : null;
 const result = buildResult();

 function node(tag, id, text) {
  const created = document.createElement(tag);
  if (id !== undefined) created.id = id;
  if (text !== undefined) created.textContent = text;
  return created;
 }
 function option(value, text) {const created = node('option', undefined, text); created.value = value; return created;}
 // Minimal finalization surface: winner, method and an explicit confirmation
 // step, so a finish is never a single accidental click. Read-only routes never
 // build it.
 function buildFinishPanel() {
  const root = node('div', 'integrated-finish');
  root.style.cssText = 'position:fixed;right:0;bottom:0;z-index:1000;background:#111;color:#fff;padding:6px 8px;font:14px sans-serif;display:flex;gap:6px;align-items:center;flex-wrap:wrap';
  const winner = node('select', 'finish-winner');
  winner.appendChild(option('', 'Ganador…'));
  const method = node('select', 'finish-method');
  method.appendChild(option('', 'Método…'));
  for (const value of METHODS) method.appendChild(option(value, METHOD_LABELS[value]));
  const ask = node('span', 'finish-ask');
  const open = node('button', 'finish-open', 'Finalizar…');
  const confirm = node('button', 'finish-confirm', 'Confirmar finalización');
  const cancel = node('button', 'finish-cancel', 'Cancelar');
  root.append(winner, method, open, ask, confirm, cancel);
  document.body.appendChild(root);
  return {root, winner, method, ask, open, confirm, cancel, filled: null};
 }
 // A separate, explicit release surface: it is never merged with finalization and
 // it is only usable once the result is closed, because releasing an open fight
 // would throw a result away.
 function buildClearPanel() {
  const root = node('div', 'integrated-clear');
  root.style.cssText = 'position:fixed;left:0;bottom:0;z-index:1000;background:#111;color:#fff;padding:6px 8px;font:14px sans-serif;display:flex;gap:6px;align-items:center;flex-wrap:wrap';
  const ask = node('span', 'clear-ask');
  const open = node('button', 'clear-open', 'Liberar Tatami');
  const confirm = node('button', 'clear-confirm', 'Confirmar liberación');
  const cancel = node('button', 'clear-cancel', 'Cancelar');
  root.append(open, ask, confirm, cancel);
  document.body.appendChild(root);
  return {root, ask, open, confirm, cancel};
  }
// A third, separate surface for the mistaken assignment. It is neither the
// post-finish release nor a side effect of finishing: it only ever appears while
// the match is still untouched (ready, full clock, no scoring, no result), which
// is exactly the window in which nothing can be lost by dropping it.
 function buildCancelPanel() {
  const root = node('div', 'integrated-cancel');
  root.style.cssText = 'position:fixed;left:0;bottom:36px;z-index:1000;background:#111;color:#fff;padding:6px 8px;font:14px sans-serif;display:flex;gap:6px;align-items:center;flex-wrap:wrap';
  const ask = node('span', 'cancel-ask');
  const open = node('button', 'cancel-open', 'Cancelar asignación');
  const confirm = node('button', 'cancel-confirm', 'Confirmar cancelación');
  const abort = node('button', 'cancel-abort', 'Cancelar');
  root.append(open, ask, confirm, abort);
  document.body.appendChild(root);
  return {root, ask, open, confirm, abort};
 }
 // The server refuses anything that is not a pristine ready match; the panel
 // mirrors that same predicate so it is never offered where it would be refused.
 function cancelable() {
  if (state === null || state.status !== 'ready') return false;
  if (state.remaining_seconds !== state.duration_seconds) return false;
  // A missing result field means the same as an explicit null: the canonical
  // snapshot always carries both, but offering the action must not depend on
  // that. The server is the authority and refuses anything that is not pristine.
  if (state.winner_team_id !== null && state.winner_team_id !== undefined) return false;
  if (state.method !== null && state.method !== undefined) return false;
  return [state.fighter_a, state.fighter_b].every(fighter =>
   fighter.points === 0 && fighter.advantages === 0 && fighter.penalties === 0);
 }
 function buildResult() {
  const banner = node('div', 'integrated-result');
  banner.style.cssText = 'position:fixed;right:0;top:0;z-index:1000;background:#0b6;color:#fff;padding:4px 8px;font:14px sans-serif';
  document.body.appendChild(banner);
  return banner;
 }
 function methodLabel(method) {return typeof method === 'string' && METHOD_LABELS[method] !== undefined ? METHOD_LABELS[method] : String(method);}
 function winnerName() {
  if (state === null) return null;
  if (state.winner_team_id === state.fighter_a.team_id) return state.fighter_a.name;
  if (state.winner_team_id === state.fighter_b.team_id) return state.fighter_b.name;
  return null;
 }
 function finalText() {
  const name = winnerName();
  if (name === null) return 'Finalizado · sin ganador registrado';
  return 'Finalizado · Ganador: ' + name + (state.method === null ? '' : ' · ' + methodLabel(state.method));
 }
 // The read-only display announces that the time is up without inventing a winner.
 function resultText() {
  if (state === null) return 'Tatami 1 libre — sin combate asignado';
  if (state.status === 'finished') return finalText();
  if (state.status === 'awaiting_result') return PENDING;
  return '';
 }
 function fillWinner() {
  const previous = panel.winner.value;
  panel.winner.replaceChildren(option('', 'Ganador…'));
  if (state !== null) {
   for (const [side, fighter] of [['A', state.fighter_a], ['B', state.fighter_b]]) {
    if (Number.isSafeInteger(fighter.team_id) === true) panel.winner.appendChild(option(String(fighter.team_id), side + ' · ' + fighter.name));
   }
  }
  panel.winner.value = [...panel.winner.options].some(candidate => candidate.value === previous) ? previous : '';
  panel.filled = state === null ? null : state.session_id;
 }
 function selectedName() {
  const current = panel.winner.selectedOptions[0];
  return current === undefined ? '' : current.textContent.replace(/^[AB] · /, '');
 }
 // The panel mirrors the server state: it never guesses and never stays armed
 // over a new snapshot.
 function paintFinish() {
  if (panel === null) return;
  const finished = state !== null && state.status === 'finished';
  const live = state !== null && finished === false;
  if (panel.filled !== (state === null ? null : state.session_id)) fillWinner();
  panel.winner.disabled = live === false || armed === true;
  panel.method.disabled = live === false || armed === true;
  panel.open.disabled = live === false || armed === true || panel.winner.value === '' || panel.method.value === '';
  panel.open.style.display = armed === true || finished === true ? 'none' : '';
  // The pending notice is visible as soon as the clock runs out: the result is
  // open and the operator is asked to close it.
  const notice = armed === true || finished === true || (state !== null && state.status === 'awaiting_result');
  panel.ask.style.display = notice === true ? '' : 'none';
  panel.confirm.style.display = armed === true ? '' : 'none';
  panel.cancel.style.display = armed === true ? '' : 'none';
  if (finished === true) panel.ask.textContent = finalText();
  else if (armed === true) panel.ask.textContent = '¿Finalizar como ganador ' + selectedName() + ' por ' + methodLabel(panel.method.value) + '?';
  else if (state !== null && state.status === 'awaiting_result') panel.ask.textContent = PENDING;
  else panel.ask.textContent = '';
 }
 function commandId() {
  const source = typeof globalThis.crypto === 'object' && globalThis.crypto !== null ? globalThis.crypto : null;
  if (source !== null && typeof source.randomUUID === 'function') return source.randomUUID();
  sequence += 1;
  return 'cmd-' + Date.now().toString(36) + '-' + sequence.toString(36) + '-' + Math.random().toString(36).slice(2, 10);
 }
 function active(id) {
  if (control !== true || state === null) return false;
  // Pending and closed results lock every mutation control: scoring, clock and
  // reset answer only while the fight is open.
  if (LIVE.includes(state.status) === false) return false;
  return Object.hasOwn(SCORING, id) || id === 'start' || id === 'restart';
 }
 function paintClear() {
  if (clearPanel === null) return;
  const cleared = state !== null && state.status === 'finished';
  clearPanel.root.style.display = state === null ? 'none' : '';
  clearPanel.open.disabled = cleared === false || clearArmed === true;
  clearPanel.open.style.display = clearArmed === true ? 'none' : '';
  clearPanel.ask.textContent = clearArmed === true ? '¿Liberar el Tatami? El resultado en memoria se perderá.' : '';
  for (const element of [clearPanel.ask, clearPanel.confirm, clearPanel.cancel]) {
   element.style.display = clearArmed === true ? '' : 'none';
  }
 }
 // The cancellation surface is offered only while the match is untouched, and it
 // is always a two-step action of its own: it is never the release after a finish.
 function paintCancel() {
  if (cancelPanel === null) return;
  const allowed = cancelable();
  if (allowed === false) cancelArmed = false;
  cancelPanel.root.style.display = allowed === true ? '' : 'none';
  cancelPanel.open.disabled = allowed === false || cancelArmed === true;
  cancelPanel.open.style.display = cancelArmed === true ? 'none' : '';
  cancelPanel.ask.textContent = cancelArmed === true ? '¿Cancelar la asignación? El combate quedará sin asignar.' : '';
  for (const element of [cancelPanel.ask, cancelPanel.confirm, cancelPanel.abort]) {
   element.style.display = cancelArmed === true ? '' : 'none';
  }
 }
 function paint() {
  document.querySelectorAll(LOCKABLE).forEach(node => {
   // The finalization, release and cancellation controls live outside the legacy lock set.
   if (node.closest('#integrated-finish') !== null || node.closest('#integrated-clear') !== null || node.closest('#integrated-cancel') !== null) return;
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
  paintFinish();
  paintClear();
  paintCancel();
 }
 function waiting() {
  state = null;
  revision = -1;
  remaining = null;
  document.querySelectorAll('.fighter-1-score,.fighter-2-score,.fighter-1-adv,.fighter-2-adv,.fighter-1-penal,.fighter-2-penal').forEach(node => {node.textContent = '0';});
  document.querySelectorAll('.points-score').forEach(node => {node.textContent = '—';});
  badgeText.textContent = 'Integrated · Waiting for assignment · ' + (control === true ? 'Control' : 'Read-only');
  document.querySelectorAll('input[id^="fighter-"]').forEach(input => {input.value = ''; input.placeholder = '';});
  document.querySelectorAll('.timer').forEach(node => {node.textContent = '--:--';});
  armed = false;
  clearArmed = false;
  cancelArmed = false;
  result.textContent = resultText();
  paint();
 }
 function present() {
  badgeText.textContent = 'Integrated · ' + state.status + ' · ' + (control === true ? 'Control' : 'Read-only');
  // The read-only display also reflects the pending or final result, without controls.
  result.textContent = resultText();
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
  // Finalization is terminal here as well: no later snapshot may resurrect the
  // same match (a brand new session is a different match and still replaces it).
  if (state !== null && state.status === 'finished' && next.session_id === state.session_id && next.status !== 'finished') return;
  // A same-revision snapshot is only a clock tick: it may never run time backwards.
  if (next.revision === revision && next.remaining_seconds > remaining) return;
  state = next;
  revision = next.revision;
  remaining = next.remaining_seconds;
  present();
 });

 if (control === true) {
  // Every handler re-checks authorization: a locked control cannot emit even if
  // an event reaches it (a disabled node still fires a synthetic click).
  for (const id of Object.keys(SCORING)) {
   const node = document.querySelector('#' + id);
   if (node !== null) node.addEventListener('click', () => {if (active(id) === true) send('score_delta', SCORING[id]);});
  }
  const start = document.querySelector('#start');
  if (start !== null) start.addEventListener('click', () => {if (active('start') === true) send('set_running', {running: state.status === 'running' ? false : true});});
  const restart = document.querySelector('#restart');
  if (restart !== null) restart.addEventListener('click', () => {if (active('restart') === true) send('reset');});
  // Selecting a winner or a method only repaints: it never emits.
  panel.winner.addEventListener('change', () => paintFinish());
  panel.method.addEventListener('change', () => paintFinish());
  // Explicit two-step finalization: arming never emits, confirming does.
  panel.open.addEventListener('click', () => {
   if (panel.winner.value === '' || panel.method.value === '') {panel.ask.textContent = 'Selecciona ganador y método'; panel.ask.style.display = ''; return;}
   armed = true;
   panel.ask.textContent = '¿Finalizar como ganador ' + selectedName() + ' por ' + methodLabel(panel.method.value) + '?';
   paintFinish();
  });
  panel.cancel.addEventListener('click', () => {armed = false; panel.ask.textContent = ''; paintFinish();});
  panel.confirm.addEventListener('click', () => {
   if (armed !== true) return;
   const winner = Number(panel.winner.value);
   if (Number.isSafeInteger(winner) === false || METHODS.includes(panel.method.value) === false) return;
   send('finish', {winner_team_id: winner, method: panel.method.value});
   armed = false;
   panel.ask.textContent = '';
   paintFinish();
  });
  // Releasing the tatami is its own two-step action, never a side effect of a
  // finish and never available while the result is still open.
  clearPanel.open.addEventListener('click', () => {
   if (state === null || state.status !== 'finished') return;
   clearArmed = true;
   paintClear();
  });
  clearPanel.cancel.addEventListener('click', () => {clearArmed = false; paintClear();});
  clearPanel.confirm.addEventListener('click', () => {
   if (clearArmed !== true || state === null || state.status !== 'finished') return;
   send('clear_match', {});
   clearArmed = false;
   paintClear();
  });
  // Cancelling a mistaken assignment is a separate two-step action, offered only
  // on an untouched ready match: it is never the post-finish release.
  cancelPanel.open.addEventListener('click', () => {
   if (cancelable() !== true) return;
   cancelArmed = true;
   paintCancel();
  });
  cancelPanel.abort.addEventListener('click', () => {
   cancelArmed = false;
   paintCancel();
  });
  cancelPanel.confirm.addEventListener('click', () => {
   if (cancelArmed !== true || cancelable() !== true) return;
   send('cancel_assignment', {});
   cancelArmed = false;
   paintCancel();
  });
}
})();

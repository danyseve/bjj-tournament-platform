'use strict';
// Read-only integrated presentation. The standalone asset is never modified.
(() => {
 const badge = document.createElement('div');
 badge.id = 'integrated-mode';
 badge.setAttribute('role', 'status');
 badge.style.cssText = 'position:fixed;top:0;left:0;z-index:1000;background:#222;color:#fff;padding:4px 8px;font:14px sans-serif';
 document.body.appendChild(badge);
 let session = null;
 let revision = -1;
 function waiting() {
  session = null;
  revision = -1;
  document.querySelectorAll('.fighter-1-score,.fighter-2-score,.fighter-1-adv,.fighter-2-adv,.fighter-1-penal,.fighter-2-penal').forEach(node => {node.textContent = '0';});
  document.querySelectorAll('.points-score').forEach(node => {node.textContent = '—';});
  badge.textContent = 'Integrated · Waiting for assignment · Read-only';
  document.querySelectorAll('input[id^="fighter-"]').forEach(input => {input.value = ''; input.placeholder = '';});
  document.querySelectorAll('.timer').forEach(node => {node.textContent = '--:--';});
 }
 document.querySelectorAll('input,button,#start,#restart,[id^="add"],[id^="sub"]').forEach(control => {
  control.setAttribute('aria-disabled', 'true');
  control.setAttribute('tabindex', '-1');
  control.setAttribute('disabled', '');
  control.style.pointerEvents = 'none';
  control.style.opacity = '0.5';
 });
 waiting();

 const socket = io();
 socket.on('tatami:state', state => {
  if (!state) {waiting(); return;}
  if (state.session_id !== session) {
   session = state.session_id;
   revision = -1;
   document.querySelectorAll('.points-score').forEach(node => {node.textContent = '—';});
  }
  if (state.revision <= revision) return;
  revision = state.revision;
  badge.textContent = 'Integrated · ' + state.status + ' · Read-only';
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
 });
})();

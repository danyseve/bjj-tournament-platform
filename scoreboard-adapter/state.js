'use strict';
const {isDeepStrictEqual} = require('node:util');
const {randomUUID} = require('node:crypto');
function exact(value, keys) {
 return value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
const positive = value => Number.isSafeInteger(value) && value > 0;
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
function createStore() {
 let active = null;
 let assignment = null;
 return {
  snapshot: () => structuredClone(active),
  assign(payload) {
   if (!valid(payload)) return {status: 400};
   if (assignment && isDeepStrictEqual(assignment, payload)) return {status: 200, state: structuredClone(active)};
   if (assignment) return {status: 409};
   assignment = structuredClone(payload);
   active = {...structuredClone(payload),
    fighter_a: {...payload.fighter_a, points: 0, advantages: 0, penalties: 0},
    fighter_b: {...payload.fighter_b, points: 0, advantages: 0, penalties: 0},
    remaining_seconds: payload.duration_seconds, status: 'ready', winner_team_id: null,
    method: null, session_id: randomUUID(), revision: 1};
   return {status: 201, state: structuredClone(active)};
  }
 };
}
module.exports = {createStore};

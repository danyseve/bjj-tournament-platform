'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const TOKEN='synthetic-internal-token';
process.env.SCOREBOARD_INTERNAL_TOKEN=TOKEN;
const fixture=()=>({tournament_id:7,match_id:40,tatami_id:1,fighter_a:{stage_item_input_id:1,team_id:101,name:'Ana',club:null},fighter_b:{stage_item_input_id:2,team_id:102,name:'Bea',club:null},category:{stage_item_id:9,name:'Adult'},duration_seconds:300});
const store=()=>require('../state').createStore();
test('01 empty state is explicit null',()=>{assert.equal(store().snapshot(),null);});
test('02 assignment initializes exact ready snapshot',()=>{
 const s=store(),p=fixture(),r=s.assign(p); assert.equal(r.status,201);
 const a=s.snapshot(); assert.match(a.session_id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
 assert.deepEqual(a,{...p,fighter_a:{...p.fighter_a,points:0,advantages:0,penalties:0},fighter_b:{...p.fighter_b,points:0,advantages:0,penalties:0},remaining_seconds:300,status:'ready',winner_team_id:null,method:null,session_id:a.session_id,revision:1});
 assert.deepEqual(r.state,a);assert.notEqual(store().assign(fixture()).state.session_id,a.session_id);
});
test('03 snapshots and accepted payload are deep copies',()=>{
 const s=store(),p=fixture(),r=s.assign(p);p.category.name='Changed';r.state.fighter_a.points=10;
 const first=s.snapshot();first.fighter_b.penalties=8;assert.equal(s.snapshot().category.name,'Adult');
 assert.equal(s.snapshot().fighter_a.points,0);assert.equal(s.snapshot().fighter_b.penalties,0);
});
test('04 reordered replay preserves session and mutated internal state without reset',()=>{
 // Test-only vm instrumentation: no runtime mutation API or export.
 const vm=require('node:vm'); const source=fs.readFileSync(path.join(__dirname,'../state.js'),'utf8').replace('snapshot: () =>','_mutateForTest: fn => fn(active), snapshot: () =>');
 const box={require,module:{exports:{}},structuredClone};vm.runInNewContext(source,box);
 const s=box.module.exports.createStore(),p=fixture();s.assign(p);
 s._mutateForTest(a=>{a.fighter_a.points=4;a.remaining_seconds=123;a.status='paused';a.revision=8;});
 const before=s.snapshot(),reorder=o=>Object.fromEntries(Object.entries(o).reverse().map(([k,v])=>[k,v&&typeof v==='object'?reorder(v):v]));
 const r=s.assign(reorder(p));assert.equal(r.status,200);assert.equal(JSON.stringify(r.state),JSON.stringify(before));
});
test('05 altered same-match assignment conflicts without changing state',()=>{
 const s=store();s.assign(fixture());const before=s.snapshot(),p=fixture();p.duration_seconds=301;
 assert.equal(s.assign(p).status,409);assert.deepEqual(s.snapshot(),before);
});
test('06 other-match assignment conflicts without replacing active match',()=>{
 const s=store();s.assign(fixture());const before=s.snapshot(),p=fixture();p.match_id=41;
 assert.equal(s.assign(p).status,409);assert.deepEqual(s.snapshot(),before);
});
test('07 exact fields required, unknown keys and nonobjects rejected at every level',()=>{
 for(const level of ['', 'fighter_a','fighter_b','category']) {
  const p=fixture(),obj=level?p[level]:p;
  for(const key of Object.keys(obj)) {const bad=structuredClone(p);delete (level?bad[level]:bad)[key];assert.equal(store().assign(bad).status,400);}
  obj.extra=1;assert.equal(store().assign(p).status,400);
 }
 for(const value of [null,[],true,'x',42]) {assert.equal(store().assign(value).status,400);for(const level of ['fighter_a','fighter_b','category']){const p=fixture();p[level]=value;assert.equal(store().assign(p).status,400);}}
});
test('08 all identifiers require positive safe integer numbers',()=>{
 for(const field of ['tournament_id','match_id','fighter_a.stage_item_input_id','fighter_b.stage_item_input_id','fighter_a.team_id','fighter_b.team_id','category.stage_item_id']) {
  for(const v of [true,false,'1',0,-1,1.5,Number.MAX_SAFE_INTEGER+1,NaN,Infinity,null]) {
   const p=fixture(),parts=field.split('.');if(parts.length===1)p[field]=v;else p[parts[0]][parts[1]]=v;
   assert.equal(store().assign(p).status,400,field+': '+v);
  }
 }
});
test('09 tatami must be literal integer 1',()=>{
 for(const v of [true,'1',2,0,null,1.5]){const p=fixture();p.tatami_id=v;assert.equal(store().assign(p).status,400);}
});
test('10 inputs and teams must both be distinct',()=>{
 for(const key of ['team_id','stage_item_input_id']){const p=fixture();p.fighter_b[key]=p.fighter_a[key];assert.equal(store().assign(p).status,400);}
});
test('11 duration is positive safe integer, names strings, clubs null',()=>{
 for(const v of [true,'300',0,-1,1.5,Number.MAX_SAFE_INTEGER+1,null]){const p=fixture();p.duration_seconds=v;assert.equal(store().assign(p).status,400);}
 for(const level of ['fighter_a','fighter_b','category'])for(const v of [null,1,true,{}]){const p=fixture();p[level].name=v;assert.equal(store().assign(p).status,400);}
 for(const level of ['fighter_a','fighter_b'])for(const v of ['',1,true,{}]){const p=fixture();p[level].club=v;assert.equal(store().assign(p).status,400);}
});
const legacyRoot=path.resolve(__dirname,'../../services/scoreboard');
async function running(t) {
 const a=require('../integrated').createServer(legacyRoot);await new Promise(r=>a.server.listen(0,'127.0.0.1',r));
 t.after(()=>new Promise(r=>a.io.close(r)));return {...a,url:'http://127.0.0.1:'+a.server.address().port};
}
const auth=(extra={})=>({'x-internal-token':TOKEN,...extra});
const putAssignment=(url,p)=>fetch(url+'/internal/tatamis/1/assignment',{method:'PUT',headers:auth({'content-type':'application/json'}),body:JSON.stringify(p)});
const putAssignmentNoToken=(url,p)=>fetch(url+'/internal/tatamis/1/assignment',{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify(p)});
test('12 integrated HTTP assignment/state, errors, and legacy routes',async t=>{
 const {url}=await running(t);assert.deepEqual(await (await fetch(url+'/internal/tatamis/1/state',{headers:auth()})).json(),{state:null});
 for(const route of ['/','/control','/control2','/js/main.js','/socket.io/socket.io.js'])assert.equal((await fetch(url+route)).status,200,route);
 assert.equal((await putAssignment(url,{...fixture(),extra:1})).status,400);
 const malformed=await fetch(url+'/internal/tatamis/1/assignment',{method:'PUT',headers:{'content-type':'application/json'},body:'{'});assert.equal(malformed.status,400);
 const r=await putAssignment(url,fixture());assert.equal(r.status,201);const body=await r.json();
 assert.deepEqual(await (await fetch(url+'/internal/tatamis/1/state',{headers:auth()})).json(),body);
 assert.equal((await putAssignment(url,fixture())).status,200);
 assert.equal((await putAssignment(url,{...fixture(),duration_seconds:400})).status,409);
 assert.equal((await putAssignment(url,{...fixture(),match_id:41})).status,409);
 assert.equal((await fetch(url+'/internal/tatamis/2/state')).status,404);
});
async function connect(url) {
 const open=await (await fetch(url+'/socket.io/?EIO=4&transport=polling')).text();assert.equal(open[0],'0');const sid=JSON.parse(open.slice(1)).sid;
 const endpoint=url+'/socket.io/?EIO=4&transport=polling&sid='+sid;
 assert.equal((await fetch(endpoint,{method:'POST',body:'40'})).status,200);
 return {poll:async()=> (await (await fetch(endpoint,{signal:AbortSignal.timeout(1000)})).text()).split('\x1e'),send:async(event,data)=>fetch(endpoint,{method:'POST',body:'42'+JSON.stringify([event,data])}),close:async()=>fetch(endpoint,{method:'POST',body:'41'})};
}
const events=packets=>packets.filter(p=>p.startsWith('42')).map(p=>JSON.parse(p.slice(2)));
test('13 connection snapshot and both accepted and idempotent assignment emit tatami:state only',async t=>{
 const {url}=await running(t),a=await connect(url);const initial=await a.poll();assert.equal(events(initial).length,0);
 await putAssignment(url,fixture());const state=await (await fetch(url+'/internal/tatamis/1/state',{headers:auth()})).json();
 assert.deepEqual(events(await a.poll()),[['tatami:state',state.state]]);
 assert.equal((await putAssignment(url,{...fixture(),duration_seconds:301})).status,409);
 assert.equal((await putAssignment(url,{...fixture(),extra:true})).status,400);
 await putAssignment(url,fixture());assert.deepEqual(events(await a.poll()),[['tatami:state',state.state]]);
 const b=await connect(url);assert.deepEqual(events(await b.poll()),[['tatami:state',state.state]]);
 await a.close();await b.close();
});
test('14 exact legacy four relays: three include sender, name excludes sender; no state mutation/update',async t=>{
 const {url}=await running(t);await putAssignment(url,fixture());const before=await (await fetch(url+'/internal/tatamis/1/state',{headers:auth()})).json();
 const a=await connect(url),b=await connect(url);await a.poll();await b.poll();
 for(const event of ['bjj:score','bjj:start','bjj:restart']) {
  const payload={nested:{x:event},score:99};await a.send(event,payload);
  assert.deepEqual(events(await a.poll()),[[event,payload]]);assert.deepEqual(events(await b.poll()),[[event,payload]]);
 }
 await a.send('bjj:name',{name:'Synthetic'});assert.deepEqual(events(await b.poll()),[['bjj:name',{name:'Synthetic'}]]);
 await assert.rejects(a.poll(),e=>e.name==='TimeoutError');
 assert.deepEqual(await (await fetch(url+'/internal/tatamis/1/state',{headers:auth()})).json(),before);
 await b.close();
});
test('15 default standalone launcher starts unchanged legacy app; integrated is explicit',async t=>{
 const {spawn}=require('node:child_process'),net=require('node:net');
 for(const mode of [undefined,'integrated']) {
  const probe=net.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;await new Promise(r=>probe.close(r));
  const env={...process.env,PORT:String(port)};delete env.SCOREBOARD_MODE;if(mode)env.SCOREBOARD_MODE=mode;
  const child=spawn(process.execPath,['-e',`require(${JSON.stringify(path.resolve(__dirname,'../launcher'))}).start(${JSON.stringify(legacyRoot)})`],{env,stdio:'ignore'});
  const stopped=new Promise(r=>child.once('exit',r));t.after(async()=>{if(child.exitCode===null)child.kill();await stopped;});
  const url='http://127.0.0.1:'+port;let ready=false;
  for(let i=0;i<60;i++){try{if((await fetch(url+'/')).status===200){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,25));}
  assert.equal(ready,true,'launcher mode '+mode+' must listen');
  assert.equal((await fetch(url+'/control')).status,200);assert.equal((await fetch(url+'/control2')).status,200);
  assert.equal((await fetch(url+'/internal/tatamis/1/state',{headers:auth()})).status,mode?200:404);
  if(!mode)assert.equal((await putAssignment(url,fixture())).status,404);
  child.kill();await stopped;
 }
});

test('16 internal endpoints reject a missing token with 401',async t=>{
 const {url}=await running(t);
 assert.equal((await fetch(url+'/internal/tatamis/1/state')).status,401);
 assert.equal((await fetch(url+'/internal/tatamis/1/state',{headers:{'x-internal-token':''}})).status,401);
 assert.equal((await putAssignmentNoToken(url,fixture())).status,401);
});

test('17 internal endpoints reject a wrong token with 401',async t=>{
 const {url}=await running(t);
 for(const bad of ['synthetic-internal-tokeX','short','',TOKEN+'x']) {
  assert.equal((await fetch(url+'/internal/tatamis/1/state',{headers:{'x-internal-token':bad}})).status,401,bad);
  assert.equal((await fetch(url+'/internal/tatamis/1/assignment',{method:'PUT',headers:{'x-internal-token':bad,'content-type':'application/json'},body:JSON.stringify(fixture())})).status,401,bad);
 }
 assert.deepEqual(await (await fetch(url+'/internal/tatamis/1/state',{headers:{'x-internal-token':TOKEN}})).json(),{state:null});
});

test('18 correct token is accepted while the browser receives tatami:state without any token',async t=>{
 const {url}=await running(t);
 assert.equal((await putAssignment(url,fixture())).status,201);
 const state=await (await fetch(url+'/internal/tatamis/1/state',{headers:{'x-internal-token':TOKEN}})).json();
 for(const route of ['/','/control','/control2','/js/main.js'])assert.equal((await fetch(url+route)).status,200,route);
 const a=await connect(url);
 assert.deepEqual(events(await a.poll()),[['tatami:state',state.state]]);
 await a.close();
});

'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const legacyRoot=path.resolve(__dirname,'../../services/scoreboard');
async function running(t) {
 const a=require('../integrated').createServer(legacyRoot);
 await new Promise(r=>a.server.listen(0,'127.0.0.1',r));
 t.after(()=>new Promise(r=>a.io.close(r)));
 return {...a,url:'http://127.0.0.1:'+a.server.address().port};
}
async function page(url,route='/') {
 const html=await (await fetch(url+route)).text();
 const code=await (await fetch(url+'/js/main.js')).text();
 return harness(html,code);
}
function harness(html,code) {
 const dom=new JSDOM(html,{runScripts:'outside-only'}),w=dom.window;
 const handlers={},emits=[],timers=[],registrations=[];
 w.io=()=>({on:(event,fn)=>{handlers[event]=fn;return this;},emit:(...args)=>emits.push(args)});
 for(const key of ['setTimeout','setInterval'])w[key]=(...args)=>timers.push([key,...args]);
 const original=w.EventTarget.prototype.addEventListener;
 w.EventTarget.prototype.addEventListener=function(event,...args){registrations.push([event,this.id]);return original.call(this,event,...args);};
 // Legacy asset must execute too: supply its actual jQuery, not a stub.
 if(code.includes('const App ='))w.eval(fs.readFileSync(path.join(legacyRoot,'public/js/jquery-3.3.1.slim.min.js'),'utf8'));
 timers.length=0;registrations.length=0;
 w.eval(code);
 w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
 return {dom,w,doc:w.document,handlers,emits,timers,registrations,code};
}
const snapshot=(extra={})=>({session_id:'synthetic-session-a',revision:1,duration_seconds:305,remaining_seconds:305,status:'ready',fighter_a:{name:'Synthetic <Ana>',points:4,advantages:2,penalties:1},fighter_b:{name:'Synthetic Bea',points:7,advantages:1,penalties:3},...extra});
function presentation(p) {
 return {names:[1,2].map(i=>p.doc.querySelector('#fighter-'+i+'-name').value),time:p.doc.querySelector('.timer').textContent,scores:[1,2].map(i=>['score','adv','penal'].map(k=>p.doc.querySelector('.fighter-'+i+'-'+k).textContent)),mode:p.doc.querySelector('#integrated-mode')?.textContent};
}

test('UI01 integrated overlay uses real markup and waits without invented names on all three routes',async t=>{
 const {url}=await running(t);
 for(const route of ['/','/control','/control2']) {
  const p=await page(url,route);
  assert.match(presentation(p).mode || '',/Integrated/);
  assert.deepEqual(presentation(p).names,['','']);
  assert.equal(presentation(p).time,'--:--');
  assert.match(presentation(p).mode,/Waiting/);
  assert.equal(typeof p.handlers['tatami:state'],'function');
  const scripts=[...p.doc.scripts];assert.equal(scripts.filter(s=>s.getAttribute('src')==='/js/main.js').length,1);
  assert.equal(scripts.filter(s=>!s.src && s.textContent.trim()).length,0,'no inline legacy init');
 }
});

test('UI02 snapshots replace names, seconds mm:ss, points advantages penalties on every route',async t=>{
 const {url}=await running(t);
 for(const route of ['/','/control','/control2']) {
  const p=await page(url,route);p.handlers['tatami:state'](snapshot());
  assert.deepEqual(presentation(p).names,['Synthetic <Ana>','Synthetic Bea']);
  assert.equal(presentation(p).time,'05:05');
  assert.deepEqual(presentation(p).scores,[['4','2','1'],['7','1','3']]);
  assert.match(presentation(p).mode,/ready/);
  p.handlers['tatami:state'](snapshot({revision:2,remaining_seconds:59,status:'paused'}));
  assert.equal(presentation(p).time,'00:59');
  assert.match(presentation(p).mode,/paused/);
 }
});

test('UI03 newer revision replaces and older/equal same-session snapshots cannot regress presentation',async t=>{
 const {url}=await running(t),p=await page(url);
 p.handlers['tatami:state'](snapshot({revision:5,remaining_seconds:123}));
 const before=presentation(p);
 for(const revision of [4,5])p.handlers['tatami:state'](snapshot({revision,remaining_seconds:999}));
 assert.deepEqual(presentation(p),before);
 p.handlers['tatami:state'](snapshot({revision:6,remaining_seconds:62}));
 assert.equal(presentation(p).time,'01:02');
});

test('UI04 a new session resets all presentation even with a lower revision',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state'](snapshot({revision:9,remaining_seconds:1}));
 p.doc.querySelectorAll('.points-score').forEach(n=>n.textContent='99');
 const fresh=snapshot({session_id:'synthetic-session-b',revision:1,remaining_seconds:420,fighter_a:{name:'New A',points:0,advantages:0,penalties:0},fighter_b:{name:'New B',points:0,advantages:0,penalties:0}});
 p.handlers['tatami:state'](fresh);
 assert.deepEqual(presentation(p).names,['New A','New B']);
 assert.equal(presentation(p).time,'07:00');
 assert.deepEqual(presentation(p).scores,[['0','0','0'],['0','0','0']]);
 assert.ok([...p.doc.querySelectorAll('.points-score')].every(n=>n.textContent==='—'),'per-technique breakdown is not supplied by snapshot');
});

test('UI05 legacy editing scoring duration start restart controls are disabled, including icon controls',async t=>{
 const {url}=await running(t);
 for(const route of ['/','/control','/control2']) {
  const p=await page(url,route);
  for(const n of p.doc.querySelectorAll('input,button,#start,#restart,[id^="add"],[id^="sub"]')) {
   assert.equal(n.getAttribute('aria-disabled'),'true',route+' '+n.id);
   assert.equal(n.getAttribute('tabindex'),'-1');
   if(n.matches('input,button'))assert.equal(n.disabled,true);
   n.dispatchEvent(new p.w.Event('click',{bubbles:true}));n.dispatchEvent(new p.w.Event('keyup',{bubbles:true}));
  }
  assert.deepEqual(p.emits,[]);
  assert.ok(!p.registrations.some(([event])=>['click','keyup','keydown','change'].includes(event)));
 }
});

test('UI06 explicit empty snapshot clears presentation and revision tracking',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state'](snapshot({revision:9}));
 p.handlers['tatami:state'](null);
 assert.deepEqual(presentation(p).scores,[['0','0','0'],['0','0','0']]);
 assert.deepEqual(presentation(p).names,['','']);
 assert.equal(presentation(p).time,'--:--');
 p.handlers['tatami:state'](snapshot({revision:1,remaining_seconds:60}));
 assert.equal(presentation(p).time,'01:00');
});

test('UI07 snapshot presentation creates no countdown timers and never autoruns',async t=>{
 const {url}=await running(t),p=await page(url,'/control2');
 p.handlers['tatami:state'](snapshot({status:'running',remaining_seconds:125}));
 assert.deepEqual(p.timers,[]);assert.equal(presentation(p).time,'02:05');
 assert.ok(!/set(?:Timeout|Interval)|new Timer|startTimer/.test(p.code));
});
test('UI08 only tatami:state is registered; no legacy listeners or outbound events',async t=>{
 const {url}=await running(t);
 for(const route of ['/','/control','/control2']) {
  const p=await page(url,route);p.handlers['tatami:state'](snapshot());
  assert.deepEqual(Object.keys(p.handlers),['tatami:state']);assert.deepEqual(p.emits,[]);
  assert.ok(!/bjj:|tatami:update|socket\.emit/.test(p.code));
 }
});
const assignment=()=>({tournament_id:77,match_id:400,tatami_id:1,fighter_a:{stage_item_input_id:1,team_id:101,name:'Synthetic Ana',club:null},fighter_b:{stage_item_input_id:2,team_id:102,name:'Synthetic Bea',club:null},category:{stage_item_id:9,name:'Synthetic Adult'},duration_seconds:305});
async function assign(url) {
 const res=await fetch(url+'/internal/tatamis/1/assignment',{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify(assignment())});assert.equal(res.status,201);return (await res.json()).state;
}
async function connectionSnapshot(url) {
 const opening=await (await fetch(url+'/socket.io/?EIO=4&transport=polling')).text();
 const sid=JSON.parse(opening.slice(1)).sid,endpoint=url+'/socket.io/?EIO=4&transport=polling&sid='+sid;
 await fetch(endpoint,{method:'POST',body:'40'});
 try {
  const packets=(await (await fetch(endpoint,{signal:AbortSignal.timeout(2000)})).text()).split('\x1e');
  const event=packets.filter(p=>p.startsWith('42')).map(p=>JSON.parse(p.slice(2))).find(p=>p[0]==='tatami:state');
  assert.ok(event,'actual socket connection snapshot');return event[1];
 } finally {await fetch(endpoint,{method:'POST',body:'41'});}
}
test('UI09 two socket reconnections per route deliver actual snapshots into existing callback',async t=>{
 const {url}=await running(t),state=await assign(url);
 for(const route of ['/','/control','/control2']) {
  const p=await page(url,route);
  for(let i=0;i<2;i++) {
   const received=await connectionSnapshot(url);assert.deepEqual(received,state);
   p.handlers['tatami:state'](received);
   assert.deepEqual(presentation(p).names,['Synthetic Ana','Synthetic Bea']);
   assert.equal(presentation(p).time,'05:05');
   assert.deepEqual(presentation(p).scores,[['0','0','0'],['0','0','0']]);
  }
 }
});
test('UI10 two full reloads per route render actual socket assignment snapshots',async t=>{
 const {url}=await running(t),state=await assign(url);
 for(const route of ['/','/control','/control2'])for(let i=0;i<2;i++) {
  const p=await page(url,route),received=await connectionSnapshot(url);assert.deepEqual(received,state);
  p.handlers['tatami:state'](received);
  assert.deepEqual(presentation(p).names,['Synthetic Ana','Synthetic Bea']);assert.equal(presentation(p).time,'05:05');
  assert.deepEqual(presentation(p).scores,[['0','0','0'],['0','0','0']]);
 }
});
test('UI11 names are literal text and zero/long second durations are exact',async t=>{
 const {url}=await running(t),p=await page(url);
 const baselineImages=p.doc.querySelectorAll('img').length;
 for(const [i,seconds,expected]of [[1,0,'00:00'],[2,61,'01:01'],[3,3605,'60:05']]) {
  p.handlers['tatami:state'](snapshot({revision:i,remaining_seconds:seconds,fighter_a:{name:'<img src=x onerror=alert(1)>',points:0,advantages:0,penalties:0}}));
  assert.equal(presentation(p).time,expected);assert.equal(presentation(p).names[0],'<img src=x onerror=alert(1)>');
  assert.equal(p.doc.querySelectorAll('img').length,baselineImages,'malicious name must not add <img> elements');
  assert.ok(![...p.doc.querySelectorAll('img')].some(n=>n.getAttribute('src')==='x'||n.hasAttribute('onerror')),'no injected <img> from snapshot');
 }
});
test('UI12 default standalone serves original main JS and all legacy assets byte-for-byte',async t=>{
 const {spawn}=require('node:child_process'),net=require('node:net');
 const probe=net.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;await new Promise(r=>probe.close(r));
 const env={...process.env,PORT:String(port)};delete env.SCOREBOARD_MODE;
 const child=spawn(process.execPath,['-e',`require(${JSON.stringify(path.resolve(__dirname,'../launcher'))}).start(${JSON.stringify(legacyRoot)})`],{env,stdio:'ignore'});
 const stopped=new Promise(r=>child.once('exit',r));t.after(async()=>{if(child.exitCode===null)child.kill();await stopped;});
 const url='http://127.0.0.1:'+port;
 for(let i=0;i<60;i++){try{if((await fetch(url+'/')).status===200)break;}catch{}await new Promise(r=>setTimeout(r,25));}
 for(const relative of ['js/main.js','js/jquery-3.3.1.slim.min.js','js/popper.min.js','js/bootstrap.min.js','css/all.css','css/bootstrap.min.css','css/scoreboard.css','css/control.css','css/scoreboard-control.css']) {
  const res=await fetch(url+'/'+relative);assert.equal(res.status,200);
  assert.deepEqual(Buffer.from(await res.arrayBuffer()),fs.readFileSync(path.join(legacyRoot,'public',relative)));
 }
 child.kill();await stopped;
});

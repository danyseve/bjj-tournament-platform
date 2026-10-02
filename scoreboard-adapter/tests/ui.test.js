'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const TOKEN='synthetic-internal-token';
process.env.SCOREBOARD_INTERNAL_TOKEN=TOKEN;
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
const snapshot=(extra={})=>({session_id:'synthetic-session-a',revision:1,tatami_id:1,match_id:400,duration_seconds:305,remaining_seconds:305,status:'ready',fighter_a:{name:'Synthetic <Ana>',points:4,advantages:2,penalties:1},fighter_b:{name:'Synthetic Bea',points:7,advantages:1,penalties:3},...extra});
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

test('UI05 la pantalla / es solo lectura con combate activo: bloquea todo y no emite nada',async t=>{
 const {url}=await running(t),p=await page(url,'/');
 p.handlers['tatami:state'](snapshot());
 for(const n of p.doc.querySelectorAll('input,button,#start,#restart,[id^="add"],[id^="sub"]')) {
  assert.equal(n.getAttribute('aria-disabled'),'true','/'+' '+n.id);
  assert.equal(n.getAttribute('tabindex'),'-1');
  if(n.matches('input,button'))assert.equal(n.disabled,true);
  n.dispatchEvent(new p.w.Event('click',{bubbles:true}));n.dispatchEvent(new p.w.Event('keyup',{bubbles:true}));
 }
 assert.deepEqual(p.emits,[]);
 assert.ok(!p.registrations.some(([event])=>['click','keyup','keydown','change'].includes(event)));
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
test('UI08 la pantalla / solo se suscribe a tatami:state y el cliente integrado no usa bjj:*',async t=>{
 const {url}=await running(t),p=await page(url,'/');
 p.handlers['tatami:state'](snapshot());
 assert.deepEqual(Object.keys(p.handlers),['tatami:state']);
 assert.deepEqual(p.emits,[]);
 assert.ok(!/bjj:/.test(p.code),'el cliente integrado no usa eventos legacy');
});
const assignment=()=>({tournament_id:77,match_id:400,tatami_id:1,fighter_a:{stage_item_input_id:1,team_id:101,name:'Synthetic Ana',club:null},fighter_b:{stage_item_input_id:2,team_id:102,name:'Synthetic Bea',club:null},category:{stage_item_id:9,name:'Synthetic Adult'},duration_seconds:305});
async function assign(url) {
 const res=await fetch(url+'/internal/tatamis/1/assignment',{method:'PUT',headers:{'content-type':'application/json','x-internal-token':TOKEN},body:JSON.stringify(assignment())});assert.equal(res.status,201);return (await res.json()).state;
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

const SCORING={add4f1:['a','points',4],sub4f1:['a','points',-4],add3f1:['a','points',3],sub3f1:['a','points',-3],add2f1:['a','points',2],sub2f1:['a','points',-2],
 addadvf1:['a','advantages',1],subadvf1:['a','advantages',-1],addpenalf1:['a','penalties',1],subpenalf1:['a','penalties',-1],
 add4f2:['b','points',4],sub4f2:['b','points',-4],add3f2:['b','points',3],sub3f2:['b','points',-3],add2f2:['b','points',2],sub2f2:['b','points',-2],
 addadvf2:['b','advantages',1],subadvf2:['b','advantages',-1],addpenalf2:['b','penalties',1],subpenalf2:['b','penalties',-1]};
const PAYLOAD_KEYS=['command_id','delta','expected_revision','field','fighter','match_id','operation','session_id','tatami_id'];
const click=(p,id)=>p.doc.querySelector('#'+id)?.dispatchEvent(new p.w.Event('click',{bubbles:true}));

test('UI13 las paginas de control emiten tatami:update canonico mapeado desde los controles legacy',async t=>{
 const {url}=await running(t);
 for(const route of ['/control','/control2']) {
  const p=await page(url,route);p.handlers['tatami:state'](snapshot());
  const present=Object.keys(SCORING).filter(id=>p.doc.querySelector('#'+id)!==null);
  assert.ok(present.length>=8,route+' expone controles de scoring');
  present.forEach(id=>click(p,id));
  assert.equal(p.emits.length,present.length,route+' un comando por clic');
  p.emits.forEach(([event,payload],index)=>{
   assert.equal(event,'tatami:update');
   assert.equal(payload.operation,'score_delta',present[index]);
   assert.equal(payload.session_id,'synthetic-session-a');
   assert.equal(payload.expected_revision,1);
   assert.equal(payload.tatami_id,1);
   assert.equal(payload.match_id,400);
   assert.equal(typeof payload.command_id,'string');
   assert.ok(payload.command_id.length>0);
   assert.deepEqual(Object.keys(payload).sort(),PAYLOAD_KEYS,present[index]+' sin campos desconocidos');
   assert.deepEqual([payload.fighter,payload.field,payload.delta],SCORING[present[index]],present[index]);
  });
  assert.equal(new Set(p.emits.map(([,payload])=>payload.command_id)).size,present.length,'command_id unico por comando');
 }
});

test('UI14 iniciar, pausar y reset usan operaciones explicitas y no toggle',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state'](snapshot({status:'ready'}));
 click(p,'start');
 p.handlers['tatami:state'](snapshot({revision:2,status:'running',remaining_seconds:300}));
 click(p,'start');
 click(p,'restart');
 assert.deepEqual(p.emits.map(([event,payload])=>[event,payload.operation,payload.running===undefined?null:payload.running]),
  [['tatami:update','set_running',true],['tatami:update','set_running',false],['tatami:update','reset',null]]);
 assert.deepEqual(Object.keys(p.emits[2][1]).sort(),['command_id','expected_revision','match_id','operation','session_id','tatami_id']);
 assert.equal(p.emits[1][1].expected_revision,2,'la revision esperada sigue al ultimo snapshot del servidor');
});

test('UI15 sin sesion no se emite y los controles sin operacion canonica siguen bloqueados',async t=>{
 const {url}=await running(t);
 for(const route of ['/control','/control2']) {
  const p=await page(url,route);
  for(const id of ['add4f1','add2f2','start','restart'])click(p,id);
  assert.deepEqual(p.emits,[],route+' sin snapshot no emite comandos');
  p.handlers['tatami:state'](snapshot());
  for(const id of ['addmin','submin','fighter-1-name','fighter-2-name']) {
   const n=p.doc.querySelector('#'+id);if(n===null)continue;
   assert.equal(n.getAttribute('aria-disabled'),'true',route+' '+id);
   if(n.matches('input,button'))assert.equal(n.disabled,true);
   n.dispatchEvent(new p.w.Event('click',{bubbles:true}));n.dispatchEvent(new p.w.Event('keyup',{bubbles:true}));
  }
  assert.deepEqual(p.emits,[],route+' los controles sin operacion no emiten');
  for(const id of ['add4f1','start','restart']) {
   const n=p.doc.querySelector('#'+id);if(n===null)continue;
   assert.notEqual(n.getAttribute('aria-disabled'),'true',route+' '+id+' habilitado con sesion');
   assert.ok(!n.disabled,route+' '+id+' habilitado con sesion');
  }
 }
});

test('UI16 el control refleja el status del servidor y no admite retrocesos',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state'](snapshot({status:'running',remaining_seconds:120}));
 assert.equal(presentation(p).time,'02:00');
 assert.match(p.doc.querySelector('#start').getAttribute('class')||'',/pause/);
 p.handlers['tatami:state'](snapshot({revision:3,status:'paused',remaining_seconds:120}));
 assert.match(p.doc.querySelector('#start').getAttribute('class')||'',/play/);
 p.handlers['tatami:state'](snapshot({revision:2,status:'running',remaining_seconds:300}));
 assert.equal(presentation(p).time,'02:00','un snapshot antiguo no reanuda la presentacion');
 assert.equal(presentation(p).mode.includes('paused'),true);
});

const select=(p,id,value)=>{const n=p.doc.querySelector('#'+id);n.value=value;n.dispatchEvent(new p.w.Event('change',{bubbles:true}));};
const sides=(a={},b={})=>snapshot({fighter_a:{name:'Ana',team_id:101,points:0,advantages:0,penalties:0,...a},
 fighter_b:{name:'Bea',team_id:102,points:0,advantages:0,penalties:0,...b}});
const armed=p=>p.doc.querySelector('#finish-confirm').style.display!=='none';

test('UI17 las paginas de control ofrecen ganador y metodo y la pantalla / no construye el panel',async t=>{
 const {url}=await running(t);
 for(const route of ['/control','/control2']) {
  const p=await page(url,route);
  assert.ok(p.doc.querySelector('#integrated-finish'),route+' construye el panel de finalizacion');
  const winner=p.doc.querySelector('#finish-winner'),method=p.doc.querySelector('#finish-method');
  assert.deepEqual([...method.options].slice(1).map(o=>o.value),require('../state').METHODS,route+' enum completo de metodos');
  assert.equal(method.options[0].value,'','sin metodo por defecto');
  assert.equal(p.doc.querySelector('#finish-open').disabled,true,route+' sin sesion no se puede finalizar');
  assert.equal(winner.options.length,1,'sin sesion no hay luchadores');
  p.handlers['tatami:state'](sides());
  assert.deepEqual([...winner.options].slice(1).map(o=>o.value),['101','102']);
  assert.match(winner.options[1].textContent,/A · Ana/);
  assert.match(winner.options[2].textContent,/B · Bea/);
  assert.equal(p.doc.querySelector('#finish-open').disabled,true,'sin ganador ni metodo no se puede armar');
  select(p,'finish-winner','101');select(p,'finish-method','decision');
  assert.equal(p.doc.querySelector('#finish-open').disabled,false);
  assert.equal(armed(p),false,'armado solo tras pulsar finalizar');
 }
 const read=await page(url,'/');
 assert.equal(read.doc.querySelector('#integrated-finish'),null,'/ no construye el panel');
 assert.equal(read.doc.querySelector('#finish-open'),null);
});

test('UI18 finalizar exige confirmacion explicita y emite un unico comando canonico',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state'](sides());
 click(p,'finish-open');
 assert.deepEqual(p.emits,[],'sin ganador ni metodo no se emite nada');
 assert.equal(armed(p),false);
 select(p,'finish-winner','102');select(p,'finish-method','submission');
 click(p,'finish-open');
 assert.deepEqual(p.emits,[],'armar nunca emite');
 assert.equal(armed(p),true);
 assert.match(p.doc.querySelector('#finish-ask').textContent,/Bea/);
 assert.match(p.doc.querySelector('#finish-ask').textContent,/Sumisión/);
 click(p,'finish-cancel');
 assert.deepEqual(p.emits,[]);assert.equal(armed(p),false,'cancelar desarma sin emitir');
 click(p,'finish-open');click(p,'finish-confirm');
 assert.equal(p.emits.length,1,'un unico comando al confirmar');
 const [event,payload]=p.emits[0];
 assert.equal(event,'tatami:update');assert.equal(payload.operation,'finish');
 assert.equal(payload.winner_team_id,102);assert.equal(payload.method,'submission');
 assert.equal(payload.session_id,'synthetic-session-a');assert.equal(payload.expected_revision,1);
 assert.equal(payload.tatami_id,1);assert.equal(payload.match_id,400);
 assert.deepEqual(Object.keys(payload).sort(),['command_id','expected_revision','match_id','method','operation','session_id','tatami_id','winner_team_id'],'sin campos desconocidos');
 click(p,'finish-confirm');
 assert.equal(p.emits.length,1,'un segundo clic no reemite');
});

test('UI19 tras finalizar los controles de mutacion quedan bloqueados y no emiten',async t=>{
 const {url}=await running(t);
 for(const route of ['/control','/control2']) {
  const p=await page(url,route);
  p.handlers['tatami:state'](sides({points:4},{points:2}));
  for(const id of ['add4f1','add2f2','start','restart'])assert.equal(p.doc.querySelector('#'+id).disabled,false,route+' '+id+' habilitado con combate vivo');
  p.handlers['tatami:state']({...sides({points:4},{points:2}),revision:7,status:'finished',remaining_seconds:298,winner_team_id:101,method:'points'});
  for(const id of ['add4f1','sub2f1','addadvf2','start','restart']) {
   const n=p.doc.querySelector('#'+id);if(n===null)continue;
   // Los controles de icono son <i>: el bloqueo efectivo es aria-disabled.
   if(n.matches('input,button'))assert.equal(n.disabled,true,route+' '+id+' bloqueado tras finalizar');
   assert.equal(n.getAttribute('aria-disabled'),'true',route+' '+id);
  }
  assert.equal(p.doc.querySelector('#finish-open').disabled,true);
  assert.equal(p.doc.querySelector('#finish-winner').disabled,true);
  assert.equal(p.doc.querySelector('#finish-method').disabled,true);
  assert.match(p.doc.querySelector('#finish-ask').textContent,/Finalizado/);
  assert.match(p.doc.querySelector('#finish-ask').textContent,/Ana/);
  assert.match(p.doc.querySelector('#finish-ask').textContent,/Puntos/);
  assert.match(p.doc.querySelector('#integrated-result').textContent,/Finalizado/);
  assert.equal(presentation(p).time,'04:58');
  assert.match(presentation(p).mode,/finished/);
  p.emits.length=0;
  for(const id of ['add4f1','add2f2','start','restart'])click(p,id);
  assert.deepEqual(p.emits,[],route+' ninguna mutacion tras finalizar');
 }
});

test('UI20 la pantalla / refleja el resultado final y sigue siendo solo lectura',async t=>{
 const {url}=await running(t),p=await page(url,'/');
 assert.equal(p.doc.querySelector('#integrated-finish'),null);
 p.handlers['tatami:state']({...sides({points:2},{points:4,advantages:1}),revision:5,status:'finished',remaining_seconds:0,winner_team_id:102,method:'submission'});
 const banner=p.doc.querySelector('#integrated-result');
 assert.match(banner.textContent,/Finalizado/);assert.match(banner.textContent,/Bea/);assert.match(banner.textContent,/Sumisión/);
 assert.deepEqual(presentation(p).names,['Ana','Bea']);
 assert.equal(presentation(p).time,'00:00');
 assert.match(presentation(p).mode,/finished/);
 for(const n of p.doc.querySelectorAll('input,button,#start,#restart,[id^="add"],[id^="sub"]')) {
  assert.equal(n.getAttribute('aria-disabled'),'true');
  assert.equal(n.getAttribute('tabindex'),'-1');
  if(n.matches('input,button'))assert.equal(n.disabled,true);
  n.dispatchEvent(new p.w.Event('click',{bubbles:true}));
 }
 assert.deepEqual(p.emits,[]);
 p.handlers['tatami:state']({...sides(),revision:9,status:'running',remaining_seconds:200});
 assert.match(presentation(p).mode,/finished/,'un snapshot posterior no resucita el combate');
 assert.match(p.doc.querySelector('#integrated-result').textContent,/Finalizado/);
 p.handlers['tatami:state']({...sides({name:'New A'},{name:'New B'}),session_id:'synthetic-session-b',revision:1,status:'ready',remaining_seconds:300});
 assert.equal(p.doc.querySelector('#integrated-result').textContent,'','una sesion nueva limpia el resultado');
 assert.equal(presentation(p).time,'05:00');
});

test('UI21 con el tiempo agotado la UI bloquea scoring y reloj y pide el resultado',async t=>{
 const {url}=await running(t);
 for(const route of ['/control','/control2']) {
  const p=await page(url,route);
  p.handlers['tatami:state']({...sides({points:2},{points:1}),status:'running',remaining_seconds:120});
  assert.equal(p.doc.querySelector('#add4f1').disabled,false,route+' combate vivo');
  p.handlers['tatami:state']({...sides({points:2},{points:1}),status:'awaiting_result',remaining_seconds:0,revision:6});
  for(const id of ['add4f1','sub2f1','addadvf2','start','restart']) {
   const n=p.doc.querySelector('#'+id);if(n===null)continue;
   assert.equal(n.getAttribute('aria-disabled'),'true',route+' '+id);
   if(n.matches('input,button'))assert.equal(n.disabled,true,route+' '+id);
  }
  assert.equal(p.doc.querySelector('#finish-winner').disabled,false,'el panel de finalizacion sigue habilitado');
  assert.equal(p.doc.querySelector('#finish-method').disabled,false);
  assert.equal(p.doc.querySelector('#finish-ask').textContent,'Tiempo finalizado — pendiente de resultado');
  assert.equal(p.doc.querySelector('#clear-open').disabled,true,'no se libera sin cerrar el resultado');
  assert.equal(presentation(p).time,'00:00');
  assert.equal(p.doc.querySelector('#integrated-result').textContent,'Tiempo finalizado — pendiente de resultado');
  p.emits.length=0;
  for(const id of ['add4f1','start','restart'])click(p,id);
  assert.deepEqual(p.emits,[],route+' sin mutaciones con el tiempo agotado');
 }
});

test('UI22 desde pendiente la UI permite finalizar con confirmacion previa',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state']({...sides({points:2},{points:4}),status:'awaiting_result',remaining_seconds:0,revision:6});
 select(p,'finish-winner','102');select(p,'finish-method','decision');
 click(p,'finish-open');
 assert.deepEqual(p.emits,[],'armar no emite');
 assert.match(p.doc.querySelector('#finish-ask').textContent,/Bea/);
 click(p,'finish-confirm');
 assert.equal(p.emits.length,1);
 assert.equal(p.emits[0][1].operation,'finish');
 assert.equal(p.emits[0][1].winner_team_id,102);
 assert.equal(p.emits[0][1].method,'decision');
 assert.equal(p.emits[0][1].expected_revision,6);
 p.handlers['tatami:state']({...sides({points:2},{points:4}),status:'finished',revision:7,remaining_seconds:0,winner_team_id:102,method:'decision'});
 assert.match(p.doc.querySelector('#integrated-result').textContent,/Ganador: Bea/);
 assert.equal(p.doc.querySelector('#finish-open').disabled,true);
 assert.equal(p.doc.querySelector('#clear-open').disabled,false,'cerrado el resultado ya se puede liberar');
 assert.equal(p.doc.querySelector('#finish-ask').textContent,'Finalizado · Ganador: Bea · Decisión');
});

test('UI23 liberar el Tatami exige confirmacion explicita y no se combina con finish',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state']({...sides({points:4},{points:1}),status:'finished',revision:5,remaining_seconds:0,winner_team_id:101,method:'points'});
 assert.equal(p.doc.querySelector('#clear-open').disabled,false);
 p.emits.length=0;
 click(p,'clear-open');
 assert.deepEqual(p.emits,[],'el primer acto no emite');
 assert.equal(p.doc.querySelector('#clear-confirm').style.display,'');
 assert.equal(p.doc.querySelector('#finish-confirm').style.display,'none','liberar no arma la finalizacion');
 assert.match(p.doc.querySelector('#clear-ask').textContent,/perderá/);
 click(p,'clear-cancel');
 assert.deepEqual(p.emits,[]);
 assert.equal(p.doc.querySelector('#clear-confirm').style.display,'none');
 click(p,'clear-open');click(p,'clear-confirm');
 assert.equal(p.emits.length,1);
 assert.equal(p.emits[0][0],'tatami:update');
 assert.equal(p.emits[0][1].operation,'clear_match');
 assert.deepEqual(Object.keys(p.emits[0][1]).sort(),['command_id','expected_revision','match_id','operation','session_id','tatami_id']);
 assert.equal(p.emits[0][1].session_id,'synthetic-session-a');
 click(p,'clear-confirm');
 assert.equal(p.emits.length,1,'el segundo clic no reemite');
 p.handlers['tatami:state'](null);
 assert.match(presentation(p).mode,/Waiting/);
 assert.equal(p.doc.querySelector('#integrated-result').textContent,'Tatami 1 libre — sin combate asignado');
 assert.deepEqual(presentation(p).names,['','']);
 assert.equal(p.doc.querySelector('#clear-open').disabled,true);
});

test('UI24 la pantalla / anuncia el tiempo agotado sin inventar ganador y nunca libera',async t=>{
 const {url}=await running(t),p=await page(url,'/');
 assert.equal(p.doc.querySelector('#integrated-clear'),null,'/ no construye el panel de liberacion');
 assert.equal(p.doc.querySelector('#finish-open'),null,'/ no construye el panel de finalizacion');
 p.handlers['tatami:state']({...sides({points:2},{points:4}),status:'awaiting_result',remaining_seconds:0,revision:4});
 assert.equal(p.doc.querySelector('#integrated-result').textContent,'Tiempo finalizado — pendiente de resultado');
 assert.deepEqual(presentation(p).names,['Ana','Bea']);
 assert.equal(presentation(p).time,'00:00');
 for(const n of p.doc.querySelectorAll('input,button,#start,#restart,[id^="add"],[id^="sub"]')) {
  assert.equal(n.getAttribute('aria-disabled'),'true');
  n.dispatchEvent(new p.w.Event('click',{bubbles:true}));
 }
 assert.deepEqual(p.emits,[],'solo lectura');
});

test('UI25 el panel de cancelacion solo existe en las paginas de control y solo con un combate intacto',async t=>{
 const {url}=await running(t),display=await page(url,'/');
 assert.equal(display.doc.querySelector('#integrated-cancel'),null,'/ no construye el panel de cancelacion');
 for(const route of ['/control','/control2']) {
  const p=await page(url,route);
  assert.ok(p.doc.querySelector('#integrated-cancel'),route+' construye el panel');
  assert.equal(p.doc.querySelector('#cancel-open').disabled,true,route+' sin sesion no se puede cancelar');
  assert.equal(p.doc.querySelector('#integrated-cancel').style.display,'none',route+' sin combate esta oculto');
  p.handlers['tatami:state'](sides());
  assert.equal(p.doc.querySelector('#cancel-open').disabled,false,route+' ready intacto se puede cancelar');
  assert.notEqual(p.doc.querySelector('#integrated-cancel').style.display,'none',route+' con combate intacto se ofrece');
  p.handlers['tatami:state'](sides({points:2}));
  assert.equal(p.doc.querySelector('#integrated-cancel').style.display,'none',route+' con puntos no se ofrece');
  p.handlers['tatami:state']({...sides({advantages:1},{penalties:2}),revision:3});
  assert.equal(p.doc.querySelector('#integrated-cancel').style.display,'none',route+' con ventajas y penalizaciones no se ofrece');
  p.handlers['tatami:state']({...sides(),status:'running',remaining_seconds:200,revision:4});
  assert.equal(p.doc.querySelector('#integrated-cancel').style.display,'none',route+' en marcha no se ofrece');
  p.handlers['tatami:state']({...sides({points:4},{points:2}),status:'finished',revision:5,remaining_seconds:0,winner_team_id:101,method:'points'});
  assert.equal(p.doc.querySelector('#integrated-cancel').style.display,'none',route+' finalizado no se ofrece');
  p.emits.length=0;
  for(const id of ['cancel-open','cancel-confirm','cancel-abort']) {
   const n=p.doc.querySelector('#'+id);if(n!==null)n.dispatchEvent(new p.w.Event('click',{bubbles:true}));
  }
  assert.deepEqual(p.emits,[],route+' sin combate intacto no se emite nada');
 }
});

test('UI26 cancelar exige confirmacion explicita y emite un unico cancel_assignment',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state'](sides());
 assert.equal(p.doc.querySelector('#cancel-open').disabled,false);
 p.emits.length=0;
 click(p,'cancel-open');
 assert.deepEqual(p.emits,[],'el primer acto no emite');
 assert.equal(p.doc.querySelector('#cancel-confirm').style.display,'');
 assert.equal(p.doc.querySelector('#clear-confirm').style.display,'none','cancelar no arma la liberacion');
 assert.equal(p.doc.querySelector('#finish-confirm').style.display,'none','cancelar no arma la finalizacion');
 assert.match(p.doc.querySelector('#cancel-ask').textContent,/Cancelar la asignación/);
 click(p,'cancel-abort');
 assert.deepEqual(p.emits,[]);
 assert.equal(p.doc.querySelector('#cancel-confirm').style.display,'none');
 click(p,'cancel-open');click(p,'cancel-confirm');
 assert.equal(p.emits.length,1);
 assert.equal(p.emits[0][0],'tatami:update');
 assert.equal(p.emits[0][1].operation,'cancel_assignment');
 assert.deepEqual(Object.keys(p.emits[0][1]).sort(),['command_id','expected_revision','match_id','operation','session_id','tatami_id']);
 assert.equal(p.emits[0][1].session_id,'synthetic-session-a');
 assert.equal(p.emits[0][1].expected_revision,1);
 click(p,'cancel-confirm');
 assert.equal(p.emits.length,1,'el segundo clic no reemite');
 p.handlers['tatami:state'](null);
 assert.match(presentation(p).mode,/Waiting/);
 assert.equal(p.doc.querySelector('#cancel-open').disabled,true);
});

test('UI27 armar la cancelacion no sobrevive a un cambio de estado del servidor',async t=>{
 const {url}=await running(t),p=await page(url,'/control');
 p.handlers['tatami:state'](sides());
 click(p,'cancel-open');
 assert.equal(p.doc.querySelector('#cancel-confirm').style.display,'');
 p.handlers['tatami:state']({...sides(),status:'running',remaining_seconds:200,revision:2});
 assert.equal(p.doc.querySelector('#integrated-cancel').style.display,'none','en marcha se retira');
 p.emits.length=0;
 click(p,'cancel-confirm');
 assert.deepEqual(p.emits,[],'la cancelacion armada no se emite sobre un combate vivo');
 p.handlers['tatami:state']({...sides(),status:'ready',remaining_seconds:305,revision:3});
 assert.equal(p.doc.querySelector('#cancel-open').disabled,false,'vuelto a ready intacto se ofrece otra vez');
 assert.equal(p.doc.querySelector('#cancel-confirm').style.display,'none','y no queda armado de antes');
});

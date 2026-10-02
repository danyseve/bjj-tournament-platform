'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {createStateFile}=require('../state-store');
const legacyRoot=path.resolve(__dirname,'../../services/scoreboard');

function workspace(label){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'bjj-health-'+label+'-'));
 return {directory,file:path.join(directory,'state.json'),cleanup:()=>fs.rmSync(directory,{recursive:true,force:true})};
}
// The integrated server reads SCOREBOARD_STATE_FILE when it is created, so the
// variable is set and restored around each server start.
async function running(t,statePath){
 const previous=process.env.SCOREBOARD_STATE_FILE;
 if(statePath===undefined)delete process.env.SCOREBOARD_STATE_FILE;else process.env.SCOREBOARD_STATE_FILE=statePath;
 const a=require('../integrated').createServer(legacyRoot);
 await new Promise(r=>a.server.listen(0,'127.0.0.1',r));
 t.after(()=>new Promise(r=>a.io.close(()=>{
  if(previous===undefined)delete process.env.SCOREBOARD_STATE_FILE;else process.env.SCOREBOARD_STATE_FILE=previous;
  r();
 })));
 return 'http://127.0.0.1:'+a.server.address().port;
}

test('H01 readiness probe is read-only and honest about the state directory',()=>{
 const space=workspace('ready');
 try{
  const files=createStateFile({file:space.file});
  assert.equal(files.ready(),true,'a writable directory is ready before any save');
  assert.deepEqual(fs.readdirSync(space.directory),[],'the probe created nothing');
  files.save({schema_version:1});
  assert.equal(files.ready(),true);
  fs.chmodSync(space.file,0o400);
  assert.equal(files.ready(),false,'an unwritable existing file is not ready');
  fs.chmodSync(space.file,0o600);
  assert.equal(createStateFile({file:path.join(space.directory,'missing','state.json')}).ready(),false);
  const frozen=workspace('frozen');
  try{
   fs.chmodSync(frozen.directory,0o500);
   assert.equal(createStateFile({file:frozen.file}).ready(),false,'an unwritable directory is not ready');
  }finally{fs.chmodSync(frozen.directory,0o700);frozen.cleanup();}
 }finally{space.cleanup();}
});

test('H02 health reports the mode and a usable state store, and nothing else',async t=>{
 const space=workspace('ok');
 t.after(()=>space.cleanup());
 const url=await running(t,space.file);
 const response=await fetch(url+'/health');
 assert.equal(response.status,200);
 const body=await response.json();
 assert.deepEqual(body,{status:'ok',service:'bjj-scoreboard',mode:'integrated',state_store:{enabled:true,ready:true}});
 assert.deepEqual(Object.keys(body).sort(),['mode','service','state_store','status'],'no extra field is exposed');
});

test('H03 without a state file health stays up and says persistence is off',async t=>{
 const url=await running(t,undefined);
 const response=await fetch(url+'/health');
 assert.equal(response.status,200);
 assert.deepEqual((await response.json()).state_store,{enabled:false,ready:false});
});

test('H04 an unwritable state directory fails closed instead of reporting healthy',async t=>{
 const space=workspace('readonly');
 t.after(()=>{fs.chmodSync(space.directory,0o700);space.cleanup();});
 fs.chmodSync(space.directory,0o500);
 const url=await running(t,space.file);
 const response=await fetch(url+'/health');
 assert.equal(response.status,503,'a store that cannot be written is not a healthy service');
 assert.deepEqual((await response.json()).state_store,{enabled:true,ready:false});
});

test('H05 health never carries a token',async t=>{
 const previousInternal=process.env.SCOREBOARD_INTERNAL_TOKEN;
 const previousControl=process.env.SCOREBOARD_CONTROL_TOKEN;
 process.env.SCOREBOARD_INTERNAL_TOKEN='synthetic-internal-token-health';
 process.env.SCOREBOARD_CONTROL_TOKEN='synthetic-control-token-health';
 t.after(()=>{
  if(previousInternal===undefined)delete process.env.SCOREBOARD_INTERNAL_TOKEN;else process.env.SCOREBOARD_INTERNAL_TOKEN=previousInternal;
  if(previousControl===undefined)delete process.env.SCOREBOARD_CONTROL_TOKEN;else process.env.SCOREBOARD_CONTROL_TOKEN=previousControl;
 });
 const space=workspace('secret');
 t.after(()=>space.cleanup());
 const url=await running(t,space.file);
 const text=await (await fetch(url+'/health')).text();
 assert.doesNotMatch(text,/synthetic-internal-token-health|synthetic-control-token-health/);
});

// Real route-rendered HTML + actual production scripts; controlled fetch responses.
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const {spawnSync}=require('node:child_process');const {test}=require('node:test');const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../..');
const local=path.join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const python=process.env.PYTHON||(fs.existsSync(local)?local:(process.platform==='win32'?'python':'python3'));
function render(extra=[]){const r=spawnSync(python,[path.join(__dirname,'render-planning.py'),...extra],{cwd:root,encoding:'utf8'});assert.equal(r.status,0,r.stderr);return r.stdout;}
const html=render(),fragment=render(['--pantry-fragment']);
const app=fs.readFileSync(path.join(root,'app/static/app.js'),'utf8');const pantryCode=fs.readFileSync(path.join(root,'app/static/planning-pantry.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup({stored={},saved=false,errors=false,user=null,fetcher=null,storageFails=false}={}){
 const dom=new JSDOM(html,{url:'http://localhost/survey'+(saved?'?saved=1':''),runScripts:'outside-only'}),win=dom.window,doc=win.document;
 win.matchMedia=()=>({matches:false});win.scrollTo=()=>{};win.HTMLElement.prototype.scrollIntoView=function(){};
 const page=doc.querySelector('.planning-page');if(saved)page.dataset.preferencesSaved='1';if(errors)page.dataset.preferencesErrors='1';if(user)page.dataset.preferencesUser=user;
 Object.entries(stored).forEach(([key,value])=>win.sessionStorage.setItem(key,value));
 if(storageFails)win.Storage.prototype.setItem=()=>{throw Error('Quota exceeded');};
 const requests=[];win.fetch=async(url,options)=>{requests.push([url,options]);if(fetcher)return fetcher(url,options);throw Error('Unexpected network request');};
 win.eval(app);win.eval(pantryCode);
 const form=doc.getElementById('wizard'),input=name=>form.elements.namedItem(name);
 const type=(name,value)=>{input(name).value=String(value);input(name).dispatchEvent(new win.Event('input',{bubbles:true}));};
 const key='pj-preferences-draft:'+page.dataset.preferencesUser;
 return {dom,win,doc,page,form,input,type,key,requests,close:()=>win.close()};
}
function response(data,ok=true){return {ok,headers:{get:()=> 'application/json'},json:async()=>data};}
function draft(state,fields={budget:['177']},step=2,version=state.page.dataset.preferencesVersion){return JSON.stringify({version,fields,step,expanded:['pantry','schedule-windows']});}
function submit(state,form){form.dispatchEvent(new state.win.Event('submit',{bubbles:true,cancelable:true}));}
function testCase(name,fn){test(name,async()=>{const s=setup();try{await fn(s);}finally{s.close();}});}

testCase('draft stores preferences but never CSRF fields or pantry inputs',s=>{
 s.type('budget',177);s.type('free_text','No fish');
 const d=JSON.parse(s.win.sessionStorage.getItem(s.key));assert.deepEqual(d.fields.budget,['177']);assert.deepEqual(d.fields.free_text,['No fish']);
 assert.equal('csrf_token' in d.fields,false);assert.equal('name' in d.fields,false);assert.equal('goals_present' in d.fields,false);
});
testCase('navigation/reload restores exact values, selected controls, active step and expanded sections',s=>{
 s.type('budget',177);s.form.querySelector('[name=goals][value=high_protein]').click();s.type('protein_target',137);
 s.form.querySelector('[name=restrictions][value=vegan]').click();s.form.querySelector('[name=busy_2]').click();
 s.form.querySelector('[data-goto="3"]').click();s.doc.getElementById('pantry').open=true;s.doc.getElementById('schedule-windows').open=true;
 s.win.dispatchEvent(new s.win.Event('pagehide'));
 const restored=setup({stored:{[s.key]:s.win.sessionStorage.getItem(s.key)}});
 try{assert.equal(restored.input('budget').value,'177');assert.equal(restored.input('protein_target').value,'137');assert.equal(restored.form.querySelector('[name=goals][value=high_protein]').checked,true);assert.equal(restored.form.querySelector('[name=restrictions][value=vegan]').checked,true);assert.equal(restored.doc.getElementById('planning-step-3').hidden,false);assert.equal(restored.doc.getElementById('pantry').open,true);assert.equal(restored.doc.getElementById('schedule-windows').open,true);assert.equal(restored.form.querySelector('[name=busy_2]').closest('.dayrow').classList.contains('is-busy'),true);}finally{restored.close();}
});
testCase('a successful save clears old tab drafts instead of restoring them',s=>{
 const restored=setup({saved:true,stored:{[s.key]:draft(s)}});try{assert.equal(restored.input('budget').value,'150');assert.equal(restored.win.sessionStorage.getItem(s.key),null);}finally{restored.close();}
});
testCase('server validation values take precedence and remain recoverable as a draft',s=>{
 const restored=setup({errors:true,stored:{[s.key]:draft(s)}});try{assert.equal(restored.input('budget').value,'150');assert.equal(JSON.parse(restored.win.sessionStorage.getItem(s.key)).fields.budget[0],'150');}finally{restored.close();}
});
testCase('a different account cannot restore another account draft',s=>{
 const restored=setup({user:'2',stored:{[s.key]:draft(s)}});try{assert.equal(restored.input('budget').value,'150');assert.equal(restored.doc.querySelector('[data-draft-notice]').hidden,true);}finally{restored.close();}
});
testCase('newer saved preferences require an explicit choice before restoring a conflicting draft',s=>{
 const restored=setup({stored:{[s.key]:draft(s,{budget:['177'],goals:['high_protein'],protein_target:['137']},2,'older-version')}});
 try{assert.equal(restored.input('budget').value,'150');assert.equal(restored.form.hasAttribute('inert'),true);assert.equal(restored.doc.querySelector('[data-restore-draft]').hidden,false);restored.doc.querySelector('[data-restore-draft]').click();assert.equal(restored.input('budget').value,'177');assert.equal(restored.form.hasAttribute('inert'),false);assert.equal(restored.input('protein_target').disabled,false);assert.equal(JSON.parse(restored.win.sessionStorage.getItem(s.key)).version,restored.page.dataset.preferencesVersion);}finally{restored.close();}
});
testCase('discarding a conflicting draft keeps the saved values and removes the block',s=>{
 const restored=setup({stored:{[s.key]:draft(s,{budget:['177']},2,'older-version')}});try{restored.doc.querySelector('[data-discard-draft]').click();assert.equal(restored.input('budget').value,'150');assert.equal(restored.form.hasAttribute('inert'),false);assert.equal(restored.win.sessionStorage.getItem(s.key),null);}finally{restored.close();}
});
testCase('malformed storage and quota failures do not break planning controls',s=>{
 const malformed=setup({stored:{[s.key]:'not json'}}),blocked=setup({storageFails:true});try{assert.equal(malformed.input('budget').value,'150');blocked.type('budget',177);assert.equal(blocked.doc.querySelector('[data-summary-budget]').textContent,'$177');}finally{malformed.close();blocked.close();}
});
testCase('stored draft data cannot replace a CSRF token',s=>{
 const restored=setup({stored:{[s.key]:draft(s,{budget:['177'],csrf_token:['forged-token']})}});try{assert.notEqual(restored.input('csrf_token').value,'forged-token');assert.equal(restored.input('budget').value,'177');}finally{restored.close();}
});
testCase('logout clears only this app draft keys',s=>{
 s.type('budget',177);s.win.sessionStorage.setItem('other-app','keep');s.win.sessionStorage.setItem('pj-preferences-draft:2','old');
 const logout=s.doc.querySelector('form[action="/logout"]');logout.addEventListener('submit',event=>event.preventDefault());submit(s,logout);s.win.dispatchEvent(new s.win.Event('pagehide'));
 assert.equal(s.win.sessionStorage.getItem(s.key),null);assert.equal(s.win.sessionStorage.getItem('pj-preferences-draft:2'),null);assert.equal(s.win.sessionStorage.getItem('other-app'),'keep');
});

test('pantry add replaces only the fragment while goals, quantities, step and draft remain intact',async()=>{
 const s=setup({fetcher:async()=>response({ok:true,html:fragment,message:'Added rice.'})});
 try{s.type('budget',177);s.form.querySelector('[name=goals][value=high_protein]').click();s.type('protein_target',137);s.form.querySelector('[data-goto="3"]').click();const form=s.doc.querySelector('[data-pantry-form][action="/pantry/add"]');form.elements.name.value='rice';form.elements.quantity.value='2';form.elements.unit.value='cup';submit(s,form);await tick();assert.equal(s.requests.length,1);assert.equal(s.requests[0][1].body.get('csrf_token'),s.input('csrf_token').value);assert.equal(s.input('budget').value,'177');assert.equal(s.input('protein_target').value,'137');assert.equal(s.doc.getElementById('planning-step-3').hidden,false);assert.match(s.doc.querySelector('[data-pantry-body]').textContent,/rice/);assert.equal(s.doc.querySelector('[data-pantry-status]').textContent,'Added rice.');assert.equal(JSON.parse(s.win.sessionStorage.getItem(s.key)).fields.budget[0],'177');}finally{s.close();}
});
test('pantry delete does not submit or reset the preferences form',async()=>{
 const s=setup({fetcher:async()=>response({ok:true,html:'<p>Nothing yet.</p>',message:'Removed item.'})});
 try{s.doc.querySelector('[data-pantry-body]').innerHTML=fragment;s.type('free_text','Keep my unsaved note');let mainSubmits=0;s.form.addEventListener('submit',()=>mainSubmits++);submit(s,s.doc.querySelector('form[action$="/delete"]'));await tick();assert.equal(mainSubmits,0);assert.equal(s.input('free_text').value,'Keep my unsaved note');assert.equal(s.requests[0][1].method,'POST');assert.match(s.doc.querySelector('[data-pantry-body]').textContent,/Nothing yet/);}finally{s.close();}
});
test('a rejected pantry update preserves typed pantry values and unrelated edits',async()=>{
 const s=setup({fetcher:async()=>response({ok:false,error:'Invalid amount'},false)});try{s.type('budget',177);const form=s.doc.querySelector('form[action="/pantry/add"]');form.elements.name.value='rice';form.elements.quantity.value='2';submit(s,form);await tick();assert.equal(form.elements.name.value,'rice');assert.equal(form.elements.quantity.value,'2');assert.equal(s.input('budget').value,'177');assert.equal(s.doc.querySelector('[data-pantry-status]').textContent,'Invalid amount');assert.equal(form.querySelector('button').disabled,false);}finally{s.close();}
});
test('a network failure never falls back to a page reload and offers a safe pantry refresh',async()=>{
 let fail=true;const s=setup({fetcher:async()=>{if(fail)throw Error('offline');return response({ok:true,html:fragment,message:'Pantry refreshed.'});}});
 try{s.type('budget',177);const form=s.doc.querySelector('form[action="/pantry/add"]');form.elements.name.value='rice';submit(s,form);await tick();assert.equal(s.requests.length,1);assert.equal(s.doc.querySelector('[data-pantry-refresh]').hidden,false);fail=false;s.doc.querySelector('[data-pantry-refresh]').click();await tick();assert.equal(s.requests[1][1].method,'GET');assert.equal(s.input('budget').value,'177');assert.equal(s.doc.querySelector('[data-pantry-refresh]').hidden,true);}finally{s.close();}
});
test('double submits are serialized before the first response',async()=>{
 let release;const pending=new Promise(resolve=>release=resolve);const s=setup({fetcher:()=>pending});try{const form=s.doc.querySelector('form[action="/pantry/add"]');form.elements.name.value='rice';submit(s,form);submit(s,form);assert.equal(s.requests.length,1);release(response({ok:true,html:fragment}));await tick();assert.equal(s.doc.getElementById('pantry').getAttribute('aria-busy'),'false');}finally{s.close();}
});
test('late pantry responses do not steal focus from a preference field',async()=>{
 let release;const pending=new Promise(resolve=>release=resolve);const s=setup({fetcher:()=>pending});try{const form=s.doc.querySelector('form[action="/pantry/add"]');form.elements.name.value='rice';form.elements.name.focus();submit(s,form);s.input('budget').focus();release(response({ok:true,html:fragment}));await tick();assert.equal(s.doc.activeElement,s.input('budget'));}finally{s.close();}
});


test('new edits made immediately after a successful save survive the next refresh',()=>{
 const saved=setup({saved:true});let restored;
 try{assert.equal(saved.win.location.search,'');saved.type('budget',177);saved.win.dispatchEvent(new saved.win.Event('pagehide'));restored=setup({stored:{[saved.key]:saved.win.sessionStorage.getItem(saved.key)}});assert.equal(restored.input('budget').value,'177');assert.equal(restored.doc.querySelector('[data-draft-notice]').hidden,false);}finally{if(restored)restored.close();saved.close();}
});

// Exercise production JS against HTML from the actual route, without paid services.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const {test}=require('node:test');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../..');
const localPython=process.platform==='win32'?path.join(root,'.venv/Scripts/python.exe'):path.join(root,'.venv/bin/python');
const python=process.env.PYTHON || (fs.existsSync(localPython)?localPython:(process.platform==='win32'?'python':'python3'));
function render(first){
  const result=spawnSync(python,[path.join(__dirname,'render-planning.py'),...(first?['--first']:[])],{cwd:root,encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);return result.stdout;
}
const returning=render(false),onboarding=render(true);
const source=fs.readFileSync(path.join(root,'app/static/app.js'),'utf8');
function setup({first=false,hash=''}={}){
  const dom=new JSDOM(first?onboarding:returning,{url:'http://localhost/survey'+hash,runScripts:'outside-only'});
  const win=dom.window;win.matchMedia=()=>({matches:false});win.scrollTo=()=>{};
  win.HTMLElement.prototype.scrollIntoView=function(){};
  win.fetch=()=>{throw Error('Planning controls must not send background requests');};
  win.eval(source);
  const doc=win.document,form=doc.getElementById('wizard');
  const input=name=>form.elements.namedItem(name);
  const enable=goal=>{const check=form.querySelector(`input[name=goals][value="${goal}"]`);if(!check.checked)check.click();};
  const type=(name,value)=>{input(name).value=String(value);input(name).dispatchEvent(new win.Event('input',{bubbles:true}));};
  return {dom,win,doc,form,input,enable,type};
}
function check(name,fn){test(name,()=>{const state=setup();try{fn(state);}finally{state.dom.window.close();}});}
check('both goal checkboxes stay selected and submit their own exact targets',({form,input,enable,type,win})=>{
  enable('high_protein');enable('calorie_target');type('protein_target',137);type('calorie_target',2150);
  const data=new win.FormData(form);
  assert.deepEqual(data.getAll('goals'),['high_protein','calorie_target']);
  assert.equal(data.get('protein_target'),'137');assert.equal(data.get('calorie_target'),'2150');
  assert.equal(input('protein_target').disabled,false);assert.equal(input('calorie_target').disabled,false);
});
check('protein slider updates the exact amount, accessible value and summary',({doc,input,enable,win})=>{
  enable('high_protein');const slider=doc.getElementById('protein-slider');slider.value='163';slider.dispatchEvent(new win.Event('input',{bubbles:true}));
  assert.equal(input('protein_target').value,'163');assert.equal(slider.getAttribute('aria-valuetext'),'163 grams per day');
  assert.equal(doc.querySelector('[data-summary-protein]').textContent,'163g / day');
});
check('typing a non-preset protein amount updates the slider without rounding',({doc,enable,type})=>{
  enable('high_protein');type('protein_target',137);assert.equal(doc.getElementById('protein-slider').value,'137');
});
check('turning off one goal disables its field while preserving the other target',({form,input,enable,type,win})=>{
  enable('high_protein');enable('calorie_target');type('protein_target',140);type('calorie_target',2000);
  form.querySelector('[name=goals][value=high_protein]').click();
  const data=new win.FormData(form);assert.equal(data.has('protein_target'),false);assert.equal(data.get('calorie_target'),'2000');
  assert.equal(input('protein_target').value,'140');assert.equal(input('protein_target').disabled,true);
});
check('clear goals selects neither and excludes their inactive values from submission',({form,enable,win,doc})=>{
  enable('high_protein');enable('calorie_target');form.querySelector('[data-clear-goals]').click();
  const data=new win.FormData(form);assert.equal(data.has('goals'),false);assert.equal(data.has('protein_target'),false);assert.equal(data.has('calorie_target'),false);
  assert.equal(data.get('goals_present'),'1');assert.equal(doc.querySelector('[data-summary-protein]').textContent,'Not selected');
});
check('invalid protein on a hidden step blocks saving and opens that step',({form,enable,type,win,doc})=>{
  enable('high_protein');type('protein_target',301);form.querySelector('[data-goto="3"]').click();
  const event=new win.Event('submit',{cancelable:true,bubbles:true});form.dispatchEvent(event);
  assert.equal(event.defaultPrevented,true);assert.equal(doc.getElementById('planning-step-0').hidden,false);
  assert.equal(doc.activeElement.name,'protein_target');
});
check('Next validates the current step instead of silently advancing invalid calories',({form,enable,type,doc})=>{
  enable('calorie_target');type('calorie_target',1100);form.querySelector('[data-next]').click();
  assert.equal(doc.getElementById('planning-step-0').hidden,false);assert.equal(doc.activeElement.name,'calorie_target');
});
check('preset buttons update values and pressed state without submitting',({form,input,doc})=>{
  let submits=0;form.addEventListener('submit',()=>submits++);form.querySelector('[data-target=budget] [data-set="80"]').click();
  assert.equal(input('budget').value,'80');assert.equal(submits,0);assert.equal(form.querySelector('[data-save-note]').textContent,'Unsaved changes');assert.equal(doc.querySelector('[data-summary-budget]').textContent,'$80');
  assert.equal(form.querySelector('[data-target=budget] [data-set="80"]').getAttribute('aria-pressed'),'true');
});
check('each navigation button opens exactly one section with the current step announced',({form,doc})=>{
  for(let index=0;index<4;index++){
    form.querySelector(`[data-goto="${index}"]`).click();
    assert.equal([...form.querySelectorAll('.wstep')].filter(step=>!step.hidden).length,1);
    assert.equal(form.querySelector('[aria-current=step]').dataset.goto,String(index));
    assert.equal(doc.getElementById('planning-step-label').textContent,`Step ${index+1} of 4`);
  }
});
check('campus meals have seven consistently structured rows and serialize the chosen slot',({form,win})=>{
  const rows=form.querySelectorAll('.planning-meal-grid tbody tr');assert.equal(rows.length,7);
  rows.forEach(row=>assert.equal(row.querySelectorAll('td').length,3));
  form.querySelector('[name=external_2_lunch]').click();const data=new win.FormData(form);
  assert.equal(data.get('external_2_lunch'),'on');assert.equal(data.has('external_2_breakfast'),false);
});
check('kitchen, timing and goals share one non-nested save form',({form,doc,win})=>{
  assert.equal(form.action,'http://localhost/survey');assert.equal(form.querySelector('form'),null);
  for(const name of ['lifestyle_present','schedule_present','goals_present','prep_present'])assert.equal(new win.FormData(form).get(name),'1');
  assert.equal(form.contains(doc.querySelector('[name=cooking_skill]')),true);
});
check('invalid time in closed advanced settings is revealed before reporting validity',({form,input,win,doc})=>{
  input('time_breakfast').value='';form.querySelector('[data-goto="3"]').click();
  const event=new win.Event('submit',{bubbles:true,cancelable:true});form.dispatchEvent(event);
  assert.equal(event.defaultPrevented,true);assert.equal(doc.getElementById('schedule-windows').open,true);
  assert.equal(doc.getElementById('planning-step-2').hidden,false);
});
test('schedule hash opens the correct section and details on arrival',()=>{
  const {dom,doc}=setup({hash:'#schedule-windows'});try{assert.equal(doc.getElementById('planning-step-2').hidden,false);assert.equal(doc.getElementById('schedule-windows').open,true);}finally{dom.window.close();}
});
test('onboarding requires budget before Next and leaves all optional targets off',()=>{
  const {dom,form,input,doc}=setup({first:true});try{form.querySelector('[data-next]').click();assert.equal(doc.getElementById('planning-step-0').hidden,false);assert.equal(doc.activeElement,input('budget'));assert.equal(form.querySelectorAll('[name=goals]:checked').length,0);}finally{dom.window.close();}
});

// In-process DOM checks; no browser launch, network, model calls or cart writes.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const source=fs.readFileSync(path.join(__dirname,'../../app/static/kroger.js'),'utf8');
const test=require('node:test');
function setup(hash=''){
  const dom=new JSDOM(`<main data-kroger-shop>
    <button type="button" data-kroger-filter="all" aria-pressed="true">All</button>
    <button type="button" data-kroger-filter="remaining" aria-pressed="false">Remaining</button>
    <details id="ingredient-0" data-ingredient data-selected="true"><summary>Rice selected</summary></details>
    <details id="ingredient-1" data-ingredient data-selected="false"><summary>Bananas</summary>
      <form><div data-quantity><button type="button" data-quantity-step="-1">−</button><input type="number" value="1" min="1" max="99"><button type="button" data-quantity-step="1">+</button></div></form>
    </details><details id="stores"><summary>Store</summary></details>
    <div><img data-product-photo src="https://www.kroger.com/test.jpg"></div>
    </main>`,{url:'http://localhost/grocery/kroger'+hash,runScripts:'outside-only'});
  dom.window.fetch=()=>{throw Error('Visual controls must not make network calls');};
  let submissions=0;
  dom.window.document.addEventListener('submit',event=>{event.preventDefault();submissions++;});
  const photo=dom.window.document.querySelector('[data-product-photo]');
  Object.defineProperty(photo,'complete',{value:false,configurable:true});
  dom.window.eval(source);
  return {dom,window:dom.window,doc:dom.window.document,submissions:()=>submissions};
}

test('opens the first unmatched ingredient when there is no hash',()=>{
  const {dom,doc}=setup();
  assert.equal(doc.getElementById('ingredient-0').open,false);
  assert.equal(doc.getElementById('ingredient-1').open,true);dom.window.close();
});
test('minus and plus enforce the package count boundaries without submitting',()=>{
  const {dom,doc,submissions}=setup();const input=doc.querySelector('input');
  doc.querySelector('[data-quantity-step="-1"]').click();assert.equal(input.value,'1');
  for(let n=0;n<110;n++)doc.querySelector('[data-quantity-step="1"]').click();
  assert.equal(input.value,'99');assert.equal(submissions(),0);dom.window.close();
});
test('a typed package count updates from its actual value',()=>{
  const {dom,doc}=setup();const input=doc.querySelector('input');input.value='4';
  doc.querySelector('[data-quantity-step="1"]').click();assert.equal(input.value,'5');dom.window.close();
});
test('remaining filter hides selected ingredients and keeps unselected ones',()=>{
  const {dom,doc,submissions}=setup();doc.querySelector('[data-kroger-filter="remaining"]').click();
  assert.equal(doc.getElementById('ingredient-0').hidden,true);
  assert.equal(doc.getElementById('ingredient-1').hidden,false);
  assert.equal(doc.querySelector('[data-kroger-filter="remaining"]').getAttribute('aria-pressed'),'true');
  assert.equal(submissions(),0);dom.window.close();
});
test('all filter restores selected ingredients',()=>{
  const {dom,doc}=setup();doc.querySelector('[data-kroger-filter="remaining"]').click();
  doc.querySelector('[data-kroger-filter="all"]').click();
  assert.equal(doc.getElementById('ingredient-0').hidden,false);dom.window.close();
});
test('a selection redirect hash reveals the relevant ingredient',()=>{
  const {dom,doc}=setup('#ingredient-0');assert.equal(doc.getElementById('ingredient-0').open,true);dom.window.close();
});
test('a later hash change reveals a selected ingredient hidden by the filter',()=>{
  const {dom,doc,window}=setup();doc.querySelector('[data-kroger-filter="remaining"]').click();
  window.location.hash='#ingredient-0';window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  assert.equal(doc.getElementById('ingredient-0').hidden,false);
  assert.equal(doc.getElementById('ingredient-0').open,true);
  assert.equal(doc.querySelector('[data-kroger-filter="all"]').getAttribute('aria-pressed'),'true');dom.window.close();
});
test('store search redirect expands store choices',()=>{
  const {dom,doc}=setup('#stores');assert.equal(doc.getElementById('stores').open,true);dom.window.close();
});
test('a broken retailer photo becomes a stable neutral placeholder',()=>{
  const {dom,doc,window}=setup();const image=doc.querySelector('[data-product-photo]');
  image.dispatchEvent(new window.Event('error'));
  assert.equal(image.hidden,true);assert.equal(image.parentElement.classList.contains('no-photo'),true);dom.window.close();
});
test('unrelated hashes and pages without a shopping workspace are harmless',()=>{
  const {dom}=setup('#does-not-exist');dom.window.close();
  const empty=new JSDOM('<main>Other page</main>',{runScripts:'outside-only'});
  assert.doesNotThrow(()=>empty.window.eval(source));empty.window.close();
});

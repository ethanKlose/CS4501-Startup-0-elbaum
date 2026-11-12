/* Pantry forms update only their own fragment; preference inputs never reload. */
(() => {
  'use strict';
  const pantry=document.getElementById('pantry');
  if(!pantry)return;
  const body=pantry.querySelector('[data-pantry-body]'),status=pantry.querySelector('[data-pantry-status]');
  const refresh=pantry.querySelector('[data-pantry-refresh]');let pending=false;
  function busy(value){pending=value;pantry.setAttribute('aria-busy',String(value));pantry.querySelectorAll('button').forEach(button=>button.disabled=value);}
  async function update(url,options){
    if(pending)return;const focusAtStart=document.activeElement;busy(true);status.textContent='Updating pantry…';status.classList.remove('error');
    try{
      const response=await fetch(url,{...options,credentials:'same-origin',headers:{Accept:'application/json'}});
      const type=response.headers.get('content-type')||'';
      if(!type.includes('application/json'))throw Error('Could not confirm the pantry change. Your unsaved preferences are still here. Check your connection or sign in again in another tab, then refresh the pantry list.');
      const data=await response.json();
      if(!response.ok || !data.ok){status.textContent=data.error||'The pantry could not be updated.';status.classList.add('error');return;}
      body.innerHTML=data.html;status.textContent=data.message||'Pantry updated.';refresh.hidden=true;
      if(options.method==='POST' && url.endsWith('/add') && (document.activeElement===focusAtStart || pantry.contains(document.activeElement))){const name=body.querySelector('[name=name]');if(name)name.focus();}
    }catch(error){status.textContent='Could not confirm the pantry change. Your unsaved preferences are still here. Refresh the pantry list before trying again.';status.classList.add('error');refresh.hidden=false;}
    finally{busy(false);}
  }
  pantry.addEventListener('submit',event=>{
    const form=event.target;if(!form.matches('[data-pantry-form]'))return;event.preventDefault();
    if(!form.reportValidity())return;
    update(form.getAttribute('action'),{method:'POST',body:new FormData(form)});
  });
  refresh.addEventListener('click',()=>update('/pantry',{method:'GET'}));
})();

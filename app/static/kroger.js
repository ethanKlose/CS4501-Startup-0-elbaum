/* Visual controls only. Selection and cart writes remain server-confirmed forms. */
(() => {
  const page=document.querySelector('[data-kroger-shop]');
  if(!page) return;
  const ingredients=[...page.querySelectorAll('[data-ingredient]')];
  function openHash(){
    const raw=location.hash.slice(1);
    const target=document.getElementById(raw);
    if(target && (target.matches('[data-ingredient]') || target.id==='stores')){
      target.hidden=false;target.open=true;
      if(target.matches('[data-ingredient]')) setFilter('all');
    }
  }
  function setFilter(value){
    page.querySelectorAll('[data-kroger-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.krogerFilter===value)));
    ingredients.forEach(item=>item.hidden=value==='remaining' && item.dataset.selected==='true');
  }
  page.querySelectorAll('[data-kroger-filter]').forEach(button=>button.addEventListener('click',()=>setFilter(button.dataset.krogerFilter)));
  page.querySelectorAll('[data-quantity-step]').forEach(button=>button.addEventListener('click',()=>{
    const input=button.closest('[data-quantity]').querySelector('input');
    const value=Number(input.value);
    input.value=String(Math.max(Number(input.min),Math.min(Number(input.max),(Number.isFinite(value)?Math.round(value):1)+Number(button.dataset.quantityStep))));
    input.dispatchEvent(new Event('change',{bubbles:true}));
  }));
  page.querySelectorAll('[data-product-photo]').forEach(photo=>{
    const fallback=()=>{photo.hidden=true;photo.parentElement.classList.add('no-photo');};
    photo.addEventListener('error',fallback,{once:true});
    if(photo.complete && !photo.naturalWidth) fallback();
  });
  if(!location.hash && !ingredients.some(item=>item.open)){
    const first=ingredients.find(item=>item.dataset.selected!=='true') || ingredients[0];
    if(first) first.open=true;
  }
  openHash();
  window.addEventListener('hashchange',openHash);
})();

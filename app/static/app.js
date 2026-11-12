/* PlateJoy front-end: small, dependency-free, progressive enhancement only. */
(function () {
  'use strict';
  document.documentElement.classList.add('js');
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---- theme toggle ---- */
  $$('[data-theme-toggle]').forEach(function (b) {
    b.addEventListener('click', function () {
      var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('pj-theme', next); } catch (e) {}
    });
  });

  /* ---- close the account menu when clicking elsewhere ---- */
  document.addEventListener('click', function (e) {
    $$('details.usermenu[open]').forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute('open'); });
  });

  /* ---- password show/hide + strength meter ---- */
  $$('[data-pw-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = $('input', btn.closest('.pw'));
      input.type = input.type === 'password' ? 'text' : 'password';
    });
  });
  $$('[data-strength]').forEach(function (input) {
    var bar = $('i', document.getElementById(input.getAttribute('data-strength')));
    input.addEventListener('input', function () {
      var v = input.value, score = 0;
      if (v.length >= 8) score++; if (v.length >= 12) score++; if (/[A-Z]/.test(v) && /[a-z]/.test(v)) score++; if (/\d/.test(v) && /[^A-Za-z0-9]/.test(v)) score++;
      bar.style.width = (v ? 20 + score * 20 : 0) + '%';
      bar.style.background = ['#d93f3f', '#e08a2d', '#d9b52c', '#7cc243', '#0f9d74'][score];
    });
  });

  /* ---- "generating" overlay for any form marked data-generate ---- */
  var overlay = document.getElementById('gen-overlay');
  var genTimer = null;
  function showGenerating(title) {
    if (!overlay) return;
    var steps = $$('#gen-steps li');
    if (title) document.getElementById('gen-title').textContent = title;
    overlay.hidden = false;
    var i = 0;
    steps.forEach(function (li) { li.className = ''; });
    function tick() {
      if (i > 0 && steps[i - 1]) steps[i - 1].className = 'done';
      if (steps[i]) steps[i].className = 'active';   // the last step keeps spinning until the server answers
      i++;
      if (i >= steps.length) clearInterval(genTimer);
    }
    tick();
    genTimer = setInterval(tick, 1150);
  }
  window.PJ = window.PJ || {};
  window.PJ.showGenerating = showGenerating;
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (f.getAttribute && f.getAttribute('action') === '/logout') {
      window.PJ=window.PJ||{};window.PJ.loggingOut=true;
      try { for (var k=sessionStorage.length-1;k>=0;k--) { var name=sessionStorage.key(k);if(name && name.startsWith('pj-preferences-draft:'))sessionStorage.removeItem(name); } } catch(error) {}
    }
    if (!f.matches || !f.matches('form[data-generate]')) return;
    if (f.dataset.confirm && !window.confirm(f.dataset.confirm)) { e.preventDefault(); return; }
    if (f.dataset.busy) { e.preventDefault(); return; }
    f.dataset.busy = '1';
    showGenerating(f.getAttribute('data-generate-title') || '');
    setTimeout(function () { $$('button', f).forEach(function (b) { b.disabled = true; }); }, 0);
  });
  window.addEventListener('pageshow', function (e) {
    if (e.persisted && overlay) { overlay.hidden = true; clearInterval(genTimer); $$('form[data-busy]').forEach(function (f) { delete f.dataset.busy; $$('button', f).forEach(function (b) { b.disabled = false; }); }); }
  });
  /* a form marked data-autosubmit fires itself (used right after onboarding) */
  var auto = $('form[data-autosubmit]');
  if (auto) setTimeout(function () { if (auto.requestSubmit) auto.requestSubmit(); else auto.submit(); }, 900);
})();

/* ---- planning preferences: native forms with progressive enhancement ---- */
(function () {
  'use strict';
  var form = document.getElementById('wizard');
  if (!form) return;
  var page = form.closest('.planning-page') || document;
  var $$ = function (s, r) { return Array.from((r || form).querySelectorAll(s)); };
  var steps = $$('.wstep'), tabs = $$('.wiz-tabs button'), first = form.dataset.first === '1';
  var cur = 0;
  var draftKey='pj-preferences-draft:'+page.dataset.preferencesUser;
  var draftVersion=page.dataset.preferencesVersion, restored=null, conflict=null, draftDirty=page.dataset.preferencesErrors==='1';
  var controls=Array.from(form.elements).filter(function(input){return input.name && input.type!=='hidden' && !['submit','button'].includes(input.type);});
  function writeDraft(){
    if((window.PJ && window.PJ.loggingOut) || conflict || !draftDirty || !draftVersion || !page.dataset.preferencesUser)return;
    var fields={};controls.forEach(function(input){
      if(!fields[input.name])fields[input.name]=[];
      if(!['checkbox','radio'].includes(input.type) || input.checked)fields[input.name].push(input.value);
    });
    var expanded=['pantry','schedule-windows'].filter(function(id){var section=page.querySelector('#'+id);return section && section.open;});
    try{sessionStorage.setItem(draftKey,JSON.stringify({version:draftVersion,fields:fields,step:cur,expanded:expanded}));}catch(error){}
  }
  function restoreFields(candidate){
        controls.forEach(function(input){
          var values=candidate.fields[input.name];
          if(!Array.isArray(values) || !values.every(function(value){return typeof value==='string' && value.length<=2000;}))return;
          if(['checkbox','radio'].includes(input.type))input.checked=values.includes(input.value);
          else if(values.length)input.value=values[0];
        });
        restored=candidate;draftDirty=true;
        (Array.isArray(candidate.expanded)?candidate.expanded:[]).forEach(function(id){if(['pantry','schedule-windows'].includes(id)){var section=document.getElementById(id);if(section)section.open=true;}});
  }
  try{
    var encoded=sessionStorage.getItem(draftKey);
    if(page.dataset.preferencesSaved==='1'){
      // Treat the redirect marker once. Leaving it in the URL would discard
      // a NEW draft typed after saving when the user refreshes this page.
      var cleanURL=new URL(location.href);cleanURL.searchParams.delete('saved');
      history.replaceState(history.state,'',cleanURL.pathname+cleanURL.search+cleanURL.hash);
    }
    if(page.dataset.preferencesSaved==='1' || page.dataset.preferencesErrors==='1')sessionStorage.removeItem(draftKey);
    else if(encoded && encoded.length<=50000){
      var candidate=JSON.parse(encoded);
      if(candidate && candidate.fields && typeof candidate.fields==='object'){
        if(candidate.version===draftVersion)restoreFields(candidate);
        else conflict=candidate;
      }else sessionStorage.removeItem(draftKey);
    }
  }catch(error){try{sessionStorage.removeItem(draftKey);}catch(ignored){}}
  function go(i, scroll) {
    cur = Math.max(0, Math.min(steps.length - 1, i));
    steps.forEach(function (section, index) { section.hidden=index!==cur;section.classList.toggle('on', index===cur); });
    tabs.forEach(function (tab, index) {
      tab.classList.toggle('on', index===cur);tab.classList.toggle('done',index<cur);
      if(index===cur) tab.setAttribute('aria-current','step');else tab.removeAttribute('aria-current');
    });
    document.getElementById('wiz-progress').style.width=((cur+1)/steps.length*100)+'%';
    var label=document.getElementById('planning-step-label');if(label) label.textContent='Step '+(cur+1)+' of '+steps.length;
    form.classList.toggle('last',cur===steps.length-1);
    steps.forEach(function (_,index) { form.classList.remove('step'+index); });form.classList.add('step'+cur);
    writeDraft();
    if(scroll) form.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
  }
  function invalid(section) {
    return Array.from(section.querySelectorAll('input,select,textarea')).find(function(input){return !input.disabled && !input.checkValidity();});
  }
  function reveal(input) {
    var index=steps.findIndex(function(section){return section.contains(input);});
    if(index>=0) go(index,true);
    var details=input.closest('details');if(details) details.open=true;
    input.focus();if(input.reportValidity) input.reportValidity();
  }
  tabs.forEach(function(tab,index){tab.addEventListener('click',function(){go(index,true);});});
  var next=form.querySelector('[data-next]'),prev=form.querySelector('[data-prev]');
  if(next) next.addEventListener('click',function(){var bad=invalid(steps[cur]);if(bad){reveal(bad);return;}go(cur+1,true);});
  if(prev) prev.addEventListener('click',function(){go(cur-1,true);});
  form.addEventListener('submit',function(event){var bad=invalid(form);if(bad){event.preventDefault();reveal(bad);}});
  form.addEventListener('submit',function(event){
    if(event.defaultPrevented)return;
    if(form.dataset.busy){event.preventDefault();return;}
    if(event.submitter && event.submitter.hasAttribute('data-build-plan')){
      form.dataset.busy='1';
      if(window.PJ && window.PJ.showGenerating)window.PJ.showGenerating('Saving preferences and building your week…');
      setTimeout(function(){form.querySelectorAll('button').forEach(function(button){button.disabled=true;});},0);
    }
  });
  form.addEventListener('keydown',function(event){
    if(first && event.key==='Enter' && event.target.tagName==='INPUT' && !['checkbox','radio','range','submit'].includes(event.target.type) && cur<steps.length-1){event.preventDefault();next.click();}
  });
  $$('.presets').forEach(function(box){
    var input=form.elements.namedItem(box.getAttribute('data-target'));if(!input)return;
    function sync(){box.querySelectorAll('.pill').forEach(function(button){var on=String(input.value)===button.dataset.set;button.classList.toggle('on',on);button.setAttribute('aria-pressed',String(on));});}
    box.addEventListener('click',function(event){var button=event.target.closest('.pill');if(!button)return;input.value=button.dataset.set;input.dispatchEvent(new Event('input',{bubbles:true}));});
    input.addEventListener('input',sync);sync();
  });
  var protein=form.elements.namedItem('protein_target'),slider=document.getElementById('protein-slider');
  function summary(){
    function write(selector,value){var target=page.querySelector(selector);if(target)target.textContent=value;}
    var budget=form.elements.namedItem('budget');write('[data-summary-budget]',budget.value?'$'+budget.value:'Not set');
    var selected=$$('input[name=goals]:checked').map(function(input){return input.value;});
    write('[data-summary-protein]',selected.includes('high_protein')?(protein.value?protein.value+'g / day':'Enter a target'):'Not selected');
    var calories=form.elements.namedItem('calorie_target');write('[data-summary-calories]',selected.includes('calorie_target')?(calories.value?calories.value+' kcal / day':'Enter a target'):'Not selected');
  }
  function dirty(){
    var note=form.querySelector('[data-save-note]');if(note)note.textContent='Unsaved changes';
    var saved=page.querySelector('[data-preferences-saved]');if(saved)saved.hidden=true;
    draftDirty=true;writeDraft();
  }
  function syncGoals(){
    $$('input[name=goals]').forEach(function(check){
      var panel=form.querySelector('[data-goal-fields="'+check.value+'"]');
      if(!panel)return;panel.hidden=!check.checked;
      panel.querySelectorAll('input').forEach(function(input){input.disabled=!check.checked;if(input.name)input.required=check.checked;});
      check.closest('[data-nutrition-card]').classList.toggle('selected',check.checked);
    });summary();
  }
  $$('input[name=goals]').forEach(function(check){check.addEventListener('change',syncGoals);});
  var clear=form.querySelector('[data-clear-goals]');if(clear)clear.addEventListener('click',function(){$$('input[name=goals]').forEach(function(check){check.checked=false;});syncGoals();dirty();});
  if(protein && slider){
    slider.addEventListener('input',function(){protein.value=slider.value;slider.setAttribute('aria-valuetext',slider.value+' grams per day');summary();});
    protein.addEventListener('input',function(){var value=Number(protein.value);if(protein.value && Number.isInteger(value) && value>=20 && value<=300){slider.value=protein.value;slider.setAttribute('aria-valuetext',protein.value+' grams per day');}});
  }
  form.addEventListener('input',summary);
  form.addEventListener('input',dirty);form.addEventListener('change',dirty);
  $$('.dayrow').forEach(function(row){var check=row.querySelector('input[type=checkbox]');row.classList.toggle('is-busy',check.checked);check.addEventListener('change',function(){row.classList.toggle('is-busy',check.checked);});});
  function openHash(){
    var target=document.getElementById(location.hash.slice(1));if(!target || !page.contains(target))return;
    var index=steps.findIndex(function(step){return step.contains(target);});if(index>=0)go(index,false);
    if(target.tagName==='DETAILS')target.open=true;
    target.scrollIntoView({block:'start'});
  }
  syncGoals();
  var start=steps.findIndex(function(step){return step.dataset.hasError==='1';});go(start>=0?start:(restored && Number.isInteger(restored.step)?restored.step:0),false);
  if(start>=0){var bad=invalid(steps[start]);if(bad)reveal(bad);}else openHash();
  window.addEventListener('hashchange',openHash);
  window.addEventListener('pagehide',writeDraft);
  form.addEventListener('submit',writeDraft);
  page.addEventListener('toggle',writeDraft,true);
  var notice=page.querySelector('[data-draft-notice]');
  if(restored){dirty();if(notice)notice.hidden=false;}
  var restoreButton=page.querySelector('[data-restore-draft]');
  if(conflict && notice){
    notice.hidden=false;form.setAttribute('inert','');
    notice.querySelector('[data-draft-message]').textContent='Preferences were saved in another tab. Restore your unsaved draft for review, or keep the saved preferences.';
    if(restoreButton)restoreButton.hidden=false;
  }
  if(restoreButton)restoreButton.addEventListener('click',function(){
    if(!conflict)return;var candidate=conflict;conflict=null;form.removeAttribute('inert');
    restoreFields(candidate);syncGoals();summary();$$('.presets').forEach(function(box){var input=form.elements.namedItem(box.dataset.target);input.dispatchEvent(new Event('input'));});if(protein)protein.dispatchEvent(new Event('input'));$$('.dayrow').forEach(function(row){row.classList.toggle('is-busy',row.querySelector('input[type=checkbox]').checked);});go(Number.isInteger(candidate.step)?candidate.step:0,false);dirty();
    restoreButton.hidden=true;
    notice.querySelector('[data-draft-message]').textContent='Your draft is restored for review. Save to apply these changes.';
  });
  var discard=page.querySelector('[data-discard-draft]');
  if(discard)discard.addEventListener('click',function(){
    form.reset();draftDirty=false;restored=null;conflict=null;form.removeAttribute('inert');if(restoreButton)restoreButton.hidden=true;
    try{sessionStorage.removeItem(draftKey);}catch(error){}
    syncGoals();summary();go(0,false);if(notice)notice.hidden=true;
    var note=form.querySelector('[data-save-note]');if(note)note.textContent='Changes are saved together.';
    $$('.presets').forEach(function(box){var input=form.elements.namedItem(box.dataset.target);box.querySelectorAll('.pill').forEach(function(button){var on=String(input.value)===button.dataset.set;button.classList.toggle('on',on);button.setAttribute('aria-pressed',String(on));});});
    $$('.dayrow').forEach(function(row){row.classList.toggle('is-busy',row.querySelector('input[type=checkbox]').checked);});
  });
})();

/* ---- calendar: meal quick-view dialog ---- */
(function () {
  'use strict';
  var dlg = document.getElementById('meal-dialog'), dataEl = document.getElementById('meals-data');
  if (!dlg || !dataEl || typeof dlg.showModal !== 'function') return;   // no <dialog> support: links just open the full page
  var meals = JSON.parse(dataEl.textContent), body = document.getElementById('md-body');
  var SLOT = { breakfast: 'b', lunch: 'l', dinner: 'd' };
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function form(action, fields, label, cls, extra) {
    fields = Object.assign({csrf_token: document.querySelector('meta[name=csrf-token]').content}, fields);
    return '<form method="post" action="' + action + '" ' + (extra || '') + '>' + Object.keys(fields).map(function (k) { return '<input type="hidden" name="' + k + '" value="' + esc(fields[k]) + '">'; }).join('') +
      '<button class="btn sm ' + cls + '">' + label + '</button></form>';
  }
  function render(m) {
    var slotCls = { breakfast: 'breakfast', lunch: 'lunch', dinner: 'dinner' }[m.slot];
    var actions = m.closed ? '' : form('/meals/' + m.id + '/pin', { next: '/' }, m.pinned ? 'Unpin' : '📌 Pin', 'line');
    if (!m.closed && m.status === 'planned' && m.rating === null) actions +=
      form('/meals/' + m.id + '/swap', {}, '⇄ Swap meal', 'line', 'data-generate data-generate-title="Finding a replacement…"');
    if (!m.closed && m.status !== 'cooked') actions += form('/meals/' + m.id + '/status', { status: 'cooked', next: '/' }, '✓ Mark cooked', 'soft');
    if (!m.closed && m.status !== 'skipped') actions += form('/meals/' + m.id + '/status', { status: 'skipped', next: '/' }, 'Skip', 'ghost');
    if (!m.closed && m.status !== 'planned') actions += form('/meals/' + m.id + '/status', { status: 'planned', next: '/' }, 'Reset', 'ghost');
    actions += '<a class="btn sm primary" href="/meals/' + m.id + '" style="margin-left:auto">Full recipe →</a>';
    body.innerHTML =
      '<div class="md-head event ' + slotCls + '" style="position:static;height:auto;width:auto;animation:none;box-shadow:none;border-radius:0;border:0">' +
        '<button type="button" class="iconbtn md-x" data-close aria-label="Close">✕</button>' +
        '<span class="chip">' + esc(m.day) + ' · ' + esc(m.slot) + (m.pinned ? ' · 📌 pinned' : '') + (m.status !== 'planned' ? ' · ' + esc(m.status) : '') + '</span>' +
        '<h2 id="md-title">' + esc(m.name) + '</h2></div>' +
      '<div class="md-body">' +
        '<div class="md-stats"><div><b>' + m.cook_minutes + ' min</b><span>cook time</span></div><div><b>' + m.calories + '</b><span>calories</span></div><div><b>' + m.protein + 'g</b><span>protein</span></div><div><b>$' + m.cost.toFixed(2) + '</b><span>cost</span></div></div>' +
        '<div class="md-note">👩‍🍳 <span>' + esc(m.when) + '</span></div>' +
        '<div><h3>Ingredients</h3><ul>' + m.ingredients.map(function (i) { return '<li>' + esc(i) + '</li>'; }).join('') + '</ul></div>' +
        '<div><h3>Steps</h3><ol>' + m.steps.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ol></div>' +
        '<div class="md-actions">' + actions + '</div></div>';
    dlg.showModal();
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a.event[data-meal]');
    if (a && !(e.metaKey || e.ctrlKey || e.shiftKey)) { var m = meals[a.getAttribute('data-meal')]; if (m) { e.preventDefault(); render(m); } return; }
    if (e.target.closest('[data-close]') || e.target === dlg) dlg.close();   // x button or backdrop
  });
})();

/* Desktop agenda shares the same meal cards and actions as the calendar. */
(function () {
  'use strict';
  var calendar = document.querySelector('.gcal');
  if (!calendar) return;
  var buttons = Array.from(document.querySelectorAll('[data-plan-view]'));
  function setView(view) {
    calendar.classList.toggle('is-agenda', view === 'agenda');
    buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.planView === view)); });
    try { localStorage.setItem('pj-plan-view', view); } catch (e) {}
  }
  var saved = 'calendar';
  try { if (localStorage.getItem('pj-plan-view') === 'agenda') saved = 'agenda'; } catch (e) {}
  setView(saved);
  buttons.forEach(function (b) { b.addEventListener('click', function () { setView(b.dataset.planView); }); });
})();

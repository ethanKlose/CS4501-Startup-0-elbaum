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
      if (steps[i]) steps[i].className = 'active';
      i++;
      if (i > steps.length) { clearInterval(genTimer); }
    }
    tick();
    genTimer = setInterval(tick, 1150);
  }
  window.PJ = window.PJ || {};
  window.PJ.showGenerating = showGenerating;
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (!f.matches || !f.matches('form[data-generate]')) return;
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

/* ---- survey wizard ---- */
(function () {
  'use strict';
  var form = document.getElementById('wizard');
  if (!form) return;
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var steps = $$('.wstep', form), tabs = $$('.wiz-tabs button', form), first = form.dataset.first === '1';
  var cur = 0;
  function go(i) {
    cur = Math.max(0, Math.min(steps.length - 1, i));
    steps.forEach(function (s, k) { s.classList.toggle('on', k === cur); });
    tabs.forEach(function (t, k) { t.classList.toggle('on', k === cur); t.classList.toggle('done', k < cur); });
    document.getElementById('wiz-progress').style.width = ((cur + 1) / steps.length * 100) + '%';
    form.classList.toggle('last', cur === steps.length - 1);
    steps.forEach(function (_, k) { form.classList.remove('step' + k); }); form.classList.add('step' + cur);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  tabs.forEach(function (t, k) { t.addEventListener('click', function () { go(k); }); });
  var next = form.querySelector('[data-next]'), prev = form.querySelector('[data-prev]');
  if (next) next.addEventListener('click', function () {
    var budget = form.elements.budget;  // step 1 requires a valid budget before moving on
    if (cur === 0 && first && (!budget.value || parseFloat(budget.value) < 30)) { budget.focus(); budget.reportValidity && budget.reportValidity(); return; }
    go(cur + 1);
  });
  if (prev) prev.addEventListener('click', function () { go(cur - 1); });
  form.addEventListener('keydown', function (e) {   // Enter inside the wizard means "Next", not "submit"
    if (first && e.key === 'Enter' && e.target.tagName === 'INPUT' && cur < steps.length - 1) { e.preventDefault(); next.click(); }
  });
  /* preset buttons fill their target input */
  $$('.presets', form).forEach(function (box) {
    var input = form.elements[box.getAttribute('data-target')];
    function sync() { $$('.pill', box).forEach(function (b) { b.classList.toggle('on', String(input.value) === b.getAttribute('data-set')); }); }
    box.addEventListener('click', function (e) { var b = e.target.closest('.pill'); if (!b) return; input.value = b.getAttribute('data-set'); sync(); input.dispatchEvent(new Event('input')); });
    input.addEventListener('input', sync); sync();
  });
  /* calorie field only when relevant */
  var cal = document.getElementById('cal-field');
  function syncGoal() { var g = form.querySelector('input[name=goal]:checked'); cal.classList.toggle('show', !!g && g.value === 'calorie_target'); }
  $$('input[name=goal]', form).forEach(function (r) { r.addEventListener('change', syncGoal); }); syncGoal();
  /* busy toggle tints the row */
  $$('.dayrow', form).forEach(function (row) { var cb = row.querySelector('input[type=checkbox]'); cb.addEventListener('change', function () { row.classList.toggle('is-busy', cb.checked); }); });
  /* jump to the first step that has a server-side error, otherwise start at 0 */
  var start = 0; steps.some(function (s, k) { if (s.getAttribute('data-has-error')) { start = k; return true; } });
  go(start);
  if (!first) form.classList.add('last');
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
    return '<form method="post" action="' + action + '" ' + (extra || '') + '>' + Object.keys(fields).map(function (k) { return '<input type="hidden" name="' + k + '" value="' + esc(fields[k]) + '">'; }).join('') +
      '<button class="btn sm ' + cls + '">' + label + '</button></form>';
  }
  function render(m) {
    var slotCls = { breakfast: 'breakfast', lunch: 'lunch', dinner: 'dinner' }[m.slot];
    var actions = form('/meals/' + m.id + '/pin', { next: '/' }, m.pinned ? 'Unpin' : '📌 Pin', 'line') +
      form('/meals/' + m.id + '/swap', {}, '⇄ Swap meal', 'line', 'data-generate data-generate-title="Finding a replacement…"');
    if (m.status !== 'cooked') actions += form('/meals/' + m.id + '/status', { status: 'cooked', next: '/' }, '✓ Mark cooked', 'soft');
    if (m.status !== 'skipped') actions += form('/meals/' + m.id + '/status', { status: 'skipped', next: '/' }, 'Skip', 'ghost');
    if (m.status !== 'planned') actions += form('/meals/' + m.id + '/status', { status: 'planned', next: '/' }, 'Reset', 'ghost');
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

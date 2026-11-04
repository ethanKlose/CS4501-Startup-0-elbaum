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

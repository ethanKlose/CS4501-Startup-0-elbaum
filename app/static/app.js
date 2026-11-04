/* PlateJoy front-end: small, dependency-free, progressive enhancement only. */
(function () {
  'use strict';
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

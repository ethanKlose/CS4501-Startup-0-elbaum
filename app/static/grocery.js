/* Persist check-offs and roll back every progress indicator when a save fails. */
(function () {
  'use strict';
  var boxes = Array.from(document.querySelectorAll('ul.grocery input[type=checkbox]'));
  var error = document.getElementById('grocery-error');
  function progress() {
    var left = boxes.filter(function (b) { return !b.checked; }).length;
    var remaining = document.getElementById('remaining');
    var bar = document.getElementById('gbar');
    if (remaining) remaining.textContent = left;
    if (bar) bar.style.width = (boxes.length ? (boxes.length - left) / boxes.length * 100 : 0) + '%';
  }
  progress(); // Use the same precision on initial render and after a rollback.
  boxes.forEach(function (box) {
    box.addEventListener('change', async function () {
      var previous = !box.checked;
      box.disabled = true; // One in-flight update per item.
      if (error) error.hidden = true;
      box.closest('li').classList.toggle('done', box.checked);
      progress();
      try {
        var response = await fetch('/grocery/toggle', {
          method: 'POST', body: new URLSearchParams({key: box.dataset.key, checked: box.checked, plan_id: document.querySelector('[data-plan-id]').dataset.planId})
        });
        // A redirected login page must not be mistaken for a successful save.
        if (response.status !== 204) throw new Error('Save failed');
      } catch (e) {
        box.checked = previous;
        box.closest('li').classList.toggle('done', previous);
        progress();
        if (error) error.hidden = false;
      } finally {
        box.disabled = false;
      }
    });
  });
})();

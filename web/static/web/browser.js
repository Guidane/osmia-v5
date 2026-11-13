/* A list beside its tree, with the details of the row picked on the right (.parts-browser): a row (tr[data-part], its
   details at data-brief-url) picked by a click, Enter or the arrow keys shows them in [data-detail], and is kept in
   the address (?<data-param of the browser, else "part">=<its data-part>). A "brief" event on the document tells
   when details were put there (to draw what they hold). Ticking rows: [data-pick-all] ticks them all; a
   [data-labels] button opens the labels of those ticked (none ticked: of all listed). */
(function () {
  'use strict';
  var root = document.querySelector('.parts-browser');
  if (!root) return;
  var detail = root.querySelector('[data-detail]'), rows = Array.prototype.slice.call(root.querySelectorAll('tr[data-part]'));
  var param = root.dataset.param || 'part', asked = 0;
  function told() { document.dispatchEvent(new CustomEvent('brief', { detail: detail })); }
  function pick(row) {
    rows.forEach(function (r) { r.classList.toggle('on', r === row); });
    var url = new URL(location.href);
    url.searchParams.set(param, row.dataset.part);
    history.replaceState(null, '', url);
    var mine = ++asked;
    fetch(row.dataset.briefUrl, { headers: { 'X-Requested-With': 'fetch' } }).then(function (r) { return r.text(); }).then(function (html) {
      if (mine !== asked) return;
      detail.innerHTML = html;
      told();
    });
  }
  rows.forEach(function (row, i) {
    row.addEventListener('click', function (e) {
      if (e.target.closest('a, input, button, select, form')) return;   // a link still opens its page; ticking stays ticking
      pick(row);
    });
    row.addEventListener('keydown', function (e) {
      if (e.target !== row) return;
      var to = e.key === 'ArrowDown' ? rows[i + 1] : e.key === 'ArrowUp' ? rows[i - 1] : e.key === 'Enter' ? row : null;
      if (!to) return;
      e.preventDefault();
      to.focus();
      pick(to);
    });
  });
  if (detail) told();

  document.querySelectorAll('[data-labels]').forEach(function (b) {
    b.addEventListener('click', function () {
      var boxes = document.querySelectorAll('input[name=pick]'), ticked = Array.prototype.filter.call(boxes, function (x) { return x.checked; });
      var ids = (ticked.length ? ticked : Array.prototype.slice.call(boxes)).map(function (x) { return x.value; });
      if (ids.length) location.href = b.dataset.labels + '?ids=' + ids.join(',');
    });
  });
  var all = document.querySelector('input[data-pick-all]');
  if (all) all.addEventListener('change', function () { document.querySelectorAll('input[name=pick]').forEach(function (x) { x.checked = all.checked; }); });
})();

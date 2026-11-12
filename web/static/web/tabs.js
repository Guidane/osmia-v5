/* A page in tabs: [data-tabs] links (data-tab="name") show the [data-panel="name"] of that name, the others hidden;
   the tab in the address (#name) shown, else the first. A tab shown fires a resize (a drawing in it fits itself). */
(function () {
  'use strict';
  var links = document.querySelectorAll('[data-tabs] [data-tab]'), panels = document.querySelectorAll('[data-panel]');
  if (!links.length) return;
  function show(name) {
    if (!document.querySelector('[data-panel="' + name + '"]')) name = links[0].dataset.tab;
    links.forEach(function (a) { a.classList.toggle('on', a.dataset.tab === name); });
    panels.forEach(function (p) { p.hidden = p.dataset.panel !== name; });
    window.dispatchEvent(new Event('resize'));
  }
  links.forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      history.replaceState(null, '', '#' + a.dataset.tab);
      show(a.dataset.tab);
    });
  });
  show(location.hash.slice(1));
})();

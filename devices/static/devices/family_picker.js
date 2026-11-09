/* The connector form's family popup: the branches of families as a tree on the left, the families of the one picked
   (and of those under it) with their face (the pin side; a socket gender's mirrored), found by
   name; picking the family (any gender) or one gender fills the field and shows it on the button that opens it. */
(function () {
  'use strict';
  var input = document.querySelector('[data-family-value]');
  if (!input || input.dataset.ready) return;
  input.dataset.ready = '1';
  var open = document.querySelector('[data-family-open]'), clear = document.querySelector('[data-family-clear]');
  var dialog = document.querySelector('.family-finder'), cards = document.querySelector('[data-family-cards]');
  var search = document.querySelector('[data-family-q]');
  var data = JSON.parse(document.getElementById('family-data').textContent);
  if (Array.isArray(data)) data = { families: data, tree: [] };   // as a server not yet restarted after an update sends it
  data.tree = data.tree || [];
  var families = data.families || [];
  var treeNav = document.querySelector('[data-family-tree]'), branch = null;   // the branch shown (null: all)

  function now() { return input.dataset.current || input.value; }   // what it is (a part: its gender or family)
  function set(value) {
    input.value = value;
    input.dataset.current = value;
    open.textContent = value || 'Choose…';
    clear.hidden = !value;
    dialog.close();
  }
  function mirrored(face) {
    return Object.assign({}, face, {
      contacts: face.contacts.map(function (c) { return [c[0], face.w - c[1], c[2]]; }),
      outline: (face.outline || []).map(function (p) { return [face.w - p[0], p[1]]; })
    });
  }
  function button(parent, label, value) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn small' + (now() === value ? ' primary' : '');
    b.textContent = label;
    b.addEventListener('click', function () { set(value); });
    parent.appendChild(b);
  }
  function show() {
    var q = search.value.trim().toLowerCase();
    cards.innerHTML = '';
    families.filter(function (f) {
      return (!q || f.name.toLowerCase().indexOf(q) !== -1) && (!branch || branch.below.indexOf(f.branch) !== -1);
    }).forEach(function (f) {
      var card = document.createElement('section');
      card.className = 'family-card' + (now() === f.name || now().indexOf(f.name + ' / ') === 0 ? ' on' : '');
      var title = document.createElement('h4');
      title.textContent = f.name;
      card.appendChild(title);
      if (f.face) {
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'pinout-drawing');
        card.appendChild(svg);
        Pinout.face(svg, { face: f.face, pins: f.face.contacts.map(function (c) { return [c[0], '']; }) });
      }
      var picks = document.createElement('div');
      picks.className = 'family-genders';
      f.genders.forEach(function (g) { button(picks, g.name, g.value); });
      button(picks, 'Any', f.name);
      card.appendChild(picks);
      if (f.face) {   // the socket genders' faces: mirrored, shown as they will be drawn
        picks.querySelectorAll('button').forEach(function (b, i) {
          var g = f.genders[i];
          if (!g) return;
          b.addEventListener('mouseenter', function () { Pinout.face(svg, { face: g.socket ? mirrored(f.face) : f.face, pins: f.face.contacts.map(function (c) { return [c[0], '']; }) }); });
        });
      }
      cards.appendChild(card);
    });
    if (!cards.children.length) cards.innerHTML = '<p class="muted small pad">No families here.</p>';
    treeNav.querySelectorAll('button').forEach(function (b, i) { b.classList.toggle('on', i === 0 ? !branch : data.tree[i - 1] === branch); });
  }
  function treeButton(label, node, depth) {   // a branch on the left: its families (and those of the branches under it)
    var b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    b.style.paddingLeft = (0.5 + depth) + 'em';
    b.addEventListener('click', function () { branch = node; show(); });
    treeNav.appendChild(b);
  }
  treeButton('All families', null, 0);
  data.tree.forEach(function (node) { treeButton(node.name, node, node.depth + 1); });
  treeNav.hidden = !data.tree.length;
  open.addEventListener('click', function () {   // opened on the branch of what it is now
    var current = families.filter(function (f) { return now() === f.name || now().indexOf(f.name + ' / ') === 0; })[0];
    branch = current && current.branch ? data.tree.filter(function (n) { return n.id === current.branch; })[0] || null : null;
    search.value = '';
    show();
    dialog.showModal();
    search.focus();
  });
  clear.addEventListener('click', function () { set(''); });
  search.addEventListener('input', show);
  document.querySelector('[data-family-close]').addEventListener('click', function () { dialog.close(); });
})();

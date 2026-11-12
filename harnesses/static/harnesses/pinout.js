/* A harness's pinout drawn. Each wire is a row: its contact number on the left, its contact number on the right, the
   connector upright beside each column and the connector's face (its pins as they sit: a single row, two rows, a
   D-sub, a circle, a grid) on the far side.

   View: wires in their colours; a twisted set crosses near each end, just past a shield (a pair: the first wire in a V down to the set's bottom
   row, the other in a Λ up to its top row; more wires: in turn the bottom one rises to the top as the others drop a row), a shielded set has an ellipse at each end whose bottom sits on the
   shield wire's row, the shield dashed between them. Clicking where a set's wires run (or its chip) lights up the set:
   its contacts and its pins on both faces.

   Edit: pick a pin on a face on the left, then one on the right (or the other way): a new row joins them. Each row
   shows in the middle the set to put it in (or a new one), its colour, and ✕; its set is drawn as in the view (twisted,
   shielded) as soon as it is picked. Connectors are added on either side, their family changed or taken away. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var PITCH = 26, R = 10, ROW = 34, C = 13;

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(e);
    return e;
  }
  function html(tag, attrs, parent) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, value, cls) { var t = el('text', { x: x, y: y, class: cls }, parent); t.textContent = value; return t; }
  function natural(a, b) { return String(a).localeCompare(String(b), undefined, { numeric: true }); }
  function twisted(type) { return /twisted/i.test(type || ''); }
  function shielded(type) { return /shielded/i.test(type || ''); }

  // a connector's face (inventory.faces: as you look at it, from its family), stood upright when it is wider than tall:
  // {w, h, shape, box: [x, y, w, h] its outline, turned, at: [[number, x, y]]}
  function face(end, flat) {
    var F = end.face, high = F.below || F.h, turned = !flat && F.w > F.h;
    var corners = F.outline || [];
    if (!turned) return { w: F.w, h: F.h, shape: F.shape, box: [0, 0, F.w, high], turned: false, at: F.contacts, outline: corners };
    return { w: F.h, h: F.w, shape: F.shape, box: [F.h - high, 0, high, F.w], turned: true,
             at: F.contacts.map(function (c) { return [c[0], F.h - c[2], c[1]]; }),
             outline: corners.map(function (p) { return [F.h - p[1], p[0]]; }) };
  }
  function outline(parent, f, fx, fy) {   // its outline: its own corners, round, a D-sub (the wide side up, or right when stood up), a box
    var x = fx + f.box[0], y = fy + f.box[1], w = f.box[2], h = f.box[3], k = 14;
    if (f.shape === 'custom' && f.outline.length > 2) {   // corners of its own
      return el('path', { d: 'M' + f.outline.map(function (p) { return (fx + p[0]) + ',' + (fy + p[1]); }).join(' L') + ' Z',
                          class: 'pd-face', 'stroke-linejoin': 'round' }, parent);
    }
    if (f.shape === 'circle') return el('circle', { cx: x + w / 2, cy: y + h / 2, r: Math.min(w, h) / 2, class: 'pd-face' }, parent);
    if (f.shape === 'dsub') {
      var d = f.turned ? 'M' + x + ',' + (y + k) + ' L' + (x + w) + ',' + y + ' V' + (y + h) + ' L' + x + ',' + (y + h - k) + ' Z'
                       : 'M' + x + ',' + y + ' H' + (x + w) + ' L' + (x + w - k) + ',' + (y + h) + ' H' + (x + k) + ' Z';
      return el('path', { d: d, class: 'pd-face', 'stroke-linejoin': 'round' }, parent);
    }
    return el('rect', { x: x, y: y, width: w, height: h, rx: 6, class: 'pd-face' }, parent);
  }


  function sides(data) {   // each end left or right, so that wires go across; one added on a side stays there
    var side = {}, count = { left: 0, right: 0 }, known = {};
    data.ends.forEach(function (e) { known[e.id] = true; });
    function spread(start) {
      var queue = [start];
      while (queue.length) {
        var id = queue.shift();
        data.wires.forEach(function (w) {
          var o = w.from === id ? w.to : w.to === id ? w.from : null;
          if (o === null || side[o] || !known[o]) return;
          side[o] = side[id] === 'left' ? 'right' : 'left';
          count[side[o]] += 1;
          queue.push(o);
        });
      }
    }
    data.ends.forEach(function (e) { if (e.side && !side[e.id]) { side[e.id] = e.side; count[e.side] += 1; } });
    data.ends.forEach(function (e) { if (e.side) spread(e.id); });
    data.ends.forEach(function (e) {
      if (side[e.id]) return;
      side[e.id] = count.left <= count.right ? 'left' : 'right';
      count[side[e.id]] += 1;
      spread(e.id);
    });
    return side;
  }

  function mount(root, data, colours) {
    var svg = root.querySelector('svg'), bar = root.querySelector('.set-chips');
    var state = { data: data, editing: false, changed: false, from: null, picked: null, drain: null };

    function post(fields) {
      var body = new FormData();
      Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
      return fetch(root.dataset.url, { method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-CSRFToken': root.dataset.csrf } })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (d) { state.data = d; state.changed = true; state.from = null; state.drain = null; render(); });
    }

    function purposePicker(current, onPick) {
      var dialog = document.querySelector('dialog.purpose-finder');
      if (!dialog) {
        dialog = html('dialog', { class: 'finder purpose-finder', 'aria-label': 'Purpose' }, document.body);
        dialog.innerHTML = '<div class="finder-head"><h3>Purpose</h3><input type="search" data-purpose-q aria-label="Purpose" autocomplete="off">' +
          '<button type="button" class="btn small primary" data-purpose-use>Use</button><button type="button" class="btn small" data-purpose-clear>Clear</button>' +
          '<span class="spacer"></span><button type="button" class="btn small ghost" data-purpose-close title="Close">✕</button></div>' +
          '<div class="finder-body"><nav class="finder-tree" data-purpose-tree aria-label="Kinds"></nav><div class="purpose-list" data-purpose-list></div></div>';
        dialog.querySelector('[data-purpose-close]').addEventListener('click', function () { dialog.close(); });
      }
      var q = dialog.querySelector('[data-purpose-q]'), nav = dialog.querySelector('[data-purpose-tree]'), list = dialog.querySelector('[data-purpose-list]');
      var nodes = state.data.purposes || [], node = null;
      function done(value) { dialog.close(); onPick(value); }
      function show() {
        var find = q.value.trim().toLowerCase();
        list.innerHTML = '';
        var groups = node ? node.groups : [].concat.apply([], nodes.filter(function (n) { return n.depth === 0; }).map(function (n) { return n.groups; }));
        groups.forEach(function (g) {
          var items = g[1].filter(function (v) { return !find || v.toLowerCase().indexOf(find) !== -1; });
          if (!items.length) return;
          var h = html('h5', {}, list);
          h.textContent = g[0];
          var row = html('div', { class: 'purpose-items' }, list);
          items.forEach(function (v) {
            var b = html('button', { type: 'button', class: 'btn small' + (v === current ? ' primary' : ''), 'data-purpose': v }, row);
            b.textContent = v;
            b.addEventListener('click', function () { done(v); });
          });
        });
        nav.querySelectorAll('button').forEach(function (b, i) { b.classList.toggle('on', i === 0 ? !node : nodes[i - 1] === node); });
      }
      nav.innerHTML = '';
      [{ name: 'All', depth: -1 }].concat(nodes).forEach(function (n, i) {
        var b = html('button', { type: 'button' }, nav);
        b.textContent = n.name;
        b.style.paddingLeft = (1.5 + n.depth) + 'em';
        b.addEventListener('click', function () { node = i === 0 ? null : n; show(); });
      });
      q.value = current || '';
      q.oninput = show;
      q.onkeydown = function (e) { if (e.key === 'Enter') { e.preventDefault(); done(q.value.trim()); } };
      dialog.querySelector('[data-purpose-use]').onclick = function () { done(q.value.trim()); };
      dialog.querySelector('[data-purpose-clear]').onclick = function () { done(''); };
      q.value = '';
      show();
      q.value = current || '';
      dialog.showModal();
      q.select();
    }

    function render() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      bar.textContent = '';
      var data = state.data, editing = state.editing;
      svg.classList.toggle('editing', editing);
      var side = sides(data), faces = {}, widest = { left: 0, right: 0 }, byId = {}, index = {};
      data.ends.forEach(function (e, i) {
        byId[e.id] = e; index[e.id] = i;
        faces[e.id] = face(e);
        widest[side[e.id]] = Math.max(widest[side[e.id]], faces[e.id].w);
      });
      var signal = {};
      data.ends.forEach(function (e) { e.pins.forEach(function (p) { signal[e.id + ':' + p[0]] = p[1]; }); });

      // the rows: each wire with its left end first
      var rows = data.wires.map(function (w) {
        var flip = side[w.from] === 'right' && side[w.to] === 'left', loop = w.from === w.to;
        var from = { end: w.from, pin: w.from_pin }, to = { end: w.to, pin: w.to_pin };
        return { w: w, a: flip ? to : from, b: flip ? from : to, same: side[w.from] === side[w.to], loopback: loop };
      });
      var sets = {}, setOrder = [];
      rows.forEach(function (r) {
        if (!r.w.set) return;
        var s = sets[r.w.set] = sets[r.w.set] || { name: r.w.set, type: '', rows: [], first: null };
        s.rows.push(r);
        if (r.w.type !== 'Shield') s.type = s.type || r.w.type;
        if (s.first === null || natural(r.a.pin, s.first) < 0) s.first = r.a.pin;
      });
      Object.keys(sets).forEach(function (k) { if (!sets[k].type) sets[k].type = 'Shield'; setOrder.push(sets[k]); });
      setOrder.sort(function (a, b) { return natural(a.first, b.first); });
      var rank = {};
      setOrder.forEach(function (s, i) { rank[s.name] = i; });

      // grouped by the two ends they join, each group's rows by set (its shield last), then by pin
      var groups = {}, list = [];
      rows.forEach(function (r) {
        var k = r.a.end + '|' + r.b.end;
        if (!groups[k]) list.push(groups[k] = { left: r.a.end, right: r.b.end, rows: [], same: r.same, loop: r.loopback });
        groups[k].rows.push(r);
      });
      list.sort(function (a, b) { return index[a.left] - index[b.left] || index[a.right] - index[b.right]; });
      list.forEach(function (g) {
        g.rows.sort(function (p, q) {
          var kp = p.w.set ? rank[p.w.set] : setOrder.length, kq = q.w.set ? rank[q.w.set] : setOrder.length;
          return kp - kq || (p.w.type === 'Shield') - (q.w.type === 'Shield') || natural(p.a.pin, q.a.pin);
        });
      });
      var seen = {};
      list.forEach(function (g) { seen[g.left] = true; if (!g.same) seen[g.right] = true; });
      var spare = { left: [], right: [] };   // ends no wire joins yet
      data.ends.forEach(function (e) { if (!seen[e.id]) spare[side[e.id]].push(e.id); });
      for (var i = 0; i < Math.max(spare.left.length, spare.right.length); i++) {
        list.push({ left: spare.left[i], right: spare.right[i], rows: [], same: false });
      }

      var x = {};
      x.leftFace = 10; x.leftBar = 10 + widest.left + 30; x.leftNum = x.leftBar + 34;
      x.left = x.leftNum + C;
      // the middle takes all the width there is (and no less than it needs)
      var fixed = x.left + C + 20 + 46 + widest.right + 10, room = (svg.parentNode.clientWidth || 0) - 20;
      state.width = svg.parentNode.clientWidth;
      x.right = x.left + Math.max(editing ? 620 : 420, room - fixed);
      x.rightNum = x.right + C; x.rightBar = x.rightNum + 20; x.rightFace = x.rightBar + 46;
      var width = x.rightFace + widest.right + 10, mid = (x.left + x.right) / 2, TWIST = 25;   // half the twist's width

      var under = el('g', {}, svg), wiresG = el('g', {}, svg), over = el('g', {}, svg), areas = el('g', {}, svg), tools = el('g', {}, svg);
      var lit = {};
      function remember(key, node) { (lit[key] = lit[key] || []).push(node); }

      function drawFace(e, y0) {
        var left = side[e.id] === 'left', f = faces[e.id];
        var fx = left ? x.leftFace + widest.left - f.w : x.rightFace, fy = y0 - 10;
        text(over, left ? x.leftFace : width - 10, y0 - 34, e.designator + (e.what ? ' · ' + e.what : ''), 'pd-title' + (left ? '' : ' end'));
        outline(under, f, fx, fy);
        if (editing) {   // its family (and gender) changed in the family popup, or taken away with its wires
          var fo = el('foreignObject', { x: left ? x.leftFace : width - 10 - 240, y: fy + f.h + 6, width: 240, height: 28 }, tools);
          var box = html('div', { class: 'pd-tools pd-end-tools' + (left ? '' : ' end') }, fo);
          var fam = html('button', { type: 'button', class: 'btn small', title: 'Family' }, box);
          fam.textContent = e.used || 'Family…';
          fam.addEventListener('click', function () {
            if (window.FamilyPicker) FamilyPicker.open(e.used, function (value) { post({ action: 'end_set', end: e.id, used: value }); });
          });
          var drop = html('button', { type: 'button', class: 'btn small ghost', title: 'Take ' + e.designator + ' away' }, box);
          drop.textContent = '✕';
          drop.addEventListener('click', function () {
            if (confirm('Take ' + e.designator + ' away, with its wires?')) post({ action: 'end_delete', end: e.id });
          });
        }
        var has = {};
        e.pins.forEach(function (p) { has[p[0]] = true; });
        f.at.forEach(function (p) {
          var g = el('g', { class: 'pd-pin' + (has[p[0]] ? '' : ' empty'), 'data-end': e.id, 'data-pin': p[0] }, over);
          el('title', {}, g).textContent = e.designator + ':' + p[0] + (signal[e.id + ':' + p[0]] ? ' ' + signal[e.id + ':' + p[0]] : '');
          el('circle', { cx: fx + p[1], cy: fy + p[2], r: R }, g);
          text(g, fx + p[1], fy + p[2] + 4, p[0], 'pd-num');
          remember(e.id + ':' + p[0], g);
          if (state.from && state.from.end === e.id && state.from.pin === p[0]) g.classList.add('chosen');
          if (editing) g.addEventListener('click', function () { pick(e.id, p[0], g); });
        });
        return editing ? f.h + 26 : f.h - 10;   // editing: its tools below it
      }
      function shieldTo(set, sideOf, end, pin) {   // a shielded set's shield joined to a contact on one side (pin '': not)
        var s = sets[set], own = s.rows.filter(function (r) { return r.w.type === 'Shield'; })[0];
        var inner = s.rows.filter(function (r) { return r.w.type !== 'Shield'; })[0];
        var a = own ? { end: own.a.end, pin: own.a.pin } : { end: inner.a.end, pin: '' };
        var b = own ? { end: own.b.end, pin: own.b.pin } : { end: inner.b.end, pin: '' };
        if (sideOf === 'left') a = { end: end === null ? a.end : end, pin: pin }; else b = { end: end === null ? b.end : end, pin: pin };
        state.drain = null;
        post({ action: 'shield', set: set, a_end: a.end, a_pin: a.pin, b_end: b.end, b_pin: b.pin });
      }
      function pick(end, pin, node) {   // edit: a pin on one side, then one on the other side, joined by a new wire
        if (state.drain) {   // a shield's circle picked first: the shield goes to this contact (one on its side)
          if (side[end] === (state.drain.on || state.drain.side)) shieldTo(state.drain.set, state.drain.side, end, pin);
          return;
        }
        if (state.from && (side[state.from.end] !== side[end] || (state.from.end === end && state.from.pin !== pin))) {   // across, or a loopback
          var a = state.from;
          post({ action: 'add', from_end: a.end, from_pin: a.pin, to_end: end, to_pin: pin });
          return;
        }
        var again = state.from && state.from.end === end && state.from.pin === pin;
        svg.querySelectorAll('.chosen').forEach(function (n) { n.classList.remove('chosen'); });
        state.from = again ? null : { end: end, pin: pin };
        if (!again) node.classList.add('chosen');
      }
      function contact(at, left, y, named) {
        var cx = left ? x.leftNum : x.rightNum, g = el('g', { class: 'pd-contact' }, over);
        el('title', {}, g).textContent = byId[at.end].designator + ':' + at.pin + (signal[at.end + ':' + at.pin] ? ' ' + signal[at.end + ':' + at.pin] : '');
        el('line', { x1: left ? x.leftBar + 12 : cx + C, y1: y, x2: left ? cx - C : x.rightBar, y2: y, class: 'pd-stub' }, under);
        el('circle', { cx: cx, cy: y, r: C }, g);
        text(g, cx, y + 4, at.pin, 'pd-num');
        if (named) text(g, cx + C + 4, y + 4, byId[at.end].designator, 'pd-sub');
        remember(at.end + ':' + at.pin, g);
        if (state.from && state.from.end === at.end && state.from.pin === at.pin) g.classList.add('chosen');
        if (editing) g.addEventListener('click', function () { pick(at.end, at.pin, g); });
        return left ? x.left : x.right;
      }
      // a contact with several wires (a splice): drawn once, at its first row; its other rows branch off beside it
      var splices = {}, lanes = { left: 0, right: 0 };   // each splice on a side its own lane
      function place(r, at, left, named) {
        if (at.pin === '') return left ? x.left + EL : x.right - ER;   // a shield not joined on this side: from its ellipse
        var key = (left ? 'L' : 'R') + at.end + ':' + at.pin, s = splices[key];
        if (!s) {
          splices[key] = { left: left, rows: [r] };
          return contact(at, left, r.y, named);
        }
        if (s.x === undefined) {   // viewing: in the middle, between the twists; editing: by the contacts
          var lane = lanes[left ? 'left' : 'right']++, off = editing ? x.right - mid - 12 : -12;
          s.x = left ? mid - off + lane * 20 : mid + off - lane * 20;   // lanes well apart
        }
        s.rows.push(r);
        return s.x;
      }

      // the shields' ellipses (and past them the twists) stand clear of the tags by the contacts: gauge, purpose
      function measure(label, cls) {
        var g = el('g', { class: 'pd-tag ' + cls }, svg), t = text(g, 0, -50, label, 'pd-tag-text'), long = 0;
        try { long = t.getComputedTextLength(); } catch (err) { /* not drawn yet */ }
        svg.removeChild(g);
        return Math.max((long || label.length * 5.6) + 8, 22) + 4;
      }
      var reach = { left: 0, right: 0 }, BOX = 76;   // editing: a box's width (and its gap)
      if (editing) rows.forEach(function (r) { reach[r.loopback && side[r.w.from] === 'right' ? 'right' : 'left'] = 2 * BOX; });
      else rows.forEach(function (r) {
        var w = r.w, g = w.gauge ? measure(w.gauge, 'pd-gauge') : 0;
        if (r.loopback) {
          var at = side[w.from] === 'right' ? 'right' : 'left';
          reach[at] = Math.max(reach[at], g + (w.signal ? measure(w.signal, 'pd-label') : 0), g + (w.to_signal ? measure(w.to_signal, 'pd-label') : 0));
          return;
        }
        reach.left = Math.max(reach.left, g + (w.signal ? measure(w.signal, 'pd-label') : 0));
        reach.right = Math.max(reach.right, g);
      });
      var EL = Math.max(70, reach.left + 28), ER = Math.max(70, reach.right + 28);
      function E(left) { return left ? EL : ER; }
      var bigHalf = TWIST;
      setOrder.forEach(function (s) {
        var n = s.rows.filter(function (r) { return r.w.type !== 'Shield'; }).length;
        if (twisted(s.type) && n > 2) bigHalf = Math.max(bigHalf, n * TWIST * 0.8);
      });

      // loopbacks: the wires of a set (or a wire on its own) go out one under another and come back in the opposite
      // order, the first the outermost: nested, none crossing; a shielded set keeps a row out and back for its shield
      var LOOP = Math.max(240, Math.max(EL, ER) + (editing ? 380 : 30 + 2 * bigHalf + 40)), loopShield = {};   // past a row's tools
      function loopUnits(g) {
        var units = [], bySet = {};
        g.rows.forEach(function (r) {
          if (!r.w.set) { units.push([r]); return; }
          if (!bySet[r.w.set]) units.push(bySet[r.w.set] = []);
          bySet[r.w.set].push(r);
        });
        return units;
      }
      function shieldRow(u) {   // a shielded set without its shield wire: a row kept for where it would be
        var s = u[0].w.set && sets[u[0].w.set];
        return !!(s && shielded(s.type)) && !u.some(function (r) { return r.w.type === 'Shield'; });
      }
      function loopRows(g) { return loopUnits(g).reduce(function (n, u) { return n + 2 * u.length + (shieldRow(u) ? 2 : 0); }, 0); }
      function loopPlace(g, y0, L) {
        var i = 0, edge = L ? x.left : x.right, dir = L ? 1 : -1;
        loopUnits(g).forEach(function (u) {
          var keep = shieldRow(u), m = u.length + (keep ? 1 : 0);
          u.forEach(function (r, j) {
            r.loop = { L: L, edge: edge, dir: dir, unit: u, turn: edge + dir * (LOOP + (m - 1 - j) * 20) };
            r.y = y0 + i++ * ROW;
            if (r.a.pin) contact(r.a, L, r.y);
          });
          if (keep) loopShield[u[0].w.set] = { out: y0 + i++ * ROW, back: y0 + i++ * ROW, turn: edge + dir * LOOP };
          u.slice().reverse().forEach(function (r) {
            r.yBack = y0 + i++ * ROW;
            if (r.b.pin) contact(r.b, L, r.yBack);
          });
          u.forEach(function (r) {
            var start = r.a.pin ? edge : edge + dir * E(L);
            r.ax = L ? start : r.loop.turn;
            r.bx = L ? r.loop.turn : start;
          });
        });
      }

      // a face runs alongside the groups of its connector; a group beside another connector starts below it
      if (editing) {   // a connector added on either side: its family (and gender) picked in the family popup
        [['left', x.leftFace], ['right', width - 10 - 150]].forEach(function (s) {
          var fo = el('foreignObject', { x: s[1], y: 6, width: 150, height: 30 }, tools);
          var box = html('div', { class: 'pd-tools' + (s[0] === 'right' ? ' end' : '') }, fo);
          var b = html('button', { type: 'button', class: 'btn small', 'data-add-end': s[0] }, box);
          b.textContent = '＋ Connector';
          b.addEventListener('click', function () {
            if (window.FamilyPicker) FamilyPicker.open('', function (value) { post({ action: 'end_add', side: s[0], used: value }); });
            else post({ action: 'end_add', side: s[0], used: '' });
          });
        });
      }
      var y = editing ? 110 : 70, GAP = 90, faced = {}, beside = { left: { id: null, until: 0 }, right: { id: null, until: 0 } };
      var bars = { left: null, right: null };
      list.forEach(function (g) {
        var y0 = y, n = g.loop ? loopRows(g) : g.rows.length, bottom = n ? (n - 1) * ROW + C : 0;
        var here = g.loop ? [[side[g.left], g.left]] :
          [['left', g.left]].concat(g.same ? [] : [['right', g.right]]).filter(function (s) { return s[1] !== undefined; });
        here.forEach(function (s) { if (beside[s[0]].id !== s[1]) y0 = Math.max(y0, beside[s[0]].until + GAP); });
        here.forEach(function (s) {
          if (faced[s[1]]) return;
          faced[s[1]] = true;
          beside[s[0]] = { id: s[1], until: y0 + drawFace(byId[s[1]], y0) };
        });
        here.forEach(function (s) { if (beside[s[0]].id !== s[1]) beside[s[0]] = { id: s[1], until: y0 + bottom }; });
        var own = { left: false, right: false };   // a contact of its own on that side (not only splices from above)
        if (g.loop) {   // out from the connector and back into it
          var L = side[g.left] !== 'right';
          loopPlace(g, y0, L);
          [[L ? 'left' : 'right', g.left, L ? x.leftBar : x.rightBar]].forEach(function (b) {
            var top = y0 - C - 6, end = y0 + (n - 1) * ROW + C + 6, last = bars[b[0]];
            if (last && last.id === b[1]) { last.rect.setAttribute('height', end - last.top); return; }
            bars[b[0]] = { id: b[1], top: top, rect: el('rect', { x: b[2], y: top, width: 12, height: end - top, rx: 3, class: 'pd-bar' }, under) };
            text(over, b[2] + 6, top - 6, byId[b[1]].designator, 'pd-bar-label');
          });
          y = y0 + bottom + GAP;
          return;
        }
        g.rows.forEach(function (r, i) {
          r.y = y0 + i * ROW;
          r.ax = place(r, r.a, true);
          r.bx = place(r, r.b, false, g.same);
          if (r.ax === x.left) own.left = true;
          if (r.bx === x.right) own.right = true;
        });
        // the connector's bar; one after another of the same connector on that side make one longer bar
        [['left', g.left, x.leftBar, own.left]].concat(g.same ? [] : [['right', g.right, x.rightBar, own.right]]).forEach(function (b) {
          if (!b[3]) return;
          var top = y0 - C - 6, end = y0 + (n - 1) * ROW + C + 6, last = bars[b[0]];
          if (last && last.id === b[1]) { last.rect.setAttribute('height', end - last.top); return; }
          bars[b[0]] = { id: b[1], top: top, rect: el('rect', { x: b[2], y: top, width: 12, height: end - top, rx: 3, class: 'pd-bar' }, under) };
          text(over, b[2] + 6, top - 6, byId[b[1]].designator, 'pd-bar-label');
        });
        y = y0 + bottom + GAP;
      });
      y = Math.max(y, beside.left.until + GAP, beside.right.until + GAP);

      Object.keys(splices).forEach(function (key) {   // a splice's rows (each but the contact's own): from past their corner
        var s = splices[key];
        s.rows.slice(1).forEach(function (r) {
          var k = Math.min(14, (r.y - s.rows[0].y) / 2);
          if (s.left) r.ax = s.x + k; else r.bx = s.x - k;
        });
      });

      // the tags by a wire's ends: its gauge by the connector (before any shield and twist); a spliced wire's gauge
      // on both sides, and its length by where it joins the splice
      var spliceOf = {};
      Object.keys(splices).forEach(function (key) {
        var s = splices[key];
        if (s.rows.length > 1) s.rows.forEach(function (r, i) { spliceOf[(s.left ? 'L' : 'R') + r.w.id] = { s: s, first: i === 0 }; });
      });
      var outer = { left: -Infinity, right: Infinity };   // the splices' outermost lanes on each side
      Object.keys(splices).forEach(function (key) {
        var s = splices[key];
        if (s.x === undefined) return;
        if (s.left) outer.left = Math.max(outer.left, s.x); else outer.right = Math.min(outer.right, s.x);
      });
      function tag(at, y, label, dir, cls, id) {   // a tag from ``at`` going ``dir``; where it ends
        var g = el('g', { class: 'pd-tag ' + cls, 'data-tag-of': id }, over), t = text(g, 0, y + 3.5, label, 'pd-tag-text'), long = 0;
        try { long = t.getComputedTextLength(); } catch (err) { /* not drawn yet */ }
        var w = Math.max((long || label.length * 5.6) + 8, 22), cx = at + dir * w / 2;
        t.setAttribute('x', cx);
        g.insertBefore(el('rect', { x: cx - w / 2, y: y - 7, width: w, height: 14, rx: 4 }), t);
        return at + dir * (w + 4);
      }
      rows.forEach(function (r) {
        r.tagEnd = {};
        if (r.y === undefined) return;
        if (editing) {   // its boxes where what they set shows: gauge, purpose by the contact; set over the twist; then the rest
          var L = r.loop ? r.loop.L : true, dir = L ? 1 : -1, start = L ? r.ax : r.bx, own = start === (L ? x.left : x.right);
          var sp = spliceOf[(L ? 'L' : 'R') + r.w.id], at = start + dir * (sp && !sp.first ? 8 : 6);
          r.slots = { dir: dir, gauge: at, purpose: at + dir * BOX };
          r.tagEnd[L ? 'left' : 'right'] = at + dir * 2 * BOX;
          r.slots.set = own ? (L ? x.left + EL + 20 : x.right - ER - 20) : at + dir * (2 * BOX + 10);
          r.slots.rest = r.slots.set + dir * 206;
          return;
        }
        var w = r.w, spliced = spliceOf['L' + w.id] || spliceOf['R' + w.id];
        [['left', 1, r.ax, x.left], ['right', -1, r.bx, x.right]].forEach(function (s) {
          var sp = spliceOf[(s[0] === 'left' ? 'L' : 'R') + w.id], dir = s[1], at = s[2] + dir * (sp && !sp.first ? 8 : 6);
          var gauge = w.gauge && (s[0] === 'left' || spliced || r.loop) && (s[2] === s[3] || sp), length = sp && w.length;
          if (gauge) at = tag(at, r.y, w.gauge, dir, 'pd-gauge', w.id);
          if (gauge) r.tagEnd[s[0]] = at;
          if (w.signal && s[0] === (r.loop ? (r.loop.L ? 'left' : 'right') : 'left')) r.tagEnd[s[0]] = at = tag(at, r.y, w.signal, dir, 'pd-label', w.id);
          if (length && sp.first) tag(dir > 0 ? Math.max(at, outer.left + 20) : Math.min(at, outer.right - 20), r.y, w.length + ' mm', dir, 'pd-length', w.id);   // past the lanes
          else if (length) r.tagEnd[s[0]] = tag(at, r.y, w.length + ' mm', dir, 'pd-length', w.id);
        });
        if (r.loop && r.b.pin) {   // a loopback coming back: its gauge, its own purpose (TX going out, RX coming back)
          var back = r.loop.edge + r.loop.dir * 6;
          if (w.gauge) back = tag(back, r.yBack, w.gauge, r.loop.dir, 'pd-gauge', w.id);
          if (w.to_signal) tag(back, r.yBack, w.to_signal, r.loop.dir, 'pd-label', w.id);
        }
      });

      // the wires
      var lines = [];
      function smooth(pts) {   // a line through the points, its corners slightly rounded (a point's third: its own radius)
        function xy(p) { return p[0] + ',' + p[1]; }
        var d = 'M' + xy(pts[0]);
        for (var i = 1; i < pts.length - 1; i++) {
          var a = pts[i - 1], p = pts[i], b = pts[i + 1];
          var la = Math.hypot(p[0] - a[0], p[1] - a[1]), lb = Math.hypot(b[0] - p[0], b[1] - p[1]), k = Math.min(p[2] || 8, la / 2, lb / 2);
          if (!k) { d += ' L' + xy(p); continue; }
          d += ' L' + xy([p[0] + (a[0] - p[0]) * k / la, p[1] + (a[1] - p[1]) * k / la]) + ' Q' + xy(p) + ' ' +
               xy([p[0] + (b[0] - p[0]) * k / lb, p[1] + (b[1] - p[1]) * k / lb]);
        }
        return d + ' L' + xy(pts[pts.length - 1]);
      }
      function twistOf(pair) {   // where a set's twists sit: near each end of the stretch its wires run side by side
        // (just past a shield's ellipses); one in the middle when there is no room for two
        var from = Math.max.apply(null, pair.map(function (r) { return Math.max(r.ax === x.left ? x.left + EL + 30 : r.ax + 14, (r.tagEnd.left || 0) + 10); }));
        var to = Math.min.apply(null, pair.map(function (r) { return Math.min(r.bx === x.right ? x.right - ER - 30 : r.bx - 14, (r.tagEnd.right || Infinity) - 10); }));
        // a twist only by a connector, not where the wires come from a splice
        var atLeft = pair.every(function (r) { return r.ax === x.left; }), atRight = pair.every(function (r) { return r.bx === x.right; });
        var half = pair.length > 2 ? pair.length * TWIST * 0.8 : TWIST;   // a multi twist: a step per wire
        if (to - from >= 4 * half + 40) {
          var ends = (atLeft ? [{ mid: from + half, half: half }] : []).concat(atRight ? [{ mid: to - half, half: half }] : []);
          if (ends.length) return ends;
        }
        return [{ mid: (from + to) / 2, half: Math.max(Math.min(half, (to - from) / 2), 16) }];
      }
      function twistPoints(pair, i, t) {   // one wire's way through a twist
        var n = pair.length, y = pair[i].y, high = pair[0].y, low = pair[n - 1].y;
        if (n === 2) return [[t.mid - t.half, y], i === 0 ? [t.mid, low] : [t.mid, high], [t.mid + t.half, y]];
        // more wires: at each step the bottom wire rises to the top and the others drop a row, n steps round
        var step = 2 * t.half / n, at = i, pts = [[t.mid - t.half, y]];
        for (var k = 1; k <= n; k++) {
          at = at === n - 1 ? 0 : at + 1;
          pts.push([t.mid - t.half + k * step, pair[at].y]);
        }
        return pts;
      }
      function colourOf(w) { var c = colours[w.colour] || ''; return c && c.indexOf('gradient') === -1 ? c : (c ? '#22c55e' : '#64748b'); }
      function wire(r, d, dashed) {
        var w = r.w, g = el('g', { class: 'pd-wire' }, wiresG);
        el('path', { d: d, class: 'pd-wire-edge' + (dashed ? ' dashed' : '') }, g);
        var core = el('path', { d: d, class: 'pd-wire-core' + (dashed ? ' dashed' : '') }, g);
        core.style.stroke = colourOf(w);
        if (w.colour === 'green/yellow') el('path', { d: d, class: 'pd-wire-core', style: 'stroke:#facc15', 'stroke-dasharray': '8 8' }, g);
        lines.push({ w: w, g: g });
      }
      function runs(list) {   // a set's wires in runs of those side by side (a set split between two connectors: two runs)
        var out = [];
        list.slice().sort(function (p, q) { return p.y - q.y; }).forEach(function (r) {
          var last = out[out.length - 1];
          if (last && r.y - last[last.length - 1].y <= ROW + 1) last.push(r); else out.push([r]);
        });
        return out;
      }
      var ellipses = {};   // a shielded set: where its ellipses sit
      function drainCircle(s, cx, cy, sideOf, on, shield) {   // its circle: picked, then a contact on its side joins the shield
        // there (a loopback: going out, coming back); picked again, the shield is not joined there
        var lit = state.drain && state.drain.set === s.name && state.drain.side === sideOf;
        var c = el('circle', { cx: cx, cy: cy, r: 5.5, class: 'pd-drain' + (lit ? ' chosen' : ''), 'data-drain': s.name + ':' + sideOf }, tools);
        el('title', {}, c).textContent = 'Shield of ' + s.name + ': join it to a contact on this side';
        c.addEventListener('click', function () {
          if (lit) {
            var joined = shield && (sideOf === 'left' ? shield.a.pin : shield.b.pin);
            if (joined) shieldTo(s.name, sideOf, null, '');
            else { state.drain = null; render(); }
            return;
          }
          state.drain = { set: s.name, side: sideOf, on: on };
          state.from = null;
          render();
        });
      }
      function loopShieldDraw(s, inner, shield) {   // a loopback set's shield: an ellipse round its wires going out, one
        var lp = inner[0].loop, cx = lp.edge + lp.dir * E(lp.L), kept = loopShield[s.name];   // round them coming back
        var outY = inner.map(function (r) { return r.y; }), backY = inner.map(function (r) { return r.yBack; });
        var outTop = Math.min.apply(null, outY) - 16, outLow = shield ? shield.y : kept.out;
        var backTop = shield ? shield.yBack : kept.back, backLow = Math.max.apply(null, backY) + 16;
        ellipses[s.name] = { loop: true, x: cx };
        [[outTop, outLow, outLow, 'left'], [backTop, backLow, backTop, 'right']].forEach(function (e) {
          var n = el('ellipse', { cx: cx, cy: (e[0] + e[1]) / 2, rx: 18, ry: (e[1] - e[0]) / 2, class: 'pd-shield', 'data-set': s.name }, over);
          el('title', {}, n).textContent = 'Set ' + s.name + ': ' + s.type.toLowerCase();
          if (editing) drainCircle(s, cx, e[2], e[3], lp.L ? 'left' : 'right', shield);
        });
        if (!shield) el('path', { d: smooth([[cx, kept.out], [kept.turn, kept.out, 14], [kept.turn, kept.back, 14], [cx, kept.back]]), class: 'pd-shield-line' }, wiresG);
      }
      setOrder.forEach(function (s) {   // editing too: what a set is shows as soon as it is picked
        if (!shielded(s.type)) return;
        var inner = s.rows.filter(function (r) { return r.w.type !== 'Shield'; }), shield = s.rows.filter(function (r) { return r.w.type === 'Shield'; })[0];
        if (!inner.length) return;
        if (inner[0].loop) { loopShieldDraw(s, inner, shield); return; }
        // an ellipse round each run of its wires side by side; the shield (its circles, its line) with the run just above it
        var parts = runs(inner.filter(function (r) { return r.y !== undefined; }));
        if (!parts.length) return;
        var main = parts[0];
        if (shield && shield.y !== undefined) parts.forEach(function (run) { if (run[run.length - 1].y < shield.y) main = run; });
        ellipses[s.name] = [x.left + EL, x.right - ER];
        parts.forEach(function (run) {
          var ys = run.map(function (r) { return r.y; }), mine = run === main;
          var top = Math.min.apply(null, ys) - 16, low = mine && shield ? shield.y : Math.max.apply(null, ys) + 16;
          ellipses[s.name].forEach(function (cx, i) {
            var e = el('ellipse', { cx: cx, cy: (top + low) / 2, rx: 18, ry: (low - top) / 2, class: 'pd-shield', 'data-set': s.name }, over);
            el('title', {}, e).textContent = 'Set ' + s.name + ': ' + s.type.toLowerCase();
            if (editing && mine) drainCircle(s, cx, low, i === 0 ? 'left' : 'right', i === 0 ? 'left' : 'right', shield);
          });
          if (mine && !shield) el('path', { d: 'M' + (x.left + EL) + ',' + low + ' H' + (x.right - ER), class: 'pd-shield-line' }, wiresG);
        });
      });
      function loopWire(r) {   // out, round the turn, back; a twisted set twists going out and coming back
        var lp = r.loop, dir = lp.dir, s = r.w.set && sets[r.w.set], ex = lp.edge + dir * E(lp.L);
        var outX = r.a.pin ? lp.edge : ex, backX = r.b.pin ? lp.edge : ex, turn = lp.turn;
        if (r.w.type === 'Shield' && ellipses[s.name]) {   // the shield: into the ellipses, dashed between them
          wire(r, 'M' + outX + ',' + r.y + ' H' + ex);
          wire(r, smooth([[ex, r.y], [turn, r.y, 14], [turn, r.yBack, 14], [ex, r.yBack]]), true);
          wire(r, 'M' + ex + ',' + r.yBack + ' H' + backX);
          return;
        }
        var out = [[outX, r.y]], back = [];
        var pair = lp.unit.filter(function (o) { return o.w.type !== 'Shield'; });
        if (s && twisted(s.type) && pair.length > 1) {
          var half = pair.length > 2 ? pair.length * TWIST * 0.8 : TWIST, t = { mid: lp.edge + dir * (E(lp.L) + 30 + half), half: half };
          var going = twistPoints(pair, pair.indexOf(r), t);
          var backPair = pair.slice().sort(function (p, q) { return p.yBack - q.yBack; });
          var coming = twistPoints(backPair.map(function (o) { return { y: o.yBack }; }), backPair.indexOf(r), t);
          out = out.concat(dir > 0 ? going : going.reverse());
          back = dir > 0 ? coming.reverse() : coming;
        }
        wire(r, smooth(out.concat([[turn, r.y, 14], [turn, r.yBack, 14]], back, [[backX, r.yBack]])));
      }
      rows.forEach(function (r) {
        if (r.y === undefined) return;
        if (r.loop) { loopWire(r); return; }
        var s = r.w.set && sets[r.w.set], y = r.y;
        if (!s) { wire(r, 'M' + r.ax + ',' + y + ' H' + r.bx); return; }
        if (r.w.type === 'Shield' && ellipses[s.name]) {   // the shield: level into the ellipses' bottoms, dashed between them
          var e = ellipses[s.name];
          wire(r, 'M' + r.ax + ',' + y + ' H' + e[0]);
          wire(r, 'M' + e[0] + ',' + y + ' H' + e[1], true);
          wire(r, 'M' + e[1] + ',' + y + ' H' + r.bx);
          return;
        }
        // twisted with the wires of its set beside it (not with one far off, beside another connector)
        var pair = runs(s.rows.filter(function (o) { return o.w.type !== 'Shield' && o.y !== undefined; }))
          .filter(function (run) { return run.indexOf(r) !== -1; })[0] || [r];
        if (twisted(s.type) && pair.length > 1) {   // see twistPoints
          var i = pair.indexOf(r), pts = [[r.ax, y]];
          twistOf(pair).forEach(function (t) { pts = pts.concat(twistPoints(pair, i, t)); });
          pts.push([r.bx, y]);
          wire(r, smooth(pts));
          return;
        }
        wire(r, 'M' + r.ax + ',' + y + ' H' + r.bx);
      });
      Object.keys(splices).forEach(function (key) {   // the splice: each wire leaves the contact's row round a corner,
        var s = splices[key];                          // down, and round a corner into its own row
        if (s.rows.length < 2) return;
        var sx = s.x, top = s.rows[0].y, dir = s.left ? 1 : -1;
        s.rows.slice(1).forEach(function (r) {
          var k = Math.min(14, (r.y - top) / 2);
          wire(s.rows[0], 'M' + (sx - dir * k) + ',' + top + ' Q' + sx + ',' + top + ' ' + sx + ',' + (top + k) +
                          ' V' + (r.y - k) + ' Q' + sx + ',' + r.y + ' ' + (sx + dir * k) + ',' + r.y);
        });
      });

      if (editing) {   // each row: its tools where what they set shows (its set drawn as it is: twisted, shielded)
        if (!document.getElementById('pd-gauges')) {   // the usual gauges to pick from
          var gauges = html('datalist', { id: 'pd-gauges' }, document.body);
          [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30].forEach(function (n) { html('option', { value: n + ' AWG' }, gauges); });
        }
        rows.forEach(function (r) {
          if (r.y === undefined) return;
          var w = r.w, at = r.slots, dir = at.dir;
          function spot(x0, y, width, cls) {   // a box of tools from x0 going the row's way
            var fo = el('foreignObject', { x: dir > 0 ? x0 : x0 - width, y: y - 12, width: width, height: 26 }, tools);
            return html('div', { class: 'pd-tools' + (dir > 0 ? '' : ' end') + (cls ? ' ' + cls : '') }, fo);
          }
          var labelButton = function (parent, value, end) {   // its purpose, picked in the popup
            var b = html('button', { type: 'button', class: 'btn small pd-label-pick' + (value ? '' : ' muted'), 'aria-label': 'Purpose', 'data-wire-signal': w.id + (end ? ':' + end : '') }, parent);
            b.textContent = value || 'Label';
            b.addEventListener('click', function () {
              purposePicker(value, function (v) { post({ action: 'signal', wire: w.id, signal: v, end: end || 'from' }); });
            });
          };
          var gauge = html('input', { type: 'text', 'aria-label': 'Gauge', placeholder: 'AWG', list: 'pd-gauges', class: 'pd-gauge-input', 'data-wire-gauge': w.id }, spot(at.gauge, r.y, BOX - 4));
          gauge.value = w.gauge || '';
          gauge.addEventListener('change', function () { post({ action: 'gauge', wire: w.id, gauge: gauge.value }); });
          labelButton(spot(at.purpose, r.y, BOX - 4), w.signal, '');
          if (r.loop) {   // a loopback coming back: its gauge, and a purpose of its own
            var tag0 = r.loop.edge + dir * 6;
            if (w.gauge) {
              var g = el('g', { class: 'pd-tag pd-gauge', 'data-tag-of': w.id }, over), t = text(g, tag0 + dir * (BOX - 4) / 2, r.yBack + 3.5, w.gauge, 'pd-tag-text');
              g.insertBefore(el('rect', { x: dir > 0 ? tag0 : tag0 - BOX + 4, y: r.yBack - 7, width: BOX - 4, height: 14, rx: 4 }), t);
            }
            labelButton(spot(tag0 + dir * BOX, r.yBack, BOX - 4), w.to_signal, 'to');
          }
          // over the twist: the set it is in, and how the set's wires go together (or this wire as the set's shield)
          var box = spot(at.set, r.y, 202);
          var pickSet = html('select', { 'aria-label': 'Set of ' + byId[r.a.end].designator + ':' + r.a.pin, 'data-wire': w.id }, box);
          var add = function (to, value, label) { var o = html('option', { value: value }, to); o.textContent = label; };
          add(pickSet, '', 'No set');
          setOrder.forEach(function (s) { add(pickSet, s.name, 'Set ' + s.name); });
          add(pickSet, 'new:Straight', '＋ New set');
          pickSet.value = w.set || '';
          pickSet.addEventListener('change', function () { post({ action: 'set', wire: w.id, set: pickSet.value }); });
          var pickType = html('select', { 'aria-label': 'Set type', 'data-wire-type': w.id, class: 'pd-type' }, box);
          data.set_types.concat(['Shield']).forEach(function (t) { add(pickType, t, t === 'Shield' ? 'Shield wire' : t); });
          pickType.value = w.type || 'Straight';
          pickType.disabled = !w.set;
          pickType.addEventListener('change', function () { post({ action: 'set_type', wire: w.id, type: pickType.value }); });
          var rest = spot(at.rest, r.y, 130);
          var pickColour = html('select', { 'aria-label': 'Colour', class: 'pd-colour' }, rest);
          [''].concat(data.colours).forEach(function (c) { var o = html('option', { value: c }, pickColour); o.textContent = c || 'colour'; });
          pickColour.value = w.colour || '';
          pickColour.addEventListener('change', function () { post({ action: 'colour', wire: w.id, colour: pickColour.value }); });
          var gone = html('button', { type: 'button', class: 'btn small', 'aria-label': 'Take the wire away' }, rest);
          gone.textContent = '✕';
          gone.addEventListener('click', function () { post({ action: 'delete', wire: w.id }); });
        });
      } else {   // where each set's wires run: clicking there picks the set
        setOrder.forEach(function (s) {
          var ys = [];
          s.rows.forEach(function (r) { if (r.y !== undefined) ys.push(r.y); if (r.yBack !== undefined) ys.push(r.yBack); });
          if (!ys.length) return;
          var top = Math.min.apply(null, ys) - ROW / 2, low = Math.max.apply(null, ys) + ROW / 2;
          var area = el('rect', { x: x.left + 2, y: top, width: x.right - x.left - 4, height: low - top, rx: 8, class: 'pd-area', 'data-set': s.name }, areas);
          el('title', {}, area).textContent = 'Set ' + s.name + ' · ' + s.type.toLowerCase();
          area.addEventListener('click', function () { show(s.name); });
        });
        rows.forEach(function (r) {   // a wire in no set: picked on its own
          if (r.w.set || r.y === undefined) return;
          var key = 'wire:' + r.w.id;
          var area = el('rect', { x: x.left + 2, y: r.y - ROW / 2, width: x.right - x.left - 4, height: (r.yBack || r.y) - r.y + ROW, rx: 8, class: 'pd-area', 'data-set': key }, areas);
          el('title', {}, area).textContent = byId[r.a.end].designator + ':' + r.a.pin + ' → ' + byId[r.b.end].designator + ':' + r.b.pin +
            (r.w.signal ? ' · ' + r.w.signal : '');
          area.addEventListener('click', function () { show(key); });
        });
      }

      var tall = Math.max(y - 50, 120);
      svg.setAttribute('viewBox', '0 0 ' + width + ' ' + tall);
      svg.style.width = width + 'px';
      svg.style.height = tall + 'px';

      function show(set) {   // light up one set (or none)
        state.picked = state.picked === set ? null : set;
        bar.querySelectorAll('[data-set]').forEach(function (b) { b.classList.toggle('on', b.dataset.set === state.picked); });
        svg.classList.toggle('picking', state.picked !== null);
        svg.querySelectorAll('.lit').forEach(function (n) { n.classList.remove('lit'); });
        if (state.picked === null) return;
        svg.querySelectorAll('[data-set]').forEach(function (n) { if (n.dataset.set === state.picked) n.classList.add('lit'); });
        lines.forEach(function (d) {
          if ((d.w.set || 'wire:' + d.w.id) !== state.picked) return;
          d.g.classList.add('lit');
          [[d.w.from, d.w.from_pin], [d.w.to, d.w.to_pin]].forEach(function (p) {
            (lit[p[0] + ':' + p[1]] || []).forEach(function (n) { n.classList.add('lit'); });
          });
        });
      }
      if (!editing) setOrder.forEach(function (s) {
        var b = html('button', { type: 'button', class: 'btn small', 'data-set': s.name }, bar);
        b.textContent = 'Set ' + s.name + ' · ' + s.type.toLowerCase();
        b.addEventListener('click', function () { show(s.name); });
      });
      var picked = state.picked;
      state.picked = null;
      svg.classList.remove('picking');
      if (picked !== null && sets[picked] && !editing) show(picked);

      html('span', { class: 'spacer' }, bar);
      var modes = html('span', { class: 'segmented' }, bar);
      [['View', false], ['Edit', true]].forEach(function (m) {
        var b = html('button', { type: 'button', class: 'btn small' + (editing === m[1] ? ' on' : ''), 'data-mode': m[0].toLowerCase() }, modes);
        b.textContent = m[0];
        b.addEventListener('click', function () {
          if (state.editing === m[1]) return;
          if (!m[1] && state.changed) { window.location.reload(); return; }   // the table below shows the changes too
          state.editing = m[1];
          state.from = null;
          render();
        });
      });
    }
    render();
    var later;
    window.addEventListener('resize', function () {   // the width there is changed: drawn again to fill it
      clearTimeout(later);
      later = setTimeout(function () { if (svg.parentNode.clientWidth !== state.width) render(); }, 150);
    });
  }

  // One connector's face on its own (a device's connector, a family's): as you look at it, each pin with its signal on
  // hover; ``onPin(number, on)`` when the pointer comes onto or leaves one.
  function drawFace(svg, end, onPin) {
    var f = face(end, true), pad = 4;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute('viewBox', '0 0 ' + (f.w + 2 * pad) + ' ' + (f.h + 2 * pad));
    svg.setAttribute('width', f.w + 2 * pad);
    svg.setAttribute('height', f.h + 2 * pad);
    function at(x, y) { return [x + pad, y + pad]; }
    outline(svg, f, pad, pad);
    var signal = {};
    end.pins.forEach(function (p) { signal[p[0]] = p[1]; });
    f.at.forEach(function (p) {
      var xy = at(p[1], p[2]), g = el('g', { class: 'pd-pin' + (p[0] in signal ? '' : ' empty'), 'data-pin': p[0] }, svg);
      el('title', {}, g).textContent = p[0] + (signal[p[0]] ? ' ' + signal[p[0]] : '');
      el('circle', { cx: xy[0], cy: xy[1], r: R }, g);
      text(g, xy[0], xy[1] + 4, p[0], 'pd-num');
      if (onPin) {
        g.addEventListener('mouseenter', function () { onPin(p[0], true); });
        g.addEventListener('mouseleave', function () { onPin(p[0], false); });
      }
    });
  }

  window.Pinout = { mount: mount, face: drawFace };
})();

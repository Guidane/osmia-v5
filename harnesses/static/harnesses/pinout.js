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
        var flip = side[w.from] === 'right' && side[w.to] === 'left';
        var from = { end: w.from, pin: w.from_pin }, to = { end: w.to, pin: w.to_pin };
        return { w: w, a: flip ? to : from, b: flip ? from : to, same: side[w.from] === side[w.to] };
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
        if (!groups[k]) list.push(groups[k] = { left: r.a.end, right: r.b.end, rows: [], same: r.same });
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
        if (e.plugs) text(over, left ? x.leftFace : width - 10, y0 - 20, '→ ' + e.plugs, 'pd-sub' + (left ? '' : ' end'));
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
          if (side[end] === state.drain.side) shieldTo(state.drain.set, state.drain.side, end, pin);
          return;
        }
        if (state.from && side[state.from.end] !== side[end]) {
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
        if (at.pin === '') return left ? x.left + 70 : x.right - 70;   // a shield not joined on this side: from its ellipse
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
        var y0 = y, n = g.rows.length, bottom = n ? (n - 1) * ROW + C : 0;
        var here = [['left', g.left]].concat(g.same ? [] : [['right', g.right]]).filter(function (s) { return s[1] !== undefined; });
        here.forEach(function (s) { if (beside[s[0]].id !== s[1]) y0 = Math.max(y0, beside[s[0]].until + GAP); });
        here.forEach(function (s) {
          if (faced[s[1]]) return;
          faced[s[1]] = true;
          beside[s[0]] = { id: s[1], until: y0 + drawFace(byId[s[1]], y0) };
        });
        here.forEach(function (s) { if (beside[s[0]].id !== s[1]) beside[s[0]] = { id: s[1], until: y0 + bottom }; });
        var own = { left: false, right: false };   // a contact of its own on that side (not only splices from above)
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

      // the wires
      var lines = [];
      function smooth(pts) {   // a line through the points, its corners slightly rounded
        var d = 'M' + pts[0];
        for (var i = 1; i < pts.length - 1; i++) {
          var a = pts[i - 1], p = pts[i], b = pts[i + 1];
          var la = Math.hypot(p[0] - a[0], p[1] - a[1]), lb = Math.hypot(b[0] - p[0], b[1] - p[1]), k = Math.min(8, la / 2, lb / 2);
          if (!k) { d += ' L' + p; continue; }
          d += ' L' + [p[0] + (a[0] - p[0]) * k / la, p[1] + (a[1] - p[1]) * k / la] + ' Q' + p + ' ' +
               [p[0] + (b[0] - p[0]) * k / lb, p[1] + (b[1] - p[1]) * k / lb];
        }
        return d + ' L' + pts[pts.length - 1];
      }
      function twistOf(pair) {   // where a set's twists sit: near each end of the stretch its wires run side by side
        // (just past a shield's ellipses); one in the middle when there is no room for two
        var from = Math.max.apply(null, pair.map(function (r) { return r.ax === x.left ? x.left + 100 : r.ax + 14; }));
        var to = Math.min.apply(null, pair.map(function (r) { return r.bx === x.right ? x.right - 100 : r.bx - 14; }));
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
      var ellipses = {};   // a shielded set: where its ellipses sit
      setOrder.forEach(function (s) {   // editing too: what a set is shows as soon as it is picked
        if (!shielded(s.type)) return;
        var inner = s.rows.filter(function (r) { return r.w.type !== 'Shield'; }), shield = s.rows.filter(function (r) { return r.w.type === 'Shield'; })[0];
        if (!inner.length) return;
        var ys = inner.map(function (r) { return r.y; });
        var top = Math.min.apply(null, ys) - 16, low = shield ? shield.y : Math.max.apply(null, ys) + 16;
        ellipses[s.name] = [x.left + 70, x.right - 70];
        ellipses[s.name].forEach(function (cx, i) {
          var e = el('ellipse', { cx: cx, cy: (top + low) / 2, rx: 18, ry: (low - top) / 2, class: 'pd-shield', 'data-set': s.name }, over);
          el('title', {}, e).textContent = 'Set ' + s.name + ': ' + s.type.toLowerCase();
          if (!editing) return;
          // its circle: picked, then a contact on its side joins the shield there; picked again, the shield isn't joined there
          var sideOf = i === 0 ? 'left' : 'right', on = state.drain && state.drain.set === s.name && state.drain.side === sideOf;
          var c = el('circle', { cx: cx, cy: low, r: 5.5, class: 'pd-drain' + (on ? ' chosen' : ''), 'data-drain': s.name + ':' + sideOf }, tools);
          el('title', {}, c).textContent = 'Shield of ' + s.name + ': join it to a contact on this side';
          c.addEventListener('click', function () {
            if (on) {
              var joined = shield && (sideOf === 'left' ? shield.a.pin : shield.b.pin);
              if (joined) shieldTo(s.name, sideOf, null, '');
              else { state.drain = null; render(); }
              return;
            }
            state.drain = { set: s.name, side: sideOf };
            state.from = null;
            render();
          });
        });
        if (!shield) el('path', { d: 'M' + (x.left + 70) + ',' + low + ' H' + (x.right - 70), class: 'pd-shield-line' }, wiresG);
      });
      rows.forEach(function (r) {
        if (r.y === undefined) return;
        var s = r.w.set && sets[r.w.set], y = r.y;
        if (!s) { wire(r, 'M' + r.ax + ',' + y + ' H' + r.bx); return; }
        if (r.w.type === 'Shield' && ellipses[s.name]) {   // the shield: level into the ellipses' bottoms, dashed between them
          var e = ellipses[s.name];
          wire(r, 'M' + r.ax + ',' + y + ' H' + e[0]);
          wire(r, 'M' + e[0] + ',' + y + ' H' + e[1], true);
          wire(r, 'M' + e[1] + ',' + y + ' H' + r.bx);
          return;
        }
        var pair = s.rows.filter(function (o) { return o.w.type !== 'Shield'; }).sort(function (p, q) { return p.y - q.y; });
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

      if (editing) {   // each row, in the middle: the set it is in (drawn as it is: twisted, shielded), its colour, ✕
        rows.forEach(function (r) {
          if (r.y === undefined) return;
          var w = r.w;
          var fo = el('foreignObject', { x: mid - 180, y: r.y - 12, width: 360, height: 26 }, tools);
          var box = html('div', { class: 'pd-tools' }, fo);
          var pickSet = html('select', { 'aria-label': 'Set of ' + byId[r.a.end].designator + ':' + r.a.pin, 'data-wire': w.id }, box);
          var add = function (to, value, label) { var o = html('option', { value: value }, to); o.textContent = label; };
          add(pickSet, '', 'No set');
          setOrder.forEach(function (s) { add(pickSet, s.name, 'Set ' + s.name); });
          add(pickSet, 'new:Straight', '＋ New set');
          pickSet.value = w.set || '';
          pickSet.addEventListener('change', function () { post({ action: 'set', wire: w.id, set: pickSet.value }); });
          // how the set's wires go together (for the whole set), or this wire as the set's shield
          var pickType = html('select', { 'aria-label': 'Set type', 'data-wire-type': w.id, class: 'pd-type' }, box);
          data.set_types.concat(['Shield']).forEach(function (t) { add(pickType, t, t === 'Shield' ? 'Shield wire' : t); });
          pickType.value = w.type || 'Straight';
          pickType.disabled = !w.set;
          pickType.addEventListener('change', function () { post({ action: 'set_type', wire: w.id, type: pickType.value }); });
          var pickColour = html('select', { 'aria-label': 'Colour', class: 'pd-colour' }, box);
          [''].concat(data.colours).forEach(function (c) { var o = html('option', { value: c }, pickColour); o.textContent = c || 'colour'; });
          pickColour.value = w.colour || '';
          pickColour.addEventListener('change', function () { post({ action: 'colour', wire: w.id, colour: pickColour.value }); });
          var gone = html('button', { type: 'button', class: 'btn small', 'aria-label': 'Take the wire away' }, box);
          gone.textContent = '✕';
          gone.addEventListener('click', function () { post({ action: 'delete', wire: w.id }); });
        });
      } else {   // where each set's wires run: clicking there picks the set
        setOrder.forEach(function (s) {
          var ys = s.rows.map(function (r) { return r.y; }).filter(function (v) { return v !== undefined; });
          if (!ys.length) return;
          var top = Math.min.apply(null, ys) - ROW / 2, low = Math.max.apply(null, ys) + ROW / 2;
          var area = el('rect', { x: x.left + 2, y: top, width: x.right - x.left - 4, height: low - top, rx: 8, class: 'pd-area', 'data-set': s.name }, areas);
          el('title', {}, area).textContent = 'Set ' + s.name + ' · ' + s.type.toLowerCase();
          area.addEventListener('click', function () { show(s.name); });
        });
        rows.forEach(function (r) {   // a wire in no set: picked on its own
          if (r.w.set || r.y === undefined) return;
          var key = 'wire:' + r.w.id;
          var area = el('rect', { x: x.left + 2, y: r.y - ROW / 2, width: x.right - x.left - 4, height: ROW, rx: 8, class: 'pd-area', 'data-set': key }, areas);
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

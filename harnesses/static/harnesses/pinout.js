/* A harness's pinout drawn. Each wire is a row: its contact number on the left, its contact number on the right, the
   connector upright beside each column and the connector's face (its pins as they sit: a single row, two rows, a
   D-sub, a circle, a grid) on the far side.

   View: wires in their colours; a twisted set crosses in the middle (the first wire in a V down to the set's bottom
   row, the others in a Λ up to its top row), a shielded set has an ellipse at each end whose bottom sits on the
   shield wire's row, the shield dashed between them. Clicking where a set's wires run (or its chip) lights up the set:
   its contacts and its pins on both faces.

   Edit: pick a pin on a face on the left, then one on the right (or the other way): a new row joins them. Each row
   shows its set left of the middle, and right of it the set to put it in (or a new one), its colour, and ✕. */
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

  function face(end) {   // where each pin sits on the connector's face: {w, h, shape, at: [[number, x, y]]}
    var pins = end.pins.map(function (p) { return p[0]; });
    if (pins.length && pins.every(function (p) { return /^\d+$/.test(p); })) {   // numbered: every position, from 1, in its place
      var last = Math.max.apply(null, [end.positions].concat(pins.map(Number)));
      pins = [];
      for (var k = 1; k <= last; k++) pins.push(String(k));
    }
    var n = pins.length, at = [], half = Math.ceil(n / 2), m = 18;
    if (end.layout === 'staggered') {   // upright like a D-sub: the first half down the wide side, the rest between them
      var apart = 24;
      pins.forEach(function (p, i) {
        var inner = i >= half;
        at.push([p, m + R + (inner ? 0 : apart), m + R + (inner ? i - half + 0.5 : i) * PITCH]);
      });
      return { w: 2 * m + apart + 2 * R, h: 2 * m + (half - 1) * PITCH + 2 * R, shape: 'trapezoid', at: at };
    }
    if (end.layout === 'rows') {
      pins.forEach(function (p, i) { var right = i >= half; at.push([p, m + R + (right ? PITCH : 0), m + R + (right ? i - half : i) * PITCH]); });
      return { w: 2 * m + PITCH + 2 * R, h: 2 * m + (half - 1) * PITCH + 2 * R, shape: 'box', at: at };
    }
    if (end.layout === 'circle') {
      var ring = Math.max(PITCH * n / (2 * Math.PI), 22), c = m + ring + R;
      pins.forEach(function (p, i) {
        var a = -Math.PI / 2 + 2 * Math.PI * i / Math.max(n, 1);
        at.push([p, c + ring * Math.cos(a), c + ring * Math.sin(a)]);
      });
      return { w: 2 * c, h: 2 * c, shape: 'circle', at: at };
    }
    if (end.layout === 'grid') {
      var cols = end.columns || Math.ceil(Math.sqrt(n)) || 1, lines = Math.ceil(n / cols);
      pins.forEach(function (p, i) { at.push([p, m + R + (i % cols) * PITCH, m + R + Math.floor(i / cols) * PITCH]); });
      return { w: 2 * m + (cols - 1) * PITCH + 2 * R, h: 2 * m + (lines - 1) * PITCH + 2 * R, shape: 'box', at: at };
    }
    pins.forEach(function (p, i) { at.push([p, m + R, m + R + i * PITCH]); });
    return { w: 2 * m + 2 * R, h: 2 * m + Math.max(n - 1, 0) * PITCH + 2 * R, shape: 'box', at: at };
  }

  function sides(data) {   // each end left or right, so that wires go across
    var side = {}, count = { left: 0, right: 0 }, known = {};
    data.ends.forEach(function (e) { known[e.id] = true; });
    data.ends.forEach(function (e) {
      if (side[e.id]) return;
      side[e.id] = count.left <= count.right ? 'left' : 'right';
      count[side[e.id]] += 1;
      var queue = [e.id];
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
    });
    return side;
  }

  function mount(root, data, colours) {
    var svg = root.querySelector('svg'), bar = root.querySelector('.set-chips');
    var state = { data: data, editing: false, changed: false, from: null, picked: null };

    function post(fields) {
      var body = new FormData();
      Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
      return fetch(root.dataset.url, { method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-CSRFToken': root.dataset.csrf } })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (d) { state.data = d; state.changed = true; state.from = null; render(); });
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
      x.right = x.left + (editing ? 620 : 420);
      x.rightNum = x.right + C; x.rightBar = x.rightNum + 20; x.rightFace = x.rightBar + 46;
      var width = x.rightFace + widest.right + 10, mid = (x.left + x.right) / 2;

      var under = el('g', {}, svg), wiresG = el('g', {}, svg), over = el('g', {}, svg), areas = el('g', {}, svg), tools = el('g', {}, svg);
      var lit = {};
      function remember(key, node) { (lit[key] = lit[key] || []).push(node); }

      function drawFace(e, y0) {
        var left = side[e.id] === 'left', f = faces[e.id];
        var fx = left ? x.leftFace + widest.left - f.w : x.rightFace, fy = y0 - 10;
        text(over, left ? x.leftFace : width - 10, y0 - 34, e.designator + (e.what ? ' · ' + e.what : ''), 'pd-title' + (left ? '' : ' end'));
        if (e.plugs) text(over, left ? x.leftFace : width - 10, y0 - 20, '→ ' + e.plugs, 'pd-sub' + (left ? '' : ' end'));
        if (f.shape === 'circle') el('circle', { cx: fx + f.w / 2, cy: fy + f.h / 2, r: f.w / 2, class: 'pd-face' }, under);
        else if (f.shape === 'trapezoid') {
          var k = 14;   // the narrow side slants in at the top and bottom
          el('path', { d: 'M' + fx + ',' + (fy + k) + ' L' + (fx + f.w) + ',' + fy + ' V' + (fy + f.h) + ' L' + fx + ',' + (fy + f.h - k) + ' Z', class: 'pd-face' }, under);
        } else el('rect', { x: fx, y: fy, width: f.w, height: f.h, rx: 6, class: 'pd-face' }, under);
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
        return f.h - 10;
      }
      function pick(end, pin, node) {   // edit: a pin on one side, then one on the other side, joined by a new wire
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
        return left ? x.left : x.right;
      }

      var y = 70, faced = {};
      function drawn(id, y0) { if (faced[id]) return 0; faced[id] = true; return drawFace(byId[id], y0); }
      list.forEach(function (g) {
        var y0 = y, n = g.rows.length, bottom = n ? (n - 1) * ROW + C : 0;
        if (g.left !== undefined) bottom = Math.max(bottom, drawn(g.left, y0));
        if (g.right !== undefined && !g.same) bottom = Math.max(bottom, drawn(g.right, y0));
        if (n) {
          [[g.left, x.leftBar]].concat(g.same ? [] : [[g.right, x.rightBar]]).forEach(function (b) {
            el('rect', { x: b[1], y: y0 - C - 6, width: 12, height: (n - 1) * ROW + 2 * C + 12, rx: 3, class: 'pd-bar' }, under);
            text(over, b[1] + 6, y0 - C - 12, byId[b[0]].designator, 'pd-bar-label');
          });
        }
        g.rows.forEach(function (r, i) {
          r.y = y0 + i * ROW;
          r.ax = contact(r.a, true, r.y);
          r.bx = contact(r.b, false, r.y, g.same);
        });
        y = y0 + bottom + 90;
      });

      // the wires
      var x1 = x.left + 110, x4 = x.right - 110, lines = [];
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
      if (!editing) setOrder.forEach(function (s) {
        if (!shielded(s.type)) return;
        var inner = s.rows.filter(function (r) { return r.w.type !== 'Shield'; }), shield = s.rows.filter(function (r) { return r.w.type === 'Shield'; })[0];
        if (!inner.length) return;
        var ys = inner.map(function (r) { return r.y; });
        var top = Math.min.apply(null, ys) - 16, low = shield ? shield.y : Math.max.apply(null, ys) + 16;
        ellipses[s.name] = [x.left + 45, x.right - 45];
        ellipses[s.name].forEach(function (cx) {
          var e = el('ellipse', { cx: cx, cy: (top + low) / 2, rx: 18, ry: (low - top) / 2, class: 'pd-shield', 'data-set': s.name }, over);
          el('title', {}, e).textContent = 'Set ' + s.name + ': ' + s.type.toLowerCase();
        });
      });
      rows.forEach(function (r) {
        if (r.y === undefined) return;
        var s = r.w.set && sets[r.w.set], y = r.y;
        if (editing || !s) { wire(r, 'M' + r.ax + ',' + y + ' H' + r.bx); return; }
        if (r.w.type === 'Shield' && ellipses[s.name]) {   // the shield: level into the ellipses' bottoms, dashed between them
          var e = ellipses[s.name];
          wire(r, 'M' + r.ax + ',' + y + ' H' + e[0]);
          wire(r, 'M' + e[0] + ',' + y + ' H' + e[1], true);
          wire(r, 'M' + e[1] + ',' + y + ' H' + r.bx);
          return;
        }
        var pair = s.rows.filter(function (o) { return o.w.type !== 'Shield'; }).sort(function (p, q) { return p.y - q.y; });
        if (twisted(s.type) && pair.length > 1) {   // the first wire in a V to the bottom row, the others in a Λ to the top
          var high = pair[0].y, low = pair[pair.length - 1].y, i = pair.indexOf(r);
          var peak = i === 0 ? { x: mid, y: low } : { x: mid + (i - pair.length / 2) * 50, y: high };
          wire(r, 'M' + r.ax + ',' + y + ' H' + x1 + ' L' + peak.x + ',' + peak.y + ' L' + x4 + ',' + y + ' H' + r.bx);
          return;
        }
        wire(r, 'M' + r.ax + ',' + y + ' H' + r.bx);
      });

      if (editing) {   // each row: its set left of the middle; the set to put it in, its colour and ✕ right of it
        rows.forEach(function (r) {
          if (r.y === undefined) return;
          var w = r.w;
          text(tools, mid - 10, r.y + 4, w.set ? (w.type === 'Shield' ? 'Shield of ' + w.set : 'Set ' + w.set + ' · ' + w.type.toLowerCase()) : '—', 'pd-setname end');
          var fo = el('foreignObject', { x: mid + 6, y: r.y - 12, width: 290, height: 26 }, tools);
          var box = html('div', { class: 'pd-tools' }, fo);
          var pickSet = html('select', { 'aria-label': 'Set of ' + byId[r.a.end].designator + ':' + r.a.pin, 'data-wire': w.id }, box);
          var add = function (value, label) { var o = html('option', { value: value }, pickSet); o.textContent = label; };
          add('', 'No set');
          setOrder.forEach(function (s) { if (s.type !== 'Shield') add(s.name, 'Set ' + s.name + ' · ' + s.type.toLowerCase()); });
          setOrder.forEach(function (s) { if (shielded(s.type)) add('shield:' + s.name, 'Shield of ' + s.name); });
          data.set_types.forEach(function (t) { add('new:' + t, '＋ New ' + t.toLowerCase() + ' set'); });
          pickSet.value = w.set ? (w.type === 'Shield' ? 'shield:' + w.set : w.set) : '';
          pickSet.addEventListener('change', function () { post({ action: 'set', wire: w.id, set: pickSet.value }); });
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
      }

      svg.setAttribute('viewBox', '0 0 ' + width + ' ' + Math.max(y - 50, 120));
      svg.style.maxWidth = width + 'px';

      function show(set) {   // light up one set (or none)
        state.picked = state.picked === set ? null : set;
        bar.querySelectorAll('[data-set]').forEach(function (b) { b.classList.toggle('on', b.dataset.set === state.picked); });
        svg.classList.toggle('picking', state.picked !== null);
        svg.querySelectorAll('.lit').forEach(function (n) { n.classList.remove('lit'); });
        if (state.picked === null) return;
        svg.querySelectorAll('[data-set]').forEach(function (n) { if (n.dataset.set === state.picked) n.classList.add('lit'); });
        lines.forEach(function (d) {
          if (d.w.set !== state.picked) return;
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
  }

  window.Pinout = { mount: mount };
})();

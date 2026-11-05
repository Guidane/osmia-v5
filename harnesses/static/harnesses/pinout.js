/* A harness's pinout drawn: each end's connector face on the far left or right, its pins where they sit (single row,
   two rows, staggered like a D-sub, circular, a grid); then the connector upright, and its contact numbers, grouped by
   wire set, which the wires join in their colours: straight across, a twisted set crossing in the middle (the first
   wire in a V, the others in a Λ), a shielded set with an ellipse at each end and its shield wire dashed between them.
   Picking a set (the chips above, or one of its wires) lights up its contacts and its pins on the faces. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var PITCH = 26, R = 10, ROW = 34, C = 13, MIDDLE = 420;

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]); });
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

  function draw(svg, chips, data, colours) {
    var side = {}, faces = {}, widest = { left: 0, right: 0 };
    data.ends.forEach(function (e, i) {
      side[e.id] = i % 2 ? 'right' : 'left';
      faces[e.id] = face(e);
      widest[side[e.id]] = Math.max(widest[side[e.id]], faces[e.id].w);
    });
    var signal = {};
    data.ends.forEach(function (e) { e.pins.forEach(function (p) { signal[e.id + ':' + p[0]] = p[1]; }); });

    // the contacts of each end, in order: on the left by wire set (its shield last), then the rest; on the right as the
    // wires come from the left, so only the twists cross
    var sets = {}, setOrder = [];
    data.wires.forEach(function (w) {
      if (!w.set) return;
      var s = sets[w.set] = sets[w.set] || { name: w.set, type: '', wires: [], first: null };
      s.wires.push(w);
      if (w.type !== 'Shield') s.type = s.type || w.type;
      var key = w.from_pin;
      if (s.first === null || natural(key, s.first) < 0) s.first = key;
    });
    Object.keys(sets).forEach(function (k) { if (!sets[k].type) sets[k].type = 'Shield'; setOrder.push(sets[k]); });
    setOrder.sort(function (a, b) { return natural(a.first, b.first); });
    var setRank = {};
    setOrder.forEach(function (s, i) { setRank[s.name] = i; });
    function wiresAt(e, pin) {
      return data.wires.filter(function (w) { return (w.from === e.id && w.from_pin === pin) || (w.to === e.id && w.to_pin === pin); });
    }
    var rows = {}, top = { left: 60, right: 60 }, order = {};
    data.ends.forEach(function (e) {
      var pins = e.pins.map(function (p) { return p[0]; });
      if (side[e.id] === 'left') {
        pins.sort(function (a, b) {
          var wa = wiresAt(e, a)[0], wb = wiresAt(e, b)[0];
          var ka = wa ? (wa.set ? setRank[wa.set] : setOrder.length) : setOrder.length + 1;
          var kb = wb ? (wb.set ? setRank[wb.set] : setOrder.length) : setOrder.length + 1;
          if (ka !== kb) return ka - kb;
          var sa = wa && wa.type === 'Shield' ? 1 : 0, sb = wb && wb.type === 'Shield' ? 1 : 0;
          return sa - sb || natural(a, b);
        });
      }
      order[e.id] = pins;
    });
    data.ends.forEach(function (e) {   // the right: as their wires' other ends are placed
      if (side[e.id] !== 'right') return;
      var place = {};
      Object.keys(order).forEach(function (id) { if (side[id] === 'left') order[id].forEach(function (p, i) { place[id + ':' + p] = i; }); });
      order[e.id].sort(function (a, b) {
        var at = function (pin) {
          var w = wiresAt(e, pin)[0];
          if (!w) return 1e6;
          var other = w.from === e.id && w.from_pin === pin ? w.to + ':' + w.to_pin : w.from + ':' + w.from_pin;
          return other in place ? place[other] : 1e5;
        };
        return at(a) - at(b) || natural(a, b);
      });
    });

    var x = {}, width;
    x.leftFace = 10; x.leftBar = 10 + widest.left + 30; x.leftNum = x.leftBar + 34;
    x.left = x.leftNum + C;                       // where wires leave the left contacts
    x.right = x.left + MIDDLE;
    x.rightNum = x.right + C; x.rightBar = x.rightNum + 20; x.rightFace = x.rightBar + 46;
    width = x.rightFace + widest.right + 10;

    var under = el('g', {}, svg), wiresG = el('g', {}, svg), over = el('g', {}, svg);
    var lit = {};      // end id + pin: what lights up with it (its contact, its pin on the face)
    function remember(key, node) { (lit[key] = lit[key] || []).push(node); }

    data.ends.forEach(function (e) {
      var s = side[e.id], left = s === 'left', f = faces[e.id], pins = order[e.id];
      var y0 = top[s], n = Math.max(pins.length, 1), body = (n - 1) * ROW;
      // the face, at the far side
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
        var g = el('g', { class: 'pd-pin' + (has[p[0]] ? '' : ' empty') }, over);
        el('circle', { cx: fx + p[1], cy: fy + p[2], r: R }, g);
        text(g, fx + p[1], fy + p[2] + 4, p[0], 'pd-num');
        remember(e.id + ':' + p[0], g);
      });
      // the connector, upright beside its contact numbers
      var bx = left ? x.leftBar : x.rightBar;
      el('rect', { x: bx, y: y0 - C - 6, width: 12, height: body + 2 * C + 12, rx: 3, class: 'pd-bar' }, under);
      text(over, bx + 6, y0 - C - 12, e.designator, 'pd-bar-label');
      // its contact numbers
      pins.forEach(function (pin, i) {
        var cx = left ? x.leftNum : x.rightNum, cy = y0 + i * ROW, g = el('g', { class: 'pd-contact' }, over);
        el('title', {}, g).textContent = e.designator + ':' + pin + (signal[e.id + ':' + pin] ? ' ' + signal[e.id + ':' + pin] : '');
        el('line', { x1: left ? bx + 12 : cx + C, y1: cy, x2: left ? cx - C : bx, y2: cy, class: 'pd-stub' }, under);
        el('circle', { cx: cx, cy: cy, r: C }, g);
        text(g, cx, cy + 4, pin, 'pd-num');
        rows[e.id + ':' + pin] = { x: left ? x.left : x.right, y: cy, left: left };
        remember(e.id + ':' + pin, g);
      });
      top[s] = y0 + Math.max(body + 2 * C, f.h) + 90;
    });

    // the wires
    var x1 = x.left + 110, x4 = x.right - 110, mid = (x1 + x4) / 2, drawn = [];
    function colourOf(w) { var c = colours[w.colour] || ''; return c && c.indexOf('gradient') === -1 ? c : (c ? '#22c55e' : '#64748b'); }
    function wire(w, d, dashed) {
      var g = el('g', { class: 'pd-wire' }, wiresG);
      el('title', {}, g).textContent = (w.signal || signal[w.from + ':' + w.from_pin] || '') + (w.set ? ' · set ' + w.set + ', ' + w.type.toLowerCase() : '');
      el('path', { d: d, class: 'pd-wire-edge' + (dashed ? ' dashed' : '') }, g);
      var core = el('path', { d: d, class: 'pd-wire-core' + (dashed ? ' dashed' : '') }, g);
      core.style.stroke = colourOf(w);
      if (w.colour === 'green/yellow') el('path', { d: d, class: 'pd-wire-core', style: 'stroke:#facc15', 'stroke-dasharray': '8 8' }, g);
      drawn.push({ w: w, g: g });
      return g;
    }
    var ellipses = {};   // set + end id: its ellipse {cx, bottom}
    setOrder.forEach(function (s) {
      if (!shielded(s.type)) return;
      data.ends.forEach(function (e) {
        var ys = s.wires.filter(function (w) { return w.type !== 'Shield'; }).map(function (w) {
          var at = rows[w.from === e.id ? w.from + ':' + w.from_pin : w.to === e.id ? w.to + ':' + w.to_pin : ''];
          return at ? at.y : null;
        }).filter(function (y) { return y !== null; });
        if (!ys.length) return;
        var left = side[e.id] === 'left', cx = left ? x.left + 45 : x.right - 45;
        var y0 = Math.min.apply(null, ys) - 22, y1 = Math.max.apply(null, ys) + 22;
        var g = el('ellipse', { cx: cx, cy: (y0 + y1) / 2, rx: 18, ry: (y1 - y0) / 2, class: 'pd-shield', 'data-set': s.name }, over);
        el('title', {}, g).textContent = 'Set ' + s.name + ': ' + s.type.toLowerCase();
        ellipses[s.name + ':' + e.id] = { cx: cx, bottom: y1 };
      });
    });
    data.wires.forEach(function (w) {
      var a = rows[w.from + ':' + w.from_pin], b = rows[w.to + ':' + w.to_pin];
      if (!a || !b) return;
      if (a.left === b.left) {   // both ends on one side: a loop into the middle
        var out = a.left ? 1 : -1;
        wire(w, 'M' + a.x + ',' + a.y + ' H' + (a.x + out * 160) + ' V' + b.y + ' H' + b.x);
        return;
      }
      if (!a.left) { var t = a; a = b; b = t; }
      var s = w.set && sets[w.set];
      if (w.type === 'Shield' && s) {   // the shield: to the ellipses, dashed between them
        var ea = ellipses[w.set + ':' + (rows[w.from + ':' + w.from_pin].left ? w.from : w.to)];
        var eb = ellipses[w.set + ':' + (rows[w.from + ':' + w.from_pin].left ? w.to : w.from)];
        if (ea && eb) {
          wire(w, 'M' + a.x + ',' + a.y + ' L' + ea.cx + ',' + ea.bottom);
          wire(w, 'M' + ea.cx + ',' + ea.bottom + ' H' + eb.cx, true);
          wire(w, 'M' + eb.cx + ',' + eb.bottom + ' L' + b.x + ',' + b.y);
          return;
        }
      }
      if (s && twisted(s.type)) {   // twisted: the first wire in a V, the others in a Λ, crossing in the middle
        var pair = s.wires.filter(function (o) { return o.type !== 'Shield'; });
        var ys = [];
        pair.forEach(function (o) {
          [rows[o.from + ':' + o.from_pin], rows[o.to + ':' + o.to_pin]].forEach(function (r) { if (r) ys.push(r.y); });
        });
        var high = Math.min.apply(null, ys), low = Math.max.apply(null, ys), i = pair.indexOf(w);
        var peak = i === 0 ? { x: mid, y: low + 14 } : { x: mid + (i - (pair.length) / 2) * 50, y: high - 14 - (i - 1) * 16 };
        wire(w, 'M' + a.x + ',' + a.y + ' H' + x1 + ' L' + peak.x + ',' + peak.y + ' L' + x4 + ',' + b.y + ' H' + b.x);
        return;
      }
      wire(w, 'M' + a.x + ',' + a.y + ' H' + x1 + ' L' + x4 + ',' + b.y + ' H' + b.x);
    });

    var bottom = Math.max(top.left, top.right) - 50;
    svg.setAttribute('viewBox', '0 0 ' + width + ' ' + bottom);
    svg.style.maxWidth = width + 'px';

    var picked = null;
    function show(set) {   // light up one set (or none)
      picked = picked === set ? null : set;
      chips.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.dataset.set === picked); });
      svg.classList.toggle('picking', picked !== null);
      svg.querySelectorAll('.lit').forEach(function (n) { n.classList.remove('lit'); });
      if (picked === null) return;
      svg.querySelectorAll('.pd-shield[data-set="' + picked.replace(/"/g, '\\"') + '"]').forEach(function (n) { n.classList.add('lit'); });
      drawn.forEach(function (d) {
        if (d.w.set !== picked) return;
        d.g.classList.add('lit');
        [[d.w.from, d.w.from_pin], [d.w.to, d.w.to_pin]].forEach(function (p) {
          (lit[p[0] + ':' + p[1]] || []).forEach(function (n) { n.classList.add('lit'); });
        });
      });
    }
    setOrder.forEach(function (s) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'btn small'; b.dataset.set = s.name;
      b.textContent = 'Set ' + s.name + ' · ' + s.type.toLowerCase();
      b.addEventListener('click', function () { show(s.name); });
      chips.appendChild(b);
    });
    drawn.forEach(function (d) { if (d.w.set) d.g.addEventListener('click', function () { show(d.w.set); }); });
  }

  window.Pinout = { draw: draw };
})();

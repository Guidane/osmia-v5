/* The connector editor: a family's face as seen from the pin side. Contacts are dragged where they sit (on a grid of
   half the pitch, or freely), picked to renumber or take away, added. The outline is a box, a D-sub or round, fitted
   around them, or one of its own: its corners dragged, a new corner pulled out of the middle of an edge, a picked
   corner taken away. The view fits the window; zoomed (buttons, the wheel) and moved by dragging what is empty. Saved as {shape, contacts: [[number, x, y]], outline: [[x, y]]} (inventory.faces fits it again). */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg', R = 10, PITCH = 26, MARGIN = 16, GRID = PITCH / 2, MAX_FIT = 4, K = 14;
  var data = JSON.parse(document.getElementById('connector-face').textContent);
  var shape = data.shape || 'rect', contacts = (data.contacts || []).map(function (c) { return [String(c[0]), +c[1], +c[2]]; });
  var corners = (data.outline || []).map(function (p) { return [+p[0], +p[1]]; });
  var svg = document.querySelector('[data-canvas]'), picked = null, corner = null, drag = null, size = { w: 0, h: 0 };
  var shapeIn = document.querySelector('[data-shape]'), snapIn = document.querySelector('[data-snap]');
  var pickedBox = document.querySelector('[data-picked]'), numberIn = document.querySelector('[data-number]');
  var cornerBox = document.querySelector('[data-corner]');
  var zoom = 1, pan = [0, 0], fitted = null, view = { scale: 1 }, panning = null, zoomLevel = document.querySelector('[data-zoom-level]');

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(e);
    return e;
  }
  function min(list) { return Math.min.apply(null, list); }
  function max(list) { return Math.max.apply(null, list); }

  function fit() {   // everything moved to start at the margin, and the outline's size (as inventory.faces.fitted)
    var dx, dy, w, h;
    if (shape === 'custom') {   // its own corners: moved by whole grid steps, so contacts stay on the grid
      var xs = corners.map(function (p) { return p[0]; }).concat(contacts.map(function (c) { return c[1] - R - 4; }));
      var ys = corners.map(function (p) { return p[1]; }).concat(contacts.map(function (c) { return c[2] - R - 4; }));
      dx = Math.ceil(-min(xs) / GRID) * GRID; dy = Math.ceil(-min(ys) / GRID) * GRID;
      w = max(corners.map(function (p) { return p[0]; }).concat(contacts.map(function (c) { return c[1] + R + 4; }))) + dx;
      h = max(corners.map(function (p) { return p[1]; }).concat(contacts.map(function (c) { return c[2] + R + 4; }))) + dy;
      corners.forEach(function (p) { p[0] += dx; p[1] += dy; });
    } else {
      if (!contacts.length) return { w: 2 * (MARGIN + R), h: 2 * (MARGIN + R), dx: 0, dy: 0 };
      var cx = contacts.map(function (c) { return c[1]; }), cy = contacts.map(function (c) { return c[2]; });
      dx = MARGIN + R - min(cx); dy = MARGIN + R - min(cy);
      w = max(cx) - min(cx) + 2 * (MARGIN + R); h = max(cy) - min(cy) + 2 * (MARGIN + R);
      if (shape === 'circle') { var side = Math.max(w, h); dx += (side - w) / 2; dy += (side - h) / 2; w = h = side; }
      if (shape === 'dsub') { dx += GRID; w += PITCH; }
    }
    contacts.forEach(function (c) { c[1] += dx; c[2] += dy; });
    return { w: w, h: h, dx: dx, dy: dy };
  }

  function cornersOf(from, w, h) {   // the outline as it is drawn now, as corners to move
    if (from === 'dsub') return [[0, 0], [w, 0], [w - K, h], [K, h]];
    if (from === 'circle') {
      var out = [];
      for (var i = 0; i < 16; i++) {
        var a = 2 * Math.PI * i / 16;
        out.push([Math.round(w / 2 + w / 2 * Math.cos(a)), Math.round(h / 2 + h / 2 * Math.sin(a))]);
      }
      return out;
    }
    return [[0, 0], [w, 0], [w, h], [0, h]];
  }

  function draw(moving) {   // moving: as it is (nothing fitted while something is dragged)
    if (!moving) {   // everything moved and the outline grown: the view stays where it was (no zooming to fit)
      var was = size;
      size = fit();
      if (was.w) pan = [pan[0] + size.dx + (was.w - size.w) / 2, pan[1] + size.dy + (was.h - size.h) / 2];
    }
    // the window's width and the height left in it, the face in the middle at the size that fits, times the zoom
    var w = size.w, h = size.h, cw = Math.max(svg.parentNode.clientWidth - 20, 200);
    var ch = Math.max(window.innerHeight - svg.parentNode.getBoundingClientRect().top - 58, 220);
    if (fitted === null) fitted = Math.min(cw / (w + 4 * PITCH), ch / (h + 4 * PITCH), MAX_FIT);   // on opening, and Fit
    var scale = fitted * zoom, W = cw / scale, H = ch / scale;
    var x0 = w / 2 + pan[0] - W / 2, y0 = h / 2 + pan[1] - H / 2;
    view = { scale: scale };
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute('viewBox', [x0, y0, W, H].join(' '));
    svg.setAttribute('width', cw);
    svg.setAttribute('height', ch);
    for (var gx = Math.floor(x0 / GRID) * GRID; gx <= x0 + W; gx += GRID) el('line', { x1: gx, y1: y0, x2: gx, y2: y0 + H, class: 'conn-grid' }, svg);
    for (var gy = Math.floor(y0 / GRID) * GRID; gy <= y0 + H; gy += GRID) el('line', { x1: x0, y1: gy, x2: x0 + W, y2: gy, class: 'conn-grid' }, svg);
    zoomLevel.textContent = Math.round(zoom * 100) + '%';
    if (shape === 'custom') {
      el('path', { d: 'M' + corners.map(function (p) { return p.join(','); }).join(' L') + ' Z', class: 'pd-face', 'stroke-linejoin': 'round' }, svg);
    } else if (shape === 'circle') el('circle', { cx: w / 2, cy: h / 2, r: Math.min(w, h) / 2, class: 'pd-face' }, svg);
    else if (shape === 'dsub') el('path', { d: 'M0,0 H' + w + ' L' + (w - K) + ',' + h + ' H' + K + ' Z', class: 'pd-face', 'stroke-linejoin': 'round' }, svg);
    else el('rect', { x: 0, y: 0, width: w, height: h, rx: 6, class: 'pd-face' }, svg);
    contacts.forEach(function (c) {
      var g = el('g', { class: 'pd-pin conn-contact' + (c === picked ? ' chosen' : '') }, svg);
      el('circle', { cx: c[1], cy: c[2], r: R }, g);
      var t = el('text', { x: c[1], y: c[2] + 4, class: 'pd-num' }, g);
      t.textContent = c[0];
      g.addEventListener('pointerdown', function (e) { start(e, { contact: c }); });
    });
    if (shape === 'custom') {
      corners.forEach(function (p, i) {   // between two corners: pulled out, a new one
        var q = corners[(i + 1) % corners.length], mid = el('circle', { cx: (p[0] + q[0]) / 2, cy: (p[1] + q[1]) / 2, r: 5 / view.scale, class: 'conn-mid' }, svg);
        mid.addEventListener('pointerdown', function (e) {
          var added = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
          corners.splice(i + 1, 0, added);
          start(e, { corner: added });
        });
      });
      corners.forEach(function (p) {
        var hs = 6 / view.scale, c = el('rect', { x: p[0] - hs, y: p[1] - hs, width: 2 * hs, height: 2 * hs, rx: hs / 3, class: 'conn-corner' + (p === corner ? ' chosen' : '') }, svg);
        c.addEventListener('pointerdown', function (e) { start(e, { corner: p }); });
      });
    }
    pickedBox.hidden = !picked;
    cornerBox.hidden = !corner;
    if (picked && document.activeElement !== numberIn) numberIn.value = picked[0];
    var face = { shape: shape, contacts: contacts };
    if (shape === 'custom') face.outline = corners;
    document.querySelector('[data-face]').value = JSON.stringify(face);
  }

  function point(e) {   // where the pointer is, in the drawing's units
    var m = svg.getScreenCTM().inverse(), p = svg.createSVGPoint();
    p.x = e.clientX; p.y = e.clientY;
    p = p.matrixTransform(m);
    return [p.x, p.y];
  }
  function snap(v) { return snapIn.checked ? Math.round(v / GRID) * GRID : Math.round(v * 2) / 2; }

  function start(e, what) {   // a contact or a corner taken hold of
    e.preventDefault();
    e.stopPropagation();
    picked = what.contact || null;
    corner = what.corner || null;
    var at = point(e), xy = picked ? [picked[1], picked[2]] : corner;
    drag = { dx: xy[0] - at[0], dy: xy[1] - at[1] };
    svg.setPointerCapture(e.pointerId);
    draw(true);
  }
  svg.addEventListener('pointermove', function (e) {
    if (panning) {
      pan = [panning.pan[0] - (e.clientX - panning.x) / view.scale, panning.pan[1] - (e.clientY - panning.y) / view.scale];
      draw(true);
      return;
    }
    if (!drag) return;
    var at = point(e), x = snap(at[0] + drag.dx), y = snap(at[1] + drag.dy);
    if (picked) { picked[1] = x; picked[2] = y; } else { corner[0] = x; corner[1] = y; }
    draw(true);
  });
  svg.addEventListener('pointerup', function () { panning = null; if (drag) { drag = null; draw(); } });
  svg.addEventListener('pointerdown', function (e) {   // on nothing: nothing picked, and the view moved by dragging
    picked = corner = null;
    panning = { x: e.clientX, y: e.clientY, pan: pan.slice() };
    svg.setPointerCapture(e.pointerId);
    draw(true);
  });

  function zoomBy(factor, e) {   // around the pointer (else the middle): what is under it stays under it
    var was = zoom;
    zoom = Math.min(Math.max(zoom * factor, 0.25), 8);
    if (e) {
      var at = point(e), c = [size.w / 2 + pan[0], size.h / 2 + pan[1]], k = was / zoom;
      pan = [at[0] - (at[0] - c[0]) * k - size.w / 2, at[1] - (at[1] - c[1]) * k - size.h / 2];
    }
    draw(true);
  }
  svg.addEventListener('wheel', function (e) { e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15, e); }, { passive: false });
  document.querySelector('[data-zoom-in]').addEventListener('click', function () { zoomBy(1.25); });
  document.querySelector('[data-zoom-out]').addEventListener('click', function () { zoomBy(1 / 1.25); });
  document.querySelector('[data-zoom-fit]').addEventListener('click', function () { zoom = 1; pan = [0, 0]; fitted = null; draw(true); });

  function takeAway() {
    if (picked) contacts.splice(contacts.indexOf(picked), 1);
    else if (corner && corners.length > 3) corners.splice(corners.indexOf(corner), 1);
    picked = corner = null;
    draw();
  }
  shapeIn.addEventListener('change', function () {
    if (shapeIn.value === 'custom' && shape !== 'custom') corners = cornersOf(shape, size.w, size.h);
    shape = shapeIn.value;
    corner = null;
    draw();
  });
  numberIn.addEventListener('input', function () { if (picked) { picked[0] = numberIn.value.trim(); draw(); } });
  numberIn.addEventListener('blur', function () { draw(); });
  document.querySelector('[data-remove]').addEventListener('click', takeAway);
  document.querySelector('[data-remove-corner]').addEventListener('click', takeAway);
  document.querySelector('[data-add]').addEventListener('click', function () {   // the next number, right of the others
    var numbers = contacts.map(function (c) { return parseInt(c[0], 10); }).filter(function (n) { return !isNaN(n); });
    var right = contacts.length ? max(contacts.map(function (c) { return c[1]; })) + PITCH : MARGIN + R;
    var top = contacts.length ? min(contacts.map(function (c) { return c[2]; })) : MARGIN + R;
    picked = [String(numbers.length ? max(numbers) + 1 : contacts.length + 1), right, top];
    corner = null;
    contacts.push(picked);
    draw();
  });
  document.addEventListener('keydown', function (e) {
    if ((picked || corner) && (e.key === 'Delete' || e.key === 'Backspace') && document.activeElement === document.body) takeAway();
  });
  var later;
  window.addEventListener('resize', function () { clearTimeout(later); later = setTimeout(function () { if (!drag) draw(true); }, 150); });
  draw();
})();

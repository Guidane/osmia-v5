/* A project configuration drawn: each device a box listing its connectors, each harness a pill joined to the
   connectors its ends plug into. Drag a box to move it (saved in the configuration); click a box or a harness to find
   it in the lists below; what the configuration added is green, what it changed orange, what it took away faded. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var W = 200, HEAD = 42, ROW = 24, PAD = 8;

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, value, cls) { var t = el('text', { x: x, y: y, class: cls }, parent); t.textContent = value; return t; }
  function height(d) { return HEAD + Math.max(d.connectors.length, 1) * ROW + PAD; }

  function draw(svg, data, opts) {
    if (!svg) return;
    var byKey = {};
    data.devices.forEach(function (d) { byKey[d.key] = d; });

    function port(end) {   // where an end's line meets its device: the connector's row, the side facing (x, y) chosen later
      var d = byKey[end.device];
      if (!d) return null;
      var i = d.connectors.findIndex(function (c) { return c.id === end.connector; });
      return { d: d, y: d.y + (i < 0 ? HEAD / 2 : HEAD + i * ROW + ROW / 2), known: i >= 0 };
    }

    function render() {
      svg.innerHTML = '';
      var lines = el('g', {}, svg), boxes = el('g', {}, svg), pills = el('g', {}, svg);
      data.ghosts.forEach(function (g) {
        el('rect', { x: g.x, y: g.y, width: W, height: HEAD, rx: 8, class: 'ghost' }, boxes);
        text(boxes, g.x + 12, g.y + 26, g.label + ' (taken away)', 'ghost-label');
      });
      data.devices.forEach(function (d) {
        var g = el('g', { class: 'device ' + d.state, 'data-key': d.key, transform: 'translate(' + d.x + ',' + d.y + ')' }, boxes);
        el('rect', { width: W, height: height(d), rx: 8, class: 'box' }, g);
        el('rect', { width: W, height: 6, rx: 3, fill: d.colour }, g);
        text(g, 12, 24, d.label, 'label');
        text(g, 12, 37, d.number + ' · ' + d.name, 'sub');
        d.connectors.forEach(function (c, i) {
          var y = HEAD + i * ROW;
          el('line', { x1: 0, x2: W, y1: y, y2: y, class: 'row-line' }, g);
          text(g, 12, y + 16, c.designator, 'conn');
          text(g, 52, y + 16, c.name.length > 20 ? c.name.slice(0, 19) + '…' : c.name, 'conn-name');
        });
        if (!d.connectors.length) text(g, 12, HEAD + 16, 'no connectors', 'conn-name');
      });
      data.harnesses.forEach(function (h) {
        var ports = h.ends.map(port).filter(Boolean);
        var cx, cy;
        if (ports.length) {
          cx = ports.reduce(function (s, p) { return s + p.d.x + W / 2; }, 0) / ports.length;
          cy = ports.reduce(function (s, p) { return s + p.y; }, 0) / ports.length;
          var lefts = ports.map(function (p) { return p.d.x; });
          if (Math.max.apply(null, lefts) - Math.min.apply(null, lefts) < W) {   // one above the other (or one device): beside them
            cx = Math.max.apply(null, lefts) + W + 80;
          }
        } else { cx = 60; cy = 20; }
        var cls = 'harness ' + h.state + (h.bad ? ' bad' : '');
        ports.forEach(function (p) {
          var side = cx < p.d.x + W / 2 ? p.d.x : p.d.x + W;
          var bend = (side === p.d.x ? -1 : 1) * 60;
          el('path', { d: 'M' + cx + ',' + cy + ' C' + (cx - bend * 0.2) + ',' + cy + ' ' + (side + bend) + ',' + p.y + ' ' + side + ',' + p.y,
                       class: 'wire ' + cls }, lines);
          el('circle', { cx: side, cy: p.y, r: 4, class: 'port ' + cls }, lines);
        });
        var label = h.number, w = 16 + label.length * 7.5;
        var pill = el('g', { class: 'pill ' + cls, 'data-harness': h.key }, pills);
        el('title', {}, pill).textContent = h.number + ' ' + h.name + (h.bad ? ' (see what to look at)' : '');
        el('rect', { x: cx - w / 2, y: cy - 11, width: w, height: 22, rx: 11 }, pill);
        text(pill, cx, cy + 4, label, 'pill-label');
      });
      fit();
    }

    function fit() {
      var xs = [0], ys = [0], xe = [400], ye = [200];
      data.devices.concat(data.ghosts).forEach(function (d) {
        xs.push(d.x); ys.push(d.y); xe.push(d.x + W); ye.push(d.y + (d.connectors ? height(d) : HEAD));
      });
      var x0 = Math.min.apply(null, xs) - 40, y0 = Math.min.apply(null, ys) - 30;
      var x1 = Math.max.apply(null, xe) + 140, y1 = Math.max.apply(null, ye) + 30;
      svg.setAttribute('viewBox', [x0, y0, x1 - x0, y1 - y0].join(' '));
      svg.style.height = Math.min(Math.max((y1 - y0) * Math.min(1, svg.clientWidth / (x1 - x0 || 1)), 260), 720) + 'px';
    }

    function point(ev) {
      var p = svg.createSVGPoint();
      p.x = ev.clientX; p.y = ev.clientY;
      return p.matrixTransform(svg.getScreenCTM().inverse());
    }

    var drag = null;
    svg.addEventListener('pointerdown', function (ev) {
      var g = ev.target.closest('.device'), pill = ev.target.closest('.pill');
      if (pill) { show('har-' + pill.getAttribute('data-harness')); return; }
      if (!g) return;
      var d = byKey[g.getAttribute('data-key')], p = point(ev);
      drag = { d: d, dx: p.x - d.x, dy: p.y - d.y, moved: false, g: g };
      svg.setPointerCapture(ev.pointerId);
    });
    svg.addEventListener('pointermove', function (ev) {
      if (!drag) return;
      var p = point(ev);
      drag.d.x = Math.round((p.x - drag.dx) / 10) * 10;
      drag.d.y = Math.round((p.y - drag.dy) / 10) * 10;
      drag.moved = true;
      drag.g.setAttribute('transform', 'translate(' + drag.d.x + ',' + drag.d.y + ')');
    });
    svg.addEventListener('pointerup', function () {
      if (!drag) return;
      var d = drag.d, moved = drag.moved;
      drag = null;
      if (!moved) { show('dev-' + d.key); return; }
      render();
      var body = new URLSearchParams({ action: 'move', config: opts.config, key: d.key, x: d.x, y: d.y });
      fetch(opts.url, { method: 'POST', body: body, headers: { 'X-CSRFToken': opts.csrf } });
    });

    function show(id) {
      var row = document.getElementById(id);
      if (!row) return;
      document.querySelectorAll('tr.placed.picked').forEach(function (r) { r.classList.remove('picked'); });
      row.classList.add('picked');
      row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    render();
    window.addEventListener('resize', fit);
  }

  window.Diagram = { draw: draw };
})();

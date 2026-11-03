/* A project configuration drawn: each device a box listing its connectors, each connector a square on the box's
   side (click it for its pinout; drag from it to another square to make a harness between the two, its wires matched by
   signal, else by pin number), each harness a pill joined to the squares of the connectors its ends plug into. Drag a box to move it (saved in the configuration), its lines going with it; click a
   box or a harness to find it in the lists below; what the configuration added is green, what it changed orange, what
   it took away faded. Zoom with the buttons or Ctrl + the wheel; drag the background to move around. */
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
    var view = null, zoomed = false;   // the part of the drawing shown; zoomed: chosen by hand, so it stays

    function port(end) {   // where an end's line meets its device: the connector's row, the side facing (x, y) chosen later
      var d = byKey[end.device];
      if (!d) return null;
      var i = d.connectors.findIndex(function (c) { return c.id === end.connector; });
      return { d: d, y: d.y + (i < 0 ? HEAD / 2 : HEAD + i * ROW + ROW / 2), known: i >= 0, connector: end.connector };
    }

    var lines, boxes, squares, pills;
    function render() {
      svg.innerHTML = '';
      lines = el('g', {}, svg); boxes = el('g', {}, svg); squares = el('g', {}, svg); pills = el('g', {}, svg);
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
      harnesses();
      if (!zoomed) fit(); else show();
    }

    function harnesses() {   // the lines, the connector squares and the pills: drawn again whenever a device moves
      lines.innerHTML = ''; squares.innerHTML = ''; pills.innerHTML = '';
      var sides = {};   // device key + connector: the side its square is on (where its lines come in)
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
          if (p.known) sides[p.d.key + ':' + p.connector] = { x: side, cls: cls };
          else el('circle', { cx: side, cy: p.y, r: 4, class: 'port ' + cls }, lines);
        });
        var label = h.number, w = 16 + label.length * 7.5;
        var pill = el('g', { class: 'pill ' + cls, 'data-harness': h.key }, pills);
        el('title', {}, pill).textContent = h.number + ' ' + h.name + (h.bad ? ' (see what to look at)' : '');
        el('rect', { x: cx - w / 2, y: cy - 11, width: w, height: 22, rx: 11 }, pill);
        text(pill, cx, cy + 4, label, 'pill-label');
      });
      data.devices.forEach(function (d) {
        d.connectors.forEach(function (c, i) {
          var at = sides[d.key + ':' + c.id], y = d.y + HEAD + i * ROW + ROW / 2;
          var sq = el('rect', { x: (at ? at.x : d.x + W) - 6, y: y - 6, width: 12, height: 12, rx: 2,
                                class: 'sq' + (at ? ' on ' + at.cls : ''), 'data-device': d.key, 'data-connector': c.id }, squares);
          el('title', {}, sq).textContent = c.designator + (c.name ? ' ' + c.name : '') + ': ' + c.pins.length + ' pin' + (c.pins.length === 1 ? '' : 's');
        });
      });
    }

    function match(a, b) {   // the wires between two connectors: [pin of a, pin of b, signal, set] by signal, else by number
      var used = {}, out = [];
      var name = function (p) { return (p[1] || '').trim().toLowerCase(); };
      a.pins.forEach(function (pa) {
        var free = b.pins.filter(function (pb) { return !used[pb[0]]; });
        var pb = name(pa) && free.find(function (p) { return name(p) === name(pa); });
        if (!pb) pb = free.find(function (p) { return p[0] === pa[0] && (!name(pa) || !name(p)); });
        if (!pb) return;
        used[pb[0]] = true;
        var set = pa[2] ? pa : pb;
        out.push([pa[0], pb[0], pa[1] || pb[1], set[2] ? set[2] + ' · ' + set[3].toLowerCase() : '']);
      });
      return out;
    }

    function connect(a, b) {   // the popup making a harness between the connectors a and b
      var box = opts.connect;
      if (!box) return;
      var form = box.querySelector('form');
      form.elements.a.value = a.d.key; form.elements.a_connector.value = a.c.id;
      form.elements.b.value = b.d.key; form.elements.b_connector.value = b.c.id;
      form.elements.name.value = (a.d.label + ' ' + a.c.designator + ' – ' + b.d.label + ' ' + b.c.designator).slice(0, 200);
      box.querySelector('[data-a]').textContent = 'P1 · ' + a.d.label + ' ' + a.c.designator;
      box.querySelector('[data-b]').textContent = 'P2 · ' + b.d.label + ' ' + b.c.designator;
      form.elements.a_part.value = ''; form.elements.b_part.value = '';
      var body = box.querySelector('tbody'), wires = match(a.c, b.c);
      body.replaceChildren();
      wires.forEach(function (w) {
        var tr = document.createElement('tr'), td = document.createElement('td'), tick = document.createElement('input');
        tick.type = 'checkbox'; tick.name = 'wire'; tick.checked = true; tick.value = JSON.stringify([w[0], w[1]]);
        tick.setAttribute('aria-label', 'Wire ' + w[0] + ' to ' + w[1]);
        td.appendChild(tick); tr.appendChild(td);
        w.forEach(function (value, i) { var c = document.createElement('td'); c.textContent = value; if (i > 1) c.className = 'small'; tr.appendChild(c); });
        body.appendChild(tr);
      });
      box.querySelector('[data-none]').hidden = wires.length > 0;
      box.querySelector('[data-all-wires]').checked = true;
      box.showModal();
      form.elements.name.select();
    }

    function pinout(d, c) {   // the connector's pins in the popup
      var box = opts.pinout;
      if (!box) return;
      box.querySelector('[data-title]').textContent = d.label + ' · ' + c.designator + (c.name ? ' ' + c.name : '') + (c.part ? ' · ' + c.part : '');
      box.querySelector('[data-edit]').href = c.pins_url;
      var body = box.querySelector('tbody');
      body.replaceChildren();
      c.pins.forEach(function (p) {
        var tr = document.createElement('tr');
        p.forEach(function (value, i) {
          var td = document.createElement('td'); td.textContent = value; if (i > 1) td.className = 'small'; tr.appendChild(td);
        });
        body.appendChild(tr);
      });
      box.querySelector('[data-none]').hidden = c.pins.length > 0;
      box.showModal();
    }

    function fit() {   // everything in view, the drawing as tall as it needs (within limits)
      var xs = [0], ys = [0], xe = [400], ye = [200];
      data.devices.concat(data.ghosts).forEach(function (d) {
        xs.push(d.x); ys.push(d.y); xe.push(d.x + W); ye.push(d.y + (d.connectors ? height(d) : HEAD));
      });
      var x0 = Math.min.apply(null, xs) - 40, y0 = Math.min.apply(null, ys) - 30;
      var x1 = Math.max.apply(null, xe) + 140, y1 = Math.max.apply(null, ye) + 30;
      svg.style.height = Math.min(Math.max((y1 - y0) * Math.min(1, svg.clientWidth / (x1 - x0 || 1)), 260), 720) + 'px';
      view = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
      zoomed = false;
      show();
    }

    function show() { svg.setAttribute('viewBox', [view.x, view.y, view.w, view.h].join(' ')); }

    function zoom(factor, at) {   // factor < 1 comes closer; around ``at`` (drawing units), else the middle
      var w = view.w * factor;
      if (w < 150 || w > 20000) return;
      at = at || { x: view.x + view.w / 2, y: view.y + view.h / 2 };
      view = { x: at.x - (at.x - view.x) * factor, y: at.y - (at.y - view.y) * factor, w: w, h: view.h * factor };
      zoomed = true;
      show();
    }

    function point(ev) {
      var p = svg.createSVGPoint();
      p.x = ev.clientX; p.y = ev.clientY;
      return p.matrixTransform(svg.getScreenCTM().inverse());
    }

    var drag = null, pan = null, link = null;

    function square(sq) {
      var d = byKey[sq.getAttribute('data-device')], id = +sq.getAttribute('data-connector');
      return { d: d, c: d.connectors.find(function (c) { return c.id === id; }) };
    }
    svg.addEventListener('pointerdown', function (ev) {
      var g = ev.target.closest('.device'), pill = ev.target.closest('.pill'), sq = ev.target.closest('.sq');
      if (pill) { pick('har-' + pill.getAttribute('data-harness')); return; }
      if (sq) {   // a click: its pinout; dragged onto another square: a harness between them
        link = { from: square(sq), x: +sq.getAttribute('x') + 6, y: +sq.getAttribute('y') + 6, moved: false };
        svg.setPointerCapture(ev.pointerId);
        return;
      }
      if (!g) {   // the background: move the view
        pan = { at: point(ev) };
        svg.setPointerCapture(ev.pointerId);
        svg.classList.add('panning');
        return;
      }
      var dev = byKey[g.getAttribute('data-key')], p = point(ev);
      drag = { d: dev, dx: p.x - dev.x, dy: p.y - dev.y, moved: false, g: g };
      svg.setPointerCapture(ev.pointerId);
    });
    svg.addEventListener('pointermove', function (ev) {
      if (link) {
        var at = point(ev);
        if (!link.moved && Math.abs(at.x - link.x) + Math.abs(at.y - link.y) < 6) return;
        link.moved = true;
        link.line = link.line || el('path', { class: 'linking' }, svg);
        link.line.setAttribute('d', 'M' + link.x + ',' + link.y + ' L' + at.x + ',' + at.y);
        return;
      }
      if (pan) {
        var now = point(ev);
        view.x -= now.x - pan.at.x; view.y -= now.y - pan.at.y;
        zoomed = true;
        show();
        return;
      }
      if (!drag) return;
      var p = point(ev);
      var x = Math.round((p.x - drag.dx) / 10) * 10, y = Math.round((p.y - drag.dy) / 10) * 10;
      if (x === drag.d.x && y === drag.d.y) return;
      drag.d.x = x; drag.d.y = y;
      drag.moved = true;
      drag.g.setAttribute('transform', 'translate(' + x + ',' + y + ')');
      harnesses();
    });
    svg.addEventListener('pointerup', function (ev) {
      if (link) {
        var from = link.from, moved = link.moved;
        if (link.line) link.line.remove();
        link = null;
        if (!moved) { pinout(from.d, from.c); return; }
        var hit = document.elementFromPoint(ev.clientX, ev.clientY), to = hit && hit.closest('.sq');
        if (to) {
          to = square(to);
          if (to.d !== from.d || to.c !== from.c) connect(from, to);
        }
        return;
      }
      if (pan) { pan = null; svg.classList.remove('panning'); return; }
      if (!drag) return;
      var d = drag.d, moved = drag.moved;
      drag = null;
      if (!moved) { pick('dev-' + d.key); return; }
      if (!zoomed) fit();
      var body = new URLSearchParams({ action: 'move', config: opts.config, key: d.key, x: d.x, y: d.y });
      fetch(opts.url, { method: 'POST', body: body, headers: { 'X-CSRFToken': opts.csrf } });
    });
    svg.addEventListener('wheel', function (ev) {
      if (!ev.ctrlKey) return;   // the wheel alone scrolls the page
      ev.preventDefault();
      zoom(ev.deltaY > 0 ? 1.15 : 1 / 1.15, point(ev));
    }, { passive: false });
    [opts.pinout, opts.connect].forEach(function (box) {
      if (box) box.querySelector('[data-close]').addEventListener('click', function () { box.close(); });
    });
    if (opts.connect) opts.connect.querySelector('[data-all-wires]').addEventListener('change', function (ev) {
      opts.connect.querySelectorAll('[name=wire]').forEach(function (t) { t.checked = ev.target.checked; });
    });
    (opts.zoom || []).forEach(function (b) {
      b.addEventListener('click', function () {
        if (b.dataset.zoom === 'fit') fit(); else zoom(b.dataset.zoom === 'in' ? 1 / 1.25 : 1.25);
      });
    });

    function pick(id) {
      var row = document.getElementById(id);
      if (!row) return;
      document.querySelectorAll('tr.placed.picked').forEach(function (r) { r.classList.remove('picked'); });
      row.classList.add('picked');
      row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    render();
    window.addEventListener('resize', function () { if (!zoomed) fit(); });
  }

  window.Diagram = { draw: draw };
})();

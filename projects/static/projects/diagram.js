/* A project configuration drawn: each device a box with its name; each of its connectors a square, with its name, on
   the box's outline (drag it along the outline to move it, saved with the device; click it for its pinout; drag it away
   onto another square to make a harness between the two, its wires matched by signal, else by pin number); each harness
   a pill joined to the squares of the connectors its ends plug into, each line with a handle (grey: it finds its own
   way; click or drag it to pin it there, blue; click a blue one to let it go). Drag a box to move it (saved in the
   configuration), its lines going with it; click a box or a harness to find it in the lists below; what the
   configuration added is green, what it changed orange, what it took away faded. Zoom with the buttons or Ctrl + the
   wheel; drag the background to move around. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var SIDES = { top: [0, -1], right: [1, 0], bottom: [0, 1], left: [-1, 0] };

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, value, cls) { var t = el('text', { x: x, y: y, class: cls }, parent); t.textContent = value; return t; }

  function size(d) {   // a box big enough for the squares on its sides
    var n = { top: 0, right: 0, bottom: 0, left: 0 };
    (d.connectors || []).forEach(function (c) { n[c.side || c.auto || 'right'] += 1; });
    return { w: Math.max(170, 30 + 56 * Math.max(n.top, n.bottom)), h: Math.max(64, 22 + 30 * Math.max(n.left, n.right)) };
  }

  function spot(d, c) {   // where a connector's square sits: {x, y, nx, ny} (ny, nx: outwards)
    var s = size(d), side = c.side || c.auto || 'right', along = c.along;
    if (!c.side) {   // not placed by hand: spread along the side facing what it is plugged into
      var loose = d.connectors.filter(function (o) { return !o.side && (o.auto || 'right') === side; });
      along = (loose.indexOf(c) + 1) / (loose.length + 1);
    }
    var n = SIDES[side];
    var x = side === 'left' ? d.x : side === 'right' ? d.x + s.w : d.x + s.w * along;
    var y = side === 'top' ? d.y : side === 'bottom' ? d.y + s.h : d.y + s.h * along;
    return { x: x, y: y, nx: n[0], ny: n[1] };
  }

  function onOutline(d, p) {   // the side and place on a box's outline nearest to p
    var s = size(d), best = null;
    [['top', d.x, d.y, d.x + s.w, d.y], ['bottom', d.x, d.y + s.h, d.x + s.w, d.y + s.h],
     ['left', d.x, d.y, d.x, d.y + s.h], ['right', d.x + s.w, d.y, d.x + s.w, d.y + s.h]].forEach(function (e) {
      var horizontal = e[2] !== e[1], length = horizontal ? s.w : s.h;
      var along = Math.min(Math.max(((horizontal ? p.x - e[1] : p.y - e[2]) / length), 0.08), 0.92);
      var x = horizontal ? e[1] + along * length : e[1], y = horizontal ? e[2] : e[2] + along * length;
      var far = Math.hypot(p.x - x, p.y - y);
      if (!best || far < best.far) best = { side: e[0], along: Math.round(along * 1000) / 1000, far: far };
    });
    return best;
  }

  function outside(d, p) {   // how far p is from a box (0 inside it)
    var s = size(d);
    return Math.hypot(Math.max(d.x - p.x, 0, p.x - d.x - s.w), Math.max(d.y - p.y, 0, p.y - d.y - s.h));
  }

  function curve(points, n) {   // a smooth line through points, leaving the first along n
    var p = [{ x: points[0].x - n.x * 80, y: points[0].y - n.y * 80 }].concat(points);
    var last = points[points.length - 1], before = points[points.length - 2];
    p.push({ x: 2 * last.x - before.x, y: 2 * last.y - before.y });
    var d = 'M' + p[1].x + ',' + p[1].y;
    for (var i = 1; i < p.length - 2; i++) {
      d += ' C' + (p[i].x + (p[i + 1].x - p[i - 1].x) / 6) + ',' + (p[i].y + (p[i + 1].y - p[i - 1].y) / 6) + ' ' +
           (p[i + 1].x - (p[i + 2].x - p[i].x) / 6) + ',' + (p[i + 1].y - (p[i + 2].y - p[i].y) / 6) + ' ' + p[i + 1].x + ',' + p[i + 1].y;
    }
    return d;
  }

  function draw(svg, data, opts) {
    if (!svg) return;
    var byKey = {};
    data.devices.forEach(function (d) { byKey[d.key] = d; });
    var view = null, zoomed = false;   // the part of the drawing shown; zoomed: chosen by hand, so it stays
    var handleAt = {};                 // harness key + end: where its handle is drawn now

    function port(end) {   // where an end's line meets its device: its connector's square, else the right side
      var d = byKey[end.device];
      if (!d) return null;
      var c = d.connectors.find(function (o) { return o.id === end.connector; });
      var at = c ? spot(d, c) : { x: d.x + size(d).w, y: d.y + size(d).h / 2, nx: 1, ny: 0 };
      return { d: d, c: c, end: end, x: at.x, y: at.y, n: { x: at.nx, y: at.ny } };
    }

    function facing() {   // a connector not placed by hand: on the side of its box facing what its harness goes to
      data.devices.forEach(function (d) { d.connectors.forEach(function (c) { c.auto = null; }); });
      data.harnesses.forEach(function (h) {
        var ends = h.ends.map(function (e) { return { e: e, d: byKey[e.device] }; }).filter(function (x) { return x.d; });
        ends.forEach(function (x) {
          var c = x.d.connectors.find(function (o) { return o.id === x.e.connector; });
          var others = ends.filter(function (o) { return o.d !== x.d; });
          if (!c || c.side || !others.length) return;
          var s = size(x.d), cx = x.d.x + s.w / 2, cy = x.d.y + s.h / 2;
          var dx = others.reduce(function (t, o) { return t + o.d.x + size(o.d).w / 2; }, 0) / others.length - cx;
          var dy = others.reduce(function (t, o) { return t + o.d.y + size(o.d).h / 2; }, 0) / others.length - cy;
          // left or right unless what it goes to is well above or below (boxes are wide, harnesses mostly run across)
          c.auto = Math.abs(dx) >= Math.abs(dy) / 2 ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'bottom' : 'top');
        });
      });
    }

    var lines, boxes, squares, pills;
    function render() {
      svg.innerHTML = '';
      lines = el('g', {}, svg); boxes = el('g', {}, svg); squares = el('g', {}, svg); pills = el('g', {}, svg);
      data.ghosts.forEach(function (g) {
        el('rect', { x: g.x, y: g.y, width: 170, height: 64, rx: 8, class: 'ghost' }, boxes);
        text(boxes, g.x + 85, g.y + 36, g.label + ' (taken away)', 'ghost-label');
      });
      data.devices.forEach(function (d) {
        var g = el('g', { class: 'device ' + d.state, 'data-key': d.key, transform: 'translate(' + d.x + ',' + d.y + ')' }, boxes);
        el('title', {}, g).textContent = d.number + ' · ' + d.name;
        d.box = el('rect', { rx: 8, class: 'box' }, g);
        d.bar = el('rect', { height: 6, rx: 3, fill: d.colour }, g);
        d.name_ = text(g, 0, 0, d.label, 'label');
      });
      harnesses();
      if (!zoomed) fit(); else show();
    }

    function harnesses() {   // what moves with a device: its box's size, the lines, squares, handles and pills
      lines.innerHTML = ''; squares.innerHTML = ''; pills.innerHTML = '';
      data.devices.forEach(function (d) {
        var s = size(d);
        d.box.setAttribute('width', s.w); d.box.setAttribute('height', s.h); d.bar.setAttribute('width', s.w);
        d.name_.setAttribute('x', s.w / 2); d.name_.setAttribute('y', s.h / 2 + 5);
      });
      facing();
      var used = {};   // device key + connector: the class of the harness plugged into it
      data.harnesses.forEach(function (h) {
        var ports = h.ends.map(port).filter(Boolean);
        var c = { x: 60, y: 20 };
        if (ports.length) {
          var reach = ports.length > 1 ? 70 : 110;
          c = { x: ports.reduce(function (s, p) { return s + p.x + p.n.x * reach; }, 0) / ports.length,
                y: ports.reduce(function (s, p) { return s + p.y + p.n.y * reach; }, 0) / ports.length };
        }
        var cls = 'harness ' + h.state + (h.bad ? ' bad' : '');
        ports.forEach(function (p) {
          var pinned = h.handles[p.end.id];
          var at = pinned ? { x: pinned[0], y: pinned[1] } : { x: (p.x + p.n.x * 40 + c.x) / 2, y: (p.y + p.n.y * 40 + c.y) / 2 };
          handleAt[h.key + ':' + p.end.id] = at;
          el('path', { d: curve([{ x: p.x, y: p.y }, at, c], p.n), class: 'wire ' + cls }, lines);
          var dot = el('circle', { cx: at.x, cy: at.y, r: 5, class: 'handle' + (pinned ? ' pinned' : ''), 'data-harness': h.key, 'data-end': p.end.id }, pills);
          el('title', {}, dot).textContent = pinned ? 'Pinned: click to let it go, drag to move it' : 'Click or drag to pin the line here';
          if (p.c) used[p.d.key + ':' + p.c.id] = cls;
          else el('circle', { cx: p.x, cy: p.y, r: 4, class: 'port ' + cls }, lines);
        });
        var label = h.number, w = 16 + label.length * 7.5;
        var pill = el('g', { class: 'pill ' + cls, 'data-harness': h.key }, pills);
        el('title', {}, pill).textContent = h.number + ' ' + h.name + (h.bad ? ' (see what to look at)' : '');
        el('rect', { x: c.x - w / 2, y: c.y - 11, width: w, height: 22, rx: 11 }, pill);
        text(pill, c.x, c.y + 4, label, 'pill-label');
      });
      (data.requests || []).forEach(function (r) {   // asked for, not made yet
        var a = byKey[r.a], b = byKey[r.b];
        if (!a || !b) return;
        var sa = size(a), sb = size(b);
        var ax = a.x + sa.w / 2, ay = a.y + sa.h / 2, bx = b.x + sb.w / 2, by = b.y + sb.h / 2;
        el('path', { d: 'M' + ax + ',' + ay + ' L' + bx + ',' + by, class: 'requested' }, lines);
        var mark = el('g', { class: 'pill requested-pill', 'data-request': r.id }, pills);
        el('title', {}, mark).textContent = 'Asked for: ' + r.text;
        el('rect', { x: (ax + bx) / 2 - 34, y: (ay + by) / 2 - 10, width: 68, height: 20, rx: 10 }, mark);
        text(mark, (ax + bx) / 2, (ay + by) / 2 + 4, 'requested', 'pill-label');
      });
      data.devices.forEach(function (d) {
        d.connectors.forEach(function (c) {
          var at = spot(d, c), w = Math.max(24, 12 + c.designator.length * 7), on = used[d.key + ':' + c.id];
          var sq = el('g', { class: 'sq' + (on ? ' on ' + on : ''), 'data-device': d.key, 'data-connector': c.id }, squares);
          el('title', {}, sq).textContent = c.designator + (c.name ? ' ' + c.name : '') + ': ' + c.pins.length + ' pin' + (c.pins.length === 1 ? '' : 's');
          el('rect', { x: at.x - w / 2, y: at.y - 10, width: w, height: 20, rx: 3 }, sq);
          text(sq, at.x, at.y + 4, c.designator, 'sq-label');
        });
      });
    }

    function match(a, b) {   // the wires between two connectors: [pin of a, pin of b, signal, set] by signal, else by number
      var taken = {}, out = [];
      var name = function (p) { return (p[1] || '').trim().toLowerCase(); };
      a.pins.forEach(function (pa) {
        var free = b.pins.filter(function (pb) { return !taken[pb[0]]; });
        var pb = name(pa) && free.find(function (p) { return name(p) === name(pa); });
        if (!pb) pb = free.find(function (p) { return p[0] === pa[0] && (!name(pa) || !name(p)); });
        if (!pb) return;
        taken[pb[0]] = true;
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
      data.devices.forEach(function (d) { var s = size(d); xs.push(d.x); ys.push(d.y); xe.push(d.x + s.w); ye.push(d.y + s.h); });
      data.ghosts.forEach(function (g) { xs.push(g.x); ys.push(g.y); xe.push(g.x + 170); ye.push(g.y + 64); });
      Object.keys(handleAt).forEach(function (k) { xs.push(handleAt[k].x); ys.push(handleAt[k].y); xe.push(handleAt[k].x); ye.push(handleAt[k].y); });
      var x0 = Math.min.apply(null, xs) - 140, y0 = Math.min.apply(null, ys) - 60;
      var x1 = Math.max.apply(null, xe) + 140, y1 = Math.max.apply(null, ye) + 60;
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

    function send(fields) {
      fetch(opts.url, { method: 'POST', body: new URLSearchParams(Object.assign({ config: opts.config }, fields)),
                        headers: { 'X-CSRFToken': opts.csrf } });
    }

    var drag = null, pan = null, grab = null, pull = null;

    function square(sq) {
      var d = byKey[sq.getAttribute('data-device')], id = +sq.getAttribute('data-connector');
      return { d: d, c: d.connectors.find(function (c) { return c.id === id; }) };
    }
    function harness(key) { return data.harnesses.find(function (h) { return h.key === key; }); }

    svg.addEventListener('pointerdown', function (ev) {
      var t = ev.target, g = t.closest('.device'), pill = t.closest('.pill'), sq = t.closest('.sq'), dot = t.closest('.handle');
      if (dot) {   // a harness line's handle
        var h = harness(dot.getAttribute('data-harness'));
        pull = { h: h, end: dot.getAttribute('data-end'), was: !!h.handles[dot.getAttribute('data-end')], moved: false };
      } else if (pill) {
        pick(pill.dataset.request ? 'req-' + pill.dataset.request : 'har-' + pill.getAttribute('data-harness'));
        return;
      } else if (sq) {   // along the outline: moved; away from it: a harness to another square; a click: its pinout
        var from = square(sq);
        grab = { from: from, start: point(ev), side: from.c.side, along: from.c.along, mode: null, at: spot(from.d, from.c) };
      } else if (g) {
        var dev = byKey[g.getAttribute('data-key')], p = point(ev);
        drag = { d: dev, dx: p.x - dev.x, dy: p.y - dev.y, moved: false, g: g };
      } else {   // the background: move the view
        pan = { at: point(ev) };
        svg.classList.add('panning');
      }
      svg.setPointerCapture(ev.pointerId);
    });
    svg.addEventListener('pointermove', function (ev) {
      var p;
      if (pull) {
        p = point(ev);
        pull.h.handles[pull.end] = [Math.round(p.x), Math.round(p.y)];
        pull.moved = true;
        harnesses();
        return;
      }
      if (grab) {
        p = point(ev);
        if (!grab.mode && Math.hypot(p.x - grab.start.x, p.y - grab.start.y) < 5) return;
        if (grab.mode !== 'link' && outside(grab.from.d, p) > 30) {   // pulled away: a harness, the square back where it was
          grab.mode = 'link';
          grab.from.c.side = grab.side; grab.from.c.along = grab.along;
          harnesses();
        }
        if (grab.mode === 'link') {
          grab.line = grab.line || el('path', { class: 'linking' }, svg);
          grab.line.setAttribute('d', 'M' + grab.at.x + ',' + grab.at.y + ' L' + p.x + ',' + p.y);
        } else {
          grab.mode = 'slide';
          var place = onOutline(grab.from.d, p);
          grab.from.c.side = place.side; grab.from.c.along = place.along;
          harnesses();
        }
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
      p = point(ev);
      var x = Math.round((p.x - drag.dx) / 10) * 10, y = Math.round((p.y - drag.dy) / 10) * 10;
      if (x === drag.d.x && y === drag.d.y) return;
      drag.d.x = x; drag.d.y = y;
      drag.moved = true;
      drag.g.setAttribute('transform', 'translate(' + x + ',' + y + ')');
      harnesses();
    });
    svg.addEventListener('pointerup', function (ev) {
      if (pull) {
        var h = pull.h, end = pull.end;
        if (!pull.moved && pull.was) delete h.handles[end];   // a click on a pinned one: let go
        else if (!pull.moved) { var at = handleAt[h.key + ':' + end]; h.handles[end] = [Math.round(at.x), Math.round(at.y)]; }
        pull = null;
        harnesses();
        var pinned = h.handles[end];
        send(pinned ? { action: 'handle', key: h.key, end: end, x: pinned[0], y: pinned[1] } : { action: 'handle', key: h.key, end: end });
        return;
      }
      if (grab) {
        var from = grab.from, mode = grab.mode;
        if (grab.line) grab.line.remove();
        grab = null;
        if (!mode) { pinout(from.d, from.c); return; }
        if (mode === 'slide') { send({ action: 'place_connector', connector: from.c.id, side: from.c.side, along: from.c.along }); return; }
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
      send({ action: 'move', key: d.key, x: d.x, y: d.y });
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

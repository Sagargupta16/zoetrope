'use strict';
// Kit graphics: drawn devices any build can use as an overlay type. Each is a pure function of time.
//   signal  a scope trace that changes character on cue: tone, data, noise, flat
//   pulse   a dot of light travelling between two named ends, with a running count
//   disc    a gold record that turns
//   blocks  a memory grid: one cell fails, the lit cells move to free ones
//   meter   a bar that drains
// Promoted from the films of 2026-11-24 and 2026-11-25 (each film had its own copy):
//   punch     a punch-in on the picture layer alone, so type, chips and the tag stand still
//   hush      draws nothing: it carries "says" for a stretch in which a device says the line
//   plate     one of the build's pictures, blurred past reading, at a chosen brightness
//   light     a soft warm light on a blurred plate, under the tag and the type
//   topshade  the kit's top shade at a chosen strength, under the tag
//   ground    a plain plate drawn by the stage, as a shot's media (no generated picture, so no tag)
//   veil      soft spots and bands over parts of a shot's picture, following the camera
//   stepsrow  a row of numbered step chips that light in turn
//   reasons   the film's question as numbered answers at title size; an open one shows a question mark
//   answers   answers at title size, each under a chip that names whose answer it is
//   words     words in their own script, each with its Roman spelling and its meaning
//   document  a document redrawn on a paper card, with a line that says it is redrawn
//   years     a rail of years with a large counter that shows its last value only on its cue
// A film's own graphics.js loads after this file, so a device it defines under one of these names replaces
// the kit's for that film.
(() => {
  const { h, lerp, remap, clamp, ease, spring, hash, noise } = Stage;
  const { graphic, pop, slide } = Kit;
  const svgNode = (tag, attrs) => {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  };

  // signal: {y, h, standing, modes: [{at, mode, badge, tone}]}; at is absolute seconds (the builder resolves
  // cues). One panel, two lanes: DATA (a thick accent wave) and SIGNAL (the thin carrier under it).
  //   data     the data lane carries its wave, the signal lane runs
  //   tone     the data lane falls flat and grey, the signal lane keeps running (a signal with no data)
  //   noise    the data lane is jagged (unreadable), the signal lane runs
  //   carrier  as tone, with the signal lane lit in the accent colour and a pulse running along it
  //   flat     both lanes flat
  // badge is the state word at the right of the lane it speaks about; tone is red, green or accent.
  graphic('signal', (wrap, spec, ctx) => {
    const W = 936, H = spec.h || 250, N = 220, X0 = 204, X1 = W - 26;
    const box = h('div', { class: 'k-panel' });
    box.style.top = (spec.y === undefined ? 620 : spec.y) + 'px';
    box.style.height = H + 'px';
    const yData = H * 0.36, yCar = H * 0.79, aData = H * 0.24, aCar = H * 0.085;
    const svg = svgNode('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H });
    const rule = y => svgNode('line', { x1: X0, y1: y, x2: X1, y2: y, stroke: 'rgba(255,255,255,0.14)', 'stroke-width': 2 });
    const poly = (stroke, width) => svgNode('polyline', { fill: 'none', stroke, 'stroke-width': width, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' });
    const dataUnder = poly('rgba(0,0,0,0.55)', 12), dataLine = poly('var(--accent)', 6);
    const carUnder = poly('rgba(0,0,0,0.55)', 9), carLine = poly('#ffffff', 4);
    svg.append(rule(yData), rule(yCar), dataUnder, dataLine, carUnder, carLine);
    const nameData = h('div', { class: 'k-lane', 'data-role': 'label', text: spec.dataName || 'DATA' });
    const nameCar = h('div', { class: 'k-lane', 'data-role': 'label', text: spec.signalName || 'SIGNAL' });
    nameData.style.top = (yData - 17).toFixed(0) + 'px';
    nameCar.style.top = (yCar - 17).toFixed(0) + 'px';
    const badge = h('div', { class: 'k-badge', 'data-role': 'label', text: '' });
    box.append(svg, nameData, nameCar, badge);
    wrap.appendChild(box);
    const modes = (spec.modes && spec.modes.length ? spec.modes : [{ at: ctx.at, mode: 'tone' }]).slice().sort((a, b) => a.at - b.at);
    const dataWave = (mode, x, t, i) => {
      if (mode === 'data') {
        const bit = hash(Math.floor(x * 24 - t * 7) + 3) > 0.5 ? 0.92 : 0.3;
        return Math.sin(2 * Math.PI * (12 * x - 2.6 * t)) * bit;
      }
      if (mode === 'noise') return (hash(i * 13.7 + Math.floor(t * 30) * 7.1) * 2 - 1) * 0.95;
      return 0;
    };
    const hasData = mode => mode === 'data' || mode === 'noise';
    return t => {
      // The waves run on the device's own clock, so the same signal draws the same frames wherever it stands.
      // A standing signal is the exception: it continues the signal of the shot before it, so its waves stay
      // on film time and do not jump at the cut (after a moved cut the film comparison names such a shot).
      const lt = spec.standing ? t : t - ctx.at;
      let k = 0;
      for (let i = 0; i < modes.length; i++) if (t >= modes[i].at) k = i;
      const cur = modes[k], prev = modes[Math.max(0, k - 1)];
      const mix = k === 0 ? 1 : ease.outCubic(remap(t, cur.at, cur.at + 0.38));
      // standing: the panel carries over from the shot before, so it neither pops nor draws in again.
      const grow = spec.standing ? 1 : ease.outExpo(remap(t, ctx.at + 0.05, ctx.at + 0.55));
      const lit = cur.mode === 'carrier' ? mix : prev.mode === 'carrier' && k > 0 ? 1 - mix : 0;
      const carOn = cur.mode === 'flat' ? 1 - mix : prev.mode === 'flat' && k > 0 ? mix : 1;
      // The data lane's trace stops short of a badge that sits on it.
      const words = cur.badge || '';
      const onData = cur.lane !== 'signal';
      // This frame's badge is set before its width is read, so a seek draws the same trace as playing through.
      if (badge.textContent !== words) badge.textContent = words;
      badge.className = 'k-badge ' + (cur.tone || (cur.mode === 'data' ? 'green' : 'red'));
      badge.style.display = words ? 'block' : 'none';
      const room = words && onData ? badge.offsetWidth + 30 : 0;
      let dataPts = '', carPts = '';
      for (let i = 0; i <= N; i++) {
        const x = i / N, px = X0 + x * (X1 - X0), on = x <= grow ? 1 : 0;
        const dpx = X0 + x * (X1 - room - X0);
        const d = lerp(dataWave(prev.mode, x, lt, i), dataWave(cur.mode, x, lt, i), mix) * on;
        dataPts += dpx.toFixed(1) + ',' + (yData - d * aData).toFixed(1) + ' ';
        // The carrier: a steady small wave; when lit, a bump travels along it.
        const bump = lit ? 1 + 0.6 * Math.exp(-Math.pow((x - (((t - cur.at) * 0.55) % 1.3)) / 0.09, 2)) * lit : 1;
        const c = Math.sin(2 * Math.PI * (7 * x - 1.5 * lt)) * carOn * on * bump;
        carPts += px.toFixed(1) + ',' + (yCar - c * aCar * (1 + 0.3 * lit)).toFixed(1) + ' ';
      }
      dataUnder.setAttribute('points', dataPts);
      dataLine.setAttribute('points', dataPts);
      carUnder.setAttribute('points', carPts);
      carLine.setAttribute('points', carPts);
      // A lane with nothing on it turns thin and grey.
      const alive = lerp(hasData(prev.mode) ? 1 : 0, hasData(cur.mode) ? 1 : 0, mix);
      dataLine.setAttribute('stroke', alive > 0.5 ? 'var(--accent)' : 'rgba(255,255,255,0.42)');
      dataLine.setAttribute('stroke-width', lerp(3, 6, alive).toFixed(2));
      carLine.setAttribute('stroke', lit > 0.5 ? 'var(--accent)' : '#ffffff');
      carLine.setAttribute('stroke-width', lerp(4, 7, lit).toFixed(2));
      badge.style.top = ((onData ? yData : yCar) - 31).toFixed(0) + 'px';
      if (words) {
        // A badge that carries over from the mode before does not land again.
        const born = (k === 0 && spec.standing) || (k > 0 && prev.badge === words) ? -10 : cur.at;
        const s = spring(t - born, 4.2, 0.5);
        badge.style.opacity = t < born ? '0' : '1';
        badge.style.transform = 'scale(' + lerp(1.5, 1, s).toFixed(4) + ')';
      }
      if (!spec.standing) pop(box, t, ctx.at, { rise: 30, from: 0.94 });
    };
  });

  // pulse: {y, from, to, trips: [{t0, t1, dir, label}], count: {to, unit}}; t0 and t1 are absolute seconds
  graphic('pulse', (wrap, spec, ctx) => {
    const W = 936;
    const box = h('div', { class: 'k-pulse' });
    box.style.top = (spec.y === undefined ? 700 : spec.y) + 'px';
    const big = h('div', { class: 'k-pulse-big', 'data-role': 'number', text: '' });
    if (spec.size) big.style.fontSize = spec.size + 'px';
    const dot = h('div', { class: 'k-pulse-dot' });
    const tail = h('div', { class: 'k-pulse-tail' });
    const a = h('div', { class: 'k-pulse-end a', 'data-role': 'label', text: spec.from || 'EARTH' });
    const b = h('div', { class: 'k-pulse-end b', 'data-role': 'label', text: spec.to || '' });
    box.append(big, h('div', { class: 'k-pulse-line' }), tail, dot, h('div', { class: 'k-pulse-node a' }), h('div', { class: 'k-pulse-node b' }), a, b);
    wrap.appendChild(box);
    const trips = spec.trips || [{ t0: ctx.at + 0.3, t1: (ctx.out === null ? ctx.shot.t1 : ctx.out) - 0.2, dir: 1 }];
    return t => {
      let trip = trips[0], p = 0;
      for (const item of trips) if (t >= item.t0) { trip = item; }
      p = clamp((t - trip.t0) / (trip.t1 - trip.t0));
      const x = (trip.dir === -1 ? 1 - p : p) * W;
      dot.style.transform = 'translate(' + x.toFixed(1) + 'px, 0)';
      const len = Math.min(170, p * W, (1 - p) * W + 170) * (p > 0 && p < 1 ? 1 : 0);
      tail.style.width = len.toFixed(1) + 'px';
      tail.style.transform = 'translate(' + (trip.dir === -1 ? x : x - len).toFixed(1) + 'px, 0)';
      tail.style.background = 'linear-gradient(' + (trip.dir === -1 ? 270 : 90) + 'deg, rgba(255,214,10,0), var(--accent))';
      dot.style.opacity = t < trips[0].t0 ? '0' : '1';
      if (spec.count) {
        // The count runs on its own trip when it names one (count.trip), else on the current trip.
        const own = spec.count.trip === undefined ? trip : trips[spec.count.trip];
        const cp = clamp((t - own.t0) / (own.t1 - own.t0));
        const dec = spec.count.decimals || 0;
        const v = spec.count.to * cp;
        big.textContent = (cp >= 0.999 && spec.count.display ? spec.count.display : (dec ? v.toFixed(dec) : String(Math.round(v))) + ' ' + spec.count.unit);
      } else {
        big.textContent = trip.label || '';
      }
      slide(box, t, ctx.at, { dx: 0 });
      pop(big, t, trip.t0 - 0.05, { rise: 20, from: 0.9 });
    };
  });

  // disc: {x, y, r}
  graphic('disc', (wrap, spec, ctx) => {
    const r = spec.r || 300;
    const hold = h('div', { class: 'k-disc-hold' });
    hold.style.left = (spec.x === undefined ? 540 : spec.x) + 'px';
    hold.style.top = (spec.y === undefined ? 760 : spec.y) + 'px';
    const disc = h('div', { class: 'k-disc' });
    disc.style.width = disc.style.height = 2 * r + 'px';
    const etch = svgNode('svg', { width: 2 * r, height: 2 * r, viewBox: '-100 -100 200 200', class: 'k-disc-etch' });
    for (let i = 0; i < 14; i++) {
      const ang = -1.25 + i * 0.19 + (hash(i + 5) - 0.5) * 0.08;
      const len = 26 + hash(i + 9) * 46;
      etch.appendChild(svgNode('line', { x1: -62, y1: 34, x2: (-62 + Math.cos(ang) * len).toFixed(1), y2: (34 + Math.sin(ang) * len).toFixed(1), stroke: 'rgba(60,38,0,0.75)', 'stroke-width': 1.1 }));
    }
    etch.appendChild(svgNode('circle', { cx: 44, cy: -46, r: 24, fill: 'none', stroke: 'rgba(60,38,0,0.75)', 'stroke-width': 1.3 }));
    etch.appendChild(svgNode('circle', { cx: 44, cy: -46, r: 3, fill: 'rgba(60,38,0,0.75)' }));
    etch.appendChild(svgNode('circle', { cx: 40, cy: 44, r: 8, fill: 'none', stroke: 'rgba(60,38,0,0.75)', 'stroke-width': 1.2 }));
    etch.appendChild(svgNode('circle', { cx: 62, cy: 44, r: 8, fill: 'none', stroke: 'rgba(60,38,0,0.75)', 'stroke-width': 1.2 }));
    etch.appendChild(svgNode('line', { x1: 48, y1: 44, x2: 54, y2: 44, stroke: 'rgba(60,38,0,0.75)', 'stroke-width': 1.2 }));
    const shine = h('div', { class: 'k-disc-shine' });
    shine.style.width = shine.style.height = 2 * r + 'px';
    disc.appendChild(etch);
    hold.append(disc, shine);
    wrap.appendChild(hold);
    return t => {
      const s = spring(t - ctx.at, 2.6, 0.62);
      hold.style.opacity = t < ctx.at ? '0' : Math.min(1, (t - ctx.at) / 0.1).toFixed(3);
      hold.style.transform = 'translate(-50%,-50%) scale(' + lerp(0.6, 1, s).toFixed(4) + ')';
      disc.style.transform = 'rotate(' + ((t - ctx.at) * 14).toFixed(2) + 'deg)';
      shine.style.transform = 'rotate(' + (noise(3, (t - ctx.at) * 0.4) * 10).toFixed(2) + 'deg)';
    };
  });

  // blocks: {y, cols, rows, code: [cells], bad: cell, to: [cells], failAt, moveAt}; times are absolute seconds
  graphic('blocks', (wrap, spec, ctx) => {
    const cols = spec.cols || 8, rows = spec.rows || 4, gap = 14;
    const size = Math.floor((936 - gap * (cols - 1)) / cols);
    const grid = h('div', { class: 'k-blocks' });
    grid.style.top = (spec.y === undefined ? 640 : spec.y) + 'px';
    grid.style.height = rows * size + (rows - 1) * gap + 'px';
    const at = i => [(i % cols) * (size + gap), Math.floor(i / cols) * (size + gap)];
    for (let i = 0; i < cols * rows; i++) {
      const cell = h('div', { class: 'k-cell' });
      const [x, y] = at(i);
      cell.style.left = x + 'px';
      cell.style.top = y + 'px';
      cell.style.width = cell.style.height = size + 'px';
      grid.appendChild(cell);
    }
    const bad = h('div', { class: 'k-cell bad' });
    const [bx, by] = at(spec.bad);
    bad.style.left = bx + 'px';
    bad.style.top = by + 'px';
    bad.style.width = bad.style.height = size + 'px';
    grid.appendChild(bad);
    const movers = spec.code.map((cell, n) => {
      const el = h('div', { class: 'k-cell code' });
      el.style.width = el.style.height = size + 'px';
      grid.appendChild(el);
      return { el, from: at(cell), to: at(spec.to[n]), n };
    });
    grid.appendChild(bad); // above the code cells: the failed cell shows at once, and its code flies out from under it
    // A line that joins the moved code again, in order, drawn on at linkAt (it never touches the failed cell).
    const centre = i => { const [x, y] = at(i); return (x + size / 2).toFixed(1) + ',' + (y + size / 2).toFixed(1); };
    const link = svgNode('svg', { width: 936, height: rows * size + (rows - 1) * gap, style: 'position:absolute;left:0;top:0;overflow:visible' });
    const linkPts = spec.to.map(centre).join(' ');
    const linkUnder = svgNode('polyline', { points: linkPts, fill: 'none', stroke: 'rgba(6,8,12,0.9)', 'stroke-width': 16, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', pathLength: 1, 'stroke-dasharray': 1, 'stroke-dashoffset': 1 });
    const linkLine = svgNode('polyline', { points: linkPts, fill: 'none', stroke: '#ffffff', 'stroke-width': 7, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', pathLength: 1, 'stroke-dasharray': 1, 'stroke-dashoffset': 1 });
    link.append(linkUnder, linkLine);
    grid.appendChild(link);
    wrap.appendChild(grid);
    const failAt = spec.failAt === undefined ? ctx.at + 0.6 : spec.failAt;
    const moveAt = spec.moveAt === undefined ? failAt + 1.2 : spec.moveAt;
    return t => {
      slide(grid, t, ctx.at, { dx: 0 });
      const f = remap(t, failAt, failAt + 0.25);
      bad.style.opacity = f.toFixed(3);
      const shake = (1 - remap(t, failAt, failAt + 0.5)) * (t >= failAt ? 1 : 0);
      bad.style.transform = 'translate(' + (noise(7, (t - failAt) * 40) * 8 * shake).toFixed(2) + 'px,' + (noise(8, (t - failAt) * 40) * 8 * shake).toFixed(2) + 'px)';
      for (const m of movers) {
        const p = ease.inOutCubic(remap(t, moveAt + m.n * 0.12, moveAt + m.n * 0.12 + 0.6));
        const x = lerp(m.from[0], m.to[0], p), y = lerp(m.from[1], m.to[1], p) - Math.sin(Math.PI * p) * 46;
        m.el.style.transform = 'translate(' + x.toFixed(2) + 'px,' + y.toFixed(2) + 'px)';
      }
      const drawn = spec.linkAt === undefined ? 0 : ease.inOutCubic(remap(t, spec.linkAt, spec.linkAt + 0.7));
      link.style.opacity = spec.linkAt === undefined || t < spec.linkAt ? '0' : '1';
      linkUnder.setAttribute('stroke-dashoffset', (1 - drawn).toFixed(4));
      linkLine.setAttribute('stroke-dashoffset', (1 - drawn).toFixed(4));
    };
  });

  // lamps: {y, total, cols, keep: [indices], offAt, step}; every lamp is lit, then all but `keep` go dark one by one
  graphic('lamps', (wrap, spec, ctx) => {
    const total = spec.total || 10, cols = spec.cols || 5, gap = 18;
    const rows = Math.ceil(total / cols);
    const size = Math.floor((936 - gap * (cols - 1)) / cols);
    const grid = h('div', { class: 'k-blocks' });
    grid.style.top = (spec.y === undefined ? 600 : spec.y) + 'px';
    grid.style.height = rows * size + (rows - 1) * gap + 'px';
    const keep = spec.keep || [];
    const lamps = [];
    let order = 0;
    for (let i = 0; i < total; i++) {
      const el = h('div', { class: 'k-lamp' });
      el.style.left = (i % cols) * (size + gap) + 'px';
      el.style.top = Math.floor(i / cols) * (size + gap) + 'px';
      el.style.width = el.style.height = size + 'px';
      const core = h('div', { class: 'k-lamp-core' });
      el.appendChild(core);
      grid.appendChild(el);
      const stays = keep.includes(i);
      lamps.push({ el, core, stays, n: stays ? 0 : order++ });
    }
    wrap.appendChild(grid);
    const offAt = spec.offAt === undefined ? ctx.at + 0.5 : spec.offAt;
    const step = spec.step === undefined ? 0.1 : spec.step;
    return t => {
      slide(grid, t, ctx.at, { dx: 0 });
      for (const lamp of lamps) {
        const lit = lamp.stays ? 1 : 1 - remap(t, offAt + lamp.n * step, offAt + lamp.n * step + 0.16);
        lamp.core.style.opacity = lit.toFixed(3);
        const beat = lamp.stays ? 1 + 0.05 * spring(t - (offAt + order * step), 3.2, 0.5) : 1;
        lamp.el.style.transform = 'scale(' + beat.toFixed(4) + ')';
      }
    };
  });

  // ladder: {y, standing, rows: [{label, value, state, at, hot, count: {to, unit, decimals, display, t0, t1}}]}
  // A list that builds across shots: a row is 'done' (its value stands), 'wait' (a dim question mark) or
  // 'count' (its value runs from t0 and lands on t1, in the accent colour) or 'reveal' (a question mark
  // until `at`, then its value in words; `hot` keeps it in the accent colour).
  graphic('ladder', (wrap, spec, ctx) => {
    // plate: a dark plate behind the rows, for a list that stands on a busy picture (y is then the plate's top,
    // 16 px above the first row)
    const box = h('div', { class: 'k-ladder' + (spec.plate ? ' plate' : '') });
    box.style.top = (spec.y === undefined ? 290 : spec.y) + 'px';
    const rows = spec.rows.map(r => {
      const val = h('span', { class: 'val', text: r.state === 'done' ? r.value : '?' });
      const el = h('div', { class: 'k-rung' + (r.state === 'wait' ? ' wait' : ''), 'data-role': 'body' }, [h('span', { class: 'name', text: r.label }), h('span', { class: 'dots' }), val]);
      box.appendChild(el);
      return { r, el, val };
    });
    wrap.appendChild(box);
    return t => {
      if (!spec.standing) slide(box, t, ctx.at, { dx: 0 });
      for (const x of rows) {
        // reveal: the row stands with a question mark and its value (words, not a count) lands at `at`.
        if (x.r.state === 'reveal') {
          const on = t >= x.r.at;
          x.val.textContent = on ? x.r.value : '?';
          x.el.className = 'k-rung' + (on ? (x.r.hot ? ' live' : '') : ' wait');
          x.val.style.transform = on ? 'scale(' + (1 + 0.16 * Math.max(0, 1 - spring(t - x.r.at, 3.4, 0.55))).toFixed(4) + ')' : '';
          continue;
        }
        if (x.r.state !== 'count') continue;
        const c = x.r.count;
        const p = clamp((t - c.t0) / Math.max(0.01, c.t1 - c.t0));
        const dec = c.decimals || 0;
        const v = c.to * p;
        const landed = p >= 0.999;
        x.val.textContent = t < c.t0 ? '?' : landed ? (c.display || x.r.value) : (dec ? v.toFixed(dec) : String(Math.round(v))) + ' ' + c.unit;
        x.el.className = 'k-rung' + (t < c.t0 ? ' wait' : ' live');
        x.val.style.transform = landed ? 'scale(' + (1 + 0.16 * Math.max(0, 1 - spring(t - c.t1, 3.4, 0.55))).toFixed(4) + ')' : '';
      }
    };
  });

  // strip: {y, from, to, marks: [{day, label, side, t0}]}; a row of numbered days; each mark lights at t0
  graphic('strip', (wrap, spec, ctx) => {
    const W = 880, n = spec.to - spec.from;
    const box = h('div', { class: 'k-strip' });
    box.style.top = (spec.y === undefined ? 600 : spec.y) + 'px';
    box.appendChild(h('div', { class: 'k-strip-plate' }));
    box.appendChild(h('div', { class: 'k-strip-line' }));
    for (let d = spec.from; d <= spec.to; d++) {
      const x = ((d - spec.from) / n) * W;
      const tick = h('div', { class: 'k-strip-tick' });
      tick.style.left = x.toFixed(1) + 'px';
      const num = h('div', { class: 'k-strip-day', 'data-role': 'label', text: String(d) });
      num.style.left = x.toFixed(1) + 'px';
      box.append(tick, num);
    }
    const marks = (spec.marks || []).map(m => {
      const x = ((m.day - spec.from) / n) * W;
      const dot = h('div', { class: 'k-strip-dot' });
      dot.style.left = x.toFixed(1) + 'px';
      const tag = h('div', { class: 'k-strip-tag ' + (m.side === 'down' ? 'down' : 'up'), 'data-role': 'label', text: m.label });
      const align = x < 120 ? 'left' : x > W - 120 ? 'right' : 'mid';
      tag.style.left = x.toFixed(1) + 'px';
      tag.style.transform = 'translateX(' + (align === 'left' ? '-6px' : align === 'right' ? 'calc(-100% + 6px)' : '-50%') + ')';
      tag.dataset.shift = tag.style.transform;
      box.append(dot, tag);
      return { m, dot, tag };
    });
    wrap.appendChild(box);
    return t => {
      slide(box, t, ctx.at, { dx: 0 });
      for (const x of marks) {
        const at = x.m.t0 === undefined ? ctx.at + 0.3 : x.m.t0;
        const s = spring(t - at, 4, 0.5);
        x.dot.style.opacity = t < at ? '0' : '1';
        x.dot.style.transform = 'translate(-50%,-50%) scale(' + lerp(0.2, 1, s).toFixed(4) + ')';
        x.tag.style.opacity = t < at ? '0' : Math.min(1, (t - at) / 0.08).toFixed(3);
        x.tag.style.transform = x.tag.dataset.shift + ' translateY(' + ((1 - s) * (x.m.side === 'down' ? -18 : 18)).toFixed(2) + 'px)';
      }
    };
  });

  // meter: {y, label, from, to, note}; drains from `from` to `to` (0 to 1) across the overlay's life
  graphic('meter', (wrap, spec, ctx) => {
    const fill = h('div', { class: 'k-meter-fill' });
    const name = h('div', { class: 'k-meter-name', 'data-role': 'label', text: spec.label || '' });
    const note = h('div', { class: 'k-meter-note', 'data-role': 'body', text: spec.note || '' });
    const box = h('div', { class: 'k-meter' }, [name, h('div', { class: 'k-meter-track' }, [fill]), note]);
    box.style.top = (spec.y === undefined ? 700 : spec.y) + 'px';
    wrap.appendChild(box);
    const end = (ctx.out === null ? ctx.shot.t1 : ctx.out) - 0.2;
    return t => {
      const p = ease.inOutCubic(remap(t, ctx.at + 0.4, end));
      fill.style.transform = 'scaleX(' + lerp(spec.from === undefined ? 1 : spec.from, spec.to === undefined ? 0.5 : spec.to, p).toFixed(4) + ')';
      slide(box, t, ctx.at, { dx: -30 });
    };
  });

  // route: {x, y, h, standing, travel, stops: [{name, date, note, at}]}: a journey told as a rail of named
  // stops, for films that may not show a map. The marker runs down the rail and reaches each stop at its
  // `at`; a reached stop is lit and its name stands white, the stops ahead are dim. `date` is a yellow chip
  // after the name, `note` a small line under it (a source, a qualifier).
  graphic('route', (wrap, spec, ctx) => {
    const tall = spec.h === undefined ? 600 : spec.h, n = spec.stops.length;
    const box = h('div', { class: 'k-route' });
    box.style.top = (spec.y === undefined ? 420 : spec.y) + 'px';
    box.style.height = tall + 'px';
    if (spec.big) box.className = 'k-route big';  // larger names, each note beside its name
    if (spec.x !== undefined) box.style.left = spec.x + 'px';
    const mark = h('div', { class: 'mark' });
    // One piece of rail per pair of stops, so a link the source only calls 'akin to' can be drawn dashed
    // (spec.dashed: the numbers of the stops such a link starts from, counted from 0).
    const segs = [];
    for (let i = 0; i < n - 1; i++) {
      const y0 = (i / (n - 1)) * tall, y1 = ((i + 1) / (n - 1)) * tall;
      const kind = (spec.dashed || []).includes(i) ? ' dashed' : '';
      const base = h('div', { class: 'line' + kind }), fill = h('div', { class: 'done' + kind });
      for (const el of [base, fill]) { el.style.top = y0.toFixed(1) + 'px'; el.style.bottom = 'auto'; el.style.height = (y1 - y0).toFixed(1) + 'px'; }
      box.append(base, fill);
      segs.push({ y0, y1, fill });
    }
    const stops = spec.stops.map((s, i) => {
      const y = n > 1 ? (i / (n - 1)) * tall : 0;
      const name = h('span', { class: 'name', 'data-role': 'body', text: s.name });
      const kids = [h('span', { class: 'ring' }), name];
      if (s.date) kids.push(h('span', { class: 'date', 'data-role': 'label', text: s.date }));
      if (s.note) kids.push(h('span', { class: 'note', 'data-role': 'source', text: s.note }));
      const el = h('div', { class: 'stop' }, kids);
      el.style.top = y.toFixed(1) + 'px';
      box.appendChild(el);
      return { s, y, el, name };
    });
    box.appendChild(mark);
    wrap.appendChild(box);
    const travel = spec.travel === undefined ? 0.6 : spec.travel;
    return t => {
      if (!spec.standing) slide(box, t, ctx.at, { dx: -30 });
      // The marker stands on the last stop reached, or is on its way to the next one.
      let y = stops[0].y;
      stops.forEach((x, i) => {
        const on = t >= x.s.at;
        x.el.className = 'stop' + (on ? ' on' : '');
        const beat = on ? 'scale(' + (1 + 0.08 * Math.max(0, 1 - spring(t - x.s.at, 3.6, 0.55))).toFixed(4) + ')' : '';
        // big: the note stands beside the name, so the whole row pops (a name alone would grow over its note)
        if (spec.big) x.el.style.transform = beat ? 'translateY(-50%) ' + beat : '';
        else x.name.style.transform = beat;
        if (i > 0 && t >= stops[i - 1].s.at) y = Math.max(y, lerp(stops[i - 1].y, x.y, ease.inOutCubic(remap(t, x.s.at - travel, x.s.at))));
      });
      mark.style.top = y.toFixed(1) + 'px';
      mark.style.opacity = t >= stops[0].s.at ? '1' : '0';
      segs.forEach(s => { s.fill.style.transform = 'scaleY(' + Math.min(1, Math.max(0, (y - s.y0) / (s.y1 - s.y0))).toFixed(4) + ')'; });
    };
  });

  // ---- devices promoted from the films (see the list at the top)
  const NEVER = 1e9;
  const beat = (t, at, k) => 1 + k * Math.max(0, 1 - spring(t - at, 3.6, 0.55));
  const camOf = wrap => wrap.parentElement && wrap.parentElement.querySelector('.cam');

  // punch: {at, from, d, to}: from its `at` the picture layer (the shot's camera) is `to` times larger (default
  // 1: a cut-in whose own camera is already tighter; `step` is the older name) and settles from `from` (1.06)
  // over `d` seconds (0.35). Type, chips and the tag stand still. It multiplies the transform the shot has just
  // set for this frame, so it stays a pure function of time.
  graphic('punch', (wrap, spec, ctx) => {
    const cam = camOf(wrap);
    const d = spec.d || 0.35, from = spec.from || 1.06, to = spec.to || spec.step || 1;
    return t => {
      const k = to * lerp(from, 1, ease.outExpo(remap(t, ctx.at, ctx.at + d)));
      if (cam && Math.abs(k - 1) > 0.0001) cam.style.transform += ' scale(' + k.toFixed(4) + ')';
    };
  });

  // hush: draws nothing. With "says" (true, or seconds) it marks a stretch where a device on screen speaks the
  // line, so the caption pages that would begin inside it are left out (build.py reads "says").
  graphic('hush', () => () => {});

  // plate: {src, blur, bright, sat}: one of the build's pictures, blurred until nothing in it can be read, as a
  // shot's media ({"kind": "none", "graphic": "plate", "src": "media/p01.jpg"}). blur is in px (22), bright
  // (0.8) and sat (1) finish the filter. A drawn shot carries no tag: the shot asks for it with "tag": true.
  graphic('plate', (wrap, spec) => {
    const pic = Stage.img(Kit.base() + spec.src);
    pic.style.filter = 'blur(' + (spec.blur === undefined ? 22 : spec.blur) + 'px) brightness(' + (spec.bright === undefined ? 0.8 : spec.bright) + ') saturate(' + (spec.sat === undefined ? 1 : spec.sat) + ')';
    pic.style.transform = 'scale(1.16)';
    wrap.appendChild(pic);
  });

  // light: {k}: a soft warm light inside the shot's camera layer, over the picture and under the tag, the shades
  // and every overlay, so only a blurred plate gets brighter. k is its strength at the centre (0.16 lifts a
  // plate of mean brightness 50 to a little over 60).
  graphic('light', (wrap, spec) => {
    const cam = camOf(wrap);
    const k = spec.k === undefined ? 0.16 : spec.k;
    if (cam) cam.appendChild(h('div', { class: 'k-light', style: { background: 'radial-gradient(120% 66% at 50% 36%, rgba(255, 222, 176, ' + k + ') 0%, rgba(255, 222, 176, 0) 100%)' } }));
  });

  // topshade: {k}: the gradient of the kit's "shade" right after the camera layer (over the picture, under the
  // tag), with k scaling its strength (1).
  graphic('topshade', (wrap, spec) => {
    const cam = camOf(wrap);
    const k = spec.k === undefined ? 1 : spec.k;
    const a = v => (v * k).toFixed(3);
    if (cam) cam.insertAdjacentElement('afterend', h('div', { class: 'k-top', style: { background: 'linear-gradient(180deg, rgba(4, 6, 10, ' + a(0.72) + ') 0%, rgba(4, 6, 10, ' + a(0.5) + ') 45%, rgba(4, 6, 10, 0) 100%)' } }));
  });

  // ground: {k}: a plain plate drawn by the stage, used as a shot's media ({"kind": "none", "graphic":
  // "ground"}): a soft warm dark gradient with no generated picture in it, so the kit puts no tag on the shot.
  // k is the strength of its warm glow (0.17). A redrawn document stands on it.
  graphic('ground', (cam, spec) => {
    const k = spec.k === undefined ? 0.17 : spec.k;
    cam.appendChild(h('div', { class: 'k-ground', style: { background: 'radial-gradient(120% 64% at 50% 30%, rgba(255, 214, 150, ' + k + ') 0%, rgba(255, 214, 150, 0) 64%), linear-gradient(180deg, #544539 0%, #453a2f 48%, #332a23 100%)' } }));
    return null;
  });

  // veil: {blur, soft, fog, tint, spots: [{x, y, rx, ry, fog, blur, path}], bands: [{y, h, feather}]}: an
  // overlay that softens parts of its shot's picture. A spot is an ellipse in the picture's own pixels (1080 x
  // 1920): a patch of mist (the tint, [r, g, b], at the fog's strength, 0.55, over a soft blur of 7 px) that
  // thins to nothing at its edge; with fog 0 it is only out of focus. A spot with a path ([[seconds into the
  // clip, x, y], ...]) follows a thing that moves in a clip. A band is a full-width strip from y down h px,
  // blurred (soft, 12 px) like a foreground out of focus and feathered at its top (feather, 30 per cent). All
  // sit inside the camera, so they stay on the same part of the picture.
  graphic('veil', (wrap, spec, ctx) => {
    const cam = camOf(wrap);
    const make = (box, mask, px) => {
      const el = h('div', { class: 'k-veil' });
      const blur = 'blur(' + px + 'px)';
      Object.assign(el.style, box, { backdropFilter: blur, webkitBackdropFilter: blur, maskImage: mask, webkitMaskImage: mask });
      cam.appendChild(el);
      return el;
    };
    const tint = (spec.tint || [198, 208, 200]).join(','), fog = spec.fog === undefined ? 0.55 : spec.fog;
    const movers = [];
    for (const s of spec.spots || []) {
      const x = s.path ? s.path[0][1] : s.x, y = s.path ? s.path[0][2] : s.y;
      const el = make({ left: (x - s.rx) + 'px', top: (y - s.ry) + 'px', width: 2 * s.rx + 'px', height: 2 * s.ry + 'px', background: 'rgba(' + tint + ',' + (s.fog === undefined ? fog : s.fog) + ')' }, 'radial-gradient(ellipse closest-side, #000 0%, #000 38%, rgba(0,0,0,0.6) 64%, rgba(0,0,0,0.18) 84%, transparent 100%)', s.blur || spec.blur || 7);
      if (s.path) movers.push({ el, s });
    }
    for (const b of spec.bands || []) make({ left: '-60px', top: b.y + 'px', width: '1200px', height: b.h + 'px' }, 'linear-gradient(to bottom, transparent 0%, #000 ' + (b.feather || 30) + '%)', spec.soft || 12);
    if (!movers.length) return null;
    const m = ctx.shot.media || {};
    return t => {
      const at = Math.max(0, t - ctx.shot.t0) * (m.rate || 1) + (m.offset || 0);  // seconds into the clip
      for (const { el, s } of movers) {
        const path = s.path;
        let i = 0;
        while (i + 2 < path.length && at >= path[i + 1][0]) i++;
        const a = path[i], b = path[i + 1], p = clamp((at - a[0]) / Math.max(0.001, b[0] - a[0]));
        el.style.left = (lerp(a[1], b[1], p) - s.rx).toFixed(1) + 'px';
        el.style.top = (lerp(a[2], b[2], p) - s.ry).toFixed(1) + 'px';
      }
    };
  });

  // stepsrow: {y, steps: [{text, at}]}: a row of numbered step chips (as tall as a label chip, 63 px), dim
  // until each lights on its `at` (`rows` is the older name of steps). y defaults to 380, the chip row.
  graphic('stepsrow', (wrap, spec) => {
    const box = h('div', { class: 'k-steprow' });
    box.style.top = (spec.y === undefined ? 380 : spec.y) + 'px';
    const rows = (spec.steps || spec.rows).map((r, i) => {
      const el = h('div', { class: 'k-step', 'data-role': 'label' }, [h('span', { class: 'n', text: String(i + 1) }), h('span', { text: r.text })]);
      box.appendChild(el);
      return { r, el };
    });
    wrap.appendChild(box);
    return t => rows.forEach(x => {
      const on = t >= x.r.at;
      x.el.className = 'k-step' + (on ? ' on' : '');
      x.el.style.transform = on ? 'scale(' + beat(t, x.r.at, 0.07).toFixed(4) + ')' : '';
    });
  });

  // reasons: {y, size, rows: [{text, at, hotAt}]}: the film's question as numbered answers at title size (150).
  // Every row is on the card from its first frame. A row with `at` shows a question mark until then; its answer
  // lands there in the accent colour. A row with `hotAt` is dim until its word is spoken.
  graphic('reasons', (wrap, spec) => {
    const box = h('div', { class: 'k-reasons' });
    box.style.top = (spec.y === undefined ? 380 : spec.y) + 'px';
    if (spec.size) box.style.fontSize = spec.size + 'px';
    const rows = spec.rows.map((r, i) => {
      const what = h('span', { class: 'what', text: r.text });
      const el = h('div', { class: 'k-reason', 'data-role': 'headline' }, [h('span', { class: 'n', text: String(i + 1) }), what]);
      box.appendChild(el);
      return { r, el, what };
    });
    wrap.appendChild(box);
    return t => rows.forEach(x => {
      const open = x.r.at !== undefined && t < x.r.at;
      const dim = x.r.hotAt !== undefined && t < x.r.hotAt;
      x.what.textContent = open ? '?' : x.r.text;
      x.el.className = 'k-reason' + (open ? ' open' : x.r.at !== undefined ? ' hot' : dim ? ' dim' : '');
      const land = x.r.at !== undefined && !open ? x.r.at : x.r.hotAt !== undefined && !dim ? x.r.hotAt : -9;
      x.el.style.transform = 'scale(' + beat(t, land, 0.14).toFixed(4) + ')';
    });
  });

  // answers: {y, part, ahead, standing, rows: [{who, what, at, hot, size}]}: answers at title size (150), each
  // under a chip that names whose answer it is (`label` and `text` are the older names of who and what). A row
  // lands on its `at` (left out: it stands from the first frame) with a small pop, in the accent when `hot`;
  // before then its answer stands dim (ahead "dim", the default), shows a question mark (ahead "?") or is not
  // drawn (ahead "hide"). size sets one answer's px. part: "who" draws the chips alone, "what" the answers
  // alone, each in the same place, so the chips can stand from the shot's first frame and the answers arrive
  // as a second overlay that carries "says". standing: no fade in (a card that carries over a cut).
  graphic('answers', (wrap, spec, ctx) => {
    const box = h('div', { class: 'k-answers' });
    box.style.top = (spec.y === undefined ? 380 : spec.y) + 'px';
    const ahead = spec.ahead || 'dim';
    const rows = spec.rows.map(r => {
      const text = r.what === undefined ? r.text : r.what;
      const what = h('div', { class: 'what', 'data-role': 'headline', text });
      if (r.size) what.style.fontSize = r.size + 'px';
      const who = h('div', { class: 'who', 'data-role': 'label', text: r.who === undefined ? r.label : r.who });
      if (spec.part === 'what') who.style.visibility = 'hidden';
      if (spec.part === 'who') what.style.visibility = 'hidden';
      const el = h('div', { class: 'k-answer' }, [who, what]);
      box.appendChild(el);
      return { r, el, what, text, at: r.at === undefined ? -NEVER : r.at };
    });
    wrap.appendChild(box);
    return t => {
      box.style.opacity = spec.standing ? '1' : remap(t, ctx.at, ctx.at + 0.15).toFixed(3);
      rows.forEach(x => {
        const on = t >= x.at;
        x.el.className = 'k-answer' + (on ? (x.r.hot ? ' hot' : '') : ' wait');
        const shown = on || ahead !== '?' ? x.text : '?';
        if (x.what.textContent !== shown) x.what.textContent = shown;
        if (spec.part !== 'who') x.what.style.visibility = on || ahead !== 'hide' ? '' : 'hidden';
        // The row pops from its left edge (x 72), so its peak is capped where its right edge meets the safe box
        // (x 1020): a wide row at 1.16 ran past the frame edge for three frames (WHERE THEY ARE RAR).
        const wide = x.what.offsetWidth;
        const peak = wide ? Math.min(1.16, Math.max(1, 948 / wide)) : 1.16;
        x.what.style.transform = 'scale(' + (on && x.at > -NEVER ? lerp(peak, 1, spring(t - x.at, 4, 0.6)) : 1).toFixed(4) + ')';
      });
    };
  });

  // words: {y, size, gap, standing, rows: [{script, hot, latin, gloss, at}]}: words of a language in their own
  // script, set as type (Nirmala UI, never drawn by a model), each with its Roman spelling and its meaning (a
  // chip). Every row is on the card dim from the card's first frame and lights on its `at`. hot is one whole
  // word of the script line, or one part of a compound written without a space, shown in the accent; Roman
  // letters in [brackets] are shown in the accent too. size is the script's px (118; the Roman line and the
  // gloss follow it), gap the px between rows (34). standing: every row is lit throughout.
  const scriptLine = (text, hot) => h('div', { class: 'script', 'data-role': 'body' }, text.split(' ').flatMap((w, i, all) => {
    const tail = i < all.length - 1 ? ' ' : '';
    const cut = hot && w !== hot ? w.indexOf(hot) : -1;
    if (cut < 0) return [h('span', { class: w === hot ? 'hot' : '', text: w + tail })];
    return [h('span', { text: w.slice(0, cut) }), h('span', { class: 'hot', text: hot }), h('span', { text: w.slice(cut + hot.length) + tail })].filter(el => el.textContent);
  }));
  const pieces = text => text.split(/(\[[^\]]+\])/).filter(Boolean).map(p => (p.startsWith('[') ? h('span', { class: 'hot', text: p.slice(1, -1) }) : h('span', { text: p })));
  graphic('words', (wrap, spec, ctx) => {
    const box = h('div', { class: 'k-words' });
    box.style.top = (spec.y === undefined ? 380 : spec.y) + 'px';
    if (spec.gap !== undefined) box.style.gap = spec.gap + 'px';
    const size = spec.size || 118;
    const rows = spec.rows.map(r => {
      const latin = h('span', { class: 'latin', 'data-role': 'body' }, pieces(r.latin));
      const gloss = r.gloss ? h('span', { class: 'gloss', 'data-role': 'label', text: r.gloss }) : null;
      const script = scriptLine(r.script, r.hot);
      script.style.fontSize = size + 'px';
      latin.style.fontSize = Math.round(size * 0.5) + 'px';
      if (gloss) gloss.style.fontSize = Math.max(38, Math.round(size * 0.3)) + 'px';
      const el = h('div', { class: 'k-word' }, [script, h('div', { class: 'line' }, [latin, gloss])]);
      box.appendChild(el);
      return { r, el };
    });
    wrap.appendChild(box);
    return t => rows.forEach(x => {
      const at = x.r.at === undefined ? ctx.at : x.r.at;
      const lit = !!spec.standing || t >= at;
      x.el.className = 'k-word' + (lit ? ' on' : '');
      x.el.style.opacity = (lit ? 1 : 0.45 * remap(t, ctx.at, ctx.at + 0.25)).toFixed(3);
      const k = lit && !spec.standing ? Math.max(0, 1 - spring(t - at, 3.4, 0.6)) : 0;
      x.el.style.transform = 'scale(' + (1 + 0.05 * k).toFixed(4) + ')';
    });
  });

  // document: {y, book, aAt, script, latin, z, zoomFrom, standing, redrawn, senses: [{n, text, at, hotAt}],
  //            rows: [{script, latin, ours, gloss, extra, big, at}]}
  // A document (a dictionary entry, a register line) redrawn on a paper card: the book and its year, the
  // headword (script and latin, both optional), its numbered senses and sub-entries that arrive at their cues.
  // Senses stand from their `at` (default: with the card); a sense with hotAt and every row can carry the
  // marker, and the newest of them does. A row's `ours` (and `extra`, a note at the row's right end) is our
  // own, shown as a dark chip so it cannot be taken for the document's words; `big` sets a row a size larger.
  // aAt: the year that ends the book line (after its last ", ") appears on its spoken word, not with the card.
  // z: the size of the headword and its senses (1); zoomFrom: they settle from that size over 0.45 s.
  // redrawn: the line under the card that says the card is ours ("Redrawn by us, not the original page");
  // false leaves it out. The card belongs on a plain plate drawn by the stage (ground), never on a picture.
  graphic('document', (wrap, spec, ctx) => {
    const card = h('div', { class: 'k-doc' });
    const hold = h('div', { class: 'k-doc-hold' }, [card]);
    hold.style.top = (spec.y === undefined ? 380 : spec.y) + 'px';
    const book = spec.book || '';
    const cut = spec.aAt === undefined ? -1 : book.lastIndexOf(', ');
    const year = cut < 0 ? null : h('span', { text: book.slice(cut) });
    if (book) card.appendChild(h('div', { class: 'book', 'data-role': 'label' }, [h('span', { text: cut < 0 ? book : book.slice(0, cut) }), year]));
    if (spec.script || spec.latin) card.appendChild(h('div', { class: 'head' }, [spec.script ? h('span', { class: 'script', 'data-role': 'body', text: spec.script }) : null, spec.latin ? h('span', { class: 'latin', 'data-role': 'body', text: spec.latin }) : null]));
    const senses = (spec.senses || []).map(s => {
      const el = h('div', { class: 'sense', 'data-role': 'body' }, [h('b', { text: s.n + '.' }), h('span', { text: s.text })]);
      card.appendChild(el);
      return { s, el };
    });
    const rows = (spec.rows || []).map(r => {
      const top = h('div', { class: 'top' }, [r.script ? h('span', { class: 'script', 'data-role': 'body', text: r.script }) : null, r.latin ? h('span', { class: 'latin', 'data-role': 'body', text: r.latin }) : null]);
      const kids = [];
      if (r.ours) kids.push(h('span', { class: 'ours', 'data-role': 'label', text: r.ours }), h('span', { class: 'is', text: '=' }));
      kids.push(h('span', { class: 'gloss', 'data-role': 'body', text: r.gloss || '' }));
      const el = h('div', { class: 'row' + (r.big ? ' big' : '') }, [top, h('div', { class: 'bottom' }, kids)]);
      if (r.extra) el.appendChild(h('span', { class: 'ours extra', 'data-role': 'label', text: r.extra }));
      card.appendChild(el);
      return { r, el };
    });
    const note = spec.redrawn === false ? null : h('div', { class: 'k-doc-note', 'data-role': 'source', text: spec.redrawn || 'Redrawn by us, not the original page' });
    if (note) hold.appendChild(note);
    wrap.appendChild(hold);
    const marks = senses.filter(x => x.s.hotAt !== undefined).map(x => ({ at: x.s.hotAt, x, cls: 'sense' }))
      .concat(rows.map(x => ({ at: x.r.at === undefined ? ctx.at : x.r.at, x, cls: 'row' + (x.r.big ? ' big' : '') })));
    const zTo = spec.z || 1;
    return t => {
      // The card is on the plate from the shot's first frame (no card opens on an empty plate); it only settles.
      if (!spec.standing) hold.style.transform = 'translateY(' + ((1 - spring(t - ctx.at, 3.2, 0.62)) * 28).toFixed(2) + 'px)';
      const z = spec.zoomFrom === undefined ? zTo : lerp(spec.zoomFrom, zTo, ease.outCubic(remap(t, ctx.at, ctx.at + 0.45)));
      card.style.setProperty('--z', z.toFixed(4));
      if (year) year.style.opacity = t >= spec.aAt ? '1' : '0';
      senses.forEach(x => {
        const at = x.s.at === undefined ? ctx.at : x.s.at;
        x.el.style.opacity = remap(t, at, at + 0.2).toFixed(3);
      });
      rows.forEach(x => {
        const at = x.r.at === undefined ? ctx.at : x.r.at;
        x.el.style.opacity = remap(t, at, at + 0.2).toFixed(3);
        x.el.style.display = t < at ? 'none' : 'block';
      });
      const live = marks.filter(m => t >= m.at);
      const newest = live.length ? live.reduce((a, b) => (b.at >= a.at ? b : a)) : null;
      marks.forEach(m => { m.x.el.className = m.cls + (m === newest ? ' hot' : ''); });
    };
  });

  // years: {y, from, to, until, size, prefix, marks: [{at, label}]}: a rail of years (936 px) with a large
  // counter (size, 170) above its dot. The dot runs from the overlay's `at` plus 0.3 s to `until`, and the
  // counter shows its last value only at `until` (by the clock), so the number is never up before its word. A
  // prefix (ABOUT) stands small to the left of the figure from the first frame: the source's hedge. A mark
  // label at the rail's end is set inward, so it stays inside the safe box.
  graphic('years', (wrap, spec, ctx) => {
    const size = spec.size || 170, span = spec.to - spec.from;
    const box = h('div', { class: 'k-years' });
    box.style.top = (spec.y === undefined ? 352 : spec.y) + 'px';
    const num = h('div', { class: 'num', 'data-role': 'number' });
    const val = h('span', { text: String(spec.from) });
    if (spec.prefix) num.appendChild(h('span', { class: 'pre', text: spec.prefix }));
    num.appendChild(val);
    num.style.fontSize = size + 'px';
    const railY = size + 12;
    const line = h('div', { class: 'line' }), done = h('div', { class: 'done' }), dot = h('div', { class: 'dot' });
    for (const el of [line, done, dot]) el.style.top = railY + 'px';
    box.append(line, done, dot, num);
    for (const m of spec.marks || []) {
      const tick = h('div', { class: 'tick', text: m.label, 'data-role': 'label' });
      tick.style.top = (railY + 26) + 'px';
      if (m.at === spec.to) tick.style.right = '0';
      else tick.style.left = (((m.at - spec.from) / span) * 936).toFixed(1) + 'px';
      box.appendChild(tick);
    }
    wrap.appendChild(box);
    const t1 = spec.until === undefined ? (ctx.out === null ? ctx.shot.t1 : ctx.out) - 0.4 : spec.until;
    // The counter's reach either side of the dot, measured on the first shown frame (a hidden scene has no
    // width): the wider of the two end values, the prefix and its 14 px gap on the left, at the landing
    // pop's 1.12. The box starts at x 72, so the safe box (60 to 1020) is -12 to 948 inside it.
    let reach = null;
    const measure = () => {
      let w = 0;
      for (const v of [spec.from, spec.to]) { val.textContent = String(v); w = Math.max(w, num.offsetWidth); }
      const pre = num.querySelector('.pre');
      reach = { w, left: (w / 2 + (pre ? pre.offsetWidth + 14 : 0)) * 1.12, right: (w / 2) * 1.12 };
    };
    return t => {
      if (!reach || !reach.w) measure();
      const p = ease.inOutCubic(remap(t, ctx.at + 0.3, t1));
      const x = p * 936;
      done.style.transform = 'scaleX(' + p.toFixed(4) + ')';
      dot.style.left = x.toFixed(1) + 'px';
      num.style.left = clamp(x, reach.left - 12, 948 - reach.right).toFixed(1) + 'px';
      const landed = t >= t1 - 0.0005;
      val.textContent = String(landed ? spec.to : Math.min(Math.round(spec.from + span * p), spec.to - 1));
      num.style.transform = 'translateX(-50%) scale(' + (landed ? 1 + 0.12 * Math.max(0, 1 - spring(t - t1, 3.4, 0.55)) : 1).toFixed(4) + ')';
      box.style.opacity = remap(t, ctx.at, ctx.at + 0.25).toFixed(3);
    };
  });
})();

'use strict';
// Kit: builds a whole video on the Stage from data (timeline.json): shots with media, a camera and
// overlays, word-lit captions, a progress bar and an end card. A build adds its own graphics with
// Kit.graphic(name, build) in graphics.js. Times in the data are absolute seconds.
const Kit = (() => {
  const { h, img, clip, scene, layer, video, lerp, remap, clamp, ease, spring, noise, OVERLAP } = Stage;
  const custom = {};
  let base = '/';
  let tagText = '';
  let pageList = [];
  const graphic = (name, fn) => { custom[name] = fn; };

  // ---- motion helpers
  const pop = (el, t, at, o = {}) => {
    const s = spring(t - at, o.f || 3.4, o.z || 0.52);
    el.style.opacity = t < at ? '0' : Math.min(1, (t - at) / 0.07).toFixed(3);
    el.style.transform = 'translateY(' + ((1 - s) * (o.rise === undefined ? 44 : o.rise)).toFixed(2) + 'px) scale(' + lerp(o.from || 0.84, 1, s).toFixed(4) + ')';
  };
  const slide = (el, t, at, o = {}) => {
    const p = ease.outExpo(remap(t, at, at + (o.d || 0.4)));
    el.style.opacity = t < at ? '0' : Math.min(1, (t - at) / 0.1).toFixed(3);
    el.style.transform = 'translateX(' + ((1 - p) * (o.dx === undefined ? -40 : o.dx)).toFixed(2) + 'px)';
  };
  const leave = (t, out, d = 0.16) => (out === null || t < out - d ? 1 : 1 - remap(t, out - d, out));

  // ---- text helpers
  const bare = w => w.replace(/[^A-Za-z0-9']/g, '').toUpperCase();
  const isHot = (w, hot) => !!hot && hot.some(x => bare(x) === bare(w));
  // "*word*" or "*several words*" lights them in the accent colour.
  const mark = (text, hot) => {
    const parts = text.split(" ").filter(Boolean);
    let lit = false;
    return parts.map((raw, i) => {
      let w = raw, on = lit;
      if (w.startsWith("*")) { on = true; lit = true; w = w.slice(1); }
      // The closing star may be followed by punctuation ("*about*, from now").
      const close = w.match(/^(.*)\*([,.;:!?"')\]]*)$/);
      if (close) { lit = false; w = close[1] + close[2]; }
      return h("span", { class: "word" + (on || isHot(w, hot) ? " hot" : ""), text: w + (i < parts.length - 1 ? " " : "") });
    });
  };
  const meas = document.createElement('canvas').getContext('2d');
  // The largest font size (px) at which every line fits the width.
  const fitPx = (lines, width, max, min, weight, family, spacing = 0) => {
    meas.font = weight + ' 100px "' + family + '"';
    let px = max;
    for (const line of lines) {
      const w100 = meas.measureText(line.toUpperCase()).width || 1;
      px = Math.min(px, (100 * (width - spacing * (line.length - 1))) / w100);
    }
    return Math.max(min, Math.floor(px));
  };
  const svgNode = (tag, attrs) => {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  };

  // ---- overlays: each returns update(t)
  const headline = (wrap, spec, ctx, o) => {
    const spans = [];
    const el = h('div', { class: 'k-head', 'data-role': o.role }, spec.lines.map(line => {
      const ws = mark(line, spec.hot);
      spans.push(...ws);
      return h('div', {}, ws);
    }));
    el.style.top = (spec.y === undefined ? o.y : spec.y) + 'px';
    el.style.fontSize = (spec.size || o.max) + 'px';
    const plain = spec.lines.map(line => line.split('*').join(''));
    Stage.afterFonts(() => { el.style.fontSize = fitPx(plain, spec.width || o.width || 936, spec.size || o.max, o.min, '900', 'Barlow Condensed', -1) + 'px'; });
    wrap.appendChild(el);
    const step = spec.step || 0.075;
    if (o.standing) {
      // The hook stands complete on its first frame; its entrance only settles it. standing: it stands settled
      // from the shot's first frame (a shot that continues the hook's shot after a cut-in).
      const at = spec.standing ? ctx.at - 9 : ctx.at;
      return t => {
        const p = ease.outExpo(remap(t, at, at + 0.55));
        el.style.transformOrigin = '0 50%';
        el.style.transform = 'scale(' + lerp(1.07, 1, p).toFixed(4) + ')';
      };
    }
    // standing: the headline is complete on the shot's first frame (a shot that continues another).
    const from = spec.standing ? ctx.at - 9 : ctx.at;
    return t => spans.forEach((sp, i) => pop(sp, t, from + i * step));
  };
  const TYPES = {
    hook: (wrap, spec, ctx) => headline(wrap, spec, ctx, { role: 'hook', y: 540, max: 190, min: 96, standing: true, width: 874 }),
    title: (wrap, spec, ctx) => headline(wrap, spec, ctx, { role: 'headline', y: 560, max: 136, min: 80 }),
    label: (wrap, spec, ctx) => {
      const el = h('div', { class: 'k-label' + (spec.tone === 'accent' ? ' accent' : ''), text: spec.text, 'data-role': 'label' });
      el.style.top = (spec.y === undefined ? 440 : spec.y) + 'px';
      if (spec.x !== undefined) el.style.left = spec.x + 'px';
      wrap.appendChild(el);
      return t => (spec.standing ? null : slide(el, t, ctx.at));
    },
    number: (wrap, spec, ctx) => {
      const num = h('span', { text: '' });
      const size = spec.size || 300;
      // align "center": the figure and its second line are centred on the frame. x: their left edge (not read
      // when centred: the two would centre the figure between x and the right edge, not on the frame).
      const center = spec.align === 'center';
      const left = center || typeof spec.x !== 'number' || !Number.isFinite(spec.x) ? undefined : spec.x;
      const el = h('div', { class: 'k-num' + (spec.tone === 'accent' ? ' accent' : '') + (center ? ' center' : ''), 'data-role': 'number' }, [
        spec.prefix ? h('span', { class: 'pre', text: spec.prefix }) : null, num,
        spec.unit ? h('span', { class: 'unit', text: spec.unit }) : null,
      ]);
      const y = spec.y === undefined ? 600 : spec.y;
      el.style.top = y + 'px';
      if (left !== undefined) el.style.left = left + 'px';
      // the room the figure is fitted to: from its left edge (70 by the kit's CSS) to 24 px inside the safe box
      const room = 996 - (left === undefined ? 70 : left);
      el.style.fontSize = size + 'px';
      wrap.appendChild(el);
      const dec = spec.decimals || 0, from = spec.from || 0, to = spec.value;
      const fmt = v => v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec, useGrouping: spec.group !== false });
      const full = (spec.prefix || '') + fmt(to);
      Stage.afterFonts(() => {
        meas.font = '900 100px "Barlow Condensed"';
        const w100 = meas.measureText(full).width + (spec.unit ? meas.measureText(' ' + spec.unit).width * 0.5 : 0);
        el.style.fontSize = Math.min(size, Math.floor((100 * room) / w100)) + 'px';
      });
      let subs = [];
      if (spec.sub) {
        subs = mark(spec.sub, spec.hot);
        const sub = h('div', { class: 'k-sub' + (center ? ' center' : ''), 'data-role': 'body' }, subs);
        sub.style.top = (spec.subY === undefined ? y + size * 0.9 + 26 : spec.subY) + 'px';
        if (left !== undefined) sub.style.left = (left + 2) + 'px';
        wrap.appendChild(sub);
      }
      const dur = spec.count === undefined ? 1.1 : spec.count;
      // standing: the figure and its second line stand landed from the shot's first frame (a count that landed on
      // the shot before and stands on after the cut); count and landAt are then not read.
      const at = spec.standing ? ctx.at - 9 : ctx.at;
      // landAt: the count ends on this time (the spoken number). The figure stands at its start value from the
      // overlay's first frame and the final value is never on screen before its word.
      const land = spec.standing ? undefined : spec.landAt;
      const step = dec ? Math.pow(10, -dec) : 1;
      return t => {
        const p = !dur ? 1 : land === undefined ? ease.outExpo(remap(t, at + 0.05, at + 0.05 + dur)) : ease.inOutCubic(remap(t, land - dur, land));
        const landed = land === undefined ? p >= 0.999 : t >= land - 0.0005;  // by the clock when it lands on a word
        let v = landed ? to : from + (to - from) * p;
        if (land !== undefined && !landed && to > from) v = Math.min(dec ? v : Math.round(v), to - step);
        num.textContent = fmt(dec ? v : Math.round(v));
        pop(el, t, land === undefined ? at : Math.max(ctx.at, land - dur - 0.05), { f: 2.8, z: 0.62, rise: 30 });
        subs.forEach((sp, i) => pop(sp, t, at + (spec.subAt === undefined ? 0.5 : spec.subAt) + i * 0.06, { rise: 26 }));
      };
    },
    lower: (wrap, spec, ctx) => {
      const rule = h('div', { class: 'rule' });
      const spans = mark(spec.text, spec.hot);
      const el = h('div', { class: 'k-lower', 'data-role': 'body' }, [rule, ...spans]);
      el.style.top = (spec.y === undefined ? 870 : spec.y) + 'px';
      if (spec.size) el.style.fontSize = spec.size + 'px';
      wrap.appendChild(el);
      // standing: the lower third is complete on the shot's first frame (a line that stands across a cut).
      const at = spec.standing ? ctx.at - 9 : ctx.at;
      return t => {
        rule.style.transform = 'scaleY(' + ease.outExpo(remap(t, at, at + 0.3)).toFixed(4) + ')';
        spans.forEach((sp, i) => pop(sp, t, at + 0.08 + i * 0.05, { rise: 26 }));
      };
    },
    source: (wrap, spec, ctx) => {
      const el = h('div', { class: 'k-source', text: spec.text, 'data-role': 'source' });
      if (spec.y !== undefined) el.style.top = spec.y + 'px';
      if (spec.align === 'center') el.classList.add('center');
      wrap.appendChild(el);
      return t => { el.style.opacity = spec.standing ? '1' : remap(t, ctx.at, ctx.at + 0.3).toFixed(3); };
    },
    chapter: (wrap, spec, ctx) => {
      const el = h('div', { class: 'k-chapter', 'data-role': 'label' }, [h('b', { text: spec.n + '/' + spec.of }), h('span', { text: spec.text })]);
      wrap.appendChild(el);
      return t => slide(el, t, ctx.at, { dx: -60 });
    },
    stamp: (wrap, spec, ctx) => {
      const hold = h('div', { style: { position: 'absolute', left: (spec.x === undefined ? 540 : spec.x) + 'px', top: (spec.y === undefined ? 760 : spec.y) + 'px' } });
      // who: the speaker or the hedge, set small inside the stamp (RESEARCHERS SAY over STRONGER WITH AGE)
      const el = h('div', { class: 'k-stamp' + (spec.tone ? ' ' + spec.tone : ''), 'data-role': 'stamp' }, (spec.who ? [h('span', { class: 'who', text: spec.who })] : []).concat([h('span', { text: spec.text })]));
      if (spec.size) el.style.fontSize = spec.size + 'px';
      hold.appendChild(el);
      wrap.appendChild(hold);
      const rot = spec.rot === undefined ? -7 : spec.rot;
      // standing: the stamp stands landed from the shot's first frame, with no slam and no shake (it landed on
      // the shot before and still stands after the cut).
      const at = spec.standing ? ctx.at - 9 : ctx.at;
      return t => {
        const p = ease.outExpo(remap(t, at, at + 0.24));
        const settle = 1 - remap(t, at + 0.2, at + 0.55);
        const jx = noise(11, (t - at) * 38) * 9 * settle, jy = noise(17, (t - at) * 38) * 9 * settle;
        el.style.opacity = t < at ? '0' : Math.min(1, (t - at) / 0.05).toFixed(3);
        el.style.transform = 'translate(-50%,-50%) translate(' + jx.toFixed(2) + 'px,' + jy.toFixed(2) + 'px) rotate(' + rot + 'deg) scale(' + lerp(2.6, 1, p).toFixed(4) + ')';
      };
    },
    callout: (wrap, spec, ctx) => {
      const dx = spec.dx === undefined ? 70 : spec.dx, dy = spec.dy === undefined ? -130 : spec.dy;
      const lx = spec.x + dx, ly = spec.y + dy;
      const svg = svgNode('svg', { width: 1080, height: 1920, style: 'position:absolute;left:0;top:0' });
      const len = Math.hypot(dx, dy);
      const dark = svgNode('line', { x1: spec.x, y1: spec.y, x2: lx, y2: ly, stroke: '#0b0b0b', 'stroke-width': 10, 'stroke-linecap': 'round', 'stroke-dasharray': len, 'stroke-dashoffset': len });
      const line = svgNode('line', { x1: spec.x, y1: spec.y, x2: lx, y2: ly, stroke: '#fff', 'stroke-width': 5, 'stroke-linecap': 'round', 'stroke-dasharray': len, 'stroke-dashoffset': len });
      svg.append(dark, line);
      const pin = h('div', { class: 'k-pin' });
      pin.style.left = spec.x + 'px';
      pin.style.top = spec.y + 'px';
      const hold = h('div', { style: { position: 'absolute', left: lx + 'px', top: ly + 'px', transform: 'translate(' + (dx >= 0 ? '-12%' : '-88%') + ',' + (dy <= 0 ? '-100%' : '0') + ')' } });
      const box = h('div', { class: 'k-call', 'data-role': 'label' }, mark(spec.text, spec.hot));
      hold.appendChild(box);
      // hang: where the box sits from the end of its leader. By default its top left corner is at the end
      // (the box runs right and down). "left" puts its right edge there, "up" its bottom edge, "left-up" both.
      if (spec.hang) {
        Stage.afterFonts(() => {
          const plain = spec.text.split('*').join('');
          meas.font = '700 44px "Barlow Condensed"';
          const wide = meas.measureText(plain.toUpperCase()).width + 1.5 * plain.length + 44;
          if (spec.hang.includes('left')) hold.style.left = (lx - wide).toFixed(1) + 'px';
          if (spec.hang.includes('up')) hold.style.top = (ly - 71) + 'px';
        });
      }
      wrap.append(svg, pin, hold);
      // standing: the callout is complete on the shot's first frame (a shot that continues another).
      const at = spec.standing ? ctx.at - 9 : ctx.at;
      return t => {
        pop(pin, t, at, { from: 0.2, rise: 0, f: 4.2, z: 0.45 });
        const p = ease.outCubic(remap(t, at + 0.1, at + 0.4));
        const off = (len * (1 - p)).toFixed(2);
        dark.setAttribute('stroke-dashoffset', off);
        line.setAttribute('stroke-dashoffset', off);
        svg.style.opacity = t < at + 0.1 ? '0' : '1';
        pop(box, t, at + 0.32, { rise: 18 });
      };
    },
    compare: (wrap, spec, ctx) => {
      const max = spec.max || Math.max(...spec.rows.map(r => r.value));
      const dec = spec.decimals || 0;
      const fmt = v => v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + (spec.unit ? ' ' + spec.unit : '');
      const rows = spec.rows.map(r => {
        const val = h('span', { text: '' });
        const fill = h('div', { class: 'fill' });
        const name = h('div', { class: 'name', 'data-role': 'body' }, [h('span', { text: r.label }), val]);
        // size: the row's type size (the value is set a quarter larger); tick: a mark at the start of a
        // bar too short to see.
        if (spec.size) { name.style.fontSize = spec.size + 'px'; val.style.fontSize = Math.round(spec.size * 1.2) + 'px'; }
        const el = h('div', { class: 'k-bar' + (r.hot ? ' hot' : '') }, [
          name,
          h('div', { class: 'track' }, [fill, r.tick ? h('div', { class: 'tick' }) : null]),
        ]);
        return { r, el, val, fill };
      });
      const box = h('div', { class: 'k-bars' }, rows.map(x => x.el));
      box.style.top = (spec.y === undefined ? 620 : spec.y) + 'px';
      wrap.appendChild(box);
      const step = spec.step === undefined ? 0.4 : spec.step;
      return t => rows.forEach((x, i) => {
        // a row's at is absolute seconds: build.py resolves every cue in an overlay's lists
        const at = x.r.at === undefined ? ctx.at + i * step : x.r.at;
        // wait: the row stands from the start with a question mark and fills in at its own time.
        const shown = x.r.wait ? ctx.at : at;
        const p = ease.outExpo(remap(t, at + 0.05, at + 0.95));
        x.fill.style.transform = 'scaleX(' + ((p * x.r.value) / max).toFixed(4) + ')';
        // fixed: the row shows its display text from the start (a value too small to count up).
        x.val.textContent = x.r.wait && t < at ? '?' : x.r.display && (p >= 0.999 || x.r.fixed) ? x.r.display : fmt(dec ? x.r.value * p : Math.round(x.r.value * p));
        slide(x.el, t, shown, { dx: -30 });
      });
    },
    rail: (wrap, spec, ctx) => {
      const year = h('div', { class: 'year', 'data-role': 'number', text: String(spec.from) });
      const done = h('div', { class: 'done' });
      const dot = h('div', { class: 'dot' });
      const el = h('div', { class: 'k-rail' }, [h('div', { class: 'line' }), done, dot, year]);
      const span = spec.to - spec.from;
      for (const m of spec.marks || []) {
        const tick = h('div', { class: 'tick', text: m.label || String(m.at), 'data-role': 'label' });
        tick.style.left = (((m.at - spec.from) / span) * 936).toFixed(1) + 'px';
        // a label at either end of the rail is set inward, so it stays inside the safe box
        if (m.at === spec.from) tick.style.transform = 'none';
        else if (m.at === spec.to) tick.style.transform = 'translateX(-100%)';
        el.appendChild(tick);
      }
      el.style.top = (spec.y === undefined ? 560 : spec.y) + 'px';
      wrap.appendChild(el);
      const t1 = spec.until === undefined ? (ctx.out === null ? ctx.shot.t1 : ctx.out) - 0.4 : spec.until;
      return t => {
        const p = ease.inOutCubic(remap(t, ctx.at + 0.3, t1));
        const x = p * 936;
        done.style.transform = 'scaleX(' + p.toFixed(4) + ')';
        dot.style.left = x.toFixed(1) + 'px';
        year.style.left = clamp(x, 110, 826).toFixed(1) + 'px';
        // the last value shows only when the count ends, so a number is never on screen before its word
        // (by the clock, not by the eased value: an eased count reaches its end a quarter second early)
        const landed = t >= t1 - 0.0005;
        const now = Math.round(spec.from + span * p);
        year.textContent = String(landed ? spec.to : span > 0 ? Math.min(now, spec.to - 1) : now);
        el.style.opacity = remap(t, ctx.at, ctx.at + 0.25).toFixed(3);
      };
    },
    quote: (wrap, spec, ctx) => {
      const spans = [];
      const el = h('div', { class: 'k-quote', 'data-role': 'headline' }, spec.lines.map(line => {
        const ws = mark(line, spec.hot);
        spans.push(...ws);
        return h('div', {}, ws);
      }));
      el.style.top = (spec.y === undefined ? 640 : spec.y) + 'px';
      if (spec.size) el.style.fontSize = spec.size + 'px';
      wrap.appendChild(el);
      return t => spans.forEach((sp, i) => pop(sp, t, ctx.at + i * (spec.step || 0.09)));
    },
    end: (wrap, spec, ctx) => {
      // "*word*" lights words in the big lines and in the send line; a line break in `line` is kept (the CSS).
      // Marked text is set one block per line: a word is an inline block, so a break inside one would stack it.
      const set = (attrs, given) => {
        const text = String(given);  // a line given as a number (a year) is still a line
        if (!text.includes('*')) return h('div', Object.assign({}, attrs, { text }));
        if (!text.includes('\n')) return h('div', attrs, mark(text, spec.hot));
        // A marked phrase may run across the break: it is closed at the end of its row and opened again on the
        // next. Whether a row leaves the phrase open is told by mark()'s own rule (a word that starts with a
        // star opens, a word that ends with a star and any punctuation closes), so a star inside a word is
        // only a star. An empty row keeps its height, as it does in an unmarked line.
        const leaves = (row, lit) => {
          for (const raw of row.split(' ').filter(Boolean)) {
            const w = raw.startsWith('*') ? raw.slice(1) : raw;
            if (raw.startsWith('*')) lit = true;
            if (/^(.*)\*([,.;:!?"')\]]*)$/.test(w)) lit = false;
          }
          return lit;
        };
        let lit = false;
        const rows = text.split('\n').map(given => {
          const row = given.trim();
          if (!row) return null;
          const opened = lit && !row.startsWith('*');
          lit = leaves(row, lit);
          return (opened ? '*' : '') + row + (lit ? '*' : '');
        });
        return h('div', attrs, rows.map(row => h('div', {}, row === null ? [document.createTextNode(String.fromCharCode(160))] : mark(row, spec.hot))));
      };
      const big = h('div', { class: 'big', 'data-role': 'endcard' }, (spec.big || ['FOLLOW', 'FOR MORE']).map((line, i) => set({ class: i === 0 ? 'hot' : '' }, line)));
      const kids = [big];
      // chip: a small dark chip under the big words (AS OF 2026 under a claim about today)
      if (spec.chip) kids.push(h('div', { class: 'chip', 'data-role': 'label', text: spec.chip }));
      if (spec.handle) kids.push(h('div', { class: 'handle', 'data-role': 'endcard', text: '@' + spec.handle }));
      if (spec.line) kids.push(set({ class: 'line', 'data-role': 'endcard' }, spec.line));
      const el = h('div', { class: 'k-end' }, kids);
      // lift: raise the stack by this many px (it is centred, so the bottom padding grows by twice that)
      if (spec.lift) el.style.paddingBottom = (300 + 2 * spec.lift) + 'px';
      wrap.appendChild(el);
      return t => kids.forEach((k, i) => pop(k, t, ctx.at + 0.1 + i * 0.14, { rise: 60 }));
    },
  };
  const overlay = (parent, spec, shot) => {
    const make = TYPES[spec.type] || custom[spec.type];
    if (!make) throw new Error('unknown overlay type: ' + spec.type + ' in shot ' + shot.id);
    const wrap = h('div', { class: 'k-over' });
    parent.appendChild(wrap);
    const at = spec.at === undefined ? shot.t0 : spec.at;
    const out = spec.out === undefined || spec.out === null ? null : spec.out;
    const inner = make(wrap, spec, { at, out, shot }) || (() => {});
    return t => {
      const on = t >= at - 0.0005 && (out === null || t < out);
      wrap.style.display = on ? 'block' : 'none';
      if (!on) return;
      wrap.style.opacity = out === null ? '' : leave(t, out).toFixed(3);
      inner(t);
    };
  };

  // ---- a shot: media under a camera, then shades, then overlays
  const shot = s => scene({ id: s.id, t0: s.t0, t1: s.t1, tin: s.tin || { kind: 'cut', d: 0 }, build(el) {
    el.classList.add('k-shot');
    const cam = h('div', { class: 'cam' });
    const m = s.media || { kind: 'none' };
    let media = null;
    if (m.kind === 'clip') media = clip(base + m.dir, m.frames, m.fps || 24);
    else if (m.kind === 'still') media = img(base + m.src);
    if (media) {
      // "bright" replaces the brightness of the shot's grade (blur 0.55, dim 0.5, soft 0.78, lift 1.24, past 1.08,
      // no grade 1): a plate under a device as bright as the pictures around it, a dark picture lifted to its
      // neighbours without touching its frames. A bright that is not a number above 0 keeps the grade's own.
      const bright = typeof s.bright === 'number' && Number.isFinite(s.bright) && s.bright > 0;
      const lit = d => (bright ? s.bright : d);
      if (s.grade === 'blur') media.style.filter = 'blur(22px) brightness(' + lit(0.55) + ') saturate(1.1)';
      else if (s.grade === 'dim') media.style.filter = 'brightness(' + lit(0.5) + ')';
      else if (s.grade === 'soft') media.style.filter = 'brightness(' + lit(0.78) + ')';
      else if (s.grade === 'lift') media.style.filter = 'brightness(' + lit(1.24) + ') contrast(0.95)';
      else if (s.grade === 'past') media.style.filter = 'saturate(0.38) contrast(1.06) brightness(' + lit(1.08) + ')';
      else if (bright) media.style.filter = 'brightness(' + s.bright + ')';
      if (s.flip) media.style.transform = 'scaleX(-1)';
      cam.appendChild(media);
    }
    el.appendChild(cam);
    // A drawn picture (media kind none) may return an update function, so it can change with time. It starts
    // on the shot's first shown frame, half an overlapping transition before t0, so it slides in drawn.
    if (m.kind === 'none' && m.graphic && !custom[m.graphic]) throw new Error('unknown graphic: ' + m.graphic + ' in shot ' + s.id);
    const tinD = s.tin && OVERLAP[s.tin.kind] && Number.isFinite(s.tin.d) ? s.tin.d / 2 : 0;
    const drawn = m.kind === 'none' && m.graphic ? custom[m.graphic](cam, m, { at: s.t0 - tinD, out: null, shot: s }) : null;
    // Every generated picture carries the film's tag (the batch's disclosure chip; an empty tag draws none)
    // unless the shot turns it off.
    // (a drawn shot that shows a generated picture inside its drawing asks for the tag with "tag": true)
    // The top shade lies over the picture and under the tag, so the tag keeps its full strength.
    if (s.shade) el.appendChild(h('div', { class: 'k-top' }));
    if (tagText && (media || s.tag === true) && s.tag !== false) el.appendChild(h('div', { class: 'k-tag', 'data-role': 'source', text: tagText }));
    if (s.vignette !== false) el.appendChild(h('div', { class: 'k-vig' }));
    if (s.floor !== false) el.appendChild(h('div', { class: 'k-floor' }));
    const ups = (s.over || []).map(o => overlay(el, o, s));
    const still = m.kind === 'still';
    const c = Object.assign({ from: still ? 1.06 : 1.0, to: still ? 1.16 : 1.05, x: [0, 0], y: [0, 0], shake: still ? 4 : 0, pad: s.grade === 'blur' ? 1.12 : 1 }, s.cam || {});
    let seed = 0;
    // order counts, so s01 and s10 shake differently; still a pure function of the id
    for (const ch of s.id) seed = (seed * 31 + ch.charCodeAt(0)) % 9973;
    const dur = s.t1 - s.t0;
    // tin {kind: "punch", picture: true}: the punch scales the picture layer alone, so type, chips and the
    // tag stand still (runtime.js leaves such a punch to the kit). from (1.12) and d as the shot's tin punch.
    const tin = s.tin || {};
    const punch = tin.kind === 'punch' && tin.picture ? lt => lerp(tin.from || 1.12, 1, ease.outExpo(remap(lt, 0, tin.d || 0))) : null;
    return (lt, t) => {
      const p = clamp(lt / dur);
      const k = c.ease === 'out' ? ease.outCubic(p) : c.ease === 'inout' ? ease.inOutCubic(p) : p;
      const z = lerp(c.from, c.to, k) * c.pad * (punch ? punch(lt) : 1);
      // The shake runs on the shot's own clock (lt), as every jitter in the kit runs on its device's: a shot
      // then looks the same wherever it stands in the film, so a changed gap earlier on moves it and changes
      // nothing in it (studio.py changed compares shot by shot on that).
      const x = lerp(c.x[0], c.x[1], k) + (c.shake ? noise(seed, lt * 0.7) * c.shake : 0);
      const y = lerp(c.y[0], c.y[1], k) + (c.shake ? noise(seed + 5, lt * 0.7) * c.shake : 0);
      cam.style.transform = 'translate(' + x.toFixed(2) + 'px,' + y.toFixed(2) + 'px) scale(' + z.toFixed(4) + ')';
      if (media && media.setTime) media.setTime(Math.max(0, lt) * (m.rate || 1) + (m.offset || 0));
      if (drawn) drawn(t);
      for (const u of ups) u(t);
    };
  } });

  // ---- captions: the spoken words, a few at a time, the current one lit
  // Caption pages follow the phrase, not only the length: a name and its number stay together
  // ("Voyager 1"), so do a number and its unit ("24 hours", "23 people") and a date in either order
  // ("November 19 2026", "29 February 2024"); a number opens its page, so it appears as it is spoken, but
  // never flashes alone; a hedge stays with its negator; and no page is left holding one short word.
  const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];
  const isNum = x => !!x && /^\d[\d,.]*$/.test(x.d);
  const isMonth = x => !!x && MONTHS.includes(x.d.toLowerCase());
  const isName = x => !!x && x.d.toLowerCase() === 'voyager';
  // A word that can follow a number as its unit (24 hours, 55 languages, 25.9 billion).
  const UNITS = ['km', 'cm', 'feet', 'foot', 'percent', 'billion', 'million', 'thousand', 'day', 'year', 'hour', 'minute', 'second', 'month', 'week', 'people', 'person', 'pair'];
  const isUnit = x => !!x && (UNITS.includes(x.d.toLowerCase()) || (x.d.length >= 4 && /s$/i.test(x.d) && !/(ss|us|is)$/i.test(x.d)));
  // In a quiet stretch (a shot with captions: "quiet", used while the viewer must keep their eyes on one
  // mark) a page is a whole sentence, set smaller and dimmer, with no pop and no lit word.
  const groupTokens = (tokens, quiet = []) => {
    const groups = [];
    let cur = [];
    const hush = x => quiet.some(q => x.t0 >= q[0] - 0.05 && x.t0 < q[1]);
    const flush = () => { if (cur.length) { if (hush(cur[0])) cur.quiet = true; groups.push(cur); cur = []; } };
    tokens.forEach((x, i) => {
      const prev = tokens[i - 1], next = tokens[i + 1], before = tokens[i - 2];
      const same = !!prev && prev.line === x.line;
      if (hush(x)) {
        if (cur.length && (!hush(prev) || prev.end || !same)) flush();
        cur.push(x);
        return;
      }
      if (cur.length && hush(prev)) flush();
      const nameNum = same && isName(prev) && isNum(x);
      // A day before its month (29 February). May and March are also plain words (1 in 3 may ...), so they
      // count as a month there only when a year follows.
      const dayMonth = same && isMonth(x) && !!prev && /^\d{1,2}$/.test(prev.d) && +prev.d >= 1 && +prev.d <= 31
        && (!['may', 'march'].includes(x.d.toLowerCase()) || (isNum(next) && /^\d{4}$/.test(next.d)));
      const date = dayMonth || (same && isNum(x) && (isMonth(prev) || (isNum(prev) && isMonth(before) && /^\d{4}$/.test(x.d))));
      const unit = same && isNum(prev) && !prev.stop && !isName(before) && isUnit(x);
      // A number with no unit after it closes its page (ONLY 2 / OF ITS 10 / SCIENCE INSTRUMENTS).
      const bare = same && isNum(prev) && !unit && !date && cur.length > 0;
      const glued = nameNum || date || unit;
      const chars = cur.reduce((n, y) => n + y.d.length + 1, 0);
      // A negator (NOT, NEVER, NO, NOBODY, NOTHING, NONE, or a word ending in N'T) opens its page and keeps up to
      // three words with it, so no page reads as the opposite of its sentence (IT IS / NOT THE BRIDGE, never THE
      // BRIDGE alone). lint.py's NEGATORS holds the same words; selftest.py fails when the two lists differ.
      const NEGATORS = ['not', 'no', 'never', 'nobody', 'nothing', 'none'];
      const isNot = y => !!y && (NEGATORS.includes(y.d.toLowerCase()) || /n['’]t$/i.test(y.d));
      // A hedge right before a negator opens the page with it (ALMOST NOBODY TAKES), so the page a viewer is
      // left on never loses the hedge of its sentence.
      const HEDGES = ['almost', 'nearly', 'hardly', 'barely', 'practically', 'virtually'];
      const isHedge = y => !!y && HEDGES.includes(y.d.toLowerCase());
      const hedged = same && cur.length === 1 && isHedge(cur[0]) && isNot(x);
      const notPage = cur.length > 0 && (isNot(cur[0]) || (isHedge(cur[0]) && (isNot(cur[1]) || hedged)));
      if (cur.length && !glued && same && isNot(x) && !hedged) flush();
      if (cur.length && !glued && isHedge(x) && isNot(next) && next.line === x.line) flush();
      if (cur.length && !glued && !hedged) {
        const full = bare || cur.length >= (notPage ? 4 : 3) || chars + x.d.length > (notPage ? 22 : 20);
        // A number opens its page, unless that would strand one short word before it ("By 2026").
        const stub = cur.length === 1 && cur[0].d.length <= 5;
        const opens = (isNum(x) && !stub) || ((isName(x) || isMonth(x)) && isNum(next) && cur.length >= 2);
        if (full || opens || prev.stop || !same || x.t0 - prev.t1 > 0.45) flush();
      }
      cur.push(x);
    });
    flush();
    // A number alone on its page joins a neighbour where it belongs to one. A number that ends its clause, or
    // follows a determiner, ends a phrase and joins the page before it (A CLASS OF 60, THE OTHER 2, OF THE 23,
    // ANOTHER 100). Any other number spoken in under half a second would only flash, so it joins the page
    // after it (1 JOB, 11 OF 91 TRIES), or the page before it when the next one has no room. The rest keep
    // their own page (HE ASKED / 100 / MIT STUDENTS TO).
    const DETERMINERS = ['a', 'an', 'the', 'other', 'another', 'these', 'those', 'all', 'every', 'both', 'its', 'our', 'their', 'his', 'her', 'my', 'your', 'first', 'last', 'next'];
    const room = (page, extra) => page.length < 4 && page.reduce((n, y) => n + y.d.length + 1, 0) + extra.d.length <= 22;
    for (let i = 0; i < groups.length; i++) {
      const g = groups[i], p = groups[i - 1], n = groups[i + 1];
      if (g.quiet || g.length !== 1 || !isNum(g[0])) continue;
      const x = g[0], last = p && p[p.length - 1];
      const back = !!p && !p.quiet && last.line === x.line && !last.stop && x.t0 - last.t1 <= 0.45 && room(p, x);
      const on = !!n && !n.quiet && n[0].line === x.line && !x.stop && n[0].t0 - x.t1 <= 0.45 && room(n, x);
      const closes = x.stop || (!!last && last.line === x.line && DETERMINERS.includes(last.d.toLowerCase()));
      const brief = x.t1 - x.t0 < 0.5;
      if (back && (closes || (brief && !on))) { p.push(x); groups.splice(i, 1); i--; }
      else if (on && !closes && brief) { n.unshift(x); groups.splice(i, 1); i--; }
    }
    // A page of one short word takes the last word of the page before it (THE SIGNAL / HAD NOT).
    for (let i = 1; i < groups.length; i++) {
      const g = groups[i], p = groups[i - 1];
      if (g.quiet || p.quiet) continue;
      if (g.length !== 1 || g[0].d.length > 5 || isNum(g[0]) || p.length < 2) continue;
      const moved = p[p.length - 1], keep = p[p.length - 2];
      if (moved.stop || moved.line !== g[0].line || g[0].t0 - moved.t1 > 0.45) continue;
      if (isNum(moved) || isName(keep) || isMonth(keep) || (isMonth(moved) && isNum(keep))) continue;
      // A unit stays with its number (never ABOUT 6 / FEET TALL): the short word joins that page instead, when
      // the page has room for it (ABOUT 6 FEET TALL); otherwise both pages stay as they are.
      if (keep.line === moved.line && isNum(keep) && !keep.stop && isUnit(moved)) {
        const chars = p.reduce((n, y) => n + y.d.length + 1, 0) + g[0].d.length;
        if (p.length < 4 && chars <= 22) { p.push(g.shift()); groups.splice(i, 1); i--; }
        continue;
      }
      g.unshift(p.pop());
    }
    return groups;
  };
  const captions = (tokens, mute, quiet, says = []) => layer({ id: 'captions', build(el) {
    const groups = groupTokens(tokens, quiet);
    const spans = [];
    const boxes = groups.map(g => {
      if (g.quiet) {
        // A quiet page keeps its commas, colons and question marks and breaks on sense: a clause stays on one
        // line when it fits the caption box (x 190 to 890), and the lines are balanced.
        const clauses = [[]];
        g.forEach((x, i) => { clauses[clauses.length - 1].push(x); if (x.p === ',' && i < g.length - 1) clauses.push([]); });
        const parts = clauses.map(c => h('span', { class: 'clause', text: c.map(x => x.d + (x.p || '')).join(' ') }));
        const quietBox = h('div', { class: 'k-cap quiet', 'data-role': 'caption' });
        parts.forEach((part, i) => { quietBox.appendChild(part); if (i < parts.length - 1) quietBox.appendChild(document.createTextNode(' ')); });
        Stage.afterFonts(() => {
          meas.font = '700 46px "Poppins"';
          parts.forEach(part => { if (meas.measureText(part.textContent.toUpperCase()).width > 690) part.style.whiteSpace = 'normal'; });
        });
        spans.push([]);
        quietBox.style.display = 'none';
        el.appendChild(quietBox);
        return quietBox;
      }
      const mine = g.map(x => h('span', { text: x.d }));
      spans.push(mine);
      const box = h('div', { class: 'k-cap', 'data-role': 'caption' }, mine);
      box.style.display = 'none';
      el.appendChild(box);
      return box;
    });
    const times = groups.map((g, i) => {
      const a = g[0].t0 - 0.03;
      // A page that begins inside a muted stretch never shows, not even its tail after the stretch ends.
      if (mute.some(m => g[0].t0 >= m[0] - 0.05 && g[0].t0 < m[1])) return [1e9, 1e9];
      // A page that would begin while a device is speaking the line (an overlay with "says": true) is left
      // out too; a page already up stays to its own end.
      if (says.some(m => g[0].t0 >= m[0] && g[0].t0 < m[1])) return [1e9, 1e9];
      // A quiet page stands until the next page or the end of its quiet stretch (the cut), so a hold
      // never leaves the viewer with nothing to read.
      const stretch = g.quiet ? quiet.find(q => g[0].t0 >= q[0] - 0.05 && g[0].t0 < q[1]) : null;
      const tail = stretch ? stretch[1] : g[g.length - 1].t1 + 0.32;
      const b = i + 1 < groups.length ? Math.min(groups[i + 1][0].t0 - 0.03, tail) : tail;
      return [a, b];
    });
    // Kit.pages(): each page as the film shows it. A muted stretch cuts a page's time on screen into the
    // pieces around it (one entry per piece). A page that never shows is listed with shown: false and the
    // times it would have had, so the lint sees a NOT that was muted while the rest of its sentence shows.
    pageList = [];
    groups.forEach((g, i) => {
      let parts = [[times[i][0], times[i][1]]];
      const text = g.map(x => x.d + (g.quiet ? x.p || '' : '')).join(' ');
      if (parts[0][0] >= 1e9) {
        pageList.push({ t0: g[0].t0 - 0.03, t1: g[g.length - 1].t1 + 0.32, text, line: g[0].line, shown: false });
        return;
      }
      for (const m of mute) parts = parts.flatMap(([a, b]) => (m[1] <= a || m[0] >= b ? [[a, b]] : [[a, m[0]], [m[1], b]].filter(([x, y]) => y > x)));
      for (const [a, b] of parts) pageList.push(Object.assign({ t0: a, t1: b, text, line: g[0].line }, g.quiet ? { quiet: true } : {}));
    });
    let shown = -1;
    return t => {
      let on = -1;
      const muted = mute.some(m => t >= m[0] && t < m[1]);
      if (!muted) for (let i = 0; i < times.length; i++) if (t >= times[i][0] && t < times[i][1]) { on = i; break; }
      if (on !== shown) {
        if (shown >= 0) boxes[shown].style.display = 'none';
        if (on >= 0) boxes[on].style.display = groups[on].quiet ? 'block' : 'flex';
        shown = on;
      }
      if (on < 0) return;
      const g = groups[on];
      if (g.quiet) { boxes[on].style.opacity = remap(t, times[on][0], times[on][0] + 0.25).toFixed(3); return; }
      boxes[on].style.transform = 'scale(' + lerp(0.9, 1, spring(t - times[on][0], 5.5, 0.62)).toFixed(4) + ')';
      g.forEach((x, wi) => {
        const until = wi + 1 < g.length ? g[wi + 1].t0 : times[on][1];
        const lit = t >= x.t0 - 0.03 && t < until;
        const sp = spans[on][wi];
        sp.style.color = lit ? 'var(--accent)' : '#fff';
        sp.style.transform = lit ? 'translateY(' + (-7 * spring(t - x.t0 + 0.03, 6, 0.5)).toFixed(2) + 'px) scale(' + (1 + 0.05 * spring(t - x.t0 + 0.03, 6, 0.5)).toFixed(4) + ')' : '';
      });
    };
  } });
  const progress = duration => layer({ id: 'progress', build(el) {
    const bar = h('div', { class: 'k-progress' });
    el.appendChild(bar);
    return t => { bar.style.transform = 'scaleX(' + clamp(t / duration).toFixed(5) + ')'; };
  } });

  const mount = (tl, baseUrl) => {
    base = baseUrl;
    tagText = tl.tag || '';
    if (tl.accent) document.documentElement.style.setProperty('--accent', tl.accent);
    video({ duration: tl.duration, fps: tl.fps || 30 });
    tl.shots.forEach(shot);
    if (tl.tokens && tl.tokens.length) captions(tl.tokens, tl.mute || [], tl.quiet || [], tl.says || []);
    if (tl.progress !== false) progress(tl.duration);
  };
  // base(): the build's URL prefix, for a build's own graphics that load a picture (Stage.img(Kit.base() + src)).
  // pages(): the caption pages, [{t0, t1, text, line}] (quiet pages add quiet: true, pages that never show
  // add shown: false), for the lint.
  return { mount, graphic, pop, slide, mark, fitPx, TYPES, base: () => base, pages: () => pageList.map(p => Object.assign({}, p)) };
})();

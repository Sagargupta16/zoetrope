'use strict';
// Stage runtime: a 1080x1920 DOM stage where every visible value is a pure function of time.
// A video file calls Stage.video(), Stage.scene() and Stage.layer(); the renderer calls
// window.__seek(t) once per frame and takes a screenshot. No timers, no CSS animations, no
// Date and no unseeded random: the same t always draws the same frame.
const Stage = (() => {
  const W = 1080, H = 1920;
  const state = { fps: 30, duration: 0, scenes: [], layers: [], loads: [], pending: [], hooks: [], raf: true };
  let scenesEl = null, layersEl = null;

  // ---- maths
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, p) => a + (b - a) * p;
  const remap = (t, t0, t1) => (t1 === t0 ? (t >= t1 ? 1 : 0) : clamp((t - t0) / (t1 - t0)));
  const ease = {
    linear: p => p,
    inQuad: p => p * p,
    outQuad: p => 1 - (1 - p) * (1 - p),
    inCubic: p => p * p * p,
    outCubic: p => 1 - Math.pow(1 - p, 3),
    inOutCubic: p => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
    outQuart: p => 1 - Math.pow(1 - p, 4),
    inExpo: p => (p <= 0 ? 0 : Math.pow(2, 10 * p - 10)),
    outExpo: p => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
    inOutExpo: p => (p <= 0 ? 0 : p >= 1 ? 1 : p < 0.5 ? Math.pow(2, 20 * p - 10) / 2 : (2 - Math.pow(2, -20 * p + 10)) / 2),
    outBack: p => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); },
  };
  // A damped spring that settles at 1. f in Hz; z is the damping ratio (under 1 overshoots).
  const spring = (t, f = 3.2, z = 0.55) => {
    if (t <= 0) return 0;
    const w = 2 * Math.PI * f;
    if (z >= 1) return 1 - Math.exp(-w * t) * (1 + w * t);
    const wd = w * Math.sqrt(1 - z * z);
    return 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + ((z * w) / wd) * Math.sin(wd * t));
  };
  const hash = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
  const noise = (seed, t) => {
    const i = Math.floor(t), f = t - i, u = f * f * (3 - 2 * f);
    return lerp(hash(seed * 57.3 + i), hash(seed * 57.3 + i + 1), u) * 2 - 1;
  };

  // ---- DOM
  const h = (tag, props = {}, kids = []) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') el.className = v;
      else if (k === 'style') Object.assign(el.style, v);
      else if (k === 'text') el.textContent = v;
      else if (k === 'html') el.innerHTML = v;
      else el.setAttribute(k, v);
    }
    for (const kid of [].concat(kids)) if (kid) el.appendChild(kid);
    return el;
  };
  const img = (src, cls = 'media') => {
    const el = h('img', { class: cls, src });
    state.loads.push(el.decode().catch(() => { throw new Error('image failed: ' + src); }));
    return el;
  };
  // A clip is a folder of numbered JPEG frames (f0001.jpg ...), stepped by local time.
  const clip = (dir, count, fps = 24, cls = 'media') => {
    const el = h('img', { class: cls });
    let shown = -1;
    el.setTime = lt => {
      const i = clamp(Math.floor(lt * fps), 0, count - 1);
      if (i === shown) return;
      shown = i;
      el.src = dir + '/f' + String(i + 1).padStart(4, '0') + '.jpg';
      state.pending.push(el.decode());
    };
    el.setTime(0);
    return el;
  };
  // Split a line into word spans so each word can move on its own.
  const words = (text, cls = '') => {
    const parts = text.split(' ').filter(Boolean);
    return parts.map((w, i) => h('span', { class: ('word ' + cls).trim(), text: w + (i < parts.length - 1 ? ' ' : '') }));
  };

  // ---- scenes and the way they meet
  const DIRS = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] };
  const OVERLAP = { whip: true, slide: true, zoom: true, fade: true };
  const video = def => { state.fps = def.fps || 30; state.duration = def.duration || 0; state.raf = def.raf !== false; };
  const mount = () => {
    if (scenesEl) return;
    const root = document.getElementById('stage');
    scenesEl = h('div', { class: 'layer', id: 'scenes' });
    layersEl = h('div', { class: 'layer', id: 'overlays' });
    root.appendChild(scenesEl);
    root.appendChild(layersEl);
  };
  const scene = def => {
    mount();
    const el = h('section', { class: 'scene' });
    if (def.id) el.id = def.id;
    el.style.display = 'none';
    scenesEl.appendChild(el);
    const s = Object.assign({ tin: { kind: 'cut', d: 0 } }, def, { el, shown: false });
    // a length the builder did not fill reads as 0 (a cut), never as NaN, which would keep the scene off
    if (!Number.isFinite(s.tin.d)) s.tin = Object.assign({}, s.tin, { d: 0 });
    s.update = def.build(el, s) || (() => {});
    state.scenes.push(s);
    return s;
  };
  const layer = def => {
    mount();
    const el = h('div', { class: 'layer' });
    if (def.id) el.id = def.id;
    layersEl.appendChild(el);
    const l = { el, update: def.build(el) || (() => {}) };
    state.layers.push(l);
    return l;
  };
  const transit = (s, next, t) => {
    let tx = 0, ty = 0, sc = 1, op = 1, blur = 0, bx = 1, bright = 1;
    const a = s.tin;
    // A punch with picture: true is drawn by the kit on the picture layer alone, not on the whole scene.
    if (a.kind === 'punch' && !a.picture) sc *= lerp(a.from || 1.12, 1, ease.outExpo(remap(t, s.t0, s.t0 + a.d)));
    if (a.kind === 'flash') bright = lerp(a.gain || 1.7, 1, ease.outCubic(remap(t, s.t0, s.t0 + a.d)));
    if (a.kind === 'whip' || a.kind === 'slide') {
      const p = ease.inOutCubic(remap(t, s.t0 - a.d / 2, s.t0 + a.d / 2));
      const d = DIRS[a.dir || 'left'];
      tx += (1 - p) * -d[0] * W;
      ty += (1 - p) * -d[1] * H;
      if (a.kind === 'whip') { blur = Math.max(blur, Math.sin(Math.PI * p) * (a.blur || 46)); bx = d[0] ? 1 : 0; }
    }
    if (a.kind === 'zoom') {
      const p = remap(t, s.t0 - a.d / 2, s.t0 + a.d / 2);
      // the incoming shot settles from slightly large, so it is full bleed on every frame (it used to grow
      // from 0.72 and stood as a small inset on the dark stage for a few frames)
      sc *= lerp(1.3, 1, ease.outCubic(remap(p, 0.45, 1)));
      op *= remap(p, 0.4, 0.7);
    }
    if (a.kind === 'fade') op *= remap(t, s.t0 - a.d / 2, s.t0 + a.d / 2);
    const b = next && next.tin;
    if (b && OVERLAP[b.kind]) {
      if (b.kind === 'whip' || b.kind === 'slide') {
        const p = ease.inOutCubic(remap(t, next.t0 - b.d / 2, next.t0 + b.d / 2));
        const d = DIRS[b.dir || 'left'];
        tx += p * d[0] * W;
        ty += p * d[1] * H;
        if (b.kind === 'whip') { blur = Math.max(blur, Math.sin(Math.PI * p) * (b.blur || 46)); bx = d[0] ? 1 : 0; }
      }
      if (b.kind === 'zoom') {
        const p = remap(t, next.t0 - b.d / 2, next.t0 + b.d / 2);
        sc *= lerp(1, 1.7, ease.inCubic(remap(p, 0, 0.6)));
        op *= 1 - remap(p, 0.3, 0.6);
      }
    }
    const st = s.el.style;
    st.transform = (tx || ty || sc !== 1) ? 'translate(' + tx.toFixed(2) + 'px,' + ty.toFixed(2) + 'px) scale(' + sc.toFixed(4) + ')' : '';
    st.opacity = op >= 0.999 ? '' : op.toFixed(3);
    let f = '';
    if (bright !== 1) f += 'brightness(' + bright.toFixed(3) + ') ';
    if (blur > 0.5) {
      document.getElementById('blur-x-fe').setAttribute('stdDeviation', bx ? blur.toFixed(1) + ' 0' : '0 ' + blur.toFixed(1));
      f += 'url(#blur-x)';
    }
    st.filter = f.trim();
  };

  // ---- time
  const seek = async t => {
    state.pending = [];
    const list = state.scenes;
    for (let i = 0; i < list.length; i++) {
      const s = list[i];
      const on = t >= s.v0 && t < s.v1;
      if (on !== s.shown) { s.el.style.display = on ? 'block' : 'none'; s.shown = on; }
      if (on) { transit(s, list[i + 1], t); s.update(t - s.t0, t); }
    }
    for (const l of state.layers) l.update(t);
    if (state.pending.length) await Promise.all(state.pending);
    if (state.raf) await new Promise(r => requestAnimationFrame(() => r()));
    return true;
  };
  // Every element with data-role is text the checks care about.
  const registry = () => {
    const out = [];
    for (const el of document.querySelectorAll('[data-role]')) {
      let op = 1, hidden = false;
      for (let n = el; n && n.id !== 'stage'; n = n.parentElement) {
        const c = getComputedStyle(n);
        if (c.display === 'none' || c.visibility === 'hidden') { hidden = true; break; }
        op *= parseFloat(c.opacity);
      }
      if (hidden || op < 0.05) continue;
      // the text itself, not its container: a headline block is as wide as the stage
      const range = document.createRange();
      range.selectNodeContents(el);
      const r = range.getBoundingClientRect(), cs = getComputedStyle(el);
      if (r.width < 1 || r.height < 1) continue;
      out.push({ role: el.dataset.role, text: el.textContent.trim(), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), px: parseFloat(cs.fontSize), color: cs.color, opacity: +op.toFixed(2) });
    }
    return out;
  };
  const boot = async () => {
    try {
      const list = state.scenes.sort((a, b) => a.t0 - b.t0);
      list.forEach((s, i) => {
        const next = list[i + 1];
        s.v0 = s.t0 - (OVERLAP[s.tin.kind] ? s.tin.d / 2 : 0);
        s.v1 = s.t1 + (next && OVERLAP[next.tin.kind] ? next.tin.d / 2 : 0);
        s.el.style.zIndex = String(i + 1);
      });
      if (!state.duration) state.duration = list.length ? list[list.length - 1].t1 : 0;
      for (const face of document.fonts) await face.load();
      await document.fonts.ready;
      for (const fn of state.hooks) fn();
      await Promise.all(state.loads);
      await seek(0);
      window.__meta = { duration: state.duration, fps: state.fps, width: W, height: H, scenes: list.map(s => ({ id: s.id || '', t0: s.t0, t1: s.t1, tin: s.tin.kind })) };
      window.__ready = true;
    } catch (e) { window.__error = String((e && e.message) || e); }
  };
  // Work that needs the fonts (measuring text) runs once they are loaded, before the first frame.
  const afterFonts = fn => state.hooks.push(fn);
  window.__seek = seek;
  window.__registry = registry;
  return { W, H, state, clamp, lerp, remap, ease, spring, hash, noise, h, img, clip, words, video, scene, layer, seek, registry, boot, afterFonts, OVERLAP };
})();

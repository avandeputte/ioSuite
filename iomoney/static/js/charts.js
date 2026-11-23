/* The charts, as inline SVG: a line over time, money in and out by month, a bar. */
import { put } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { CUR, fmtDay, fmtMonth, money } from './core.js';

// ------------------------------------------------------------------ charts: inline SVG
/** A line of values over days ([{day, value}]), with the area under it, a few gridlines and a tip that follows the
    pointer. */
export function lineChart(points, { height = 220, cur = CUR() } = {}) {
  const box = h('div', { class: 'chart' });
  if (!points || points.length < 2) { put(box, h('p', { class: 'muted small' }, 'Not enough history yet: it grows with every day ioMoney runs.')); return box; }
  const W = 800, H = height, padL = 4, padR = 4, padT = 12, padB = 22;
  const vals = points.map((p) => p.value);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo -= Math.abs(lo) * 0.05 || 1; hi += Math.abs(hi) * 0.05 || 1; }
  const span = hi - lo; lo -= span * 0.08; hi += span * 0.08;
  const x = (i) => padL + (i / (points.length - 1)) * (W - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join('');
  const ns = 'http://www.w3.org/2000/svg';
  const el = (n, a = {}) => { const e = document.createElementNS(ns, n); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img', 'aria-label': 'Chart' });
  const g = el('g', { class: 'grid' });
  for (let i = 0; i <= 3; i++) { const yy = padT + i * (H - padT - padB) / 3; put(g, el('line', { x1: 0, x2: W, y1: yy, y2: yy })); }
  put(svg, g);
  if (lo < 0 && hi > 0) put(svg, el('line', { class: 'zero', x1: 0, x2: W, y1: y(0), y2: y(0) }));
  put(svg, el('path', { class: 'area', d: `${d}L${x(points.length - 1)},${H - padB}L${x(0)},${H - padB}Z` }), el('path', { class: 'line', d }));
  const t1 = el('text', { x: padL, y: H - 6 }); t1.textContent = fmtDay(points[0].day);
  const t2 = el('text', { x: W - padR, y: H - 6, 'text-anchor': 'end' }); t2.textContent = fmtDay(points[points.length - 1].day);
  put(svg, t1, t2);
  const hair = el('line', { class: 'hairline', y1: padT, y2: H - padB, visibility: 'hidden' });
  const dot = el('circle', { class: 'dot', r: 4, visibility: 'hidden' });
  put(svg, hair, dot);
  const tip = h('div', { class: 'tip', hidden: true });
  const hi2 = h('div', { class: 'tip', style: { left: '0', top: '-4px', transform: 'none', boxShadow: 'none', border: '0', background: 'none', padding: '0' } });
  hi2.textContent = money(hi - span * 0.08, cur, { whole: true });
  put(box, svg, tip, hi2);
  const move = (e) => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(points.length - 1, Math.round(((e.clientX - r.left) / r.width * W - padL) / (W - padL - padR) * (points.length - 1))));
    const px = x(i), py = y(points[i].value);
    hair.setAttribute('x1', px); hair.setAttribute('x2', px); hair.setAttribute('visibility', 'visible');
    dot.setAttribute('cx', px); dot.setAttribute('cy', py); dot.setAttribute('visibility', 'visible');
    tip.hidden = false; tip.style.left = `${(px / W) * 100}%`; tip.style.top = `${Math.max(0, (py / H) * r.height - 40)}px`;
    tip.replaceChildren(h('b', null, money(points[i].value, cur)), ' · ', fmtDay(points[i].day, true));
  };
  const leave = () => { tip.hidden = true; hair.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); };
  svg.addEventListener('pointermove', move); svg.addEventListener('pointerleave', leave);
  return box;
}

/** Money in and out, month by month: two bars a month. */
export function flowChart(items, { height = 200, cur = CUR() } = {}) {
  const box = h('div', { class: 'chart' });
  if (!items.length) return box;
  const W = 800, H = height, padB = 22, padT = 8;
  const top = Math.max(1, ...items.map((m) => Math.max(m.income, m.spent)));
  const slot = W / items.length, bw = Math.max(2, Math.min(26, slot / 3));
  const ns = 'http://www.w3.org/2000/svg';
  const el = (n, a = {}) => { const e = document.createElementNS(ns, n); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img', 'aria-label': 'Money in and out by month' });
  const y = (v) => padT + (1 - v / top) * (H - padT - padB);
  const tip = h('div', { class: 'tip', hidden: true });
  items.forEach((m, i) => {
    const cx = slot * i + slot / 2;
    const r1 = el('rect', { class: 'bar-in', x: cx - bw - 1, y: y(m.income), width: bw, height: H - padB - y(m.income), rx: 2 });
    const r2 = el('rect', { class: 'bar-out', x: cx + 1, y: y(m.spent), width: bw, height: H - padB - y(m.spent), rx: 2 });
    const hit = el('rect', { x: slot * i, y: 0, width: slot, height: H, fill: 'transparent' });
    hit.addEventListener('pointerenter', () => { tip.hidden = false; tip.style.left = `${(cx / W) * 100}%`; tip.replaceChildren(h('b', null, fmtMonth(m.month)), h('br'), `In ${money(m.income, cur, { whole: true })} · Out ${money(m.spent, cur, { whole: true })}`); });
    hit.addEventListener('pointerleave', () => { tip.hidden = true; });
    hit.addEventListener('click', () => { location.hash = `#/spending/${m.month}`; });
    const t = el('text', { x: cx, y: H - 6, 'text-anchor': 'middle' }); t.textContent = new Date(`${m.month}-15T12:00:00`).toLocaleDateString(undefined, { month: 'short' });
    put(svg, r1, r2, t, hit);
  });
  put(box, svg, tip);
  return box;
}

export function bar(label, value, max, { href, hueVar, cur, sub } = {}) {
  const w = max ? Math.max(1, Math.round(Math.abs(value) / max * 100)) : 0;
  const kids = [h('span', { class: 'barname' }, label, sub ? h('small', { class: 'muted' }, ` ${sub}`) : null),
    h('span', { class: 'bartrack' }, h('span', { class: `barfill ${value < 0 ? 'neg' : ''}`, style: { width: `${w}%`, '--hue': hueVar ? `var(${hueVar})` : null } })),
    h('span', { class: 'num' }, money(value, cur, { whole: Math.abs(value) >= 1000 }))];
  return href ? h('a', { class: 'barrow', href }, kids) : h('div', { class: 'barrow' }, kids);
}

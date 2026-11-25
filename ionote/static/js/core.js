/** DOM helpers, icons, dates, the API calls, toasts, dialogs and menus, and the state every module shares.
 *  What every app's page has (the icons, the note at the foot, dialogs, the sidebar) comes from the suite's frame
 *  (iosuite_shared/static/frame.js); what is left here is ioNote's own. */
import * as frame from '../../api/auth/frame.js';
import { $, $$, addIcons, confirmDialog, fail, icon, paintIcons, toast } from '../../api/auth/frame.js';
export { $, $$, fail, icon, paintIcons, toast };
export const store = frame.storeFor('ionote');  // what this browser remembers for the app (the sidebar, a folded section)

// ioNote's own icons, beside the ones every app's page has (frame.ICONS)
addIcons({
  notes: 'M3 18h12v-2H3v2zM3 6v2h18V6H3zm0 7h18v-2H3v2z',
  folder: 'M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z',
  folderOff: 'M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z',
  tag: 'M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z',
  trash: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  restore: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z',
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  gear: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  family: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  paste: 'M19 2h-4.18C14.4.84 13.3 0 12 0S9.6.84 9.18 2H5c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm7 18H5V4h2v3h10V4h2v16z',
  eye: 'M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z',
  checklist: 'M22 7h-9v2h9V7zm0 8h-9v2h9v-2zM5.54 11 2 7.46l1.41-1.41 2.12 2.12 4.24-4.24 1.41 1.41L5.54 11zm0 8L2 15.46l1.41-1.41 2.12 2.12 4.24-4.24 1.41 1.41L5.54 19z',
  attach: 'M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5a2.5 2.5 0 0 1 5 0v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5a2.5 2.5 0 0 0 5 0V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z',
  file: 'M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
  pdf: 'M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8.5 7.5c0 .83-.67 1.5-1.5 1.5H9v2H7.5V7H10c.83 0 1.5.67 1.5 1.5v1zm5 2c0 .83-.67 1.5-1.5 1.5h-2.5V7H15c.83 0 1.5.67 1.5 1.5v3zm4-3H19v1h1.5V11H19v2h-1.5V7h3v1.5zM9 9.5h1v-1H9v1zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm10 5.5h1v-3h-1v3z',
  template: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z',
  down: 'M7 10l5 5 5-5z',
  bold: 'M15.6 10.79c.97-.67 1.65-1.77 1.65-2.79 0-2.26-1.75-4-4-4H7v14h7.04c2.09 0 3.71-1.7 3.71-3.79 0-1.52-.86-2.82-2.15-3.42zM10 6.5h3c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-3v-3zm3.5 9H10v-3h3.5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5z',
  italic: 'M10 4v3h2.21l-3.42 8H6v3h8v-3h-2.21l3.42-8H18V4z',
  strike: 'M10 19h4v-3h-4v3zM5 4v3h5v3h4V7h5V4H5zM3 14h18v-2H3v2z',
  code: 'M9.4 16.6 4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0 4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z',
  heading: 'M5 4v3h5.5v12h3V7H19V4z',
  bullets: 'M4 10.5c-.83 0-1.5.67-1.5 1.5s.67 1.5 1.5 1.5 1.5-.67 1.5-1.5-.67-1.5-1.5-1.5zm0-6c-.83 0-1.5.67-1.5 1.5S3.17 7.5 4 7.5 5.5 6.83 5.5 6 4.83 4.5 4 4.5zm0 12c-.83 0-1.5.68-1.5 1.5s.68 1.5 1.5 1.5 1.5-.68 1.5-1.5-.67-1.5-1.5-1.5zM7 19h14v-2H7v2zm0-6h14v-2H7v2zm0-8v2h14V5H7z',
  numbers: 'M2 17h2v.5H3v1h1v.5H2v1h3v-4H2v1zm1-9h1V4H2v1h1v3zm-1 3h1.8L2 13.1v.9h3v-1H3.2L5 10.9V10H2v1zm5-6v2h14V5H7zm0 14h14v-2H7v2zm0-6h14v-2H7v2z',
  quote: 'M6 17h3l2-4V7H5v6h3zm8 0h3l2-4V7h-6v6h3z',
  codeblock: 'M4 7v2c0 .55-.45 1-1 1H2v4h1c.55 0 1 .45 1 1v2c0 1.65 1.35 3 3 3h3v-2H7c-.55 0-1-.45-1-1v-2c0-1.3-.84-2.42-2-2.83v-.34C5.16 11.42 6 10.3 6 9V7c0-.55.45-1 1-1h3V4H7C5.35 4 4 5.35 4 7zm17 3c-.55 0-1-.45-1-1V7c0-1.65-1.35-3-3-3h-3v2h3c.55 0 1 .45 1 1v2c0 1.3.84 2.42 2 2.83v.34c-1.16.41-2 1.52-2 2.83v2c0 .55-.45 1-1 1h-3v2h3c1.65 0 3-1.35 3-3v-2c0-.55.45-1 1-1h1v-4h-1z',
  rule: 'M4 11h16v2H4z',
});

/** h('div.card', {onclick}, child, 'text', ...): a small element builder. */
export function h(tag, attrs, ...kids) {
  const [head, ...classes] = tag.split('.');
  const [name, id] = head.split('#');
  const e = document.createElement(name || 'div');
  if (id) e.id = id;
  if (classes.length) e.className = classes.join(' ');
  if (attrs && (typeof attrs !== 'object' || attrs instanceof Node || Array.isArray(attrs))) { kids.unshift(attrs); attrs = null; }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className += (e.className ? ' ' : '') + v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k in e && typeof v !== 'string') e[k] = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k instanceof Node ? k : String(k));
  return e;
}

export const COLORS = ['red', 'orange', 'yellow', 'green', 'mint', 'teal', 'blue', 'indigo', 'purple', 'pink', 'brown', 'gray'];
export const colorVar = (c) => (c && COLORS.includes(c) ? `var(--c-${c})` : null);

// ---- dates
const DAY = 86400000;
export function fmtDate(sec, long = false) {
  if (!sec) return '';
  const d = new Date(sec * 1000), now = new Date();
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (long) return d.toLocaleDateString([], { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' }) + ', ' + time;
  if (d.toDateString() === now.toDateString()) return time;
  if (now - d < 6 * DAY) return d.toLocaleDateString([], { weekday: 'short' }) + ' ' + time;
  return d.toLocaleDateString([], { year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric', month: 'short', day: 'numeric' });
}

// ---- the API
export class ApiError extends Error { constructor(status, msg, body) { super(msg); this.status = status; this.body = body; } }
export async function api(path, { method = 'GET', body, raw, headers, keepalive } = {}) {
  const opt = { method, headers: { ...(headers || {}) }, credentials: 'same-origin' };
  if (body instanceof FormData || raw) opt.body = body;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers['Content-Type'] = 'application/json'; }
  // keepalive: the request outlives the page (a save as the tab closes); browsers take up to 64 KB that way
  if (keepalive && typeof opt.body === 'string' && opt.body.length < 60000) opt.keepalive = true;
  const r = await fetch(path, opt);
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('json') ? await r.json().catch(() => null) : null;
  if (!r.ok) {
    if (r.status === 401 && state.onSignedOut) state.onSignedOut();
    throw new ApiError(r.status, (data && data.detail) || `${r.status} ${r.statusText}`, data);
  }
  return data;
}

// ---- shared state
export const state = { me: null, meta: null, settings: {}, onSignedOut: null };
export const canWrite = () => !!(state.me && state.me.canWrite);  // a member or more: the notes are one's own
/** The Family space: shown to who is signed in; its notes are changed by editors and admins (meta.familyWrite). */
export const hasFamily = () => !!(state.me && state.me.user);
export const familyWrite = () => canWrite() && !!(state.meta && state.meta.familyWrite);
export const canChange = (n) => canWrite() && (!n.family || familyWrite());
export const isAdmin = () => !!(state.me && state.me.isAdmin);

// ---- toast, dialogs, menus
/** A dialog over the page, as every app draws it (frame.dialog), with ioNote's buttons: `action` is waited for, and
 *  false keeps the dialog open (a form that was not right yet). opts.cls: a class for the box ('wide'). */
export function dialog(title, content, buttons = [], opts = {}) {
  const list = (buttons.length ? buttons : [{ label: 'OK', value: true, primary: true }]).filter(Boolean).map((b) => ({
    label: b.label, primary: b.primary, danger: b.danger,
    value: b.action ? async () => { const v = await b.action(); return v === false ? undefined : (v === undefined ? b.value : v); } : b.value,
  }));
  return frame.dialog(title, content, list, opts.cls || '', { wait: true });
}
export async function ask(title, label, value = '', okLabel = 'OK') {
  const input = h('input', { class: 't', type: 'text', value, 'aria-label': label, placeholder: label });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') input.closest('.dialog').querySelector('.primary').click(); });
  return dialog(title, input, [{ label: 'Cancel', value: null }, { label: okLabel, primary: true, action: () => input.value.trim() || false }]);
}
export const confirmIt = (title, text, okLabel = 'OK', danger = false) => confirmDialog(title, text, okLabel, danger);

let openMenu = null;
export function closeMenu() { if (openMenu) { openMenu.remove(); openMenu = null; } }
export function menu(anchor, items) {
  closeMenu();
  const m = h('div.menu', { role: 'menu' }, items.filter(Boolean).map((it) => {
    if (it === '-') return h('div.sep');
    if (it.head) return h('div.mh', it.head);
    if (it.node) return it.node;
    return h('div.mi', { role: 'menuitem', onclick: () => { closeMenu(); it.action(); } }, it.icon ? icon(it.icon) : null, it.label);
  }));
  document.body.append(m);
  const r = anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: anchor.x, right: anchor.x, top: anchor.y, bottom: anchor.y };
  const mw = m.offsetWidth, mh = m.offsetHeight;
  m.style.left = Math.max(8, Math.min(window.innerWidth - mw - 8, r.left)) + 'px';
  m.style.top = (r.bottom + mh + 8 > window.innerHeight ? Math.max(8, r.top - mh - 4) : r.bottom + 4) + 'px';
  openMenu = m;
  setTimeout(() => document.addEventListener('click', (e) => { if (!m.contains(e.target)) closeMenu(); }, { once: true }), 0);
  return m;
}
export function colorPicker(current, onPick) {
  return h('div.swatches', h('div.swatch.none' + (current ? '' : '.on'), { title: 'No colour', onclick: () => { closeMenu(); onPick(null); } }),
    COLORS.map((c) => h('div.swatch' + (c === current ? '.on' : ''), { title: c, style: { background: `var(--c-${c})` }, onclick: () => { closeMenu(); onPick(c); } })));
}

export function debounce(fn, ms) { let t; const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; d.flush = () => { clearTimeout(t); fn(); }; return d; }
export const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16); })).toUpperCase();
export function initials(name) { return (name || '?').trim().slice(0, 1).toUpperCase(); }
export function displayTitle(n) {
  for (const t of [n.title, n.body, n.ocrText]) { const line = (t || '').split('\n').map((s) => s.trim()).find(Boolean); if (line) return line.slice(0, 80); }
  return n.hasImage ? 'Image' : 'Untitled';
}

/* The frame the pages of the io apps share, kept once: finding things in the page, the icons most of them draw, the
   note at the foot of the page, dialogs, the menu that drops from a button, the menu of the suite's apps, the sidebar
   that docks or slides and the parts it is made of (navParts), the suite's one appearance choice. One ES module,
   served by every app at <app>/api/auth/frame.js (beside ui.js, the account panels and h()), so a page loads it from
   its own app whichever server that is:

       import * as frame from '../api/auth/frame.js';
       import { $, addIcons, dialog, icon, toast } from '../api/auth/frame.js';
       addIcons({ box: 'M20 2H4…' });              // the app's own icons, beside the shared ones
       const store = frame.storeFor('iothings');   // what this browser remembers for the app

   Each page stays its own page: this is what they all did in the same words, nothing more. */
import { h, passkeyButton, signIn } from './ui.js';

// ------------------------------------------------------------------ the page
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
export const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
/** append with the same manners. */
export const put = (el, ...kids) => el.append(...kids.flat(9).filter((k) => k != null && k !== false));
/** A colour of its own for a name (an avatar without a picture), and the letters on it. */
export const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
export const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
/** A labelled field of a form. */
export const fld = (l, e, hint) => h('label', { class: 'field' }, h('span', null, l), e, hint ? h('small', { class: 'muted' }, hint) : null);
/** What this browser remembers for an app (the sidebar, a folded section, the last tab): localStorage under the app's
    name, and nothing when the browser keeps none (private mode). The appearance is not here: it is the suite's one
    choice, kept with the account (applyTheme). */
export const storeFor = (app) => ({
  get: (k) => { try { return localStorage.getItem(`${app}.${k}`); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(`${app}.${k}`, v); } catch { /* private mode */ } },
});

// ------------------------------------------------------------------ icons
// Material icons as path data (24x24): the ones several apps draw; an app adds its own with addIcons()
export const ICONS = {
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  globe: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z',
  history: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z',
  home: 'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  list: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  minus: 'M19 13H5v-2h14v2z',
  money: 'M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z',
  next: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  photo: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  prev: 'M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z',
  print: 'M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z',
  receipt: 'M18 17H6v-2h12v2zm0-4H6v-2h12v2zm0-4H6V7h12v2zM3 22l1.5-1.5L6 22l1.5-1.5L9 22l1.5-1.5L12 22l1.5-1.5L15 22l1.5-1.5L18 22l1.5-1.5L21 22V2l-1.5 1.5L18 2l-1.5 1.5L15 2l-1.5 1.5L12 2l-1.5 1.5L9 2 7.5 3.5 6 2 4.5 3.5 3 2v20z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
};
export function addIcons(more) { Object.assign(ICONS, more); }
/** The icons the page itself names (<span class="ic" data-ic="menu">), drawn once the page's script is in. */
export function paintIcons(root = document) { root.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic))); }
export const icon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'ic ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

// ------------------------------------------------------------------ the note at the foot of the page
let toastTimer;
/** A note at the foot of the page (#toast), gone after a few seconds. `act`: [label, what it does], a button beside
    the words (Undo), and the note stays longer. */
export function toast(msg, act, ms) {
  const t = $('#toast');
  fill(t, act ? h('span', null, msg) : msg, act ? h('button', { class: 'undo', onclick: () => { t.hidden = true; act[1](); } }, act[0]) : null);
  t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, ms || (act ? 9000 : 3500));
}
export const fail = (e) => toast(e.message || String(e));

// ------------------------------------------------------------------ dialogs
/** A dialog over the page; resolves with the value of the button pressed, or null when it is put away (a click
    beside it). buttons: [{ label, value, primary, danger }]; a value that is a function is called and its answer is
    the dialog's. `cls`: a class for the box ('wide').
    opts.wait: a function's answer is waited for, the dialog stays open when it answers nothing (a form that was not
    right yet) and what it throws is shown as a note. opts.focus: which field gets the cursor. */
export function dialog(title, body, buttons, cls = '', opts = {}) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.close = close;  // Escape, or something inside the dialog, ends it with this answer
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const press = opts.wait
      ? async (b) => {
        if (typeof b.value !== 'function') { close(b.value); return; }
        try { const v = await b.value(); if (v !== undefined) close(v); } catch (e) { fail(e); }
      }
      : (b) => close(typeof b.value === 'function' ? b.value() : b.value);
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: () => press(b) }, b.label));
    back.append(h('div', { class: `dialog ${cls || ''}`, role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector(opts.focus || 'input,select,textarea'); if (f) f.focus();
  });
}
/** A question with Cancel and one answer; `text` is words or an element. */
export const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, typeof text === 'string' ? h('p', null, text) : text,
  [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);
export function closeDialogs() { document.querySelectorAll('.dialog-back').forEach((d) => d.remove()); }

// ------------------------------------------------------------------ the menu that drops from a button
let openMenu = null;
/** Whether a menu is open (Escape puts it away before anything else). */
export const menuOpen = () => !!openMenu;
export function closeMenu() {
  if (!openMenu) return;
  openMenu.el.remove(); document.removeEventListener('click', openMenu.outside); openMenu = null;
}
/** A menu that drops from a button: items are [icon, label, what it does (a function, or an address)]; a second click
    on the button, a click elsewhere or scrolling puts it away. */
export function popMenu(btn, items) {
  const mine = openMenu && openMenu.btn === btn;
  closeMenu();
  if (mine) return;
  const el = h('div', { class: 'menu pop', role: 'menu' }, items.filter(Boolean).map(([ic, label, act]) => (typeof act === 'string'
    ? h('a', { class: 'mi', role: 'menuitem', href: act, onclick: closeMenu }, icon(ic, 's'), label)
    : h('button', { class: 'mi', role: 'menuitem', onclick: () => { closeMenu(); act(); } }, icon(ic, 's'), label))));
  document.body.append(el);
  const r = btn.getBoundingClientRect();
  el.style.left = `${Math.round(Math.max(8, Math.min(r.right - el.offsetWidth, innerWidth - el.offsetWidth - 8)))}px`;
  el.style.top = `${Math.round(r.bottom + 4 + el.offsetHeight > innerHeight - 8 ? Math.max(8, r.top - el.offsetHeight - 4) : r.bottom + 4)}px`;
  const outside = (e) => { if (!el.contains(e.target) && !btn.contains(e.target)) closeMenu(); };
  openMenu = { el, btn, outside };
  setTimeout(() => document.addEventListener('click', outside), 0);
  const main = $('#main'); if (main) main.addEventListener('scroll', closeMenu, { once: true });
}

// ------------------------------------------------------------------ the menu of the suite's apps
/** The apps of the suite this person may open, in the suite's one order (this app too), and this app's key. Empty
    when this app is the only one: then there is no menu. */
export const suite = { items: [], self: null };
let suitePop = null;
/** Ask the app which apps there are (api: the page's client), show or hide the page's #suitebtn. */
export async function loadSuite(api) {
  try {
    const r = await api('api/auth/suite');
    suite.items = (r.items || []).filter((a) => a.url); suite.self = r.app;
    if (!suite.items.some((a) => a.app !== r.app)) suite.items = [];
  } catch { suite.items = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !suite.items.length; b.onclick = () => toggleSuite(b); }
  if (!suite.items.length) closeSuite();
  return suite.items;
}
function appTile(a) {
  const mark = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span', { class: 'appic fb', style: { background: a.color || 'var(--brand)' } }, mark);
  const ic = a.icon ? h('img', { class: 'appic', src: a.icon, alt: '', onerror: (e) => e.currentTarget.replaceWith(fallback()) }) : fallback();
  const el = h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite },
    ic, h('span', { class: 'appnm' }, a.name || a.app));
  el.classList.toggle('tool', !!a.adminTool);  // admin tools: a smaller icon
  if (a.app === suite.self) { el.classList.add('cur'); el.setAttribute('aria-current', 'page'); }
  return el;
}
function suiteOutside(e) { if (suitePop && !suitePop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
function suiteKey(e) { if (e.key === 'Escape' && suitePop) { closeSuite(); e.stopPropagation(); } }
export function closeSuite() {
  if (!suitePop) return;
  suitePop.remove(); suitePop = null;
  document.querySelectorAll('.suitebtn[aria-expanded]').forEach((b) => b.removeAttribute('aria-expanded'));
  document.removeEventListener('click', suiteOutside, true);
  document.removeEventListener('keydown', suiteKey, true);
  removeEventListener('resize', closeSuite);
}
/** The menu under the button with the suite's mark: the apps, then the admin tools in a section of their own (the
    server sends those to their admins only). A second click, a click elsewhere or Escape puts it away. */
export function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!suite.items.length) return;
  const apps = suite.items.filter((a) => !a.adminTool), tools = suite.items.filter((a) => a.adminTool);
  suitePop = h('div', { class: 'suitepop', role: 'menu', 'aria-label': 'ioSuite apps', style: { '--cols': String(Math.min(3, Math.max(apps.length, tools.length))) } },
    ...apps.map(appTile), ...(tools.length ? [h('div', { class: 'suitesec' }, 'Admin tools'), ...tools.map(appTile)] : []));
  document.body.append(suitePop);
  btn.setAttribute('aria-expanded', 'true');
  const r = btn.getBoundingClientRect();
  suitePop.style.top = `${Math.round(r.bottom + 6)}px`;
  suitePop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - suitePop.offsetWidth - 8)))}px`;
  suitePop.querySelector('a')?.focus({ preventScroll: true });
  // at once, not after a timer: a busy page runs a tap before a timer, so a quick tap outside left the menu open (the
  // click that opened it has passed the document already, and suiteOutside ignores the button anyway)
  document.addEventListener('click', suiteOutside, true); document.addEventListener('keydown', suiteKey, true); addEventListener('resize', closeSuite);
}
/** Settings › People, Apps, Servers and Keys: the suite's panel (api/suite-admin/ui.js), in the app's Settings page. */
export async function suitePanel(el, r, cls = 'warn') {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: cls }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}
/** Settings › This app (the app's admins): the settings the app declares (its app.json), kept in the suite's one
    home for them and read as they are now, so a change takes hold without a restart. The same block in every app,
    beside the app's own screens for the ones that need a picker or a list (those say so and are shown here only). */
export async function appSettings(el, { toast: say = toast } = {}) {
  const url = new URL('api/app-settings', document.baseURI).href;
  let d;
  try { d = await (await fetch(url, { headers: { Accept: 'application/json' } })).json(); } catch (e) { el.append(h('p', { class: 'warn' }, `The settings did not load: ${e.message}`)); return; }
  if (!d || !d.settings) { el.append(h('p', { class: 'warn' }, (d && d.detail) || 'Only an admin of this app sees its settings.')); return; }
  const save = async (st, value, back) => {
    try {
      const r = await fetch(`${url}/${encodeURIComponent(st.name)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ value }) });
      const n = await r.json();
      if (!r.ok) throw new Error(n.detail || r.statusText);
      st.value = (n.settings || []).find((x) => x.name === st.name)?.value ?? '';
      say(st.value === '' ? 'Back to the default' : 'Saved');
    } catch (e) { say(e.message); if (back) back(); }
  };
  const yes = (v) => /^(1|true|yes|on)$/i.test(v || '');
  const row = (st) => {
    const fallback = st.suite ? `the suite’s: ${st.suite}` : st.default ? `default: ${st.default}` : '';
    const id = `io-set-${st.name}`;
    let input;
    if (st.byApp) {   // its own screen is the editor for it (a list, a picker); here it is only shown
      const now = st.value !== '' ? st.value : (st.suite || st.default || '');
      input = h('div', { class: 'io-set-shown' }, st.type === 'switch' ? (yes(now) ? 'On' : 'Off') : st.value !== '' ? st.value.replace(/,(?=\S)/g, ', ') : now ? `${now} (default)` : 'not set');
    } else if (st.type === 'switch') {
      const on = st.value !== '' ? yes(st.value) : yes(st.suite || st.default);
      input = h('input', { id, type: 'checkbox', checked: on, onchange: (e) => save(st, e.target.checked, () => { e.target.checked = !e.target.checked; }) });
    } else if (st.type === 'choice') {
      const opts = (st.choices || []).map((c) => (Array.isArray(c) ? c : [c, c]));
      input = h('select', { id, class: 't', onchange: (e) => save(st, e.target.value) },
        h('option', { value: '', selected: st.value === '' ? true : null }, fallback || 'default'),
        opts.map(([k, l]) => h('option', { value: k, selected: st.value === String(k) ? true : null }, l)));
    } else {
      input = h('input', { id, class: 't', type: st.type === 'number' ? 'number' : 'text', value: st.value, placeholder: fallback, autocomplete: 'off', spellcheck: false,
        onchange: (e) => save(st, e.target.value.trim(), () => { e.target.value = st.value; }) });
    }
    // one line: the label (and the name `iosuite set` takes) on the left, the field on the right, what it does below it
    const note = [st.hint, st.byApp ? '' : st.restart ? 'Applies when the app starts again.' : ''].filter(Boolean).join(' ');
    return h('div', { class: 'io-set' }, h('label', { for: st.byApp ? null : id }, st.label, h('span', null, st.name)),
      h('div', null, input, note ? h('div', { class: 'io-set-note' }, note) : null));
  };
  if (!document.getElementById('io-set-css')) document.head.append(h('style', { id: 'io-set-css' }, SET_CSS));
  const here = d.settings.filter((st) => !st.byApp), shown = d.settings.filter((st) => st.byApp);
  el.append(h('div', { class: 'box' }, h('h2', null, 'This app'),
    h('p', { class: 'muted small' }, 'Every setting of this app, kept with the suite in one place: the same values Settings › Apps › All settings shows. A field left empty takes the default.'),
    h('div', { class: 'io-sets' }, here.map(row)),
    shown.length ? [h('h3', { class: 'io-set-head' }, 'Changed on their own screens'),
      h('p', { class: 'muted small' }, 'These have a screen of their own in this app; here they are only shown.'),
      h('div', { class: 'io-sets' }, shown.map(row))] : null));
}
/* Settings › This app: one line per setting, as Settings › Apps › All settings draws them. Carried here, not in a
   stylesheet, so the block looks the same in an app with its own stylesheet (the start page, ioPix). */
const SET_CSS = `
.io-set { display: grid; grid-template-columns: minmax(160px, 260px) minmax(0, 1fr); gap: 2px 16px; align-items: start; padding: 7px 0; border-top: 1px solid var(--line, #8884); margin: 0; }
.io-sets > .io-set:first-child { border-top: 0; }
.io-set > label { min-height: 36px; display: flex; flex-direction: column; justify-content: center; gap: 0; margin: 0; font-size: inherit; font-weight: 500; color: inherit; overflow-wrap: anywhere; }
.io-set > label > span { font-weight: 400; font-size: 11px; color: var(--fg2, #888); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.io-set > div { min-width: 0; }
.io-set input.t, .io-set select.t { display: block; width: 100%; max-width: 420px; height: 36px; margin: 0; box-sizing: border-box; padding: 0 12px; font: inherit; color: inherit;
  border: 1px solid var(--line, #8884); border-radius: var(--r-s, 8px); background: var(--bg, transparent); outline: 0; }
.io-set input.t:focus, .io-set select.t:focus { border-color: var(--accent, #68c); }
.io-set input[type="checkbox"] { display: block; width: 18px; height: 18px; margin: 9px 0; }
.io-set-shown { min-height: 36px; display: flex; align-items: center; color: var(--fg2, #888); overflow-wrap: anywhere; word-break: break-word; }
.io-set-note { margin-top: 3px; max-width: 640px; font-size: 12px; color: var(--fg2, #888); }
.io-set-head { margin: 22px 0 2px; font-size: 14px; font-weight: 600; }
@media (max-width: 600px) { .io-set { grid-template-columns: minmax(0, 1fr); } .io-set > label { min-height: 0; } .io-set input.t, .io-set select.t { max-width: none; } }
`;

/** The account panels (api/auth/ui.js), asked for when Settings opens. */
export const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);

// ------------------------------------------------------------------ the sign-in screen
/** The sign-in screen over the page, the same in every app: a tile per account (one click for an account without a
    password, a password for the others), "Other" for a name typed in, a passkey where the browser has one; while the
    suite has no account at all (`first`), the form that makes the admin. name: the app's name after "io" (Things).
    api: the page's client. face(account): the picture on a tile, where the app has one of its own. */
export function signInScreen({ api, name: app, first, face }) {
  if (document.querySelector('.signin')) return;
  const name = h('input', { class: 't', placeholder: 'User name', autocomplete: 'username', autocapitalize: 'none' });
  const pw = h('input', { class: 't', type: 'password', placeholder: first ? 'Password (8 or more)' : 'Password', autocomplete: first ? 'new-password' : 'current-password' });
  const err = h('div', { class: 'err' });
  const form = h('div', { class: 'signin-form' }, name, pw);
  const tiles = h('div', { class: 'accounts' });
  const btn = h('button', { class: 'pillbtn primary noic', type: 'submit' }, first ? 'Create the admin account' : 'Sign in');
  const login = async (n, p) => {
    err.textContent = '';
    try { if (first) await api('api/auth/setup', { method: 'POST', json: { name: n, password: p } }); else await signIn({ name: n, password: p }); location.reload(); } catch (x) { err.textContent = x.message; }
  };
  const submit = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: submit },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, app))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who adds the rest of the family in Settings.') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn), first ? null : passkeyButton(() => location.reload()))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  const letters = (a) => h('span', { class: 'av big', style: { '--h': hue(a.displayName || a.name) } }, initials(a.displayName || a.name));
  api('api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true; btn.hidden = true;
    tiles.append(...d.accounts.map((a) => {
      const t = h('button', { type: 'button', class: 'account', title: a.passwordless ? `Sign in as ${a.name}` : `${a.name} (password)`, onclick: () => {
        pick(t);
        if (a.passwordless) { login(a.name, ''); return; }
        name.value = a.name; name.hidden = true; form.hidden = false; btn.hidden = false; pw.value = ''; pw.focus();
      } }, (face || letters)(a, letters), h('span', { class: 'nm' }, a.displayName || a.name), a.passwordless ? null : h('span', { class: 'muted small' }, 'password'));
      return t;
    }), h('button', { type: 'button', class: 'account', title: 'Type a user name', onclick: (e) => {
      pick(e.currentTarget); name.value = ''; name.hidden = false; form.hidden = false; btn.hidden = false; name.focus();
    } }, h('span', { class: 'av big other' }, '…'), h('span', { class: 'nm' }, 'Other')));
  }).catch(() => name.focus());
}

// ------------------------------------------------------------------ the account's menu
/** The round button with the account's letters (in `m`, the page's #usermenu) and the menu under it: who is signed
    in, the app's own entries (`more(close)`: a list of elements, see menuLink and themeEntry), Settings and Sign out.
    api: the page's client. Signing out goes on to the proxy's own sign-out where there is one (Cloudflare Access). */
export function userMenu(m, user, api, more) {
  m.replaceChildren();
  if (!user) return;
  const btn = h('button', { class: 'avatarbtn', title: user.displayName, style: { background: `hsl(${hue(user.name)} 45% 45%)` } }, initials(user.displayName));
  let menu = null;
  const close = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) close(); };
  btn.onclick = () => {
    if (menu) return close();
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, user.displayName), h('div', { class: 'muted small' }, `${user.name} · ${user.role}`)),
      more ? more(close) : null,
      menuLink('#/settings', 'settings', 'Settings', close),
      h('button', { class: 'mi', onclick: async () => { const r = await api('api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/** An entry of a menu that goes to an address of the page. */
export const menuLink = (href, ic, label, close) => h('a', { class: 'mi', href, onclick: close }, icon(ic, 's'), label);
/** The entry that steps the suite's appearance on: the device's, light, dark. apply(choice): the app's applyTheme. */
export function themeEntry(apply, close) {
  const theme = themeChoice();
  return h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; apply(n); close(); toast(`Appearance: ${n}`); } },
    icon('theme', 's'), `Appearance: ${theme}`);
}

// ------------------------------------------------------------------ the sidebar
// It docks beside the page on a wide screen unless its button put it away (remembered); otherwise it slides over.
export const DOCK_MIN = 1100;
export function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
export function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
/** The sidebar as this browser remembers it for the app (`store`), and what its button (#sidebtn) shows. */
export function applySidebar(store) {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && store.get('sidebar') !== '0';
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
/** The sidebar's own buttons, the same in every app: the menu button slides it over the page, the dimmed page and
    choosing a row put it away (while it is not docked), and a window resized docks or undocks it. `rows`: which rows
    put it away (ioCalendar keeps its calendar links from doing so). Escape stays with the app: what it answers to
    first differs (a menu, a dialog, then the sidebar). */
export function wireSidebar(store, { rows = 'a' } = {}) {
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest(rows) && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', () => applySidebar(store));
  applySidebar(store);
}
/** What #sidebtn does: put a docked sidebar away, dock it on a wide screen, close it on a narrow one. */
export function sidebarButton(store) {
  if (document.body.classList.contains('side-docked')) store.set('sidebar', '0');
  else if (innerWidth >= DOCK_MIN) store.set('sidebar', '1');
  else { closeNav(); return; }
  applySidebar(store);
}

// ------------------------------------------------------------------ the sidebar's parts
/** The pieces every app's sidebar is made of, so each app writes only its own rows:

      const { head, link, sec, fold, shown, gap, more } = frame.navParts(store, { name: 'Docs', title: 'All documents', redraw: drawNav });
      $('#nav').replaceChildren(...[head(), link('all', '#/', 'box', 'Everything', 12, r.view === 'all', '--c-blue'), more(moreSheet)]);

    `store` is what this browser remembers for the app (which sections are folded away); `name` follows "io" in the
    wordmark; `home` and `title` are the link on it; `redraw` is the app's own drawNav, called when a section is
    folded or unfolded; `suite` says whether the other apps' menu is offered. */
export function navParts(store, { name, home = '#/', title = '', redraw = () => {}, suite: hasSuite = () => suite.items.length }) {
  const folded = new Set((store.get('navfold') || '').split(',').filter(Boolean));
  const turn = (key) => { folded.has(key) ? folded.delete(key) : folded.add(key); store.set('navfold', [...folded].join(',')); redraw(); };
  const mark = () => h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' });
  const word = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, name)];
  return {
    folded,
    /** A row: its view, where it goes, its icon, its label, a count, whether it is the one shown, its colour (a
        --c-* token or a colour of its own) and how far it is indented. */
    link: (v, href, ic, label, n, on, hue, depth) => h('a', { href, 'data-v': v, class: on ? 'on' : null,
      style: { ...(hue ? { '--hue': String(hue).startsWith('--') ? `var(${hue})` : hue } : {}), ...(depth ? { paddingLeft: `${12 + depth * 14}px` } : {}) } },
      icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null),
    /** A heading over a group of rows, with a button of its own at the end (a new list, a new cookbook). */
    sec: (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null),
    /** A heading whose group folds away, remembered on this device; folded, it says how many it holds. */
    fold: (key, label, n, btn) => h('div', { class: `navsec${folded.has(key) ? ' folded' : ''}` },
      h('button', { class: 'fold', 'aria-expanded': String(!folded.has(key)), title: folded.has(key) ? `Show the ${label.toLowerCase()}` : `Fold the ${label.toLowerCase()} away`,
        onclick: () => turn(key) }, icon('next', 's'), h('span', null, label), folded.has(key) && n ? h('span', { class: 'fn' }, n) : null), btn || null),
    /** What a folded group still shows: the row you are on. */
    shown: (key, list, on) => (folded.has(key) ? list.filter(on) : list),
    /** The space between two groups. */
    gap: () => h('div', { class: 'navgap' }),
    /** The top: the app's mark (the suite's menu where other apps are there), its name, and the sidebar's button. */
    head: () => h('div', { class: 'navhead' },
      hasSuite()
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioSuite apps', 'aria-label': 'ioSuite apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) }, mark()),
          h('a', { class: 'brand-name', href: home, title: title || null }, word()))
        : h('a', { class: 'brand', href: home, title: title || null }, mark(), h('span', { class: 'brand-name' }, word())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: () => sidebarButton(store) })),
    /** The More row, which opens the rest on a phone's bottom bar. */
    more: (onclick, label = 'More') => h('button', { class: 'navmore', 'data-v': 'more', title: label, onclick }, icon('more'), h('span', { class: 'nl' }, label)),
  };
}

// ------------------------------------------------------------------ the theme
// One appearance choice for the whole suite: it is kept with the account, so every app and every browser follows it,
// and mirrored under one key here so a page draws in it at once (api/auth/theme.js, before any module loads).
const THEME_KEY = 'iosuite.theme';
export const themeChoice = () => { try { return localStorage.getItem(THEME_KEY) || 'system'; } catch { return 'system'; } };
/** The appearance: the device's unless light or dark was chosen. With `choice`, that becomes the suite's choice (kept
    in this browser and, when somebody is signed in, with the account; `save: false` leaves the saving to the caller). */
export function applyTheme(choice, { save = true } = {}) {
  if (choice) {
    try { localStorage.setItem(THEME_KEY, choice); } catch { /* private mode */ }
    if (save) fetch(new URL('api/auth/settings', document.baseURI).href,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme: choice }) }).catch(() => { /* not signed in */ });
  }
  const t = choice || themeChoice();
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}
/** The choice the account carries (/api/auth/me settings.theme), taken as a page loads: one made in another app, or
    in another browser, takes hold here too. */
export function themeFromAccount(settings) {
  const t = (settings || {}).theme;
  if (t && t !== themeChoice()) { try { localStorage.setItem(THEME_KEY, t); } catch { /* private mode */ } }
  applyTheme();
}

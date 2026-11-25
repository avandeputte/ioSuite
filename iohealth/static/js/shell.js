import { $, TZ, route } from './core.js';
import { authApi, signIn } from './accounts.js';
import * as frame from '../../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { addIcons, applyTheme, dialog, icon, paintIcons, themeChoice, themeFromAccount, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
export { applyTheme, dialog, h, icon, themeChoice, themeFromAccount, toast };  // the appearance is the suite's one choice
const store = frame.storeFor('iohealth');  // what this browser remembers for the app (the sidebar)

// ---------- the sidebar: the pages in groups, Settings at the foot (the suite's parts, the same in every app) ----------

// ioHealth's own icons, beside the ones every app's page has (frame.ICONS)
addIcons({
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  calendar: 'M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V9h14v11z',
  chart: 'M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z',
  scatter: 'M7 10c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3zm8.01 3c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-.01-3c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z',
  run: 'M13.49 5.48c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm-3.6 13.9l1-4.4 2.1 2v6h2v-7.5l-2.1-2 .6-3c1.3 1.5 3.3 2.5 5.5 2.5v-2c-1.9 0-3.5-1-4.3-2.4l-1-1.6c-.4-.6-1-1-1.7-1-.3 0-.5.1-.8.1l-5.2 2.2v4.7h2v-3.4l1.8-.7-1.6 8.1-4.9-1-.4 2 7 1.4z',
  map: 'M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z',
  trophy: 'M19 5h-2V3H7v2H5c-1.1 0-2 .9-2 2v1c0 2.55 1.92 4.63 4.39 4.94.63 1.5 1.98 2.63 3.61 2.96V19H7v2h10v-2h-4v-3.1c1.63-.33 2.98-1.46 3.61-2.96C19.08 12.63 21 10.55 21 8V7c0-1.1-.9-2-2-2zM5 8V7h2v3.82C5.84 10.4 5 9.3 5 8zm14 0c0 1.3-.84 2.4-2 2.82V7h2v1z',
  bed: 'M7 13c1.66 0 3-1.34 3-3S8.66 7 7 7s-3 1.34-3 3 1.34 3 3 3zm12-6h-8v7H3V5H1v15h2v-3h18v3h2v-9c0-2.21-1.79-4-4-4z',
  drop: 'M12 2c-5.33 4.55-8 8.48-8 11.8 0 4.98 3.8 8.2 8 8.2s8-3.22 8-8.2c0-3.32-2.67-7.25-8-11.8z',
  pill: 'M4.22 11.29l5.07-5.07a5.003 5.003 0 0 1 7.07 0 5.003 5.003 0 0 1 0 7.07l-5.07 5.07a5.003 5.003 0 0 1-7.07 0 5.003 5.003 0 0 1 0-7.07zm1.42 1.42a2.98 2.98 0 0 0 0 4.24 2.98 2.98 0 0 0 4.24 0l2.12-2.12-4.24-4.24-2.12 2.12z',
  badge: 'M20 4H4c-1.11 0-2 .89-2 2v12c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm-9 12H8v-3H5v-3h3V7h3v3h3v3h-3v3zm8-1h-4v-2h4v2zm0-4h-4V9h4v2z',
});
paintIcons();

// The pages, in the sidebar's order: [page, label, icon, hue]. A gap and a heading start each group; Settings and
// sits at the foot. On phones the bottom bar shows the first four and the rest open from More.
export const NAV = [
  ['dashboard', 'Dashboard', 'dashboard', 'purple'], ['day', 'Day', 'calendar', 'amber'], ['metrics', 'Metrics', 'chart', 'blue'], ['workouts', 'Workouts', 'run', 'orange'],
  ['correlations', 'Correlations', 'scatter', 'teal'], ['map', 'Map', 'map', 'cyan'], ['records', 'Records', 'trophy', 'green'],
  ['sleep', 'Sleep', 'bed', 'indigo'], ['glucose', 'Glucose', 'drop', 'rose'], ['medicines', 'Medicines', 'pill', 'green'], ['emergency', 'Emergency card', 'badge', 'rose'],
];
export const NAV_GROUPS = { correlations: 'Analysis', sleep: 'Health' };  // the first page of each group after the first
export const NAV_FOOT = [['settings', 'Settings', 'settings', 'slate']];
export const PHONE_BAR = ['dashboard', 'day', 'metrics', 'workouts'];
export const navLink = ([page, label, ic], link) => link(page, page === 'dashboard' ? '#/' : `#/${page}`, ic, label, null, false);
export const pageTitle = (ic, hue, ...kids) => h('h1', { class: 'ptitle', style: { '--hue': `var(--c-${hue})` } }, h('span', { class: 'pic' }, icon(ic)), ...kids);

export function buildNav() {
  // the sidebar's parts, the same in every app (iosuite_shared/static/frame.js); below them, ioHealth's own rows
  const { head, link, sec, gap, more } = frame.navParts(store, { name: 'Health', title: 'Dashboard', redraw: buildNav });
  $('#nav').replaceChildren(...[
    head(),
    NAV.map((n) => [NAV_GROUPS[n[0]] ? [gap(), sec(NAV_GROUPS[n[0]])] : null, navLink(n, link)]),
    more(moreSheet),
    h('div', { class: 'navfoot' }, ...NAV_FOOT.map((n) => navLink(n, link)), h('div', { class: 'ver', id: 'nav-version' })),
  ].flat(3).filter(Boolean));
  $('#sidebtn').onclick = () => frame.sidebarButton(store);
  frame.wireSidebar(store);
  setNavOn(route().page === 'workout' ? 'workouts' : route().page);
}

/* The suite (iosuite_shared's suite_apps): when other ioSuite apps are registered, the app mark top left (in the
   sidebar; in the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link
   to the Dashboard. */
export async function loadSuite() { await frame.loadSuite(authApi); buildNav(); }

/** Phones: the bottom bar shows four pages; the rest, with Settings, open from More. */
export function moreSheet() {
  const current = route().page === 'workout' ? 'workouts' : route().page;
  const rest = [...NAV.filter(n => !PHONE_BAR.includes(n[0]) && !$(`#nav a[data-v="${n[0]}"]`)?.hidden), ...NAV_FOOT];
  const grid = h('div', { class: 'sheetgrid' }, rest.map(([page, label, ic, hue]) => h('a', { href: `#/${page}`, class: current === page ? 'on' : null, style: { '--hue': `var(--c-${hue})` } },
    h('span', { class: 'sic' }, icon(ic)), label)));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) frame.closeDialogs(); });
  return p;
}

export function setNavOn(page) {
  const inBar = !!$(`#nav a[data-v="${page}"]`);
  for (const a of document.querySelectorAll('#nav a')) a.classList.toggle('on', a.dataset.v === page);
  $('#nav .navmore')?.classList.toggle('on', !inBar || (!PHONE_BAR.includes(page) && innerWidth <= 800));
}

export const settings = (() => {
  const defaults = { units: 'auto', maxHr: '', glucoseUnit: '', glucoseLow: '70', glucoseHigh: '180', hiddenSections: [], hiddenTypes: [] };
  try { return Object.assign(defaults, JSON.parse(localStorage.getItem('iohealth.settings') || '{}')); } catch { return defaults; }
})();
// Settings live in the database (hlt_user_settings), shared by every browser; the copy in localStorage makes the
// first page draw right before the server answers. The appearance is not here: it is the suite's one choice, kept
// with the account (api/auth/frame.js).
export let settingsTimer;
export function saveSettings() {
  try { localStorage.setItem('iohealth.settings', JSON.stringify(settings)); } catch { /* private mode */ }
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(() => fetch('api/settings', { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings) }).catch(e => console.error('saving settings', e)), 300);
}
export async function loadSettings() {
  try {
    const r = await fetch('api/settings', { credentials: 'same-origin' });
    if (r.status === 401) { signIn(); return; }
    const stored = await r.json();
    if (Object.keys(stored).length) Object.assign(settings, stored);
    else saveSettings(); // first run: keep what this browser had
  } catch (e) { console.error('loading settings', e); }
}

export const apiCache = new Map();
export let inflight = 0;
// whenIdle resolves once no API request has been running for a moment (the page has drawn what it loads).
export async function whenIdle(quiet = 400, max = 15000) {
  const end = Date.now() + max;
  let calm = 0;
  while (Date.now() < end && calm < quiet) { await new Promise(r => setTimeout(r, 50)); calm = inflight ? 0 : calm + 50; }
}
export async function api(path, params = {}, { cache = true } = {}) {
  const q = new URLSearchParams({ ...params, tz: TZ });
  if (settings.maxHr) q.set('maxHr', settings.maxHr);
  const url = 'api/' + path + '?' + q;
  if (cache && apiCache.has(url)) {
    const hit = apiCache.get(url);
    if (Date.now() - hit.at < 60000) return hit.promise;
  }
  inflight++;
  const promise = fetch(url, { credentials: 'same-origin' }).then(async r => {
    if (r.status === 401) { signIn(); throw new Error('not signed in'); }
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || body.detail || r.statusText);
    return body;
  }).finally(() => { inflight--; });
  apiCache.set(url, { at: Date.now(), promise });
  promise.catch(() => apiCache.delete(url));
  return promise;
}

/* The start page itself: the top row, the search box, the apps' tiles, the cards. */
import { h } from '../../api/auth/ui.js';
import { api, dayKey, S } from './core.js';
import { badgeRow, refreshBadges } from './badges.js';
import { capAgenda, drawBirthdays, drawBookmarks, drawStrip, drawWeather, drawWeek } from './cards.js';
import { arrangeBar, arrangeGo, arrangeRedraw, arrangeStart, arrangeWire, arrMark, customize } from './customize.js';
import { drawGrid, gridFrom } from './grid.js';
import { drawHomeCard, haSubscribe } from './homeassistant.js';
import { onRoute } from './main.js';
import * as news from './news.js';
import { pageId, pageTabs, pageView, putPage, swipePages } from './pages.js';
import { searchBox } from './search.js';
import { userMenu } from './shell.js';
import { arrangeTiles, askAgain, drawGlance, drawWidgets, EMPTY, fitStack, LOW, quietKeys, quietTile, tileOf, WIDGETS } from './tiles.js';
import { timersBlock } from './timers.js';
import { usesHa, whenOk } from './when.js';

// ------------------------------------------------------------------ the start page
const greeting = () => { const hr = new Date().getHours(); return hr < 5 ? 'Good night' : hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening'; };

/* ---- the person's setup (iostart/layout.py): this device's own when it has one, else the account's, else the family's */
export const NO_LAYOUT = () => ({ hidden: [], order: [], cards: [], strip: null, sizes: {}, todayOff: [], grid: null, whens: {}, badges: [], name: null, pages: [] });
/** The id this browser keeps for itself once the person gives the device a setup of its own ('' until then). */
export const deviceId = () => { try { return localStorage.getItem('iostart.device') || ''; } catch { return ''; } };
export function newDeviceId() {
  const a = new Uint8Array(12); crypto.getRandomValues(a);
  const id = [...a].map((b) => (b % 36).toString(36)).join('');
  localStorage.setItem('iostart.device', id);  // throws in a private window: the caller says so
  return id;
}
/** "iPhone", "Mac", "Windows PC": a first name for this device, for the person to change. */
export function deviceGuess() {
  const ua = navigator.userAgent || '';
  if (/iPhone/.test(ua)) return 'iPhone';
  if (/iPad/.test(ua) || (/Mac/.test(navigator.platform || '') && navigator.maxTouchPoints > 1)) return 'iPad';
  if (/Android/.test(ua)) return /Mobile/.test(ua) ? 'Android phone' : 'Android tablet';
  if (/Mac/.test(navigator.platform || ua)) return 'Mac';
  if (/Win/.test(navigator.platform || ua)) return 'Windows PC';
  if (/CrOS/.test(ua)) return 'Chromebook';
  return 'Computer';
}
/** /api/apps for this device: the tiles, and the setup the page is drawn from (S.layoutOf: where it comes from). */
export async function loadApps() {
  const dev = deviceId();
  const got = await api(`api/apps${dev ? `?device=${encodeURIComponent(dev)}` : ''}`);
  got.layout = { ...NO_LAYOUT(), ...(got.layout || {}) };
  S.layoutOf = got.layoutOf || { scope: 'none', device: null, devices: [], family: false };
  S.full = got.layout; S.allApps = got.items; S.photoStrip = got.photoStrip;  // Customize works from these, on any view
  applyLook(got.layout);
  return got;
}
/** Keeps a setup where the page's came from: this device's own when it has one (or `to`: {id, name}), else the account's. */
export function saveLayout(json, to = S.layoutOf && S.layoutOf.scope === 'device' ? S.layoutOf.device : null) {
  return api(`api/me/layout${to ? `?${new URLSearchParams({ device: to.id, name: to.name || '' })}` : ''}`, { method: 'PUT', json });
}
/** The page's colour and the size of its type (layout accent, text): on the document, and kept in this browser so the
    next visit draws in them at once (static/js/look.js). */
export function applyLook(L) {
  const d = document.documentElement.dataset, look = { accent: (L && L.accent) || '', text: (L && L.text) || '' };
  if (look.accent) d.accent = look.accent; else delete d.accent;
  if (look.text) d.text = look.text; else delete d.text;
  try { if (look.accent || look.text) localStorage.setItem('iostart.look', JSON.stringify(look)); else localStorage.removeItem('iostart.look'); } catch { /* private mode */ }
}
/** How an app stands in the layout with a card for each: 'card' (always), 'tile' (always low), '' (by itself). */
export const sizeOf = (key, L = S.layout) => (L && L.sizes && L.sizes[key]) || '';
export const TOP_PARTS = { greeting: 'The greeting', search: 'The search box', weather: 'The weather' };
export const CARD_NAMES = { home: 'Home (Home Assistant)', birthdays: 'Birthdays (ioContact)', week: 'This week (ioCalendar)', strip: 'The photo strip (ioPix)', news: 'Headlines (your feeds)', bookmarks: 'Bookmarks' };

/* The setup holds one page or several (static/js/pages.js): S.full is all of it, S.pid the page shown ('' the first)
   and S.layout that page as it is drawn: the person's own part (the colour, the units, the photos) with what the page
   holds by itself (its layout, its tiles and cards, its badges). */
export async function showHome(page, r = {}) {
  const got = S.arrange && S.arrange.got ? S.arrange.got : await loadApps();
  // the viewer's own layout (Customize the page) on top of the admin's: tiles and cards hidden, tiles in their order;
  // while the page is being arranged (arrangeStart), the copy being worked on, not saved yet
  if (S.arrangeNext) {
    S.arrangeNext = false;
    const full = JSON.parse(JSON.stringify(got.layout)), pid = pageId(full, r.page);
    S.arrange = { full, pid, L: pageView(full, pid), was: JSON.stringify(full), seen: new Map() };
  }
  const A = S.arrange;
  if (A) A.got = got;
  document.body.classList.toggle('arranging', !!A);
  const full = S.full = A ? A.full : got.layout, pid = S.pid = A ? A.pid : pageId(full, r.page);
  const L = S.layout = A ? A.L : pageView(full, pid);
  S.photoStrip = got.photoStrip;  // the admin's choice, what Customize calls "as the admin set it"
  S.allApps = got.items;
  const rank = (a) => { const i = L.order.indexOf(a.key); return i < 0 ? 100 + got.items.indexOf(a) : i; };
  // the admin tools (ioDNS…) are not tiles: the gear menu lists them
  S.apps = got.items.filter((a) => !a.adminTool && !L.hidden.includes(a.key)).sort((a, b) => rank(a) - rank(b));
  // the person's own grid (static/js/grid.js); the first time, the page as it was, block for block
  const own = L.style === 'grid';
  if (own && !L.grid) L.grid = gridFrom({ ...L, style: null }, got.photoStrip);
  // "show when" (static/js/when.js): a rule on a tile, a card, a part of the top row, a badge, a block, a section or a
  // page's tab. While the page is arranged everything shows, to be moved and changed
  const whens = L.whens || {}, rules = A ? [] : [...Object.values(whens), ...(L.badges || []).map((b) => b.when), ...(full.pages || []).map((p) => p.when),
    ...(own ? L.grid.sections.flatMap((s) => [s.when, ...s.blocks.map((b) => b.when)]) : [])].filter(Boolean);
  if (rules.some(usesHa) && S.ha == null) { try { const d = await api('api/ha'); S.ha = d.enabled ? d : false; } catch { S.ha = false; } }
  const shows = (k) => !L.hidden.includes(k) && (A || whenOk(whens[k]));
  const onlyWith = (k) => !A && whens[k] && whens[k].content;  // off the page until it has something to say
  const first = (S.user.displayName || S.user.name).split(/\s+/)[0];
  // the top row: the greeting, the search box and the weather, each there unless the person took it off (the date and
  // the gear stay: the way back to Customize)
  const wx = shows('weather') ? arrMark(h('div', { class: 'weather' }), 'top', 'weather', TOP_PARTS.weather) : null;
  const hello = shows('greeting') ? arrMark(h('h1', { class: 'greet' }, `${greeting()}, ${first}`), 'top', 'greeting', TOP_PARTS.greeting) : null;
  S.focusSearch = null;
  const search = shows('search') ? arrMark(searchBox(), 'top', 'search', TOP_PARTS.search) : null;
  if (A) page.append(arrangeBar());
  page.append(h('div', { class: 'top' }, h('div', { class: 'hello' }, hello,
    h('div', { class: 'dateline' }, h('span', { class: 'muted' }, new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })), userMenu())), search, wx));
  // under it: a tab for each page when there are several, and the page's badges
  const tabs = pageTabs(full, pid, A ? { A, go: arrangeGo, redraw: arrangeRedraw, commit: () => putPage(A.full, A.pid, A.L) } : {});
  const badges = badgeRow(L, { A, redraw: arrangeRedraw });
  if (tabs) page.append(tabs);
  if (badges) page.append(badges);
  // under the greeting: a column for the tiles and the cards and, on a wide screen, the bookmarks in a column of their
  // own on the right (when they come last, as by default); narrower, the side column simply follows the main one
  const col = h('div', { class: 'homecol' }), side = h('div', { class: 'homeside' });
  page.append(timersBlock(), h('div', { class: 'homegrid' }, col, side));
  if (wx) drawWeather(wx);  // fills in when AccuWeather (or the server's copy) answers
  let glance = null, grid = null;
  if (own) {
    page.classList.add('gridpage'); page.classList.toggle('g4', (L.grid.cols || 3) > 3);
    grid = drawGrid(col, { L, A, page, redraw: arrangeRedraw, strip: got.photoStrip, arrange: arrangeStart });
  } else {
    glance = drawClassic({ page, col, side, got, L, A, shows, onlyWith });
    drawWidgets(page);
  }
  drawAppStatus(page);
  if (A) { arrangeWire(page); return; }  // a page being arranged stays as it is until Done
  swipePages(page, full, pid);
  // live refresh: every few minutes, and on coming back to the tab, the page brings itself up to date in place
  S.shownDay = dayKey(); S.refreshedAt = Date.now();
  S.refresh = () => {
    askAgain();
    const g = page.querySelector('.greet'); if (g) g.textContent = `${greeting()}, ${first}`;
    drawAppStatus(page); if (wx) drawWeather(wx, true);
    refreshBadges(page);
    if (grid) { grid.refresh(); return; }
    drawWidgets(page, true);
    if (glance) drawGlance(glance, true);
    for (const c of page.querySelectorAll('.card.birthdays.capped')) drawBirthdays(c, true);
    for (const c of page.querySelectorAll('.card.week.capped')) drawWeek(c, true);
    const hc = page.querySelector('.homecard'); if (hc) drawHomeCard(hc, true);
    const bm = page.querySelector('.bookmarks'); if (bm) drawBookmarkStatus(bm);
    const nc = page.querySelector('.newscard'); if (nc) news.drawNewsCard(nc);
  };
  // the rules are looked at again each minute, when the window changes its size and when Home Assistant says something
  // changed (static/js/main.js); the page is drawn anew only when one of them turned
  if (rules.length) {
    const now = () => rules.map((w) => (whenOk(w) ? 1 : 0)).join('');
    const was = now();
    S.whenCheck = () => {
      if (!page.isConnected || S.arrange || now() === was || document.querySelector('.dialog-back')) return;
      if (document.activeElement && document.activeElement.matches('input, textarea, select')) return;  // not under someone's typing: the next look
      onRoute();
    };
    if (rules.some(usesHa)) haSubscribe(() => S.whenCheck && S.whenCheck());
  }
}

/** The page as it lays itself out (the styles "cards" and "today"): the apps' tiles, and the cards under them. Gives
    back the Today card's element when the page has one. */
function drawClassic({ page, col, side, got, L, A, shows, onlyWith }) {
  // the tiles, as the person laid the page out (Customize › Layout):
  // "cards": an app with something to show gets a card, as many across as fit at a width its lines can be read in; the
  //   others are low tiles that share one cell (arrangeTiles). A card with nothing to show today turns into a low tile
  //   with one line ("Nothing planned"), and back when it has something again (drawWidgets); unless the person fixed
  //   its size (layout sizes): always a card, or always a low tile with one line of what the card would say.
  // "today": every app in one row to open it (the dock), and under it what the day holds in a few cards (drawGlance)
  // a low tile of an app in LOW gets one line under its name (ioDocs: what is to renew)
  const tile = (a, small) => arrMark(tileOf(a, small), 'tile', a.key, a.name);
  const tiles = S.apps.filter((a) => shows(a.key));  // a tile a rule keeps off for now: its app is still the page's
  let glance = null;
  if (!S.apps.length) col.append(h('div', { class: 'empty' }, got.items.length ? 'Every tile is hidden. ' : 'No io app has registered itself in the Shared ioSuite database yet: each one appears here once it has started.',
    got.items.length && !A ? h('button', { class: 'lnk', onclick: () => customize('apps') }, 'Customize the page') : null));
  else if (L.style === 'today') {
    glance = h('div', { class: 'glance' });
    const dock = h('div', { class: 'dock' }, tiles.map((a) => tile(a, true)));
    col.append(dock, glance);
    // one row when the tiles fit at 92px or more, else rows of the same length (ten apps: five and five, not seven and three)
    const fit = () => { const most = Math.max(1, Math.floor((dock.clientWidth + 8) / 100)), rows = Math.ceil(tiles.length / most); dock.style.setProperty('--per', Math.ceil(tiles.length / Math.max(1, rows)) || 1); };
    new ResizeObserver(fit).observe(dock); fit();
    drawGlance(glance);
  } else {
    // a card that had nothing to show the last time starts as a low tile, so the page does not jump when it loads
    const was = quietKeys(), apps = h('div', { class: 'apps' }, tiles.map((a) => {
      const size = WIDGETS[a.key] ? sizeOf(a.key) : 'tile';  // an app with nothing to show here is a low tile, whatever is asked
      const low = size ? size === 'tile' : !!(LOW[a.key] || was.includes(a.key)), el = tile(a, low);
      if (low && !size && !LOW[a.key]) quietTile(el, EMPTY[a.key]);
      if (onlyWith(a.key)) el.onquiet = (q) => { el.hidden = q; fitStack(apps); };
      return el;
    }));
    col.append(apps);
    arrangeTiles(apps);
    new ResizeObserver(() => fitStack(apps)).observe(apps);
  }
  // the week ahead: birthdays from ioContact and the coming days' events from ioCalendar, a card each
  // the cards under the tiles, in the viewer's order (Customize); Birthdays and This week share a row when they follow
  // each other, else each stands on its own
  const has = (k) => S.apps.some((a) => a.key === k);
  S.birthdaysCard = shows('birthdays') && has('iocontact');  // then the calendar leaves birthdays to it
  const stripKind = L.strip || got.photoStrip;
  const card = (k, cls, draw) => () => { const c = arrMark(h('div', { class: cls }), 'card', k, CARD_NAMES[k]); draw(c); return c; };
  const cards = {
    home: shows('home') ? () => { const c = arrMark(h('div', { class: 'card homecard', hidden: true }), 'card', 'home', CARD_NAMES.home); drawHomeCard(c); return c; } : null,
    birthdays: S.birthdaysCard ? card('birthdays', 'card capped birthdays', drawBirthdays) : null,
    week: shows('week') && has('iocalendar') ? card('week', 'card capped week', drawWeek) : null,
    strip: shows('strip') && stripKind !== 'off' && has('iopix') ? card('strip', 'strip', (c) => drawStrip(c, stripKind)) : null,
    news: shows('news') ? () => { const c = arrMark(h('div', { class: 'card newscard', hidden: !A }), 'card', 'news', CARD_NAMES.news); news.drawNewsCard(c, !!A); return c; } : null,  // there once the person follows a feed
    bookmarks: shows('bookmarks') ? card('bookmarks', 'bookmarks', drawBookmarks) : null,
  };
  // a card with the rule "only while it has something to show" stays off the page until it says it has (core.js quiet)
  const make = (k) => {
    const c = cards[k]();
    if (onlyWith(k)) { c.hidden = true; c.onquiet = (q, gone) => setTimeout(() => { if (c.isConnected) c.hidden = q || gone; }, 0); }
    return c;
  };
  let agenda = null;
  const order = cardOrder(L).filter((k) => cards[k]);
  for (const k of order) {
    if (k === 'bookmarks' && k === order[order.length - 1]) { side.append(make(k)); continue; }
    if (k === 'birthdays' || k === 'week') {
      if (!agenda || !agenda.isConnected || agenda !== col.lastElementChild) { agenda = h('div', { class: 'agenda' }); col.append(agenda); capAgenda(page.querySelector('.apps, .glance'), agenda); }
      agenda.append(make(k));
    } else col.append(make(k));
  }
  return glance;
}

// ------------------------------------------------------------------ the cards there are, the styles of the page
export const CARDS = ['home', 'birthdays', 'week', 'strip', 'news', 'bookmarks'];
// how the apps are laid out (Customize › Layout; layout.style, null: cards)
export const STYLES = { cards: 'A card for each app', today: 'One Today card, the apps in a row', grid: 'My own grid: blocks where I put them' };
/** The cards' order: the viewer's, then any the viewer's list does not name, in the usual order. */
export const cardOrder = (L) => [...(L.cards || []), ...CARDS.filter((k) => !(L.cards || []).includes(k))];

// ------------------------------------------------------------------ a dot by each app and by each bookmark: does it answer?
async function drawAppStatus(page) {
  let d;
  try { d = await api('api/apps/status'); } catch { return; }
  if (!page.isConnected) return;
  for (const [key, s] of Object.entries(d.items || {})) {
    // an app can stand on the page more than once (the person's own grid: its card, and its tile in a row of apps)
    for (const st of page.querySelectorAll(`.app[data-app="${key}"] .st`)) st.replaceChildren(h('span', { class: `dot ${s.ok ? 'ok' : 'down'}`, title: s.ok ? `Up${s.version ? ` · v${s.version}` : ''}` : `Not reachable${s.why ? `: ${s.why}` : ''}` }));
  }
}
/** The bookmarks the server could not reach get a red dot and a tooltip. */
export async function drawBookmarkStatus(el) {
  let d;
  try { d = await api('api/bookmarks/status'); } catch { return; }
  if (!el.isConnected) return;
  for (const a of el.querySelectorAll('.bm[data-id]')) {
    const s = d.items[a.dataset.id];
    if (!s) continue;
    a.classList.toggle('down', s.ok === false);
    const what = `${a.dataset.name ? `${a.dataset.name}\n` : ''}${a.getAttribute('href')}`;  // with icons alone, the name is in the tooltip
    a.title = s.ok === false ? `${what}\nNot reachable${s.status ? ` (${s.status})` : ''}` : what;  // set afresh: the live refresh draws this again and again
  }
}

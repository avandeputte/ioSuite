/* The routes, keeping the page fresh while it stays open, the note of a newer version, and the start. */
import { confirmDialog, fail, icon } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { $, api, BM_APP, dayKey, S, showSignIn } from './core.js';
import { showBookmarks } from './bookmarks.js';
import { showHome } from './home.js';
import { haStreamStop } from './homeassistant.js';
import * as news from './news.js';
import { showSettings } from './settings.js';
import { applyTheme, drawUser, setTheme, userMenu } from './shell.js';
import { showPair, showWall } from './wall.js';

// ------------------------------------------------------------------ routes
export function route() {
  const [a, b, c] = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  if (a === 'bookmarks' || (a === 'settings' && b === 'bookmarks')) return { view: 'bookmarks' };
  if (a === 'news') return { view: 'news', b, c };  // the reader (static/js/news.js)
  if (a === 'wall') return { view: 'wall' };
  if (a === 'pair') return { view: 'pair', code: b || '' };
  if (BM_APP && !a) return { view: 'bookmarks' };  // the Bookmarks app opens on them
  return { view: 'home' };
}
export async function onRoute() {
  const r = route();
  const page = h('div', { class: 'page' });
  // the start page has no top bar: the account menu sits in its first row instead (showHome moves it there)
  document.body.classList.toggle('home', r.view === 'home');
  document.body.classList.toggle('wall', r.view === 'wall');
  S.refresh = null; S.shownDay = null;  // the view drawn next says how it refreshes itself (liveRefresh)
  if (r.view !== 'home') { S.arrange = null; S.arrangeNext = false; document.body.classList.remove('arranging'); }  // arranging is the start page's: going elsewhere drops what was not saved
  if (S.wallStop) { S.wallStop(); S.wallStop = null; }
  haStreamStop();  // the view opens its own stream of Home Assistant changes when it needs one
  $('#topbar').append(userMenu());  // out of the old page before it goes; showHome takes it into the new one
  $('#main').replaceChildren(page);
  try { await ({ home: showHome, settings: showSettings, wall: showWall, bookmarks: showBookmarks, pair: showPair, news: news.showNews })[r.view](page, r); } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ live refresh
/* A start page stays open all day: every five minutes (and when the tab is shown again) the view on screen brings
   itself up to date in place (S.refresh: the tiles' widgets, the weather, the cards, the dots), without a flicker; at
   midnight the whole page is drawn anew, for the new day's greeting, date, On this day and birthdays. Nothing runs
   while the tab is hidden, a dialog is open, or someone is typing in the search box. */
const REFRESH_EVERY = 5 * 60 * 1000;
export function liveRefresh(force = false) {
  if (document.hidden || !S.refresh || document.querySelector('.dialog-back')) return;
  if (S.shownDay && S.shownDay !== dayKey()) { onRoute(); return; }
  const typing = document.activeElement && document.activeElement.matches('input, textarea, select');
  if (typing || (!force && Date.now() - (S.refreshedAt || 0) < REFRESH_EVERY)) return;
  S.refreshedAt = Date.now();
  try { S.refresh(); } catch { /* the next round */ }
}

// ------------------------------------------------------------------ settings › server (admins)
/* The server panel every io app shares (iosuite_shared /api/server/ui.js): version and updates,
   the server log and Restart. */

/** Suite admins: one note when a newer version of the suite is out (every app has the same one), with Update now.
 *  Hidden until the next version when dismissed. The details are Settings › Servers › Updates. */
async function updateNote() {
  if (!S.user || !S.user.suiteAdmin) return;
  let u;
  try { u = await api('api/suite-admin/updates'); } catch { return; }
  $('#updnote')?.remove();
  let dismissed = null; try { dismissed = localStorage.getItem('iostart.updateDismissed'); } catch { /* private mode */ }
  if (u.status !== 'update' || !u.latest || dismissed === u.latest) return;
  const page = '#/settings/apps/updates';
  const b = h('div', { id: 'updnote', role: 'status' }, icon('update'),
    h('span', null, `ioSuite v${u.latest} is available (now v${u.installed || '?'}).`),
    u.canUpdate ? h('button', { class: 'pillbtn primary noic', onclick: async () => {
      if (!await confirmDialog(`Update to v${u.latest}`, 'Update every app and restart them? Each one is away for a moment.', 'Update now')) return;
      try { await api('api/suite-admin/updates', { method: 'POST', json: { action: 'update' } }); } catch (e) { fail(e); return; }
      b.remove(); location.hash = page;
    } }, 'Update now') : null,
    h('a', { class: 'pillbtn noic', href: page, onclick: () => b.remove() }, 'Details'),
    h('button', { class: 'iconbtn', title: 'Not now (hidden until the next version)', onclick: () => { try { localStorage.setItem('iostart.updateDismissed', u.latest); } catch { /* */ } b.remove(); } }, icon('close', 's')));
  document.body.append(b);
}

// ------------------------------------------------------------------ start
async function start() {
  applyTheme();
  S.status = await api('api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  // sent here to sign in by a sync app's "may it sync?" page (iostart/appsignin.py): back to it, now signed in
  const flow = new URLSearchParams(location.search).get('flow');
  if (flow && /^[\w-]{20,}$/.test(flow)) { location.replace('dav/nextcloud/index.php/login/v2/flow/' + flow); return; }
  try { S.settings = (await api('api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme && S.settings.theme !== (localStorage.getItem('iostart.theme') || 'system')) setTheme(S.settings.theme);
  drawUser();
  if (BM_APP) { document.body.classList.add('bmapp'); $('#topbar .brand').href = './'; $('#topbar .brand').title = 'The start page'; }
  addEventListener('hashchange', onRoute);
  await onRoute();
  updateNote();
  document.addEventListener('keydown', (e) => { const b = e.key === 'Escape' ? [...document.querySelectorAll('.dialog-back')].pop() : null; if (b && b.close) b.close(null); else if (b) b.remove(); });
  // ⌘K / Ctrl-K: the search box on the start page (from another view: go there first)
  document.addEventListener('keydown', (e) => {
    if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey) {
      e.preventDefault();
      if (route().view !== 'home') { location.hash = '#/'; setTimeout(() => S.focusSearch && S.focusSearch(), 300); } else if (S.focusSearch) S.focusSearch();
    }
  });
  // back from an app: the page again as it is now (in place); and every few minutes while it stays open (liveRefresh)
  document.addEventListener('visibilitychange', () => liveRefresh(true));
  setInterval(() => liveRefresh(), 60 * 1000);
  // and the moment anything changes in any app of the suite: the one live-refresh stream (iosuite_shared/live.py), so a
  // task ticked off in ioTask or an event moved in ioCalendar shows here at once, without a timer to wait for
  import(new URL('api/live.js', document.baseURI).href)
    .then((live) => live.onChange('*', () => { S.refreshedAt = 0; liveRefresh(true); }, { wait: 700 }))
    .catch(() => { /* no stream on this server: the timer above keeps the page fresh */ });
  setInterval(updateNote, 15 * 60 * 1000);
}
start().catch(fail);

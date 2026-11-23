/* One live-refresh connection per browser, carrying every app's changes (iosuite_shared/live.py).

   A page opens one stream, whatever it wants to watch:

     import { onChange } from './api/live.js';
     onChange(['iocalendar:events', 'iotask:tasks'], () => reload());   // what to watch, what to do
     onChange('*', (c) => console.log(c.app, c.what));                  // everything

   The connection is shared by every onChange of the page, is dropped while the tab is hidden and opened again when
   it comes back, and the browser reconnects by itself if the server restarts. A change made in this very tab is
   heard too, so leave out what the page has already drawn, or pass `mine: false` to ignore changes this tab made.

   What a line says is only which app's what changed, and when: never what changed. A page asks again for what it
   shows, as it would have done on a timer, but only when there is a reason to. */

const WATCHERS = new Set();
let stream = null, last = 0, mineUntil = 0;

/** Watch for changes. `what`: 'app:what', 'app:*', '*', or a list of those. `fn(change)` gets {app, what, at}.
    Options: `mine` (default true; false ignores a change made in this tab, within the last two seconds),
    `wait` (default 400 ms: changes closer together than this call fn once). Returns a function that stops it. */
export function onChange(what, fn, opts = {}) {
  const want = (Array.isArray(what) ? what : [what]).map((s) => String(s));
  const w = { want, fn, mine: opts.mine !== false, wait: opts.wait === undefined ? 400 : opts.wait, timer: null };
  WATCHERS.add(w);
  open();
  return () => { WATCHERS.delete(w); if (w.timer) clearTimeout(w.timer); if (!WATCHERS.size) close(); };
}

/** Say that this tab is making a change right now, so watchers with `mine: false` leave the next moment alone. */
export function mine() { mineUntil = Date.now() + 2000; }

/** The address of the stream, next to the page (so the app's own folder and port are whatever the page's are). */
const url = () => new URL('api/live', document.baseURI).href;

function open() {
  if (stream || !window.EventSource || document.visibilityState === 'hidden') return;
  stream = new EventSource(url());
  stream.addEventListener('change', (e) => {
    let c;
    try { c = JSON.parse(e.data); } catch { return; }
    if (!c || !c.app) return;
    last = c.at || Date.now();
    for (const w of WATCHERS) {
      if (!matches(w.want, c)) continue;
      if (!w.mine && Date.now() < mineUntil) continue;
      if (!w.wait) { w.fn(c); continue; }
      if (w.timer) clearTimeout(w.timer);
      w.timer = setTimeout(() => { w.timer = null; w.fn(c); }, w.wait);
    }
  });
  // the browser reconnects on its own; a stream that errors while the tab is hidden is simply closed
  stream.addEventListener('error', () => { if (document.visibilityState === 'hidden') close(); });
}

function close() {
  if (stream) { stream.close(); stream = null; }
}

function matches(want, c) {
  return want.some((s) => s === '*' || s === `${c.app}:*` || s === c.app || s === `${c.app}:${c.what}`);
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') close();
  else if (WATCHERS.size) open();
});

/* ---- an app's own page, kept up to date --------------------------------------------------------------------------

     import { keepFresh } from './api/live.js';
     keepFresh('iotask', () => refresh(), { when: () => LISTS.includes(route().view) });

   `again()` runs when something of the app changed that this tab did not change itself: a phone that synced, an
   assistant over MCP, another person, another tab. It waits until nothing is in the way, so nobody loses what they
   were doing: the tab is visible, no dialog or photo is open over the page, nothing is being typed, and `when()` (the
   app's own word on whether the open view may be drawn again) says yes. A tab that comes back after a while is
   brought up to date as well, since it heard nothing while it was hidden. */

const OVER = '.dialog-back, .modal-back, [role="dialog"], dialog[open], .lightbox, .signin';
const AWAY_MS = 30000;

function typing() {
  const el = document.activeElement;
  return !!el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable);
}

let watchingOwn = false, own = 0;
/** This tab's own requests that change something count as its own changes (mine()), for as long as they run. */
function watchOwnRequests() {
  if (watchingOwn || !window.fetch) return;
  watchingOwn = true;
  const plain = window.fetch;
  window.fetch = function (input, init) {
    const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    if (method === 'GET' || method === 'HEAD') return plain.apply(this, arguments);
    own += 1;
    mineUntil = Infinity;   // while it runs, however long it takes
    const done = () => { own -= 1; if (own <= 0) { own = 0; mine(); } };
    const p = plain.apply(this, arguments);
    p.then(done, done);
    return p;
  };
}

/** Keep an app's page up to date (see above). Options: `when()` (may the open view be drawn again now?), `also`
    (other apps' changes this page shows, as onChange takes them), `wait` (ms). Returns a function that stops it. */
export function keepFresh(app, again, opts = {}) {
  watchOwnRequests();
  let due = false, timer = null, hiddenAt = 0;
  const inTheWay = () => document.visibilityState === 'hidden' || typing() || !!document.querySelector(OVER) || (opts.when ? !opts.when() : false);
  const run = () => {
    timer = null;
    if (!due) return;
    if (inTheWay()) { timer = setTimeout(run, 1500); return; }
    due = false;
    try { Promise.resolve(again()).catch(() => {}); } catch { /* the page says so itself */ }
  };
  const ask = () => { due = true; if (!timer) timer = setTimeout(run, 0); };
  const seen = () => {
    if (document.visibilityState === 'hidden') { hiddenAt = Date.now(); return; }
    if (hiddenAt && Date.now() - hiddenAt > AWAY_MS) ask();
    hiddenAt = 0;
  };
  document.addEventListener('visibilitychange', seen);
  const stop = onChange([`${app}:*`, ...(opts.also || [])], ask, { mine: false, wait: opts.wait === undefined ? 600 : opts.wait });
  return () => { stop(); document.removeEventListener('visibilitychange', seen); if (timer) clearTimeout(timer); };
}

/** When the page last heard anything, as the server timed it: for a page that wants to know how fresh it is. */
export const heardAt = () => last;

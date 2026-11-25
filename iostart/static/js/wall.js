/* The wall display (#/wall) and a display signing in (#/pair/<code>). */
import { fail, fill, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, dayKey, degF, fmtTemp, itemImage, S, wxIcon } from './core.js';
import { hourRow, nextHours, rainNote, withoutBirthdays, wxImperial } from './cards.js';
import { loadApps, saveLayout } from './home.js';
import { haIcon, haSubscribe } from './homeassistant.js';
import { onRoute } from './main.js';
import { evDay, evTime, inDays, widget } from './tiles.js';
import { timersBlock } from './timers.js';

// ------------------------------------------------------------------ the wall display (#/wall)
/* For a tablet on the wall or a TV: the full screen, ioPix photos one after another behind a big clock, the date, the
   weather and its next hours, and what is planned today and in the coming days (and birthdays). Behind the photos (and
   instead of them without ioPix, or as the person picks: layout wallBg) a sky in the colours of the hour and the weather. It keeps the screen
   on where the browser allows it, refreshes itself (liveRefresh), and goes back to the start page with Escape or the
   button that shows on a touch. #/wall can be the tablet's home address. */
export function enterWall() {
  location.hash = '#/wall';
  const el = document.documentElement;
  if (el.requestFullscreen && !document.fullscreenElement) el.requestFullscreen().catch(() => { /* not allowed here: the page still fills the window */ });
}
export async function showWall(page) {
  const got = await loadApps();
  S.allApps = got.items; S.layout = got.layout;
  S.apps = got.items.filter((a) => !a.adminTool);
  const has = (k) => S.apps.some((a) => a.key === k);
  page.className = 'wallpage';
  const L = got.layout || {};
  const bg = L.wallBg || (has('iopix') ? 'photos' : 'sky');
  const sky = h('div', { class: 'wallsky' }), photos = h('div', { class: 'wallphotos' });
  const clock = h('div', { class: 'wallclock' }), date = h('div', { class: 'walldate' });
  const wx = h('div', { class: 'wallwx' }), hours = h('div', { class: 'wallhours' }), sensors = h('div', { class: 'wallsensors' });
  const agenda = h('div', { class: 'wallagenda' }), caption = h('div', { class: 'wallcap' });
  const bar = h('div', { class: 'wallbar' },
    h('button', { class: 'iconbtn', title: `Background: ${WALL_BGS[bg]} (a tap: the next one)`, onclick: () => wallNextBg(bg, has('iopix')) }, icon('image')),
    h('button', { class: 'iconbtn', title: 'Full screen', onclick: () => { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen().catch(() => {}); } }, icon('fullscreen')),
    h('a', { class: 'iconbtn', title: 'Back to the start page (Esc)', href: '#/' }, icon('close')));
  page.classList.toggle('black', bg === 'black');
  page.append(sky, photos, h('div', { class: 'wallshade' }),
    h('div', { class: 'walltop' }, h('div', null, clock, date), wx),
    h('div', { class: 'wallbottom' }, agenda, h('div', { class: 'wallright' }, timersBlock(true), sensors, hours, caption)), bar);
  // the controls show on a touch or a move of the mouse, and fade after a few seconds
  let hideT;
  const wake = () => { bar.classList.add('on'); clearTimeout(hideT); hideT = setTimeout(() => bar.classList.remove('on'), 4000); };
  page.addEventListener('pointermove', wake); page.addEventListener('pointerdown', wake);
  const tick = () => {
    const n = new Date();
    clock.textContent = n.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    date.textContent = n.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
  };
  tick();
  const timers = [setInterval(tick, 1000)];
  // keep the screen on (Screen Wake Lock: Chrome, Safari 16.4+), asked again when the tab comes back
  let lock = null;
  const keepOn = async () => { try { if (navigator.wakeLock && !document.hidden) lock = await navigator.wakeLock.request('screen'); } catch { lock = null; } };
  let show = null;  // the slideshow's next(), to catch up when the tab comes back
  const onVis = () => { if (!document.hidden) { keepOn(); if (show && !photos.children.length) show(); } };
  document.addEventListener('visibilitychange', onVis); keepOn();
  const onKey = (e) => { if (e.key === 'Escape' && !document.fullscreenElement) location.hash = '#/'; };
  document.addEventListener('keydown', onKey);
  S.wallStop = () => { timers.forEach(clearInterval); clearTimeout(hideT); document.removeEventListener('visibilitychange', onVis); document.removeEventListener('keydown', onKey); if (lock) lock.release().catch(() => {}); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); };
  if (bg === 'photos' && has('iopix')) {
    const every = (WALL_EVERY.includes(L.wallEvery) ? L.wallEvery : WALL_DEFAULT_EVERY) * 1000;
    const ss = wallSlideshow(photos, caption, L.wallPhotos || L.strip || got.photoStrip, every);
    show = ss.next; timers.push(ss.timer);
  }
  const draw = () => { wallWeather(wx, hours, bg === 'black' ? null : sky); wallAgenda(agenda, has); wallSensors(sensors); };
  draw();
  haSubscribe((d) => renderWallSensors(sensors, d));  // the house changes faster than the weather: as it happens
  timers.push(setInterval(() => { if (!document.hidden && !S.haStream) wallSensors(sensors); }, 60 * 1000));
  S.shownDay = dayKey(); S.refreshedAt = Date.now(); S.refresh = draw;
}
/** The Home Assistant entities ticked "wall" (Settings › Home Assistant), name and state each; what needs attention first. */
async function wallSensors(el) {
  let d;
  try { d = await api('api/ha'); } catch { return; }
  renderWallSensors(el, d);
}
function renderWallSensors(el, d) {
  if (!el.isConnected) return;
  if (!d.enabled) { el.replaceChildren(); return; }
  const on = new Set(d.wall || []);
  const items = (d.items || []).filter((t) => on.has(t.id));
  el.replaceChildren(...(d.alerts || []).slice(0, 3).map((a) => h('div', { class: 'wallsensor alert' }, icon('warn', 's'), h('span', { class: 'hname' }, a.name), h('span', { class: 'hstate' }, a.text))),
    ...items.map((t) => h('div', { class: `wallsensor${t.on ? ' on' : ''}` }, icon(haIcon(t), 's'), h('span', { class: 'hname' }, t.name), h('span', { class: 'hstate' }, t.text || t.state))));
}
/** A photo every so often (the person's wallEvery), fading into the next and drifting slowly; landscape ones first on
    a landscape screen. A fresh batch when the row is used up; one that does not load is skipped at once, so the sky
    behind shows only while there is nothing to show. Returns {timer, next}: the interval, for showWall to stop, and
    next, for a tab that comes back. */
function wallSlideshow(el, caption, kind, every) {
  let queue = [], busy = false, empty = 0;
  const fill = async () => {
    const d = await widget('iopix', { kind: !kind || kind === 'off' ? 'rediscover' : kind, n: 24 });  // favorites, album:<id> too
    let items = (d && d.items) || [];
    const wide = innerWidth >= innerHeight;
    items = items.slice().sort((a, b) => (a.w && a.h ? ((a.w >= a.h) === wide ? 0 : 1) : 0.5) - (b.w && b.h ? ((b.w >= b.h) === wide ? 0 : 1) : 0.5));
    queue = items.map((it) => ({ ...it, otd: d.kind === 'onthisday' }));
  };
  const next = async () => {
    if (busy || !el.isConnected || document.hidden) return;
    if (empty && Date.now() - empty < 5 * 60 * 1000) return;  // ioPix had nothing: ask again in a while, not every tick
    busy = true;
    try {
      for (let tries = 0; tries < 4; tries++) {  // a photo that does not load: the next one, right away
        if (!queue.length) await fill();
        const it = queue.shift();
        if (!it) { empty = Date.now(); return; }
        empty = 0;
        const img = new Image();
        img.alt = ''; img.className = 'wallimg';
        img.style.setProperty('--drift', `${Math.round(every / 1000) + 4}s`);
        img.style.transformOrigin = `${[20, 50, 80][Math.floor(Math.random() * 3)]}% ${[30, 50, 70][Math.floor(Math.random() * 3)]}%`;
        img.src = itemImage('iopix', 'photo', it.id, 'preview');
        await img.decode().catch(() => null);
        if (!el.isConnected) return;
        if (!img.naturalWidth) continue;
        const old = [...el.children];
        el.append(img);
        requestAnimationFrame(() => img.classList.add('on'));
        setTimeout(() => old.forEach((o) => o.remove()), 2000);
        caption.textContent = it.otd ? (it.yearsAgo === 1 ? '1 year ago today' : `${it.yearsAgo} years ago today`) : (it.year ? String(it.year) : '');
        return;
      }
    } finally { busy = false; }
  };
  next();
  return { timer: setInterval(next, every), next };
}
export const WALL_BGS = { photos: 'ioPix photos', sky: 'the sky', black: 'black' };
export const WALL_BG_NAMES = { photos: 'Photos from ioPix', sky: 'The sky: colours of the hour and the weather', black: 'Black' };
export const WALL_EVERY = [20, 60, 300, 900];  // seconds
export const WALL_DEFAULT_EVERY = 60;
/** The wall bar's background button: the next of photos, sky and black, kept in the person's layout. */
async function wallNextBg(bg, pix) {
  const order = pix ? ['photos', 'sky', 'black'] : ['sky', 'black'];
  const to = order[(order.indexOf(bg) + 1) % order.length];
  try {
    S.layout = await saveLayout({ ...S.layout, wallBg: to === (pix ? 'photos' : 'sky') ? null : to });
    toast(`Background: ${WALL_BGS[to]}`); onRoute();
  } catch (e) { fail(e); }
}
/** The sky behind the wall: the hour's colours (night, dawn, day, dusk) and the weather's (clear, cloudy, rain, snow),
    from AccuWeather's icon number when there is weather; the CSS (.wallsky.<time>.<weather>) does the painting. */
function paintSky(el, w) {
  const hr = new Date().getHours(), c = w && w.current;
  let time = hr >= 6 && hr < 8 ? 'dawn' : hr >= 8 && hr < 17 ? 'day' : hr >= 17 && hr < 20 ? 'dusk' : 'night';
  if (c && c.isDay === false && time !== 'dusk' && time !== 'dawn') time = 'night';
  const i = c ? +c.icon : 0;
  const sky = [6, 7, 8, 11, 35, 36, 37, 38].includes(i) ? 'cloudy' : (i >= 12 && i <= 18) || (i >= 39 && i <= 42) ? 'rain'
    : (i >= 19 && i <= 29) || i === 43 || i === 44 ? 'snow' : 'clear';
  el.className = `wallsky ${time} ${sky}`;
}
async function wallWeather(el, hoursEl, sky) {
  let w;
  try { w = await api('api/weather'); } catch { if (sky) paintSky(sky, null); return; }
  if (sky) paintSky(sky, w);
  if (!el.isConnected || !w.enabled || !w.current) { if (w && !w.enabled) { el.replaceChildren(); hoursEl.replaceChildren(); } return; }
  const c = w.current, imp = wxImperial(w), u = imp ? 'imperial' : 'metric', t = (v) => fmtTemp(imp ? degF(v) : v);
  const rain = rainNote(w);
  fill(el, h('div', { class: 'wallnow' }, wxIcon(c.icon, 'big'), h('div', null, h('div', { class: 'walltemp' }, fmtTemp(c.temp[u])), h('div', null, c.text), rain ? h('div', { class: 'wxrain' }, rain) : null)),
    w.forecast && w.forecast.days ? h('div', { class: 'wxdays' }, w.forecast.days.slice(1, 5).map((d) => h('div', { class: 'wxday' },
      h('span', null, new Date(`${d.date}T12:00:00`).toLocaleDateString([], { weekday: 'short' })), wxIcon(d.icon), h('span', null, `${t(d.max)} ${t(d.min)}`)))) : null);
  const hs = nextHours(w).slice(0, 8);
  hoursEl.replaceChildren(hs.length ? hourRow(w, hs) : '');
}
/** A short name for an event's place: what comes before the first comma ("Nan Xiang Dumpling, 38-12 Prince St, …"),
    on one line. */
export function shortPlace(loc) {
  const t = String(loc || '').replace(/\s+/g, ' ').trim();
  return (t.split(',')[0] || '').trim() || t;
}
/** One line of the wall's agenda: its calendar's dot, the time, the title and "@ place" (cut short before the title). */
function wallEvent(o) {
  const at = shortPlace(o.location);
  return h('div', { class: 'wallev' }, h('span', { class: 'dot', style: { background: o.color || 'var(--fg2)' } }), h('span', { class: 'when' }, evTime(o)),
    h('span', { class: 'evtitle' }, o.title), at ? h('span', { class: 'evwhere', title: o.location }, `@ ${at}`) : null);
}
/** Today (what is left of it) and the coming days, a line per event, with today's and tomorrow's birthdays on top. */
async function wallAgenda(el, has) {
  const [today, week, bdays] = await Promise.all([has('iocalendar') ? widget('iocalendar', { n: 6 }) : null, has('iocalendar') ? widget('iocalendar', { kind: 'week' }) : null,
    has('iocontact') ? widget('iocontact') : null]);
  if (!el.isConnected) return;
  S.birthdaysCard = !!(bdays && bdays.items);
  const kids = [];
  const soon = ((bdays && bdays.items) || []).filter((b) => b.in <= 1);
  if (soon.length) kids.push(h('div', { class: 'wallsec' }, soon.map((b) => h('div', { class: 'wallev' }, h('span', { class: 'when' }, inDays(b.in)), h('span', null, `🎂 ${b.name}${b.label === 'birthday' ? (b.turns ? ` turns ${b.turns}` : '') : ` · ${b.label}`}`)))));
  if (today) {
    const items = withoutBirthdays(today.today || []);
    kids.push(h('div', { class: 'wallsec' }, h('div', { class: 'wallhead' }, 'Today'),
      items.length ? items.map((o) => wallEvent(o))
        : h('div', { class: 'wallev muted' }, today.next ? `Nothing more today · next: ${today.next.title}, ${evDay(today.next)}` : 'Nothing more today'),
      today.more ? h('div', { class: 'wallev muted' }, `+${today.more} more`) : null));
  }
  if (week && week.days) {
    const days = week.days.map((d) => ({ ...d, items: withoutBirthdays(d.items) })).filter((d) => d.items.length).slice(0, 3);
    for (const d of days) {
      const s = new Date(`${d.date}T12:00:00`), n = Math.round((s - new Date().setHours(12, 0, 0, 0)) / 86400000);
      kids.push(h('div', { class: 'wallsec' }, h('div', { class: 'wallhead' }, n === 1 ? 'Tomorrow' : s.toLocaleDateString([], { weekday: 'long' })),
        d.items.slice(0, 4).map((o) => wallEvent(o))));
    }
  }
  el.replaceChildren(...kids);
}

// ------------------------------------------------------------------ a wall display signing in (#/pair/<code>)
/* A wall display of its own (devices/tab5-wall: an M5Stack Tab5) shows a code and a QR code of this page. Approving it
   gives the display an app password of the person's (Settings › Account lists it under the display's name; removing
   it there signs the display out). */
export async function showPair(page, r) {
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Sign in a wall display')));
  const box = h('div', { class: 'box' }); page.append(box);
  const ask = (msg) => {
    const code = h('input', { class: 't', placeholder: 'The code on the display, e.g. K7QM-4ZPA', autocomplete: 'off', autocapitalize: 'characters', value: r.code || '' });
    const go = () => { const c = code.value.replace(/[^a-z0-9]/gi, '').toUpperCase(); if (c) location.hash = `#/pair/${c}`; };
    code.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); go(); } };
    fill(box, h('h2', null, icon('wall'), 'The code on the display'), msg ? h('p', { class: 'err' }, msg) : null,
      h('div', { class: 'multi' }, code, h('button', { class: 'pillbtn noic', onclick: go }, 'Next')),
      h('p', { class: 'muted small' }, 'The display shows the code when it starts without a sign-in, with a QR code of this page.'));
  };
  if (!r.code) { ask(); return; }
  let p;
  try { p = await api(`api/wall/pair/code/${encodeURIComponent(r.code)}`); } catch (e) { ask(e.message); return; }
  const code = `${p.code.slice(0, 4)}-${p.code.slice(4)}`;
  box.replaceChildren(h('h2', null, icon('wall'), p.label),
    h('p', null, `The display showing ${code} asks to show your start page: the time, the weather, your calendar, tasks, birthdays and photos, as the wall display does here, and lets a tap tick off a task, add one, or switch what Home Assistant lets you switch.`),
    h('p', { class: 'muted small' }, `It gets an app password of yours, named “${p.label}”. Settings › Account lists it; removing it there signs the display out.`),
    h('div', { class: 'row' }, h('button', { class: 'pillbtn noic', onclick: async (e) => {
      e.target.disabled = true;
      try {
        await api(`api/wall/pair/code/${encodeURIComponent(p.code)}`, { method: 'POST', json: {} });
        box.replaceChildren(h('h2', null, icon('wall'), p.label), h('p', null, 'Done: the display signs in within a few seconds.'), h('p', null, h('a', { class: 'lnk', href: '#/' }, 'Back to the start page')));
      } catch (err) { e.target.disabled = false; fail(err); }
    } }, 'Let it in'), ' ', h('a', { class: 'lnk', href: '#/' }, 'Not now')));
}

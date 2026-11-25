import { drawNav, showSignIn } from './shell.js';
import { onRoute, refresh } from './main.js';
import { client, h, safeUrl } from '../../api/auth/ui.js';  // the suite's shared helpers (iosuite_shared/static/account-panel.js)
import * as frame from '../../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { ICONS, addIcons, closeDialogs, closeMenu, confirmDialog, dialog, fail, fill, hue, icon, initials, menuOpen, popMenu, put } from '../../api/auth/frame.js';
export { ICONS, closeDialogs, closeMenu, confirmDialog, dialog, fail, fill, hue, icon, initials, menuOpen, popMenu, put };
export { h, safeUrl };
export const api = client(document.baseURI, { signIn: () => showSignIn() });

// The helpers every page uses (api, h, icon, drag to sort), dates and repeat rules, and the app's state.

// ------------------------------------------------------------------ helpers
export const $ = (s, el = document) => el.querySelector(s);
addIcons({
  today: 'M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z',
  event: 'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
  inbox: 'M19 3H4.99C3.88 3 3 3.9 3 5v14c0 1.1.88 2 1.99 2H19c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 12h-4c0 1.66-1.35 3-3 3s-3-1.34-3-3H4.99V5H19v10z',
  done: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
  repeat: 'M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z',
  bell: 'M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z',
  flag: 'M14.4 6 14 4H5v17h2v-7h5.6l.4 2h7V6z',
  devices: 'M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z',
  chevR: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  subtask: 'M19 15l-6 6-1.42-1.42L15.17 16H4V4h2v10h9.17l-3.59-3.58L13 9l6 6z',
  later: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
  grip: 'M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  template: 'M19 3h-4.18C14.4 1.84 13.3 1 12 1s-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm-2 14-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z',
  sort: 'M3 18h6v-2H3v2zM3 6v2h18V6H3zm0 7h12v-2H3v2z',
});

export function toast(msg, undo) { frame.toast(msg, undo ? ['Undo', () => undoStep(undo)] : null, undo ? 10000 : 0); }
export async function undoStep(batch) {
  try { await api(`api/undo/${batch}`, { method: 'POST' }); await refresh(); toast('Undone'); } catch (e) { fail(e); }
}


/** Drag to reorder: the children of `box` that match `item` change places among themselves, taken by the `grip` inside
    one (mouse or finger) or, without a grip, by the whole item (mouse only, once it moved a little, so a click stays a
    click). The item moves as the pointer passes its neighbours; done(ids) gets the new order of their data-id. */
export function dragSort(box, item, grip, done) {
  const items = () => [...box.children].filter((x) => x.matches(item));
  box.addEventListener('click', (e) => { if (e.target.closest('[data-dragged]')) { e.preventDefault(); e.stopPropagation(); } }, true);
  box.addEventListener('dragstart', (e) => e.preventDefault());  // a link or a picture would be dragged off as itself
  box.addEventListener('pointerdown', (e) => {
    if (e.button) return;
    const g = grip ? e.target.closest(grip) : (e.pointerType === 'mouse' ? e.target.closest(item) : null);
    const it = g && g.closest(item);
    if (!it || it.parentElement !== box) return;
    const before = items().map((x) => x.dataset.id).join();
    const y0 = e.clientY;
    let on = false;
    const start = () => { on = true; it.classList.add('dragging'); document.body.classList.add('sorting'); };
    if (grip) { e.preventDefault(); start(); }
    const move = (ev) => {
      if (!on) { if (Math.abs(ev.clientY - y0) < 6) return; start(); }
      ev.preventDefault();
      const others = items().filter((x) => x !== it);
      const next = others.find((x) => { const r = x.getBoundingClientRect(); return ev.clientY < r.top + r.height / 2; });
      if (next) { if (it.nextElementSibling !== next) box.insertBefore(it, next); }
      else if (others.length && others[others.length - 1].nextElementSibling !== it) others[others.length - 1].after(it);
    };
    const up = () => {
      removeEventListener('pointermove', move); removeEventListener('pointerup', up); removeEventListener('pointercancel', up);
      if (!on) return;
      it.classList.remove('dragging'); document.body.classList.remove('sorting');
      it.dataset.dragged = '1'; setTimeout(() => { delete it.dataset.dragged; }, 60);
      const after = items().map((x) => x.dataset.id);
      if (after.join() !== before) done(after.map(Number));
    };
    addEventListener('pointermove', move, { passive: false }); addEventListener('pointerup', up); addEventListener('pointercancel', up);
  });
}

export async function copyText(t) { try { await navigator.clipboard.writeText(t); toast('Copied'); } catch { toast(t); } }
export const copyRow = (v) => h('div', { class: 'copy' }, h('code', null, v), h('button', { class: 'iconbtn', title: 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));
export const store = frame.storeFor('iotask');

// ------------------------------------------------------------------ dates
export const pad2 = (n) => String(n).padStart(2, '0');
export const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
export const hm = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
export const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
export const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
export const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
export const fmtTime = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
export const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
export const TZQ = `tz=${encodeURIComponent(LOCAL_TZ)}`;  // whose "today" the server counts with
export const DOW = (i, style = 'short') => new Date(2026, 1, 1 + i).toLocaleDateString([], { weekday: style }); // 1 Feb 2026 is a Sunday
export const RDAY = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];

/** A task's due as a Date (all-day: local midnight), or null. */
export const dueOf = (t) => (t.due ? (t.dueAllDay ? parseDay(t.due) : new Date(t.due)) : null);
/** Open and past its time (a timed task) or its day (an all-day one). */
export function isLate(t) {
  const d = dueOf(t);
  if (!d || t.done) return false;
  return t.dueAllDay ? d < dayStart(new Date()) : d < new Date();
}
/** A day in words: Today, Tomorrow, Yesterday, a weekday this week, else the date. */
export function dayWords(d) {
  const t = dayStart(new Date()), n = Math.round((dayStart(d) - t) / 864e5);
  if (n === 0) return 'Today';
  if (n === 1) return 'Tomorrow';
  if (n === -1) return 'Yesterday';
  if (n > 1 && n < 7) return d.toLocaleDateString([], { weekday: 'long' });
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: d.getFullYear() !== t.getFullYear() ? 'numeric' : undefined });
}
export const dueText = (t) => { const d = dueOf(t); return d ? dayWords(d) + (t.dueAllDay ? '' : `, ${fmtTime(d)}`) : ''; };
export const ordinal = (n) => ({ 1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', '-1': 'last' })[n] || `${n}th`;

/** A repeat rule (RRULE) in words. */
export function describeRule(rule, day) {
  if (!rule) return '';
  const p = Object.fromEntries(rule.split(';').map((x) => x.split('=')));
  const n = +(p.INTERVAL || 1);
  const unit = { DAILY: 'day', WEEKLY: 'week', MONTHLY: 'month', YEARLY: 'year', HOURLY: 'hour' }[p.FREQ] || (p.FREQ || '').toLowerCase();
  let s = n === 1 ? `Every ${unit}` : `Every ${n} ${unit}s`;
  if (p.FREQ === 'DAILY' && n === 1) s = 'Daily';
  if (p.FREQ === 'WEEKLY' && p.BYDAY) {
    const days = p.BYDAY.split(',');
    if (days.length === 5 && ['MO', 'TU', 'WE', 'TH', 'FR'].every((d) => days.includes(d))) s = n === 1 ? 'Every weekday' : `${s} on weekdays`;
    else s += ' on ' + days.map((d) => DOW(RDAY.indexOf(d), 'long')).join(', ');
  }
  if (p.FREQ === 'MONTHLY') {
    if (p.BYDAY) { const m = p.BYDAY.match(/^(-?\d)?([A-Z]{2})$/); if (m) s += ` on the ${ordinal(m[1] || 1)} ${DOW(RDAY.indexOf(m[2]), 'long')}`; }
    else if (p.BYMONTHDAY) s += ` on day ${p.BYMONTHDAY}`;
    else if (day) s += ` on day ${day.getDate()}`;
  }
  if (p.COUNT) s += `, ${p.COUNT} more times`;
  if (p.UNTIL) { const u = p.UNTIL; s += `, until ${parseDay(`${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}`).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })}`; }
  return s;
}

/* A task that repeats after completion comes back some time after the day it is ticked off: "P2W" (an ISO 8601
   duration of days, weeks, months or years) is two weeks. The form shows it as the repeat rule of that length. */
export const AFTER_UNIT = { D: 'DAILY', W: 'WEEKLY', M: 'MONTHLY', Y: 'YEARLY' };
export const afterParts = (p) => { const m = /^P(\d+)([DWMY])$/.exec(p || ''); return m ? [+m[1], m[2]] : null; };
export const afterRule = (p) => { const a = afterParts(p); return a ? `FREQ=${AFTER_UNIT[a[1]]}${a[0] > 1 ? `;INTERVAL=${a[0]}` : ''}` : ''; };
/** A rule that is only "every n days, weeks, months or years" as such a duration (null: it says more than that). */
export function afterOf(rule) {
  const p = Object.fromEntries((rule || '').split(';').map((x) => x.split('=')));
  const u = Object.keys(AFTER_UNIT).find((k) => AFTER_UNIT[k] === p.FREQ);
  return u && Object.keys(p).every((k) => k === 'FREQ' || k === 'INTERVAL') ? `P${+p.INTERVAL || 1}${u}` : null;
}
export function describeAfter(p) {
  const a = afterParts(p);
  if (!a) return '';
  const unit = { D: 'day', W: 'week', M: 'month', Y: 'year' }[a[1]];
  return `${a[0] === 1 ? `A ${unit}` : `${a[0]} ${unit}s`} after it is ticked off`;
}
/** Where a task can be put off to: [label, day]; Today only for what is overdue. */
export function laterDays(withToday) {
  const t = dayStart(new Date()), wd = t.getDay();
  return [withToday ? ['Today', t] : null, ['Tomorrow', addDays(t, 1)], ['This weekend', addDays(t, (6 - wd + 7) % 7 || 7)],
    ['Next week', addDays(t, (8 - wd) % 7 || 7)]].filter(Boolean);
}

// ------------------------------------------------------------------ state
export const S = { status: {}, user: null, suite: [], settings: {}, lists: [], counts: {}, members: [], who: new Set(), q: '' };
// the suite's roles, each able to do what the one before can: a viewer only looks, a member keeps their own lists,
// an editor changes the shared ones too
export const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
export const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
export const canOwn = () => roleAtLeast('member');
export const canShared = () => roleAtLeast('editor');
export const listOf = (id) => S.lists.find((c) => c.id === id) || {};
export const writable = () => S.lists.filter((c) => c.writable);
/** Where a new task goes when no list is open: the one chosen in Settings › Display, else your own first list. */
export function defaultList() {
  const w = writable();
  return w.find((c) => c.id === +S.settings.defaultList) || w.find((c) => c.mine) || w[0] || null;
}
export const memberOf = (id) => S.members.find((m) => m.id === id);
/** Each family member's colour, initials and face are the suite's (Settings › People › Family), the same in every io app. */
export const memberColor = (m) => m.color || '#5f6b7a';
/** A member's badge: their initials on their colour; `face`: their face (ioPix, else their ioContact card) when they have one. */
export const memberBadge = (m, face = false) => h('span', { class: `mem${face && m.hasFace ? ' face' : ''}`, title: m.displayName, style: { '--mc': memberColor(m) } }, m.initials || initials(m.displayName),
  face && m.hasFace ? h('img', { src: `api/auth/family/${m.id}/face`, alt: '', loading: 'lazy', onerror: (e) => { e.currentTarget.parentNode.classList.remove('face'); e.currentTarget.remove(); } }) : null);
export function toggleWho(id) {
  if (id == null) S.who.clear(); else if (S.who.has(id)) S.who.delete(id); else S.who.add(id);
  saveSettings({ memberFilter: [...S.who].join(',') });
  onRoute();
}

export async function loadLists() {
  const [lists, fam, counts] = await Promise.all([api(`api/lists?${TZQ}`), api('api/members').catch(() => ({ items: S.members })), api(`api/counts?${TZQ}`).catch(() => S.counts)]);
  S.lists = lists.items;
  S.members = fam.items || [];
  S.counts = counts || {};
  for (const id of [...S.who]) if (!memberOf(id)) S.who.delete(id);
  $('#newbtn').hidden = !writable().length;
  drawNav();
}
export async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}

/* What each app's tile shows under its name (/api/widgets/<app>), and the Today card. */
import { fail, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, appName, itemImage, money, quiet, S, viewerTz } from './core.js';
import { isBirthdayEvent, withoutBirthdays } from './cards.js';
import { arrangeToday } from './customize.js';
import { sizeOf } from './home.js';
import { shortPlace } from './wall.js';

// ------------------------------------------------------------------ what the tiles show (/api/widgets/<app>)
/* Under an app's name, a glimpse of it: ioPix's photos from this day in earlier years (else a few at random),
   ioCalendar's rest of today (else what's next), ioHealth's steps and rings. The server asks each app with the
   viewer's own sign-in; an app that is down or not open to this account leaves its tile as it was. */
export const WIDGETS = { iopix: drawPixWidget, iocalendar: drawCalendarWidget, iotask: drawTasksWidget, iohealth: drawHealthWidget, iomoney: drawMoneyWidget, iodocs: drawDocsWidget };
/** ioPix opens one photo in its lightbox at #/photos?p=<id>. */
export const pixPhotoUrl = (pix, id) => `${pix.url}/#/photos?p=${id}`;

/* Apps whose tile is a low one in the shared column, with one line under the name rather than a column of its own:
   draw(d) gives [text, warn, tooltip, idle] (idle: nothing to report). */
export const LOW = { iodocs: drawDocsLine };

/** An app's tile: its icon, its name with the dot that says whether it answers, a line under the name (a low tile's),
    and room for what the app shows here (drawWidgets; a block of the person's own grid fills it itself). */
export const tileOf = (a, small) => h('a', { class: `app${small ? ' small' : ''}`, href: a.url, 'data-app': a.key, title: a.url },
  h('img', { src: a.icon, alt: '' }), h('span', { class: 'who' }, h('span', { class: 'nmrow' }, appName(a.name, a.color), h('span', { class: 'st' })), h('span', { class: 'line muted small' })),
  h('div', { class: 'more' }));

export function drawWidgets(page, again = false) {
  const tz = viewerTz();
  for (const tile of page.querySelectorAll('.app[data-app]')) {
    const key = tile.dataset.app, draw = WIDGETS[key], box = tile.querySelector('.more'), grid = tile.closest('.apps');
    const size = grid && draw ? sizeOf(key) : '';  // the person's choice for this app, in the layout with a card for each
    // a low tile with its one line: an app that is always one (LOW), or one the person keeps low
    const line = size === 'card' ? null : LOW[key] || (size === 'tile' ? LINES[key] : null);
    if (line) { drawLowLine(tile, tile.querySelector('.who > .line'), tz, line); continue; }
    if (!draw || !box || !grid) continue;  // in the dock the tiles only open their app: the glance cards show the day
    const why = (text) => { if (box.isConnected) box.replaceChildren(h('div', { class: 'wg' }, h('div', { class: 'muted small wgwhy' }, text))); };
    // a card again (it has something to show, or to say why not), or a low tile (nothing today); the tiles move when that changes
    const card = (quiet) => { if (tile.classList.contains('small') === quiet) return; if (quiet) quietTile(tile, EMPTY[key]); else tile.classList.remove('small'); arrangeTiles(grid); };
    wget(`api/widgets/${key}?tz=${encodeURIComponent(tz)}`)
      .then((r) => { if (r.ok && r.body) return r.body; throw new Error((r.body && r.body.detail) || `${r.status}`); })
      .then((d) => {
        if (!box.isConnected) return;
        const kids = draw(d);
        if (kids) box.replaceChildren(h('div', { class: 'wg' }, kids));
        else if (size === 'card') box.replaceChildren(h('div', { class: 'wg' }, h('div', { class: 'muted small wgwhy' }, EMPTY[key] || 'Nothing to show')));  // kept a card: it says so
        else box.replaceChildren();
        card(!kids && size !== 'card');
        if (!size) quietKeys(key, !kids);
        quiet(tile, !kids);
      })
      .catch((e) => { if (again && (tile.classList.contains('small') || box.querySelector('.wg .wghead'))) return; why(e.message); card(false); });  // the app is down, or not open to this account: the tile says so (a refresh that fails keeps what it showed)
  }
}

// what a card that has nothing to show says, as a low tile's one line
export const EMPTY = { iopix: 'No photos yet', iocalendar: 'Nothing planned', iotask: 'Nothing due today', iohealth: 'Nothing for today yet', iomoney: 'Nothing due this week', iodocs: 'Nothing to renew' };
/** A card as a low tile, with its one line. */
export function quietTile(tile, text) {
  tile.classList.add('small');
  const line = tile.querySelector('.who > .line');
  if (line) line.textContent = text || 'Nothing to show';
}
/** The apps whose card had nothing to show the last time, kept in this browser (so the next visit starts with them low);
    with a key, notes how that app's card was this time. */
export function quietKeys(key, quiet) {
  let keys = [];
  try { const v = JSON.parse(localStorage.getItem('iostart.quiet') || '[]'); if (Array.isArray(v)) keys = v.filter((k) => typeof k === 'string'); } catch { /* private mode, or not ours */ }
  if (key == null || keys.includes(key) === quiet) return keys;
  keys = quiet ? [...keys, key] : keys.filter((k) => k !== key);
  try { localStorage.setItem('iostart.quiet', JSON.stringify(keys)); } catch { /* private mode */ }
  return keys;
}
/** The cards first and the low tiles after them in one stack, each in the page's order of apps. */
export function arrangeTiles(grid) {
  const rank = (el) => S.apps.findIndex((a) => a.key === el.dataset.app);
  const tiles = [...grid.querySelectorAll('.app[data-app]')].sort((a, b) => rank(a) - rank(b));
  const low = tiles.filter((el) => el.classList.contains('small'));
  let stack = grid.querySelector(':scope > .stack');
  if (low.length && !stack) stack = h('div', { class: 'stack' });
  grid.append(...tiles.filter((el) => !low.includes(el)), ...(low.length ? [stack] : []));
  if (stack) { if (low.length) stack.append(...low); else stack.remove(); }
  fitStack(grid);
}
/** The stack of low tiles takes the free cell at the end of the last row of cards, as a column of thin tiles; with no
    cell free (or no card, or one column: a phone) it takes a row of its own, the tiles side by side. */
export function fitStack(grid) {
  const stack = grid.querySelector(':scope > .stack');
  if (!stack) return;
  const cols = getComputedStyle(grid).gridTemplateColumns.split(' ').length, cards = grid.querySelectorAll(':scope > .app:not([hidden])').length, n = stack.querySelectorAll(':scope > :not([hidden])').length;
  const across = cols < 2 || !cards || cards % cols === 0 || n > 6;  // more than six would make their row taller than its cards
  stack.classList.toggle('across', across);
  stack.classList.toggle('dense', !across && n > 3);
  stack.style.setProperty('--n', Math.max(3, n));
}
export const wgHead = (t, extra) => h('div', { class: 'wghead' }, h('span', null, t), extra ? h('span', { class: 'muted' }, extra) : null);

function drawPixWidget(d, n = 4) {
  if (!d.items || !d.items.length) return null;
  const otd = d.kind === 'onthisday';
  const cap = (it) => (otd ? (it.yearsAgo === 1 ? '1 year ago' : `${it.yearsAgo} years ago`) : (it.year || ''));
  // n small squares in a row (four on a card): the year fits under each, "14 years ago" is the tooltip
  return [wgHead(otd ? 'On this day' : 'Rediscover', otd && d.count > d.items.length ? `${d.count} photos` : null),
    h('div', { class: 'wgpix' }, d.items.slice(0, n).map((it) => h('span', { class: 'wgph', title: String(cap(it)), role: 'link', tabindex: '0',
      onclick: (e) => { e.preventDefault(); e.stopPropagation(); location.href = pixPhotoUrl(S.apps.find((a) => a.key === 'iopix'), it.id); },
      onkeydown: (e) => { if (e.key === 'Enter') e.target.click(); } },
      h('img', { src: itemImage('iopix', 'photo', it.id), alt: '', loading: 'lazy', onerror: (e) => e.target.parentNode.remove() }),
      it.year ? h('span', null, it.year) : null)))];
}

export function evTime(o) {
  if (o.allDay) return 'All day';
  const s = new Date(o.start);
  return isNaN(s) ? '' : s.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}
export function evDay(o) {
  const s = new Date(o.allDay ? `${o.start}T12:00:00` : o.start);
  if (isNaN(s)) return '';
  const t = new Date(); t.setHours(0, 0, 0, 0);
  const days = Math.round((new Date(s.getFullYear(), s.getMonth(), s.getDate()) - t) / 86400000);
  return days === 1 ? 'Tomorrow' : s.toLocaleDateString([], days < 7 ? { weekday: 'long' } : { weekday: 'short', month: 'short', day: 'numeric' });
}
export const evRow = (o, when) => h('div', { class: 'wgev', title: [o.title, o.location].filter(Boolean).join(' · ') },
  h('span', { class: 'dot', style: { background: o.color || 'var(--fg2)' } }), h('span', { class: 'wgwhen muted' }, when), h('span', { class: 'wgtitle' }, o.title));

/* A task's box, which ticks it off in ioTask where it stands (and opens it again with a second click, while the page
   still shows it): the row is struck through until the next refresh takes it away. A repeating task moves on to its
   next time; the step ioTask gives back undoes exactly that. The rows are inside links, so the click stops here. */
function taskTick(t) {
  const box = h('span', { class: 'tick', role: 'checkbox', tabindex: '0', 'aria-checked': 'false', 'aria-label': `Done: ${t.title}`, title: 'Tick off', style: { color: t.color || 'var(--fg2)' } });
  let step = null, busy = false;
  const flip = async (e) => {
    e.preventDefault(); e.stopPropagation();
    if (busy || t.id == null) return;
    const done = box.getAttribute('aria-checked') !== 'true', row = box.closest('.wgev');
    const show = (on) => { box.setAttribute('aria-checked', String(on)); box.title = on ? 'Not done after all' : 'Tick off'; if (row) row.classList.toggle('done', on); };
    busy = true; show(done);  // at once; back when ioTask says no
    try {
      const r = await api(`api/widgets/iotask/tasks/${encodeURIComponent(t.id)}/done`, { method: 'POST', json: { done, undo: done ? undefined : step || undefined, timezone: viewerTz() } });
      step = done ? r.undo || null : null;
      if (done && r.moved) toast(`“${t.title}” moves on to its next time`);
      S.refreshedAt = 0;  // the next look at the page (liveRefresh) asks the apps again
    } catch (err) { show(!done); fail(err); }
    busy = false;
  };
  box.onclick = flip;
  box.onkeydown = (e) => { if (e.key === ' ' || e.key === 'Enter') flip(e); };
  return box;
}

function drawCalendarWidget(d) {
  const today = withoutBirthdays(d.today || []);
  if (today.length) {
    return [wgHead('Today', d.more ? `+${d.more} more` : null), today.map((o) => evRow(o, evTime(o)))];
  }
  return d.next ? [wgHead('Next', evDay(d.next)), evRow(d.next, evTime(d.next))] : null;
}

/** ioTask: what is due today (and what is overdue, first), in each list's colour. */
function drawTasksWidget(d) {
  const today = d.today || [];
  if (!today.length) return null;
  const when = (t) => { if (t.late) return 'Late'; if (t.allDay || !t.due) return ''; const s = new Date(t.due); return isNaN(s) ? '' : s.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); };
  return [wgHead('Due today', [d.overdue ? `${d.overdue} overdue` : null, d.more ? `+${d.more} more` : null].filter(Boolean).join(' · ') || null),
    today.map((t) => h('div', { class: 'wgev', title: t.title }, taskTick(t), h('span', { class: `wgwhen ${t.late ? 'wgwarn' : 'muted'}` }, when(t)), h('span', { class: 'wgtitle' }, t.title)))];
}

/** ioMoney: what needs a look first (a cash account about to run low, bank links that are behind), then the bills and
    subscriptions due in the coming week, the soonest first; three lines in all, as the other tiles. */
function drawMoneyWidget(d) {
  const bills = d.bills || [], low = d.low || [], behind = d.behind || [];
  if (!bills.length && !low.length && !behind.length) return null;
  const dayOf = (iso) => new Date(`${iso}T12:00:00`);
  const short = (iso) => { const n = Math.round((dayOf(iso).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
    return n <= 0 ? 'Today' : n === 1 ? 'Tmrw' : dayOf(iso).toLocaleDateString([], { weekday: 'short' }); };
  const long = (iso) => dayOf(iso).toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });
  const warn = (text, title) => h('div', { class: 'wgev wgwarn', title }, icon('warn', 's'), h('span', { class: 'wgtitle' }, text));
  const notes = [];
  if (low.length) {
    const a = low[0];
    const n = Math.round((dayOf(a.belowOn).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
    const on = n <= 0 ? 'today' : n === 1 ? 'tomorrow' : n < 7 ? short(a.belowOn) : dayOf(a.belowOn).toLocaleDateString([], { month: 'short', day: 'numeric' });
    // the day first: on a narrow tile the account's name is what gets cut (the tooltip has it all)
    notes.push(warn(low.length > 1 ? `${low.length} accounts run low` : `Low ${on}: ${a.name}`,
      low.map((x) => `${x.name}: under ${x.floor ? money(x.floor, x.currency) : money(0, x.currency)} on ${long(x.belowOn)}, down to ${money(x.value, x.currency)}`).join('\n')));
  }
  if (behind.length) notes.push(warn(behind.length > 1 ? `${behind.length} bank links behind` : `Bank link behind: ${behind[0].name}`,
    `Not updated from the bank lately: ${behind.map((x) => [x.name, x.institution].filter(Boolean).join(' at ')).join(', ')}`));
  const shown = bills.slice(0, Math.max(1, 3 - notes.length)), more = (d.more || 0) + bills.length - shown.length;
  const total = d.total != null && bills.length + (d.more || 0) > 1 ? money(-d.total, d.currency) : null;  // one bill: its own amount says it
  const all = bills.length + (d.more || 0);
  const head = wgHead('This week', total || (more ? `+${more} more` : null));
  if (all) head.title = `${all} ${all === 1 ? 'payment' : 'payments'} due in the next 7 days${d.total != null ? `: ${money(-d.total, d.currency)}` : ''}`;
  return [head, notes,
    shown.map((b) => h('div', { class: 'wgev', title: [b.name, long(b.day), b.account, b.approximate ? 'about this much' : null].filter(Boolean).join(' · ') },
      h('span', { class: 'wgwhen muted' }, short(b.day)), h('span', { class: 'wgtitle' }, b.name),
      h('span', { class: 'wgamt' }, `${b.approximate ? '~' : ''}${money(-b.amount, b.currency)}`)))];
}

/** The "today" layout's cards under the dock. Today: ioCalendar's events and ioTask's tasks in one list by the hour
    (what is late first, then ioContact's birthdays, what has no hour last), and under them the coming days' as far as the card has room beside
    the other two (fitGlance), so a light day shows what is ahead; ioMoney's week of bills beside them; then ioHealth and ioPix's
    On this day, one above the other. Each part is there when its app is on the page and answers; a row opens its app.
    again: a refresh, which keeps what the cards show when nothing answers. */
const GLANCE_LINES = 9, GLANCE_PHOTOS = 6;  // the most lines of today in the Today card's list (and of the coming days, on a phone); On this day's photos
const GLANCE_MIN = 8;  // the lines the list has at least when there are that many, however low the cards beside it are
const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export async function drawGlance(el, again = false) {
  const app = (k) => S.apps.find((a) => a.key === k);
  // what the person left in (Customize › Cards, or the switches on the page while it is arranged): layout todayOff
  const L = S.layout || {}, has = (part) => !(L.todayOff || []).includes(part);
  const ask = (k, part, params) => (app(k) && has(part) ? widget(k, params) : null);
  const [cal, task, mon, health, pix, calWeek, taskWeek, bdays] = await Promise.all([ask('iocalendar', 'events', { n: GLANCE_LINES }), ask('iotask', 'tasks', { n: GLANCE_LINES }), ask('iomoney', 'bills'), ask('iohealth', 'health'),
    ask('iopix', 'photos', { n: GLANCE_PHOTOS }), ask('iocalendar', 'events', { kind: 'week' }), ask('iotask', 'tasks', { kind: 'week' }), ask('iocontact', 'birthdays')]);
  if (!el.isConnected || (again && ![cal, task, mon, health, pix].some(Boolean))) return;
  const head = (k, text, extra) => h('a', { class: 'ghead', href: app(k).url, title: app(k).url }, h('img', { src: app(k).icon, alt: '' }), h('span', null, text),
    extra ? h('span', { class: typeof extra === 'string' ? 'gextra muted' : 'gextra' }, extra) : null);
  const row = (k, title, kids) => h('a', { class: 'wgev', href: app(k).url, title }, kids);
  // a day's events and tasks by the hour
  const timed = (t) => t.due && !t.allDay && !isNaN(new Date(t.due));
  const taskRow = (t) => ({ at: t.late ? -1 : timed(t) ? +new Date(t.due) : Infinity, el: row('iotask', t.title, [taskTick(t),
    h('span', { class: `wgwhen ${t.late ? 'wgwarn' : 'muted'}` }, t.late ? 'Late' : timed(t) ? evTime({ start: t.due }) : ''), h('span', { class: 'wgtitle' }, t.title)]) });
  const eventRow = (o) => ({ at: o.allDay ? 0 : +new Date(o.start), el: row('iocalendar', [o.title, o.location].filter(Boolean).join(' · '), [h('span', { class: 'dot', style: { background: o.color || 'var(--fg2)' } }),
    h('span', { class: 'wgwhen muted' }, evTime(o)), h('span', { class: 'wgtitle' }, o.title), o.location ? h('span', { class: 'wgat muted' }, `@ ${shortPlace(o.location)}`) : null]) });
  const byHour = (rows) => rows.sort((a, b) => a.at - b.at).map((r) => r.el);
  // ioContact's birthdays (and its other dates) of today and the coming week, whether or not the Birthdays card is on the
  // page: on top of their day. ioCalendar's Birthdays calendar has them too ("Ava Calloway's birthday"): those are left out
  const dates = ((bdays && bdays.items) || []).filter((b) => b.in >= 0 && b.in <= 7);
  const dateRow = (b) => ({ at: -0.5, el: h('a', { class: 'wgev', href: `${app('iocontact').url}/#/c/${b.id}`, title: b.label === 'birthday' ? (b.turns ? `${b.name} turns ${b.turns}` : `${b.name}'s birthday`) : `${b.name}: ${b.label}` },
    h('span', { class: 'gcake' }, b.label === 'birthday' ? '🎂' : '🎉'), h('span', { class: 'wgwhen muted' }, b.label === 'birthday' ? 'Birthday' : ''), h('span', { class: 'wgtitle' }, b.name),
    h('span', { class: 'wgat muted' }, b.label === 'birthday' ? (b.turns ? `turns ${b.turns}` : '') : b.label + (b.turns ? ` · ${b.turns} years` : ''))) });
  // without the birthdays, the calendar's own "X's birthday" events go too
  const mine = (items, n) => items.filter((o) => !(isBirthdayEvent(o) && (!has('birthdays') || dates.some((b) => b.in === n && (o.title || '').includes(b.name)))));
  const dayIn = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return isoDay(d); };
  const daysTo = (date) => Math.round((new Date(`${date}T12:00:00`) - new Date().setHours(12, 0, 0, 0)) / 86400000);
  const events = mine(withoutBirthdays((cal && cal.today) || []), 0);
  const all = byHour([...dates.filter((b) => b.in === 0).map(dateRow), ...((task && task.today) || []).map(taskRow), ...events.map(eventRow)]), lines = all.slice(0, GLANCE_LINES);
  const moreToday = all.length - lines.length + ((cal && cal.more) || 0) + ((task && task.more) || 0);
  const none = cal && task ? 'Nothing planned or due today' : cal ? 'Nothing planned today' : task ? EMPTY.iotask : 'No birthdays today';
  if (!lines.length) lines.push(h('div', { class: 'muted small' }, none));
  // the coming days, each under its name, while the column has lines left (a day's name and at least one row of it)
  const ahead = new Map();
  const far = L.todayDays == null ? Infinity : L.todayDays;  // how many of the coming days the person wants listed (nothing: the week)
  const on = (date, r) => { if (daysTo(date) > far) return; if (!ahead.has(date)) ahead.set(date, []); ahead.get(date).push(r); };
  for (const b of dates) if (b.in > 0) on(dayIn(b.in), dateRow(b));
  for (const day of (calWeek && calWeek.days) || []) for (const o of mine(withoutBirthdays(day.items), daysTo(day.date))) on(day.date, eventRow(o));
  for (const t of (taskWeek && taskWeek.week) || []) { const d = t.allDay || !timed(t) ? String(t.due).slice(0, 10) : isoDay(new Date(t.due)); if (d > isoDay(new Date())) on(d, taskRow(t)); }
  const later = [];  // in steps that show together: a day's name with its first row, then a row at a time
  for (const date of [...ahead.keys()].sort()) {
    const noon = new Date(`${date}T12:00:00`), days = daysTo(date);
    const name = h(cal ? 'a' : 'div', { class: 'gday', href: cal ? `${app('iocalendar').url}/#/day/${date}` : null }, days === 1 ? 'Tomorrow' : noon.toLocaleDateString([], { weekday: 'long' }),
      h('span', { class: 'muted' }, noon.toLocaleDateString([], { month: 'short', day: 'numeric' })));
    byHour(ahead.get(date)).forEach((r, i) => later.push(i ? [r] : [name, r]));
  }
  for (const step of later) for (const x of step) x.hidden = true;  // fitGlance shows what there is room for
  // nothing today and nothing in the week: the next event, however far off
  if (cal && !events.length && !ahead.size && cal.next && far > 0) lines.push(row('iocalendar', cal.next.title, [h('span', { class: 'dot', style: { background: cal.next.color || 'var(--fg2)' } }),
    h('span', { class: 'wgwhen muted' }, 'Next'), h('span', { class: 'wgtitle' }, cal.next.title), h('span', { class: 'wgat muted' }, `${evDay(cal.next)} ${cal.next.allDay ? '' : evTime(cal.next)}`.trim())]));
  const more = [moreToday ? `+${moreToday} more today` : null, task && task.overdue ? `${task.overdue} overdue` : null].filter(Boolean).join(' · ');
  const plans = cal || task || dates.length ? h('div', null, wgHead(cal && task ? 'Plans and tasks' : cal ? 'Plans' : task ? 'Tasks' : 'Birthdays', more || ' '), lines, later) : null;
  // the week's bills (and what needs a look in ioMoney), as its card has them
  const mk = mon ? drawMoneyWidget(mon) : null;
  const bills = mon ? h('a', { class: 'gbills', href: app('iomoney').url, title: app('iomoney').url }, mk || [wgHead('This week'), h('div', { class: 'muted small' }, 'Nothing due')]) : null;
  if (bills) bills.querySelector('.wghead > span').textContent = 'Bills this week';
  const today = plans || bills ? h('div', { class: 'card todaycard' }, head(cal ? 'iocalendar' : task ? 'iotask' : plans ? 'iocontact' : 'iomoney', 'Today'), h('div', { class: `todaycols${plans && bills ? '' : ' one'}` }, plans, bills)) : null;
  // the two low cards: ioHealth's steps go in its head (no "Today" line), On this day shows six smaller photos
  const hk = health ? drawHealthWidget(health) : null, pk = pix ? drawPixWidget(pix, GLANCE_PHOTOS) : null;
  const side = [hk ? h('div', { class: 'card' }, head('iohealth', 'Health', hk[0].children[1]), h('div', { class: 'wg' }, hk.slice(1))) : null,
    pk ? h('div', { class: 'card' }, head('iopix', pk[0].firstChild.textContent, pk[0].children[1] ? pk[0].children[1].textContent : null), h('div', { class: 'wg' }, pk.slice(1))) : null].filter(Boolean);
  el.classList.toggle('one', !today || !side.length);
  el.replaceChildren(...[S.arrange ? arrangeToday(el) : null, today, side.length ? h('div', { class: `gside${today ? '' : ' flat'}` }, side) : null].filter(Boolean));
  // how many of the coming days' rows show: again when the cards' width changes
  const beyond = far === Infinity ? ((calWeek && calWeek.more) || 0) + ((taskWeek && taskWeek.more) || 0) : null;  // "+3 more this week" only when the week is what the list shows
  el.fit = () => fitGlance(el, plans, lines.length, later, more || beyond == null ? null : beyond);
  if (!el.watched) { el.watched = new ResizeObserver(() => el.fit && el.fit()); el.watched.observe(el); }
  el.fit();
}
/** The coming days in the Today card's list: with the other cards beside it, as many rows as fit without the card growing
    taller than they (or today's own rows) make it, and GLANCE_MIN lines with today's whatever their height (a low Health
    card alone must not leave the list empty); on its own (a phone), up to GLANCE_LINES lines with today's. The head says how many are left out (unless
    it has something to say about today). */
function fitGlance(el, plans, shown, later, beyond) {
  if (!plans || !plans.isConnected) return;
  const show = (step, on) => { for (const x of step) x.hidden = !on; };
  let i = 0;
  for (const step of later) show(step, false);
  const card = el.querySelector('.todaycard'), side = el.querySelector('.gside');
  if (card && side && Math.abs(card.offsetTop - side.offsetTop) < 4) {  // side by side: the row stays as low as it is
    for (const tall = el.offsetHeight; i < later.length; i++) {
      show(later[i], true);
      if (shown + later[i].length > GLANCE_MIN && el.offsetHeight > tall) { show(later[i], false); break; }
      shown += later[i].length;
    }
  } else for (; i < later.length && shown + later[i].length <= GLANCE_LINES; i++) { show(later[i], true); shown += later[i].length; }
  const note = plans.querySelector('.wghead .muted');
  if (note && beyond != null) { const left = later.slice(i).reduce((n, step) => n + step.filter((x) => !x.classList.contains('gday')).length, 0) + beyond; note.textContent = left ? `+${left} more this week` : ''; }
}

/** A low tile's one line (LOW); an app that is down or closed to this account leaves the line empty. */
export function drawLowLine(tile, line, tz, of = LOW[tile.dataset.app]) {
  wget(`api/widgets/${tile.dataset.app}?tz=${encodeURIComponent(tz)}`)
    .then((r) => (r.ok ? r.body : null))
    .then((d) => {
      if (!d || !line.isConnected) return;
      const [text, warn, title, idle] = of(d);
      tile.classList.toggle('idle', !!idle);  // nothing to report: the dock leaves the line out
      quiet(tile, !!idle);
      line.classList.toggle('wgwarn', !!warn); line.classList.toggle('muted', !warn);
      line.replaceChildren(warn ? icon('warn', 's') : '', text);
      tile.title = title || tile.href;
    })
    .catch(() => { /* the next refresh */ });
}

/** ioDocs in its low tile: "Nothing to renew", "2 to renew", "1 expired +2" (short, to fit the narrow tile); the tooltip names them. */
function drawDocsLine(d) {
  const items = d.items || [], n = items.length + (d.more || 0);
  if (!n) return ['Nothing to renew', false, '', true];
  const expired = items.filter((x) => x.state === 'expired').length;
  const text = expired ? `${expired} expired${n > expired ? ` +${n - expired}` : ''}` : `${n} to renew`;
  const title = items.map((x) => `${x.title}: ${docWhen(x)}`).concat(d.more ? [`+${d.more} more`] : []).join('\n');
  return [text, expired > 0, title];
}

/* An app the person keeps as a low tile (layout sizes: tile): what its card would show, in one line.
   Each gives [text, warn, tooltip, idle] as LOW's do. A badge says the same (static/js/badges.js). */
export const LINES = {
  iocontact: (d) => { const it = (d.items || [])[0]; if (!it) return ['No birthdays soon', false, '', true];
    return [`${it.name.split(/\s+/)[0]}: ${inDays(it.in).toLowerCase()}`, false, (d.items || []).map((x) => `${x.name}: ${inDays(x.in).toLowerCase()}`).join('\n'), it.in > 7]; },
  iopix: (d) => { const n = (d.items || []).length; if (!n) return [EMPTY.iopix, false, '', true];
    return [d.kind === 'onthisday' ? `${d.count || n} from this day` : 'Photos to rediscover', false, '']; },
  iocalendar: (d) => {
    const today = withoutBirthdays(d.today || []), n = today.length + (d.more || 0);
    const names = today.map((o) => `${evTime(o)} ${o.title}`).join('\n');
    if (n) { const next = today.find((o) => !o.allDay && new Date(o.start) > Date.now()); return [`${n} today${next ? ` · next ${evTime(next)}` : ''}`, false, names]; }
    return d.next ? [`Next: ${evDay(d.next)}`, false, `${d.next.title} · ${evDay(d.next)} ${d.next.allDay ? '' : evTime(d.next)}`.trim()] : [EMPTY.iocalendar, false, '', true];
  },
  iotask: (d) => { const today = d.today || [], n = today.length + (d.more || 0); if (!n) return [EMPTY.iotask, false, '', true];
    return [`${n} due today${d.overdue ? ` · ${d.overdue} overdue` : ''}`, !!d.overdue, today.map((t) => t.title).join('\n')]; },
  iohealth: (d) => {
    if (d.steps == null && !d.rings && !d.sleep) return [EMPTY.iohealth, false, '', true];
    const r = d.rings, bits = [d.steps != null ? `${Math.round(d.steps).toLocaleString()} steps` : null, d.steps == null && r && r.moveGoal ? `Move ${Math.round(r.move || 0)}/${Math.round(r.moveGoal)}` : null,
      d.sleep && d.sleep.asleep ? `slept ${hm(d.sleep.asleep)}` : null].filter(Boolean);
    return [bits.join(' · ') || 'Today', false, ''];
  },
  iomoney: (d) => {
    const bills = d.bills || [], low = d.low || [], behind = d.behind || [], all = bills.length + (d.more || 0);
    if (low.length) return [low.length > 1 ? `${low.length} accounts run low` : `Low soon: ${low[0].name}`, true, low.map((x) => x.name).join('\n')];
    if (behind.length) return [behind.length > 1 ? `${behind.length} bank links behind` : `Bank link behind: ${behind[0].name}`, true, behind.map((x) => x.name).join('\n')];
    if (!all) return [EMPTY.iomoney, false, '', true];
    return [`${all} due${d.total != null ? ` · ${money(-d.total, d.currency, { maximumFractionDigits: 0, minimumFractionDigits: 0 })}` : ''}`, false, bills.map((b) => `${b.name}: ${money(-b.amount, b.currency)}`).join('\n')];
  },
  iodocs: drawDocsLine,
};

/** ioDocs: the passports, licenses and policies that have expired or come within their reminder, the soonest first. */
function drawDocsWidget(d) {
  const items = d.items || [];
  if (!items.length) return [wgHead('To renew'), h('div', { class: 'muted small' }, 'Nothing to renew')];
  const head = wgHead('To renew', d.more ? `+${d.more} more` : null);
  return [head, items.map((x) => h('div', { class: `wgev${x.state === 'expired' ? ' wgwarn' : ''}`, title: [x.title, x.kind, x.people.join(', '), docWhen(x)].filter(Boolean).join(' · ') },
    x.state === 'expired' ? icon('warn', 's') : null, h('span', { class: 'wgtitle' }, x.title),
    h('span', { class: 'wgamt muted' }, x.days < 0 ? 'expired' : x.days === 0 ? 'today' : x.days < 60 ? `${x.days}d` : new Date(`${x.expiresOn}T12:00:00`).toLocaleDateString([], { month: 'short', year: '2-digit' }))))];
}

/** Three rings, outside in: move, exercise, stand; each full at its goal (and past it, a second lap is not drawn). */
function rings(r) {
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 64 64'); svg.setAttribute('class', 'wgrings');
  [['move', 27, 'var(--ring-move)'], ['exercise', 19, 'var(--ring-exercise)'], ['stand', 11, 'var(--ring-stand)']].forEach(([k, rad, col]) => {
    const goal = r[`${k}Goal`], v = r[k], frac = goal > 0 && v != null ? Math.min(1, v / goal) : 0, len = 2 * Math.PI * rad;
    for (const [op, dash] of [[0.22, null], [1, frac]]) {
      if (dash === 0) continue;
      const c = document.createElementNS(ns, 'circle');
      c.setAttribute('cx', 32); c.setAttribute('cy', 32); c.setAttribute('r', rad); c.setAttribute('fill', 'none');
      c.setAttribute('stroke', col); c.setAttribute('stroke-width', 7); c.setAttribute('stroke-opacity', op);
      if (dash != null) { c.setAttribute('stroke-linecap', 'round'); c.setAttribute('stroke-dasharray', `${dash * len} ${len}`); c.setAttribute('transform', 'rotate(-90 32 32)'); }
      svg.append(c);
    }
  });
  return svg;
}
/** Seven bars, a day each, the last one today: the week's steps at a glance. */
function sparkline(week) {
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg'), W = 7, G = 3, H = 22;
  svg.setAttribute('viewBox', `0 0 ${week.length * (W + G) - G} ${H}`); svg.setAttribute('class', 'wgspark');
  const top = Math.max(1, ...week.map((x) => x.steps || 0));
  week.forEach((x, i) => {
    const r = document.createElementNS(ns, 'rect'), hgt = x.steps ? Math.max(2, (x.steps / top) * H) : 2;
    r.setAttribute('x', i * (W + G)); r.setAttribute('y', H - hgt); r.setAttribute('width', W); r.setAttribute('height', hgt); r.setAttribute('rx', 1.5);
    r.setAttribute('class', i === week.length - 1 ? 'today' : x.steps ? '' : 'none');
    const t = document.createElementNS(ns, 'title');
    t.textContent = `${new Date(`${x.date}T12:00:00`).toLocaleDateString([], { weekday: 'short' })}: ${x.steps == null ? 'no data' : `${x.steps.toLocaleString()} steps`}`;
    r.append(t); svg.append(r);
  });
  return svg;
}
const hm = (min) => (min >= 60 ? `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')}` : `${min} min`);
function drawHealthWidget(d) {
  if (d.steps == null && !d.rings && !d.sleep) return null;
  const r = d.rings, n = (v) => (v == null ? '–' : Math.round(v).toLocaleString());
  const line = (k, label, unit) => (r && r[`${k}Goal`] ? h('div', { class: 'wgring', title: `${label}: ${n(r[k])} of ${n(r[`${k}Goal`])} ${unit}` },
    h('span', { class: 'dot', style: { background: `var(--ring-${k})` } }), label, h('span', { class: 'muted' }, `${n(r[k])}/${n(r[`${k}Goal`])}`)) : null);
  const week = d.week && d.week.filter((x) => x.steps != null).length > 1 ? d.week : null;
  const when = (iso) => { const t = new Date(iso); return isNaN(t) ? '' : t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); };
  const total = week ? week.reduce((a, x) => a + (x.steps || 0), 0) : 0;
  // the head: "Today", and on its right the steps with the week's bars; under it the rings with their three lines
  // beside them, and the night's sleep as a fourth line (kept short so the row of tiles stays low)
  const steps = d.steps != null ? h('span', { class: 'wgsteps' }, h('span', null, h('b', null, n(d.steps)), ' steps'),
    week ? h('span', { class: 'wgtrend', title: `${n(total)} steps in the last 7 days` }, sparkline(week)) : null) : null;
  const sleep = d.sleep ? h('div', { class: 'wgsleep', title: d.sleep.start && d.sleep.end ? `Asleep ${when(d.sleep.start)} – ${when(d.sleep.end)}${d.sleep.inBed ? `, ${hm(d.sleep.inBed)} in bed` : ''}` : '' },
    h('span', { class: 'dot', style: { background: 'var(--sleep)' } }), 'Sleep', h('span', { class: 'muted' }, hm(d.sleep.asleep), h('span', { class: 'wgunit' }, ' asleep'))) : null;
  return [h('div', { class: 'wghead' }, h('span', null, 'Today'), steps),
    r ? h('div', { class: 'wghealth' }, rings(r), h('div', null, line('move', 'Move', 'kcal'), line('exercise', 'Exercise', 'min'), line('stand', 'Stand', 'h'), sleep)) : sleep];
}

// ------------------------------------------------------------------ what an app says about itself, fetched once per drawing
/** "expired", "expires in 12 days", "until Mar 2028": how a document stands, short (the search box and the ioDocs tile). */
function docWhen(x) {
  if (!x.expiresOn) return '';
  const d = new Date(`${x.expiresOn}T12:00:00`), n = x.days;
  if (n == null) return '';
  if (n < 0) return n === -1 ? 'expired yesterday' : `expired ${d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}`;
  if (n === 0) return 'expires today';
  if (n === 1) return 'expires tomorrow';
  if (n < 60) return `expires in ${n} days`;
  return x.state === 'soon' ? `expires ${d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}` : `until ${d.toLocaleDateString([], { month: 'short', year: 'numeric' })}`;
}

/** /api/widgets/<key>?... as JSON, or null when the app is down, not open to this account, or the answer is not JSON. */
export async function widget(key, params = {}) {
  try {
    const r = await wget(`api/widgets/${key}?${new URLSearchParams({ tz: viewerTz(), ...params })}`);
    return r.ok ? r.body : null;
  } catch { return null; }
}
/** GET of what an app shows on the page: {ok, status, body (its JSON, or null)}. While the page is being arranged, what
    each answered is kept (S.arrange.seen), so moving a tile draws the page again without asking every app again.
    Otherwise an answer serves whoever asks the same within a moment: a card, a badge and a second card of the
    same app drawn together are one question. */
const asked = new Map(), ASKED_FOR = 1500;
/** Before the page brings itself up to date: every app is asked anew. */
export const askAgain = () => asked.clear();
export function wget(url) {
  const A = S.arrange, seen = A ? A.seen : asked;
  const was = seen.get(url);
  if (was && (A || Date.now() - was.at < ASKED_FOR)) return was.got;
  const got = fetch(url, { credentials: 'same-origin' }).then(async (r) => { let body = null; try { body = await r.json(); } catch { /* no JSON */ } return { ok: r.ok, status: r.status, body }; });
  seen.set(url, { got, at: Date.now() });
  got.catch(() => seen.delete(url));
  if (!A) for (const [k, v] of asked) if (Date.now() - v.at > ASKED_FOR) asked.delete(k);
  return got;
}
export const inDays = (n) => (n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : `In ${n} days`);

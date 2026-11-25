import { $, DOW, ICONS, LOCAL_TZ, REFRESH_HOURS, S, addDays, addMonths, api, canOwn, canShared, dialog, fail, h, icon, isAuto, loadCals, memberBadge, memberColor, sameDay, startOfWeek, tasksOn, billsOn, billsOffered, toggleBills, papersOn, papersOffered, togglePapers, toast, toggleCal, toggleTasks, toggleWho, weekStart, writable, ymd } from './core.js';
import * as frame from '../../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { DOCK_MIN, applyTheme, closeNav, closeSuite, openNav, themeChoice, themeFromAccount } from '../../api/auth/frame.js';
export { DOCK_MIN, applyTheme, closeNav, closeSuite, openNav, themeChoice, themeFromAccount };  // the appearance is the suite's one choice
const store = frame.storeFor('iocalendar');  // what this browser remembers for the app
import { go, route } from './main.js';
import { drawView } from './views.js';

// ------------------------------------------------------------------ chrome
export function drawUser() {
  frame.userMenu($('#usermenu'), S.user, api, (close) => [
    frame.menuLink('#/settings/account', 'person', 'Account', close),
    frame.menuLink('#/settings/devices', 'devices', 'Connect apps and devices', close),
    frame.themeEntry(applyTheme, close)]);
}
/* The suite (iosuite_shared's suite_apps): when other ioSuite apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to the calendar. */
export async function loadSuite() { S.suite = await frame.loadSuite(api); drawNav(); }

/** A small month in the sidebar: pick a day to go to it. */
export function miniMonth() {
  const base = S.mini || new Date(S.date.getFullYear(), S.date.getMonth(), 1);
  const first = startOfWeek(base), today = new Date();
  const g = h('div', { class: 'g' }, [0, 1, 2, 3, 4, 5, 6].map((i) => h('span', { class: 'h' }, DOW((i + weekStart()) % 7, 'narrow'))));
  for (let i = 0; i < 42; i++) {
    const d = addDays(first, i);
    g.append(h('span', { class: [d.getMonth() !== base.getMonth() ? 'o' : '', sameDay(d, today) ? 't' : sameDay(d, S.date) ? 'sel' : ''].join(' '),
      onclick: () => go(S.view === 'agenda' ? 'day' : S.view, d) }, d.getDate()));
  }
  return h('div', { class: 'mini' }, h('div', { class: 'mh' },
    h('span', null, base.toLocaleDateString([], { month: 'long', year: 'numeric' })),
    h('span', null, h('button', { class: 'iconbtn', title: 'Previous month', onclick: () => { S.mini = addMonths(base, -1); drawNav(); } }, icon('chevL', 's')),
      h('button', { class: 'iconbtn', title: 'Next month', onclick: () => { S.mini = addMonths(base, 1); drawNav(); } }, icon('chevR', 's')))), g);
}

/* The sidebar, as in ioPix and ioContact: the name on top, the destinations, the calendars (each with its colour as a
   check box that shows or hides it), Settings at the foot. It docks beside the page on a wide screen unless its button
   put it away (remembered); otherwise it slides over the page. Phones get a bottom bar instead. */
export function drawNav() {
  const nav = $('#nav'); const r = route();
  // the sidebar's parts, the same in every app (iosuite_shared/static/frame.js); below them, its own rows
  const { head, link, sec, gap, more } = frame.navParts(store, { name: 'Calendar', title: 'Calendar', redraw: drawNav });
  const calView = ['month', 'week', 'day'].includes(r.view);
  const check = '<svg viewBox="0 0 24 24"><path d="' + ICONS.check + '"/></svg>';
  const calRow = (c) => {
    const ck = h('span', { class: 'ck' }); ck.innerHTML = check;
    return h('a', { href: '#', 'data-v': 'cal', class: `cal ${S.hidden.has(c.id) ? '' : 'shown'}`, title: `${S.hidden.has(c.id) ? 'Show' : 'Hide'} ${c.name}`,
      style: { '--hue': c.color }, onclick: (e) => { e.preventDefault(); toggleCal(c.id); } },
      ck, h('span', { class: 'nl' }, c.name), h('span', { class: 'n' }, isAuto(c) ? '' : c.count || ''));
  };
  const whoRow = (m) => h('a', { href: '#', 'data-v': 'who', class: `who ${S.who.has(m.id) ? 'picked' : ''}`, style: { '--mc': memberColor(m) },
    title: S.who.has(m.id) ? `Stop showing only ${m.displayName}'s events` : `Show only ${m.displayName}'s events`,
    onclick: (e) => { e.preventDefault(); toggleWho(m.id); } }, memberBadge(m, true), h('span', { class: 'nl' }, m.displayName));
  const taskRow = () => {
    const ck = h('span', { class: 'ck' }); ck.innerHTML = check;
    const why = tasksOn() && S.tasks.available === false ? S.tasks.reason : null;
    return h('a', { href: '#', 'data-v': 'cal', class: `cal ${tasksOn() ? 'shown' : ''} ${why ? 'away' : ''}`, style: { '--hue': '#146b5e' },
      title: why || (tasksOn() ? 'Hide the tasks that are due' : 'Show the tasks on the day they are due'),
      onclick: (e) => { e.preventDefault(); toggleTasks(); } }, ck, h('span', { class: 'nl' }, 'Tasks due'));
  };
  const billRow = () => {
    const ck = h('span', { class: 'ck' }); ck.innerHTML = check;
    const why = billsOn() && S.bills.available === false ? S.bills.reason : null;
    return h('a', { href: '#', 'data-v': 'cal', class: `cal ${billsOn() ? 'shown' : ''} ${why ? 'away' : ''}`, style: { '--hue': '#94650a' },
      title: why || (billsOn() ? 'Hide the bills that are due' : 'Show the household’s bills on the day they are due'),
      onclick: (e) => { e.preventDefault(); toggleBills(); } }, ck, h('span', { class: 'nl' }, 'Bills due'));
  };
  const paperRow = () => {
    const ck = h('span', { class: 'ck' }); ck.innerHTML = check;
    const why = papersOn() && S.papers.available === false ? S.papers.reason : null;
    return h('a', { href: '#', 'data-v': 'cal', class: `cal ${papersOn() ? 'shown' : ''} ${why ? 'away' : ''}`, style: { '--hue': '#a03a6a' },
      title: why || (papersOn() ? 'Hide the documents that expire' : 'Show the day a passport, a license or a policy expires'),
      onclick: (e) => { e.preventDefault(); togglePapers(); } }, ck, h('span', { class: 'nl' }, 'Documents expiring'));
  };
  const shared = S.cals.filter((c) => c.shared), mine = S.cals.filter((c) => !c.shared);
  nav.replaceChildren(...[
    head(),
    link('calendar', `#/${S.view === 'agenda' ? 'month' : S.view}/${ymd(S.date)}`, 'today', 'Calendar', null, calView, '--c-rose'),
    link('agenda', '#/agenda', 'agenda', 'Agenda', null, r.view === 'agenda', '--c-blue'),
    more(moreSheet),
    miniMonth(),
    sec('Shared', canShared() ? h('button', { class: 'iconbtn', title: 'New shared calendar', onclick: () => newCalendar(true) }, icon('add', 's')) : null),
    shared.map(calRow),
    S.members.length > 1 ? [gap(),
      sec('Family', S.who.size ? h('button', { class: 'pillbtn noic tiny', title: 'Show everyone again', onclick: () => toggleWho(null) }, 'Everyone') : null),
      S.members.map(whoRow)] : null,
    gap(),
    canOwn() || mine.length ? sec('Mine', canOwn() ? h('button', { class: 'iconbtn', title: 'New private calendar', onclick: () => newCalendar(false) }, icon('add', 's')) : null) : null,
    mine.map(calRow),
    S.status.iotask ? [gap(),
      sec('ioTask', S.tasks.url ? h('a', { class: 'iconbtn', href: S.tasks.url, target: '_blank', rel: 'noopener', title: 'Open ioTask' }, icon('open', 's')) : null),
      taskRow()] : null,
    billsOffered() ? [gap(),
      sec('ioMoney', S.bills.url ? h('a', { class: 'iconbtn', href: S.bills.url, target: '_blank', rel: 'noopener', title: 'Open ioMoney' }, icon('open', 's')) : null),
      billRow()] : null,
    papersOffered() ? [gap(),
      sec('ioDocs', S.papers.url ? h('a', { class: 'iconbtn', href: S.papers.url, target: '_blank', rel: 'noopener', title: 'Open ioDocs' }, icon('open', 's')) : null),
      paperRow()] : null,
    gap(), sec('Manage'),
    writable().some((c) => !isAuto(c)) ? link('import', '#/import', 'upload', 'Import', null, r.view === 'import', '--c-green') : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['import', 'settings', 'search'].includes(r.view));
}
export function applySidebar() { frame.applySidebar(store); }
/** Phones: what the bottom bar has no room for (the calendars to show, import, settings). */
export function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hue, on, click) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hue }, onclick: click || null }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.cals.map((c) => tile('#', S.hidden.has(c.id) ? 'close' : 'check', c.name, c.color, !S.hidden.has(c.id), (e) => { e.preventDefault(); e.stopPropagation(); toggleCal(c.id); document.querySelector('.dialog-back')?.remove(); moreSheet(); })),
    S.members.length > 1 ? S.members.map((m) => tile('#', 'person', S.who.has(m.id) ? `Only ${m.displayName}` : m.displayName, memberColor(m), S.who.has(m.id),
      (e) => { e.preventDefault(); e.stopPropagation(); toggleWho(m.id); document.querySelector('.dialog-back')?.remove(); moreSheet(); })) : null,
    writable().some((c) => !isAuto(c)) ? tile('#/import', 'upload', 'Import', 'var(--c-green)', r.view === 'import') : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { const a = e.target.closest('a'); if (a && a.getAttribute('href') !== '#') document.querySelector('.dialog-back')?.remove(); });
  return p;
}

export const SWATCHES = ['#8e44d6', '#0b8a9e', '#1a73e8', '#e0426a', '#1e8e3e', '#e8710a', '#4b53c7', '#e8a100', '#5f6b7a', '#b5452f'];
export function colorPicker(value, onPick) {
  let cur = value || SWATCHES[0];
  const own = h('input', { type: 'color', value: cur, title: 'Another colour' });
  const row = h('div', { class: 'colors' });
  const draw = () => row.replaceChildren(...SWATCHES.map((c) => h('button', { type: 'button', class: c === cur ? 'on' : '', style: { '--c': c }, title: c, onclick: () => { cur = c; own.value = c; draw(); if (onPick) onPick(c); } })), own);
  own.oninput = () => { cur = own.value; draw(); };
  own.onchange = () => { if (onPick) onPick(cur); };
  draw();
  row.get = () => cur;
  return row;
}
export async function newCalendar(shared) {
  const name = h('input', { class: 't', placeholder: shared ? 'Name, e.g. Soccer or School' : 'Name, e.g. Work' });
  const col = colorPicker(SWATCHES[S.cals.length % SWATCHES.length]);
  // or an outside calendar: its web address (school, sports club, bin collection), fetched again on a schedule
  const url = h('input', { class: 't', type: 'url', inputmode: 'url', autocomplete: 'off', spellcheck: 'false', placeholder: 'https://… or webcal://… (optional)' });
  const every = h('select', { class: 't' }, REFRESH_HOURS.map(([n, l]) => h('option', { value: n, selected: n === 6 ? true : null }, l)));
  const subRow = h('div', { style: { display: 'grid', gap: '6px' }, hidden: true },
    h('label', { class: 'field' }, h('span', null, 'Fetch it again'), every),
    h('p', { class: 'muted small', style: { margin: 0 } }, 'Read-only here: its events change only at the address. Leave the name empty to use the calendar\'s own.'));
  url.oninput = () => { subRow.hidden = !url.value.trim(); name.placeholder = url.value.trim() ? 'Name (optional)' : shared ? 'Name, e.g. Soccer or School' : 'Name, e.g. Work'; };
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, name, col,
    h('label', { class: 'field' }, h('span', null, 'Subscribe to an outside calendar by its web address'), url), subRow,
    h('p', { class: 'muted small', style: { margin: 0 } }, shared ? 'Everyone in the family sees it; editors change it.' : 'Only you see it.'));
  for (;;) {  // a wrong address keeps the dialog's answers for another try
    if (!await dialog(shared ? 'New shared calendar' : 'New private calendar', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
    try {
      if (url.value.trim()) {
        toast('Reading the calendar…');
        const r = await api('api/subscriptions', { method: 'POST', json: { url: url.value.trim(), name: name.value, shared, color: col.get(), refreshHours: Number(every.value) } });
        toast(`${r.calendar.name}: ${r.calendar.count || 0} events`);
      } else {
        await api('api/calendars', { method: 'POST', json: { name: name.value, shared, color: col.get(), timezone: LOCAL_TZ } });
      }
      await loadCals(); drawView(); return;
    } catch (e) { fail(e); }
  }
}

// ------------------------------------------------------------------ sign-in
export function showSignIn() { frame.signInScreen({ api, name: 'Calendar', first: !S.status.usersExist }); }

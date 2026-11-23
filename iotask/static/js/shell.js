import { $, S, api, canOwn, canShared, closeDialogs, dialog, dragSort, fail, h, icon, loadLists, memberBadge, memberColor, store, toggleWho, writable } from './core.js';
import * as frame from '../../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { DOCK_MIN, closeNav, closeSuite, openNav, toggleSuite } from '../../api/auth/frame.js';
export { DOCK_MIN, closeNav, closeSuite, openNav, toggleSuite };
import { route } from './main.js';

// ------------------------------------------------------------------ chrome
export function drawUser() { frame.userMenu($('#usermenu'), S.user, api); }
/* The suite (iosuite_shared's suite_apps): when other ioSuite apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to Today. */
export async function loadSuite() { S.suite = await frame.loadSuite(api); drawNav(); }
export function applyTheme(choice) { frame.applyTheme(store, choice); }

/* The sidebar, as in the other io apps: the name on top, the smart lists, the shared lists, the family, your own lists,
   Settings at the foot. It docks beside the page on a wide screen unless its button put it away (remembered); otherwise
   it slides over the page. Phones get a bottom bar instead. */
export const SMART = { today: ['Today', 'today', '--c-blue'], scheduled: ['Scheduled', 'event', '--c-rose'], all: ['All', 'inbox', '--c-slate'], done: ['Completed', 'done', '--c-green'] };
export function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const listRow = (c) => h('a', { href: `#/list/${c.id}`, 'data-v': 'list', 'data-id': c.id, class: r.view === 'list' && r.id === c.id ? 'on' : null, style: { '--hue': c.color } },
    h('span', { class: 'ldot' }), h('span', { class: 'nl' }, c.name),
    h('span', { class: `n ${c.overdue ? 'late' : ''}`, title: c.overdue ? `${c.overdue} overdue` : null }, c.count || ''));
  const whoRow = (m) => h('a', { href: '#', 'data-v': 'who', class: `who ${S.who.has(m.id) ? 'picked' : ''}`, style: { '--mc': memberColor(m) },
    title: S.who.has(m.id) ? `Stop showing only ${m.displayName}'s tasks` : `Show only ${m.displayName}'s tasks`,
    onclick: (e) => { e.preventDefault(); toggleWho(m.id); } }, memberBadge(m, true), h('span', { class: 'nl' }, m.displayName));
  const shared = S.lists.filter((c) => c.shared), mine = S.lists.filter((c) => !c.shared);
  // the lists of a kind, in the order they were put in: drag one (with a mouse) to move it
  const group = (lists, can) => {
    const g = h('div', { class: 'navgrp' }, lists.map(listRow));
    if (can && lists.length > 1) dragSort(g, 'a', null, orderLists);
    return g;
  };
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Task')];
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioSuite apps', 'aria-label': 'ioSuite apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'Today' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'Today' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    Object.entries(SMART).map(([k, [label, ic, hv]]) => link(k, `#/${k}`, ic, label, k === 'done' ? null : (k === 'today' ? S.counts.today : S.counts[k]) || null, r.view === k, hv)),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    h('div', { class: 'navgap' }),
    sec('Shared', canShared() ? h('button', { class: 'iconbtn', title: 'New shared list', onclick: () => newList(true) }, icon('add', 's')) : null),
    group(shared, canShared()),
    S.members.length > 1 ? [h('div', { class: 'navgap' }),
      sec('Family', S.who.size ? h('button', { class: 'pillbtn noic tiny', title: 'Show everyone again', onclick: () => toggleWho(null) }, 'Everyone') : null),
      S.members.map(whoRow)] : null,
    h('div', { class: 'navgap' }),
    canOwn() || mine.length ? sec('Mine', canOwn() ? h('button', { class: 'iconbtn', title: 'New private list', onclick: () => newList(false) }, icon('add', 's')) : null) : null,
    group(mine, canOwn()),
    h('div', { class: 'navgap' }), sec('Manage'),
    link('activity', '#/activity', 'history', 'Activity', null, r.view === 'activity', '--c-slate'),
    writable().length ? link('import', '#/import', 'upload', 'Import', null, r.view === 'import', '--c-teal') : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['list', 'import', 'settings', 'search', 'activity'].includes(r.view));
}
export async function orderLists(ids) {
  try { await api('api/lists/order', { method: 'POST', json: { ids } }); await loadLists(); } catch (e) { fail(e); drawNav(); }
}
export function applySidebar() { frame.applySidebar(store); }
export function sidebarButton() { frame.sidebarButton(store); }
/** Phones: what the bottom bar has no room for (the lists, the family filter, import, settings). */
export function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on, click) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV }, onclick: click || null }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.lists.map((c) => tile(`#/list/${c.id}`, 'list', c.name, c.color, r.view === 'list' && r.id === c.id)),
    S.members.length > 1 ? S.members.map((m) => tile('#', 'person', S.who.has(m.id) ? `Only ${m.displayName}` : m.displayName, memberColor(m), S.who.has(m.id),
      (e) => { e.preventDefault(); e.stopPropagation(); closeDialogs(); toggleWho(m.id); moreSheet(); })) : null,
    tile('#/activity', 'history', 'Activity', 'var(--c-slate)', r.view === 'activity'),
    writable().length ? tile('#/import', 'upload', 'Import', 'var(--c-teal)', r.view === 'import') : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { const a = e.target.closest('a'); if (a && a.getAttribute('href') !== '#') closeDialogs(); });
  return p;
}

export const SWATCHES = ['#146b5e', '#1a73e8', '#e0426a', '#e8710a', '#8e44d6', '#1e8e3e', '#e8a100', '#b5452f', '#4b53c7', '#5f6b7a'];
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
export async function newList(shared) {
  const name = h('input', { class: 't', placeholder: shared ? 'Name, e.g. Groceries or Chores' : 'Name, e.g. Work' });
  const col = colorPicker(SWATCHES[S.lists.length % SWATCHES.length]);
  const tpls = (await api('api/templates').catch(() => ({ items: [] }))).items;
  const from = h('select', { class: 't' }, h('option', { value: '' }, 'An empty list'), tpls.map((t) => h('option', { value: t.id }, `The template ${t.name} (${t.count} tasks)`)));
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, name, col, tpls.length ? h('label', { class: 'field' }, h('span', null, 'Start with'), from) : null,
    h('p', { class: 'muted small', style: { margin: 0 } }, shared ? 'Everyone in the family sees it and ticks tasks off; editors change it.' : 'Only you see it.'));
  if (!await dialog(shared ? 'New shared list' : 'New private list', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
  try {
    const picked = tpls.find((t) => t.id === +from.value);
    const r = await api('api/lists', { method: 'POST', json: { name: name.value || (picked ? picked.name : ''), shared, color: col.get() } });
    if (picked) await api(`api/templates/${picked.id}/apply`, { method: 'POST', json: { listId: r.list.id } });
    await loadLists();
    location.hash = `#/list/${r.list.id}`;
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ sign-in
export function showSignIn() { frame.signInScreen({ api, name: 'Task', first: !S.status.usersExist }); }

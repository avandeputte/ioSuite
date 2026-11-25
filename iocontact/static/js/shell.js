import { $, S, api, dialog, fail, h, icon, loadMeta } from './core.js';
import * as frame from '../../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { DOCK_MIN, applyTheme, closeNav, closeSuite, openNav, themeChoice, themeFromAccount } from '../../api/auth/frame.js';
export { DOCK_MIN, applyTheme, closeNav, closeSuite, openNav, themeChoice, themeFromAccount };  // the appearance is the suite's one choice
const store = frame.storeFor('iocontact');  // what this browser remembers for the app
import { route } from './main.js';

// ------------------------------------------------------------------ chrome
export function drawUser() {
  frame.userMenu($('#usermenu'), S.user, api, (close) => [
    frame.menuLink('#/settings/account', 'person', 'Account', close),
    frame.menuLink('#/settings/devices', 'devices', 'Connect apps and devices', close),
    frame.themeEntry(applyTheme, close)]);
}
/* The suite (iosuite_shared's suite_apps): when other ioSuite apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to All contacts. */
export async function loadSuite() { S.suite = await frame.loadSuite(api); drawNav(); }

/* The sidebar, as in ioPix: the name on top, the destinations in groups, Settings at the foot. It docks
   beside the page on a wide screen unless its button put it away (remembered); otherwise it slides over the page from the
   menu button. Phones get a bottom bar instead: four destinations and More. */
export function drawNav() {
  const nav = $('#nav'); const r = route();
  // the sidebar's parts, the same in every app (iosuite_shared/static/frame.js); below them, its own rows
  const { head, link, sec, gap, more } = frame.navParts(store, { name: 'Contact', title: 'All contacts', redraw: drawNav });
  const listView = ['list', 'contact', 'edit', 'new'].includes(r.view);
  const total = S.books.reduce((a, b) => a + (b.count || 0), 0);
  nav.replaceChildren(...[
    head(),
    link('all', '#/', 'people', 'All contacts', total, listView && S.scope.kind === 'all', '--c-purple'),
    link('fav', '#/fav', 'star', 'Favorites', null, listView && S.scope.kind === 'fav', '--c-amber'),
    link('upcoming', '#/upcoming', 'cake', 'Birthdays', null, r.view === 'upcoming', '--c-rose'),
    S.status.iopix ? link('iopix', '#/iopix', 'image', 'ioPix people', null, r.view === 'iopix', '--c-indigo') : null,
    more(moreSheet),
    gap(),
    sec('Address books', canOwn() ? h('button', { class: 'iconbtn', title: 'New address book', onclick: newBook }, icon('add', 's')) : null),
    S.books.map((b) => h('a', { href: `#/book/${b.id}`, 'data-v': 'book', class: listView && S.scope.kind === 'book' && +S.scope.id === b.id ? 'on' : null,
      style: { '--hue': b.color || (b.shared ? 'var(--c-purple)' : 'var(--c-teal)') } },
      h('span', { class: 'ic dotic' }, h('span', { class: 'dot' })), h('span', { class: 'nl' }, b.name), h('span', { class: 'n' }, b.count))),
    S.tags.length ? [gap(), sec('Labels'),
      S.tags.map((t) => h('a', { href: `#/tag/${encodeURIComponent(t.tag)}`, 'data-v': 'tag', class: listView && S.scope.kind === 'tag' && S.scope.name === t.tag ? 'on' : null, style: { '--hue': 'var(--c-orange)' } },
        icon('tag'), h('span', { class: 'nl' }, t.tag), h('span', { class: 'n' }, t.n)))] : null,
    gap(), sec('Manage'),
    link('import', '#/import', 'upload', 'Import and export', null, r.view === 'import', '--c-green'),
    link('cleanup', '#/cleanup', 'wrench', 'Clean up', S.status.suggestions || null, r.view === 'cleanup', '--c-amber'),
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['book', 'tag', 'import', 'cleanup', 'settings', 'iopix'].some((v) => (v === 'book' || v === 'tag') ? listView && S.scope.kind === v : r.view === v));
}
export function applySidebar() { frame.applySidebar(store); }
/** Phones: what the bottom bar has no room for. */
export function moreSheet() {
  const r = route(); const listView = ['list', 'contact', 'edit', 'new'].includes(r.view);
  const tile = (href, ic, label, hue, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hue } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.books.map((b) => tile(`#/book/${b.id}`, 'book', b.name, b.color || (b.shared ? 'var(--c-purple)' : 'var(--c-teal)'), listView && S.scope.kind === 'book' && +S.scope.id === b.id)),
    S.tags.map((t) => tile(`#/tag/${encodeURIComponent(t.tag)}`, 'tag', t.tag, 'var(--c-orange)', listView && S.scope.kind === 'tag' && S.scope.name === t.tag)),
    S.status.iopix ? tile('#/iopix', 'image', 'ioPix people', 'var(--c-indigo)', r.view === 'iopix') : null,
    tile('#/import', 'upload', 'Import and export', 'var(--c-green)', r.view === 'import'),
    tile('#/cleanup', 'wrench', 'Clean up', 'var(--c-amber)', r.view === 'cleanup'),
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) document.querySelector('.dialog-back')?.remove(); });
  return p;
}

// the suite's roles, each able to do what the one before can: a viewer only looks, a member keeps their own books,
// an editor changes the shared ones too
export const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
export const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
export const canOwn = () => roleAtLeast('member');
export const canShared = () => roleAtLeast('editor');

export async function newBook() {
  const name = h('input', { class: 't', placeholder: 'Name, e.g. Work or School friends' });
  const shared = h('input', { type: 'checkbox' });
  const body = h('div', null, name, canShared() ? h('label', { class: 'prefck', style: { marginTop: '10px' } }, shared, 'Shared with the whole family') : null);
  if (!await dialog('New address book', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
  try { const r = await api('api/books', { method: 'POST', json: { name: name.value, shared: shared.checked } }); await loadMeta(); location.hash = `#/book/${r.book.id}`; } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ sign-in
/** The sign-in screen: the suite's, with the picture of the account's own contact on its tile where it has one. */
export function showSignIn() {
  frame.signInScreen({ api, name: 'Contact', first: !S.status.usersExist, face: (a, letters) => {
    const el = letters(a);
    if (a.meContactId) { const img = h('img', { src: `api/auth/accounts/${a.id}/photo`, alt: '', onerror: () => img.remove() }); el.append(img); }
    return el;
  } });
}

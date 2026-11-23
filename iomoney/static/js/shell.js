/* Around the pages: the sidebar with its views, the account menu, the suite menu, the theme. */
import * as frame from '../../api/auth/frame.js';
import { closeDialogs, dialog, icon, toggleSuite } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { $, api, behindMark, byGroup, canAdd, KIND_LOOK, may, S, store, THINGS } from './core.js';
import { accountDialog } from './account.js';
import { route } from './main.js';

// ------------------------------------------------------------------ the sidebar
/* The sidebar, as in the other io apps: the name on top, the pages (overview, transactions, spending, portfolio,
   house and cars), the accounts by kind, Settings at the foot. It docks beside the page on a wide screen unless its
   button put it away (remembered); otherwise it slides over the page. Phones get a bottom bar instead. */
const VIEWS = { overview: ['Overview', 'dashboard', '--c-amber'], transactions: ['Transactions', 'receipt', '--c-blue'],
  spending: ['Spending', 'pie', '--c-rose'], portfolio: ['Portfolio', 'trend', '--c-indigo'], assets: ['Assets', 'home', '--c-orange'],
  recurring: ['Recurring', 'repeat', '--c-green'], tidy: ['Tidy up', 'tidy', '--c-purple'], rules: ['Rules', 'tune', '--c-teal'] };
/** A search as its address has it, whatever the order of its filters: to tell whether two are the same. */
export const sameSearch = (a, b) => { const n = (x) => [...new URLSearchParams(x)].filter(([k, v]) => k !== 'offset' && v).map(([k, v]) => `${k}=${v}`).sort().join('&'); return n(a) === n(b); };
const TIDY_VIEWS = ['tidy', 'review', 'payees', 'duplicates', 'balance', 'changes', 'transfers'];
export function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n != null ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Money')];
  const shown = S.accounts.filter((a) => !a.hidden && !a.closed);
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioSuite apps', 'aria-label': 'ioSuite apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'Overview' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'Overview' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    Object.entries(VIEWS).filter(([k]) => k !== 'assets' || shown.some((a) => THINGS.includes(a.kind)) || canAdd())
      .map(([k, [label, ic, hv]]) => [link(k, k === 'overview' ? '#/' : `#/${k}`, ic, label,
        k === 'recurring' && S.sum && S.sum.recurringFlags ? S.sum.recurringFlags : k === 'tidy' && S.sum && S.sum.review ? S.sum.review : null,
        r.view === k || (k === 'tidy' && TIDY_VIEWS.includes(r.view)), hv),
      // a person's saved searches, under Transactions
      k === 'transactions' ? S.searches.map((x) => link('acct', `#/transactions?${x.query}`, 'bookmark', x.name, null, r.view === 'transactions' && sameSearch(x.query, new URLSearchParams(r.q || {})), '--c-blue')) : null]),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    byGroup(shown).map((g) => [h('div', { class: 'navgap' }), sec(g.label),
      g.list.map((a) => behindMark(link('acct', `#/account/${a.id}`, a.household ? KIND_LOOK[a.kind][0] : 'lock', a.name, null, r.view === 'account' && r.id === a.id, KIND_LOOK[a.kind][1]), a))]),
    canAdd() ? [h('div', { class: 'navgap' }), link('acct', '#/accounts/new', 'add', 'Add an account', null, false, '--c-green')] : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(4).filter(Boolean));
  nav.querySelector('a[href="#/accounts/new"]')?.addEventListener('click', (e) => { e.preventDefault(); accountDialog(); });
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['assets', 'rules', 'account', 'settings', 'categories', ...TIDY_VIEWS].includes(r.view));
}
/** Phones: what the bottom bar has no room for (the assets, the rules, the accounts, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    tile('#/assets', 'home', 'Assets', 'var(--c-orange)', r.view === 'assets'),
    tile('#/recurring', 'repeat', 'Recurring', 'var(--c-green)', r.view === 'recurring'),
    tile('#/tidy', 'tidy', 'Tidy up', 'var(--c-purple)', TIDY_VIEWS.includes(r.view)),
    tile('#/rules', 'tune', 'Rules', 'var(--c-teal)', r.view === 'rules'),
    tile('#/categories', 'list', 'Categories', 'var(--c-purple)', r.view === 'categories'),
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'),
    S.accounts.filter((a) => !a.hidden && !a.closed).map((a) => tile(`#/account/${a.id}`, KIND_LOOK[a.kind][0], a.name, `var(${KIND_LOOK[a.kind][1]})`, r.view === 'account' && r.id === a.id)));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) closeDialogs(); });
  return p;
}

// ------------------------------------------------------------------ chrome
export function drawUser() { frame.userMenu($('#usermenu'), S.user, api); }
/* The suite (iosuite_shared's suite_apps): when other ioSuite apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to the overview. */
export async function loadSuite() { S.suite = await frame.loadSuite(api); drawNav(); }
export function applyTheme(choice) { frame.applyTheme(store, choice); }

/* The sidebar docks beside the page on a wide screen unless its button put it away (remembered); otherwise it slides
   over the page. */
export function applySidebar() { frame.applySidebar(store); }
function sidebarButton() { frame.sidebarButton(store); }

// ------------------------------------------------------------------ the summary and the accounts, fetched again when something changed
export async function refreshSummary() {
  try { S.sum = await api('api/summary'); } catch { /* the page says so */ }
  try { S.accounts = (await api('api/accounts?hidden=true')).items || []; } catch { S.accounts = []; }
  try { S.searches = may('read') ? (await api('api/searches')).items || [] : []; } catch { S.searches = []; }
  drawNav();
}

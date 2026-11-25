/* The routes and the start. */
import { closeDialogs, closeMenu, closeNav, fail, icon, menuOpen, openNav, popMenu, put } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { $, api, canAdd, followsTx, may, S, showSignIn, thisMonth } from './core.js';
import { accountDialog, showAccount } from './account.js';
import { showCategories, showSpending } from './categories.js';
import { showOverview } from './overview.js';
import { holdingDialog, showAssets, showPortfolio } from './portfolio.js';
import { showBalance } from './reconcile.js';
import { showRecurring } from './recurring.js';
import { showRules, showTransfers } from './rules.js';
import { showSettings } from './settings.js';
import { applySidebar, applyTheme, drawNav, drawUser, loadSuite, refreshSummary, themeFromAccount } from './shell.js';
import { showChanges, showDuplicates, showPayees, showReview, showTidy } from './tidy.js';
import { showTransaction, showTransactions, txDialog } from './transactions.js';

// ------------------------------------------------------------------ routing
export function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query] = raw.split('?');
  const p = path.split('/').map((x) => { try { return decodeURIComponent(x); } catch { return x; } });
  const q = Object.fromEntries(new URLSearchParams(query || ''));
  const [a, b, c] = p;
  if (!a) return { view: 'overview' };
  if (a === 'transactions') return { view: 'transactions', q };
  if (a === 'transaction' && +b) return { view: 'transaction', id: +b };
  if (a === 'spending') return { view: 'spending', month: /^\d{4}-\d{2}$/.test(b || '') ? b : thisMonth() };
  if (a === 'portfolio') return { view: 'portfolio' };
  if (a === 'assets') return { view: 'assets' };
  if (a === 'rules') return { view: 'rules' };
  if (a === 'recurring') return { view: 'recurring' };
  if (a === 'categories') return { view: 'categories' };
  if (a === 'transfers') return { view: 'transfers', q };
  if (['tidy', 'review', 'payees', 'duplicates', 'balance', 'changes'].includes(a)) return { view: a, q };
  if (a === 'account' && b) return { view: 'account', id: +b, tab: c };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'overview' };
}

export async function onRoute(keep) {
  const r = route();
  const main = $('#main');
  const top = keep === true ? main.scrollTop : null;   // drawn again because something changed elsewhere: stay where the page was
  closeMenu();
  try {
    const page = h('div', { class: 'page wide' });
    if (!may('read') && r.view !== 'settings') noRole(page);
    else await ({ overview: showOverview, transactions: showTransactions, spending: showSpending, portfolio: showPortfolio,
      assets: showAssets, rules: showRules, transaction: showTransaction, transfers: showTransfers, recurring: showRecurring, categories: showCategories, account: showAccount, settings: showSettings,
      tidy: showTidy, review: showReview, payees: showPayees, duplicates: showDuplicates, balance: showBalance, changes: showChanges })[r.view](page, r);
    main.replaceChildren(page);
    if (top !== null) main.scrollTop = top;
    else if (!r.keepScroll) main.scrollTop = 0;
  } catch (e) { main.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'empty' }, icon('warning'), h('p', null, e.message || String(e)), h('p', null, h('a', { class: 'lnk', href: '#/' }, 'Overview'))))); }
  drawNav();
}
function noRole(page) {
  put(page, h('div', { class: 'empty' }, icon('lock'), h('p', null, 'You have no role in ioMoney yet.'),
    h('p', { class: 'muted' }, 'The household’s finances are shown only to the people given a role here: a suite admin gives one in Settings › People › Roles.')));
}

// ------------------------------------------------------------------ start
async function start() {
  applyTheme();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
  S.status = await api('api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('api/auth/me')).settings || {}; } catch { S.settings = {}; }
  themeFromAccount(S.settings);
  drawUser();
  await refreshSummary();
  const nb = $('#newbtn');
  nb.hidden = !canAdd();
  nb.onclick = () => popMenu(nb, [['bank', 'An account', accountDialog],
    S.accounts.some((a) => a.writable && followsTx(a)) ? ['receipt', 'A transaction', () => txDialog()] : null,
    S.accounts.some((a) => a.kind === 'investment' && a.source === 'manual' && a.writable) ? ['trend', 'A holding', () => holdingDialog(null)] : null]);
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  const q = $('#q');
  q.hidden = !may('read'); $('#search').hidden = !may('read');
  let t;
  q.addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      const v = e.target.value.trim();
      if (v) location.hash = `#/transactions?${new URLSearchParams({ q: v })}`;
      else if (route().view === 'transactions') location.hash = '#/transactions';
    }, 300);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (menuOpen()) closeMenu(); else if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin, .dialog-back')) return;
    if (e.key === '/') { e.preventDefault(); q.focus(); }
  });
  addEventListener('hashchange', () => { document.title = 'ioMoney'; closeDialogs(); onRoute(); });
  await onRoute();
  loadSuite();
  // what changed elsewhere shows by itself: a sync with Monarch Money, another person, an assistant (the suite's one
  // live stream, iosuite_shared/static/live.js); a page with work in progress on it (ticked rows, a form, tidying up)
  // is left alone
  const FRESH = ['overview', 'transactions', 'spending', 'portfolio', 'assets', 'account', 'recurring', 'transfers', 'transaction', 'balance', 'changes'];
  import(new URL('api/live.js', document.baseURI).href)
    .then((live) => live.keepFresh('iomoney', async () => { await refreshSummary(); await onRoute(true); },
      { when: () => FRESH.includes(route().view) && !$('#main').querySelector('input[type="checkbox"]:checked') }))
    .catch(() => { /* no stream on this server */ });
}
start().catch(fail);

/* More pages than one: each laid out by itself, a tab each under the top row (iostart/layout.py pages). */
import { confirmDialog, dialog, fld, icon, popMenu } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { newId, S } from './core.js';
import { whenDialog, whenOk, whenText } from './when.js';

// ------------------------------------------------------------------ a setup's pages
/* The first page is the setup itself (its name: `name`, else "Home"), the others are in `pages`, each with what a page
   holds by itself (PAGE); the rest of a setup (the colour, the units, the photo strip, the wall display) is the
   person's, the same on every page. A page is at #/p/<id>, the first at #/. */
export const PAGE = ['hidden', 'order', 'cards', 'style', 'sizes', 'todayOff', 'todayDays', 'bookmarks', 'grid', 'whens', 'badges'];
export const PAGES_MOST = 8;  // with the first
export const BLANK = () => ({ hidden: [], order: [], cards: [], style: null, sizes: {}, todayOff: [], todayDays: null, bookmarks: null, grid: null, whens: {}, badges: [] });
const copy = (v) => JSON.parse(JSON.stringify(v));
const own = (src) => Object.fromEntries(PAGE.map((k) => [k, src[k] === undefined ? BLANK()[k] : src[k]]));

/** [{id ('' the first), name, when}] in order. */
export const pagesOf = (full) => [{ id: '', name: (full && full.name) || 'Home' }, ...((full && full.pages) || []).map((p) => ({ id: p.id, name: p.name || 'Page', when: p.when || null }))];
/** The id of the page an address asks for, when the setup has it; else the first. */
export const pageId = (full, id) => (id && ((full && full.pages) || []).some((p) => p.id === id) ? id : '');
/** The setup as one of its pages sees it: the person's part, with that page's own. A copy: changing it changes nothing
    until it is put back (putPage). */
export function pageView(full, id) {
  const p = id ? (full.pages || []).find((x) => x.id === id) : null;
  return copy({ ...full, ...(p ? own(p) : {}) });
}
/** Puts what a page holds by itself (taken from `view`) back in the setup. */
export function putPage(full, id, view) {
  const p = id ? (full.pages || []).find((x) => x.id === id) : full;
  if (p) Object.assign(p, copy(own(view)));
  return full;
}
/** The pages that have a tab now: the first always, another unless its rule keeps it off (it still opens at its address). */
export const tabsOf = (full) => pagesOf(full).filter((p) => !p.id || whenOk(p.when));
export const pageHref = (id) => (id ? `#/p/${id}` : '#/');

// ------------------------------------------------------------------ the tabs
/** The row of tabs: there with more pages than one. While the page is arranged (A: S.arrange, whose `full` is the copy
    being worked on), every page has its tab, the one shown has a menu (rename, move, when it shows, remove), and a
    last tab adds a page. `go(id, commit)` shows another page (commit false: what the page shown holds is in `full`
    already); `redraw()` draws this one again after a change; `commit()` puts what the page shown holds into `full`. */
export function pageTabs(full, cur, { A, go, redraw, commit } = {}) {
  const all = pagesOf(full), shown = A ? all : tabsOf(full);
  if (!A && shown.length < 2) return null;
  const tab = (p) => {
    const on = p.id === cur;
    const a = h('a', { class: `ptab${on ? ' on' : ''}`, href: pageHref(p.id), 'aria-current': on ? 'page' : null, title: !p.id || !p.when ? null : `Shows: ${whenText(p.when)}`,
      onclick: A ? (e) => { e.preventDefault(); if (!on) go(p.id); } : null }, h('span', null, p.name), A && p.when ? icon('schedule', 's') : null);
    if (!A || !on) return a;
    const i = all.findIndex((x) => x.id === p.id);
    const move = (by) => () => { commit(); go(movePage(full, p.id, by), false); };
    const more = h('button', { class: 'ptabmore', title: `${p.name}: rename, move, remove`, 'aria-label': `${p.name}: rename, move, remove`, onclick: () => popMenu(more, [
      ['edit', 'Rename', async () => { const n = await askName('Rename the page', p.name); if (n) { renamePage(full, p.id, n); redraw(); } }],
      i > 0 ? ['left', 'Move left', move(-1)] : null,
      i < all.length - 1 ? ['right', 'Move right', move(1)] : null,
      p.id ? ['schedule', p.when ? `Shows: ${whenText(p.when)}` : 'Show its tab only when…', async () => { const r = await whenDialog(`the tab of ${p.name}`, p.when, { content: false }); if (r) { const q = full.pages.find((x) => x.id === p.id); if (r.when) q.when = r.when; else delete q.when; redraw(); } }] : null,
      p.id ? ['delete', 'Remove this page', async () => { if (await confirmDialog(`Remove ${p.name}`, 'The page goes with everything laid out on it. Nothing is lost in the apps themselves.', 'Remove', true)) { full.pages = full.pages.filter((x) => x.id !== p.id); go('', false); } }] : null,
    ]) }, icon('more', 's'));
    return h('span', { class: 'ptabwrap' }, a, more);
  };
  const add = A && all.length < PAGES_MOST ? h('button', { class: 'ptab ptabadd', title: 'Another page, laid out by itself', onclick: async () => {
    const n = await askName('A new page', '', 'It gets a tab under the top row and an address of its own, so a device can open on it.');
    if (!n) return;
    const p = { id: newId(6), name: n, ...BLANK() };
    full.pages = [...(full.pages || []), p]; go(p.id);
  } }, icon('add', 's'), 'Page') : null;
  return h('nav', { class: `pagetabs${A ? ' arrok' : ''}`, 'aria-label': 'Pages' }, [...shown.map(tab), add].filter(Boolean));
}
export async function askName(title, was, hint) {
  const name = h('input', { class: 't', maxlength: 30, value: was, placeholder: 'Kitchen' });
  const ok = await dialog(title, h('div', null, fld('Its name', name, hint)), [{ label: 'Cancel', value: false }, { label: 'OK', value: true, primary: true }]);
  return ok ? name.value.replace(/\s+/g, ' ').trim() : '';
}
export function renamePage(full, id, name) {
  if (id) full.pages.find((x) => x.id === id).name = name; else full.name = name === 'Home' ? null : name;
}
/** A page one place to the left (-1) or to the right, and the id it has afterwards. The first page's place is the
    setup's own (its address is #/): a page that moves there trades what it holds, and its name, with the first. */
export function movePage(full, id, by) {
  const ps = full.pages || [], i = ps.findIndex((x) => x.id === id);  // -1: the first page
  const j = i + by;
  if (j < -1 || j >= ps.length || i === j) return id;
  const trade = (p) => { const mine = own(full), name = full.name; Object.assign(full, copy(own(p))); full.name = p.name === 'Home' ? null : p.name; Object.assign(p, copy(mine)); p.name = name || 'Home'; };
  if (i === -1) { trade(ps[0]); return ps[0].id; }
  if (j === -1) { trade(ps[i]); return ''; }
  const [p] = ps.splice(i, 1); ps.splice(j, 0, p);
  return id;
}

// ------------------------------------------------------------------ a swipe to the next page
/** On a touch screen, a swipe to the side on the page goes to the next tab (not one that starts on something that
    scrolls sideways itself: the photo strip, a row of tabs). */
export function swipePages(page, full, cur) {
  const tabs = tabsOf(full);
  if (tabs.length < 2) return;
  let x0 = 0, y0 = 0, t0 = 0, ok = false;
  const sideways = (el) => { for (; el && el !== page; el = el.parentElement) { if (el.scrollWidth > el.clientWidth + 4 && /(auto|scroll)/.test(getComputedStyle(el).overflowX)) return true; } return false; };
  page.addEventListener('touchstart', (e) => { const t = e.touches[0]; ok = e.touches.length === 1 && !S.arrange && !sideways(e.target) && !e.target.closest('input, select, textarea, [role="slider"]'); x0 = t.clientX; y0 = t.clientY; t0 = Date.now(); }, { passive: true });
  page.addEventListener('touchend', (e) => {
    if (!ok) return;
    const t = e.changedTouches[0], dx = t.clientX - x0, dy = t.clientY - y0;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 2 || Date.now() - t0 > 600) return;
    const i = Math.max(0, tabs.findIndex((p) => p.id === cur)), to = tabs[i + (dx < 0 ? 1 : -1)];
    if (to) location.hash = pageHref(to.id);
  }, { passive: true });
}

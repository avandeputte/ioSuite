/* ioRecipe web app: one module, no build step. The recipes as cards (all of them, the family's, your own, your
   favourites, by tag, by cookbook, found by words); one recipe with its photos, ingredients to tick off while cooking
   (for the servings you want), numbered steps with their pictures, your rating, its cookbooks, the shopping list and
   a print view; the form to add or change one; import (a web page, pasted text, a photo, a file) and export; and
   settings (account, display, and for admins server, and for suite admins security and global settings), laid out as
   in the other ioSuite apps. */
import { client, h, safeUrl } from '../api/auth/ui.js';  // the suite's shared helpers (iosuite_shared/static/account-panel.js)
import * as frame from '../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { accountUi, addIcons, closeDialogs, closeMenu, closeNav, confirmDialog, dialog, fail, fill, fld, hue, icon, menuOpen, openNav, popMenu, put, toast, toggleSuite } from '../api/auth/frame.js';
const api = client(document.baseURI, { signIn: () => showSignIn() });

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
addIcons({
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  book: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z',
  tag: 'M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z',
  timer: 'M15 1H9v2h6V1zm-4 13h2V8h-2v6zm8.03-6.61 1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A8.962 8.962 0 0 0 12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9a8.994 8.994 0 0 0 7.03-14.61zM12 20c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z',
  dish: 'M8.1 13.34l2.83-2.83L3.91 3.5a4.008 4.008 0 0 0 0 5.66l4.19 4.18zm6.78-1.81c1.53.71 3.68.21 5.27-1.38 1.91-1.91 2.28-4.65.81-6.12-1.46-1.46-4.2-1.1-6.12.81-1.59 1.59-2.09 3.74-1.38 5.27L3.7 19.87l1.41 1.41L12 14.41l6.88 6.88 1.41-1.41L13.41 13l1.47-1.47z',
  favorite: 'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z',
  favoriteBorder: 'M16.5 3c-1.74 0-3.41.81-4.5 2.09C10.91 3.81 9.24 3 7.5 3 4.42 3 2 5.42 2 8.5c0 3.78 3.4 6.86 8.55 11.54L12 21.35l1.45-1.32C18.6 15.36 22 12.28 22 8.5 22 5.42 19.58 3 16.5 3zm-4.4 15.55l-.1.1-.1-.1C7.14 14.24 4 11.39 4 8.5 4 6.5 5.5 5 7.5 5c1.54 0 3.04.99 3.57 2.36h1.87C13.46 5.99 14.96 5 16.5 5c2 0 3.5 1.5 3.5 3.5 0 2.89-3.14 5.74-7.9 10.05z',
  star: 'M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z',
  starBorder: 'M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z',
  cart: 'M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49A1.003 1.003 0 0 0 20 4H5.21l-.94-2H1zm16 16c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2z',
  camera: 'M3 4V1h2v3h3v2H5v3H3V6H0V4h3zm3 6V7h3V4h7l1.83 2H21c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V10h3zm7 9c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5zm-3.2-5c0 1.77 1.43 3.2 3.2 3.2s3.2-1.43 3.2-3.2-1.43-3.2-3.2-3.2-3.2 1.43-3.2 3.2z',
  books: 'M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 10l-2.5-1.5L15 12V4h5v8z',
  text: 'M3 18h12v-2H3v2zM3 6v2h18V6H3zm0 7h18v-2H3v2z',
  file: 'M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
});


const store = frame.storeFor('iorecipe');

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, counts: {}, tags: [], books: [], draft: null };
// the suite's roles, each able to do what the one before can: a viewer only looks, a member keeps recipes of their
// own, an editor changes the family's too
const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
const canOwn = () => roleAtLeast('member');
const canFamily = () => roleAtLeast('editor');
const canAdd = () => canOwn() || canFamily();
/** What goes around the recipes: how many, the tags, the cookbooks (every list of recipes brings them along). */
function around(d) { S.counts = d.counts; S.tags = d.tags; S.books = d.books || []; }
async function refreshAround() { try { around(await api('api/summary')); } catch { /* the page says so */ } drawNav(); }
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}
/** Minutes as people say them: 45 min, 1 h, 1 h 35 min. */
function fmtMin(n) {
  if (!n) return '';
  const hh = Math.floor(n / 60), mm = n % 60;
  return [hh ? `${hh} h` : '', mm ? `${mm} min` : ''].filter(Boolean).join(' ');
}

// ------------------------------------------------------------------ chrome
function drawUser() { frame.userMenu($('#usermenu'), S.user, api); }
/* The suite (iosuite_shared's suite_apps): when other ioSuite apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to all the recipes. */
async function loadSuite() { S.suite = await frame.loadSuite(api); drawNav(); }
function applyTheme(choice) { frame.applyTheme(store, choice); }

/* The sidebar, as in the other io apps: the name on top, the recipes (all, the family's, your own, your favourites),
   the cookbooks, the tags, adding and import, Settings at the foot. It docks beside the page on a wide screen unless its button put it away (remembered);
   otherwise it slides over the page. Phones get a bottom bar instead. */
const VIEWS = { all: ['All recipes', 'book', '--c-green'], family: ['Family', 'home', '--c-orange'], mine: ['Mine', 'lock', '--c-blue'],
  favourites: ['Favourites', 'favorite', '--c-rose'] };
const viewShown = (k) => (k !== 'mine' && k !== 'favourites') || canOwn() || !!S.counts[k];
function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label) => h('div', { class: 'navsec' }, h('span', null, label));
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Recipe')];
  const shown = Object.entries(VIEWS).filter(([k]) => viewShown(k));
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioSuite apps', 'aria-label': 'ioSuite apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'All recipes' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'All recipes' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    shown.map(([k, [label, ic, hv]]) => link(k, `#/${k}`, ic, label, S.counts[k] || null, r.view === k, hv)),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    S.books.length || canOwn() ? [h('div', { class: 'navgap' }),
      h('div', { class: 'navsec' }, h('span', null, 'Cookbooks'),
        canOwn() ? h('button', { class: 'iconbtn', title: 'New cookbook', 'aria-label': 'New cookbook', onclick: () => newBook() }, icon('add', 's')) : null),
      S.books.map((b) => link('book', `#/book/${b.id}`, b.family ? 'books' : 'lock', b.name, b.count || null, r.view === 'book' && r.id === b.id, b.family ? '--c-amber' : '--c-blue'))] : null,
    S.tags.length ? [h('div', { class: 'navgap' }), sec('Tags'),
      S.tags.slice(0, 14).map((t) => link('tag', `#/tag/${encodeURIComponent(t.tag)}`, 'tag', t.tag, t.count, r.view === 'tag' && r.tag.toLowerCase() === t.tag.toLowerCase(), '--c-slate'))] : null,
    canAdd() ? [h('div', { class: 'navgap' }), sec('Add'),
      link('new', '#/new', 'add', 'New recipe', null, r.view === 'new', '--c-green'),
      link('import', '#/import', 'download', 'Import and export', null, r.view === 'import', '--c-teal')] : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['tag', 'book', 'import', 'new', 'settings', 'search'].includes(r.view));
}
function applySidebar() { frame.applySidebar(store); }
function sidebarButton() { frame.sidebarButton(store); }

/** Phones: what the bottom bar has no room for (the cookbooks, the tags, adding, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    canAdd() ? [tile('#/new', 'add', 'New recipe', 'var(--c-green)', r.view === 'new'), tile('#/import', 'globe', 'Import', 'var(--c-teal)', r.view === 'import')] : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'),
    S.books.map((b) => tile(`#/book/${b.id}`, b.family ? 'books' : 'lock', b.name, b.family ? 'var(--c-amber)' : 'var(--c-blue)', r.view === 'book' && r.id === b.id)),
    S.tags.slice(0, 18).map((t) => tile(`#/tag/${encodeURIComponent(t.tag)}`, 'tag', t.tag, 'var(--c-slate)', r.view === 'tag' && r.tag === t.tag)));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) closeDialogs(); });
  return p;
}

// ------------------------------------------------------------------ routing
function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const p = raw.split('?')[0].split('/').map((x) => { try { return decodeURIComponent(x); } catch { return x; } });
  const [a, b, c] = p;
  if (!a) return { view: VIEWS[S.settings.startView] ? S.settings.startView : 'all' };
  if (VIEWS[a]) return { view: a };
  if (a === 'tag' && b) return { view: 'tag', tag: b };
  if (a === 'book' && b) return { view: 'book', id: +b };
  if (a === 'search') return { view: 'search', q: b || '' };
  if (a === 'recipe' && b) return { view: c === 'edit' ? 'edit' : 'recipe', id: +b };
  if (a === 'new') return { view: 'new' };
  if (a === 'import') return { view: 'import', tab: b || 'web' };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'all' };
}
const GRID_VIEWS = ['all', 'family', 'mine', 'favourites', 'tag', 'book', 'search'];

async function onRoute(keep) {
  const r = route();
  const main = $('#main');
  const top = keep === true ? main.scrollTop : 0;   // drawn again because something changed elsewhere: stay where the page was
  closeMenu();
  try {
    const page = h('div', { class: 'page' });
    if (GRID_VIEWS.includes(r.view)) await drawRecipes(page, r);
    else await ({ recipe: showRecipe, edit: showForm, new: showForm, import: showImport, settings: showSettings })[r.view](page, r);
    main.replaceChildren(page);
    main.scrollTop = top;
  } catch (e) { main.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'empty' }, icon('dish'), h('p', null, e.message || String(e)), h('p', null, h('a', { class: 'lnk', href: '#/' }, 'All recipes'))))); }
  drawNav();
}

// ------------------------------------------------------------------ the recipes, as cards
const SORTS = { title: 'A to Z', new: 'Newest first', rating: 'Best rated first' };
async function fetchRecipes(r) {
  const q = new URLSearchParams();
  if (['family', 'mine', 'favourites'].includes(r.view)) q.set('scope', r.view);
  if (r.view === 'tag') q.set('tag', r.tag);
  if (r.view === 'book') q.set('book', r.id);
  if (r.view === 'search') q.set('q', r.q);
  if (SORTS[S.settings.sort] && S.settings.sort !== 'title') q.set('sort', S.settings.sort);
  const d = await api(`api/recipes?${q}`);
  around(d);
  return d.items;
}
function card(x) {
  const meta = [fmtMin(x.totalMinutes), x.servings ? (/^\d+$/.test(x.servings) ? `Serves ${x.servings}` : x.servings) : ''].filter(Boolean).join(' · ');
  return h('a', { class: 'rcard', href: `#/recipe/${x.id}` },
    x.photo ? h('img', { class: 'rpic', src: `${x.photo}?size=small`, alt: '', loading: 'lazy' })
      : h('span', { class: 'rpic none', style: { '--h': hue(x.title) } }, icon('dish')),
    x.favourite ? h('span', { class: 'rfav', title: 'One of your favourites' }, icon('favorite', 's')) : null,
    h('span', { class: 'rbody' },
      h('span', { class: 'rtitle' }, x.title),
      h('span', { class: 'rmeta' }, x.family ? null : h('span', { class: 'priv', title: 'Private: only you see it' }, icon('lock', 'xs')),
        x.ratingAverage ? h('span', { class: 'rstar', title: `Rated ${x.ratingAverage} of 5` }, icon('star', 'xs'), String(x.ratingAverage)) : null,
        meta || (x.tags || []).slice(0, 3).join(' · ') || ' ')));
}
async function drawRecipes(page, r) {
  const items = await fetchRecipes(r);
  const book = r.view === 'book' ? S.books.find((b) => b.id === r.id) : null;
  if (r.view === 'book' && !book) throw new Error('No such cookbook');
  const title = book ? book.name : r.view === 'tag' ? `#${r.tag}` : r.view === 'search' ? `“${r.q}”` : VIEWS[r.view][0];
  if (book) document.title = `${book.name} · ioRecipe`;
  page.classList.add('wide');
  const sort = h('select', { class: 't sortsel', title: 'In what order', 'aria-label': 'In what order', onchange: async (e) => { await saveSettings({ sort: e.target.value }); onRoute(); } },
    Object.entries(SORTS).map(([k, l]) => h('option', { value: k, selected: k === (S.settings.sort || 'title') ? true : null }, l)));
  put(page, h('div', { class: 'pagehead' }, h('h1', null, title), h('span', { class: 'count' }, items.length || ''), h('span', { class: 'grow' }),
    items.length > 1 ? sort : null,
    book ? h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
      book.writable ? ['edit', 'Rename', () => editBook(book)] : null,
      items.length ? ['download', 'Export this cookbook', `api/export?book=${book.id}`] : null,
      book.writable ? ['delete', 'Delete the cookbook', () => removeBook(book)] : null]) }, icon('more')) : null));
  if (book) put(page, h('p', { class: 'muted bookabout' }, icon(book.family ? 'home' : 'lock', 'xs'), book.family ? 'A family cookbook' : 'A cookbook of your own',
    book.description ? ` · ${book.description}` : ''));
  if (!items.length) {
    const first = !['search', 'tag', 'book', 'favourites'].includes(r.view);
    put(page, h('div', { class: 'empty' }, icon(r.view === 'favourites' ? 'favorite' : r.view === 'book' ? 'books' : 'dish'),
      h('p', null, r.view === 'search' ? 'No recipe has those words.' : r.view === 'tag' ? 'No recipe has that tag.' : r.view === 'mine' ? 'No private recipes yet.'
        : r.view === 'favourites' ? 'No favourites yet: the heart on a recipe makes it one.'
          : r.view === 'book' ? 'Nothing in this cookbook yet: a recipe’s menu (the three dots) puts it in.' : 'No recipes yet.'),
      first && canAdd() ? h('p', { class: 'emptybtns' }, h('a', { class: 'pillbtn primary', href: '#/new' }, icon('add', 's'), 'New recipe'),
        h('a', { class: 'pillbtn', href: '#/import' }, icon('download', 's'), 'Import')) : null));
    return;
  }
  put(page, h('div', { class: 'rgrid' }, items.map(card)));
}

// ------------------------------------------------------------------ cookbooks
/** The name (and what it is about) of a cookbook, new or not, in a dialog. The cookbook as saved, or null. */
async function bookDialog(book) {
  const name = h('input', { class: 't', value: book ? book.name : '', maxlength: 191, placeholder: 'Baking, Weeknights, To try' });
  const about = h('input', { class: 't', value: (book && book.description) || '', placeholder: 'What it holds (if you like)' });
  const where = h('select', { class: 't' }, h('option', { value: '1' }, 'A family cookbook: everyone sees it'), h('option', { value: '0' }, 'A cookbook of my own'));
  const ok = await dialog(book ? 'Rename the cookbook' : 'New cookbook',
    h('div', { class: 'pform' }, fld('Name', name), fld('About', about), !book && canFamily() ? fld('Kind', where) : null),
    [{ label: 'Cancel', value: false }, { label: book ? 'Save' : 'Create', value: true, primary: true }]);
  if (!ok) return null;
  const body = { name: name.value, description: about.value };
  if (!book && canFamily()) body.family = where.value === '1';
  try { return await api(book ? `api/books/${book.id}` : 'api/books', { method: book ? 'PATCH' : 'POST', json: body }); } catch (e) { fail(e); return null; }
}
async function newBook(go = true) {
  const b = await bookDialog(null);
  if (!b) return null;
  await refreshAround();
  if (go) location.hash = `#/book/${b.id}`;
  return b;
}
async function editBook(book) { if (await bookDialog(book)) onRoute(); }
async function removeBook(book) {
  if (!await confirmDialog('Delete this cookbook?', `“${book.name}” goes; its recipes stay.`, 'Delete', true)) return;
  try { await api(`api/books/${book.id}`, { method: 'DELETE' }); toast('Deleted'); await refreshAround(); location.hash = '#/'; } catch (e) { fail(e); }
}
/** The cookbooks a recipe is in, to tick and untick (each tick is saved at once). */
async function recipeBooks(x) {
  const inside = new Set(x.books);
  const list = h('div', { class: 'ticklist' });
  const draw = () => fill(list, S.books.length ? S.books.map((b) => {
    const cant = !b.writable || (b.family && !x.family);
    return h('label', { class: `check${cant ? ' off' : ''}`, title: !b.writable ? 'You can see this cookbook but not change it' : cant ? 'A family cookbook holds family recipes; this one is private' : null },
      h('input', { type: 'checkbox', checked: inside.has(b.id), disabled: cant, onchange: async (e) => {
        try { await api(`api/books/${b.id}/recipes/${x.id}`, { method: e.target.checked ? 'PUT' : 'DELETE' }); if (e.target.checked) inside.add(b.id); else inside.delete(b.id); } catch (err) { e.target.checked = !e.target.checked; fail(err); }
      } }), h('span', null, b.name, h('span', { class: 'muted small' }, b.family ? ' · family' : ' · yours')));
  }) : h('p', { class: 'muted' }, 'No cookbooks yet.'));
  draw();
  const add = canOwn() ? h('button', { class: 'lnk', type: 'button', onclick: async () => { const b = await newBook(false); if (b) draw(); } }, 'New cookbook…') : null;
  await dialog('Cookbooks', h('div', null, h('p', { class: 'muted' }, `Which cookbooks “${x.title}” is in.`), list, add), [{ label: 'Done', value: true, primary: true }]);
  x.books = [...inside];
  refreshAround();
}

// ------------------------------------------------------------------ amounts, for another number of servings
const FRACS = { '¼': 0.25, '½': 0.5, '¾': 0.75, '⅓': 1 / 3, '⅔': 2 / 3, '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875 };
const GLYPHS = Object.entries(FRACS).map(([g, v]) => [v, g]);
const NUM = String.raw`(?:\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:[.,]\d+)?(?:\s*[¼½¾⅓⅔⅛⅜⅝⅞])?|[¼½¾⅓⅔⅛⅜⅝⅞])`;
const AMOUNT = new RegExp(String.raw`^(\s*)(${NUM})(?:(\s*(?:-|–|to|tot|à|a|bis|or|of|ou)\s*)(${NUM}))?`, 'i');
const METRIC = /^\s*(?:g|gr|gram|grams|kg|mg|ml|cl|dl|l|liter|litre|liters|litres|cm|mm)\b/i;
/** A written amount as a number: 2, 1.5, 1,5, 1/2, 1 1/2, ½, 1½. frac: it was written as a fraction. */
function readAmount(t) {
  t = t.trim();
  let m;
  if ((m = t.match(/^(\d+)\s+(\d+)\s*\/\s*(\d+)$/))) return { v: +m[1] + m[2] / m[3], frac: true };
  if ((m = t.match(/^(\d+)\s*\/\s*(\d+)$/))) return { v: m[1] / m[2], frac: true };
  if ((m = t.match(/^(\d+(?:[.,]\d+)?)?\s*([¼½¾⅓⅔⅛⅜⅝⅞])$/))) return { v: (m[1] ? parseFloat(m[1].replace(',', '.')) : 0) + FRACS[m[2]], frac: true };
  return { v: parseFloat(t.replace(',', '.')), frac: false, dec: /[.,]/.test(t) };
}
/** A number as an amount: whole where it is, a fraction (1 ½) where the recipe counts in spoons and cups, else decimals. */
function showAmount(v, a, metric, comma) {
  if (!(v > 0) || !Number.isFinite(v)) return '0';
  const whole = Math.floor(v + 1e-9), part = v - whole;
  if (part < 0.02) return String(whole);
  if (part > 0.98) return String(whole + 1);
  if (!metric && !a.dec && v < 100) {
    const g = GLYPHS.find(([x]) => Math.abs(x - part) < 0.04);
    if (g) return whole ? `${whole} ${g[1]}` : g[1];
  }
  const s = v.toFixed(v < 10 ? 2 : v < 100 ? 1 : 0).replace(/\.?0+$/, '');
  return comma ? s.replace('.', ',') : s;
}
/** The line with the amount it begins with (2, 1/2, 2-3) multiplied by f; a line that begins with none stays. */
function scaleLine(line, f, comma) {
  if (f === 1) return line;
  const m = line.match(AMOUNT);
  if (!m) return line;
  const rest = line.slice(m[0].length);
  const metric = METRIC.test(rest);
  const one = (t) => showAmount(readAmount(t).v * f, readAmount(t), metric, comma);
  return `${m[1]}${one(m[2])}${m[4] ? `${m[3]}${one(m[4])}` : ''}${rest}`;
}
const FACTORS = [0.25, 1 / 3, 0.5, 2 / 3, 0.75, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
const factorName = (f) => { const g = GLYPHS.find(([x]) => Math.abs(x - f) < 0.01); return `× ${g ? g[1] : String(f)}`; };

// ------------------------------------------------------------------ one recipe
const isHeading = (line) => /:$/.test(line) && line.length < 80;
/** The lines of ingredients or steps as groups: [{heading, lines: [{text, i}]}], a heading being a line that ends
    with a colon; i is the line's place in the list. */
function groups(lines) {
  const out = [{ heading: null, lines: [] }];
  (lines || []).forEach((l, i) => { if (isHeading(l)) out.push({ heading: l.replace(/:$/, ''), lines: [] }); else out[out.length - 1].lines.push({ text: l, i }); });
  return out.filter((g) => g.heading || g.lines.length);
}
/** ioTask's lists that take the ingredients, asked once per visit (and again when the dialog opens). */
let shop = null;
const shopping = (fresh = false) => { if (!shop || fresh) shop = api('api/shopping').catch(() => ({ available: false, lists: [] })); return shop; };
/** A picture, large, over the page: the others of its row with the arrows, and (for who may) taking it away. */
function lightbox(pics, at, x) {
  let i = at;
  const img = h('img', { alt: '' });
  const count = h('span', { class: 'lbcount' });
  const show = () => { img.src = pics[i].url; count.textContent = pics.length > 1 ? `${i + 1} of ${pics.length}` : ''; };
  const go = (d) => { i = (i + d + pics.length) % pics.length; show(); };
  const close = () => { back.remove(); document.removeEventListener('keydown', key, true); };
  const key = (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); close(); } else if (e.key === 'ArrowLeft') go(-1); else if (e.key === 'ArrowRight') go(1);
  };
  const remove = async () => {
    if (!await confirmDialog('Remove this photo?', 'It goes for good.', 'Remove', true)) return;
    try { await api(`api/recipes/${x.id}/photos/${pics[i].id}`, { method: 'DELETE' }); close(); onRoute(); } catch (e) { fail(e); }
  };
  const back = h('div', { class: 'lightbox', onclick: (e) => { if (e.target === back) close(); } },
    img,
    h('div', { class: 'lbbar' }, count, h('span', { class: 'grow' }),
      x.writable ? h('button', { class: 'pillbtn danger', onclick: remove }, icon('delete', 's'), 'Remove') : null,
      h('button', { class: 'iconbtn', title: 'Close', onclick: close }, icon('close'))),
    pics.length > 1 ? [h('button', { class: 'iconbtn lbnav prev', title: 'The one before', onclick: () => go(-1) }, icon('prev')),
      h('button', { class: 'iconbtn lbnav next', title: 'The next', onclick: () => go(1) }, icon('next'))] : null);
  show();
  document.body.append(back);
  document.addEventListener('keydown', key, true);
}
/** One file from the device, as a promise (null when none was picked). */
function pickFile(accept, multiple = false) {
  return new Promise((resolve) => {
    const inp = h('input', { type: 'file', accept, multiple: multiple || null, hidden: true });
    inp.onchange = () => { resolve(multiple ? [...inp.files] : inp.files[0] || null); inp.remove(); };
    inp.addEventListener('cancel', () => { resolve(multiple ? [] : null); inp.remove(); });
    document.body.append(inp);
    inp.click();
  });
}
const sendPhoto = (path, file) => api(path, { method: 'POST', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } });

async function showRecipe(page, r) {
  const x = await api(`api/recipes/${r.id}`);
  document.title = `${x.title} · ioRecipe`;
  const own = x.photos.filter((p) => p.step == null), ofStep = new Map(x.photos.filter((p) => p.step != null).map((p) => [p.step, p]));
  const comma = x.ingredients.some((l) => /^\s*\d+,\d/.test(l));
  let f = 1;  // the amounts are multiplied by this

  // ---- the head: the heart, Print, Edit and the rest
  const heart = canOwn() ? h('button', { class: 'iconbtn heart' }) : null;
  const drawHeart = () => { if (!heart) return; fill(heart, icon(x.favourite ? 'favorite' : 'favoriteBorder')); heart.classList.toggle('on', x.favourite); heart.title = x.favourite ? 'One of your favourites (click to take it off)' : 'Make it a favourite'; };
  if (heart) heart.onclick = async () => { try { Object.assign(x, await api(`api/recipes/${x.id}/mark`, { method: 'PUT', json: { favourite: !x.favourite } })); drawHeart(); refreshAround(); } catch (e) { fail(e); } };
  drawHeart();
  const more = h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
    S.books.length || canOwn() ? ['books', 'Cookbooks…', () => recipeBooks(x)] : null,
    ['download', 'Export', `api/recipes/${x.id}/export`],
    x.writable ? ['delete', 'Delete', () => removeRecipe(x)] : null]) }, icon('more'));

  // ---- your rating, and everyone's
  const rating = h('div', { class: 'rating' });
  const drawRating = () => fill(rating,
    canOwn() ? h('span', { class: 'stars', role: 'group', 'aria-label': 'Your rating' }, [1, 2, 3, 4, 5].map((n) => h('button', { class: n <= (x.rating || 0) ? 'on' : null,
      title: n === x.rating ? 'Take your rating away' : `${n} of 5`, 'aria-label': `${n} of 5`, onclick: async () => {
        try { Object.assign(x, await api(`api/recipes/${x.id}/mark`, { method: 'PUT', json: { rating: n === x.rating ? null : n } })); drawRating(); } catch (e) { fail(e); }
      } }, icon(n <= (x.rating || 0) ? 'star' : 'starBorder')))) : null,
    h('span', { class: 'muted small' }, !x.ratingCount ? (canOwn() ? 'Not rated yet' : '')
      : x.ratingCount === 1 && x.rating ? 'Your rating' : `${x.ratingAverage} of 5, from ${x.ratingCount} ${x.ratingCount === 1 ? 'rating' : 'ratings'}`));
  drawRating();

  // ---- the facts; "Makes" follows the servings asked for
  const makes = h('span', null);
  const times = [['Prep', x.prepMinutes], ['Cook', x.cookMinutes], ['Total', x.totalMinutes]].filter(([, v]) => v);
  const facts = h('div', { class: 'facts' },
    times.map(([k, v]) => h('span', { class: 'fact' }, icon('timer', 's'), h('span', null, h('small', null, k), fmtMin(v)))),
    x.servings ? h('span', { class: 'fact' }, icon('people', 's'), makes) : null,
    h('span', { class: 'fact' }, icon(x.family ? 'home' : 'lock', 's'), h('span', null, h('small', null, 'Kept with'), x.family ? 'Family recipes' : 'My private recipes')));

  // ---- the ingredients, for 1× or another amount; a tick stays through a change of amount
  const ticked = new Set();
  const ingBox = h('div');
  const scaleLabel = h('span', { class: 'scalev' });
  const less = h('button', { class: 'iconbtn', title: 'Less', 'aria-label': 'Less', onclick: () => step(-1) }, icon('minus', 's'));
  const moreOf = h('button', { class: 'iconbtn', title: 'More', 'aria-label': 'More', onclick: () => step(1) }, icon('add', 's'));
  const reset = h('button', { class: 'lnk small', onclick: () => { f = 1; drawIngredients(); } }, 'As written');
  const step = (d) => { const at = FACTORS.findIndex((v) => Math.abs(v - f) < 0.01); f = FACTORS[Math.max(0, Math.min(FACTORS.length - 1, at + d))]; drawIngredients(); };
  const scaled = () => x.ingredients.map((l) => (isHeading(l) ? l : scaleLine(l, f, comma)));
  function drawIngredients() {
    const lines = scaled();
    const ing = groups(lines).map((g) => [g.heading ? h('h3', null, g.heading) : null,
      h('ul', { class: 'ings' }, g.lines.map((l) => h('li', null, h('label', { class: 'check' },
        h('input', { type: 'checkbox', checked: ticked.has(l.i), onchange: (e) => { if (e.target.checked) ticked.add(l.i); else ticked.delete(l.i); } }), h('span', null, l.text)))))]);
    fill(ingBox, ing.length ? ing : h('p', { class: 'muted' }, 'None listed.'));
    scaleLabel.textContent = factorName(f);
    scaleLabel.classList.toggle('on', f !== 1);
    reset.hidden = f === 1;
    less.disabled = f <= FACTORS[0]; moreOf.disabled = f >= FACTORS[FACTORS.length - 1];
    if (x.servings) fill(makes, h('small', null, f === 1 ? 'Makes' : `Makes (${factorName(f)})`), /\d|[¼½¾⅓⅔]/.test(x.servings) ? scaleLine(x.servings, f, comma) : x.servings);
  }
  drawIngredients();
  const hasAmounts = x.ingredients.some((l) => !isHeading(l) && AMOUNT.test(l));

  // ---- the shopping list: offered once ioTask says it is there
  const shopBtn = h('button', { class: 'pillbtn shopbtn', hidden: true, onclick: () => shoppingDialog(x, scaled(), ticked) }, icon('cart', 's'), 'Add to shopping list');
  if (x.ingredients.length) shopping().then((sh) => { shopBtn.hidden = !sh.available; });

  // ---- the steps, each with its picture; who may change the recipe adds or replaces one
  let n = 0;
  const stepPhoto = async (i) => {
    const file = await pickFile('image/*');
    if (!file) return;
    try { await sendPhoto(`api/recipes/${x.id}/photos?step=${i}`, file); onRoute(); } catch (e) { fail(e); }
  };
  const steps = groups(x.steps).map((g) => [g.heading ? h('h3', null, g.heading) : null,
    h('ol', { class: 'steps' }, g.lines.map((l) => {
      n += 1;
      const pic = ofStep.get(l.i);
      return h('li', { onclick: (e) => { if (!e.target.closest('button, img')) e.currentTarget.classList.toggle('done'); } }, h('span', { class: 'num' }, n),
        h('span', { class: 'steptext' }, l.text,
          pic ? h('img', { class: 'stepimg', src: pic.url, alt: '', loading: 'lazy', onclick: () => lightbox([pic], 0, x) }) : null),
        x.writable ? h('button', { class: 'iconbtn stepcam', title: pic ? 'Another photo for this step' : 'Add a photo to this step', onclick: () => stepPhoto(l.i) }, icon('camera', 's')) : null);
    }))]);
  const host = x.sourceUrl ? (() => { try { return new URL(x.sourceUrl).hostname.replace(/^www\./, ''); } catch { return ''; } })() : '';
  page.classList.add('recipe');
  put(page,
    h('div', { class: 'pagehead' }, h('h1', null, x.title), h('span', { class: 'grow' }), heart,
      h('button', { class: 'pillbtn', onclick: () => print() }, icon('print', 's'), 'Print'),
      x.writable ? h('a', { class: 'pillbtn', href: `#/recipe/${x.id}/edit` }, icon('edit', 's'), 'Edit') : null, more),
    own.length ? h('img', { class: 'hero', src: own[0].url, alt: '', onclick: () => lightbox(own, 0, x) }) : null,
    own.length > 1 ? h('div', { class: 'thumbs' }, own.map((p, i) => h('img', { src: `${p.url}?size=small`, alt: '', loading: 'lazy', onclick: () => lightbox(own, i, x) }))) : null,
    x.description ? h('p', { class: 'desc notes' }, x.description) : null,
    facts, rating,
    x.tags.length ? h('div', { class: 'chiprow tags' }, x.tags.map((t) => h('a', { class: 'chip', href: `#/tag/${encodeURIComponent(t)}` }, `#${t}`))) : null,
    h('div', { class: 'cols' },
      h('section', { class: 'ingcol' },
        h('div', { class: 'inghead' }, h('h2', null, 'Ingredients'),
          hasAmounts ? h('span', { class: 'scale', title: 'For more or fewer servings' }, less, scaleLabel, moreOf) : null),
        hasAmounts ? h('p', { class: 'scalenote' }, reset) : null,
        ingBox, shopBtn),
      h('section', { class: 'stepcol' }, h('h2', null, 'Steps'), steps.length ? steps : h('p', { class: 'muted' }, 'None listed.'),
        x.notes ? [h('h2', null, 'Notes'), h('p', { class: 'notes' }, x.notes)] : null)),
    linkedBox(x.id),
    x.sourceUrl || x.sourceName ? h('p', { class: 'muted source' }, 'From ',
      safeUrl(x.sourceUrl) ? h('a', { class: 'lnk', href: x.sourceUrl, target: '_blank', rel: 'noopener noreferrer' }, x.sourceName || host) : x.sourceName,
      x.sourceName && host && x.sourceName.toLowerCase() !== host ? ` (${host})` : '') : null);
}
/** "Linked" under a recipe: the events, tasks, notes, contacts and photos of the other apps linked to it (the suite's panel). */
let linkUi = null;
function linkedBox(id) {
  const el = h('div', { class: 'linked' });
  (async () => {
    try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch (e) { return; }
    linkUi.mount(el, { kind: 'recipe', id, toast });
  })();
  return el;
}
/** The ingredients (as the page shows them, for the servings asked) to send to one of your lists in ioTask: those
    ticked off on the page start unticked here (you have them). */
async function shoppingDialog(x, lines, have) {
  const sh = await shopping(true);
  const items = lines.map((text, i) => ({ text, i })).filter((l) => !isHeading(l.text));
  if (!sh.lists.length) {
    await dialog('Add to shopping list', h('p', null, sh.error || 'None of your lists in ioTask takes new tasks. ',
      sh.url ? h('a', { class: 'lnk', href: sh.url, target: '_blank', rel: 'noopener' }, 'Open ioTask') : null));
    return;
  }
  const saved = S.settings.shoppingList;
  const guess = sh.lists.find((l) => l.id === saved) || sh.lists.find((l) => /shop|grocer|boodschap|winkel|courses|einkauf/i.test(l.name)) || sh.lists[0];
  const list = h('select', { class: 't' }, sh.lists.map((l) => h('option', { value: l.id, selected: l.id === guess.id ? true : null }, l.name)));
  const boxes = items.map((l) => h('input', { type: 'checkbox', checked: !have.has(l.i) }));
  const body = h('div', null, h('div', { class: 'pform' }, fld('List in ioTask', list)),
    h('div', { class: 'ticklist' }, items.map((l, k) => h('label', { class: 'check' }, boxes[k], h('span', null, l.text)))));
  if (!await dialog('Add to shopping list', body, [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }])) return;
  const picked = items.filter((l, k) => boxes[k].checked).map((l) => l.text);
  if (!picked.length) { toast('Nothing was ticked'); return; }
  try {
    const got = await api(`api/recipes/${x.id}/shopping`, { method: 'POST', json: { listId: +list.value, lines: picked } });
    const name = sh.lists.find((l) => l.id === +list.value).name;
    toast(`${got.added} added to “${name}”`);
    saveSettings({ shoppingList: +list.value });
  } catch (e) { fail(e); }
}
async function removeRecipe(x) {
  if (!await confirmDialog('Delete this recipe?', `“${x.title}” and its photos go for good.`, 'Delete', true)) return;
  try { await api(`api/recipes/${x.id}`, { method: 'DELETE' }); toast('Deleted'); location.hash = '#/'; } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ one recipe: the form
async function showForm(page, r) {
  // a new recipe starts empty, or from the draft an import left (pasted text, a photo)
  const x = r.view === 'edit' ? await api(`api/recipes/${r.id}`) : { ingredients: [], steps: [], tags: [], family: canFamily(), photos: [], ...(S.draft || {}) };
  const draft = r.view === 'new' && !!S.draft;
  S.draft = null;
  if (r.view === 'edit' && !x.writable) { location.hash = `#/recipe/${x.id}`; return; }
  if (r.view === 'new' && !canAdd()) throw new Error('A viewer only looks at the family’s recipes.');
  const back = x.id ? `#/recipe/${x.id}` : '#/';
  const inp = (v, attrs = {}) => h('input', { class: 't', value: v == null ? '' : v, ...attrs });
  const area = (v, attrs = {}) => h('textarea', { class: 't', ...attrs }, v || '');
  const title = inp(x.title, { class: 't big', placeholder: 'Title', maxlength: 255 });
  const desc = area(x.description, { rows: 2, placeholder: 'A line or two about it' });
  const servings = inp(x.servings, { placeholder: '4, or 24 cookies', maxlength: 64 });
  const mins = (v) => inp(v, { type: 'number', min: 0, inputmode: 'numeric', placeholder: 'minutes' });
  const prep = mins(x.prepMinutes), cook = mins(x.cookMinutes);
  const total = mins(x.prepMinutes || x.cookMinutes ? ((x.prepMinutes || 0) + (x.cookMinutes || 0) === x.totalMinutes ? null : x.totalMinutes) : x.totalMinutes);
  total.placeholder = 'prep + cook';
  const where = h('select', { class: 't' }, h('option', { value: '1', selected: x.family ? true : null }, 'Family recipes'),
    h('option', { value: '0', selected: x.family ? null : true }, 'My private recipes'));
  const tags = inp((x.tags || []).join(', '), { placeholder: 'dessert, cookies, quick', list: 'taglist' });
  const ings = area((x.ingredients || []).join('\n'), { rows: 10, placeholder: '200 g flour\n100 g butter\nFor the icing:\n150 g icing sugar' });
  const steps = area((x.steps || []).join('\n\n'), { rows: 12, placeholder: 'Heat the oven to 180 °C.\n\nMix the flour and the butter.' });
  const notes = area(x.notes, { rows: 3, placeholder: 'Tips, what to change next time' });
  const url = inp(x.sourceUrl, { type: 'url', placeholder: 'https://…' });
  const from = inp(x.sourceName, { placeholder: 'Grandma, a book, a website', maxlength: 255 });

  // the photos: those the recipe has and the files just picked, in the order they will have (the first is the one
  // the cards show); the step photos are added on the recipe's own page
  let pics = (x.photos || []).filter((p) => p.step == null).map((p) => ({ id: p.id, src: `${p.url}?size=small` }));
  const gone = [];
  const view = h('div', { class: 'photopick' });
  const addFiles = async () => { for (const file of await pickFile('image/*', true)) pics.push({ file, src: URL.createObjectURL(file) }); drawPhoto(); };
  const drawPhoto = () => fill(view,
    pics.length ? h('div', { class: 'phototiles' }, pics.map((p, i) => h('div', { class: `phototile${i ? '' : ' first'}` }, h('img', { src: p.src, alt: '' }),
      i ? h('button', { type: 'button', class: 'tilebtn mk', title: 'Make it the first: the one the cards show', onclick: () => { pics = [p, ...pics.filter((q) => q !== p)]; drawPhoto(); } }, icon('star', 'xs'), 'Make first')
        : h('span', { class: 'tilebtn mk on' }, icon('star', 'xs'), 'On the card'),
      h('button', { type: 'button', class: 'tilebtn rm', title: 'Remove', 'aria-label': 'Remove', onclick: () => { if (p.id) gone.push(p.id); pics = pics.filter((q) => q !== p); drawPhoto(); } }, icon('close', 'xs')))),
      h('button', { type: 'button', class: 'phototile addtile', onclick: addFiles }, icon('photo'), h('span', null, 'Add photos')))
      : h('button', { type: 'button', class: 'none', onclick: addFiles }, icon('photo'), h('span', null, 'Add photos')));
  drawPhoto();

  const save = async (e) => {
    e.preventDefault();
    const body = { title: title.value, description: desc.value, servings: servings.value, prepMinutes: prep.value, cookMinutes: cook.value,
      totalMinutes: total.value, tags: tags.value, ingredients: ings.value, steps: steps.value, notes: notes.value, sourceUrl: url.value, sourceName: from.value };
    if (canFamily()) body.family = where.value === '1';
    const btn = $('.formbar .primary', page); btn.disabled = true;
    try {
      let got = await api(x.id ? `api/recipes/${x.id}` : 'api/recipes', { method: x.id ? 'PATCH' : 'POST', json: body });
      try {
        for (const id of gone) await api(`api/recipes/${got.id}/photos/${id}`, { method: 'DELETE' });
        for (const p of pics.filter((q) => q.file)) {
          const before = new Set(got.photos.map((q) => q.id));
          got = await sendPhoto(`api/recipes/${got.id}/photos`, p.file);
          p.id = got.photos.find((q) => !before.has(q.id)).id;
        }
        if (pics.length > 1) await api(`api/recipes/${got.id}/photos/order`, { method: 'PUT', json: { ids: pics.map((q) => q.id) } });
      } catch (err) { toast(`Saved, but not every photo: ${err.message}`); location.hash = `#/recipe/${got.id}`; return; }
      toast('Saved');
      location.hash = `#/recipe/${got.id}`;
    } catch (err) { btn.disabled = false; fail(err); }
  };
  page.classList.add('form');
  put(page, h('form', { onsubmit: save },
    h('div', { class: 'pagehead' }, h('h1', null, x.id ? 'Edit recipe' : 'New recipe')),
    draft ? h('p', { class: 'draftnote' }, icon('ai', 's'), 'This is what was read. Look it over and put right what needs it; nothing is saved until you press Save.') : null,
    title, view,
    h('div', { class: 'fsec' }, icon('dish'), 'About'),
    desc,
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('Makes', servings), fld('Preparation', prep), fld('Cooking', cook), fld('Total, when it is more', total)),
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('Tags, with commas between', tags), canFamily() ? fld('Kept with', where) : null),
    canFamily() ? h('p', { class: 'muted small hint', style: { marginTop: '6px' } }, 'Everyone sees the family’s recipes; a private one only you.') : null,
    h('datalist', { id: 'taglist' }, S.tags.map((t) => h('option', { value: t.tag }))),
    h('div', { class: 'fsec' }, icon('list'), 'Ingredients'),
    h('p', { class: 'muted small hint' }, 'One on each line. A line that ends with a colon (“For the icing:”) is a heading.'),
    ings,
    h('div', { class: 'fsec' }, icon('book'), 'Steps'),
    h('p', { class: 'muted small hint' }, 'One step on each line; empty lines between them are fine. A line that ends with a colon is a heading.'),
    steps,
    h('div', { class: 'fsec' }, icon('edit'), 'Notes'),
    notes,
    h('div', { class: 'fsec' }, icon('link'), 'Where it comes from'),
    h('div', { class: 'grid' }, fld('Source', from), fld('Link', url)),
    h('div', { class: 'formbar' }, h('button', { class: 'pillbtn primary noic', type: 'submit' }, 'Save'), h('a', { class: 'pillbtn noic', href: back }, 'Cancel'),
      h('span', { class: 'grow' }), x.id ? h('button', { type: 'button', class: 'pillbtn danger noic', onclick: () => removeRecipe(x) }, 'Delete') : null)));
  if (!x.id) setTimeout(() => title.focus(), 0);
}

// ------------------------------------------------------------------ import and export
const IMPORT_TABS = [['web', 'Web address'], ['text', 'Pasted text'], ['photo', 'Photo'], ['file', 'File'], ['export', 'Export']];
async function showImport(page, r) {
  if (!canAdd() && r.tab !== 'export') { location.hash = '#/import/export'; return; }
  const tabs = IMPORT_TABS.filter(([k]) => canAdd() || k === 'export');
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Import and export')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/import/${k}`; } }, l))));
  const where = () => h('select', { class: 't' }, h('option', { value: '1' }, 'Family recipes'), h('option', { value: '0' }, 'My private recipes'));
  const note = h('p', { class: 'err' });
  const busy = (btn, text) => { note.className = 'muted'; note.textContent = text; btn.disabled = true; };
  const failed = (btn, err) => { note.className = 'err'; note.textContent = err.message.replace(/^Bad request: /, ''); btn.disabled = false; };
  const toForm = (draft) => { S.draft = draft; location.hash = '#/new'; };
  await ({ web: importWeb, text: importText, photo: importPhoto, file: importFile, export: exportBox }[r.tab] || importWeb)();

  async function importWeb() {
    const ai = await api('api/import').then((w) => w.aiState, () => 'off');
    const url = h('input', { class: 't', type: 'url', placeholder: 'https://www.example.com/recipes/oat-cookies', autocapitalize: 'none', spellcheck: 'false' });
    const kept = where();
    const btn = h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Import');
    const go = async (e) => {
      e.preventDefault();
      if (!url.value.trim()) { url.focus(); return; }
      busy(btn, 'Fetching the page and reading the recipe…');
      try {
        const body = { url: url.value.trim() };
        if (canFamily()) body.family = kept.value === '1';
        const got = await api('api/import', { method: 'POST', json: body });
        toast(got.readBy === 'ai' ? `Imported “${got.title}”, read from the page by the AI model. Check it against the page.`
          : got.readBy === 'page' ? `Imported “${got.title}” from the page’s text${got.steps.length ? '' : ' (the page writes out no steps)'}. Check it against the page.`
          : `Imported “${got.title}”. Have a look, and edit what needs it.`);
        location.hash = `#/recipe/${got.id}`;
      } catch (err) { failed(btn, err); }
    };
    put(page, h('form', { class: 'box importbox', onsubmit: go },
      h('h2', null, icon('globe'), 'A recipe’s web address'),
      h('p', { class: 'muted' }, 'Paste the address of a recipe page. ioRecipe fetches the page and keeps the recipe it describes (title, ingredients, steps, times, tags) with its picture and a link back to where it came from.'),
      h('div', { class: 'pform' }, url, canFamily() ? fld('Kept with', kept) : null, h('div', null, btn), note),
      h('p', { class: 'muted small' }, 'Most recipe sites describe their recipes for search engines, and that is read first. Where a page does not, ioRecipe reads its lists and the text under “Ingredients”', ai === 'ready' ? ', and has the AI model on this server read the page when that gives no complete recipe (that takes a minute or so).' : ai === 'fetching' ? '. The AI model that reads other pages is still being fetched to this server.' : '.', ' A site that only answers a person’s browser cannot be fetched: copy its text and use Pasted text.')));
    setTimeout(() => url.focus(), 0);
  }

  function importText() {
    const text = h('textarea', { class: 't', rows: 16, placeholder: 'Oat cookies\n\nIngredients\n200 g oats\n100 g butter\n\nInstructions\n1. Heat the oven to 180 °C.\n2. Mix, shape and bake for 12 minutes.' });
    const btn = h('button', { class: 'pillbtn primary', type: 'submit' }, icon('text', 's'), 'Read the recipe');
    const go = async (e) => {
      e.preventDefault();
      if (!text.value.trim()) { text.focus(); return; }
      busy(btn, 'Reading…');
      try { toForm((await api('api/import/text', { method: 'POST', json: { text: text.value } })).draft); } catch (err) { failed(btn, err); }
    };
    put(page, h('form', { class: 'box importbox', onsubmit: go },
      h('h2', null, icon('text'), 'A recipe as text'),
      h('p', { class: 'muted' }, 'Paste a recipe from a message, a document or a web page. The title is its first line; “Ingredients” and “Instructions” (or what your language calls them) start their parts. It opens in the recipe form, for you to look over before it is saved.'),
      text, h('div', { class: 'pform' }, h('div', null, btn), note)));
    setTimeout(() => text.focus(), 0);
  }

  async function importPhoto() {
    const ways = await api('api/import');
    if (!ways.photo) {
      put(page, h('div', { class: 'box importbox' }, h('h2', null, icon('camera'), 'A photo of a recipe'),
        h('p', null, 'This server cannot read photos yet: the program that reads them (Tesseract) is not installed on it.'),
        h('p', { class: 'muted' }, 'The README says how to add it (“Reading a photo of a recipe”). The Docker image comes with it.')));
      return;
    }
    let file = null;
    const preview = h('div', { class: 'photopick' });
    const btn = h('button', { class: 'pillbtn primary', type: 'submit', disabled: true }, icon('ai', 's'), 'Read the recipe');
    const choose = async () => {
      const got = await pickFile('image/*');
      if (!got) return;
      file = got; btn.disabled = false; note.textContent = '';
      fill(preview, h('img', { src: URL.createObjectURL(file), alt: '' }), h('div', { class: 'photobtns' }, h('button', { type: 'button', class: 'pillbtn', onclick: choose }, icon('upload', 's'), 'Another photo')));
    };
    fill(preview, h('button', { type: 'button', class: 'none', onclick: choose }, icon('camera'), h('span', null, 'Choose a photo, or take one')));
    const go = async (e) => {
      e.preventDefault();
      if (!file) return;
      busy(btn, 'Reading the text on the photo… this can take half a minute.');
      try { toForm((await sendPhoto('api/import/photo', file)).draft); } catch (err) { failed(btn, err); }
    };
    put(page, h('form', { class: 'box importbox', onsubmit: go },
      h('h2', null, icon('camera'), 'A photo of a recipe'),
      h('p', { class: 'muted' }, 'A page of a cookbook, a printed card, a screenshot: the text on it is read on this server (the photo goes nowhere else) and opens in the recipe form, for you to put right before it is saved. Print reads well; handwriting mostly does not. A sharp, straight, well-lit photo of one recipe works best.'),
      preview, h('div', { class: 'pform', style: { marginTop: '12px' } }, h('div', null, btn), note),
      h('p', { class: 'muted small' }, `Languages read here: ${ways.languages.join(', ')}.`)));
  }

  function importFile() {
    let file = null;
    const kept = where();
    const name = h('span', { class: 'muted' }, 'No file chosen');
    const btn = h('button', { class: 'pillbtn primary', type: 'submit', disabled: true }, icon('upload', 's'), 'Import');
    const out = h('div');
    const choose = async () => { const got = await pickFile('.zip,.json,application/zip,application/json'); if (got) { file = got; name.textContent = `${file.name} (${(file.size / 1048576).toFixed(1)} MB)`; btn.disabled = false; } };
    const go = async (e) => {
      e.preventDefault();
      if (!file) return;
      busy(btn, 'Importing…');
      try {
        const got = await api(`api/import/file${canFamily() ? `?family=${kept.value === '1'}` : ''}`, { method: 'POST', body: file, headers: { 'Content-Type': 'application/octet-stream' } });
        note.textContent = ''; btn.disabled = false;
        fill(out, h('p', null, h('b', null, `${got.imported.length} ${got.imported.length === 1 ? 'recipe' : 'recipes'} imported.`)),
          h('div', { class: 'chiprow' }, got.imported.slice(0, 60).map((x) => h('a', { class: 'chip', href: `#/recipe/${x.id}` }, x.title))),
          got.skipped.length ? [h('p', { class: 'muted' }, 'Passed over:'), h('ul', { class: 'muted small' }, got.skipped.map((t) => h('li', null, t)))] : null);
        refreshAround();
      } catch (err) { failed(btn, err); }
    };
    put(page, h('form', { class: 'box importbox', onsubmit: go },
      h('h2', null, icon('file'), 'A file of recipes'),
      h('p', { class: 'muted' }, 'An export from ioRecipe (.zip), an export or a backup from Mealie (.zip), or a recipe as a .json file. Every recipe in it becomes a new recipe here, with its photos.'),
      h('div', { class: 'pform' }, h('div', { class: 'filerow' }, h('button', { type: 'button', class: 'pillbtn', onclick: choose }, icon('file', 's'), 'Choose a file'), name),
        canFamily() ? fld('Kept with', kept) : null, h('div', null, btn), note),
      out));
  }

  function exportBox() {
    const dl = (href, ic, label, n) => h('a', { class: 'pillbtn', href, download: '' }, icon(ic, 's'), label, n != null ? h('span', { class: 'muted' }, ` ${n}`) : null);
    put(page, h('div', { class: 'box importbox' },
      h('h2', null, icon('download'), 'Export'),
      h('p', { class: 'muted' }, 'A .zip with the recipes, their photos, your favourites and ratings, and the cookbooks they are in: to keep somewhere safe, to hand to someone, or to import into another ioRecipe (File, above).'),
      h('div', { class: 'chiprow exports' },
        dl('api/export', 'book', 'Everything I see', S.counts.all),
        S.counts.family ? dl('api/export?scope=family', 'home', 'Family recipes', S.counts.family) : null,
        S.counts.mine ? dl('api/export?scope=mine', 'lock', 'My private recipes', S.counts.mine) : null,
        S.counts.favourites ? dl('api/export?scope=favourites', 'favorite', 'My favourites', S.counts.favourites) : null),
      S.books.some((b) => b.count) ? [h('p', { class: 'muted', style: { marginTop: '14px' } }, 'Or one cookbook:'),
        h('div', { class: 'chiprow exports' }, S.books.filter((b) => b.count).map((b) => dl(`api/export?book=${b.id}`, 'books', b.name, b.count)))] : null,
      h('p', { class: 'muted small', style: { marginTop: '14px' } }, 'One recipe on its own: Export in the recipe’s menu (the three dots).')));
  }
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const tabs = [['account', 'Account'], ['display', 'Display'],
    ...(S.user.isAdmin ? [['app', 'This app']] : []), ...(S.user.suiteAdmin ? Object.entries(SUITE_TABS) : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, app: setApp, people: setSuite, apps: setSuite, servers: setSuite, keys: setSuite }[r.tab] || setAccount)(body, r);
}

/** Settings › Account: display name, email and password, then the app passwords: iosuite_shared's panels (the same in every io app). */
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast });
}

/** Settings › Display: the theme (saved with the account) and what the app opens on. */
async function setDisplay(el) {
  const ui = await accountUi();
  const sv = h('select', { class: 't', onchange: async (e) => { await saveSettings({ startView: e.target.value }); toast('Saved'); } },
    Object.entries(VIEWS).filter(([k]) => viewShown(k)).map(([v, [l]]) => h('option', { value: v, selected: v === (S.settings.startView || 'all') ? true : null }, l)));
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || store.get('theme') || 'system', (t) => { S.settings.theme = t; applyTheme(t); })),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Recipes'), h('div', { class: 'grid' }, fld('Open on', sv))));
}

/** Settings › People, Apps, Servers and Keys (suite admins): the people, their role in every app, app
    passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite_shared. */
const SUITE_TABS = { people: 'People', apps: 'Apps', servers: 'Servers', keys: 'Keys' };
/** Settings › This app (its admins): every setting this app declares, in the suite's one home for them. The same
    block in every app, served by iosuite_shared (frame.appSettings). */
function setApp(el) { return frame.appSettings(el, { toast }); }
function setSuite(el, r) { return frame.suitePanel(el, r); }

// ------------------------------------------------------------------ sign-in
function showSignIn() { frame.signInScreen({ api, name: 'Recipe', first: !S.status.usersExist }); }

// ------------------------------------------------------------------ start
async function start() {
  applyTheme();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
  S.status = await api('api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme) applyTheme(S.settings.theme);
  drawUser();
  const nb = $('#newbtn');
  nb.hidden = !canAdd();
  nb.onclick = () => popMenu(nb, [['edit', 'Write a recipe', '#/new'], ['globe', 'Import from the web', '#/import/web'], ['text', 'From pasted text', '#/import/text'],
    ['camera', 'From a photo', '#/import/photo'], ['file', 'From a file', '#/import/file']]);
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  let t;
  $('#q').addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      const q = e.target.value.trim();
      if (q) location.hash = `#/search/${encodeURIComponent(q)}`;
      else if (route().view === 'search') location.hash = '#/';
    }, 250);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (document.querySelector('.lightbox')) return; if (menuOpen()) closeMenu(); else if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin, .dialog-back, .lightbox')) return;
    if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
    else if (e.key === 'n' && canAdd()) location.hash = '#/new';
  });
  addEventListener('hashchange', () => { document.title = 'ioRecipe'; onRoute(); });
  try { around(await api('api/summary')); } catch { /* the page says so */ }
  await onRoute();
  loadSuite();
  // what changed elsewhere shows by itself: another person, an assistant, another tab (the suite's one live stream,
  // iosuite_shared/static/live.js); a page with a form on it is left alone
  import(new URL('api/live.js', document.baseURI).href)
    .then((live) => live.keepFresh('iorecipe', async () => { await refreshAround(); await onRoute(true); }, { when: () => [...GRID_VIEWS, 'recipe'].includes(route().view) }))
    .catch(() => { /* no stream on this server */ });
}
start().catch(fail);

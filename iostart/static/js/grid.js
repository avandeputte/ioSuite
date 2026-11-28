/* The person's own grid (layout style "grid"): sections of blocks, each as wide and as tall as the person made it. */
import { confirmDialog, dialog, fld, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, newId, quiet, S, viewerTz } from './core.js';
import { bookmarkGroups, drawBirthdays, drawBookmarks, drawStrip, drawWeek } from './cards.js';
import { arrangeDrag } from './customize.js';
import { cardOrder, drawBookmarkStatus, sizeOf } from './home.js';
import { drawHomeCard } from './homeassistant.js';
import { drawNewsCard } from './news.js';
import { drawGlance, drawLowLine, EMPTY, LINES, LOW, tileOf, wget, WIDGETS } from './tiles.js';
import { whenDialog, whenOk, whenText } from './when.js';

// ------------------------------------------------------------------ what a block can be
/* iostart/layout.py BLOCKS. Each kind: its name for a block, what an Add list says of it, whether it can stand on this
   page at all (its app is here), and `draw(b)`: the element, whose `redraw(again)` asks its app and fills it in. A card
   tells whether it has anything to say through core.js quiet(). */
const UNIT = 275, GAP = 16, MINW = 300;  // a row of a block with a set height; the gap; the least width of a column
const CAPS = new Set(['birthdays', 'week', 'news', 'bookmarks', 'home']);  // lists: with a set height, what does not fit scrolls
const appOf = (key) => (S.apps || []).find((a) => a.key === key);
const has = (key) => !!appOf(key);
let family = null;  // the family list (/api/auth/family), asked once: a week card for one of them names them
const familyList = () => (family = family || api('api/auth/family').then((d) => d.items || []).catch(() => { family = null; return []; }));

const KINDS = {
  app: {
    name: (b) => (appOf(b.app) ? appOf(b.app).name : b.app),
    there: (b) => has(b.app),
    draw(b) {
      const a = appOf(b.app), el = tileOf(a, false), box = el.querySelector('.more'), draw = WIDGETS[a.key];
      el.redraw = async (again) => {
        if (!draw) { quiet(el, true); return; }  // an app with nothing to show here: its tile opens it
        let d = null, why = '';
        try { const r = await wget(`api/widgets/${a.key}?tz=${encodeURIComponent(viewerTz())}`); if (r.ok && r.body) d = r.body; else why = (r.body && r.body.detail) || String(r.status); } catch (e) { why = e.message; }
        if (!el.isConnected) return;
        if (!d) { if (!again || !box.querySelector('.wghead')) box.replaceChildren(h('div', { class: 'wg' }, h('div', { class: 'muted small wgwhy' }, why))); quiet(el, true); return; }
        const kids = draw(d);
        box.replaceChildren(h('div', { class: 'wg' }, kids || h('div', { class: 'muted small wgwhy' }, EMPTY[a.key] || 'Nothing to show')));
        quiet(el, !kids);
      };
      return el;
    },
  },
  apps: {
    name: (b) => (b.apps && b.apps.length === 1 && appOf(b.apps[0]) ? appOf(b.apps[0]).name : 'Apps to open'),
    there: () => true,
    draw(b) {
      const list = b.apps && b.apps.length ? b.apps.map(appOf).filter(Boolean) : (S.apps || []);
      const dock = b.look !== 'list';
      const el = h('div', { class: dock ? 'dock' : 'glist' }, list.map((a) => tileOf(a, true)));
      if (dock) {  // one row when the tiles fit at 92px or more, else rows of the same length
        const fit = () => { const most = Math.max(1, Math.floor((el.clientWidth + 8) / 100)), rows = Math.ceil(list.length / most); el.style.setProperty('--per', Math.ceil(list.length / Math.max(1, rows)) || 1); };
        new ResizeObserver(fit).observe(el);
      }
      el.redraw = () => {
        for (const t of el.querySelectorAll('.app[data-app]')) { const line = LOW[t.dataset.app] || (dock ? null : LINES[t.dataset.app]); if (line) drawLowLine(t, t.querySelector('.who > .line'), viewerTz(), line); }
        quiet(el, !list.length);
      };
      return el;
    },
  },
  today: {
    name: () => 'Today',
    there: () => ['iocalendar', 'iotask', 'iocontact', 'iomoney', 'iohealth', 'iopix'].some(has),
    draw() { const el = h('div', { class: 'glance' }); el.redraw = (again) => drawGlance(el, again); return el; },
  },
  home: {
    name: (b) => b.title || 'Home',
    there: () => S.ha !== false,
    missing: 'Home Assistant is not set up (Settings): this block stays empty until it is.',
    draw(b) { const el = h('div', { class: 'card homecard', hidden: true }); el.haOpts = { title: b.title, entities: b.entities }; el.redraw = (again) => drawHomeCard(el, again); return el; },
  },
  birthdays: {
    name: () => 'Birthdays',
    there: () => has('iocontact'),
    draw() { const el = h('div', { class: 'card capped birthdays' }); el.redraw = (again) => drawBirthdays(el, again); return el; },
  },
  week: {
    name: () => 'This week',
    there: () => has('iocalendar'),
    draw(b) {
      const el = h('div', { class: 'card capped week' });
      el.redraw = async (again) => {
        if (b.who) { const m = (await familyList()).find((x) => x.id === b.who); el.who = { id: b.who, name: m ? (m.displayName || m.name).split(/\s+/)[0] : 'Their' }; }
        return drawWeek(el, again);
      };
      return el;
    },
  },
  strip: {
    name: () => 'Photos',
    there: () => has('iopix'),
    draw(b, ctx) {
      const el = h('div', { class: 'strip' }), kind = b.strip || (ctx.strip && ctx.strip !== 'off' ? ctx.strip : 'rediscover');
      el.redraw = (again) => { if (!again) drawStrip(el, kind); };  // the strip changes by itself (autoStrip)
      return el;
    },
  },
  news: {
    name: (b) => b.folder || 'Headlines',
    there: () => true,
    draw(b, ctx) { const el = h('div', { class: 'card newscard', hidden: !ctx.A }); el.folder = b.folder || ''; el.lines = Math.min(12, 8 * (b.h || 1)); el.redraw = () => drawNewsCard(el, !!ctx.A); return el; },
  },
  bookmarks: {
    name: () => 'Bookmarks',
    there: () => true,
    draw(b) { const el = h('div', { class: b.group != null ? 'bookmarks bmone' : 'bookmarks' }); if (b.group != null) el.group = b.group; el.look = b.look || null; el.redraw = (again) => { if (!again) drawBookmarks(el); else drawBookmarkStatus(el); }; return el; },
  },
};
export const blockName = (b) => (KINDS[b.kind] ? KINDS[b.kind].name(b) : b.kind);

// ------------------------------------------------------------------ a grid made from the page as it was
/** The first grid of a page: what the page showed in the layout it had, block for block, so that turning the grid on
    changes nothing until the person moves something. */
export function gridFrom(L, strip) {
  const apps = S.apps || [], blocks = [], id = () => newId(6);
  if (L.style === 'today') blocks.push({ id: id(), kind: 'apps', w: 4 }, { id: id(), kind: 'today', w: 4 });
  else {
    const low = [];
    for (const a of apps) { if (WIDGETS[a.key] && !LOW[a.key] && sizeOf(a.key, L) !== 'tile') blocks.push({ id: id(), kind: 'app', app: a.key }); else low.push(a.key); }
    if (low.length) blocks.push({ id: id(), kind: 'apps', apps: low, look: 'list' });
  }
  const shows = (k) => !(L.hidden || []).includes(k);
  for (const k of cardOrder(L)) {
    if (!shows(k)) continue;
    if (k === 'home') blocks.push({ id: id(), kind: 'home', w: 4 });
    else if (k === 'birthdays' && has('iocontact')) blocks.push({ id: id(), kind: 'birthdays', h: 1 });
    else if (k === 'week' && has('iocalendar')) blocks.push({ id: id(), kind: 'week', w: 2, h: 1 });
    else if (k === 'strip' && has('iopix') && (L.strip || strip) !== 'off') blocks.push({ id: id(), kind: 'strip', w: 4 });
    else if (k === 'news') blocks.push({ id: id(), kind: 'news', w: 4 });
    else if (k === 'bookmarks') blocks.push({ id: id(), kind: 'bookmarks', w: 4 });
  }
  return { cols: null, sections: [{ id: id(), title: null, blocks }] };
}

// ------------------------------------------------------------------ drawing it
const foldedIds = () => { try { const v = JSON.parse(localStorage.getItem('iostart.folded') || '[]'); return Array.isArray(v) ? v.map(String) : []; } catch { return []; } };
function setFolded(id, on) {
  const ids = foldedIds().filter((x) => x !== id);
  try { localStorage.setItem('iostart.folded', JSON.stringify((on ? [...ids, id] : ids).slice(-60))); } catch { /* private mode */ }
}

/** Draws the grid of the page (L.grid) into `col`. ctx: {L, A: the page is being arranged (S.arrange), page: the page's
    element, redraw: the page again after a change, strip: the admin's photo strip}. Gives back refresh(): every block
    asks its app anew. */
export function drawGrid(col, ctx) {
  const { L, A } = ctx, g = L.grid, cols = g.cols || 3, folded = foldedIds();
  const root = h('div', { class: 'gsecs' });
  root.style.setProperty('--gcols', cols);
  const wraps = [];
  S.birthdaysCard = false;
  g.sections.forEach((sec, si) => {
    if (!A && !whenOk(sec.when)) return;
    const grid = h('div', { class: 'ggrid' }), shut = !A && !!sec.title && folded.includes(sec.id);
    const el = h('section', { class: `gsec${shut ? ' shut' : ''}`, 'data-sec': sec.id }, A ? sectionBar(sec, si, ctx) : sectionHead(sec, grid), grid);
    grid.hidden = shut;
    for (const b of sec.blocks) {
      if (!KINDS[b.kind] || (!A && !whenOk(b.when))) continue;
      const w = blockEl(b, sec, ctx);
      if (!w) continue;
      if (b.kind === 'birthdays') S.birthdaysCard = true;  // then the calendar leaves birthdays to it
      grid.append(w); wraps.push(w);
    }
    if (A) grid.append(h('button', { class: 'gadd arr arrok', 'data-arr': 'block', 'data-key': `@${sec.id}`, title: 'Add a block here', onclick: async () => { const b = await addBlock(ctx); if (b) { sec.blocks.push(b); ctx.redraw(); } } }, icon('add'), 'Add a block'));
    root.append(el);
  });
  if (A) root.append(h('button', { class: 'gaddsec arrok', title: 'A new section under these, with a heading of its own', onclick: () => { if (g.sections.length >= 12) { toast('Twelve sections is the most a page holds'); return; } g.sections.push({ id: newId(6), title: 'New section', blocks: [] }); ctx.redraw(); } }, icon('add', 's'), 'Add a section'));
  else if (!wraps.length) root.append(h('div', { class: 'empty' }, 'Nothing is laid out on this page yet. ', h('button', { class: 'lnk', onclick: ctx.arrange }, 'Arrange the page')));
  col.append(root);
  // as many columns as fit at a width a card's lines can be read in, and no more than the person set; a block never
  // takes more columns than there are
  let n = 0;
  const fit = () => {
    const now = Math.max(1, Math.min(cols, Math.floor((root.clientWidth + GAP) / (MINW + GAP))));
    if (now === n) return;
    n = now; root.style.setProperty('--n', n);
    for (const w of wraps) w.style.setProperty('--w', Math.min(w.block.w || 1, n));
  };
  new ResizeObserver(fit).observe(root); fit();
  // a section whose blocks all stay off the page for now goes with them, heading and all
  const tidy = () => { if (A) return; for (const s of root.querySelectorAll('.gsec')) s.hidden = ![...s.querySelectorAll('.gblock')].some((w) => !w.hidden && w.firstElementChild && !w.firstElementChild.hidden); };
  root.tidy = tidy;
  // each block asks its app once the page stands in the document (a page being arranged is built beside it first, and
  // an answer kept from before would come back sooner than that)
  setTimeout(() => { for (const w of wraps) if (w.card.isConnected) w.card.redraw(false); tidy(); }, 0);
  if (A) for (const w of wraps) arrangeDrag(ctx.page, w, { move: (key, target, after) => moveBlock(g, key, target, after), next: (key, dir) => nextBlock(g, key, dir) });
  return { refresh: () => { for (const w of wraps) if (w.card.isConnected) w.card.redraw(true); } };
}

/** A section's heading: its name, which folds the section shut and open (this browser remembers which). */
function sectionHead(sec, grid) {
  if (!sec.title) return null;
  const btn = h('button', { class: 'gsecfold', 'aria-expanded': String(!foldedIds().includes(sec.id)), onclick: () => {
    const shut = !grid.hidden; grid.hidden = shut; btn.setAttribute('aria-expanded', String(!shut)); btn.closest('.gsec').classList.toggle('shut', shut); setFolded(sec.id, shut);
  } }, icon('right', 's'), h('span', null, sec.title));
  return h('h2', { class: 'gsechead' }, btn);
}

/** One block on the page: its card in a cell as wide and as tall as the person made it. */
function blockEl(b, sec, ctx) {
  const { A } = ctx, kind = KINDS[b.kind];
  const there = kind.there(b);
  if (!there && !A) return null;
  const card = there ? kind.draw(b, ctx) : h('div', { class: 'card gph' }, h('div', { class: 'muted small' }, kind.missing || `${blockName(b)}: its app is not on this page (Customize, Apps), so the block stays empty.`));
  if (!card.redraw) card.redraw = () => {};
  const wrap = h('div', { class: `gblock gk-${b.kind}${b.h ? ' gset' : ''}`, 'data-block': b.id }, card);
  wrap.block = b; wrap.card = card;
  wrap.style.setProperty('--w', b.w || 1); wrap.style.setProperty('--h', b.h || 1);
  const only = !A && b.when && b.when.content;  // off the page until it has something to say
  if (only) wrap.hidden = true;
  card.onquiet = (q, gone) => {
    if (A) { if (gone) setTimeout(() => { if (!card.isConnected || card.hidden) { card.hidden = false; card.className = 'card gph'; card.replaceChildren(h('div', { class: 'muted small' }, `${blockName(b)} has nothing to show right now.`)); if (!card.isConnected) wrap.prepend(card); } }, 0); return; }
    wrap.hidden = gone || (only && q);
    const root = wrap.closest('.gsecs'); if (root && root.tidy) root.tidy();
  };
  if (b.h && CAPS.has(b.kind)) capBlock(wrap, card, b.h);
  if (A) blockMark(wrap, b, sec, ctx);
  return wrap;
}

/** A list with a set height: the cell is as tall as the list wants, up to its rows; what does not fit scrolls (and the
    list fades out at the bottom). The card fills the cell, so beside a taller neighbour it shows more. */
function capBlock(wrap, card, hgt) {
  const cap = hgt * UNIT + (hgt - 1) * GAP;
  wrap.classList.add('gcap');
  const fit = () => {
    if (!card.isConnected) return;
    // what the list needs: down to the end of its last part, with what a list that was cut short (.rows) holds out of sight
    const kids = [...card.children].filter((x) => !x.hidden && x.offsetParent), cs = getComputedStyle(card);
    const cut = kids.reduce((n, x) => n + (x.classList.contains('rows') ? Math.max(0, x.scrollHeight - x.clientHeight) : 0), 0);
    const need = kids.length ? Math.ceil(Math.max(...kids.map((x) => x.offsetTop + x.offsetHeight)) + cut + parseFloat(cs.paddingBottom || 0) + parseFloat(cs.borderBottomWidth || 0)) : 60;
    const open = card.classList.contains('card') && card.querySelector('.showall') && !card.classList.contains('capped');  // "Show all" was pressed
    wrap.style.setProperty('--want', `${open ? need : Math.min(need, cap)}px`);
    const over = need > wrap.clientHeight + 1;
    card.classList.toggle('over', over);
    const btn = card.querySelector('.showall'), hide = !over && !open;
    if (btn && btn.tagName === 'BUTTON' && btn.hidden !== hide) btn.hidden = hide;
  };
  // measured once a frame at most: what it sets (a class, a button) is itself a change the card is watched for
  let due = false;
  const soon = () => { if (due) return; due = true; requestAnimationFrame(() => { due = false; fit(); }); };
  new ResizeObserver(soon).observe(wrap);
  new MutationObserver(soon).observe(card, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden'] });
  soon();
}

// ------------------------------------------------------------------ arranging: a block's handle, its options, its size
/** While the page is arranged: on a block, a handle to drag it by, its options, a button to take it off, and a corner
    to pull it wider or taller. */
function blockMark(wrap, b, sec, ctx) {
  const name = blockName(b), g = ctx.L.grid;
  wrap.classList.add('arr'); wrap.dataset.arr = 'block'; wrap.dataset.key = b.id;
  const press = (act) => (e) => { e.preventDefault(); e.stopPropagation(); act(); };
  const ctl = h('span', { class: 'arrctl' },
    h('button', { class: 'arrbtn arrgrip', title: `Drag to move ${name} (or the arrow keys)`, 'aria-label': `Move ${name}`, onclick: press(() => {}) }, icon('grip', 's')),
    h('button', { class: `arrbtn${b.when ? ' set' : ''}`, title: `${name}: what it shows, its size${b.when ? `. Shows: ${whenText(b.when)}` : ', when it shows'}`, 'aria-label': `Options of ${name}`,
      onclick: press(async () => { if (await blockDialog(b, ctx)) ctx.redraw(); }) }, icon(b.when ? 'schedule' : 'tune', 's')),
    h('button', { class: 'arrbtn', title: `Take ${name} off the page`, 'aria-label': `Remove ${name}`, onclick: press(() => { sec.blocks = sec.blocks.filter((x) => x !== b); ctx.redraw(); }) }, icon('close', 's')));
  const size = h('button', { class: 'gresize', title: 'Drag to make it wider or taller (or the arrow keys); twice: as tall as what it shows', 'aria-label': `Size of ${name}` }, icon('resize', 's'));
  wrap.append(ctl, size);
  // a card draws itself anew when its app answers: the buttons go back on top of what it drew
  const max = g.cols || 3;
  const set = (w, hh) => {
    w = Math.max(1, Math.min(max, w)); if (w >= max) w = 4;  // every column: the full width, whatever the screen has
    const was = [b.w || 1, b.h || null];
    if (w === 1) delete b.w; else b.w = w;
    if (hh == null) delete b.h; else b.h = Math.max(1, Math.min(3, hh));
    if (was[0] !== (b.w || 1) || was[1] !== (b.h || null)) ctx.redraw();
  };
  const wide = () => Math.min(b.w || 1, max);
  size.addEventListener('keydown', (e) => {
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!d) return;
    e.preventDefault();
    set(wide() + d[0], d[1] ? (b.h || 1) + d[1] : (b.h || null));
  });
  size.addEventListener('dblclick', press(() => set(wide(), null)));
  size.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); });
  size.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault(); e.stopPropagation();
    const r = wrap.getBoundingClientRect(), grid = wrap.parentNode, n = +getComputedStyle(grid).getPropertyValue('--n') || 1;
    const colW = (grid.clientWidth - GAP * (n - 1)) / n, x0 = e.clientX, y0 = e.clientY;
    const ghost = h('div', { class: 'gghost' }); document.body.append(ghost);
    let w = Math.min(b.w || 1, n), hh = b.h || null, moved = false;
    const move = (ev) => {
      if (ev.pointerId !== e.pointerId) return;
      const dx = ev.clientX - x0, dy = ev.clientY - y0;
      if (!moved && Math.hypot(dx, dy) < 5) return;
      moved = true;
      w = Math.max(1, Math.min(n, Math.round((r.width + dx + GAP) / (colW + GAP))));
      if (Math.abs(dy) > 24) hh = Math.max(1, Math.min(3, Math.round((r.height + dy + GAP) / (UNIT + GAP))));
      Object.assign(ghost.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${w * colW + (w - 1) * GAP}px`, height: `${hh ? hh * UNIT + (hh - 1) * GAP : r.height}px` });
      ghost.textContent = `${w >= n && n >= max ? 'Full width' : w === 1 ? '1 column' : `${w} columns`}${hh ? ` · ${hh === 1 ? '1 row' : `${hh} rows`}` : ''}`;
    };
    const end = (ev) => {
      if (ev.pointerId !== e.pointerId) return;
      removeEventListener('pointermove', move); removeEventListener('pointerup', end); removeEventListener('pointercancel', end);
      ghost.remove();
      if (moved && ev.type === 'pointerup') set(w >= n && n < max ? Math.max(b.w || 1, w) : w, hh);  // on a narrow screen "as wide as it gets" keeps a wider choice made elsewhere
    };
    addEventListener('pointermove', move); addEventListener('pointerup', end); addEventListener('pointercancel', end);
  });
  const A = ctx.A, held = () => A.held && A.held.kind === 'block' && A.held.key === b.id && Date.now() - A.held.at < 4000;
  new MutationObserver(() => { if (ctl.parentNode === wrap) return; wrap.append(ctl, size); if (held()) ctl.querySelector('.arrgrip').focus(); }).observe(wrap, { childList: true });
}

/** A section's bar while the page is arranged: its heading to type, up and down, when it shows, and a button to remove it. */
function sectionBar(sec, i, ctx) {
  const g = ctx.L.grid, n = g.sections.length;
  const title = h('input', { class: 't gsectitle', value: sec.title || '', maxlength: 40, placeholder: 'A heading for this section (none)', 'aria-label': 'Heading', onchange: () => { sec.title = title.value.replace(/\s+/g, ' ').trim() || null; } });
  const move = (by) => { g.sections.splice(i, 1); g.sections.splice(i + by, 0, sec); ctx.redraw(); };
  const btn = (ic, tip, act, off) => h('button', { class: 'arrbtn', title: tip, 'aria-label': tip, disabled: off ? true : null, onclick: act }, icon(ic, 's'));
  return h('div', { class: 'gsecbar arrok' }, title,
    btn('up', 'Move this section up', () => move(-1), i === 0), btn('down', 'Move this section down', () => move(1), i === n - 1),
    h('button', { class: `arrbtn${sec.when ? ' set' : ''}`, title: sec.when ? `Shows: ${whenText(sec.when)}` : 'Show this section only when…', onclick: async () => { const r = await whenDialog(sec.title || 'this section', sec.when, { content: false }); if (r) { if (r.when) sec.when = r.when; else delete sec.when; ctx.redraw(); } } }, icon('schedule', 's')),
    btn('delete', 'Remove this section', async () => {
      if (sec.blocks.length && !await confirmDialog('Remove the section', `Its ${sec.blocks.length === 1 ? 'block goes' : `${sec.blocks.length} blocks go`} with it.`, 'Remove', true)) return;
      g.sections = g.sections.filter((x) => x !== sec); ctx.redraw();
    }, n === 1 && !sec.blocks.length));
}

/** Puts block `key` before or after block `target` (or, for a target "@<section id>", at the end of that section). */
function moveBlock(g, key, target, after) {
  const from = g.sections.find((s) => s.blocks.some((b) => b.id === key));
  if (!from || key === target) return false;
  const b = from.blocks.find((x) => x.id === key);
  const to = target.startsWith('@') ? g.sections.find((s) => s.id === target.slice(1)) : g.sections.find((s) => s.blocks.some((x) => x.id === target));
  if (!to) return false;
  from.blocks = from.blocks.filter((x) => x !== b);
  const i = target.startsWith('@') ? to.blocks.length : to.blocks.findIndex((x) => x.id === target) + (after ? 1 : 0);
  to.blocks.splice(i, 0, b);
  return true;
}
/** For the arrow keys on a handle: where the block goes one place earlier or later, [target, after], or null at an end. */
function nextBlock(g, key, dir) {
  const all = g.sections.flatMap((s) => (s.blocks.length ? s.blocks.map((b) => b.id) : [`@${s.id}`]));
  const to = all[all.indexOf(key) + dir];
  return to ? [to, dir > 0 && !to.startsWith('@')] : null;
}

// ------------------------------------------------------------------ the Add list, and a block's options
/** What can be added to this page, each with a few words and how it starts out. */
function choices(ctx) {
  const out = [];
  const add = (kind, about, more = {}, name = null, ask = false) => { const b = { kind, ...more }; if (KINDS[kind].there(b)) out.push({ b, name: name || blockName(b), about, ask }); };
  add('today', 'The day’s events and tasks by the hour, the week’s bills, with Health and On this day beside', { w: 2 });
  add('apps', 'Every app of the page in a row, to open it', { w: 4 });
  for (const a of S.apps || []) if (WIDGETS[a.key]) add('app', APP_ABOUT[a.key] || 'What it has for today', { app: a.key }, `${a.name}’s card`);
  add('week', 'The coming days, day by day', { w: 2, h: 1 });
  add('week', 'The coming days of one member of the family', { w: 2, h: 1 }, 'Someone’s week', true);
  add('birthdays', 'Birthdays and other dates in the next 30 days', { h: 1 });
  add('home', 'The lights, doors and sensors picked for the page', { w: 2 });
  add('home', 'A few of them under a name of their own: the kitchen, the garden', { w: 2, entities: [] }, 'A room', true);
  add('strip', 'A row of photos that changes by itself', { w: 4 });
  add('news', 'The newest articles of the feeds you keep on the page', { w: 2 });
  add('news', 'The newest articles of one folder of your feeds', { w: 2 }, 'Headlines of one folder', true);
  add('bookmarks', 'Every group of bookmarks on the page', { w: 4 });
  add('bookmarks', 'One group, as a card of its own', {}, 'One group of bookmarks', true);
  return out;
}
const APP_ABOUT = { iopix: 'Photos from this day in earlier years', iocalendar: 'What is left of today, or what comes next', iotask: 'What is due today, to tick off', iohealth: 'Steps, rings and last night’s sleep',
  iomoney: 'Bills this week, a balance running low', iodocs: 'Papers to renew' };

/** The Add list: a dialog with everything this page can hold, each with a small look at it as it would stand. Resolves
    with the new block, or null. */
async function addBlock(ctx) {
  const body = h('div', { class: 'pickblock' });
  const back = () => body.closest('.dialog-back');
  for (const c of choices(ctx)) {
    const prev = h('div', { class: 'pickprev', 'aria-hidden': 'true' });
    const row = h('button', { class: 'pickcard', onclick: async () => {
      const b = { id: newId(6), ...JSON.parse(JSON.stringify(c.b)) };
      if (c.ask) { back().hidden = true; if (!await blockDialog(b, ctx, true)) { back().hidden = false; return; } }
      back().close(b);
    } }, prev, h('span', { class: 'pickname' }, c.name), h('span', { class: 'muted small' }, c.about));
    body.append(row);
    // its look: the real card, drawn small (one that asks first shows as a plain one of its kind)
    try {
      const card = KINDS[c.b.kind].draw({ id: 'preview', ...c.b, entities: undefined }, { ...ctx, A: null });
      const inner = h('div', { class: `pickin gblock gk-${c.b.kind}` }, card); inner.inert = true;
      prev.append(inner);
      setTimeout(() => { if (card.isConnected && card.redraw) Promise.resolve(card.redraw(false)).catch(() => {}); }, 0);
    } catch { /* no look at it then */ }
  }
  const got = await dialog('Add a block', body, [{ label: 'Cancel', value: null }], 'wide');
  return got || null;
}

/** A block's options: what it shows (by kind), how wide and how tall it is, when it shows. Changes `b` in place and
    resolves true when OK was pressed. fresh: the block is being added (no size or rule to ask about yet). */
async function blockDialog(b, ctx, fresh = false) {
  const cols = ctx.L.grid.cols || 3, kids = [];
  const pick = (opts, now) => h('select', { class: 't' }, opts.map(([v, t]) => h('option', { value: v, selected: String(v) === String(now == null ? '' : now) ? true : null }, t)));
  const ticks = (items, on) => { const boxes = items.map(([v, label]) => [v, h('input', { type: 'checkbox', checked: on.includes(v) }), label]);
    return { el: h('div', { class: 'gticks' }, boxes.map(([, box, label]) => h('label', { class: 'check' }, box, label))), get: () => boxes.filter(([, box]) => box.checked).map(([v]) => v) }; };
  const read = [];  // each part writes what it holds into b
  if (b.kind === 'app') {
    const sel = pick((S.apps || []).filter((a) => WIDGETS[a.key]).map((a) => [a.key, a.name]), b.app);
    kids.push(fld('The card of', sel)); read.push(() => { b.app = sel.value; });
  }
  if (b.kind === 'apps') {
    const look = pick([['', 'Icons in a row'], ['list', 'One under the other, with a line each']], b.look);
    const which = ticks((S.apps || []).map((a) => [a.key, a.name]), b.apps || []);
    kids.push(fld('As', look), h('h3', null, 'Which apps'), h('p', { class: 'muted small' }, 'None ticked: every app of the page, in the page’s order.'), which.el);
    read.push(() => { if (look.value) b.look = look.value; else delete b.look; const keys = which.get(); if (keys.length) b.apps = keys; else delete b.apps; });
  }
  if (b.kind === 'home') {
    let d = S.ha; if (d == null) { try { const r = await api('api/ha'); d = r.enabled ? r : false; } catch { d = false; } }
    const items = (d && d.items) || [];
    const title = h('input', { class: 't', maxlength: 40, value: b.title || '', placeholder: (d && d.name) || 'Home' });
    const which = ticks(items.map((t) => [t.id, `${t.name} (${t.text || t.state})`]), b.entities || []);
    kids.push(fld('Its name', title), h('h3', null, 'Which things'), h('p', { class: 'muted small' }, items.length ? 'None ticked: everything picked for the page (Settings, Home Assistant).' : 'Nothing is picked for the page yet (Settings, Home Assistant).'), which.el);
    read.push(() => { const t = title.value.replace(/\s+/g, ' ').trim(); if (t) b.title = t; else delete b.title; const ids = which.get(); if (ids.length) b.entities = ids; else delete b.entities; });
  }
  if (b.kind === 'week') {
    const fam = await familyList();
    const who = pick([['', 'Everyone'], ...fam.map((m) => [m.id, m.displayName || m.name])], b.who);
    kids.push(fld('Whose week', who, fam.length ? 'The events ioCalendar has someone of the family on.' : 'The family list is empty (Settings, People, Family).'));
    read.push(() => { if (who.value) b.who = +who.value; else delete b.who; });
  }
  if (b.kind === 'strip') {
    const sel = pick([['', 'As the page’s photo strip'], ['rediscover', 'Rediscover: photos at random'], ['onthisday', 'On this day']], b.strip);
    kids.push(fld('Photos', sel)); read.push(() => { if (sel.value) b.strip = sel.value; else delete b.strip; });
  }
  if (b.kind === 'news') {
    let folders = []; try { folders = (await api('api/news')).folders || []; } catch { /* not a member: no feeds */ }
    const sel = pick([['', 'The feeds you keep on the page'], ...folders.map((f) => [f, `The folder ${f}`]), ...(b.folder && !folders.includes(b.folder) ? [[b.folder, `${b.folder} (no longer there)`]] : [])], b.folder);
    kids.push(fld('Headlines of', sel, folders.length ? null : 'Put feeds in a folder in the reader (gear menu, Feeds) to give it a card of its own.'));
    read.push(() => { if (sel.value) b.folder = sel.value; else delete b.folder; });
  }
  if (b.kind === 'bookmarks') {
    let gs = []; try { gs = (await bookmarkGroups()).groups; } catch { /* none */ }
    const id = (x) => String(x.id != null ? x.id : x.name);
    const sel = pick([['', 'Every group on the page'], ...gs.map((x) => [id(x), x.name])], b.group);
    const look = pick([['', 'As the page’s (Customize, Cards)'], ['icons', 'Icons only'], ['folded', 'Folders shut, open on a tap']], b.look);
    kids.push(fld('Which', sel), fld('Shown as', look));
    read.push(() => { if (sel.value) b.group = sel.value; else delete b.group; if (look.value) b.look = look.value; else delete b.look; });
  }
  // the size, and when it shows
  const w = Math.min(b.w || 1, cols) >= cols ? 4 : b.w || 1;
  const width = pick([...Array.from({ length: cols - 1 }, (_, i) => [i + 1, i ? `${i + 1} columns` : '1 column']), [4, 'The full width']], w);
  const height = pick([['', 'As tall as what it shows'], [1, 'One row at most'], [2, 'Two rows'], [3, 'Three rows']], b.h);
  let rule = b.when || null;
  const ruleBtn = h('button', { class: 'lnk' }), ruleDraw = () => { ruleBtn.textContent = rule ? whenText(rule) : 'Always. Change…'; };
  ruleBtn.onclick = async () => { const r = await whenDialog(blockName(b), rule); if (r) { rule = r.when; ruleDraw(); } };
  ruleDraw();
  if (!fresh) {
    kids.push(h('h3', null, 'Its size'), h('div', { class: 'grid' }, fld('Width', width), fld('Height', height)),
      h('p', { class: 'muted small' }, 'On a narrower screen a block is never wider than the screen. With a height set, what does not fit scrolls inside the block.'),
      h('h3', null, 'It shows'), ruleBtn);
    read.push(() => { if (+width.value > 1) b.w = +width.value; else delete b.w; if (height.value) b.h = +height.value; else delete b.h; if (rule) b.when = rule; else delete b.when; });
  }
  if (!kids.length) return true;
  const ok = await dialog(fresh ? `Add: ${blockName(b)}` : blockName(b), h('div', { class: 'blockform' }, kids), [{ label: 'Cancel', value: false }, { label: fresh ? 'Add' : 'OK', value: true, primary: true }]);
  if (!ok) return false;
  for (const f of read) f();
  return true;
}

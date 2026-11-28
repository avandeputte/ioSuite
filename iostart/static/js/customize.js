/* Customize the page (a dialog, per account or per device) and Arrange (in place, on the page itself). */
import { confirmDialog, dialog, fail, fld, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { $, api, appName, dragSort, newId, S } from './core.js';
import { everyText, STRIP_DEFAULT, STRIP_EVERY, STRIP_MOVES } from './cards.js';
import { applyLook, CARD_NAMES, cardOrder, CARDS, deviceGuess, deviceId, loadApps, newDeviceId, NO_LAYOUT, saveLayout, showHome, sizeOf, STYLES, TOP_PARTS } from './home.js';
import { gridFrom } from './grid.js';
import { onRoute, route } from './main.js';
import { askName, BLANK, PAGES_MOST, pageHref, pageId, pagesOf, pageView, putPage } from './pages.js';
import { BANG_HELP, ENGINES } from './search.js';
import { drawGlance, LINES, widget, WIDGETS } from './tiles.js';
import { WALL_BG_NAMES, WALL_BGS, WALL_DEFAULT_EVERY, WALL_EVERY } from './wall.js';
import { whenDialog, whenText } from './when.js';

// ------------------------------------------------------------------ customize the page (per account, or per device)
/* The person's setup (iostart/layout.py), in a dialog of a few tabs: the page (which devices it is for, its pages, the
   layout, the top row), the apps (which, in what order, at what size), the cards (which, in what order, what the Today
   card holds, how the bookmarks look), the look (colour, type), the photos (the strip and the wall display), copying
   (a ready-made page, someone's setup, the setup as text) and, for an admin, the family (everyone's starting point, a
   setup given to one person). With several pages, the apps, the cards and the layout are those of the page shown; the
   rest is the same on every page. Arranging on the page itself: arrangeStart. */
const ACCENTS = { '': ['Night blue', '#3b4a8c'], blue: ['Blue', '#1a66c9'], teal: ['Teal', '#0b7a75'], green: ['Green', '#2a7d3c'], amber: ['Amber', '#a25a00'],
  red: ['Red', '#c0392f'], pink: ['Pink', '#b8336f'], purple: ['Purple', '#6b3fb5'], graphite: ['Graphite', '#4a4f57'] };
const TEXTS = [['compact', 'Smaller'], ['', 'Normal'], ['large', 'Larger']];
const BM_LOOKS = [['', 'The full list'], ['icons', 'Icons only'], ['folded', 'Folders shut, open on a tap']];
// what the Today layout shows: [its name on a switch, in the dialog, the app it comes from]
const TODAY_PARTS = { events: ['Events', 'Events', 'iocalendar'], tasks: ['Tasks', 'Tasks', 'iotask'], birthdays: ['Birthdays', 'Birthdays', 'iocontact'], bills: ['Bills', 'Bills this week', 'iomoney'],
  health: ['Health', 'Health, in a card beside it', 'iohealth'], photos: ['Photos', 'On this day photos, beside it', 'iopix'] };
// the weather's extras, each one to switch off (layout weatherOff)
const WEATHER_PARTS = { warnings: 'Severe weather warnings', sun: 'Sunrise, sunset and daylight', air: 'Air quality', pollen: 'Pollen' };
const TODAY_DAYS = [['', 'The week ahead'], ['0', 'Today only'], ['1', 'Tomorrow too'], ['2', 'Two days ahead'], ['3', 'Three days ahead']];
const SIZES = [['', 'Automatic'], ['card', 'Always a card'], ['tile', 'Always a low tile']];
const GRID_COLS = [['2', 'Two'], ['', 'Three'], ['4', 'Four']];  // the most blocks across in the person's own grid
const copy = (v) => JSON.parse(JSON.stringify(v));
const pick = (opts, now, attrs = {}) => h('select', { class: 't', ...attrs }, opts.map(([v, t]) => h('option', { value: v, selected: String(v) === String(now == null ? '' : now) ? true : null }, t)));

/** o: what the dialog starts from when it is opened again by itself: {draft: a setup not saved yet (a copy, a
    ready-made page, the text read back), note: a line on top saying so, forThis, devName: the choice of devices}. */
export async function customize(tab = 'page', o = {}) {
  if (!S.full) {  // opened from another view before the start page was ever drawn
    try { await loadApps(); } catch (e) { fail(e); return; }
  }
  const of = S.layoutOf || { scope: 'none', device: null, devices: [], family: false };
  // the whole setup (a copy: its pages are changed here), and the page shown as the tabs below have it
  const full = copy({ ...NO_LAYOUT(), ...(o.draft || S.full) }), pid = pageId(full, S.pid), L = { ...NO_LAYOUT(), ...pageView(full, pid) };
  const apps = (S.allApps || []).filter((a) => !a.adminTool);  // the admin tools are in the gear menu, not tiles
  const rank = (a) => { const i = L.order.indexOf(a.key); return i < 0 ? 100 + apps.indexOf(a) : i; };
  const tiles = apps.slice().sort((a, b) => rank(a) - rank(b)).map((a) => ({ key: a.key, on: !L.hidden.includes(a.key), size: WIDGETS[a.key] ? sizeOf(a.key, L) : null, label: [h('img', { src: a.icon, alt: '' }), appName(a.name, a.color)] }));
  const cards = cardOrder(L).map((k) => ({ key: k, on: !L.hidden.includes(k), label: [CARD_NAMES[k]] }));
  const top = Object.entries(TOP_PARTS).map(([k, name]) => ({ key: k, on: !L.hidden.includes(k), name }));
  const has = (k) => apps.some((a) => a.key === k);
  const parts = Object.entries(TODAY_PARTS).filter(([, [, , app]]) => has(app)).map(([k, [, name]]) => ({ key: k, on: !L.todayOff.includes(k), name }));
  const wxParts = Object.entries(WEATHER_PARTS).map(([k, name]) => ({ key: k, on: !(L.weatherOff || []).includes(k), name }));
  const tick = (t, label) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: t.on, onchange: (e) => { t.on = e.target.checked; } }), label);
  // a list of rows with a drag handle and a tick box, for the tiles and for the cards alike (dragSort, as the bookmarks);
  // an app that has something to show also gets its size
  const sortable = (items) => {
    const list = h('div', { class: 'lay' });
    const draw = () => {
      list.replaceChildren(...items.map((t) => h('div', { class: 'layrow', 'data-key': t.key },
        h('button', { class: 'iconbtn grip', title: 'Drag to reorder', 'aria-label': 'Drag to reorder' }, icon('grip', 's')), tick(t, t.label),
        t.size != null ? pick(SIZES, t.size, { class: 't laysize', title: 'Its size, in the layout with a card for each app', 'aria-label': 'Size', onchange: (e) => { t.size = e.target.value; } }) : null)));
      for (const g of list.querySelectorAll('.grip')) dragSort(g, g.closest('.layrow'), { root: list, lists: () => [list], items: '.layrow', sorting: 'sorting-rows',
        done: () => { const by = Object.fromEntries(items.map((t) => [t.key, t])); items.splice(0, items.length, ...[...list.querySelectorAll('.layrow[data-key]')].map((r) => by[r.dataset.key]).filter(Boolean)); draw(); } });
    };
    draw();
    return list;
  };

  // ---- the page: for which devices, the layout, the top row
  const here = of.scope === 'device' && of.device;  // this device has a setup of its own
  const mine = o.forThis == null ? !!here : !!o.forThis;
  const forAll = h('input', { type: 'radio', name: 'layscope', checked: !mine }), forThis = h('input', { type: 'radio', name: 'layscope', checked: mine });
  const devName = h('input', { class: 't', maxlength: 40, value: o.devName || (here ? of.device.name : deviceGuess()), placeholder: 'Kitchen tablet', 'aria-label': 'A name for this device' });
  const devRow = h('div', { class: 'laydev', hidden: !mine }, fld('A name for this device', devName));
  const scopeNote = h('p', { class: 'muted small' });
  const scopeDraw = () => {
    devRow.hidden = !forThis.checked;
    scopeNote.textContent = forThis.checked ? 'What you save now is for this device alone; your other devices keep the setup they have.'
      : here ? 'Saving puts this on every device, and this device gives up the setup of its own.' : '';
    scopeNote.hidden = !scopeNote.textContent;
  };
  forAll.onchange = forThis.onchange = scopeDraw; scopeDraw();
  const others = (of.devices || []).filter((d) => !here || d.id !== of.device.id);
  const otherRows = h('div', { class: 'laydevs' }, others.map((d) => { const row = h('div', { class: 'layrow' }, icon('phone', 's'), h('span', { class: 'check' }, d.name),
    h('button', { class: 'lnk small', title: 'It goes back to the setup of your account', onclick: async () => { try { await api(`api/me/layout/devices/${encodeURIComponent(d.id)}`, { method: 'DELETE' }); row.remove(); toast(`${d.name} follows your account again`); } catch (e) { fail(e); } } }, 'Remove its own setup')); return row; }));
  const style = pick(Object.entries(STYLES), L.style || 'cards');
  // the person's own grid: how many blocks across at most, once it is laid out (till then the page makes it from the
  // apps and the cards as they are set here)
  const across = pick(GRID_COLS, L.grid && L.grid.cols !== 3 ? L.grid.cols : null);
  const gridRow = h('div', { class: 'cusgrid' }, L.grid ? h('div', { class: 'grid' }, fld('Blocks across, at most', across), h('div')) : null,
    h('p', { class: 'muted small' }, L.grid ? 'Your own grid is laid out with Arrange the page: drag a block, pull its corner to make it wider or taller, add one from the list. The apps and the cards chosen here count again in the other layouts.'
      : 'Your own grid starts as the page stands now. Arrange the page then moves every block where you want it, makes it wider or taller, and adds more: the same card twice, a room of the house, one folder of feeds.'));
  const styleDraw = () => { gridRow.hidden = style.value !== 'grid'; };
  style.onchange = styleDraw; styleDraw();
  // the pages: a name each, their order, and one more
  const pagesEl = h('div', { class: 'lay cuspages' });
  const pagesDraw = () => {
    const ps = full.pages, move = (i, by) => { const [p] = ps.splice(i, 1); ps.splice(i + by, 0, p); pagesDraw(); };
    const name = (now, set) => h('input', { class: 't', maxlength: 30, value: now, 'aria-label': 'Name', onchange: (e) => { set(e.target.value.replace(/\s+/g, ' ').trim()); } });
    const btn = (ic, tip, act, off) => h('button', { class: 'iconbtn', title: tip, 'aria-label': tip, disabled: off ? true : null, onclick: act }, icon(ic, 's'));
    pagesEl.replaceChildren(
      h('div', { class: 'layrow' }, name(full.name || 'Home', (v) => { full.name = v && v !== 'Home' ? v : null; }), h('span', { class: 'muted small cusfirst' }, 'The first: the page opens on it')),
      ...ps.map((p, i) => h('div', { class: 'layrow' }, name(p.name, (v) => { p.name = v || 'Page'; }),
        btn('up', 'Earlier', () => move(i, -1), i === 0), btn('down', 'Later', () => move(i, 1), i === ps.length - 1),
        h('button', { class: `iconbtn${p.when ? ' set' : ''}`, title: p.when ? `Its tab shows: ${whenText(p.when)}` : 'Show its tab only when…', 'aria-label': 'When its tab shows',
          onclick: async () => { const r = await whenDialog(`the tab of ${p.name}`, p.when, { content: false }); if (r) { if (r.when) p.when = r.when; else delete p.when; pagesDraw(); } } }, icon('schedule', 's')),
        btn('delete', 'Remove this page', async () => { if (await confirmDialog(`Remove ${p.name}`, 'The page goes with everything laid out on it, once you save. Nothing is lost in the apps themselves.', 'Remove', true)) { full.pages = ps.filter((x) => x !== p); pagesDraw(); } }))),
      ps.length < PAGES_MOST - 1 ? h('button', { class: 'lnk small', onclick: async () => { const n = await askName('A new page', '', 'It gets a tab under the top row and an address of its own, so a device can open on it.'); if (n) { full.pages.push({ id: newId(6), name: n, ...BLANK() }); pagesDraw(); } } }, 'Add a page') : '');
  };
  pagesDraw();
  const pageName = pagesOf(full).find((p) => p.id === pid).name;
  const wxNames = { metric: '°C, km/h', imperial: '°F, mph' };
  const units = pick([['', `As set for everyone${S.wxUnits ? ` (${wxNames[S.wxUnits].split(',')[0]})` : ''}`], ['metric', wxNames.metric], ['imperial', wxNames.imperial]], L.units);
  const engines = pick(Object.entries(ENGINES).map(([k, e]) => [k === 'duckduckgo' ? '' : k, e.name]), L.search);
  const pagePanel = [
    h('h3', null, 'This setup is for'),
    h('label', { class: 'check' }, forAll, 'Every device I sign in on'), h('label', { class: 'check' }, forThis, 'This device only'), devRow, scopeNote,
    others.length ? [h('h3', null, here ? 'Other devices with a setup of their own' : 'Devices with a setup of their own'), otherRows] : null,
    h('h3', null, 'Pages'), pagesEl,
    h('p', { class: 'muted small' }, 'Each page is laid out by itself and has a tab under the top row (a swipe on a phone). What is set below, and under Apps and Cards, is for the page you came from; the look and the photos are the same on all of them.'),
    h('h3', null, full.pages.length ? `The page ${pageName}` : 'The page'),
    h('div', { class: 'grid' }, fld('Layout', style), h('div')), gridRow,
    h('h3', null, 'The top row'),
    top.map((t) => tick(t, t.name)),
    h('h3', null, 'Search and weather'),
    h('div', { class: 'grid' }, fld('Web search', engines), fld('Weather in', units)),
    wxParts.map((t) => tick(t, t.name)),
    h('p', { class: 'muted small' }, 'Warnings come from the US National Weather Service, for places in the United States; the rest from AccuWeather with the forecast. A click on the weather shows them all.'),
    h('p', { class: 'muted small' }, `In the search box, a prefix picks a site: ${BANG_HELP}. “t …” adds a task to ioTask and “n …” a note to ioNote; a line that says when (“dinner fri 19:00”) adds an event.`),
  ];

  // ---- the cards: which, in what order; what the Today card holds; how the bookmarks look
  const days = pick(TODAY_DAYS, L.todayDays), bmLook = pick(BM_LOOKS, L.bookmarks);
  const cardsPanel = [
    h('h3', null, 'Cards under the apps'),
    L.grid && L.style === 'grid' ? h('p', { class: 'muted small' }, 'This page is your own grid: its cards are blocks, added, moved and taken off with Arrange the page. The list here counts in the other layouts.') : '', sortable(cards),
    h('p', { class: 'muted small' }, 'Birthdays and This week share a row when they follow each other. On a wide screen the bookmarks take a column of their own on the right when they come last.'),
    h('div', { class: 'grid' }, fld('Bookmarks as', bmLook), h('div')),
    parts.length ? [h('h3', null, 'The Today card'), h('p', { class: 'muted small' }, 'For the layout with one Today card: what it lists, and what stands beside it.'),
      parts.map((p) => tick(p, p.name)), h('div', { class: 'grid' }, fld('Its list goes as far as', days), h('div'))] : null,
  ];

  // ---- the look: the colour and the size of the type, shown on the page behind as they are picked
  let accent = L.accent || '';
  const text = pick(TEXTS, L.text, { onchange: () => preview() });
  const swatches = h('div', { class: 'swatches', role: 'radiogroup', 'aria-label': 'Colour' });
  const preview = () => {
    const d = document.documentElement.dataset;
    if (accent) d.accent = accent; else delete d.accent;
    if (text.value) d.text = text.value; else delete d.text;
    for (const b of swatches.children) b.setAttribute('aria-checked', String(b.dataset.key === accent));
  };
  swatches.append(...Object.entries(ACCENTS).map(([k, [name, color]]) => h('button', { class: 'swatch', role: 'radio', 'data-key': k, title: name, 'aria-label': name, style: { '--sw': color }, onclick: () => { accent = k; preview(); } }, icon('check', 's'))));
  preview();
  const lookPanel = [h('h3', null, 'Colour'), swatches, h('div', { class: 'grid' }, fld('Text size', text), h('div')),
    h('p', { class: 'muted small' }, 'The colour and the size count on the start page and its settings. Light or dark is the gear menu’s Appearance, and goes with your account to every app.')];

  // ---- the photos: the strip on the page, and the wall display
  const adminStrip = { rediscover: 'Rediscover', onthisday: 'On this day', off: 'Off' }[S.photoStrip] || 'Rediscover';
  const strip = pick([['', `Default (${adminStrip})`], ['rediscover', 'Rediscover: photos at random'], ['onthisday', 'On this day'], ['off', 'Off']], L.strip);
  const moves = pick(Object.entries(STRIP_MOVES), L.stripMove || STRIP_DEFAULT.move);
  const everies = pick(STRIP_EVERY.map((x) => [x, `Every ${everyText(x)}`]), L.stripEvery || STRIP_DEFAULT.every);
  const pix = has('iopix');
  const wallBg = pick(Object.keys(WALL_BGS).filter((k) => pix || k !== 'photos').map((k) => [k, WALL_BG_NAMES[k]]), L.wallBg || (pix ? 'photos' : 'sky'));
  // which photos: as the strip, or the person's favorites or one album in ioPix (the list comes from ioPix as they look)
  const wallPhotos = pick([['', 'As the photo strip'], ['rediscover', 'Rediscover: photos at random'], ['onthisday', 'On this day'], ['favorites', 'My favorites']], L.wallPhotos);
  if (pix) widget('iopix', { kind: 'albums' }).then((d) => {
    const list = (d && d.albums) || [];
    const kept = L.wallPhotos && L.wallPhotos.startsWith('album:') && !list.some((a) => `album:${a.id}` === L.wallPhotos);
    if (list.length || kept) wallPhotos.append(h('optgroup', { label: 'An album' }, list.map((a) => h('option', { value: `album:${a.id}`, selected: `album:${a.id}` === L.wallPhotos ? true : null }, `${a.name} (${a.n})`)),
      kept ? h('option', { value: L.wallPhotos, selected: true }, 'An album no longer there') : null));
  });
  const wallEvery = pick(WALL_EVERY.map((x) => [x, `Every ${everyText(x)}`]), L.wallEvery || WALL_DEFAULT_EVERY);
  const photosPanel = [
    pix ? [h('h3', null, 'The photo strip'), h('div', { class: 'grid' }, fld('Photo strip', strip), fld('It changes to', moves)), h('div', { class: 'grid' }, fld('How often', everies), h('div'))] : null,
    h('h3', null, 'The wall display'),
    h('div', { class: 'grid' }, fld('Background', wallBg), pix ? fld('Its photo changes', wallEvery) : h('div')),
    pix ? h('div', { class: 'grid' }, fld('Photos', wallPhotos), h('div')) : null,
  ];

  /** The setup as the dialog has it now: the person's own part, the pages, and in its place what the page shown holds
      (its grid, its rules and its badges stay as they are: those are set on the page itself, with Arrange). */
  const collect = () => {
    const out = { ...copy(full), strip: strip.value || null, search: engines.value || null,
      stripMove: moves.value === STRIP_DEFAULT.move ? null : moves.value, stripEvery: +everies.value === STRIP_DEFAULT.every ? null : +everies.value,
      wallBg: wallBg.value === (pix ? 'photos' : 'sky') ? null : wallBg.value, wallEvery: +wallEvery.value === WALL_DEFAULT_EVERY ? null : +wallEvery.value,
      wallPhotos: wallPhotos.value || null, weatherOff: wxParts.filter((t) => !t.on).map((t) => t.key), units: units.value || null, accent: accent || null, text: text.value || null };
    return putPage(out, pid, { ...L, hidden: [...tiles, ...cards, ...top].filter((t) => !t.on).map((t) => t.key), order: tiles.map((t) => t.key), cards: cards.map((c) => c.key),
      style: style.value === 'cards' ? null : style.value, grid: L.grid ? { ...L.grid, cols: across.value ? +across.value : null } : null,
      sizes: Object.fromEntries(tiles.filter((t) => t.size).map((t) => [t.key, t.size])),
      // a part the dialog does not list (its app is not here) stays as it was
      todayOff: [...parts.filter((p) => !p.on).map((p) => p.key), ...L.todayOff.filter((k) => !parts.some((p) => p.key === k))],
      todayDays: days.value === '' ? null : +days.value, bookmarks: bmLook.value || null });
  };

  // ---- copying: a ready-made page, a setup from elsewhere, the setup as text. Each opens the dialog again on what
  // was taken, to look over: nothing is kept until Save
  const again = (draft, note) => body.closest('.dialog-back').close({ draft, note });
  const starts = h('div', { class: 'pickrows' }, readyMade(tiles.filter((t) => t.on).map((t) => t.key)).map(([name, about, make]) => h('button', { class: 'pickrow', onclick: () => {
    again(putPage(collect(), pid, { ...BLANK(), ...make() }), `${full.pages.length ? `${pageName} is` : 'The page is'} now “${name}”. Nothing is kept until you press Save.`);
  } }, icon('apps', 's'), h('span', null, name), h('span', { class: 'muted small' }, about))));
  const from = h('select', { class: 't', disabled: true }, h('option', { value: '' }, 'Loading…'));
  const take = h('button', { class: 'pillbtn noic', disabled: true, onclick: async () => {
    const said = from.selectedOptions[0].textContent;
    try { again((await api(`api/me/layout/copy?source=${encodeURIComponent(from.value)}`)).layout, `Copied from ${said.replace(/^My /, 'my ').replace(/^The /, 'the ')}. Nothing is kept until you press Save.`); } catch (e) { fail(e); }
  } }, 'Copy it here');
  api('api/me/layout/sources').then((d) => {
    const dev = deviceId(), opts = [
      d.account && here ? ['account', 'My account’s setup (my other devices)'] : null,
      ...d.devices.filter((x) => x.id !== dev).map((x) => [`device:${x.id}`, `My device ${x.name}`]),
      d.family ? ['family', 'The family’s starting point'] : null,
      ...d.people.map((x) => [`person:${x.id}`, `${x.displayName || x.name}’s setup`])].filter(Boolean);
    from.replaceChildren(...(opts.length ? opts.map(([v, t]) => h('option', { value: v }, t)) : [h('option', { value: '' }, 'There is no other setup to copy yet')]));
    from.disabled = take.disabled = !opts.length;
  }).catch(() => { from.replaceChildren(h('option', { value: '' }, 'The list could not be read')); });
  const asText = h('textarea', { class: 't custext', rows: 12, spellcheck: false, 'aria-label': 'The setup as text' });
  let typed = false;
  asText.oninput = () => { typed = true; };
  const readText = async () => {
    let v;
    try { v = JSON.parse(asText.value); } catch (e) { throw new Error(`This does not read as a setup: ${e.message}`); }
    return (await api('api/layout/check', { method: 'POST', json: v })).layout;
  };
  const copyPanel = [
    h('h3', null, 'A ready-made page'), h('p', { class: 'muted small' }, `A starting point for ${full.pages.length ? `the page ${pageName}` : 'the page'}, made of the apps ticked under Apps. It replaces how the page is laid out, not your colour or photos.`), starts,
    h('h3', null, 'Copy a setup'), h('p', { class: 'muted small' }, 'Another device of yours, or someone else’s whole setup with all its pages, to make your own from. Theirs stays as it is.'),
    h('div', { class: 'cusbtns cusfrom' }, from, take),
    h('h3', null, 'The setup as text'), h('p', { class: 'muted small' }, 'Everything set here, to keep somewhere, to send to someone, or to change by hand and read back.'), asText,
    h('div', { class: 'cusbtns' },
      h('button', { class: 'pillbtn noic', onclick: async () => { try { await navigator.clipboard.writeText(asText.value); toast('Copied'); } catch { asText.select(); toast('Select it and copy it by hand: this browser keeps the clipboard to itself'); } } }, 'Copy'),
      h('button', { class: 'pillbtn noic', onclick: async () => { try { asText.value = JSON.stringify(lean(await readText()), null, 2); toast('It reads fine'); } catch (e) { fail(e); } } }, 'Check it'),
      h('button', { class: 'pillbtn noic', onclick: async () => { try { again(await readText(), 'Read from the text. Nothing is kept until you press Save.'); } catch (e) { fail(e); } } }, 'Use this text')),
  ];

  const panels = {
    page: ['Page', pagePanel],
    apps: ['Apps', [h('p', { class: 'muted small' }, 'Untick an app you do not need here, and drag them into your order. The size counts in the layout with a card for each app: by itself, an app is a card on a day it has something to show and a low tile with one line when it has not.'),
      L.grid && L.style === 'grid' ? h('p', { class: 'muted small' }, 'In your own grid, an app unticked here is off the page; where each one stands is set with Arrange the page.') : '', sortable(tiles)]],
    cards: ['Cards', cardsPanel],
    look: ['Look', lookPanel],
    photos: ['Photos', photosPanel],
    copy: ['Copy', copyPanel],
    ...(S.user.role === 'admin' ? { family: ['Family', [familyPanel(collect)]] } : {}),
  };
  const tabs = h('div', { class: 'tabs custabs', role: 'tablist' }), views = h('div', { class: 'cusviews' });
  const show = (k) => {
    for (const b of tabs.children) { const on = b.dataset.tab === k; b.classList.toggle('on', on); b.setAttribute('aria-selected', String(on)); }
    for (const v of views.children) v.hidden = v.dataset.tab !== k;
    if (k === 'copy' && !typed) asText.value = JSON.stringify(lean(collect()), null, 2);  // the dialog as it stands, on all its tabs
  };
  for (const [k, [name, kids]] of Object.entries(panels)) {
    tabs.append(h('button', { role: 'tab', 'data-tab': k, onclick: () => show(k) }, name));
    views.append(h('div', { class: 'cusview', role: 'tabpanel', 'data-tab': k }, kids));
  }
  show(panels[tab] ? tab : 'page');
  const body = h('div', { class: 'customize' }, o.note ? h('p', { class: 'cusnote', role: 'status' }, icon('check', 's'), o.note) : '', tabs, views,
    o.draft ? '' : h('button', { class: 'lnk small cusarrange', onclick: () => body.closest('.dialog-back').close('arrange') }, icon('move', 's'), 'Or arrange the page where it stands: drag the tiles and cards, hide them with a tap'));
  const back = here ? 'Back to my account’s setup' : of.family ? 'Back to the family’s setup' : 'Back to the default';
  const asked = dialog('Customize the page', body, [{ label: back, value: 'reset' }, { label: 'Cancel', value: null }, { label: 'Save', value: 'save', primary: true }]);
  body.closest('.dialog').classList.add('wide');
  const v = await asked;
  if (v !== 'save') applyLook(S.layout);  // the colour and the type as they were
  if (v === 'arrange') { arrangeStart(); return; }
  if (v && v.draft) { customize('page', { draft: v.draft, note: v.note, forThis: forThis.checked, devName: devName.value }); return; }
  if (!v) return;
  try {
    if (v === 'reset') {
      if (here) { await api(`api/me/layout/devices/${encodeURIComponent(of.device.id)}`, { method: 'DELETE' }); toast('This device follows your account again'); }
      else { await saveLayout({}, null); toast(back.replace('my', 'your')); }
    } else if (forThis.checked) {
      let id = deviceId();
      if (!id) { try { id = newDeviceId(); } catch { toast('This browser keeps nothing between visits (a private window?), so it cannot have a setup of its own'); return; } }
      await saveLayout(collect(), { id, name: devName.value.trim() || deviceGuess() });
      toast('Saved for this device');
    } else {
      await saveLayout(collect(), null);
      if (here) await api(`api/me/layout/devices/${encodeURIComponent(of.device.id)}`, { method: 'DELETE' });
      toast('Saved');
    }
    if (route().view === 'home') await onRoute(); else applyLook((await loadApps()).layout);
  } catch (e) { fail(e); }
}

/** A setup without what is left as it comes (nothing set, an empty list): shorter to read as text. Read back, what is
    missing is as it comes again. */
function lean(full) {
  const set = (v) => v != null && !(Array.isArray(v) && !v.length) && !(typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length);
  const some = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => set(v)));
  return some({ ...full, pages: (full.pages || []).map(some) });
}

/** The ready-made pages: [its name, a few words on it, () => what the page holds (static/js/pages.js PAGE)], each made
    of the apps the page has (`keys`). */
function readyMade(keys) {
  const has = (k) => keys.includes(k), id = () => newId(6);
  const blk = (ok, kind, more = {}) => (ok ? { id: id(), kind, ...more } : null);
  const badges = (ks) => ks.filter((k) => has(k) && LINES[k]).map((k) => ({ id: id(), app: k }));
  const sections = (list) => list.map(([title, blocks]) => ({ id: id(), title, blocks: blocks.filter(Boolean) })).filter((x) => x.blocks.length);
  const day = ['iocalendar', 'iotask', 'iocontact', 'iomoney', 'iohealth', 'iopix'].some(has);
  return [
    ['The usual page', 'A card for each app with something to show, the cards under them', () => ({})],
    ['The day in one card', 'The apps in a row to open them, one Today card with the coming days', () => ({ style: 'today' })],
    ['A family board', 'Your own grid, in sections: today, this week, the house, photos and links', () => ({ style: 'grid', badges: badges(['iocalendar', 'iotask', 'iomoney']),
      grid: { cols: 3, sections: sections([
        [null, [blk(true, 'apps', { w: 4 }), blk(day, 'today', { w: 4 })]],
        ['This week', [blk(has('iocalendar'), 'week', { w: 2, h: 1 }), blk(has('iocontact'), 'birthdays', { h: 1 }), blk(has('iotask'), 'app', { app: 'iotask' }), blk(has('iomoney'), 'app', { app: 'iomoney' }), blk(has('iohealth'), 'app', { app: 'iohealth' })]],
        ['At home', [blk(S.ha !== false, 'home', { w: 4 })]],
        ['Photos and links', [blk(has('iopix'), 'strip', { w: 4 }), blk(true, 'news', { w: 2 }), blk(true, 'bookmarks', { w: 4 })]]]) } })],
    ['At a glance', 'For a phone: a few badges, the apps in a row, today and tomorrow, bookmarks as icons', () => ({ style: 'today', todayDays: 1, bookmarks: 'icons', badges: badges(['iocalendar', 'iotask', 'iomoney', 'iodocs']) })],
  ];
}

/** Customize › Family, for an admin: what is set in the dialog (collect()) as the setup everyone starts from, or as
    one person's. Whoever has a setup of their own keeps it, unless it is given to them. */
function familyPanel(collect) {
  const el = h('div', { class: 'cusfamily' }, h('p', { class: 'muted small' }, 'Loading…'));
  const draw = async () => {
    let d;
    try { d = await api('api/layout/family'); } catch (e) { el.replaceChildren(h('p', { class: 'muted small' }, e.message)); return; }
    const others = d.people.filter((p) => p.id !== S.user.id), name = (p) => p.displayName || p.name;
    const own = others.filter((p) => p.own || p.devices), none = others.filter((p) => !p.own && !p.devices);
    const list = (ps) => ps.map(name).join(', ');
    const run = async (what, said) => { try { await what(); toast(said); draw(); } catch (e) { fail(e); } };
    // a second tap confirms what cannot be taken back
    const sure = (btn, text, act) => { if (btn.dataset.sure) { act(); return; } btn.dataset.sure = '1'; btn.textContent = text; btn.classList.add('danger'); };
    const who = h('select', { class: 't' }, others.map((p) => h('option', { value: p.id }, name(p))));
    const give = h('button', { class: 'pillbtn noic', onclick: () => { const p = others.find((x) => String(x.id) === who.value);
      sure(give, `Replace ${name(p)}’s setup, on all their devices?`, () => run(() => api(`api/layout/people/${p.id}`, { method: 'PUT', json: collect() }), `${name(p)} has this setup now`)); } }, 'Give it to them');
    who.onchange = () => { delete give.dataset.sure; give.textContent = 'Give it to them'; give.classList.remove('danger'); };
    el.replaceChildren(h('div', null,
      h('h3', null, 'Everyone’s starting point'),
      h('p', { class: 'muted small' }, d.layout ? `Set: whoever has no setup of their own gets it${none.length ? ` (now: ${list(none)})` : ''}.` : 'None yet: whoever has no setup of their own gets the page as it comes.',
        own.length ? ` ${list(own)} ${own.length === 1 ? 'has' : 'have'} a setup of their own and ${own.length === 1 ? 'keeps' : 'keep'} it.` : ''),
      h('div', { class: 'cusbtns' },
        h('button', { class: 'pillbtn noic', onclick: () => run(() => api('api/layout/family', { method: 'PUT', json: collect() }), 'This is everyone’s starting point now') }, d.layout ? 'Replace it with what is set here' : 'Use what is set here'),
        d.layout ? h('button', { class: 'pillbtn noic', onclick: () => run(() => api('api/layout/family', { method: 'PUT', json: {} }), 'No starting point any more') }, 'Take it away') : null),
      others.length ? [h('h3', null, 'For one person'),
        h('p', { class: 'muted small' }, 'What is set here becomes their setup on every device, a child’s simpler page for instance. They can change it afterwards.'),
        h('div', { class: 'cusbtns' }, who, give)] : null,
      h('p', { class: 'muted small' }, '“What is set here” is this dialog as it stands, on all its tabs, saved or not.')));
  };
  draw();
  return el;
}

// ------------------------------------------------------------------ arranging the page where it stands
/* "Arrange the page" (the gear menu, or Customize): the start page itself, with a handle and an eye on every tile and
   card. Dragging one by its handle (or anywhere on it with a mouse; the arrow keys on the handle) moves it among the
   others, the eye takes it off the page, a tile's size button turns it from a card into a low tile and back, and the
   Today card has a switch for each of its parts. What is off the page waits in the bar on top to be put back.
   Nothing is kept until Done: S.arrange.L is the copy being worked on (showHome draws from it), saved where the page's
   setup came from (this device's own, or the account's). */
export function arrangeStart() {
  S.arrangeNext = true;
  if (route().view === 'home') onRoute(); else location.hash = '#/';
}
async function arrangeEnd(save) {
  const A = S.arrange;
  if (!A) return;
  putPage(A.full, A.pid, A.L);
  const changed = JSON.stringify(A.full) !== A.was;
  if (save && changed) {
    try { await saveLayout(A.full); toast('Saved'); } catch (e) { fail(e); return; }
  }
  S.arrange = null;
  // the page that was being arranged stays the one shown (unless it was a new one that is not kept)
  if (save && (route().page || '') !== A.pid) location.hash = pageHref(A.pid); else await onRoute();
}
/** The page again from the copy being arranged, where the reader was: built off the page, then put in its place. */
export async function arrangeRedraw() {
  const A = S.arrange;
  if (A) putPage(A.full, A.pid, A.L);  // what was changed on the page shown goes into the whole setup
  const main = $('#main'), old = main.firstElementChild, y = main.scrollTop;
  const page = h('div', { class: 'page' });
  page.style.minHeight = `${old ? old.offsetHeight : 0}px`;  // the cards fill in a moment later: the page keeps its height meanwhile
  try { await showHome(page); } catch (e) { fail(e); return; }
  main.replaceChildren(page);
  main.scrollTop = y;
  setTimeout(() => { page.style.minHeight = ''; }, 1200);
}
/** While arranging: another page of the setup (commit false: what the page shown holds is in the setup already, as
    after two pages traded places). */
export function arrangeGo(id, commit = true) {
  const A = S.arrange;
  if (!A) return null;
  if (commit) putPage(A.full, A.pid, A.L);
  A.pid = pageId(A.full, id); A.L = pageView(A.full, A.pid);
  return arrangeRedraw();
}
/** A tile, a card or a part of the top row, with its handle, its size and its eye while the page is arranged. */
export function arrMark(el, kind, key, name) {
  const A = S.arrange;
  if (!A || !el) return el;
  el.classList.add('arr'); el.dataset.arr = kind; el.dataset.key = key;
  const press = (act) => (e) => { e.preventDefault(); e.stopPropagation(); act(); };
  const ctl = h('span', { class: 'arrctl' });
  if (kind !== 'top') ctl.append(h('button', { class: 'arrbtn arrgrip', title: `Drag to move ${name} (or the arrow keys)`, 'aria-label': `Move ${name}`, onclick: press(() => {}) }, icon('grip', 's')));
  if (kind === 'tile' && A.L.style !== 'today' && WIDGETS[key]) {
    const now = sizeOf(key, A.L), next = { '': 'card', card: 'tile', tile: '' }[now];
    ctl.append(h('button', { class: 'arrbtn arrsize', title: `Size: ${SIZES.find(([v]) => v === now)[1].toLowerCase()}. A tap: ${SIZES.find(([v]) => v === next)[1].toLowerCase()}`,
      onclick: press(() => { const sizes = { ...A.L.sizes }; if (next) sizes[key] = next; else delete sizes[key]; A.L.sizes = sizes; arrangeRedraw(); }) }, { '': 'Auto', card: 'Card', tile: 'Low' }[now]));
  }
  // when it shows (static/js/when.js): on which screens, at which hours, only with something to say, by Home Assistant
  const rule = (A.L.whens || {})[key];
  ctl.append(h('button', { class: `arrbtn${rule ? ' set' : ''}`, title: rule ? `${name} shows: ${whenText(rule)}` : `Show ${name} only when…`, 'aria-label': `When ${name} shows`, onclick: press(async () => {
    const r = await whenDialog(name, rule, { content: kind !== 'top' });
    if (!r) return;
    const whens = { ...(A.L.whens || {}) };
    if (r.when) whens[key] = r.when; else delete whens[key];
    A.L.whens = whens; arrangeRedraw();
  }) }, icon('schedule', 's')));
  ctl.append(h('button', { class: 'arrbtn', title: `Take ${name} off the page`, 'aria-label': `Hide ${name}`, onclick: press(() => { A.L.hidden = [...new Set([...A.L.hidden, key])]; arrangeRedraw(); }) }, icon('eyeoff', 's')));
  el.append(ctl);
  // a card draws itself anew when its app answers: the buttons go back on top of what it drew
  // (and the handle keeps the keyboard, when it was moved with the arrow keys a moment ago)
  const held = () => A.held && A.held.kind === kind && A.held.key === key && Date.now() - A.held.at < 4000;
  new MutationObserver(() => { if (ctl.parentNode === el) return; el.append(ctl); if (held()) ctl.querySelector('.arrgrip').focus(); }).observe(el, { childList: true });
  return el;
}
/** The bar on top of a page being arranged: what to do, the layout, what is off the page, Cancel and Done. */
export function arrangeBar() {
  const A = S.arrange, L = A.L, of = S.layoutOf || {}, items = A.got.items, own = L.style === 'grid';
  const where = of.scope === 'device' && of.device ? `for this device only (${of.device.name})` : 'for every device you sign in on';
  const styles = h('div', { class: 'seg' }, Object.entries({ cards: 'Cards', today: 'Today', grid: 'My grid' }).map(([k, t]) => { const on = (L.style || 'cards') === k;
    return h('button', { class: on ? 'on' : '', 'aria-pressed': String(on), title: STYLES[k], onclick: () => {
      if (on) return;
      if (k === 'grid' && !L.grid) L.grid = gridFrom(L, A.got.photoStrip);  // the page as it stands, block for block
      L.style = k === 'cards' ? null : k; arrangeRedraw();
    } }, t); }));
  // the person's own grid: how many blocks across at most, and the way back to the page as it lays itself out
  const across = own ? h('label', { class: 'arracross muted small' }, 'Across, at most', pick(GRID_COLS, L.grid && L.grid.cols !== 3 ? L.grid.cols : null, { class: 't arrdays', onchange: (e) => { L.grid.cols = e.target.value ? +e.target.value : null; arrangeRedraw(); } })) : null;
  const over = own ? h('button', { class: 'lnk small', title: 'The blocks again as the page lays itself out, from the apps and the cards that are on', onclick: async () => {
    if (!await confirmDialog('Start the grid over', 'Every block goes back to where the page puts it by itself, and the sections go. Nothing is kept until Done.', 'Start over', true)) return;
    L.grid = gridFrom({ ...L, style: null }, A.got.photoStrip); arrangeRedraw();
  } }, 'Start over') : null;
  // what is off the page: a tap puts it back (in the person's own grid a card is a block: the Add list has them)
  const has = (k) => items.some((a) => a.key === k && !a.adminTool);
  const there = { home: true, birthdays: has('iocontact'), week: has('iocalendar'), strip: has('iopix'), news: true, bookmarks: true };
  const back = (key) => () => { L.hidden = L.hidden.filter((k) => k !== key); arrangeRedraw(); };
  const chip = (key, kids, name) => h('button', { class: 'arrchip', title: `Put ${name} back on the page`, onclick: back(key) }, kids, icon('add', 's'));
  const off = [...items.filter((a) => !a.adminTool && L.hidden.includes(a.key)).map((a) => chip(a.key, [h('img', { src: a.icon, alt: '' }), a.name], a.name)),
    ...(own ? [] : CARDS.filter((k) => L.hidden.includes(k) && there[k]).map((k) => chip(k, CARD_NAMES[k], CARD_NAMES[k]))),
    ...Object.keys(TOP_PARTS).filter((k) => L.hidden.includes(k)).map((k) => chip(k, TOP_PARTS[k], TOP_PARTS[k]))];
  const hint = own ? 'Drag a block by its handle, pull its corner to make it wider or taller. Its cog sets what it shows, and when.'
    : 'Drag a tile or a card by its handle to move it. The clock sets when it shows, the eye takes it off the page.';
  // the bar stays on top while the page scrolls under it; the layout and what is off the page scroll with the page
  return h('div', { class: 'arrtop' },
    h('div', { class: 'arrbar', role: 'region', 'aria-label': 'Arranging the page' },
      h('div', { class: 'arrtitle' }, h('b', null, 'Arranging the page'), h('span', { class: 'muted small' }, where)),
      h('div', { class: 'arrbtns' }, h('button', { class: 'pillbtn noic', onclick: () => arrangeEnd(false) }, 'Cancel'), h('button', { class: 'pillbtn noic primary', onclick: () => arrangeEnd(true) }, 'Done'))),
    h('div', { class: 'arrmore' }, [styles, across, over, h('span', { class: 'muted small arrhint' }, hint)].filter(Boolean)),
    off.length ? h('div', { class: 'arrtray' }, h('span', { class: 'muted small' }, 'Off the page:'), off) : '');
}
/** While arranging the Today layout: a switch for each part of the Today card, and how far its list goes. */
export function arrangeToday(el) {
  const L = S.arrange.L, has = (k) => S.apps.some((a) => a.key === k);
  const chips = Object.entries(TODAY_PARTS).filter(([, [, , app]]) => has(app)).map(([k, [name]]) => { const on = !L.todayOff.includes(k);
    return h('button', { class: `arrchip${on ? ' on' : ''}`, 'aria-pressed': String(on), title: on ? `Leave ${name.toLowerCase()} out` : `Show ${name.toLowerCase()}`,
      onclick: () => { L.todayOff = on ? [...L.todayOff, k] : L.todayOff.filter((x) => x !== k); drawGlance(el); } }, icon(on ? 'check' : 'add', 's'), name); });
  const days = pick(TODAY_DAYS, L.todayDays, { class: 't arrdays', 'aria-label': 'How far the list goes', onchange: (e) => { L.todayDays = e.target.value === '' ? null : +e.target.value; drawGlance(el); } });
  return h('div', { class: 'arrparts' }, h('span', { class: 'muted small' }, 'Today shows'), chips, days);
}
/** Wires a page being arranged: nothing on it opens, and every tile and card can be dragged among its kind. */
export function arrangeWire(page) {
  // (but for what arranging itself puts there: the handles, the bar, the tabs of the pages, the badges, a section's bar)
  page.addEventListener('click', (e) => { if (!e.target.closest('.arrctl, .arrtop, .arrparts, .arrok')) { e.preventDefault(); e.stopPropagation(); } }, true);
  page.addEventListener('dragstart', (e) => e.preventDefault());  // no dragging of a link or a picture as the browser does
  for (const el of page.querySelectorAll('.arr[data-arr="tile"], .arr[data-arr="card"]')) arrangeDrag(page, el);
}
/** Puts `key` before or after `target` among the tiles (or the cards) of the copy being arranged. */
function arrangeMove(kind, key, target, after) {
  const L = S.arrange.L;
  const keys = (kind === 'tile' ? S.apps.map((a) => a.key) : cardOrder(L)).filter((k) => k !== key);
  const i = keys.indexOf(target);
  if (i < 0) return false;
  keys.splice(i + (after ? 1 : 0), 0, key);
  if (kind === 'tile') L.order = [...keys, ...L.order.filter((k) => !keys.includes(k))];  // the hidden ones keep their order, after
  else L.cards = keys;
  return true;
}
/** Makes a marked thing (arrMark; a block of the person's own grid) one to drag among its kind, by its handle or, with
    a mouse, anywhere on it, and to move with the arrow keys on its handle. o.move(key, target, after): puts it before
    or after the one it was dropped by, true when that changed something; o.next(key, dir): for the arrow keys, where
    it goes one place earlier (-1) or later, [target, after] or null. Without them: a tile among the tiles, a card
    among the cards. */
export function arrangeDrag(page, el, o = {}) {
  const kind = el.dataset.arr, key = el.dataset.key, main = $('#main');
  const moveTo = o.move || ((k, target, after) => arrangeMove(kind, k, target, after));
  const next = o.next || ((k, dir) => {
    const shown = (kind === 'tile' ? S.apps.map((a) => a.key) : cardOrder(S.arrange.L)).filter((x) => page.querySelector(`.arr[data-arr="${kind}"][data-key="${x}"]`));
    const to = shown[shown.indexOf(k) + dir];
    return to ? [to, dir > 0] : null;
  });
  const others = () => [...page.querySelectorAll(`.arr[data-arr="${kind}"]`)].filter((x) => x !== el && x.offsetParent !== null);
  const refocus = () => { const g = $('#main').querySelector(`.arr[data-arr="${kind}"][data-key="${key}"] .arrgrip`); if (g) g.focus(); };
  const grip = el.querySelector(':scope > .arrctl .arrgrip');
  // the arrow keys on the handle: one place earlier or later, among what is on the page
  grip.addEventListener('keydown', (e) => {
    const dir = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key];
    if (!dir) return;
    e.preventDefault();
    const to = next(key, dir);
    if (to && moveTo(key, to[0], to[1])) { S.arrange.held = { kind, key, at: Date.now() }; arrangeRedraw().then(refocus); }
  });
  el.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || (e.target.closest('.arrbtn') && !e.target.closest('.arrgrip'))) return;
    if (e.pointerType !== 'mouse' && !e.target.closest('.arrgrip')) return;  // a finger on the tile scrolls the page: its handle drags
    e.preventDefault();
    const x0 = e.clientX, y0 = e.clientY, top0 = main.scrollTop, home = el.getBoundingClientRect();
    let x = x0, y = y0, lifted = false, target = null, after = false;
    const mark = h('div', { class: 'arrmark', hidden: true });
    const place = () => {
      el.style.transform = `translate(${x - x0}px, ${y - y0 + main.scrollTop - top0}px)`;
      // the tile or card nearest the pointer, and the side of it the pointer is on: left or right of it when it stands
      // in a row with others, above or under it when they are one under the other
      let best = null, far = Infinity;
      const all = others();
      for (const o of all) {
        const r = o.getBoundingClientRect();
        const d = Math.hypot(x < r.left ? r.left - x : x > r.right ? x - r.right : 0, y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0);
        if (d < far) { far = d; best = o; }
      }
      target = best;
      if (!best) { mark.hidden = true; return; }
      const r = best.getBoundingClientRect(), shift = main.scrollTop - top0;
      const beside = (q) => Math.abs(q.top - r.top) < Math.min(q.height, r.height) / 2 && (q.right <= r.left + 1 || q.left >= r.right - 1);
      const row = all.some((o) => o !== best && beside(o.getBoundingClientRect())) || beside({ top: home.top - shift, height: home.height, left: home.left, right: home.right });
      after = row ? x > r.left + r.width / 2 : y > r.top + r.height / 2;
      mark.hidden = false;
      Object.assign(mark.style, row ? { left: `${(after ? r.right + 6 : r.left - 10)}px`, top: `${r.top}px`, width: '4px', height: `${r.height}px` }
        : { left: `${r.left}px`, top: `${(after ? r.bottom + 6 : r.top - 10)}px`, width: `${r.width}px`, height: '4px' });
    };
    let scroll = 0;
    const tick = setInterval(() => { if (lifted && scroll) { main.scrollTop += scroll; place(); } }, 16);
    const move = (ev) => {
      if (ev.pointerId !== e.pointerId) return;
      x = ev.clientX; y = ev.clientY;
      if (!lifted) {
        if (Math.hypot(x - x0, y - y0) < 5) return;
        lifted = true; el.classList.add('lifted'); document.body.append(mark);
      }
      const box = main.getBoundingClientRect();
      scroll = y < box.top + 70 ? -14 : y > box.bottom - 70 ? 14 : 0;
      place();
    };
    const still = (ev) => { if (lifted) ev.preventDefault(); };
    const end = (ev) => {
      if (ev.pointerId !== e.pointerId) return;
      clearInterval(tick);
      removeEventListener('pointermove', move); removeEventListener('pointerup', end); removeEventListener('pointercancel', end); removeEventListener('touchmove', still);
      mark.remove(); el.classList.remove('lifted'); el.style.transform = '';
      if (lifted && ev.type === 'pointerup' && target && moveTo(key, target.dataset.key, after)) arrangeRedraw();
    };
    addEventListener('pointermove', move); addEventListener('pointerup', end); addEventListener('pointercancel', end);
    addEventListener('touchmove', still, { passive: false });  // no page scroll under the finger while it drags (iOS)
  });
}

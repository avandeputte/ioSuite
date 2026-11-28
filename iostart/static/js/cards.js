/* The cards of the start page beside the apps' tiles: the weather, the bookmarks, the coming days and birthdays, the
   strip of photos. */
import { fill, icon } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, bmIcon, bmIconsLater, contactFace, degF, fmtTemp, itemImage, quiet, S, wxIcon } from './core.js';
import { openAll } from './bookmarks.js';
import { drawBookmarkStatus } from './home.js';
import { evRow, evTime, inDays, pixPhotoUrl, widget } from './tiles.js';

// ------------------------------------------------------------------ the weather
export async function drawWeather(el, again = false) {
  let w;
  try { w = await api('api/weather'); } catch (e) { if (!again) el.replaceChildren(h('div', { class: 'muted small' }, e.message)); return; }
  if (!el.isConnected) return;
  if (!w.enabled) { fill(el, S.user.role === 'admin' ? h('a', { class: 'lnk small', href: '#/settings/weather' }, 'Add the weather') : null); return; }
  if (!w.current) { el.replaceChildren(h('div', { class: 'wxerr' }, wxIcon(7, 'big'), h('div', null, h('div', null, 'No weather right now'), h('div', { class: 'muted small' }, w.error || '')))); return; }
  S.wxUnits = w.units;  // what the weather is set up with: Customize names it
  const c = w.current, imp = wxImperial(w), u = imp ? 'imperial' : 'metric';
  const day = (d) => new Date(`${d.date}T12:00:00`).toLocaleDateString([], { weekday: 'short' });
  const t = (v) => fmtTemp(imp ? degF(v) : v);  // the forecasts come in °C
  const rain = rainNote(w);
  const hours = nextHours(w);
  const extra = wxExtras(w);
  let pop = null;
  const closePop = () => { if (pop) { pop.remove(); pop = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (pop && !pop.contains(e.target) && !now.contains(e.target) && !(warn && warn.contains(e.target))) closePop(); };
  const openPop = () => {
    if (pop) return closePop();
    pop = h('div', { class: 'wxpop' },
      extra.warnings.length ? h('div', { class: 'wxsect' }, extra.warnings.map(warnBlock), extra.warnLink ? h('a', { class: 'lnk small', href: extra.warnLink, target: '_blank', rel: 'noreferrer' }, 'At the National Weather Service') : null) : null,
      h('div', { class: 'wghead' }, h('span', null, 'Next hours'), w.location ? h('span', { class: 'muted' }, w.location) : null),
      hours.length ? hourRow(w, hours) : h('div', { class: 'muted small' }, 'No hourly forecast from AccuWeather'),
      extra.sun ? h('div', { class: 'wxsect' }, h('div', { class: 'wghead' }, h('span', null, 'Sun')), h('div', { class: 'wxsun small' },
        h('span', null, `Sunrise ${clock(extra.sun.rise)}`), h('span', null, `Sunset ${clock(extra.sun.set)}`),
        h('span', { class: 'muted' }, `${hm(extra.sun.length)} of daylight${extra.sun.change ? `, ${extra.sun.change}` : ''}`))) : null,
      extra.air || extra.pollen.length ? h('div', { class: 'wxsect' }, h('div', { class: 'wghead' }, h('span', null, [extra.air ? 'Air quality' : null, extra.pollen.length ? 'pollen' : null].filter(Boolean).join(' and ').replace(/^p/, 'P')), h('span', { class: 'muted small' }, 'today')),
        h('div', { class: 'wxair' }, extra.air ? levelPill('Air', extra.air, extra.air.value != null ? `Air quality index ${extra.air.value}${extra.air.kind ? ` (${extra.air.kind})` : ''}` : '') : null,
          extra.pollen.map((p) => levelPill(p.name, p, p.value != null ? `${p.name} pollen: ${p.value} grains per cubic metre` : '')))) : null,
      c.link ? h('a', { class: 'lnk small', href: c.link, target: '_blank', rel: 'noreferrer' }, 'More at AccuWeather') : null);
    el.append(pop);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  // under the conditions, one short line: the next sunrise or sunset, and the pollen or the air when it is bad today
  const note = [extra.sun && extra.sun.next, ...extra.bad].filter(Boolean).join(' · ');
  const now = h('button', { class: 'wxnow', 'aria-expanded': 'false',
    title: [w.location, c.feels[u] != null ? `feels ${fmtTemp(c.feels[u])}` : null, c.humidity != null ? `${c.humidity}% humidity` : null,
      c.wind[u] != null ? `wind ${Math.round(c.wind[u])} ${imp ? 'mph' : 'km/h'}` : null].filter(Boolean).join(' · '),
    onclick: openPop },
    wxIcon(c.icon, 'big'),
    h('div', null, h('div', { class: 'wxtemp' }, fmtTemp(c.temp[u])), h('div', { class: 'wxtext small' }, c.text),
      rain ? h('div', { class: 'wxrain small' }, rain) : null, note ? h('div', { class: 'wxnote small' }, note) : null));
  // a warning in force: a line of its own under the weather, coloured as serious as it is; a click shows what it says
  const w0 = extra.warnings[0];
  const warn = w0 ? h('button', { class: `wxwarn ${sevClass(w0.severity)}`, title: w0.headline || w0.event, onclick: openPop },
    icon('warn', 's'), h('span', null, w0.event), w0.ends ? h('span', { class: 'wxwhen' }, `until ${when(w0.ends)}`) : null,
    extra.warnings.length > 1 ? h('span', { class: 'wxmore' }, `+${extra.warnings.length - 1}`) : null) : null;
  fill(el, now,
    w.forecast && w.forecast.days && w.forecast.days.length ? h('div', { class: 'wxdays' }, w.forecast.days.map((d) =>
      h('div', { class: 'wxday', title: `${d.text || ''}${d.rain != null ? ` · ${d.rain}% chance of rain` : ''}` }, h('span', { class: 'muted small' }, day(d)), wxIcon(d.icon), h('span', { class: 'small wxhi' }, t(d.max)), h('span', { class: 'muted small' }, t(d.min))))) : null,
    w.stale ? h('span', { class: 'muted small', title: w.error || 'AccuWeather did not answer' }, 'older') : h('span'), warn);
}
/** The weather's extras the person keeps (Customize, layout weatherOff), worked out for today: {warnings, warnLink,
    sun: {rise, set, length (minutes), change, next}, air, pollen, bad: short notes for the line under the conditions}. */
export function wxExtras(w) {
  const off = (S.layout && S.layout.weatherOff) || [], on = (k) => !off.includes(k);
  const days = (w.forecast && w.forecast.days) || [];
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const i = Math.max(0, days.findIndex((d) => d.date === iso(new Date())));
  const today = days[i] || {}, tomorrow = days[i + 1] || {};
  const out = { warnings: [], warnLink: '', sun: null, air: null, pollen: [], bad: [] };
  if (on('warnings') && w.warnings) { out.warnings = w.warnings.items || []; out.warnLink = w.warnings.link || ''; }
  if (on('sun') && today.sunrise && today.sunset) {
    const len = (d) => (d.sunrise && d.sunset ? Math.round((new Date(d.sunset) - new Date(d.sunrise)) / 60000) : null);
    const length = len(today), next = len(tomorrow), diff = next == null ? 0 : next - length;
    const t = Date.now();
    out.sun = { rise: today.sunrise, set: today.sunset, length,
      change: diff ? `${Math.abs(diff)} min ${diff > 0 ? 'more' : 'less'} tomorrow` : next != null ? 'the same tomorrow' : '',
      next: t < new Date(today.sunrise) ? `Sunrise ${clock(today.sunrise)}` : t < new Date(today.sunset) ? `Sunset ${clock(today.sunset)}`
        : tomorrow.sunrise ? `Sunrise ${clock(tomorrow.sunrise)}` : '' };
  }
  if (on('air') && today.air && today.air.category) {
    out.air = today.air;
    if (today.air.level >= 3) out.bad.push(`Air ${today.air.category.toLowerCase()}`);
  }
  if (on('pollen')) {
    out.pollen = (today.pollen || []).filter((p) => p.category);
    const worst = out.pollen.filter((p) => p.level >= 3).sort((a, b) => b.level - a.level);
    if (worst.length) out.bad.push(`${worst.map((p) => p.name).slice(0, 2).join(' and ')} pollen ${worst[0].category.toLowerCase()}`);
  }
  return out;
}
const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const hm = (min) => `${Math.floor(min / 60)} h ${min % 60} min`;
/** A warning's end: the time today, else the day and the time. */
const when = (iso) => { const d = new Date(iso); return d.toDateString() === new Date().toDateString() ? clock(iso) : `${d.toLocaleDateString([], { weekday: 'short' })} ${clock(iso)}`; };
const sevClass = (s) => ({ Extreme: 'sev4', Severe: 'sev3', Moderate: 'sev2' })[s] || 'sev1';
/** One warning in the panel: what, until when, the headline; what it says and what to do folded under it. */
function warnBlock(x) {
  return h('details', { class: `wxalert ${sevClass(x.severity)}` },
    h('summary', null, icon('warn', 's'), h('span', { class: 'wxaev' }, x.event), x.ends ? h('span', { class: 'muted small' }, `until ${when(x.ends)}`) : null),
    x.headline ? h('div', { class: 'small' }, x.headline) : null,
    x.text ? h('p', { class: 'small wxatext' }, x.text) : null,
    x.instruction ? h('p', { class: 'small wxatext' }, h('b', null, 'What to do: '), x.instruction) : null,
    x.source ? h('div', { class: 'muted small' }, x.source) : null);
}
/** Air quality or one pollen: its name and AccuWeather's category, coloured by level (1 good … 6 hazardous). */
const levelPill = (name, x, title) => h('span', { class: `wxlvl lvl${Math.min(6, Math.max(1, x.level || 1))}`, title: title || null }, h('span', null, name), h('b', null, x.category));
/** °F and mph, or °C and km/h: the person's own choice (Customize, layout units), else what the weather is set up with. */
export const wxImperial = (w) => ((S.layout && S.layout.units) || w.units) === 'imperial';
/** The hours still ahead in AccuWeather's 12-hour forecast (the server's copy can be up to 90 minutes old). */
export const nextHours = (w) => (w.hourly || []).filter((x) => new Date(x.t) > Date.now() - 30 * 60 * 1000);
const hourLabel = (x) => new Date(x.t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const isWet = (x) => x.wet || (x.rain != null && x.rain >= 50);
/** "Rain from 15:00", "Rain until 16:00", or nothing when the next hours stay dry. */
export function rainNote(w) {
  const hs = nextHours(w);
  if (!hs.length) return '';
  const what = (x) => ({ Rain: 'Rain', Snow: 'Snow', Ice: 'Ice', Mixed: 'Sleet' })[x.kind] || 'Rain';
  if (isWet(hs[0])) {
    const dry = hs.find((x) => !isWet(x));
    return dry ? `${what(hs[0])} until ${hourLabel(dry)}` : `${what(hs[0])} for hours`;
  }
  const wet = hs.find(isWet);
  return wet ? `${what(wet)} from ${hourLabel(wet)}` : '';
}
/** The next hours in a row: the hour, the sky, the temperature, and the chance of rain when there is one. */
export function hourRow(w, hours) {
  const imp = wxImperial(w), t = (v) => fmtTemp(imp ? degF(v) : v);
  return h('div', { class: 'wxhours' }, hours.map((x) => h('div', { class: `wxhour${isWet(x) ? ' wet' : ''}`, title: `${x.text || ''}${x.rain != null ? ` · ${x.rain}% chance of rain` : ''}` },
    h('span', { class: 'muted small' }, new Date(x.t).toLocaleTimeString([], { hour: 'numeric' })), wxIcon(x.icon), h('span', { class: 'small' }, t(x.temp)),
    h('span', { class: 'small wxpct' }, x.rain ? `${x.rain}%` : ''))));
}

// ------------------------------------------------------------------ the bookmarks
/** The bookmarks, as homepage lays them out: a column per group, a row per link with its abbreviation (or icon), name and host.
    As the person likes them (Customize, layout bookmarks): that full list; "icons": each group's links as a row of
    icons, the name in the tooltip; "folded": the groups' names alone, each opening on a tap (this browser remembers which).
    A block of the person's own grid can be one group alone (el.group: its id) and have a look of its own (el.look). */
export async function drawBookmarks(el) {
  let gs;
  try { gs = (await bookmarkGroups()).groups; } catch (e) { el.replaceChildren(h('div', { class: 'muted small' }, e.message)); return; }
  if (!el.isConnected) return;
  const canEdit = ['editor', 'admin'].includes(S.user.role);
  S.bookmarks = gs.flatMap((g) => g.links);  // the search box looks through them
  if (el.group != null) gs = gs.filter((g) => String(g.id != null ? g.id : g.name) === String(el.group));
  quiet(el, !gs.some((g) => g.links.length));
  if (!gs.length) { el.replaceChildren(h('a', { class: 'lnk small', href: '#/bookmarks' }, el.group != null ? 'That group of bookmarks is not on the page any more' : canEdit ? 'Add bookmarks, or pick some for this page' : 'All bookmarks')); return; }
  const look = el.look || (S.layout && S.layout.bookmarks) || 'list';
  el.classList.toggle('bmicons', look === 'icons'); el.classList.toggle('bmfolded', look === 'folded');
  const open = bmUnfolded();
  const link = (l) => {
    const src = bmIcon(l);
    return h('a', { class: 'bm', href: l.href, title: look === 'icons' ? `${l.name}\n${l.href}` : l.href, target: '_blank', rel: 'noreferrer', 'data-id': l.id, 'data-name': look === 'icons' ? l.name : null, 'aria-label': look === 'icons' ? l.name : null },
      h('span', { class: 'bmic' }, src ? h('img', { src, alt: '', onerror: (e) => { e.target.replaceWith(l.abbr); } }) : l.abbr),
      look === 'icons' ? null : h('span', { class: 'bmname' }, l.name), look === 'icons' ? null : h('span', { class: 'bmdesc muted small' }, l.description));
  };
  const groups = gs.filter((g) => g.links.length || canEdit).map((g) => {
    const id = String(g.id != null ? g.id : g.name), n = g.links.length;
    const all = n > 1 ? h('button', { class: 'iconbtn bmopenall', title: `Open all ${n} in tabs`, 'aria-label': `Open all ${n} links of ${g.name} in tabs`, onclick: (e) => { e.stopPropagation(); openAll(g.name, g.links); } }, icon('tabs', 's')) : null;
    const links = h('div', { class: 'bmlist' }, g.links.map(link), canEdit && !n ? h('a', { class: 'lnk small', href: '#/bookmarks' }, 'Nothing shown: add or pick links') : null);
    let head;
    if (look === 'folded') {
      const shut = !open.includes(id);
      links.hidden = shut;
      head = h('h2', null, h('button', { class: 'bmgfold', 'aria-expanded': String(!shut), onclick: () => { links.hidden = !links.hidden; head.firstChild.setAttribute('aria-expanded', String(!links.hidden)); bmUnfolded(id, !links.hidden); } },
        icon('right', 's'), h('span', { class: 'bmfname' }, g.name), h('span', { class: 'muted small' }, String(n))), all);
    } else head = h('h2', null, g.name, all);
    const group = h('div', { class: 'bmgroup' }, head, links);
    // how tall it stands, for the packing: the heading, the rows (or the rows of icons, about five across), the gap under
    group.est = 36 + 20 + (look === 'folded' && links.hidden ? 0 : look === 'icons' ? Math.ceil(Math.max(1, n) / 5) * 48 : Math.max(1, n) * 48);
    return group;
  });
  packBookmarks(el, groups);
  drawBookmarkStatus(el);
  bmIconsLater(el, S.bookmarks, async () => (await api('api/bookmarks')).groups.flatMap((g) => g.links));
}
/** The groups of bookmarks on the page; cards drawn together (a block per group) ask once. */
let bmAsked = null;
export function bookmarkGroups() {
  if (!bmAsked) { bmAsked = api('api/bookmarks'); const forget = () => { bmAsked = null; }; bmAsked.then(() => setTimeout(forget, 1500), forget); }
  return bmAsked;
}
/** The folded groups this browser has open; with an id, notes that one as open or shut. */
function bmUnfolded(id, isOpen) {
  let ids = [];
  try { const v = JSON.parse(localStorage.getItem('iostart.bmopen') || '[]'); if (Array.isArray(v)) ids = v.map(String); } catch { /* private mode, or not ours */ }
  if (id == null || ids.includes(id) === isOpen) return ids;
  ids = isOpen ? [...ids, id] : ids.filter((x) => x !== id);
  try { localStorage.setItem('iostart.bmopen', JSON.stringify(ids.slice(-60))); } catch { /* private mode */ }
  return ids;
}

/** The groups packed into columns: each goes, in order, under the shortest column so far, so a short group fills the
    room under a short column instead of starting a new row under the longest one. Packed again when the width changes
    (the number of columns follows it: as many 250 px columns as fit, one on a phone). */
function packBookmarks(el, groups) {
  const GAP = 20, MIN = 250;
  let cols = 0;
  const pack = () => {
    const width = el.clientWidth || el.getBoundingClientRect().width;
    const n = Math.max(1, Math.min(groups.length, Math.floor((width + GAP) / (MIN + GAP))));
    if (n === cols) return;
    cols = n;
    const heights = new Array(n).fill(0), columns = Array.from({ length: n }, () => h('div', { class: 'bmcol' }));
    for (const g of groups) {
      const i = heights.indexOf(Math.min(...heights));
      columns[i].append(g);
      heights[i] += g.est;
    }
    el.style.setProperty('--bmcols', n);
    el.replaceChildren(...columns, h('a', { class: 'pillbtn bmall', href: '#/bookmarks', title: 'Every bookmark, what is on this page, and sync with browsers' }, icon('link', 's'), 'All bookmarks'));
  };
  pack();
  new ResizeObserver(pack).observe(el);
}

// ------------------------------------------------------------------ the coming days, birthdays, the strip of photos
/** The two cards stand no taller than four fifths of one row of tiles above them (the first: on a tablet or phone the
    tiles take two rows or more), and never under 128px; one with more gets a "Show all" in its header. */
export function capAgenda(apps, agenda) {
  if (!apps) return;
  const fit = () => {
    const row = apps.firstElementChild ? apps.firstElementChild.offsetHeight : apps.offsetHeight;
    agenda.style.setProperty('--cap', `${Math.max(128, Math.round(row * 0.8))}px`);  // a fifth lower: they use their width
    for (const card of agenda.querySelectorAll('.card')) {
      const rows = card.querySelector('.rows'), btn = card.querySelector('.showall');
      if (!rows || !btn) continue;
      const capped = card.classList.contains('capped'), over = capped ? rows.scrollHeight > rows.clientHeight + 1 : true;
      card.classList.toggle('over', capped && over);  // the fade at the bottom, only when something is cut off
      btn.hidden = capped && !over;
    }
  };
  new ResizeObserver(fit).observe(apps);
  new MutationObserver(fit).observe(agenda, { childList: true, subtree: true });
  fit();
}
const showAll = (card) => h('button', { class: 'lnk showall', hidden: true, onclick: () => { card.classList.toggle('capped'); card.querySelector('.showall').textContent = card.classList.contains('capped') ? 'Show all' : 'Show less'; } }, 'Show all');
/** ioCalendar carries the family's birthdays too (its birthdays calendar): with the Birthdays card on the page, the
    calendar's "X's birthday" / anniversary all-day events are left to that card. */
export const isBirthdayEvent = (o) => o.allDay && /\b(birthday|anniversary)\b/i.test(o.title || '');
export const withoutBirthdays = (items) => (S.birthdaysCard ? items.filter((o) => !isBirthdayEvent(o)) : items);

/** Birthdays (and the other dates ioContact keeps) in the next 30 days, a line each; a row opens the contact. */
export async function drawBirthdays(el, again = false) {
  const app = S.apps.find((a) => a.key === 'iocontact'), d = await widget('iocontact');
  if (!d || !d.items || !el.isConnected) { if (!again) { quiet(el, true, true); el.remove(); } return; }
  quiet(el, !d.items.length);
  const what = (it) => (it.label === 'birthday' ? (it.turns ? String(it.turns) : '') : it.label + (it.turns ? ` · ${it.turns} years` : ''));
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, 'Birthdays'), showAll(el), h('a', { class: 'muted', href: app.url, title: app.url }, d.more ? `+${d.more} more · ioContact` : 'ioContact')),
    d.items.length ? h('div', { class: 'rows bdrows' }, d.items.map((it) => h('a', { class: 'bday', href: `${app.url}/#/c/${it.id}`, title: it.turns && it.label === 'birthday' ? `${it.name} turns ${it.turns}` : it.name }, contactFace(it),
      h('span', { class: 'bdname' }, it.name), h('span', { class: 'muted small bdwhat' }, what(it)),
      h('span', { class: `bdwhen${it.in === 0 ? ' today' : ''}` }, inDays(it.in)))))
      : h('div', { class: 'muted small' }, 'No birthdays in the next 30 days'));
}

/** The coming week from ioCalendar, day by day (today lives on the ioCalendar tile); a day opens in ioCalendar.
    A block of the person's own grid can be the week of one member of the family (el.who: {id, name}). */
export async function drawWeek(el, again = false) {
  const app = S.apps.find((a) => a.key === 'iocalendar'), d = await widget('iocalendar', { kind: el.who ? `week:${el.who.id}` : 'week' });
  if (!d || !d.days || !el.isConnected) { if (!again) { quiet(el, true, true); el.remove(); } return; }
  const head = (date) => { const s = new Date(`${date}T12:00:00`); const days = Math.round((s - new Date().setHours(12, 0, 0, 0)) / 86400000);
    return days === 1 ? 'Tomorrow' : s.toLocaleDateString([], { weekday: 'long' }); };
  const days = d.days.map((day) => ({ ...day, items: withoutBirthdays(day.items) })).filter((day) => day.items.length);
  quiet(el, !days.length);
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, el.who ? `${el.who.name}’s week` : 'This week'), showAll(el), h('a', { class: 'muted', href: app.url, title: app.url }, d.more ? `+${d.more} more · ioCalendar` : 'ioCalendar')),
    days.length ? h('div', { class: 'rows wkrows' }, days.map((day) => h('div', { class: 'wkday' },
      h('a', { class: 'wkhead', href: `${app.url}/#/day/${day.date}`, title: new Date(`${day.date}T12:00:00`).toLocaleDateString([], { month: 'long', day: 'numeric' }) },
        head(day.date), h('span', { class: 'muted small' }, new Date(`${day.date}T12:00:00`).toLocaleDateString([], { month: 'short', day: 'numeric' }))),
      day.items.map((o) => evRow(o, evTime(o))))))
      : h('div', { class: 'muted small' }, 'Nothing planned in the next 7 days'));
}

/** A card the width of the page with a row of ioPix photos: at random (Rediscover) or from this day in earlier years. */
export async function drawStrip(el, kind) {
  const pix = S.apps.find((a) => a.key === 'iopix');
  const d = await widget('iopix', { kind, n: 16 });
  if (!d || !d.items || !d.items.length || !el.isConnected) { quiet(el, true, true); el.remove(); return; }
  quiet(el, false);
  const otd = d.kind === 'onthisday';
  const cap = (it) => (otd ? (it.yearsAgo === 1 ? '1 year ago' : `${it.yearsAgo} years ago`) : (it.year || ''));
  // Shuffle, as ioPix has: a fresh row, picked again at random (On this day is the day's photos: nothing to shuffle)
  const reshuffle = () => { el.classList.add('busy'); drawStrip(el, kind); };
  const shuffle = otd ? null : h('button', { class: 'lnk shuffle', title: 'Another row of photos', onclick: (e) => { e.preventDefault(); reshuffle(); } }, icon('update', 's'), 'Shuffle');
  el.classList.remove('busy');
  const row = h('div', { class: 'row' }, d.items.map((it) => h('a', { class: 'wgph', href: pixPhotoUrl(pix, it.id), title: String(cap(it)) },
    h('img', { src: itemImage('iopix', 'photo', it.id), alt: '', loading: 'lazy', onerror: (e) => e.target.parentNode.remove() }),
    cap(it) ? h('span', null, cap(it)) : null)));
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, otd ? 'On this day' : 'Rediscover'), shuffle,
    h('a', { class: 'muted', href: pix.url, title: pix.url }, otd && d.count > d.items.length ? `${d.count} photos · ioPix` : 'ioPix')), row);
  autoStrip(el, row, otd ? null : reshuffle);
}

/* The strip changes by itself, as each person picks in Customize (layout stripMove, stripEvery): a fresh row of photos
   (Rediscover; On this day has no other photos, so it turns the page instead), the next screenful of the row, or
   nothing. It waits while the pointer is over it, while it is touched, dragged, wheeled or has the keyboard focus (and a
   little while after), while the tab is hidden or a dialog is open. For reduced motion, the page turns without gliding. */
export const STRIP_MOVES = { shuffle: 'A fresh row of photos', page: 'The next photos in the row', off: 'Stays as it is' };
export const STRIP_EVERY = [30, 60, 120, 300, 600, 1800];  // seconds
export const STRIP_DEFAULT = { move: 'shuffle', every: 60 }, STRIP_REST = 8000;
export const everyText = (s) => (s < 60 ? `${s} seconds` : s === 60 ? '1 minute' : `${s / 60} minutes`);
function autoStrip(el, row, reshuffle) {
  if (el.stopAuto) el.stopAuto();
  const L = S.layout || {};
  let move = L.stripMove || STRIP_DEFAULT.move;
  const every = (STRIP_EVERY.includes(L.stripEvery) ? L.stripEvery : STRIP_DEFAULT.every) * 1000;
  if (move === 'shuffle' && !reshuffle) move = 'page';
  if (move === 'off') return;
  const still = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  let hover = false, touchedAt = 0, changedAt = Date.now();
  const busy = () => hover || el.contains(document.activeElement) || Date.now() - touchedAt < STRIP_REST;
  const touched = () => { touchedAt = Date.now(); };
  row.addEventListener('mouseenter', () => { hover = true; });
  row.addEventListener('mouseleave', () => { hover = false; touched(); });
  for (const ev of ['pointerdown', 'touchstart', 'touchmove', 'wheel', 'keydown']) row.addEventListener(ev, touched, { passive: true });
  const tick = () => {
    if (!el.isConnected) { el.stopAuto(); return; }
    if (Date.now() - changedAt < every || document.hidden || busy() || document.querySelector('.dialog-back')) return;
    changedAt = Date.now();
    if (move === 'shuffle') { el.stopAuto(); reshuffle(); return; }
    if (row.scrollWidth <= row.clientWidth + 1) return;
    const atEnd = row.scrollLeft + row.clientWidth >= row.scrollWidth - 2;
    row.scrollTo({ left: atEnd ? 0 : row.scrollLeft + row.clientWidth, behavior: still() ? 'auto' : 'smooth' });
  };
  const t = setInterval(tick, 1000);
  el.stopAuto = () => { clearInterval(t); el.stopAuto = null; };
}

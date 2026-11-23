/* The search box: one search across the apps and the web, quick add (an event, a task, a note), the calculator. */
import { dialog, fail, fld, icon, initials, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { $, api, appName, bmIcon, fold, itemImage, money, pad2, S, viewerTz } from './core.js';
import { drawHomeCard, HA_POPUPS, haAct, haIcon, haLink, haPopup } from './homeassistant.js';
import { liveRefresh } from './main.js';
import { parseTimer, timerLength, timerStart } from './timers.js';

// ------------------------------------------------------------------ the search box (⌘K / Ctrl-K)
// an app's own search ("Search in"), and the apps whose finds the box lists, in the order their sections come: their manifests (app.json "start")
const appSearch = (a, q) => (a.start && a.start.searchUrl ? `${a.url}/${a.start.searchUrl.replace('{q}', encodeURIComponent(q))}` : null);
const finders = () => S.apps.filter((a) => a.start && a.start.find).sort((x, y) => x.start.find.rank - y.start.find.rank);
/** "Today 19:00", "Tomorrow", "Fri 21 Nov", "12 Mar 2024": when a found event or task is, short. */
function whenShort(iso, allDay) {
  if (!iso) return '';
  const d = allDay ? new Date(`${iso.slice(0, 10)}T00:00`) : new Date(iso);
  if (isNaN(d)) return '';
  const n = Math.round((new Date(d).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
  const day = n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : n === -1 ? 'Yesterday'
    : d.toLocaleDateString([], { weekday: n > 0 && n < 7 ? 'short' : undefined, day: 'numeric', month: 'short', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
  return allDay ? day : `${day} ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
}
/** A row of the search box for what an app found, in the suite's shape (iosuite_shared.suiteitems): its picture or
    icon (with its colour), its name, then when it is, or its line, and what it comes to. */
function foundRow(a, x, mark) {
  const ic = x.icon || 'link';
  const pic = x.image != null
    ? h('span', { class: `bmic pic${x.round ? ' round' : ''}` }, h('img', { src: itemImage(a.key, x.kind, x.id, x.image), alt: '', onerror: (e) => e.target.replaceWith(x.round ? initials(x.title) : icon(ic, 's')) }))
    : h('span', { class: 'bmic hit', style: x.color ? { '--c': x.color } : undefined }, icon(ic, 's'));
  const when = x.when ? [whenShort(x.when, x.allDay), x.recurring ? '↻' : ''].filter(Boolean).join(' ') : '';
  return [pic, h('span', { class: 'qname', title: [x.title, x.text].filter(Boolean).join(' · ') }, x.title, mark ? h('span', { class: 'qfrom small' }, a.start.find.head) : null),
    when && x.amount == null ? h('span', { class: 'muted small when' }, when) : h('span', { class: `muted small ${x.amount != null ? 'when' : 'rest'}` }, x.amount != null ? (x.kind === 'payee' ? x.text : when) : x.text || ''),
    x.amount != null ? h('span', { class: `small qamt${x.amount > 0 && x.kind !== 'payee' ? ' in' : ''}` }, money(x.amount, x.currency)) : null].filter(Boolean);
}
export function searchBox() {
  const inp = h('input', { class: 'q', type: 'search', placeholder: 'Search, or add something', title: 'Search the suite and the web. Or add an event: “dinner fri 19:00”; a task: “t buy milk sat”; a note: “n the gate code is 4411”; start a timer: “timer 10m pasta”; work something out: “15% of 84”, “350f in c”, “120 usd in eur”.', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Search bookmarks, people, events, tasks, recipes, notes, things in the house, money, photos and the web, or add an event, a task (t …) or a note (n …)' });
  const list = h('div', { class: 'qlist', hidden: true });
  const box = h('div', { class: 'search' }, icon('search', 's'), inp, h('kbd', null, /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl K'), list);
  let rows = [], sel = 0, timer = null, things = { q: '', items: [] };
  let found = { q: '', items: [] };  // what the apps found for that text, ranked together (best first)
  const hide = () => { list.hidden = true; list.replaceChildren(); rows = []; };
  const row = (href, kids, ext) => { const a = h('a', { class: 'qrow', href, ...(ext ? { target: '_blank', rel: 'noreferrer' } : {}), onmousedown: (e) => e.preventDefault() }, kids); rows.push(a); return a; };
  const build = () => {
    const q = inp.value.trim(), ql = q.toLowerCase();
    rows = [];
    if (!q) return hide();
    const links = (S.bookmarks || []).filter((l) => fold(`${l.name} ${l.description || ''} ${l.href}`).includes(fold(q))).slice(0, 6);
    // what the apps found, ranked together (iostart/search.py): the best few from any app first when more than one app
    // found something, then each app's own section, the one with the best find first
    const byKey = Object.fromEntries(finders().map((a) => [a.key, a]));
    const hits = (found.q === ql ? found.items : []).filter((x) => byKey[x.app]);
    const top = new Set(new Set(hits.map((x) => x.app)).size > 1 ? hits.slice(0, 3) : []);
    const found_ = [...new Set(hits.map((x) => x.app))].map((k) => [byKey[k], hits.filter((x) => x.app === k && !top.has(x))]).filter(([, xs]) => xs.length);
    // "t buy milk fri": a task for ioTask; "n the gate code is 4411": a note for ioNote (the row comes first: Enter adds it)
    const add = quickPrefix(q);
    // "timer 10m pasta": a kitchen timer; "15% of 84", "350f in c": the answer (Enter copies it)
    const tmr = add ? null : parseTimer(q), calc = add || tmr ? null : calcOf(q);
    if (calc && calc.need === 'rates') calcRates(build);
    const bang = add || tmr ? null : webBang(q), site = bang || add || tmr ? null : looksLikeSite(q), cal = !bang && !add && !tmr && S.apps.find((a) => a.key === 'iocalendar') && parseEvent(q);
    const eng = bang ? bang.engine : webEngine(), wq = bang ? bang.q : q;
    const webRow = () => row(eng.url(wq), [h('span', { class: 'bmic' }, icon('web', 's')), h('span', { class: 'qname' }, `“${wq}”`), h('span', { class: 'muted small' }, eng.name)], true);
    const any = links.length || hits.length || (things.q === ql && things.items.length);
    const addRow = () => {
      if (add.kind === 'task') {
        const t = parseEvent(add.text) || { title: add.text[0].toUpperCase() + add.text.slice(1), date: null, start: null };
        const a = row('#', [h('span', { class: 'bmic' }, icon('task', 's')), h('span', { class: 'qname' }, t.title), h('span', { class: 'muted small' }, t.date ? taskWhen(t) : 'No due date')]);
        a.onclick = (e) => { e.preventDefault(); inp.blur(); quickTask(t); }; return a;
      }
      const a = row('#', [h('span', { class: 'bmic' }, icon('note', 's')), h('span', { class: 'qname' }, add.text), h('span', { class: 'muted small' }, 'New note')]);
      a.onclick = (e) => { e.preventDefault(); inp.blur(); quickNote(add.text); }; return a;
    };
    const kids = [
      add ? [h('div', { class: 'qhead' }, add.kind === 'task' ? 'Add a task' : 'Add a note'), addRow()] : null,
      tmr ? [h('div', { class: 'qhead' }, 'Start a timer'), (() => { const a = row('#', [h('span', { class: 'bmic' }, icon('timer', 's')), h('span', { class: 'qname' }, tmr.label), h('span', { class: 'muted small' }, timerLength(tmr.seconds))]);
        a.onclick = (e) => { e.preventDefault(); inp.blur(); timerStart(tmr); }; return a; })()] : null,
      calc && calc.text ? [h('div', { class: 'qhead' }, 'Answer'), (() => { const a = row('#', [h('span', { class: 'bmic' }, icon('calc', 's')), h('span', { class: 'qname qcalc' }, calc.text), h('span', { class: 'muted small' }, calc.note ? `${calc.note} · Enter copies` : 'Enter copies')]);
        a.onclick = (e) => { e.preventDefault(); calcCopy(calc); }; return a; })()] : null,
      calc && calc.need ? [h('div', { class: 'qhead' }, 'Answer'), h('div', { class: 'qrow muted small' }, 'Getting the exchange rates…')] : null,
      // a site typed in full, or a prefix (g, w, yt…): that first, Enter goes there
      site ? [h('div', { class: 'qhead' }, 'Open'), row(site, [h('span', { class: 'bmic' }, icon('link', 's')), h('span', { class: 'qname' }, site.replace(/^https?:\/\//, '')), h('span', { class: 'muted small' }, 'New tab')], true)] : null,
      bang ? [h('div', { class: 'qhead' }, eng.name), webRow()] : null,
      links.length ? h('div', { class: 'qhead' }, 'Bookmarks') : null,
      links.map((l) => { const src = bmIcon(l); return row(l.href, [h('span', { class: 'bmic' }, src ? h('img', { src, alt: '' }) : l.abbr), h('span', { class: 'qname' }, l.name), h('span', { class: 'muted small' }, l.description || l.href)], true); }),
      top.size ? [h('div', { class: 'qhead' }, 'Best matches'), ...[...top].map((x) => row(`${byKey[x.app].url}/${x.href || ''}`, foundRow(byKey[x.app], x, true)))] : null,
      found_.flatMap(([a, xs]) => [h('div', { class: 'qhead' }, a.start.find.head), ...xs.map((x) => row(`${a.url}/${x.href || ''}`, foundRow(a, x)))]),
      // Home Assistant: an entity's state, and a tap switches the ones the admin lets the page control
      things.q === ql && things.items.length ? h('div', { class: 'qhead' }, 'Home') : null,
      things.q === ql ? things.items.map((t) => { const a = row(t.control ? '#' : haLink(t), [h('span', { class: `bmic ha${t.on ? ' on' : ''}` }, icon(haIcon(t), 's')), h('span', { class: 'qname' }, t.name), h('span', { class: `muted small${t.control ? ' tap' : ''}` }, t.control ? `${t.text || t.state} · tap` : t.text || t.state)]);
        if (t.control && HA_POPUPS[t.domain]) a.onclick = (e) => { e.preventDefault(); inp.blur(); haPopup(t, (r) => Object.assign(t, r)); };
        else if (t.control) a.onclick = async (e) => { e.preventDefault(); const r = await haAct(t.id, 'toggle'); if (r) { Object.assign(t, r); build(); } const card = document.querySelector('.homecard'); if (card) setTimeout(() => drawHomeCard(card, true), 4000); }; return a; }) : null,
      // "dinner fri 19:00": a new event in ioCalendar (a dialog to check it first)
      cal ? [h('div', { class: 'qhead' }, 'Add to the calendar'), (() => { const a = row('#', [h('span', { class: 'bmic' }, icon('event', 's')), h('span', { class: 'qname' }, cal.title || '(no title)'), h('span', { class: 'muted small' }, eventWhen(cal))]);
        a.onclick = (e) => { e.preventDefault(); inp.blur(); quickAdd(cal); }; return a; })()] : null,
      // nothing here matches: the web first, so Enter searches it
      !bang && !site && !any && !add && !tmr ? [h('div', { class: 'qhead' }, 'Web'), webRow()] : null,
      add ? null : h('div', { class: 'qhead' }, 'Search in'),
      add ? [] : S.allApps.filter((a) => appSearch(a, q)).map((a) => row(appSearch(a, q), [h('img', { class: 'qapp', src: a.icon, alt: '' }), h('span', { class: 'qname' }, appName(a.name, a.color)), h('span', { class: 'muted small' }, `“${q}”`)])),
      !bang && !site && any ? webRow() : null,
    ];
    sel = Math.min(sel, rows.length - 1);
    rows.forEach((r, i) => r.classList.toggle('on', i === sel));
    list.replaceChildren(...kids.flat().filter(Boolean)); list.hidden = false;
  };
  // one question for every app (api/search: asked at the same time, ranked together); an app that is slow to answer
  // is asked again on its own and its finds join the others where they rank, so it holds up none of them
  const askApps = async () => {
    const q = inp.value.trim(), ql = q.toLowerCase();
    if (q.length < 2 || quickPrefix(q) || parseTimer(q)) return;  // "t buy milk" is something to add, not to look for
    const keys = finders().map((a) => a.key);
    if (!keys.length) return;
    const ask = (params) => api(`api/search?${new URLSearchParams({ q, tz: viewerTz(), ...params })}`).catch(() => null);
    const take = (d) => {
      if (!d || inp.value.trim().toLowerCase() !== ql) return;
      const items = (found.q === ql ? found.items : []).concat(d.items || []);
      items.sort((x, y) => y.score - x.score || keys.indexOf(x.app) - keys.indexOf(y.app));
      found = { q: ql, items }; build();
    };
    found = { q: ql, items: [] };
    const d = await ask({ apps: keys.join(',') });
    take(d);
    if (d && d.late && d.late.length) d.late.forEach((k) => ask({ apps: k, wait: 1 }).then(take));
  };
  const askThings = async () => {
    const q = inp.value.trim(), ql = q.toLowerCase();
    if (q.length < 2 || S.ha === false || quickPrefix(q)) return;
    let d = null;
    try { d = await api(`api/ha/search?${new URLSearchParams({ q, n: 5 })}`); } catch { d = null; }
    if (inp.value.trim().toLowerCase() !== ql) return;
    things = { q: ql, items: (d && d.items) || [] }; build();
  };
  inp.oninput = () => { sel = 0; build(); clearTimeout(timer); timer = setTimeout(() => { askApps(); askThings(); }, 250); };
  inp.onfocus = () => { if (inp.value.trim()) build(); };
  inp.onblur = () => setTimeout(hide, 150);
  inp.onkeydown = (e) => {
    if (e.key === 'Escape') { if (inp.value) { inp.value = ''; hide(); } else inp.blur(); e.preventDefault(); }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { if (!rows.length) return; sel = (sel + (e.key === 'ArrowDown' ? 1 : rows.length - 1)) % rows.length; rows.forEach((r, i) => r.classList.toggle('on', i === sel)); rows[sel].scrollIntoView({ block: 'nearest' }); e.preventDefault(); }
    else if (e.key === 'Enter') { if (rows[sel]) { rows[sel].click(); e.preventDefault(); if (rows[sel] && rows[sel].target === '_blank') { inp.value = ''; hide(); } } }
  };
  S.focusSearch = () => { inp.focus(); inp.select(); };
  return box;
}

// ------------------------------------------------------------------ the web from the search box
/* Enter with nothing of the suite matching searches the web with the viewer's engine (Customize the page); a prefix
   picks a site instead: "g …" Google, "w …" Wikipedia, "yt …" YouTube… (also as "!g …"). A typed address opens. */
const engine = (name, base) => ({ name, url: (q) => base + encodeURIComponent(q) });
export const ENGINES = {
  duckduckgo: engine('DuckDuckGo', 'https://duckduckgo.com/?q='), google: engine('Google', 'https://www.google.com/search?q='),
  bing: engine('Bing', 'https://www.bing.com/search?q='), startpage: engine('Startpage', 'https://www.startpage.com/do/search?q='),
  ecosia: engine('Ecosia', 'https://www.ecosia.org/search?q='), kagi: engine('Kagi', 'https://kagi.com/search?q='),
};
const wikiLang = () => ((navigator.language || 'en').slice(0, 2).toLowerCase().match(/^[a-z]{2}$/) || ['en'])[0];
const BANGS = {
  g: () => ENGINES.google, d: () => ENGINES.duckduckgo, ddg: () => ENGINES.duckduckgo, b: () => ENGINES.bing, sp: () => ENGINES.startpage, k: () => ENGINES.kagi,
  w: () => engine('Wikipedia', `https://${wikiLang()}.wikipedia.org/w/index.php?search=`), yt: () => engine('YouTube', 'https://www.youtube.com/results?search_query='),
  m: () => engine('Google Maps', 'https://www.google.com/maps/search/'), maps: () => engine('Google Maps', 'https://www.google.com/maps/search/'),
  gh: () => engine('GitHub', 'https://github.com/search?q='), r: () => engine('Reddit', 'https://www.reddit.com/search/?q='),
  i: () => engine('Google Images', 'https://www.google.com/search?tbm=isch&q='), tr: () => engine('Google Translate', 'https://translate.google.com/?sl=auto&op=translate&text='),
};
export const BANG_HELP = 'g Google · d DuckDuckGo · b Bing · w Wikipedia · yt YouTube · m Maps · gh GitHub · r Reddit · i Images · tr Translate';
const webEngine = () => ENGINES[(S.layout && S.layout.search) || 'duckduckgo'] || ENGINES.duckduckgo;
/** {engine, q} for "g cats" or "!g cats", else null. */
function webBang(q) {
  const m = q.match(/^!?([a-z]{1,4})\s+(\S.*)$/i);
  return m && BANGS[m[1].toLowerCase()] ? { engine: BANGS[m[1].toLowerCase()](), q: m[2].trim() } : null;
}
/** An address typed in full ("github.com", "nas.local:5000/x", "https://…"): the address to open, else null. */
function looksLikeSite(q) {
  if (/\s/.test(q)) return null;
  if (/^https?:\/\/\S+$/i.test(q)) return q;
  return /^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(:\d+)?(\/\S*)?$/i.test(q) || /^[a-z0-9-]+\.local(:\d+)?(\/\S*)?$/i.test(q) ? `https://${q}` : null;
}

// ------------------------------------------------------------------ quick add: a new ioCalendar event from the search box
/* "dinner fri 19:00", "dentist tomorrow 9am", "trip 24 dec", "call mum 14:30-15:00": the words that say when (today,
   tomorrow, a weekday, "in 3 days", a date, a time or two) are taken out, the rest is the title. Nothing said about
   when: not an event. A time without a day: today, or tomorrow when that time has passed. A day without a time: all
   day. The dialog shows what was understood, to change before it is saved. */
const WEEKDAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const weekdayOf = (w) => { const m = w.match(/^(sun|mon|tue|wed|thu|fri|sat)(day|s|sday|nesday|rs|rsday|urday|t)?$/); return m ? WEEKDAYS.indexOf(m[1]) : -1; };
const monthOf = (w) => { const m = w.match(/^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?$/); return m ? MONTHS.indexOf(m[1].slice(0, 3)) : -1; };
const ordinal = (w) => { const m = w.match(/^(\d{1,2})(st|nd|rd|th)?,?$/); return m && +m[1] >= 1 && +m[1] <= 31 ? +m[1] : 0; };
/** A time word: "19:00", "19h", "19h30", "7.30", "7pm", "7:30am", "noon", "midnight"; [h, m] or null. pm: the next word. */
function timeOf(w, next) {
  if (w === 'noon') return [12, 0];
  if (w === 'midnight') return [0, 0];
  let m = w.match(/^(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm|a|p)$/);
  if (!m && /^(am|pm)$/.test(next || '')) { m = w.match(/^(\d{1,2})(?:[:.h](\d{2}))?$/); if (m) m[3] = next; }
  if (m) { let hr = +m[1] % 12; if (m[3][0] === 'p') hr += 12; return +m[1] <= 12 && +(m[2] || 0) < 60 ? [hr, +(m[2] || 0)] : null; }
  m = w.match(/^(\d{1,2})(?::(\d{2})|h(\d{2})?)$/) || w.match(/^(\d{1,2})\.(\d{2})$/);
  if (m) { const hr = +m[1], mi = +(m[2] || m[3] || 0); return hr < 24 && mi < 60 ? [hr, mi] : null; }
  return null;
}
function parseEvent(text, now = new Date()) {
  const words = text.trim().split(/\s+/), lw = words.map((w) => w.toLowerCase());
  const used = new Array(words.length).fill(false);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const plus = (n) => new Date(today.getFullYear(), today.getMonth(), today.getDate() + n);
  let date = null, start = null, end = null;
  const take = (...ix) => ix.forEach((i) => { used[i] = true; });
  const usOrder = /^en-us/i.test(navigator.language || '');
  for (let i = 0; i < lw.length; i++) {
    const w = lw[i].replace(/,$/, ''), nx = lw[i + 1], nx2 = lw[i + 2];
    if (used[i]) continue;
    if (!date && (w === 'today' || w === 'tonight')) { date = today; take(i); continue; }
    if (!date && /^(tomorrow|tmrw|tmr|tomorow)$/.test(w)) { date = plus(1); take(i); continue; }
    if (!date && w === 'in' && /^\d{1,3}$/.test(nx || '') && /^(day|days|week|weeks)$/.test(nx2 || '')) { date = plus(+nx * (nx2[0] === 'w' ? 7 : 1)); take(i, i + 1, i + 2); continue; }
    if (!date && weekdayOf(w) >= 0) {
      let n = (weekdayOf(w) - today.getDay() + 7) % 7;
      if (i > 0 && /^(next|on)$/.test(lw[i - 1]) && !used[i - 1]) { if (lw[i - 1] === 'next' && n === 0) n = 7; take(i - 1); }
      date = plus(n); take(i); continue;
    }
    let m = w.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!date && m) { date = new Date(+m[1], +m[2] - 1, +m[3]); take(i); continue; }
    m = w.match(/^(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?$/);
    if (!date && m && !(w.includes('.') && !m[3] && timeOf(w))) {  // 7.30 is a time; 24.12 and 24/12 are dates
      const [d, mo] = usOrder ? [+m[2], +m[1]] : [+m[1], +m[2]];
      if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31) {
        let y = m[3] ? (+m[3] < 100 ? 2000 + +m[3] : +m[3]) : today.getFullYear();
        if (!m[3] && new Date(y, mo - 1, d) < today) y += 1;
        date = new Date(y, mo - 1, d); take(i); continue;
      }
    }
    if (!date && monthOf(w) >= 0) {  // "dec 24", "24 dec", "december 24th"
      let d = 0, j = -1;
      if (nx && ordinal(nx)) { d = ordinal(nx); j = i + 1; } else if (i > 0 && !used[i - 1] && ordinal(lw[i - 1])) { d = ordinal(lw[i - 1]); j = i - 1; }
      if (d) {
        const mo = monthOf(w);
        let y = today.getFullYear();
        if (new Date(y, mo, d) < today) y += 1;
        date = new Date(y, mo, d); take(i, j);
        if (i > 0 && lw[i - 1] === 'on' && !used[i - 1]) take(i - 1);
        if (j === i - 1 && i > 1 && lw[i - 2] === 'on' && !used[i - 2]) take(i - 2);
        continue;
      }
    }
    // a time, or a range: "19:00-21:00", "7-9pm", "19:00 - 21:00", "19:00 to 21:00"
    const rng = w.match(/^([^-–]+)[-–]([^-–]+)$/);
    if (!start && rng) {
      const b = timeOf(rng[2], nx), pm = /(pm|p)$/.test(rng[2]) && !/(am|pm|a|p)$/.test(rng[1]);
      const a = timeOf(rng[1] + (pm ? 'pm' : ''), null) || timeOf(rng[1], null);
      if (a && b) { start = a; end = b; take(i); if (/^(am|pm)$/.test(nx || '') && !/(am|pm|a|p)$/.test(rng[2])) take(i + 1); if (i > 0 && /^(at|@|from)$/.test(lw[i - 1])) take(i - 1); continue; }
    }
    const t = timeOf(w, nx) || (i > 0 && /^(at|@)$/.test(lw[i - 1]) && /^\d{1,2}$/.test(w) && +w < 24 ? [+w, 0] : null);
    if (t) {
      if (!start) start = t; else if (!end && i > 0 && /^(to|until|till|-|–)$/.test(lw[i - 1])) { end = t; take(i - 1); } else continue;
      take(i); if (/^(am|pm)$/.test(nx || '') && !/(am|pm|a|p)$/.test(w)) take(i + 1);
      if (i > 0 && /^(at|@|from)$/.test(lw[i - 1]) && !used[i - 1]) take(i - 1);
    }
  }
  if (!date && !start) return null;
  if (!date) date = start && (start[0] * 60 + start[1]) <= now.getHours() * 60 + now.getMinutes() ? plus(1) : today;
  const title = words.filter((_, i) => !used[i]).join(' ').replace(/\s+(on|at|@)$/i, '').trim();
  if (!title) return null;
  return { title: title[0].toUpperCase() + title.slice(1), date, start, end };
}
const ymdOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
/** A local date and time as ISO with its offset, as ioCalendar takes it: 2026-11-07T19:00:00+01:00. */
function isoLocal(d) {
  const off = -d.getTimezoneOffset(), sign = off >= 0 ? '+' : '-', a = Math.abs(off);
  return `${ymdOf(d)}T${pad2(d.getHours())}:${pad2(d.getMinutes())}:00${sign}${pad2(Math.floor(a / 60))}:${pad2(a % 60)}`;
}
function eventWhen(ev) {
  const day = (() => { const n = Math.round((ev.date - new Date(new Date().setHours(0, 0, 0, 0))) / 86400000);
    return n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : ev.date.toLocaleDateString([], n < 7 ? { weekday: 'long' } : { weekday: 'short', month: 'short', day: 'numeric' }); })();
  const tm = (t) => new Date(2000, 0, 1, t[0], t[1]).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return ev.start ? `${day} ${tm(ev.start)}${ev.end ? `–${tm(ev.end)}` : ''}` : `${day}, all day`;
}
async function quickAdd(ev) {
  const cal = S.apps.find((a) => a.key === 'iocalendar');
  let cals = [];
  try { cals = (await api('api/widgets/iocalendar/calendars')).items || []; } catch (e) { fail(e); return; }
  if (!cals.length) { toast('ioCalendar has no calendar you may add events to'); return; }
  const title = h('input', { class: 't', value: ev.title });
  const date = h('input', { class: 't', type: 'date', value: ymdOf(ev.date) });
  const tm = (t) => (t ? `${pad2(t[0])}:${pad2(t[1])}` : '');
  const from = h('input', { class: 't', type: 'time', value: tm(ev.start) }), to = h('input', { class: 't', type: 'time', value: tm(ev.end) });
  const last = localStorage.getItem('iostart.quickadd.calendar');
  const which = h('select', { class: 't' }, cals.map((c) => h('option', { value: c.id, selected: String(c.id) === last ? true : null }, c.name)));
  const body = h('div', null, h('div', { class: 'grid' }, fld('Title', title)), h('div', { class: 'qawhen' }, fld('Day', date), fld('From', from), fld('Until', to)),
    h('p', { class: 'muted small' }, 'No time: all day.'), h('div', { class: 'grid' }, fld('Calendar', which)));
  const ok = await dialog('Add to ioCalendar', body, [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }]);
  if (!ok) return;
  const [y, mo, d] = date.value.split('-').map(Number);
  if (!title.value.trim() || !y) { toast('A title and a day, please'); return; }
  const at = (v) => { const [hh, mm] = v.split(':').map(Number); return new Date(y, mo - 1, d, hh, mm); };
  const json = { title: title.value.trim(), calendarId: which.value, timezone: viewerTz() };
  if (from.value) {
    const s = at(from.value); let e = to.value ? at(to.value) : null;
    if (e && e <= s) e = new Date(+e + 86400000);  // 22:00 until 01:00: the next night
    Object.assign(json, { allDay: false, start: isoLocal(s), ...(e ? { end: isoLocal(e) } : {}) });
  } else Object.assign(json, { allDay: true, start: date.value });
  try {
    await api('api/widgets/iocalendar/events', { method: 'POST', json });
    localStorage.setItem('iostart.quickadd.calendar', which.value);
    toast(`Added to ${cal ? cal.name : 'ioCalendar'}: ${json.title}`);
    $('.search .q') && ($('.search .q').value = '');
    S.refreshedAt = 0; liveRefresh(true);  // the tile and This week show it
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ quick add: a task for ioTask, a note for ioNote
/* "t buy milk", "t call the plumber fri 9am", "todo renew the passport 12 jan": a new task, its due date read as an
   event's day is (none said: no due date). "n the gate code is 4411", "note ideas for mum's birthday": a new note.
   Each opens a small dialog with what was understood, to change before it is saved in the app, as the viewer. */
const QUICK = { t: 'task', todo: 'task', task: 'task', n: 'note', note: 'note' };
/** {kind: 'task' | 'note', text} for "t …" / "todo …" / "task …" / "n …" / "note …" when that app is on the page, else null. */
function quickPrefix(q) {
  const m = q.match(/^([a-z]{1,4})\s+(\S.*)$/i), kind = m && QUICK[m[1].toLowerCase()];
  return kind && S.apps.some((a) => a.key === (kind === 'task' ? 'iotask' : 'ionote')) ? { kind, text: m[2].trim() } : null;
}
const taskWhen = (t) => eventWhen(t).replace(', all day', '');
async function quickTask(t) {
  const app = S.apps.find((a) => a.key === 'iotask');
  let lists = [];
  try { lists = (await api('api/widgets/iotask/lists')).items || []; } catch (e) { fail(e); return; }
  if (!lists.length) { toast('ioTask has no list you may add tasks to'); return; }
  const title = h('input', { class: 't', value: t.title });
  const date = h('input', { class: 't', type: 'date', value: t.date ? ymdOf(t.date) : '' });
  const time = h('input', { class: 't', type: 'time', value: t.start ? `${pad2(t.start[0])}:${pad2(t.start[1])}` : '' });
  const last = localStorage.getItem('iostart.quickadd.list');
  const which = h('select', { class: 't' }, lists.map((c) => h('option', { value: c.id, selected: String(c.id) === last ? true : null }, c.name)));
  const body = h('div', null, h('div', { class: 'grid' }, fld('Task', title)), h('div', { class: 'qawhen two' }, fld('Due', date), fld('At', time)),
    h('p', { class: 'muted small' }, 'No day: no due date.'), h('div', { class: 'grid' }, fld('List', which)));
  const ok = await dialog('Add to ioTask', body, [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }]);
  if (!ok) return;
  if (!title.value.trim()) { toast('A title, please'); return; }
  if (time.value && !date.value) date.value = ymdOf(new Date());
  const json = { title: title.value.trim(), listId: which.value, timezone: viewerTz(), ...(date.value ? { due: time.value ? `${date.value}T${time.value}` : date.value } : {}) };
  try {
    await api('api/widgets/iotask/tasks', { method: 'POST', json });
    localStorage.setItem('iostart.quickadd.list', which.value);
    toast(`Added to ${app ? app.name : 'ioTask'}: ${json.title}`);
    $('.search .q') && ($('.search .q').value = '');
    S.refreshedAt = 0; liveRefresh(true);  // the tile shows it when it is due today
  } catch (e) { fail(e); }
}
async function quickNote(text) {
  const app = S.apps.find((a) => a.key === 'ionote');
  // one line: the note's text as typed, with room to go on; a title only when one is given
  const title = h('input', { class: 't', placeholder: 'Title (none needed)' });
  const note = h('textarea', { class: 't qanote', rows: 5 }); note.value = text;
  const ok = await dialog('Add to ioNote', h('div', null, h('div', { class: 'grid' }, fld('Note', note), fld('Title', title))), [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }]);
  if (!ok) return;
  if (!note.value.trim() && !title.value.trim()) { toast('Some text, please'); return; }
  try {
    await api('api/widgets/ionote/notes', { method: 'POST', json: { title: title.value.trim(), text: note.value.trim() } });
    toast(`Added to ${app ? app.name : 'ioNote'}`);
    $('.search .q') && ($('.search .q').value = '');
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ the calculator in the search box
/* "15% of 84", "(12+8)*1.21", "2^10", "84 + 15%", "350f in c", "3 cups in ml", "5 km to mi", "120 usd in eur": the
   answer is the first row of the box, and Enter copies it. A sum is worked out here (no eval), a currency with the
   European Central Bank's rates of the day (api/rates, fetched by the server the first time somebody converts).
   Not taken for a sum: a phone number or a date typed without spaces ("555-1234", "24/12"); "=24/12" is one. */
const CALC_SYMBOLS = { '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY', '₹': 'INR', '₩': 'KRW', 'euro': 'EUR', 'euros': 'EUR' };
const CALC_UNITS = (() => {
  const u = {};
  const add = (dim, f, ...names) => names.forEach((n) => { u[n] = { dim, f }; });
  add('len', 0.001, 'mm', 'millimeter', 'millimeters', 'millimetre', 'millimetres'); add('len', 0.01, 'cm', 'centimeter', 'centimeters', 'centimetre', 'centimetres');
  add('len', 1, 'm', 'meter', 'meters', 'metre', 'metres'); add('len', 1000, 'km', 'kilometer', 'kilometers', 'kilometre', 'kilometres');
  add('len', 0.0254, 'in', 'inch', 'inches', '"'); add('len', 0.3048, 'ft', 'foot', 'feet', "'"); add('len', 0.9144, 'yd', 'yard', 'yards'); add('len', 1609.344, 'mi', 'mile', 'miles');
  add('mass', 0.001, 'mg'); add('mass', 1, 'g', 'gram', 'grams', 'gr'); add('mass', 1000, 'kg', 'kilo', 'kilos', 'kilogram', 'kilograms');
  add('mass', 28.349523125, 'oz', 'ounce', 'ounces'); add('mass', 453.59237, 'lb', 'lbs', 'pound', 'pounds'); add('mass', 6350.29318, 'st', 'stone', 'stones');
  add('vol', 1, 'ml', 'milliliter', 'milliliters', 'millilitre', 'millilitres'); add('vol', 10, 'cl'); add('vol', 100, 'dl');
  add('vol', 1000, 'l', 'liter', 'liters', 'litre', 'litres'); add('vol', 4.92892, 'tsp', 'teaspoon', 'teaspoons'); add('vol', 14.7868, 'tbsp', 'tablespoon', 'tablespoons');
  add('vol', 236.588, 'cup', 'cups'); add('vol', 29.5735, 'floz', 'fluidounce', 'fluidounces'); add('vol', 473.176, 'pt', 'pint', 'pints');
  add('vol', 946.353, 'qt', 'quart', 'quarts'); add('vol', 3785.41, 'gal', 'gallon', 'gallons');
  add('speed', 1 / 3.6, 'km/h', 'kmh', 'kph'); add('speed', 0.44704, 'mph'); add('speed', 1, 'm/s'); add('speed', 0.514444, 'kn', 'knot', 'knots');
  for (const [k, n] of [['c', 'celsius'], ['f', 'fahrenheit'], ['k', 'kelvin']]) { u[k] = u[`°${k}`] = u[n] = u[`degrees${n}`] = { dim: 'temp', t: k }; }
  return u;
})();
const CALC_UNIT_SHOW = { floz: 'fl oz', '"': 'in', "'": 'ft' };
/** A number as typed: "1,200.5", "1.200,5" and "3,5" (a decimal comma) too. NaN when it is not one. */
function calcNum(s) {
  s = String(s).trim();
  if (!/^[\d.,]+$/.test(s) || !/\d/.test(s)) return NaN;
  const c = s.lastIndexOf(','), d = s.lastIndexOf('.');
  if (c >= 0 && d >= 0) s = c > d ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
  else if (c >= 0) s = /^\d{1,3}(,\d{3})+$/.test(s) ? s.replace(/,/g, '') : (s.split(',').length === 2 ? s.replace(',', '.') : 'x');
  return s.split('.').length > 2 ? NaN : +s;
}
const calcUnitKey = (s) => s.toLowerCase().replace(/\s+/g, '').replace(/\.$/, '');
function calcUnit(s) {
  const k = s.toLowerCase().replace(/\s+/g, '').replace(/\.$/, '');
  return CALC_UNITS[k] || CALC_UNITS[k.replace(/^degrees?/, 'degrees')] || CALC_UNITS[k.replace(/^degrees?/, '')] || null;
}
function calcTemp(v, from, to) {
  const c = from === 'c' ? v : from === 'f' ? (v - 32) * 5 / 9 : v - 273.15;
  return to === 'c' ? c : to === 'f' ? c * 9 / 5 + 32 : c + 273.15;
}
/** A result for the eye ("1,234.5") and for the clipboard ("1234.5"). */
function calcShow(v, digits = 10) {
  const r = Number(Number(v.toPrecision(12)).toFixed(digits));
  return { text: r.toLocaleString([], { maximumFractionDigits: digits }), copy: String(r) };
}
/** "350f in c": {value, text, copy, note} or null; a currency needs the rates (S.rates): {need: 'rates'} until then. */
function calcConvert(q) {
  const m = q.trim().match(/^([$€£¥₹₩]?)\s*(-?[\d.,]+)\s*([a-z°"'/.$€£¥₹₩][a-z°/. ]*?)?\s+(?:in|to|as|into|=|->|→)\s+([a-z°"'/.$€£¥₹₩][a-z°/. ]*?)\s*$/i);
  if (!m) return null;
  const v = calcNum(m[2]);
  if (!isFinite(v)) return null;
  const fromTxt = (m[1] || m[3] || '').trim(), toTxt = m[4].trim();
  const cur = (s) => { const k = s.toLowerCase(); return CALC_SYMBOLS[k] || CALC_SYMBOLS[s] || (/^[a-z]{3}$/i.test(s) ? s.toUpperCase() : null); };
  const uf = calcUnit(fromTxt), ut = calcUnit(toTxt);
  if (uf && ut && uf.dim === ut.dim) {
    const out = uf.dim === 'temp' ? calcTemp(v, uf.t, ut.t) : v * uf.f / ut.f;
    const unit = (s, x) => (x.dim === 'temp' ? `°${x.t.toUpperCase()}` : CALC_UNIT_SHOW[calcUnitKey(s)] || s.toLowerCase());
    const shown = calcShow(out, uf.dim === 'temp' ? 1 : 4);
    return { ...shown, text: `${shown.text} ${unit(toTxt, ut)}`, note: `${calcShow(v, 4).text} ${unit(fromTxt, uf)}` };
  }
  const cf = cur(fromTxt), ct = cur(toTxt);
  if (!cf || !ct || uf || ut) return null;
  if (!S.rates) return { need: 'rates' };
  const r = S.rates.rates || {};
  if (!r[cf] || !r[ct]) return null;
  const out = v / r[cf] * r[ct];
  const fmt = (x, c) => { try { return new Intl.NumberFormat([], { style: 'currency', currency: c }).format(x); } catch { return `${calcShow(x, 2).text} ${c}`; } };
  return { text: fmt(out, ct), copy: out.toFixed(2), note: `${fmt(v, cf)} · rate of ${S.rates.date || 'today'}` };
}
/** "15% of 84", "(1+2)*3", "84 + 15%", "2^10", "sqrt(2)": {text, copy, note} or null. */
function calcSum(q) {
  let s = q.trim();
  const forced = s.startsWith('=');
  if (forced) s = s.slice(1);
  s = s.replace(/×/g, '*').replace(/÷/g, '/').replace(/−/g, '-').replace(/(\d)\s*x\s*(?=[\d(.])/gi, '$1*');
  s = s.replace(/%\s*of\b/gi, '%*');
  if (!/^[\d\s.,+\-*/^%()]+$|sqrt|pi/i.test(s) || !/\d/.test(s)) return null;
  if (!/[+\-*/^%]|sqrt/i.test(s.replace(/^\s*-/, ''))) return null;  // a lone number is not a sum
  if (!forced && !/\s/.test(s) && !/[+*^%()]|sqrt/i.test(s)) return null;  // 555-1234, 24/12, 2026-11-20: not sums
  const toks = s.match(/\d[\d.,]*|\.\d+|sqrt|pi|[+\-*/^%()]|\S/gi) || [];
  let i = 0;
  const peek = () => toks[i], next = () => toks[i++];
  // each level returns {v, pct}: pct marks "15%", which a + or - takes as a share of what comes before it
  function expr() {
    let a = term();
    while (peek() === '+' || peek() === '-') {
      const op = next(), b = term();
      const bv = b.pct ? a.v * b.v : b.v;
      a = { v: op === '+' ? a.v + bv : a.v - bv };
    }
    return a;
  }
  function term() {
    let a = power();
    while (peek() === '*' || peek() === '/') {
      const op = next(), b = power();
      a = { v: op === '*' ? a.v * b.v : a.v / b.v };
    }
    return a;
  }
  function power() {
    const a = unary();
    if (peek() === '^') { next(); const b = power(); return { v: Math.pow(a.v, b.v) }; }
    return a;
  }
  function unary() {
    if (peek() === '-') { next(); const a = unary(); return { v: -a.v, pct: a.pct }; }
    if (peek() === '+') { next(); return unary(); }
    let a = primary();
    while (peek() === '%') { next(); a = { v: a.v / 100, pct: true }; }
    return a;
  }
  function primary() {
    const t = next();
    if (t === undefined) throw new Error('end');
    if (t === '(') { const a = expr(); if (next() !== ')') throw new Error(')'); return { v: a.v }; }
    if (/^sqrt$/i.test(t)) { const a = primary(); return { v: Math.sqrt(a.v) }; }
    if (/^pi$/i.test(t)) return { v: Math.PI };
    const v = calcNum(t);
    if (!isFinite(v)) throw new Error(t);
    return { v };
  }
  try {
    const r = expr();
    if (i !== toks.length || !isFinite(r.v)) return null;
    return calcShow(r.v);
  } catch { return null; }
}
/** What the box shows for this text: a conversion or a sum, else null. */
function calcOf(q) {
  if (q.length > 120) return null;
  return calcConvert(q) || calcSum(q);
}
async function calcRates(again) {
  if (S.rates || S.ratesAsked) return;
  S.ratesAsked = true;
  try { S.rates = await api('api/rates'); again(); } catch (e) { S.ratesAsked = false; toast(e.message || 'No exchange rates'); }
}
async function calcCopy(c) {
  try { await navigator.clipboard.writeText(c.copy); toast(`Copied ${c.copy}`); } catch { toast(c.copy); }
}

/* Settings: the tabs, Account and Display, the home page (the weather, Home Assistant), and the suite's panel. */
import * as frame from '../../api/auth/frame.js';
import { accountUi, confirmDialog, fail, fld, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, dragSort, S } from './core.js';
import { setBookmarkSettings } from './bookmarks.js';
import { HA_ICONS, haIcon } from './homeassistant.js';
import { onRoute } from './main.js';
import { drawUser, setTheme } from './shell.js';
import { setTrmnl } from './trmnl.js';

// ------------------------------------------------------------------ settings
export async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'], ['bookmarks', 'Bookmarks'], ['trmnl', 'TRMNL'], ...(adm ? [['weather', 'Home page']] : []),
    ...(S.user.suiteAdmin ? [['people', 'People'], ['apps', 'Apps'], ['servers', 'Servers'], ['keys', 'Keys']] : [])];
  if (!tabs.some(([k]) => k === r.tab)) r.tab = 'account';
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, bookmarks: setBookmarkSettings, trmnl: setTrmnl, weather: setHome, people: setSuite, apps: setSuite, servers: setSuite, keys: setSuite }[r.tab] || setAccount)(body, r);
}

async function setAccount(el) {
  await (await accountUi()).mountAccount(el, { toast, syncOnly: 'Bookmark sync only', onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
}
async function setDisplay(el) {
  const ui = await accountUi();
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings?.theme || 'system', setTheme)));
}

// ------------------------------------------------------------------ settings › the home page: the weather, Home Assistant (admins)
async function setHome(el) {
  const got = await api('api/home/settings');
  const strip = h('select', { class: 't', onchange: async () => { try { await api('api/home/settings', { method: 'POST', json: { photoStrip: strip.value } }); toast('Saved'); } catch (e) { fail(e); } } }, [['rediscover', 'Rediscover: photos at random'], ['onthisday', 'On this day (at random when there are none)'], ['off', 'Off']].map(([v, t]) => h('option', { value: v, selected: v === got.photoStrip ? true : null }, t)));
  el.append(h('div', { class: 'box' }, h('h2', null, icon('apps'), 'Home page'),
    h('p', { class: 'muted' }, 'The default for everyone. Each person can change it in Customize.'),
    h('div', { class: 'grid' }, fld('Photo strip under the tiles (ioPix)', strip))));
  await setWeather(el);
  await setHomeAssistant(el);
}

async function setWeather(el) {
  const s = await api('api/weather/settings');
  const key = h('input', { class: 't', type: 'password', placeholder: s.hasKey ? '(kept)' : 'API key from developer.accuweather.com', autocomplete: 'off', onchange: async () => { if (key.value.trim() && await save({ key: key.value.trim() })) { key.value = ''; key.placeholder = '(kept)'; } } });
  const units = h('select', { class: 't', style: 'width:auto', onchange: () => save({ units: units.value }) }, [['metric', '°C, km/h'], ['imperial', '°F, mph']].map(([v, l]) => h('option', { value: v, selected: v === s.units ? true : null }, l)));
  const q = h('input', { class: 't', placeholder: 'City, e.g. Boston or Antwerp' });
  const found = h('div', { class: 'found' });
  const where = h('p', null, s.locationKey ? `Place: ${s.locationName || s.locationKey}` : 'No place chosen yet.');
  const save = async (body) => { try { const r = await api('api/weather/settings', { method: 'POST', json: body }); toast('Saved'); return r; } catch (e) { fail(e); return null; } };
  const search = async () => {
    found.replaceChildren(h('span', { class: 'muted small' }, 'Looking…'));
    try {
      const r = await api(`api/weather/search?${new URLSearchParams({ q: q.value.trim(), ...(key.value.trim() ? { key: key.value.trim() } : {}) })}`);
      found.replaceChildren(...(r.items.length ? r.items.map((p) => h('button', { class: 'pillbtn noic', onclick: async () => {
        const name = [p.name, p.region, p.country].filter(Boolean).join(', ');
        if (await save({ ...(key.value.trim() ? { key: key.value.trim() } : {}), locationKey: p.key, locationName: name })) { where.textContent = `Place: ${name}`; key.value = ''; key.placeholder = '(kept)'; found.replaceChildren(); }
      } }, [p.name, p.region, p.country].filter(Boolean).join(', '))) : [h('span', { class: 'muted small' }, 'Nothing found')]));
    } catch (e) { found.replaceChildren(h('span', { class: 'err' }, e.message)); }
  };
  q.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); search(); } };
  el.append(h('div', { class: 'box' }, h('h2', null, icon('cloud'), 'Weather'),
    h('p', { class: 'muted' }, 'From AccuWeather. A free key from developer.accuweather.com is enough.'),
    h('div', { class: 'grid' }, fld('API key', key), fld('Units', units)),
    s.hasKey ? h('p', null, h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('Remove the key', 'Remove the AccuWeather key? The widget disappears from the page.', 'Remove', true)) { await save({ key: '' }); onRoute(); } } }, 'Remove the key')) : null),
  h('div', { class: 'box' }, h('h2', null, icon('cloud'), 'Place'), where,
    h('div', { class: 'multi' }, q, h('button', { class: 'pillbtn noic', onclick: search }, 'Find')), found,
    h('p', { class: 'muted small' }, 'Type a city and pick it from the list.')));
}

/** Settings › Home Assistant: the address and token, a test, and the entities the page shows, each with its name, whether
    a tap may switch it, whether it goes on the wall, and the state that needs attention. */
async function setHomeAssistant(el) {
  const s = await api('api/ha/settings');
  const saveConn = async () => { if (await save(conn())) { if (tok.value.trim()) s.hasToken = true; tok.value = ''; tok.placeholder = s.hasToken ? '(kept)' : tok.placeholder; if (s.hasToken) test(); } };
  const url = h('input', { class: 't', type: 'url', value: s.url || '', placeholder: 'http://homeassistant.local:8123', autocomplete: 'off', onchange: () => saveConn() });
  const tok = h('input', { class: 't', type: 'password', placeholder: s.hasToken ? '(kept)' : 'Long-lived access token', autocomplete: 'off', onchange: () => saveConn() });
  const result = h('span', { class: 'muted small' });
  const conn = () => ({ url: url.value.trim(), ...(tok.value.trim() ? { token: tok.value.trim() } : {}) });
  const save = async (body) => { try { const r = await api('api/ha/settings', { method: 'POST', json: body }); toast('Saved'); return r; } catch (e) { fail(e); return null; } };
  const test = async () => {
    result.className = 'muted small'; result.textContent = 'Asking…';
    try { const r = await api('api/ha/test', { method: 'POST', json: conn() }); result.className = 'small ok'; result.textContent = `${r.name} · Home Assistant ${r.version || ''} · ${r.entities} entities`; } catch (e) { result.className = 'small err'; result.textContent = e.message; }
  };
  // the entities picked, as rows
  let items = (s.entities || []).map((e) => ({ ...e }));
  const list = h('div', { class: 'halist' });
  const persist = async () => { const r = await save({ entities: items }); if (r) { items = r.entities.map((e) => ({ ...e })); drawList(); } };
  const drawList = () => { list.replaceChildren(h('div', { class: 'harow head' }, h('span'), h('span', null, 'Entity'), h('span', null, 'Shown as'), h('span', { title: 'A tap on the card switches it (editors and admins)' }, 'Control'), h('span', { title: 'On the wall display' }, 'Wall'), h('span', { title: 'Needs attention when its state is this (on, open, unlocked…); empty: never' }, 'Alert when'), h('span')),
    ...items.map((e, i) => h('div', { class: 'harow', 'data-id': e.id },
      h('button', { class: 'iconbtn grip', title: 'Drag to reorder', 'aria-label': 'Drag to reorder' }, icon('grip', 's')),
      h('span', { class: 'haid', title: e.id }, e.id),
      h('input', { class: 't', value: e.name || '', placeholder: 'Its own name', onchange: (ev) => { e.name = ev.target.value.trim(); persist(); } }),
      h('input', { type: 'checkbox', checked: e.control, onchange: (ev) => { e.control = ev.target.checked; persist(); } }),
      h('input', { type: 'checkbox', checked: e.wall, onchange: (ev) => { e.wall = ev.target.checked; persist(); } }),
      h('input', { class: 't', value: e.alert || '', placeholder: '–', onchange: (ev) => { e.alert = ev.target.value.trim().toLowerCase(); persist(); } }),
      h('span', { class: 'bmtools' }, h('button', { class: 'iconbtn', title: 'Remove', onclick: () => { items.splice(i, 1); persist(); } }, icon('close', 's'))))),
    ...(items.length ? [] : [h('p', { class: 'muted small' }, 'Nothing picked yet: find entities below and add them.')]));
    // reorder by dragging the handle (or ArrowUp / ArrowDown on it), as in the Bookmarks page
    for (const g of list.querySelectorAll('.grip')) dragSort(g, g.closest('.harow'), { root: list, lists: () => [list], items: '.harow:not(.head)', sorting: 'sorting-rows',
      done: () => { const by = Object.fromEntries(items.map((e) => [e.id, e])); items = [...list.querySelectorAll('.harow[data-id]')].map((r) => by[r.dataset.id]).filter(Boolean); persist(); } });
  };
  drawList();
  // the picker: a search among every entity Home Assistant has
  const q = h('input', { class: 't', placeholder: 'Find an entity: kitchen, garage, temperature…' });
  const found = h('div', { class: 'found' });
  const find = async () => {
    if (!q.value.trim()) { found.replaceChildren(); return; }
    found.replaceChildren(h('span', { class: 'muted small' }, 'Looking…'));
    try {
      const r = await api(`api/ha/search?${new URLSearchParams({ q: q.value.trim(), n: 30 })}`);
      const have = new Set(items.map((e) => e.id));
      found.replaceChildren(...(r.items.length ? r.items.map((t) => h('button', { class: 'pillbtn', disabled: have.has(t.id) ? true : null, title: t.id, onclick: () => { items.push({ id: t.id, name: '', control: !!HA_ICONS[t.domain] && !['climate', 'media_player', 'person', 'device_tracker', 'weather', 'camera'].includes(t.domain), wall: false, alert: '' }); persist(); find(); } },
        icon(haIcon(t), 's'), `${t.name}`, h('span', { class: 'muted small' }, ` ${t.text || t.state}`))) : [h('span', { class: 'muted small' }, 'Nothing found')]));
    } catch (e) { found.replaceChildren(h('span', { class: 'err' }, e.message)); }
  };
  q.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); find(); } };
  const builtin = h('input', { type: 'checkbox', checked: s.builtinAlerts, onchange: async (e) => { await save({ builtinAlerts: e.target.checked }); } });
  el.append(h('div', { class: 'box' }, h('h2', null, icon('home'), 'Home Assistant'),
    h('p', { class: 'muted' }, 'For the Home card, the wall display and the search box. Make a token in Home Assistant under your profile › Security › Long-lived access tokens.'),
    h('div', { class: 'grid' }, fld('Address', url), fld('Access token', tok)),
    h('p', { class: 'multi' }, h('button', { class: 'pillbtn noic', onclick: test }, 'Test'),
      s.hasToken ? h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('Remove the token', 'Remove the Home Assistant token? The Home card disappears from the page.', 'Remove', true)) { await save({ token: '' }); onRoute(); } } }, 'Remove the token') : null,
      result)),
  h('div', { class: 'box' }, h('h2', null, icon('tune'), 'On the page'),
    h('p', { class: 'muted' }, 'The Home card, in this order. Control: a tap switches it, for editors and admins (a viewer sees the state). Wall: on the wall display too. Alert when: the state to point out (on, open, unlocked…).'),
    list,
    h('div', { class: 'multi' }, q, h('button', { class: 'pillbtn noic', onclick: find }, 'Find')), found,
    h('label', { class: 'check' }, builtin, 'Also point out leak, smoke, gas and CO sensors, problems and batteries at 15% or under')));
}

// ------------------------------------------------------------------ settings › security and global settings (suite admins)
/* Everything in the Shared ioSuite database, for the whole suite: Security (people and their role in every app, roles,
   app passwords, sign-in at the proxy), Apps, Servers and Keys. The same panel in every io app,
   served by iosuite_shared at /api/suite-admin/ui.js. */
function setSuite(el, r) { return frame.suitePanel(el, r, 'err'); }

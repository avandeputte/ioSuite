/* Home Assistant on the start page: the Home card and the alerts. */
import { dialog, fail, icon } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, quiet, S } from './core.js';
import { wgHead } from './tiles.js';

// ------------------------------------------------------------------ Home Assistant: the Home card, the alerts
/** The weather widget: the conditions now (with "Rain from 15:00" when the next hours bring some), and the days
    ahead. A click on the conditions opens the next 12 hours. Hidden until an admin sets it up. again: a refresh, which
    keeps what it shows when the server does not answer. */
/* The entities an admin picked (Settings › Home Assistant), each with its state; a tap on one the admin lets the page
   control toggles it (a light, a switch, a lock, a cover, a scene…). Above the tiles, a line for what needs attention
   (a leak, smoke, a low battery, a door that should be closed). The server asks Home Assistant; the browser never does.
   The card redraws every minute on its own, on top of the page's live refresh. */
export const HA_ICONS = { light: 'bulb', switch: 'power', input_boolean: 'power', fan: 'fan', lock: 'lock', cover: 'blind', scene: 'play', script: 'play', automation: 'play', button: 'play', input_button: 'play',
  climate: 'thermo', media_player: 'play', person: 'person', device_tracker: 'person', vacuum: 'home', weather: 'cloud', camera: 'wall', siren: 'warn' };
const HA_CLASS_ICONS = { door: 'door', garage_door: 'door', window: 'door', opening: 'door', temperature: 'thermo', humidity: 'cloud', battery: 'battery', power: 'bolt', energy: 'bolt', voltage: 'bolt', current: 'bolt',
  motion: 'person', occupancy: 'person', presence: 'person', moisture: 'warn', smoke: 'warn', gas: 'warn', carbon_monoxide: 'warn', problem: 'warn', safety: 'warn', lock: 'lock', illuminance: 'bulb' };
export function haIcon(t) {
  if (t.domain === 'lock') return t.on ? 'unlock' : 'lock';
  return HA_CLASS_ICONS[t.class] || HA_ICONS[t.domain] || (t.domain === 'binary_sensor' ? 'check' : 'home');
}
/** Home Assistant's own page for an entity: its device (where a thermostat's settings are), or its history when it
    belongs to no device. */
export const haLink = (t) => `${(S.ha && S.ha.url) || ''}${t.device ? `/config/devices/device/${encodeURIComponent(t.device)}` : `/history?entity_id=${encodeURIComponent(t.id)}`}`;
/** toggle | on | off, by way of the server; the entity's new state, or null (a toast says why). */
export async function haAct(id, action) {
  try { return await api(`api/ha/${encodeURIComponent(id)}/${action}`, { method: 'POST' }); } catch (e) { fail(e); return null; }
}
const haTile = (t) => {
  const kids = [icon(haIcon(t), 's'), h('span', { class: 'hbody' }, h('span', { class: 'hname' }, t.name), h('span', { class: 'hstate small' }, t.text || t.state))];
  if (!t.control) return h('a', { class: `hatile${t.on ? ' on' : ''}${t.state === 'unavailable' || t.state === 'missing' ? ' off' : ''}`, href: haLink(t), title: `${t.id} · ${t.device ? 'its device' : 'its history'} in Home Assistant`, target: '_blank', rel: 'noreferrer' }, kids);
  if (HA_POPUPS[t.domain]) {  // a thermostat, a cover: a popup with its controls instead of a toggle
    const b = h('button', { class: `hatile ctl${t.on ? ' on' : ''}`, title: `${t.id} · tap for its controls` }, kids);
    b.onclick = () => haPopup(t, (r) => { if (b.isConnected) b.replaceWith(haTile({ ...t, ...r, control: t.control })); });
    return b;
  }
  const b = h('button', { class: `hatile ctl${t.on ? ' on' : ''}`, title: `${t.id} · tap to ${{ scene: 'run', script: 'run', button: 'press', input_button: 'press', automation: 'run' }[t.domain] || (t.on ? 'turn off' : 'turn on')}`, 'aria-pressed': t.on == null ? null : String(!!t.on) }, kids);
  b.onclick = async () => {
    b.classList.add('busy');
    const card = b.closest('.homecard');
    const r = await haAct(t.id, 'toggle');
    if (r && b.isConnected) b.replaceWith(haTile({ ...t, ...r, control: t.control })); else b.classList.remove('busy');
    // a device that reports back late (Zigbee, Z-Wave, a cloud bulb): the card asks again in a few seconds
    if (card) setTimeout(() => { if (card.isConnected && !document.hidden) drawHomeCard(card, true); }, 4000);
  };
  return b;
};
/* The popups: a thermostat (target temperature, mode, fan, preset) and a cover (open, stop, close, a position). Each
   change goes to /api/ha/<entity>/set and the popup redraws from the answer; `onChange` gets it too, for the tile. */
export const HA_POPUPS = { climate: true, cover: true };
const haWord = (m) => ({ heat_cool: 'Heat · cool', fan_only: 'Fan', not_home: 'Away' })[m] || (m ? m.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) : '');
async function haSet(id, body) {
  try { return await api(`api/ha/${encodeURIComponent(id)}/set`, { method: 'POST', json: body }); } catch (e) { fail(e); return null; }
}
export function haPopup(t, onChange) {
  const body = h('div', { class: 'hapop' });
  let cur = t, busy = false;
  const send = async (payload) => {
    if (busy) return;
    busy = true; body.classList.add('busy');
    const r = await haSet(cur.id, payload);
    busy = false; body.classList.remove('busy');
    if (r && r.id) { cur = { ...cur, ...r }; onChange(r); draw(); }
  };
  const seg = (options, value, pick, label) => h('div', { class: 'seg', role: 'group', 'aria-label': label }, options.map((o) => h('button', { class: o === value ? 'on' : '', onclick: () => pick(o) }, label(o))));
  const draw = () => {
    const kids = [];
    if (cur.domain === 'climate' && cur.climate) {
      const c = cur.climate, step = c.step || 0.5, dec = step < 1 ? 1 : 0;
      const fmt = (v) => (v == null ? '–' : `${v.toFixed(dec)}${c.unit || '°'}`);
      const off = c.mode === 'off';
      const targetRow = (label, key, value, low, high) => h('div', { class: 'hatarget' }, label ? h('span', { class: 'muted small' }, label) : null,
        h('button', { class: 'iconbtn round', title: 'Lower', disabled: off || value == null || value - step < c.min ? true : null, onclick: () => send(key === 'temperature' ? { temperature: +(value - step).toFixed(2) } : { low: key === 'low' ? +(value - step).toFixed(2) : low, high: key === 'high' ? +(value - step).toFixed(2) : high }) }, '−'),
        h('span', { class: 'hatemp' }, fmt(value)),
        h('button', { class: 'iconbtn round', title: 'Raise', disabled: off || value == null || value + step > c.max ? true : null, onclick: () => send(key === 'temperature' ? { temperature: +(value + step).toFixed(2) } : { low: key === 'low' ? +(value + step).toFixed(2) : low, high: key === 'high' ? +(value + step).toFixed(2) : high }) }, '+'));
      kids.push(h('div', { class: 'hanow' }, h('span', { class: 'hacur' }, fmt(c.current)), h('span', { class: 'muted small' }, [c.action ? haWord(c.action) : haWord(c.mode), c.humidity != null ? `${c.humidity}% humidity` : null].filter(Boolean).join(' · '))));
      if (c.low != null && c.high != null && c.target == null) kids.push(targetRow('Low', 'low', c.low, c.low, c.high), targetRow('High', 'high', c.high, c.low, c.high));
      else kids.push(targetRow('', 'temperature', c.target));
      if (c.modes.length) kids.push(h('h3', null, 'Mode'), seg(c.modes, c.mode, (m) => send({ mode: m }), haWord));
      if (c.fans.length) kids.push(h('h3', null, 'Fan'), seg(c.fans, c.fan, (m) => send({ fan: m }), haWord));
      if (c.presets.length) kids.push(h('h3', null, 'Preset'), seg(c.presets, c.preset, (m) => send({ preset: m }), haWord));
    } else if (cur.domain === 'cover' && cur.cover) {
      const c = cur.cover;
      kids.push(h('div', { class: 'hanow' }, h('span', { class: 'hacur' }, cur.text || cur.state), c.position != null ? h('span', { class: 'muted small' }, `${c.position}% open`) : null),
        h('div', { class: 'habtns' },
          c.canOpen ? h('button', { class: 'pillbtn', disabled: !c.moving && cur.state === 'open' ? true : null, onclick: () => send({ action: 'open' }) }, icon('up', 's'), 'Open') : null,
          c.canStop ? h('button', { class: 'pillbtn noic', onclick: () => send({ action: 'stop' }) }, 'Stop') : null,
          c.canClose ? h('button', { class: 'pillbtn', disabled: !c.moving && cur.state === 'closed' ? true : null, onclick: () => send({ action: 'close' }) }, icon('down', 's'), 'Close') : null));
      if (c.canPosition) {
        const range = h('input', { type: 'range', min: 0, max: 100, step: 5, value: c.position == null ? 50 : c.position, 'aria-label': 'Position', onchange: (e) => send({ position: +e.target.value }) });
        kids.push(h('h3', null, 'Position'), h('div', { class: 'harange' }, h('span', { class: 'muted small' }, 'Closed'), range, h('span', { class: 'muted small' }, 'Open')));
      }
    } else kids.push(h('p', { class: 'muted' }, cur.text || cur.state));
    kids.push(h('p', { class: 'small' }, h('a', { class: 'lnk', href: haLink(cur), target: '_blank', rel: 'noreferrer' }, 'More in Home Assistant')));
    body.replaceChildren(...kids);
  };
  draw();
  // the thing moves while the popup is open (a cover closing, a device reporting back): the stream brings it, else a poll
  const take = (d) => {
    const fresh = (d.items || []).find((x) => x.id === cur.id);
    if (fresh && body.isConnected && !busy && JSON.stringify({ a: fresh.state, b: fresh.climate, c: fresh.cover }) !== JSON.stringify({ a: cur.state, b: cur.climate, c: cur.cover })) { cur = { ...cur, ...fresh }; onChange(fresh); draw(); }
  };
  const off = haSubscribe(take);
  const timer = S.haStream ? 0 : setInterval(async () => {
    if (!body.isConnected) { clearInterval(timer); return; }
    if (busy || document.hidden) return;
    let d; try { d = await api('api/ha'); } catch { return; }
    take(d);
  }, 3000);
  dialog(cur.name, body, [{ label: 'Done', value: true, primary: true }]).then(() => { off(); if (timer) clearInterval(timer); });
}

/* Changes from Home Assistant as they happen: one EventSource per view on /api/ha/events (the server holds the
   websocket to Home Assistant and sends the Home card anew when something in it changes); whoever draws from it
   (the card, the wall's sensors, an open popup) subscribes here. The browser reconnects it by itself. */
const haListeners = new Set();
export function haSubscribe(fn) {
  haListeners.add(fn);
  if (!S.haStream && window.EventSource) {
    S.haStream = new EventSource('api/ha/events');
    S.haStream.onmessage = (e) => { let d; try { d = JSON.parse(e.data); } catch { return; } S.ha = d.enabled ? d : false; for (const f of [...haListeners]) { try { f(d); } catch { /* one listener's problem */ } } };
  }
  return () => { haListeners.delete(fn); };
}
export function haStreamStop() {
  haListeners.clear();
  if (S.haStream) { S.haStream.close(); S.haStream = null; }
}
export async function drawHomeCard(el, again = false) {
  if (!el.haLive) {  // the first draw: from here on the stream redraws the card as Home Assistant changes
    el.haLive = true;
    const off = haSubscribe((d) => { if (!el.isConnected) { off(); return; } renderHomeCard(el, d); });
  }
  let d;
  try { d = await api('api/ha'); } catch (e) { if (!again) { el.hidden = false; el.replaceChildren(h('div', { class: 'muted small' }, e.message)); } return; }
  if (!el.isConnected) return;
  renderHomeCard(el, d);
}
function renderHomeCard(el, d) {
  S.ha = d.enabled ? d : false;
  if (!d.enabled) { el.hidden = true; el.replaceChildren(); quiet(el, true, true); return; }  // no Home Assistant set up: no Home card at all (Settings › Home Assistant adds it)
  el.hidden = false;
  // a block of the person's own grid can be a few of the entities, in its own order, under its own name (el.haOpts:
  // {title, entities}): a room. Its alerts are those of its entities
  const o = el.haOpts || {};
  if (o.entities && o.entities.length) {
    const at = (x) => o.entities.indexOf(x.id);
    d = { ...d, items: (d.items || []).filter((x) => at(x) >= 0).sort((a, b) => at(a) - at(b)), alerts: (d.alerts || []).filter((x) => at(x) >= 0) };
  }
  quiet(el, !(d.items || []).length && !(d.alerts || []).length);
  const title = wgHead(o.title || d.name || 'Home', null);
  title.append(h('a', { class: 'muted', href: d.url, title: d.url, target: '_blank', rel: 'noreferrer' }, 'Home Assistant'));
  if (d.error) { el.replaceChildren(title, h('div', { class: 'muted small' }, d.error)); return; }
  // what needs attention (a leak, a problem, a low battery, a chosen entity's "alert when"), inside the card above its tiles
  const al = d.alerts || [];
  el.replaceChildren(...[title,
    al.length ? h('div', { class: 'alerts' }, al.map((a) => h('a', { class: 'alert', href: haLink(a), target: '_blank', rel: 'noreferrer', title: a.id }, icon('warn', 's'), h('b', null, a.name), h('span', null, a.text)))) : null,
    d.items.length ? h('div', { class: 'hatiles' }, d.items.map(haTile))
      : h('div', { class: 'muted small' }, S.user.role === 'admin' ? ['No entities picked yet: ', h('a', { class: 'lnk', href: '#/settings/weather' }, 'choose some')] : 'No entities picked yet.')].filter(Boolean));
  // without the stream (an old browser), its own minute: a light switched elsewhere shows here soon
  clearTimeout(el.haTimer);
  if (!S.haStream) el.haTimer = setTimeout(() => { if (el.isConnected && !document.hidden) drawHomeCard(el, true); }, 60 * 1000);
}

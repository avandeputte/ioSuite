/* Settings › TRMNL: the suite on an e-ink display. */
import { confirmDialog, fail, fld, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, pad2, S } from './core.js';

// ------------------------------------------------------------------ settings › TRMNL (the suite on an e-ink display)
/** Settings › TRMNL: the suite on a TRMNL e-ink display. Each screen is a TRMNL private plugin, downloaded as the zip
    TRMNL's Import new takes. Two ways for its data to get there: TRMNL reads the start page (a TRMNL server of your
    own inside the network, or TRMNL's cloud through Cloudflare Access), with an app password typed in TRMNL's form;
    or the start page sends it to the plugin's webhook (TRMNL's cloud, with nothing opened up), which needs that
    webhook's address here. */
export async function setTrmnl(el) {
  let d;
  try { d = await api('api/trmnl'); } catch (e) { fail(e); return; }
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  const when = (t) => new Date(t * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
  const hhmm = (v) => { const [a, b] = v.split(':').map(Number); return d.clock === 24 ? v : `${a % 12 || 12}${b ? `:${pad2(b)}` : ''} ${a < 12 ? 'AM' : 'PM'}`; };
  const clock = h('select', { class: 't', onchange: () => save({ clock: +clock.value }) }, [[12, '12 hours (6:00 PM)'], [24, '24 hours (18:00)']].map(([v, t]) => h('option', { value: v, selected: v === d.clock ? true : null }, t)));
  const check = (label, on, set, hint) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: on ? true : null, onchange: (e) => set(e.target.checked) }),
    h('span', null, label, hint ? h('span', { class: 'muted small' }, ` ${hint}`) : null));
  // one line that opens to its details: a screen's plugin, a device
  const open = {};
  function item(key, head, body, redraw) {
    const on = !!open[key];
    return h('div', { class: 'trmnl-item' + (on ? ' open' : '') },
      h('button', { class: 'trmnl-head', 'aria-expanded': String(on), onclick: () => { open[key] = !on; redraw(); } }, head, icon(on ? 'up' : 'down', 's')),
      on ? h('div', { class: 'trmnl-body' }, body()) : null);
  }
  async function save(b) {
    try { d = { ...d, ...await api('api/trmnl', { method: 'PUT', json: { tz, ...b } }) }; toast('Saved'); draw(); drawDevices(); } catch (e) { fail(e); }
  }
  // -- through TRMNL's own plugins: one line a screen, which opens to its downloads and its webhook
  const list = h('div', { class: 'trmnl-items' });
  function draw() {
    list.replaceChildren(...d.screens.map((x) => {
      const bad = x.sent && !x.sent.ok && x.sent.error;
      const st = bad ? h('span', { class: 'trmnl-state bad' }, 'Not sent') : x.push ? h('span', { class: 'trmnl-state on' }, x.sent && x.sent.at ? `Sent ${when(x.sent.at)}` : 'Sending') : null;
      return item(`s-${x.key}`, [h('b', null, x.name), h('span', { class: 'trmnl-about muted small' }, x.about), st], () => {
        const hook = h('input', { class: 't', type: 'url', placeholder: x.push ? '(kept: paste another to change it)' : 'https://trmnl.com/api/custom_plugins/…', autocomplete: 'off' });
        return [
          h('div', { class: 'btns left' }, h('span', { class: 'muted small' }, 'The plugin:'),
            h('a', { class: 'pillbtn', href: `api/trmnl/${x.key}/plugin.zip`, download: '' }, icon('download', 's'), 'For TRMNL to read'),
            h('a', { class: 'pillbtn', href: `api/trmnl/${x.key}/plugin.zip?mode=push`, download: '' }, icon('download', 's'), 'For the start page to send')),
          fld(x.push ? 'Sent to a TRMNL webhook' : 'TRMNL webhook (only to have the start page send it)', hook),
          bad ? h('p', { class: 'err small' }, `Not sent: ${x.sent.error}`) : null,
          h('div', { class: 'btns left' },
            h('button', { class: 'pillbtn primary noic', onclick: () => { const v = hook.value.trim(); if (v) save({ hooks: { [x.key]: v } }); } }, 'Save'),
            x.push ? h('button', { class: 'pillbtn noic', onclick: async () => {
              try { const r = await api(`api/trmnl/${x.key}/send`, { method: 'POST', json: {} }); x.sent = r; toast(r.ok ? 'Sent' : r.error); draw(); } catch (e) { fail(e); }
            } }, 'Send now') : null,
            x.push ? h('button', { class: 'pillbtn noic', onclick: () => save({ hooks: { [x.key]: '' } }) }, 'Stop sending') : null,
            h('span', { class: 'muted small' }, `TRMNL looks again every ${x.every >= 60 ? `${x.every / 60} hour${x.every > 60 ? 's' : ''}` : `${x.every} minutes`}.`))];
      }, draw);
    }));
    if (!d.screens.length) list.replaceChildren(h('p', { class: 'muted' }, 'None of the apps these screens show is in your suite yet.'));
  }
  // -- a TRMNL that asks the start page itself (iostart/trmnl/server.py): no TRMNL account, plugin or webhook
  const LAYOUT = { full: 'One screen', '1Lx1R': 'Two, side by side', '1Tx1B': 'Two, one above the other', '1Lx2R': 'One left, two right',
    '2Lx1R': 'Two left, one right', '2Tx1B': 'Two above, one below', '1Tx2B': 'One above, two below', '2x2': 'Four' };
  const EVERY = (sec) => (sec >= 86400 ? 'day' : sec >= 3600 ? `${sec / 3600} hour${sec > 3600 ? 's' : ''}` : `${sec / 60} minutes`);
  const GRAYS = { color: 'In color', 1: 'Black and white', 2: '4 grays', 4: '16 grays' };
  const BUTTON = { sleep: 'Sleeps until the morning', identify: 'Shows which screen it is', restart: 'Starts its turn over', back: 'Goes back one',
    hold: 'Stays on what it shows, or moves on again', send: 'Sends what it shows to your phone', wifi: 'Opens its Wi-Fi setup', none: 'Nothing' };
  const devs = h('div', { class: 'trmnl-items' });
  const shown = {};  // device id -> the playlist entry its picture shows
  const copy = (text) => h('button', { class: 'iconbtn', title: 'Copy', onclick: async () => { try { await navigator.clipboard.writeText(text); toast('Copied'); } catch { toast(text); } } }, icon('copy', 's'));
  function seen(t) {
    if (!t) return 'not seen yet';
    const m = Math.round((Date.now() / 1000 - t) / 60);
    return m < 2 ? 'seen just now' : m < 90 ? `seen ${m} minutes ago` : `seen ${when(t)}`;
  }
  function signal(r) { return r == null ? null : `signal ${r >= -60 ? 'strong' : r >= -72 ? 'good' : r >= -82 ? 'weak' : 'very weak'}`; }
  async function device(x, b, quiet) {
    try {
      const r = await api(`api/trmnl/devices/${x.id}`, { method: 'PUT', json: b });
      d.devices = d.devices.map((o) => (o.id === x.id ? r : o));
      if (!quiet) toast('Saved');
      drawDevices();
    } catch (e) { fail(e); }
  }
  function drawDevices() {
    const mine = d.screens.map((s) => s.key);
    const name = (k) => (d.screens.find((s) => s.key === k) || { name: k }).name;
    if (d.devices.length === 1 && open[`d-${d.devices[0].id}`] == null) open[`d-${d.devices[0].id}`] = true;
    devs.replaceChildren(...d.devices.map((x) => {
      const st = x.resetting ? h('span', { class: 'trmnl-state bad' }, 'Resets at its next look')
        : x.quietNow ? h('span', { class: 'trmnl-state' }, `Quiet until ${hhmm(x.quiet.to)}`)
          : x.hold ? h('span', { class: 'trmnl-state' }, 'Held') : x.battery != null && x.battery <= 15 && !x.charging ? h('span', { class: 'trmnl-state bad' }, 'Battery low') : null;
      const brief = [x.battery == null ? null : `battery ${x.battery}%${x.charging ? ', charging' : ''}`, seen(x.seen)].filter(Boolean).join(' · ');
      return item(`d-${x.id}`, [h('b', null, x.name), h('span', { class: 'trmnl-about muted small' }, brief), st], () => {
        const at = Math.min(shown[x.id] || 0, x.playlist.length - 1);
        const set = (l) => device(x, { playlist: l });
        const title = h('input', { class: 't', value: x.name, maxlength: 60, 'aria-label': 'Name', onchange: () => device(x, { name: title.value }) });
        const facts = [x.model, `${x.width} × ${x.height}`, signal(x.rssi), x.firmware ? `firmware ${x.firmware}` : null].filter(Boolean).join(' · ');
        const every = h('select', { class: 't', onchange: () => device(x, { refresh: +every.value }) }, d.refreshes.map((v) => h('option', { value: v, selected: v === x.refresh ? true : null }, EVERY(v))));
        const bits = x.canBits.length > 1 ? h('select', { class: 't', onchange: () => device(x, { bits: bits.value === 'color' ? 'color' : +bits.value }) }, x.canBits.map((v) => h('option', { value: v, selected: v === x.bits ? true : null }, GRAYS[v] || `${v} bits`))) : null;
        const rows = x.playlist.map((it, i) => {
          const places = (d.layouts.find((l) => l.key === it.layout) || { places: [] }).places;
          const lay = h('select', { class: 't', 'aria-label': 'Layout', onchange: () => {
            const n = d.layouts.find((l) => l.key === lay.value).places.length;
            const fill = it.screens.concat(mine.filter((k) => !it.screens.includes(k)), mine).slice(0, n);  // the ones not shown yet first
            shown[x.id] = i;
            set(x.playlist.map((o, j) => (j === i ? { layout: lay.value, screens: fill } : o)));
          } }, d.layouts.map((l) => h('option', { value: l.key, selected: l.key === it.layout ? true : null }, LAYOUT[l.key] || l.key)));
          const picks = places.map((_, j) => {
            const sel = h('select', { class: 't', 'aria-label': `Screen ${j + 1}`, onchange: () => {
              shown[x.id] = i;
              set(x.playlist.map((o, k) => (k === i ? { ...o, screens: o.screens.map((v, m) => (m === j ? sel.value : v)) } : o)));
            } }, mine.map((k) => h('option', { value: k, selected: k === it.screens[j] ? true : null }, name(k))));
            return sel;
          });
          const move = (to) => { const l = x.playlist.slice(); l.splice(to, 0, l.splice(i, 1)[0]); shown[x.id] = to; set(l); };
          return h('div', { class: 'trmnl-row' + (i === at ? ' on' : '') },
            h('button', { class: 'trmnl-nr', title: 'Show this one in the picture', onclick: () => { shown[x.id] = i; drawDevices(); } }, String(i + 1)),
            h('div', { class: 'trmnl-picks' }, lay, picks),
            h('button', { class: 'iconbtn', title: 'Earlier', disabled: i === 0 ? true : null, onclick: () => move(i - 1) }, icon('up', 's')),
            h('button', { class: 'iconbtn', title: 'Later', disabled: i === x.playlist.length - 1 ? true : null, onclick: () => move(i + 1) }, icon('down', 's')),
            h('button', { class: 'iconbtn', title: 'Take it out', disabled: x.playlist.length === 1 ? true : null, onclick: () => { shown[x.id] = Math.max(0, at - (i <= at ? 1 : 0)); set(x.playlist.filter((_, j) => j !== i)); } }, icon('close', 's')));
        });
        const add = h('button', { class: 'pillbtn', disabled: x.playlist.length >= 12 || !mine.length ? true : null, onclick: () => {
          const used = x.playlist.flatMap((o) => o.screens);
          shown[x.id] = x.playlist.length;
          set(x.playlist.concat([{ layout: 'full', screens: [mine.find((k) => !used.includes(k)) || mine[0]] }]));
        } }, icon('add', 's'), 'Add');
        // quiet hours: the device sleeps through them (TRMNL's sleep mode)
        const q = x.quiet || { from: '22:00', to: '07:00', show: 'sleep' };
        const quiet = (b) => device(x, { quiet: { ...q, ...b } });
        const from = h('input', { class: 't', type: 'time', value: q.from, onchange: () => from.value && quiet({ from: from.value }) });
        const to = h('input', { class: 't', type: 'time', value: q.to, onchange: () => to.value && quiet({ to: to.value }) });
        const show = h('select', { class: 't', onchange: () => quiet({ show: show.value }) }, [['sleep', 'A sleep screen, and until when'], ['last', 'What it showed last']].map(([v, t]) => h('option', { value: v, selected: v === q.show ? true : null }, t)));
        const button = h('select', { class: 't', onchange: () => device(x, { button: button.value }) }, d.buttons.map((v) => h('option', { value: v, selected: v === x.button ? true : null }, BUTTON[v] || v)));
        const log = x.log.length ? h('details', { class: 'trmnl-log' }, h('summary', { class: 'muted small' }, 'What the device reported'),
          h('ul', { class: 'small' }, x.log.slice().reverse().map((l) => h('li', null, h('span', { class: 'muted' }, `${when(l.at)}  `), l.text)))) : null;
        return [
          h('div', { class: 'trmnl-two' },
            h('div', null,
              h('h3', null, 'Shows in turn'),
              h('div', { class: 'trmnl-rows' }, rows),
              h('div', { class: 'btns left' }, add, check('Stay on what it shows now', x.hold, (v) => device(x, { hold: v })))),
            h('img', { class: 'trmnl-pic', alt: `What ${x.name} shows`, style: `aspect-ratio: ${x.width} / ${x.height}`, src: `api/trmnl/devices/${x.id}/preview.png?at=${at}&v=${Date.now()}` })),
          h('div', { class: 'grid' }, fld('Name', title), fld('Looks again every', every), bits ? fld('Shades', bits) : null, fld('Two presses of its button', button)),
          check('Quiet hours', x.quiet, (v) => device(x, { quiet: v ? q : null }), 'It sleeps through them: no flashing at night, and the battery lasts longer. A press of its button still wakes it.'),
          x.quiet ? h('div', { class: 'grid trmnl-quiet' }, fld('From', from), fld('Until', to), fld('Meanwhile it shows', show)) : null,
          h('details', { class: 'trmnl-more', open: open[`m-${x.id}`] ? true : null, ontoggle: (e) => { open[`m-${x.id}`] = e.target.open; } }, h('summary', null, 'The device itself'),
            h('p', { class: 'muted small' }, facts),
            check('Draw every picture from a blank screen', x.clean, (v) => device(x, { clean: v }), 'Slower, with a flash, and no traces of the picture before.'),
            check('Have it report in detail', x.verbose, (v) => device(x, { verbose: v }), 'For when something is wrong: more in the list below, and a little more battery.'),
            x.pairing ? h('p', { class: 'small' }, 'Pairing is open: reset the device now (hold its button until it restarts) and it gets a new key.') : null,
            x.resetting ? h('p', { class: 'small' }, 'At its next look the device forgets its Wi-Fi and its key, and starts its setup again. Pairing stays open for an hour, so it comes back as this screen.') : null,
            h('div', { class: 'btns left' },
              h('button', { class: 'pillbtn noic', title: 'After a reset of the device, or when it says it is not registered', onclick: () => device(x, { pair: !x.pairing }, true) }, x.pairing ? 'Stop pairing' : 'Pair again'),
              h('button', { class: 'pillbtn noic', onclick: async () => {
                if (!x.resetting && !await confirmDialog('Reset the device', `${x.name} forgets its Wi-Fi and its key at its next look, and starts its setup again: you join it to the Wi-Fi and give it this address once more.`, 'Reset', true)) return;
                device(x, { reset: !x.resetting }, true);
              } }, x.resetting ? 'Do not reset' : 'Reset the device'),
              h('button', { class: 'pillbtn danger noic', onclick: async () => {
                if (!await confirmDialog('Remove the screen', `Remove ${x.name}? The device shows a code again, for anyone here to take.`, 'Remove', true)) return;
                try { await api(`api/trmnl/devices/${x.id}`, { method: 'DELETE' }); d.devices = d.devices.filter((o) => o.id !== x.id); toast('Removed'); drawDevices(); } catch (e) { fail(e); }
              } }, 'Remove')),
            log)];
      }, drawDevices);
    }));
    if (!d.devices.length) devs.replaceChildren(h('p', { class: 'muted' }, 'No TRMNL of yours asks the start page yet.'));
  }
  const code = h('input', { class: 't trmnl-code', placeholder: 'ABC123', maxlength: 8, autocomplete: 'off', autocapitalize: 'characters', spellcheck: 'false', 'aria-label': 'The code on the screen' });
  async function claim() {
    if (!code.value.trim()) return;
    try {
      const x = await api('api/trmnl/devices', { method: 'POST', json: { code: code.value } });
      d.devices.push(x); code.value = ''; open[`d-${x.id}`] = true; toast(`${x.name} is yours: it shows your screens at its next look`);
      if (tz && tz !== d.tz) await save({}); else drawDevices();
    } catch (e) { fail(e); }
  }
  code.addEventListener('keydown', (e) => { if (e.key === 'Enter') claim(); });
  const where = d.deviceServer
    ? [h('li', null, 'In the TRMNL’s Wi-Fi setup, where it asks for the server, enter this address instead of TRMNL’s own:',
      h('div', { class: 'trmnl-addr' }, h('code', null, d.deviceServer), copy(d.deviceServer)),
      h('span', { class: 'muted small' }, 'The device cannot sign in, so it has to reach the start page inside your network, not through Cloudflare Access.'))]
    : [h('li', null, 'In the TRMNL’s Wi-Fi setup, where it asks for the server, enter the start page’s address inside your network instead of TRMNL’s own. ',
      h('span', { class: 'muted small' }, 'This start page does not say it has one: it listens on this machine only (HOST in its config.env) or runs in a container without INTERNAL_URL. Through a reverse proxy, let ',
        d.devicePaths.map((x, i) => [i ? (i === d.devicePaths.length - 1 ? ' and ' : ', ') : '', h('code', null, x)]), ' pass without a sign-in.'))];
  // the two ways, one at a time: the page opens on the one in use
  let way = d.devices.length || !d.screens.some((x) => x.push) ? 'own' : 'cloud';
  const own = h('div', null,
    h('div', { class: 'box' }, h('h2', null, icon('wall'), 'Your screens'),
      h('p', { class: 'muted' }, 'The start page is a TRMNL server of its own: a TRMNL set to it gets finished pictures, with no TRMNL account, and nothing leaves your network.'),
      devs),
    h('details', { class: 'box trmnl-add', open: d.devices.length ? null : true }, h('summary', null, h('h2', null, icon('add'), 'Add a TRMNL')),
      h('ol', null, where,
        h('li', null, 'The device then shows a code. Type it here and it is yours: ',
          h('div', { class: 'btns left trmnl-claim' }, code, h('button', { class: 'pillbtn primary noic', onclick: claim }, 'Add a screen')),
          h('span', { class: 'muted small' }, 'It shows your screens, read as you with an app password the start page makes for this (Settings › Account lists it as “TRMNL”).')))));
  const cloud = h('div', { class: 'box' }, h('h2', null, icon('cloud'), 'TRMNL’s own plugins'),
    h('p', { class: 'muted' }, 'For a TRMNL that stays with TRMNL’s cloud, or with another TRMNL server. Each screen is a private plugin in TRMNL’s four sizes: open one to download it, then in TRMNL choose Plugins › Private Plugin › Import new.'),
    list,
    d.screens.some((x) => x.key === 'weather') ? null : h('p', { class: 'muted small' }, `A Weather screen joins these once the start page has its weather${S.user.role === 'admin' ? ' (Settings › Home page)' : ''}.`),
    h('details', { class: 'trmnl-more' }, h('summary', null, 'Which of the two downloads'),
      h('p', null, h('b', null, 'For TRMNL to read: '), 'your own TRMNL server inside your network, or TRMNL’s cloud when it can reach the start page (through Cloudflare Access with a service token its policy lets in). In the plugin’s settings in TRMNL, give the start page’s address (', h('code', null, d.server), ') and an app password of yours (Settings › Account › App passwords).'),
      h('p', null, h('b', null, 'For the start page to send: '), 'TRMNL’s cloud when the start page is only inside your network or behind Cloudflare Access. After the import, copy the plugin’s Webhook URL from its settings in TRMNL and paste it into the screen’s line here. The start page then sends the screen every 15 minutes when it changed, reading it as you with an app password it makes for this (Settings › Account lists it as “TRMNL”).')));
  const seg = h('div', { class: 'seg trmnl-ways' });
  const view = h('div');
  function pick() {
    seg.replaceChildren(...[['own', 'Straight from the start page'], ['cloud', 'Through TRMNL’s cloud']].map(([k, t]) => h('button', { class: way === k ? 'on' : '', 'aria-pressed': String(way === k), onclick: () => { way = k; pick(); } }, t)));
    view.replaceChildren(way === 'own' ? own : cloud);
  }
  el.append(h('div', { class: 'trmnl-top' },
    h('p', null, 'Put the suite on a TRMNL e-ink display: today, the weather, the calendar, tasks, papers to renew, health and bills, each filling the display or sharing it with others.'),
    h('div', { class: 'trmnl-bar' }, seg, h('label', { class: 'trmnl-clock' }, h('span', { class: 'muted small' }, 'Times'), clock))),
  view);
  draw();
  drawDevices();
  pick();
  if (tz && tz !== d.tz && (d.screens.some((x) => x.push) || d.devices.length)) save({});
}

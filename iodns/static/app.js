/* ioDNS web app: one module, no build step, laid out as the other ioSuite apps. Pages: the master list (a row per host
   name, a column per view), Compare (a view's servers against the master list, with a decision per name), Servers,
   Dynamic DNS, History and Settings (account, display, views, and for admins server, for suite admins security and
   global settings). */
import { client, h } from '../api/auth/ui.js';  // the suite's shared helpers (iosuite_shared/static/account-panel.js)
import * as frame from '../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { accountUi, addIcons, closeDialogs, closeNav, confirmDialog, fail, fld, icon, openNav, put, toast } from '../api/auth/frame.js';
const store = frame.storeFor('iodns');  // what this browser remembers for the app
const api = client(document.baseURI, { signIn: () => showSignIn() });

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
addIcons({
  dns: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  compare: 'M10 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h5v2h2V1h-2v2zm0 15H5l5-6v6zm9-15h-5v2h5v13l-5-6v9h5c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z',
  sync: 'M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  layers: 'M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z',
  play: 'M8 5v14l11-7z',
});


function dialog(title, body, buttons, wide) {
  return frame.dialog(title, body, buttons, wide ? 'wide' : '', { wait: true, focus: 'input:not([type=checkbox]),select,textarea' });
}

const ago = (iso) => {
  if (!iso) return 'never';
  const s = (Date.now() - new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleString();
};

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, views: [], servers: [], providers: [], entries: [], ddns: {}, types: ['A', 'AAAA', 'CNAME'], q: '', cmp: {} };
const canEdit = () => S.user && ['editor', 'admin'].includes(S.user.role);
const isAdmin = () => S.user && S.user.role === 'admin';
const kindOf = (k) => S.providers.find((p) => p.kind === k) || { label: k, fields: [], target: true };
const viewOf = (slug) => S.views.find((v) => v.slug === slug) || { slug, name: slug };
const tailscales = () => S.servers.filter((s) => s.kind === 'tailscale');
const cftunnels = () => S.servers.filter((s) => s.kind === 'cftunnel');
/** A record's value as shown: a tunnel's "home|http://…" as "home → http://…". */
const fmtVal = (r) => r.type === 'TUNNEL' ? r.value.replace('|', ' → ') : r.value;

async function loadOverview() {
  const o = await api('api/overview');
  Object.assign(S, { views: o.views, servers: o.servers, providers: o.providers, ddns: o.ddns, types: o.types });
  drawNav();
}
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}

// ------------------------------------------------------------------ chrome
function drawUser() {
  frame.userMenu($('#usermenu'), S.user, api, (close) => [
    frame.menuLink('#/settings/account', 'person', 'Account', close),
    frame.themeEntry(frame.applyTheme, close)]);
}
/* The suite (iosuite_shared's suite_apps): when other ioSuite apps are registered, the app mark opens a menu of them. */
async function loadSuite() { S.suite = await frame.loadSuite(api); drawNav(); }

/* The sidebar: the master list, Compare for each view (with how many names differ), servers, dynamic DNS, history,
   Settings. Docked beside the page on a wide screen, sliding over it otherwise, a bottom bar on a phone. */
function drawNav() {
  const nav = $('#nav'); if (!S.user) return;
  const r = route();
  // the sidebar's parts, the same in every app (iosuite_shared/static/frame.js); below them, its own rows
  const { head, link, sec, gap, more } = frame.navParts(store, { name: 'DNS', title: 'Records', redraw: drawNav });
  const diffs = (slug) => { const ss = S.servers.filter((s) => s.view === slug && s.target && s.enabled); const n = ss.reduce((a, s) => a + (s.check.differences || 0), 0); const bad = ss.some((s) => s.check.ok === false); return { n, bad, any: ss.some((s) => s.check.at) }; };
  nav.replaceChildren(...[
    head(),
    link('records', '#/', 'list', 'Records', null, r.view === 'records', '--c-teal'),
    link('compare', `#/compare/${r.view === 'compare' ? r.slug : (S.views[0] || {}).slug || 'internal'}`, 'compare', 'Compare', null, r.view === 'compare', '--c-indigo'),
    link('servers', '#/servers', 'dns', 'Servers', S.servers.length || null, r.view === 'servers', '--c-blue'),
    link('ddns', '#/ddns', 'globe', 'Dynamic DNS', null, r.view === 'ddns', '--c-orange'),
    more(moreSheet),
    gap(), sec('Views'),
    S.views.map((v) => { const d = diffs(v.slug); const a = link('view', `#/compare/${v.slug}`, 'layers', v.name, d.any ? (d.bad ? '!' : d.n ? String(d.n) : '✓') : null, r.view === 'compare' && r.slug === v.slug);
      if (d.bad || d.n) a.classList.add('warnn'); return a; }),
    gap(),
    link('history', '#/history', 'history', 'History', null, r.view === 'history', '--c-slate'),
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['history', 'settings'].includes(r.view));
}
function applySidebar() { frame.applySidebar(store); }
function moreSheet() {
  const tile = (href, ic, label, hueV) => h('a', { href, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' }, S.views.map((v) => tile(`#/compare/${v.slug}`, 'layers', `Compare ${v.name}`, 'var(--c-indigo)')),
    tile('#/history', 'history', 'History', 'var(--c-slate)'), tile('#/settings', 'settings', 'Settings', 'var(--c-slate)'));
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) closeDialogs(); });
  return dialog('More', grid, [{ label: 'Close', value: null }]);
}

// ------------------------------------------------------------------ routes
function route() {
  const p = location.hash.replace(/^#\/?/, '').split('?')[0].split('/').map(decodeURIComponent);
  const [a, b, c] = p;
  if (!a) return { view: 'records' };
  if (a === 'compare') return { view: 'compare', slug: b || (S.views[0] || {}).slug || 'internal' };
  if (['servers', 'ddns', 'history'].includes(a)) return { view: a };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'records' };
}
async function onRoute() {
  const r = route();
  const main = $('#main');
  const page = h('div', { class: 'page' });
  if (location.hash !== main.dataset.at) { main.scrollTop = 0; main.dataset.at = location.hash; }  // a new page starts at the top; the same one, redrawn, stays put
  main.replaceChildren(page);
  $('#newbtn').hidden = !(canEdit() && r.view === 'records');
  $('#search').hidden = !['records', 'compare'].includes(r.view);
  try {
    await ({ records: showRecords, compare: showCompare, servers: showServers, ddns: showDdns, history: showHistory, settings: showSettings })[r.view](page, r);
  } catch (e) { page.append(h('p', { class: 'warn' }, e.message)); }
  drawNav();
}

// ------------------------------------------------------------------ records (the master list)
const SRC_LABEL = (src) => {
  if (!src) return null;
  if (src === 'publicip') return 'public IPv4';
  if (src === 'publicip6') return 'public IPv6';
  if (src.startsWith('tailscale:')) return `tailnet: ${src.split(':').slice(2).join(':')}`;
  return src;
};
const recChip = (r) => h('span', { class: `rec t-${r.type}`, title: r.source ? `Follows ${SRC_LABEL(r.source)}` : (r.ttl ? `TTL ${r.ttl}s` : '') },
  h('b', null, r.type), h('span', { class: 'v' }, fmtVal(r)), r.source ? h('span', { class: 'src' }, r.source.startsWith('tailscale') ? 'TS' : 'IP') : null);
const matches = (e, q) => !q || e.name.includes(q) || (e.comment || '').toLowerCase().includes(q) || Object.values(e.records).flat().some((r) => r.value.includes(q));

async function showRecords(page) {
  S.entries = (await api('api/entries')).items;
  const body = h('div');
  const draw = () => {
    const q = S.q.toLowerCase();
    const items = S.entries.filter((e) => matches(e, q));
    if (!S.entries.length) {
      body.replaceChildren(h('div', { class: 'empty' }, icon('dns'), h('p', null, 'The master list is empty.'),
        h('p', null, S.servers.some((s) => s.target) ? ['Bring in what a server already holds: ', h('a', { class: 'lnk', href: '#/servers' }, 'Servers › Import'), ', or add an entry with New.']
          : ['Start by adding your DNS servers under ', h('a', { class: 'lnk', href: '#/servers' }, 'Servers'), ', then import from one of them.'])));
      return;
    }
    body.replaceChildren(h('div', { class: 'tablewrap' }, h('table', { class: 't recs' },
      h('thead', null, h('tr', null, h('th', null, `Name (${items.length})`), S.views.map((v) => h('th', null, v.name)), h('th', null, 'Note'), canEdit() ? h('th', null) : null)),
      h('tbody', null, items.map((e) => h('tr', { class: canEdit() ? 'click' : null, onclick: canEdit() ? (ev) => { if (!ev.target.closest('button')) editEntry(e); } : null },
        h('td', { class: 'nm' }, e.name),
        S.views.map((v) => h('td', null, (e.records[v.slug] || []).map(recChip))),
        h('td', { class: 'muted small' }, e.comment),
        canEdit() ? h('td', { class: 'act' }, h('button', { class: 'iconbtn', title: 'Edit', onclick: () => editEntry(e) }, icon('edit', 's'))) : null))))));
  };
  S.redraw = draw;
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Records'),
    h('span', { class: 'muted' }, 'One row per name, one column per view. A value marked TS follows a Tailscale device, IP the public address; TUNNEL is a Cloudflare Tunnel public hostname.')), body);
  draw();
}

/** The entry form: the name, a note, and for each view its records (type, then a typed value, the public address or a
    Tailscale device). */
async function editEntry(e) {
  const isNew = !e;
  e = e || { name: '', comment: '', records: {} };
  const name = h('input', { class: 't', value: e.name, placeholder: 'calendar.example.com', autocapitalize: 'none', spellcheck: 'false' });
  const comment = h('input', { class: 't', value: e.comment || '', placeholder: 'What it is (optional)' });
  const ts = tailscales();
  const devices = {};
  const loadDevices = async (sid) => { if (!devices[sid]) devices[sid] = api(`api/servers/${sid}/devices`).then((r) => r.items).catch((x) => { fail(x); return []; }); return devices[sid]; };
  let tunnelNames = null;
  const loadTunnels = () => tunnelNames = tunnelNames || Promise.all(cftunnels().map((s) => api(`api/servers/${s.id}/tunnels`).then((r) => r.items).catch((x) => { fail(x); return []; })))
    .then((ls) => [...new Set(ls.flat().filter((t) => t.remote).map((t) => t.name))]);
  const rows = {};
  const viewBox = (v) => {
    const list = h('div', { class: 'reclist' });
    rows[v.slug] = [];
    const addRow = (r) => {
      r = r || { type: 'A', value: '', source: null };
      const type = h('select', { class: 't type' }, S.types.map((t) => h('option', { value: t, selected: t === r.type ? true : null }, t)));
      const value = h('input', { class: 't val', value: r.source || r.type === 'TUNNEL' ? '' : r.value, placeholder: '192.168.1.10 / host.example.com', autocapitalize: 'none', spellcheck: 'false' });
      const srcOpts = [['', 'Typed'], ['publicip', 'Public address'], ...ts.map((s) => [`tailscale:${s.id}`, `Tailscale device (${s.name})`])];
      const cur = r.source ? (r.source.startsWith('tailscale:') ? r.source.split(':').slice(0, 2).join(':') : 'publicip') : '';
      const src = h('select', { class: 't src' }, srcOpts.map(([k, l]) => h('option', { value: k, selected: k === cur ? true : null }, l)));
      const dev = h('select', { class: 't dev', hidden: true });
      const [tName, tService] = r.type === 'TUNNEL' ? [r.value.split('|')[0], r.value.split('|').slice(1).join('|')] : ['', ''];
      const tun = h('select', { class: 't dev', hidden: true });
      const svc = h('input', { class: 't val', hidden: true, value: tService, placeholder: 'http://192.168.1.151:8620', autocapitalize: 'none', spellcheck: 'false' });
      let tunFilled = false;
      const fillTunnels = async () => {
        if (tunFilled) return; tunFilled = true;
        tun.replaceChildren(h('option', { value: '' }, 'Loading…'));
        const names = await loadTunnels();
        if (tName && !names.includes(tName)) names.push(tName);
        tun.replaceChildren(h('option', { value: '' }, names.length ? 'Pick a tunnel' : 'No tunnel: add a Cloudflare Tunnel server'), ...names.map((n) => h('option', { value: n, selected: n === tName ? true : null }, n)));
      };
      const fillDevices = async () => {
        const sid = src.value.split(':')[1];
        const want = r.source && r.source.startsWith(`tailscale:${sid}:`) ? r.source.split(':').slice(2).join(':') : '';
        dev.replaceChildren(h('option', { value: '' }, 'Loading…'));
        const items = await loadDevices(sid);
        dev.replaceChildren(h('option', { value: '' }, 'Pick a device'), ...items.map((d) => h('option', { value: d.name, selected: d.name === want ? true : null }, `${d.name} (${type.value === 'AAAA' ? d.ipv6 || 'no IPv6' : d.ipv4 || 'no IPv4'})`)));
      };
      const sync = () => {
        const isT = type.value === 'TUNNEL';
        tun.hidden = svc.hidden = !isT;
        if (isT) { fillTunnels(); src.value = ''; src.hidden = true; value.hidden = true; dev.hidden = true; return; }
        src.hidden = false;
        const s = src.value;
        value.hidden = !!s; dev.hidden = !s.startsWith('tailscale:');
        if (s.startsWith('tailscale:')) fillDevices();
        if (s === 'publicip' && !['A', 'AAAA'].includes(type.value)) type.value = 'A';
        src.disabled = type.value === 'CNAME';
        if (type.value === 'CNAME') { src.value = ''; value.hidden = false; dev.hidden = true; }
      };
      src.onchange = sync; type.onchange = sync;
      const row = { type, value, src, dev, tun, svc };
      row.el = h('div', { class: 'recrow' }, type, src, value, dev, tun, svc, h('button', { class: 'iconbtn', title: 'Remove', onclick: () => { row.el.remove(); rows[v.slug].splice(rows[v.slug].indexOf(row), 1); } }, icon('close', 's')));
      rows[v.slug].push(row); list.append(row.el);
      sync();
    };
    (e.records[v.slug] || []).forEach(addRow);
    return h('div', { class: 'vsec' }, h('div', { class: 'vsech' }, icon('layers', 's'), h('b', null, v.name),
      h('button', { class: 'pillbtn tiny', onclick: () => addRow() }, icon('add', 's'), 'Add a record')),
      v.description ? h('p', { class: 'muted small desc' }, v.description) : null, list);
  };
  const collect = () => {
    const recs = {};
    for (const [slug, rs] of Object.entries(rows)) {
      recs[slug] = rs.map((r) => {
        if (r.type.value === 'TUNNEL') {
          if (!r.svc.value.trim()) return {};
          if (!r.tun.value) throw new Error('Pick the tunnel');
          return { type: 'TUNNEL', value: `${r.tun.value}|${r.svc.value.trim()}` };
        }
        const s = r.src.value;
        if (s === 'publicip') return { type: r.type.value, source: r.type.value === 'AAAA' ? 'publicip6' : 'publicip' };
        if (s.startsWith('tailscale:')) { if (!r.dev.value) throw new Error('Pick the Tailscale device'); return { type: r.type.value, source: `${s}:${r.dev.value}` }; }
        return { type: r.type.value, value: r.value.value.trim() };
      }).filter((r) => r.source || r.value);
    }
    return { name: name.value.trim(), comment: comment.value.trim(), records: recs };
  };
  const body = h('div', { class: 'pform' }, h('div', { class: 'grid' }, fld('Name', name), fld('Note', comment)), S.views.map(viewBox),
    h('p', { class: 'muted small' }, 'A view without records leaves that name out of its servers (an internal-only name never reaches public DNS). After saving, ioDNS offers to push the change to the servers.'));
  const buttons = [
    !isNew ? { label: 'Delete', danger: true, value: async () => { if (!await confirmDialog('Delete', `Take ${e.name} out of the master list? ioDNS then offers to remove it from the servers too.`, 'Delete', true)) return undefined; await api(`api/entries/${e.id}`, { method: 'DELETE' }); return 'deleted'; } } : null,
    { label: 'Cancel', value: null },
    { label: isNew ? 'Add' : 'Save', primary: true, value: async () => api(isNew ? 'api/entries' : `api/entries/${e.id}`, { method: isNew ? 'POST' : 'PUT', json: collect() }) },
  ].filter(Boolean);
  const r = await dialog(isNew ? 'New entry' : e.name, body, buttons, true);
  if (!r) return;
  if (route().view === 'records') onRoute();
  // the name as saved, and the one it had (a renamed entry leaves its old name on the servers otherwise)
  const names = r === 'deleted' ? [e.name] : [r.name, isNew ? null : e.name].filter((n, i, a) => n && a.indexOf(n) === i);
  offerPush(names, r === 'deleted' ? 'Deleted' : 'Saved');
}

// After a change to the master list: what pushing it would do on the servers, and the choice to do it now.
// names: the names that changed; null: everything that differs in every view (after an import; extras stay).
async function offerPush(names, done) {
  if (!canEdit()) { toast(done); return; }
  let preview;
  try { preview = await api('api/push', { method: 'POST', json: { names, dryRun: true } }); } catch (e) { toast(`${done}. Compare to push it (${e.message})`); return; }
  const ops = preview.views.flatMap((v) => v.servers.flatMap((s) => s.ops.map((o) => ({ ...o, server: s.name, view: v.name }))));
  if (!ops.length) { toast(`${done}: the servers hold it already`); return; }
  const many = new Set(preview.views.map((v) => v.view)).size > 1;
  const opline = (o) => h('li', null, h('b', null, o.server), many ? h('span', { class: 'muted' }, ` (${o.view})`) : null, ': ', { add: 'add', delete: 'remove', update: 'change' }[o.op], ' ',
    h('code', null, `${o.name} ${o.type} ${fmtVal(o)}`), o.was ? h('span', { class: 'muted' }, ` (was ${fmtVal({ type: o.type, value: o.was })})`) : null);
  const body = h('div', null, h('p', null, `${done}. Push the change to the servers now?`),
    h('ul', { class: 'ops' }, ops.map(opline)));
  if (!await dialog('Push now?', body, [{ label: 'Later', value: false }, { label: `Push ${ops.length}`, value: true, primary: true }], true)) { toast(`${done}: Compare pushes it later`); return; }
  try {
    const res = await api('api/push', { method: 'POST', json: { names } });
    const errs = res.views.flatMap((v) => v.servers.flatMap((s) => s.errors.map((x) => `${s.name}: ${x}`)));
    if (errs.length) await dialog('Some changes failed', h('ul', { class: 'ops' }, errs.map((x) => h('li', { class: 'warn' }, x))));
    else toast(`Pushed: ${res.views.reduce((a, v) => a + v.servers.reduce((b, s) => b + s.ops.length, 0), 0)} change(s) on the servers`);
  } catch (e) { fail(e); }
  if (route().view === 'records') onRoute();
}

// ------------------------------------------------------------------ compare and push
const STATE = { same: ['ok', 'In sync'], missing: ['missing', 'Missing'], extra: ['extra', 'Only on the server'], different: ['diff', 'Different'],
  unreachable: ['unr', 'Unreachable'], outside: ['out', 'Not in its zones'], leftout: ['out', 'Left out'], ok: ['ok', 'In sync'] };
async function showCompare(page, r) {
  const v = viewOf(r.slug);
  const head = h('div', { class: 'pagehead' }, h('h1', null, `Compare: ${v.name}`));
  const tabs = h('div', { class: 'tabs' }, S.views.map((x) => h('button', { class: x.slug === v.slug ? 'on' : '', onclick: () => { location.hash = `#/compare/${x.slug}`; } }, x.name)));
  const out = h('div', null, h('p', { class: 'muted' }, 'Reading every server of this view…'));
  page.append(head, tabs, out);
  let st;
  try { st = await api(`api/sync/${encodeURIComponent(v.slug)}`); } catch (e) { out.replaceChildren(h('p', { class: 'warn' }, e.message)); return; }
  api('api/servers').then((x) => { S.servers = x.items; drawNav(); }).catch(() => {});
  if (!st.servers.length) {
    out.replaceChildren(h('div', { class: 'empty' }, icon('dns'), h('p', null, `No server answers for the ${v.name} view yet.`), isAdmin() ? h('a', { class: 'pillbtn primary', href: '#/servers' }, icon('add', 's'), 'Add a server') : null));
    return;
  }
  const decisions = {};
  let onlyDiff = S.cmp.onlyDiff ?? true;
  const servers = st.servers;
  const summary = h('div', { class: 'srvchips' }, servers.map((s) => h('span', { class: `chip srv ${s.ok ? (s.differences ? 'diff' : 'ok') : 'unr'}`, title: s.ok ? `${s.count} records` : s.error },
    h('span', { class: 'dot' }), h('b', null, s.name), h('span', { class: 'lab' }, s.ok ? (s.differences ? `${s.differences} to fix` : 'in sync') : 'unreachable'))));
  const notes = st.notes && st.notes.length ? h('p', { class: 'muted small' }, st.notes.join(' · ')) : null;
  const errors = servers.filter((s) => !s.ok).map((s) => h('p', { class: 'warn' }, `${s.name}: ${s.error}`));
  const applyBtn = h('button', { class: 'pillbtn primary', disabled: true, onclick: () => run(false) }, icon('play', 's'), 'Apply');
  const count = () => Object.values(decisions).filter((d) => d && d !== 'skip').length;
  const refreshBtn = () => { const n = count(); applyBtn.disabled = !n || !canEdit(); applyBtn.lastChild.textContent = n ? `Apply ${n} change${n > 1 ? 's' : ''}` : 'Apply'; };
  const choice = (row) => {
    const opts = [['skip', 'Leave as it is']];
    if (row.master.length) opts.unshift(['master', 'Use the master list']);
    servers.forEach((s) => { const c = row.servers[s.id]; if (c && c.records.length && c.state !== 'same') opts.push([`server:${s.id}`, `Use ${s.name}'s`]); });
    opts.push(['delete', 'Delete everywhere']);
    const sel = h('select', { class: 't', disabled: !canEdit() }, opts.map(([k, l]) => h('option', { value: k, selected: k === (decisions[row.name] ?? row.default) ? true : null }, l)));
    decisions[row.name] = decisions[row.name] ?? row.default;
    sel.onchange = () => { decisions[row.name] = sel.value; refreshBtn(); };
    return sel;
  };
  const table = h('div', { class: 'tablewrap' });
  const draw = () => {
    const q = S.q.toLowerCase();
    const rows = st.rows.filter((x) => (!onlyDiff || x.state !== 'ok') && (!q || x.name.includes(q)));
    table.replaceChildren(rows.length ? h('table', { class: 't cmp' },
      h('thead', null, h('tr', null, h('th', null, `Name (${rows.length})`), h('th', null, 'Master list'), servers.map((s) => h('th', null, s.name)), h('th', null, 'Resolve'))),
      h('tbody', null, rows.map((x) => h('tr', { class: `st-${STATE[x.state][0]}` },
        h('td', { class: 'nm' }, x.name, h('div', { class: `badge b-${STATE[x.state][0]}` }, STATE[x.state][1])),
        h('td', null, x.master.length ? x.master.map(recChip) : h('span', { class: 'muted small' }, 'none')),
        servers.map((s) => { const c = x.servers[s.id] || { state: 'unreachable', records: [] }; return h('td', { class: `cell c-${STATE[c.state][0]}`, title: STATE[c.state][1] },
          c.state === 'same' ? h('span', { class: 'okmark' }, icon('check', 's')) : c.records.length ? c.records.map(recChip) : h('span', { class: 'muted small' }, STATE[c.state][1])); }),
        h('td', null, x.state === 'ok' ? null : choice(x))))))
      : h('div', { class: 'empty' }, icon('check'), h('p', null, onlyDiff ? 'Every server of this view holds the master list.' : 'Nothing here.')));
    refreshBtn();
  };
  const only = h('input', { type: 'checkbox', checked: onlyDiff, onchange: () => { onlyDiff = S.cmp.onlyDiff = only.checked; draw(); } });
  const prune = h('input', { type: 'checkbox' });
  async function run(all) {
    const path = all ? `api/sync/${v.slug}/push` : `api/sync/${v.slug}/apply`;
    const payload = all ? { prune: prune.checked } : { decisions };
    let preview;
    try { preview = await api(path, { method: 'POST', json: { ...payload, dryRun: true } }); } catch (e) { fail(e); return; }
    const masterChanges = Object.entries(preview.master || {});
    const ops = preview.servers.flatMap((s) => s.ops.map((o) => ({ ...o, server: s.name })));
    if (!ops.length && !masterChanges.length) { toast('Nothing to change'); return; }
    const opline = (o) => h('li', null, h('b', null, o.server), ': ', { add: 'add', delete: 'remove', update: 'change' }[o.op], ' ', h('code', null, `${o.name} ${o.type} ${fmtVal(o)}`), o.was ? h('span', { class: 'muted' }, ` (was ${fmtVal({ type: o.type, value: o.was })})`) : null);
    const body = h('div', null,
      masterChanges.length ? [h('h3', null, 'The master list'), h('ul', { class: 'ops' }, masterChanges.map(([n, rs]) => h('li', null, h('code', null, n), ' ← ', rs.length ? rs.map((x) => `${x.type} ${fmtVal(x)}`).join(', ') : 'removed')))] : null,
      ops.length ? [h('h3', null, 'The servers'), h('ul', { class: 'ops' }, ops.map(opline))] : null);
    if (!await confirmDialog(all ? 'Push the master list' : 'Apply these changes', body, `Apply ${ops.length + masterChanges.length}`)) return;
    applyBtn.disabled = true;
    try {
      const res = await api(path, { method: 'POST', json: payload });
      const errs = res.servers.flatMap((s) => s.errors.map((e) => `${s.name}: ${e}`));
      if (errs.length) await dialog('Some changes failed', h('ul', { class: 'ops' }, errs.map((e) => h('li', { class: 'warn' }, e))));
      else toast(`Done: ${res.servers.reduce((a, s) => a + s.ops.length, 0)} change(s) on the servers`);
    } catch (e) { fail(e); }
    onRoute();
  }
  out.replaceChildren(...[summary, notes, ...errors].filter(Boolean),
    h('div', { class: 'cmpbar' }, h('label', { class: 'check' }, only, ' Only what differs'), h('span', { class: 'grow' }),
      h('button', { class: 'pillbtn', onclick: () => onRoute() }, icon('sync', 's'), 'Compare again'),
      canEdit() ? [h('label', { class: 'check', title: 'Also remove the names only the servers hold' }, prune, ' and remove extras'),
        h('button', { class: 'pillbtn', onclick: () => run(true) }, icon('upload', 's'), 'Push all'), applyBtn] : null),
    table);
  draw();
  S.redraw = draw;
}

// ------------------------------------------------------------------ servers
async function showServers(page) {
  await loadOverview();
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Servers'),
    isAdmin() ? h('button', { class: 'pillbtn primary', onclick: () => editServer(null) }, icon('add', 's'), 'Add a server') : null));
  if (!S.servers.length) {
    page.append(h('div', { class: 'empty' }, icon('dns'), h('p', null, 'No DNS server yet.'), h('p', { class: 'muted' }, 'AdGuard Home, Pi-hole, UniFi gateways and Cloudflare are kept in sync; Tailscale gives device addresses and split DNS.')));
    return;
  }
  for (const v of [...S.views, { slug: null, name: 'Sources' }]) {
    const ss = S.servers.filter((s) => (v.slug ? s.view === v.slug && s.target : !s.target));
    if (!ss.length) continue;
    page.append(h('h2', { class: 'sech' }, v.slug ? `${v.name} view` : 'Sources'), h('div', { class: 'cards' }, ss.map(serverCard)));
  }
}
function serverCard(s) {
  const st = s.check.ok === null ? 'unk' : s.check.ok ? (s.check.differences ? 'diff' : 'ok') : 'unr';
  const msg = h('div', { class: 'muted small' }, s.check.at ? `${s.check.ok ? (s.check.differences != null ? (s.check.differences ? `${s.check.differences} name(s) differ` : 'Matches the master list') : s.check.message) : s.check.message} · ${ago(s.check.at)}` : 'Not checked yet');
  const test = async () => { msg.textContent = 'Testing…'; try { const r = await api(`api/servers/${s.id}/test`, { method: 'POST' }); msg.textContent = r.message; msg.className = r.ok ? 'small' : 'warn small'; } catch (e) { msg.textContent = e.message; } };
  return h('div', { class: `card srvcard s-${st}` + (s.enabled ? '' : ' off') },
    h('h3', null, h('span', { class: 'dot' }), s.name, h('span', { class: 'muted small kind' }, s.kindLabel)),
    h('div', { class: 'small' }, s.url || '', s.enabled ? null : h('b', null, ' · off')),
    msg,
    h('div', { class: 'cardbtns' },
      isAdmin() ? h('button', { class: 'pillbtn noic', onclick: test }, 'Test') : null,
      s.target && canEdit() ? h('button', { class: 'pillbtn noic', onclick: () => importDialog(s) }, 'Import') : null,
      s.kind === 'tailscale' && isAdmin() ? h('button', { class: 'pillbtn noic', onclick: () => splitDns(s) }, 'Split DNS') : null,
      isAdmin() ? h('button', { class: 'pillbtn noic', onclick: () => editServer(s) }, 'Edit') : null));
}

async function editServer(s) {
  const isNew = !s;
  const kinds = S.providers;
  const kind = h('select', { class: 't', disabled: !isNew }, kinds.map((k) => h('option', { value: k.kind, selected: s && s.kind === k.kind ? true : null }, k.label)));
  const name = h('input', { class: 't', value: s ? s.name : '', placeholder: 'AdGuard 1' });
  const view = h('select', { class: 't' }, S.views.map((v) => h('option', { value: v.slug, selected: (s ? s.view : 'internal') === v.slug ? true : null }, v.name)));
  const enabled = h('input', { type: 'checkbox', checked: s ? s.enabled : true });
  const fieldsBox = h('div', { class: 'grid' });
  const status = h('p', { class: 'muted small' });
  let inputs = {};
  const drawFields = () => {
    const k = kindOf(kind.value);
    inputs = {};
    const opts = s ? s.options : {};
    const show = [];
    for (const f of k.fields) {
      let el;
      const cur = f.key === 'url' ? (s ? s.url : '') || f.default || '' : opts[f.key] ?? f.default ?? '';
      if (f.type === 'password') el = h('input', { class: 't', type: 'password', autocomplete: 'new-password', placeholder: s && s.secretSet ? 'Kept (type to replace)' : '' });
      else if (f.type === 'check') el = h('input', { type: 'checkbox', checked: !!cur });
      else if (f.type === 'select') el = h('select', { class: 't' }, f.options.map(([v, l]) => h('option', { value: v, selected: v === cur ? true : null }, l)));
      else el = h('input', { class: 't', value: cur, placeholder: f.hint || '', autocapitalize: 'none', spellcheck: 'false' });
      inputs[f.key] = { f, el };
      const wrap = f.type === 'check' ? h('label', { class: 'check full' }, el, ' ', f.label) : fld(f.label, el, f.type !== 'text' && f.type !== 'url' ? f.hint : null);
      inputs[f.key].wrap = wrap;
      show.push(wrap);
    }
    fieldsBox.replaceChildren(...show);
    const when = () => { for (const { f, wrap } of Object.values(inputs)) if (f.when) wrap.hidden = !Object.entries(f.when).every(([kk, vv]) => inputs[kk] && inputs[kk].el.value === vv); };
    for (const { el } of Object.values(inputs)) el.addEventListener('change', when);
    when();
    view.closest('label').hidden = !k.target;
    if (!name.value) name.placeholder = k.label;
  };
  const collect = () => {
    const b = { kind: kind.value, name: name.value.trim() || kindOf(kind.value).label, enabled: enabled.checked, options: {} };
    if (kindOf(kind.value).target) b.view = view.value;
    for (const [key, { f, el }] of Object.entries(inputs)) {
      const v = f.type === 'check' ? el.checked : el.value.trim();
      if (key === 'url') b.url = v;
      else if (key === 'secret') { if (v) b.secret = v; }
      else b.options[key] = v;
    }
    return b;
  };
  const body = h('div', { class: 'pform' }, h('div', { class: 'grid' }, fld('Kind', kind), fld('Name', name), fld('View', view, 'which answers this server gives')), fieldsBox,
    h('label', { class: 'check' }, enabled, ' Kept in sync (off: left out of comparisons and pushes)'), status,
    h('p', { class: 'muted small' }, 'The password or key is kept with the suite\'s keys and tokens (Settings › Keys), never shown again.'));
  kind.onchange = drawFields;
  drawFields();
  const testIt = async () => { status.textContent = 'Testing…'; status.className = 'muted small'; try { const r = await api('api/servers/test', { method: 'POST', json: { ...collect(), id: s ? s.id : null } }); status.textContent = r.message; status.className = r.ok ? 'okmsg small' : 'warn small'; } catch (e) { status.textContent = e.message; status.className = 'warn small'; } return undefined; };
  const r = await dialog(isNew ? 'Add a DNS server' : s.name, body, [
    !isNew ? { label: 'Remove', danger: true, value: async () => { if (!await confirmDialog('Remove', `Forget ${s.name}? Nothing on the server itself changes.`, 'Remove', true)) return undefined; await api(`api/servers/${s.id}`, { method: 'DELETE' }); return 'removed'; } } : null,
    { label: 'Test', value: testIt },
    { label: 'Cancel', value: null },
    { label: isNew ? 'Add' : 'Save', primary: true, value: () => api(isNew ? 'api/servers' : `api/servers/${s.id}`, { method: isNew ? 'POST' : 'PATCH', json: collect() }) },
  ].filter(Boolean), true);
  if (r) { toast(r === 'removed' ? 'Removed' : 'Saved'); onRoute(); }
}

async function importDialog(s) {
  const mode = h('div', { class: 'radios' }, [
    ['merge', 'Merge', 'Add the names the master list lacks; where both have a name, the master list stays.'],
    ['overwrite', 'Merge, the server wins', 'As Merge, but where both have a name, take the server\'s records.'],
    ['replace', 'Replace', `The ${viewOf(s.view).name} records of the master list become exactly ${s.name}'s.`]].map(([v, l, d], i) =>
    h('label', { class: 'radio' }, h('input', { type: 'radio', name: 'mode', value: v, checked: i === 0 }), h('span', null, h('b', null, l), h('br'), h('span', { class: 'muted small' }, d)))));
  const ok = await confirmDialog(`Import from ${s.name}`, h('div', null, h('p', null, `Load the master list's ${viewOf(s.view).name} records from ${s.name}. ioDNS then offers to push what changed to the other servers.`), mode), 'Import');
  if (!ok) return;
  try {
    const r = await api(`api/servers/${s.id}/import`, { method: 'POST', json: { mode: mode.querySelector('input:checked').value } });
    location.hash = '#/';
    const done = `${r.records} records read: ${r.added} added, ${r.changed} changed, ${r.removed} removed`;
    if (r.added || r.changed || r.removed) offerPush(null, done); else toast(done);
  } catch (e) { fail(e); }
}

async function splitDns(s) {
  let cur = {};
  try { cur = (await api(`api/servers/${s.id}/split-dns`)).domains || {}; } catch (e) { fail(e); return; }
  const domain = h('input', { class: 't', placeholder: 'example.com', autocapitalize: 'none' });
  const ns = h('input', { class: 't', placeholder: '100.101.102.103 (the tailnet address of the DNS server)' });
  const list = h('table', { class: 't' }, Object.entries(cur).map(([d, v]) => h('tr', null, h('td', null, d), h('td', null, (v || []).join(', ')),
    h('td', null, h('button', { class: 'pillbtn noic tiny', onclick: async () => { try { await api(`api/servers/${s.id}/split-dns`, { method: 'PUT', json: { domain: d, nameservers: [] } }); toast(`${d}: off`); closeDialogs(); } catch (e) { fail(e); } } }, 'Stop')))));
  const r = await dialog('Tailscale split DNS', h('div', { class: 'pform' },
    h('p', { class: 'muted' }, 'Devices on the tailnet ask these name servers for these domains. Point your domain at the DNS server that holds the Tailscale view.'),
    Object.keys(cur).length ? list : h('p', { class: 'muted small' }, 'No split DNS yet.'),
    h('div', { class: 'grid' }, fld('Domain', domain), fld('Name server', ns))), [
    { label: 'Close', value: null },
    { label: 'Save', primary: true, value: () => api(`api/servers/${s.id}/split-dns`, { method: 'PUT', json: { domain: domain.value.trim(), nameservers: ns.value.split(',').map((x) => x.trim()).filter(Boolean) } }) }], true);
  if (r) toast('Split DNS saved');
}

// ------------------------------------------------------------------ dynamic DNS
async function showDdns(page) {
  const d = await api('api/ddns');
  const unifi = S.servers.filter((s) => s.kind === 'unifi');
  const entries = (await api('api/entries')).items.filter((e) => Object.values(e.records).flat().some((r) => r.source === 'publicip' || r.source === 'publicip6'));
  const detect = h('select', { class: 't', disabled: !isAdmin() },
    h('option', { value: 'auto', selected: d.detect === 'auto' ? true : null }, 'Ask an address service (ipify, icanhazip)'),
    unifi.map((s) => h('option', { value: `unifi:${s.id}`, selected: d.detect === `unifi:${s.id}` ? true : null }, `The WAN address of ${s.name}`)),
    h('option', { value: 'url', selected: d.detect.startsWith('http') ? true : null }, 'This page…'));
  const url = h('input', { class: 't', value: d.detect.startsWith('http') ? d.detect : '', placeholder: 'https://… (answers with the address alone)', hidden: !d.detect.startsWith('http') });
  const minutes = h('input', { class: 't', type: 'number', min: 0, max: 1440, value: d.minutes, disabled: !isAdmin() });
  detect.onchange = () => { url.hidden = detect.value !== 'url'; if (detect.value !== 'url') save(); };
  const save = async () => { try { await api('api/ddns', { method: 'PUT', json: { detect: detect.value === 'url' ? url.value.trim() : detect.value, minutes: +minutes.value } }); toast('Saved'); } catch (e) { fail(e); } };
  url.onchange = save; minutes.onchange = save;
  const now = async (push) => { try { const r = await api('api/ddns/run', { method: 'POST', json: { push } }); toast(r.changed ? `New address: ${r.ipv4 || ''} ${r.ipv6 || ''}` : push ? 'Pushed' : `Unchanged: ${r.ipv4 || r.ipv6 || 'none found'}`); onRoute(); } catch (e) { fail(e); } };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Dynamic DNS')),
    h('div', { class: 'box' }, h('h2', null, icon('globe'), 'The public address'),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'IPv4'), h('div', { class: 'v' }, h('code', null, d.ipv4 || 'not found yet'))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'IPv6'), h('div', { class: 'v' }, h('code', null, d.ipv6 || 'none'))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'Checked'), h('div', { class: 'v' }, d.checkedAt ? ago(new Date(+d.checkedAt * 1000).toISOString()) : 'never', d.error ? h('span', { class: 'warn' }, ` · ${d.error}`) : null)),
      canEdit() ? h('p', null, h('button', { class: 'pillbtn', onclick: () => now(false) }, icon('sync', 's'), 'Check now'), ' ',
        h('button', { class: 'pillbtn', onclick: () => now(true) }, icon('upload', 's'), 'Push the records now')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'How'),
      h('div', { class: 'grid' }, fld('Find the address with', detect), fld('Every (minutes, 0: never on its own)', minutes)), url,
      h('p', { class: 'muted small' }, 'When it changes, every record set to "Public address" takes it, and the servers that hold those records are updated straight away.')),
    h('div', { class: 'box' }, h('h2', null, icon('list'), `Records that follow it (${entries.length})`),
      entries.length ? h('table', { class: 't' }, entries.map((e) => h('tr', null, h('td', { class: 'nm' }, e.name),
        h('td', null, Object.entries(e.records).map(([v, rs]) => rs.filter((r) => r.source && r.source.startsWith('publicip')).map((r) => [h('span', { class: 'muted small' }, `${viewOf(v).name}: `), recChip(r)]))))))
        : h('p', { class: 'muted' }, 'None yet. In an entry, set a record\'s value to "Public address" (usually in the External view).')));
}

// ------------------------------------------------------------------ history
async function showHistory(page) {
  const items = (await api('api/history?limit=300')).items;
  const LABEL = { edit: 'Changed', delete: 'Deleted', push: 'Pushed', resolve: 'Resolved', import: 'Imported', server: 'Server', ddns: 'Dynamic DNS', tailscale: 'Tailscale' };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'History')),
    items.length ? h('div', { class: 'hist' }, items.map((x) => h('div', { class: `hrow ${x.ok ? '' : 'bad'}` },
      h('div', { class: 'hmeta' }, h('b', null, LABEL[x.action] || x.action), x.server ? ` · ${x.server}` : '', h('span', { class: 'muted small' }, ` · ${x.user || 'ioDNS'} · ${new Date(x.at + (x.at.endsWith('Z') ? '' : 'Z')).toLocaleString()}`)),
      h('pre', { class: 'hdetail' }, x.detail))))
      : h('div', { class: 'empty' }, icon('history'), h('p', null, 'Nothing yet.')));
}

// ------------------------------------------------------------------ settings
const SUITE_TABS = { people: 'People', apps: 'Apps', servers: 'Servers', keys: 'Keys' };
async function showSettings(page, r) {
  const tabs = [['account', 'Account'], ['display', 'Display'], ['views', 'Views'], ['data', 'Export and import'],
    ...(S.status.isAdmin ? [['app', 'This app']] : []), ...(S.user.suiteAdmin ? Object.entries(SUITE_TABS) : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, app: setApp, views: setViews, data: setData, people: setSuite, apps: setSuite, servers: setSuite, keys: setSuite }[r.tab] || setAccount)(body, r);
}
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast });
}
async function setDisplay(el) {
  const ui = await accountUi();
  el.append(ui.box('theme', 'Appearance', ui.themeRow(frame.themeChoice(), frame.applyTheme)));
}
async function setViews(el) {
  await loadOverview();
  el.append(h('div', { class: 'box' }, h('h2', null, icon('layers'), 'Views'),
    h('p', { class: 'muted' }, 'A view is one answer to "who is asking": the house, the internet, the tailnet… Each server answers for one view, and each entry can hold different records in each.'),
    h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'What it is'), h('th', null, 'Servers'), h('th', null, 'Entries'), h('th', null)),
      S.views.map((v) => {
        const nm = h('input', { class: 't', value: v.name, disabled: !isAdmin(), onchange: async (e) => { try { await api(`api/views/${v.id}`, { method: 'PATCH', json: { name: e.target.value } }); await loadOverview(); toast('Saved'); } catch (x) { fail(x); } } });
        const ds = h('input', { class: 't', value: v.description, disabled: !isAdmin(), onchange: async (e) => { try { await api(`api/views/${v.id}`, { method: 'PATCH', json: { description: e.target.value } }); toast('Saved'); } catch (x) { fail(x); } } });
        return h('tr', null, h('td', null, nm), h('td', null, ds), h('td', null, v.servers), h('td', null, v.entries),
          h('td', null, isAdmin() ? h('button', { class: 'pillbtn noic danger tiny', onclick: async () => {
            if (!await confirmDialog('Delete the view', `Delete ${v.name} and its records in the master list (${v.entries} entries have some)? Its servers are kept, without a view.`, 'Delete', true)) return;
            try { await api(`api/views/${v.id}`, { method: 'DELETE' }); onRoute(); } catch (x) { fail(x); }
          } }, 'Delete') : null));
      })),
    isAdmin() ? h('p', null, h('button', { class: 'pillbtn', onclick: async () => {
      const name = h('input', { class: 't', placeholder: 'Guests' });
      const r = await dialog('New view', fld('Name', name), [{ label: 'Cancel', value: null }, { label: 'Add', primary: true, value: () => api('api/views', { method: 'POST', json: { name: name.value.trim() } }) }]);
      if (r) onRoute();
    } }, icon('add', 's'), 'New view')) : null));
}
async function setData(el) {
  const file = h('input', { type: 'file', accept: '.json,application/json' });
  const replace = h('input', { type: 'checkbox' });
  put(el, h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'), h('p', null, 'The master list (views and entries) as a JSON file.'),
    h('p', null, h('a', { class: 'pillbtn', href: 'api/export', download: 'iodns.json' }, icon('download', 's'), 'Download'))),
  canEdit() ? h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import a file'), h('p', null, 'An ioDNS export back in: entries are added, or replaced when the name is already here.'),
    h('div', { class: 'pform' }, file, h('label', { class: 'check' }, replace, ' Remove the entries that are not in the file'),
      h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
        const f = file.files[0]; if (!f) { toast('Pick a file'); return; }
        try { const data = JSON.parse(await f.text()); const r = await api('api/import/file', { method: 'POST', json: { data, replace: replace.checked } }); offerPush(null, `${r.entries} entries imported${r.removed ? `, ${r.removed} removed` : ''}`); } catch (e) { fail(e); }
      } }, icon('upload', 's'), 'Import')))) : null);
}
/** Settings › This app (its admins): every setting this app declares, in the suite's one home for them. The same
    block in every app, served by iosuite_shared (frame.appSettings). */
function setApp(el) { return frame.appSettings(el, { toast }); }
function setSuite(el, r) { return frame.suitePanel(el, r); }
// ------------------------------------------------------------------ sign-in
function showSignIn() { frame.signInScreen({ api, name: 'DNS', first: !S.status.usersExist }); }

// ------------------------------------------------------------------ start
async function start() {
  frame.applyTheme();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
  S.status = await api('api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('api/auth/me')).settings || {}; } catch { S.settings = {}; }
  frame.themeFromAccount(S.settings);
  drawUser();
  await loadOverview();
  $('#newbtn').onclick = () => editEntry(null);
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  let t;
  $('#q').addEventListener('input', (e) => { clearTimeout(t); t = setTimeout(() => { S.q = e.target.value.trim(); if (S.redraw) S.redraw(); }, 150); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin, .dialog-back')) return;
    if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
    else if (e.key === 'n' && canEdit()) { e.preventDefault(); editEntry(null); }
  });
  addEventListener('hashchange', () => { S.redraw = null; onRoute(); });
  await onRoute();
  loadSuite();
  // what changed elsewhere shows by itself: another admin, an assistant (the suite's one live stream)
  import(new URL('api/live.js', document.baseURI).href)
    .then((live) => live.keepFresh('iodns', () => onRoute(), { when: () => ['records', 'history', 'ddns'].includes(route().view) }))
    .catch(() => { /* no stream on this server */ });
}
start().catch(fail);

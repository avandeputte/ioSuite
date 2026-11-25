import { S, api, confirmDialog, copyRow, downloadProfile, fail, h, icon, loadMeta, toast } from './core.js';
import { applyTheme, canOwn, drawUser, newBook, themeChoice } from './shell.js';
import { onRoute } from './main.js';
import { profileScope as scopeSelect } from '../../api/auth/ui.js';
import * as frame from '../../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { accountUi, fld } from '../../api/auth/frame.js';
export { accountUi };

// ------------------------------------------------------------------ settings
export async function showSettings(page, r) {
  const tabs = [['account', 'Account'], ['display', 'Display'], ['devices', 'Apps and devices'], ['books', 'Address books'],
    ...(S.user.isAdmin ? [['app', 'This app']] : []), ...(S.user.suiteAdmin ? Object.entries(SUITE_TABS) : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, app: setApp, devices: setDevices, books: setBooks, people: setSuite, apps: setSuite, servers: setSuite, keys: setSuite }[r.tab] || setAccount)(body, r);
}
const kv = (k, v) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k), h('div', { class: 'v', style: { flex: 1 } }, typeof v === 'string' ? copyRow(v) : v));

/** Settings › Account: display name, email and password, then the app passwords: iosuite_shared's panels (the same in every io app). */
export async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast, syncOnly: 'Contacts apps only (CardDAV, LDAP)' });
}

/** Settings › Display: the theme, saved with the account. The sort order and the fields shown are at the top of the list. */
export async function setDisplay(el) {
  const ui = await accountUi();
  el.append(ui.box('theme', 'Appearance', ui.themeRow(themeChoice(), applyTheme)));
}

/** The "Set up" choice of the profile box: this app only, or every app that syncs (iosuite_shared's suite profile),
 * offered when the account may use two or more of them. Fields marked data-own belong to this app's own profile. */
export const profileScope = (apps, own) => { const s = scopeSelect(apps, own, { class: 't' }); return s && fld('Set up', s); };

/** Settings › Apps and devices: how to connect each kind of app (the app passwords themselves are on Settings › Account). */
export async function setDevices(el) {
  const info = await api('api/connect');
  const suiteApps = S.user.passwordless ? [] : (await api('api/apple-profile/suite').catch(() => ({ apps: [] }))).apps;
  const isApple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  const plabel = h('input', { class: 't', name: 'label', value: /iPad/.test(navigator.userAgent) ? 'iPad' : /Macintosh/.test(navigator.userAgent) ? 'Mac' : 'iPhone', style: 'max-width:200px' });
  const how = (summary, ...kids) => h('details', null, h('summary', { class: 'lnk' }, summary), ...kids);
  const subs = h('div');
  el.append(...[
    S.user.passwordless ? null : h('div', { class: 'box' }, h('h2', null, icon('devices'), 'iPhone, iPad and Mac'),
      h('p', null, 'A profile that adds your contacts and, if you like, a birthday calendar in one step.'),
      h('form', { method: 'POST', action: 'api/apple-profile', class: 'pform', onsubmit: downloadProfile },
        profileScope(suiteApps, 'ioContact'),
        fld('Device name', plabel),
        fld('Password', h('select', { class: 't', name: 'password' }, h('option', { value: 'new' }, 'Include a new app password'), h('option', { value: 'ask' }, 'Ask on the device'))),
        h('div', { 'data-own': '' }, fld('Birthday calendar', h('select', { class: 't', name: 'calendar' }, h('option', { value: 'family' }, 'Family birthdays'), h('option', { value: 'all' }, 'Birthdays from all my books'), h('option', { value: 'none' }, 'No calendar')))),
        info.ldap.enabled ? h('label', { class: 'check', 'data-own': '' }, h('input', { type: 'checkbox', name: 'ldap', value: 'true' }), ' Also the LDAP directory (Mail on a Mac)') : null,
        h('p', null, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Download the profile'))),
      how('How to install', h('p', { class: 'muted small' }, isApple ? 'Open the download, then Settings › Profile Downloaded › Install.' : 'Download it in Safari on the iPhone or iPad, then Settings › Profile Downloaded › Install. On a Mac: open the file, then System Settings › Privacy & Security › Profiles.',
        ' iOS shows the profile as “Not Verified”: that is expected. Revoke its app password under Settings › Account if the device is lost.',
        suiteApps.length > 1 ? ' A profile for all apps holds one app password per app; revoke each one in its own app.' : null))),
    h('div', { class: 'box' }, h('h2', null, icon('book'), 'Contacts apps (CardDAV)'),
      h('p', null, 'Two-way sync with your user name and an app password (Settings › Account).'),
      kv('Server', info.server), kv('User name', info.user), kv('CardDAV address', info.carddav),
      how('Address of each address book', info.books.map((b) => kv(b.name, b.url))),
      how('How to connect', h('p', { class: 'muted small' }, 'Apple Contacts: Settings › Contacts › Accounts › Add Account › Other › Add CardDAV Account. Android: DAVx⁵. Also Thunderbird, Evolution, GNOME, KDE.'))),
    subs,
    info.ldap.enabled ? h('div', { class: 'box' }, h('h2', null, icon('mail'), 'Mail apps (LDAP directory)'),
      h('p', null, 'Read-only address lookup for mail apps, desk phones and printers. Sign in with an app password; plain LDAP, so keep it on your own network.'),
      kv('Host', info.ldap.host), kv('Port', String(info.ldap.port)), kv('Base DN', info.ldap.base), kv('Bind DN', info.ldap.bindDn)) : null,
    S.status.mcp ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'),
      h('p', null, 'Give the assistant its own app password (not “Contacts apps only”), sent as a Bearer token.'),
      kv('MCP address', info.mcp),
      how('Setup for Claude Code and JSON-configured apps',
        copyRow(`claude mcp add --transport http iocontact ${info.mcp} --header "Authorization: Bearer APP-PASSWORD"`),
        copyRow(JSON.stringify({ mcpServers: { iocontact: { command: 'npx', args: ['-y', 'mcp-remote', info.mcp, '--header', 'Authorization: Bearer APP-PASSWORD'] } } }))))
      : (S.user.suiteAdmin ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'), h('p', { class: 'muted' }, 'Off. Turn it on in ', h('a', { class: 'lnk', href: '#/settings/apps' }, 'Settings › Apps'), '.')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('link'), 'Other apps (REST API)'),
      h('p', null, 'JSON, vCard or jCard with your user name and an app password. ', h('a', { class: 'lnk', href: 'api/docs', target: '_blank' }, 'API documentation')),
      copyRow(`curl -u ${info.user}:APP-PASSWORD -H 'Accept: application/vcard+json' ${info.server}/api/contacts?q=smith`))].filter(Boolean));
  (await accountUi()).mountFeeds(subs, { toast, icon: 'devices', title: 'Family birthday calendar',
    intro: 'A calendar subscription with birthdays and anniversaries, for calendar apps. Anyone with a link can read the dates, so make one per app or device and stop it when it is no longer used.' }).catch(fail);
}

export async function setBooks(el) {
  el.append(h('p', null, canOwn() ? h('button', { class: 'pillbtn primary', onclick: newBook }, icon('add', 's'), 'New address book') : null),
    h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Who sees it'), h('th', null, 'Contacts'), h('th', null, 'Colour'), h('th')),
      S.books.map((b) => {
        const save = async (body) => { try { await api(`api/books/${b.id}`, { method: 'PATCH', json: body }); await loadMeta(); toast('Saved'); } catch (e) { fail(e); } };
        const name = h('input', { class: 't', value: b.name, disabled: !b.writable, onchange: (e) => save({ name: e.target.value }) });
        const col = h('input', { type: 'color', value: b.color || (b.shared ? '#8e44d6' : '#0b8a9e'), disabled: !b.writable, onchange: (e) => save({ color: e.target.value }) });
        return h('tr', null, h('td', null, name), h('td', null, b.shared ? 'Everyone' : 'Only you'), h('td', null, b.count), h('td', null, col),
          h('td', { style: { whiteSpace: 'nowrap' } },
            b.writable && (!b.shared || S.user.role === 'admin') ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
              if (!await confirmDialog('Delete address book', `Delete ${b.name} and its ${b.count} contacts?`, 'Delete', true)) return;
              try { await api(`api/books/${b.id}`, { method: 'DELETE' }); await loadMeta(); onRoute(); } catch (e) { fail(e); }
            } }, 'Delete') : null));
      })));
}

/** Settings › People, Apps, Servers and Keys (suite admins): the people and their role in every app (here
    too), app passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by
    iosuite_shared. */
export const SUITE_TABS = { people: 'People', apps: 'Apps', servers: 'Servers', keys: 'Keys' };
/** Settings › This app (its admins): every setting this app declares, in the suite's one home for them. The same
    block in every app, served by iosuite_shared (frame.appSettings). */
function setApp(el) { return frame.appSettings(el, { toast }); }
export function setSuite(el, r) { return frame.suitePanel(el, r); }


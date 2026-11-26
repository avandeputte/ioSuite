/** Settings, one page as in every ioSuite app (Account and Display for accounts; Server for admins;
 *  People, Apps, Servers and Keys for suite admins), the Import and export page and the change log. */
import { $, h, api, state, icon, toast, fail, canWrite, fmtDate } from './core.js';
import { appSettings, applyTheme, themeChoice } from '../../api/auth/frame.js';  // the appearance: the suite's one choice

/** Settings › Account (with the app passwords) and Display: iosuite_shared's panels, the same in every io app. */
const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
async function accountPanel() {
  const ui = await accountUi(), el = h('div'), pw = h('div');
  await ui.mountAccount(el, { toast });
  await ui.mountAppPasswords(pw, { toast });
  return [el, pw];
}
async function displayPanel() { const ui = await accountUi(); return ui.box('theme', 'Appearance', ui.themeRow(themeChoice(), applyTheme)); }

/** Settings › People, Apps, Servers and Keys (suite admins): the people and their role in every app (here
 *  too), app passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by
 *  iosuite_shared. */
async function suitePanel(tab, sub) {
  const el = h('div');
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { return h('p.err', `The panel did not load: ${e.message}`); }
  await ui.mount(el, { tab, sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${tab}/${x}`) });
  return el;
}

/** A page as iopix lays one out: the title with its icon tile, the tabs under it (the tab is in the address:
 *  #/settings/display), then the tab's boxes. */
function pageTitle(text, ic, hue, sub = '') { return h('h1.ptitle', h('span.pic', { style: `--hue:${hue}` }, icon(ic)), text, sub ? h('span.muted', sub) : null); }
async function tabbedPage(base, title, ic, hue, tabs, tab) {
  const main = $('#main');
  main.textContent = '';
  const cur = tabs.find((t) => t[0] === tab) || tabs[0];
  const inner = h('div.pagein', pageTitle(title, ic, hue),
    tabs.length > 1 ? h('div.stabs', { role: 'tablist' }, tabs.map(([k, label]) => h('a.pillbtn' + (k === cur[0] ? '.on' : ''), { href: `#/${base}/${k}`, role: 'tab', 'aria-selected': String(k === cur[0]) }, label))) : null);
  main.append(h('div.page', inner));
  try { for (const b of await cur[2]()) if (b) inner.append(b); } catch (e) { inner.append(h('p.err', e.message)); }
}

/** Settings: Account and Display for accounts; This app for its admins; and the suite's own tabs (People, Apps, Servers, Keys) for
 *  suite admins. Before any account exists, only Display. */
export function renderSettings(tab, sub) {
  const tabs = [];
  if (state.me.user) tabs.push(['account', 'Account', accountPanel]);
  tabs.push(['display', 'Display', async () => [await displayPanel()]]);
  // This app (its admins): every setting ioNote declares, the same block in every app (frame.appSettings)
  if (state.me.isAdmin) tabs.push(['app', 'This app', async () => { const el = h('div'); await appSettings(el, { toast }); return [el]; }]);
  if (state.me.isSuiteAdmin) {
    for (const [k, l] of [['people', 'People'], ['apps', 'Apps'], ['servers', 'Servers'], ['keys', 'Keys']]) {
      tabs.push([k, l, async () => [await suitePanel(k, sub)]]);
    }
  }
  return tabbedPage('settings', 'Settings', 'gear', 'var(--c-gray)', tabs, tab);
}

/** Import and export (#/import): your own notes as Markdown with their pictures plus notes.json, and back. */
export function renderImport() {
  const main = $('#main');
  main.textContent = '';
  const file = h('input', { type: 'file', accept: '.zip,.json', hidden: true, onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    toast('Importing…', 60000);
    try { const r = await api('api/import', { method: 'POST', body: fd }); toast(`Imported ${r.notes} notes, ${r.pictures} pictures, ${r.files || 0} files, ${r.folders} folders, ${r.templates || 0} templates${r.skipped ? `; ${r.skipped} were newer here` : ''}`, 6000); } catch (err) { fail(err); }
  } });
  main.append(h('div.page', h('div.pagein', pageTitle('Import and export', 'download', 'var(--c-green)'),
    h('section.sec', h('h2', 'Export'), h('p.intro', 'Your notes as Markdown files with their pictures, plus notes.json with everything.'),
      h('div.row', h('a.pillbtn', { href: 'api/export.zip' }, icon('download'), 'Export all notes'), h('a.pillbtn', { href: 'api/export.zip?trash=1' }, 'With the trash'))),
    canWrite() ? h('section.sec', h('h2', 'Import'), h('p.intro', 'A zip or notes.json from any ioNote server. Newer copies here are kept.'),
      h('div.row', h('button.pillbtn', { onclick: () => file.click() }, icon('upload'), 'Import…'), file)) : null)));
}

export async function renderChanges() {
  const main = $('#main');
  main.textContent = '';
  const tbody = h('tbody');
  const inner = h('div.pagein', pageTitle('Change log', 'history', 'var(--c-indigo)'), h('p.muted', 'Every change to a note, folder or tag, from the web app, the Mac and iPhone apps and MCP, newest first.'),
    h('table.grid', h('thead', h('tr', h('th', 'When'), h('th', 'Who'), h('th', 'What'), h('th', ''))), tbody));
  main.append(h('div.page', inner));
  if (!canWrite()) { tbody.append(h('tr', h('td', { colspan: 4 }, 'Editors only.'))); return; }
  let before = null;
  const more = h('button.pillbtn.more', { onclick: () => load() }, 'Older');
  const load = async () => {
    const r = await api('api/changes?limit=200' + (before ? '&before=' + before : ''));
    for (const c of r.changes) {
      tbody.append(h('tr', h('td.small', fmtDate(c.ts, true)), h('td', c.user), h('td', `${c.action} ${c.kind}`),
        h('td', c.kind === 'note' && c.action !== 'delete' ? h('a', { href: '#/note/' + c.uuid }, c.summary) : c.summary)));
      before = c.id;
    }
    if (r.changes.length < 200) more.remove();
  };
  inner.append(more);
  await load();
}

/* Settings: Account and Display, Money (admins), and the suite's panel. */
import * as frame from '../../api/auth/frame.js';
import { accountUi, fail, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { ago, api, fld, fmts, inp, S, store } from './core.js';
import { onRoute } from './main.js';
import { newAccountsDialog, startSync, syncLabel, watchSync } from './overview.js';
import { transferMaintenance } from './rules.js';
import { applyTheme, drawUser, refreshSummary, themeChoice } from './shell.js';

// ------------------------------------------------------------------ settings
export async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'],
    ...(adm ? [['money', 'Money']] : []),
    ...(S.status.isAdmin ? [['app', 'This app']] : []), ...(S.user.suiteAdmin ? Object.entries(SUITE_TABS) : [])];
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div', { style: { maxWidth: '900px' } }); put(page, body);
  await ({ account: setAccount, display: setDisplay, app: setApp, money: setMoney, people: setSuite, apps: setSuite, servers: setSuite, keys: setSuite }[r.tab] || setAccount)(body, r);
}

/** Settings › Money (admins): the household's currency, and Monarch Money: whether its sign-in is kept (in the
    suite's keys and tokens: never here), the last syncs, Sync now, a code by hand, the automatic sync. */
async function setMoney(el) {
  const [st, set] = await Promise.all([api('api/monarch'), api('api/settings')]);
  const cur = inp(set.currency, { maxlength: 3, style: { textTransform: 'uppercase', width: '90px' } });
  cur.onchange = async () => { try { await api('api/settings', { method: 'PUT', json: { currency: cur.value } }); fmts.length = 0; Object.keys(fmts).forEach((k) => delete fmts[k]); await refreshSummary(); toast('Saved'); } catch (e) { fail(e); } };
  put(el, h('div', { class: 'box' }, h('h2', null, icon('bank'), 'The household’s currency'),
    h('p', { class: 'muted' }, 'The net worth and every total are in this currency; an account or a holding in another is converted at the day’s rate (Yahoo Finance).'),
    fld('Currency (USD, EUR, GBP…)', cur)));
  const keysLink = S.user.suiteAdmin ? h('a', { class: 'lnk', href: '#/settings/keys' }, 'Settings › Keys') : 'Settings › Keys (a suite admin)';
  const K = st.keys || {};
  const keyRow = (k, l) => h('li', null, icon(K[k] ? 'check' : 'close', K[k] ? 'ok' : 'warn'), l, K[k] ? '' : ': not set');
  const last = st.last;
  const code = inp('', { inputmode: 'numeric', maxlength: 6, placeholder: '123456', style: { width: '110px' } });
  const auto = h('input', { type: 'checkbox', checked: set.monarchAuto ? true : null, onchange: async (e) => { try { await api('api/settings', { method: 'PUT', json: { monarchAuto: e.target.checked } }); toast('Saved'); } catch (x) { fail(x); } } });
  if (st.running) watchSync();
  put(el, h('div', { class: 'box' }, h('h2', null, icon('sync'), 'Monarch Money'),
    h('p', { class: 'muted' }, 'ioMoney copies in Monarch Money’s accounts, balances, transactions, holdings and bills (houses from Zillow and vehicles included) every ', st.every, ' hours. It only reads: nothing is changed in Monarch. The sign-in is kept with the suite’s keys and tokens, in ', keysLink, ':'),
    h('ul', { class: 'keylist' }, keyRow('monarch_email', 'Monarch Money email'), keyRow('monarch_password', 'Monarch Money password'),
      keyRow('monarch_mfa_secret', 'Monarch Money authenticator key (the text under the QR code when you set up the authenticator app in Monarch)'),
      h('li', null, icon(K.monarch_token ? 'check' : 'close', K.monarch_token ? 'ok' : 'muted'), K.monarch_token ? 'Signed in (a session is kept)' : 'Not signed in yet')),
    st.running ? h('p', { class: 'note syncing' }, h('span', { class: 'spin' }), ' Syncing: ', h('span', { 'data-syncstage': '' }, syncLabel(st.progress)),
      h('small', null, ` · started ${ago(st.progress && st.progress.started)}. It goes on if you leave this page.`))
      : last ? h('p', { class: `note ${last.ok ? '' : 'bad'}` }, last.ok ? `Last sync ${ago(last.finished || last.started)}: ${last.message}` : `The last sync (${ago(last.started)}) did not work: ${last.message}`) : null,
    S.sum.monarch && S.sum.monarch.newAccounts ? h('p', { class: 'note warnnote' }, icon('warning', 's'), h('span', { class: 'grow' }, `${S.sum.monarch.newAccounts} account${S.sum.monarch.newAccounts === 1 ? '' : 's'} from Monarch wait${S.sum.monarch.newAccounts === 1 ? 's' : ''} for you to say whether ${S.sum.monarch.newAccounts === 1 ? 'it is' : 'they are'} new.`),
      h('button', { class: 'pillbtn primary', onclick: () => newAccountsDialog() }, 'Review')) : null,
    h('div', { class: 'chiprow' },
      h('button', { class: 'pillbtn primary', disabled: st.running || !st.configured ? true : null, onclick: (e) => startSync(false, e.currentTarget) }, icon('sync'), h('span', null, st.running ? 'Syncing…' : 'Sync now')),
      h('button', { class: 'pillbtn', disabled: st.running || !st.configured ? true : null, onclick: (e) => startSync(true, e.currentTarget) }, h('span', null, 'Sync two years again')),
      K.monarch_token ? h('button', { class: 'pillbtn', onclick: async () => { await api('api/monarch/session', { method: 'DELETE' }); toast('The next sync signs in again'); onRoute(); } }, 'Sign in again') : null),
    h('label', { class: 'check', style: { marginTop: '12px' } }, auto, `Sync every ${st.every} hours on its own`),
    !K.monarch_mfa_secret && K.monarch_email ? h('div', { style: { marginTop: '14px' } }, h('p', { class: 'muted small' }, 'No authenticator key kept: sign in once with the code your authenticator app shows now.'),
      h('div', { class: 'chiprow' }, code, h('button', { class: 'pillbtn', onclick: async () => { try { await api('api/monarch/code', { method: 'POST', json: { code: code.value } }); toast('Signed in'); onRoute(); } catch (e) { fail(e); } } }, 'Sign in with the code'))) : null,
    st.history && st.history.length > 1 ? h('details', { style: { marginTop: '14px' } }, h('summary', { class: 'muted small' }, 'The last syncs'),
      h('ul', { class: 'keylist' }, st.history.map((x) => h('li', null, icon(x.ok ? 'check' : 'close', x.ok ? 'ok' : 'warn'), `${new Date(x.started).toLocaleString()}: ${x.message || ''}`)))) : null));
  put(el, h('div', { class: 'box' }, h('h2', null, icon('link'), 'Maintenance'),
    h('p', { class: 'muted' }, 'Go through every transaction and link the transfers between your own accounts (card payments, bank transfers, loan payments), then see what still looks like one, with why it was not linked.'),
    h('div', { class: 'chiprow' }, h('button', { class: 'pillbtn', onclick: () => transferMaintenance() }, icon('link'), h('span', null, 'Link transfers')))));
}

// ------------------------------------------------------------------ the tabs every app has: Account, Display, the suite's panel
/** Settings › Account: display name, email and password, then the app passwords: iosuite_shared's panels (the same in every io app). */
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  put(el, pw);
  await ui.mountAppPasswords(pw, { toast });
}

/** Settings › Display: the theme, saved with the account. */
async function setDisplay(el) {
  const ui = await accountUi();
  put(el, ui.box('theme', 'Appearance', ui.themeRow(themeChoice(), applyTheme)));
}

/** Settings › People, Apps, Servers and Keys (suite admins): the people, their role in every app, app
    passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite_shared. */
const SUITE_TABS = { people: 'People', apps: 'Apps', servers: 'Servers', keys: 'Keys' };
/** Settings › This app (its admins): every setting this app declares, in the suite's one home for them. The same
    block in every app, served by iosuite_shared (frame.appSettings). */
function setApp(el) { return frame.appSettings(el, { toast }); }
function setSuite(el, r) { return frame.suitePanel(el, r); }

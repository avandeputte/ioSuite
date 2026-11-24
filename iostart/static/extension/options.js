/* The settings page: signing in (with the name and password typed here, or by asking the start page, where whoever is
 * signed in says yes; either way the extension is handed an app password of its own), the state of the sync, signing
 * out. */
'use strict';
let waiting = null;  // the sign-in under way: {stop}

async function show() {
  const { account, status, sync } = await ext.storage.local.get(['account', 'status', 'sync']);
  $('in').hidden = !account;
  $('out').hidden = !!account;
  if (!account) return;
  const d = describe(account, status);
  $('dot').className = 'dot ' + d.cls;
  $('state').textContent = d.text;
  const vivaldi = sync && String(sync.layout || '').startsWith('vivaldi');
  $('who').textContent = `Signed in as ${account.user} at ${account.server}` + (vivaldi ? ' · lined up for Vivaldi' : '') + (account.canWrite === false ? '. This account can read the bookmarks, not change them: changes made here are not kept.' : '');
}

function address(text) {
  let t = (text || '').trim();
  if (!t) throw new Error('Type the address of your start page');
  if (!/^https?:\/\//i.test(t)) t = 'https://' + t;
  let u;
  try { u = new URL(t); } catch (e) { throw new Error('That is not an address'); }
  return (u.origin + u.pathname).replace(/\/+$/, '');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** What both ways of signing in begin with: the address, and the browser's leave to reach it. */
async function begin() {
  $('error').textContent = '';
  let server;
  try { server = address($('server').value); } catch (e) { $('error').textContent = e.message; return null; }
  const mode = document.querySelector('input[name="mode"]:checked').value;
  // the browser asks whether this extension may talk to that one site (asked here, on the click)
  const granted = await ext.permissions.request({ origins: [new URL(server).origin + '/*'] }).catch(() => false);
  if (!granted) { $('error').textContent = 'The browser did not allow the extension to reach that address.'; return null; }
  return { server, mode };
}

async function clientName() {
  const [top] = await ext.bookmarks.getTree();
  return 'ioStart Bookmarks in ' + (IoSync.isVivaldi(top) ? 'Vivaldi' : browserName());
}

async function signedIn(server, mode, user, password) {
  await ext.storage.local.remove(['sync', 'status']);
  await ext.storage.local.set({ account: { server, user, password }, mode });
  $('password').value = $('code').value = '';
  $('codebox').hidden = true;
  ext.runtime.sendMessage('sync').catch(() => {});
}

function busy(on, text) {
  $('signin').disabled = $('ask').disabled = on;
  $('wait').textContent = on ? text : '';
}

/** With the name and password typed here: the start page checks them once and answers with an app password of this
 * extension's own, for sync only. An account with two-step sign-in is asked for its code as well. */
async function signIn() {
  const b = await begin();
  if (!b) return;
  const name = $('name').value.trim(), password = $('password').value, code = $('code').value.trim();
  if (!name || !password) { $('error').textContent = 'Type your name and your password, or ask the start page instead.'; return; }
  busy(true, 'Signing in…');
  try {
    const r = await fetch(b.server + '/api/auth/device', {
      method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, password, code, label: await clientName(), scope: 'dav' }),
    }).catch(() => null);
    if (!r) throw new Error('That address cannot be reached.');
    const d = await r.json().catch(() => ({}));
    if (r.status === 401 && d.twoStep) {
      $('codebox').hidden = false;
      $('code').focus();
      throw new Error(code ? 'That code is not right.' : 'Type the code from your code app as well.');
    }
    if (r.status === 404 || r.status === 405) throw new Error('That address did not answer as an ioStart page (signing in here needs ioSuite 4.2 or later).');
    if (!r.ok || !d.password) throw new Error(d.detail || `The start page answered with an error (${r.status}).`);
    await signedIn(b.server, b.mode, d.name, d.password);
  } catch (e) {
    $('error').textContent = e.message;
  } finally {
    busy(false);
    show();
  }
}

/** Without a password typed here: the start page asks whoever is signed in there, in a tab, to say yes. */
async function ask() {
  const b = await begin();
  if (!b) return;
  const { server, mode } = b;
  busy(true, 'Asking the start page…');
  let tab = null, stopped = false;
  waiting = { stop: () => { stopped = true; } };
  try {
    const nc = server + '/dav/nextcloud/index.php/login/v2';
    const r = await fetch(`${nc}?client=${encodeURIComponent(await clientName())}`, { method: 'POST', credentials: 'omit' }).catch(() => null);
    if (!r || !r.ok) throw new Error(r ? `That address did not answer as an ioStart page (${r.status}).` : 'That address cannot be reached.');
    const flow = await r.json();
    // the addresses the start page answers with are as it sees itself; this goes by the address typed here (asked at
    // the address for devices, the page is sent on to where the start page's pages are)
    const page = String(flow.login || '').split('/').pop(), token = flow.poll && flow.poll.token;
    if (!page || !token) throw new Error('That address did not answer as an ioStart page.');
    tab = await ext.tabs.create({ url: `${nc}/flow/${encodeURIComponent(page)}` });
    $('wait').textContent = 'Say yes in the tab that opened…';
    let got = null;
    for (let i = 0; i < 600 && !stopped && !got; i++) {  // 20 minutes, as long as the start page keeps the question
      await sleep(2000);
      const p = await fetch(nc + '/poll', { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) }).catch(() => null);
      if (p && p.ok) got = await p.json();
    }
    if (!got) throw new Error('Nobody said yes in time. Try again.');
    await signedIn(server, mode, got.loginName, got.appPassword);
    if (tab) ext.tabs.remove(tab.id).catch(() => {});
  } catch (e) {
    $('error').textContent = e.message;
  } finally {
    waiting = null;
    busy(false);
    show();
  }
}

$('signin').addEventListener('click', signIn);
$('ask').addEventListener('click', ask);
for (const id of ['server', 'name', 'password', 'code']) $(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') signIn(); });
$('sync').addEventListener('click', async () => {
  $('sync').disabled = true;
  $('state').textContent = 'Syncing…';
  await ext.runtime.sendMessage('sync').catch(() => {});
  $('sync').disabled = false;
  show();
});
$('open').addEventListener('click', async () => {
  const { account } = await ext.storage.local.get('account');
  ext.tabs.create({ url: account.server + '/#/bookmarks' });
});
$('signout').addEventListener('click', async () => {
  const { account } = await ext.storage.local.get('account');
  await ext.storage.local.remove(['account', 'sync', 'status', 'mode']);
  ext.runtime.sendMessage('signed-out').catch(() => {});
  // the app password goes back to the start page, so it is not left in Settings › Account for nothing
  if (account) fetch(account.server + '/api/auth/device', { method: 'DELETE', credentials: 'omit', headers: { Authorization: 'Basic ' + btoa(unescape(encodeURIComponent(`${account.user}:${account.password}`))) } }).catch(() => {});
  if (account) $('server').value = account.server;
  show();
});
ext.storage.onChanged.addListener(show);
show();

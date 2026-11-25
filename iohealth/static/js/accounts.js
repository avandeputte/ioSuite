import * as frame from '../../api/auth/frame.js';  // what every app's page has (iosuite_shared/static/frame.js)
import { toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';

// ---------- accounts: sign-in, the account menu, Settings › Account (people, roles and proxy sign-in: Settings › People) ----------
// The same as every other io app (iosuite_shared's frame.js): accounts live in the Shared ioSuite database, so one
// sign-in serves every app on the domain. Health data is private: nothing shows until someone signs in.

export let me = { user: null, usersExist: false, isAdmin: false };
export const isAdmin = () => !!me.isAdmin;

/** The page's client, as the shared parts want it: `json` is sent as JSON, and an error carries the server's words. */
export async function authApi(path, { method = 'GET', json } = {}) {
  const r = await fetch(path, { method, credentials: 'same-origin', headers: json ? { 'Content-Type': 'application/json' } : {},
    body: json ? JSON.stringify(json) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || data.detail || r.statusText);
  return data;
}

export async function loadMe() {
  try { me = await authApi('api/auth/me'); } catch { me = { user: null, usersExist: false, isAdmin: false }; }
  return me;
}

/** The sign-in screen, the suite's: a tile per account (one click for an account without a password, a password for
 *  the others), "Other" for a name typed in, and the form that makes the admin while the suite has no account yet.
 *  ioHealth shows nothing else until someone signs in, so there is no way past it. */
export function signIn() {
  frame.signInScreen({ api: authApi, name: 'Health', first: !me.usersExist });
}

export function renderUserMenu() {
  const el = frame.$('#usermenu');
  if (!el) return;
  if (!me.user) {
    el.replaceChildren(h('button', { class: 'pillbtn noic', onclick: () => signIn() }, me.usersExist ? 'Sign in' : 'Set up'));
    return;
  }
  frame.userMenu(el, me.user, authApi, (close) => [frame.themeEntry(frame.applyTheme, close)]);
}

// ---- Settings › Account

export const accountUi = frame.accountUi;
/** Settings › Account: display name, email and password, iosuite_shared's panel (the same in every io app). */
export async function setAccount() {
  const el = h('div');
  await (await accountUi()).mountAccount(el, { toast, onSaved: (u) => { Object.assign(me.user, u); renderUserMenu(); } });
  return [el];
}

// ---- Settings › People, Apps, Servers and Keys (suite admins): the people and their role in every app
// (here too), app passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite_shared.

export async function suitePanel(tab, sub) {
  const el = h('div');
  await frame.suitePanel(el, { tab, sub }, 'error');
  return [el];
}

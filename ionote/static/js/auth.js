/** Signing in and the account menu: the suite's, the same screen and menu in every io app
 *  (iosuite_shared/static/frame.js). Notes are private to each account, so nothing shows until someone signs in. */
import { $, api, state } from './core.js';
import * as frame from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';

export async function loadMe() {
  state.me = await api('api/auth/me');
  return state.me;
}

/** The sign-in screen: a tile per account (one click for an account without a password, a password for the others),
 *  "Other" for a name typed in, and the form that makes the admin while the suite has no account yet. */
export function signIn() {
  frame.signInScreen({ api: apiForFrame, name: 'Note', first: !state.me.usersExist });
}

/** The page's client as the shared parts want it (`json` sent as JSON). */
const apiForFrame = (path, { method = 'GET', json } = {}) => api(path, { method, body: json });

/** The top right, as in every ioSuite app: the account's letters, and the menu under them (the appearance,
 *  Settings, sign out); signed out, a button that signs in (or creates the admin account). */
export function renderUserMenu() {
  const el = $('#usermenu');
  const me = state.me;
  if (!me.user) {
    el.replaceChildren(h('button', { class: 'pillbtn noic', title: me.usersExist ? 'Sign in' : 'Create the admin account', onclick: () => signIn() },
      me.usersExist ? 'Sign in' : 'Set up'));
    return;
  }
  frame.userMenu(el, me.user, apiForFrame, (close) => [frame.themeEntry(frame.applyTheme, close)]);
}

/* The account menu (the gear) and the theme. */
import * as frame from '../../api/auth/frame.js';
import { applyTheme, icon, themeChoice, themeFromAccount, toast } from '../../api/auth/frame.js';
export { applyTheme, themeChoice, themeFromAccount };  // the appearance is the suite's one choice
import { h } from '../../api/auth/ui.js';
import { $, api, S, store } from './core.js';
import { arrangeStart, customize } from './customize.js';
import { enterWall } from './wall.js';

// ------------------------------------------------------------------ the account menu, the theme
/* The account menu lives in the top bar, or in the start page's first row (showHome moves it there). It is held by
   reference: when the page is drawn again the old page, and the menu inside it, are gone from the document, and
   looking it up by id would find nothing (the menu then vanished until a reload). */
export const userMenu = () => (S.userMenu = S.userMenu || $('#usermenu'));
export function drawUser() {
  const m = userMenu(); m.replaceChildren();
  if (!S.user) return;
  const btn = h('button', { class: 'iconbtn gear', title: `${S.user.displayName} · settings` }, icon('settings'));
  let menu = null;
  const closeMenu = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) closeMenu(); };
  btn.onclick = () => {
    if (menu) return closeMenu();
    const theme = themeChoice();
    // the admin tools (ioDNS…: only their admins get them) are listed here, not on the start page
    const tools = h('div', { class: 'mtools', hidden: true });
    const listTools = (apps) => {
      const t = apps.filter((a) => a.adminTool);
      tools.hidden = !t.length;
      tools.replaceChildren(h('div', { class: 'mhead muted small' }, 'Admin tools'),
        ...t.map((a) => h('a', { class: 'mi', href: a.url, onclick: closeMenu }, h('img', { src: a.icon, alt: '' }), a.name)));
    };
    if (S.allApps) listTools(S.allApps);
    else api('api/apps').then((got) => { S.allApps = got.items; listTools(got.items); }).catch(() => {});
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      h('a', { class: 'mi', href: '#/bookmarks', onclick: closeMenu }, icon('link', 's'), 'Bookmarks'),
      h('a', { class: 'mi', href: '#/news', onclick: closeMenu }, icon('rss', 's'), 'Feeds'),
      h('button', { class: 'mi', onclick: () => { closeMenu(); customize(); } }, icon('tune', 's'), 'Customize the page'),
      h('button', { class: 'mi', onclick: () => { closeMenu(); arrangeStart(); } }, icon('move', 's'), 'Arrange the page'),
      h('button', { class: 'mi', onclick: () => { closeMenu(); enterWall(); } }, icon('wall', 's'), 'Wall display'),
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; applyTheme(n); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      tools,
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('api/auth/logout', { method: 'POST' }); try { localStorage.removeItem('iostart.look'); } catch { /* private mode */ } if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}

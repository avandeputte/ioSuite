/* The badges: small chips under the greeting, one fact each (iostart/layout.py badges). */
import { dialog, icon, popMenu } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, newId, quiet, S } from './core.js';
import { haAct, HA_POPUPS, haIcon, haLink, haPopup, haSubscribe } from './homeassistant.js';
import { LINES, widget } from './tiles.js';
import { whenDialog, whenOk, whenText } from './when.js';

// ------------------------------------------------------------------ the badges
/* A badge is an app's one line ("3 today · next 2:30 PM", "2 due today", "4 to renew": what its low tile says, LINES) and
   opens the app; or one Home Assistant entity of those an admin picked, with its state, which a tap switches when the
   page may control it (else it opens in Home Assistant). Each can have a rule for when it shows. */
const BADGES_MOST = 12;
/** The apps that have a line to say here. */
export const badgeApps = () => (S.apps || []).filter((a) => LINES[a.key]);

/** The row of badges of the page (L: its setup). A: the page is being arranged (every badge shows, each with a menu;
    a last chip adds one); `redraw()` draws the page again after a change. Nothing at all without badges. */
export function badgeRow(L, { A, redraw } = {}) {
  const list = L.badges || [];
  if (!list.length && !A) return null;
  const row = h('div', { class: `badges${A ? ' arrok' : ''}`, role: 'list' });
  const chips = list.map((b) => {
    const el = b.app ? appBadge(b) : haBadge(b);
    if (!el) return null;
    el.setAttribute('role', 'listitem');
    if (!A) {
      if (!whenOk(b.when)) return null;
      if (b.when && b.when.content) { el.hidden = true; el.onquiet = (q) => { el.hidden = q; }; }
      return el;
    }
    // while the page is arranged: a tap opens the badge's menu instead of the app
    el.classList.add('arr');
    if (b.when) el.append(h('span', { class: 'badgewhen', title: `Shows: ${whenText(b.when)}` }, icon('schedule', 's')));
    el.addEventListener('click', (e) => {
      e.preventDefault(); e.stopPropagation();
      const i = list.indexOf(b), move = (by) => { list.splice(i, 1); list.splice(i + by, 0, b); redraw(); };
      popMenu(el, [
        i > 0 ? ['left', 'Move left', () => move(-1)] : null,
        i < list.length - 1 ? ['right', 'Move right', () => move(1)] : null,
        ['schedule', b.when ? `Shows: ${whenText(b.when)}` : 'Show only when…', async () => { const r = await whenDialog('this badge', b.when); if (r) { if (r.when) b.when = r.when; else delete b.when; redraw(); } }],
        ['delete', 'Remove', () => { L.badges = list.filter((x) => x !== b); redraw(); }],
      ]);
    }, true);
    return el;
  }).filter(Boolean);
  row.append(...chips);
  if (A && list.length < BADGES_MOST) row.append(h('button', { class: 'badge badgeadd', title: 'A badge: one fact of an app, or a thing in Home Assistant', onclick: async (e) => {
    e.stopPropagation();
    const b = await pickBadge(list);
    if (b) { L.badges = [...list, b]; redraw(); }
  } }, icon('add', 's'), 'Badge'));
  return row.childElementCount ? row : null;
}

function appBadge(b) {
  const app = (S.apps || []).find((a) => a.key === b.app), line = LINES[b.app];
  if (!app || !line) return null;  // the app is not on the page (or was taken out of the suite)
  const text = h('span', { class: 'badgetext' }, '…');
  const el = h('a', { class: 'badge', href: app.url, title: app.name, 'data-badge': b.id }, h('img', { src: app.icon, alt: '' }), text);
  el.redraw = async () => {
    const d = await widget(b.app);
    if (!el.isConnected) return;
    if (!d) { if (text.textContent === '…') { text.textContent = app.name; quiet(el, true); } return; }  // down, or closed to this account: its name alone
    const [say, warn, tip, idle] = line(d);
    text.textContent = say; el.classList.toggle('warn', !!warn); el.title = [app.name, tip].filter(Boolean).join('\n');
    quiet(el, !!idle);
  };
  setTimeout(el.redraw, 0);  // once it is on the page
  return el;
}

function haBadge(b) {
  const text = h('span', { class: 'badgetext' }, '…'), pic = h('span', { class: 'badgeic' });
  const el = h('a', { class: 'badge', 'data-badge': b.id, title: b.entity }, pic, text);
  let cur = null;
  const show = (d) => {
    if (!el.isConnected) return;
    const t = d && d.enabled ? (d.items || []).find((x) => x.id === b.entity) : null;
    if (!t) { text.textContent = b.entity.split('.')[1].replace(/_/g, ' '); el.classList.add('off'); quiet(el, true); return; }
    cur = t;
    pic.replaceChildren(icon(haIcon(t), 's'));
    text.replaceChildren(h('span', { class: 'badgename' }, t.name), ' ', t.text || t.state);
    el.classList.toggle('on', !!t.on); el.classList.toggle('off', t.state === 'unavailable' || t.state === 'missing');
    el.title = `${t.name}: ${t.text || t.state}${t.control ? ' · tap to switch' : ''}`;
    if (!t.control) { el.href = haLink(t); el.target = '_blank'; el.rel = 'noreferrer'; } else el.removeAttribute('href');
    el.setAttribute('role', t.control ? 'button' : 'listitem'); el.tabIndex = 0;
    quiet(el, t.on === false);
  };
  el.addEventListener('click', async (e) => {
    if (S.arrange || !cur || !cur.control) return;
    e.preventDefault();
    if (HA_POPUPS[cur.domain]) { haPopup(cur, (r) => show({ enabled: true, items: [{ ...cur, ...r }] })); return; }
    el.classList.add('busy');
    const r = await haAct(cur.id, 'toggle');
    el.classList.remove('busy');
    if (r) show({ enabled: true, items: [{ ...cur, ...r, control: cur.control }] });
  });
  el.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && cur && cur.control) { e.preventDefault(); el.click(); } });
  el.redraw = async () => { let d; try { d = await api('api/ha'); } catch { d = null; } if (d) S.ha = d.enabled ? d : false; show(d); };
  setTimeout(() => { if (!el.isConnected) return; const off = haSubscribe((d) => { if (!el.isConnected) { off(); return; } show(d); }); el.redraw(); }, 0);
  return el;
}

/** The dialog that adds a badge: the apps that have something to say, then Home Assistant's things. */
async function pickBadge(have) {
  let ha = null;
  try { const d = await api('api/ha'); ha = d.enabled ? d : null; } catch { /* no Home Assistant */ }
  const body = h('div', { class: 'pickbadge' });
  const done = (b) => body.closest('.dialog-back').close({ id: newId(6), ...b });
  const apps = badgeApps().filter((a) => !have.some((b) => b.app === a.key));
  const things = ((ha && ha.items) || []).filter((t) => !have.some((b) => b.entity === t.id));
  body.append(
    apps.length ? h('h3', null, 'From an app') : '',
    h('div', { class: 'pickrows' }, apps.map((a) => h('button', { class: 'pickrow', onclick: () => done({ app: a.key }) }, h('img', { src: a.icon, alt: '' }), h('span', null, a.name), h('span', { class: 'muted small' }, BADGE_ABOUT[a.key] || '')))),
    things.length ? h('h3', null, ha.name || 'Home Assistant') : '',
    h('div', { class: 'pickrows' }, things.map((t) => h('button', { class: 'pickrow', onclick: () => done({ entity: t.id }) }, icon(haIcon(t), 's'), h('span', null, t.name), h('span', { class: 'muted small' }, t.text || t.state)))),
    !apps.length && !things.length ? h('p', { class: 'muted' }, 'Everything that can be a badge is one already.') : '',
    ha ? '' : h('p', { class: 'muted small' }, 'With Home Assistant set up (Settings), its lights, doors and sensors can be badges too.'));
  return (await dialog('Add a badge', body, [{ label: 'Cancel', value: null }])) || null;
}
const BADGE_ABOUT = { iocalendar: 'How many events today, and the next', iotask: 'How many tasks are due', iomoney: 'Bills this week, a low balance', iohealth: 'Steps and sleep',
  iodocs: 'Papers to renew', iopix: 'Photos from this day', iocontact: 'The next birthday' };

/** Asks every badge on the page anew (the page's live refresh). */
export function refreshBadges(page) {
  for (const el of page.querySelectorAll('.badge[data-badge]')) if (el.redraw) el.redraw();
}

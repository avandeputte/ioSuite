/* The overview (the net worth, its history, the accounts by kind) and the Monarch sync as it runs. */
import { dialog, fail, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { ago, amt, api, behind, behindText, byGroup, canAdd, CUR, fld, followsTx, GROUP_LOOK, kindLabel, money, pct, S, store, THINGS, tone } from './core.js';
import { accountDialog, lowNote } from './account.js';
import { bar, lineChart } from './charts.js';
import { onRoute } from './main.js';
import { refreshSummary } from './shell.js';

// ------------------------------------------------------------------ overview: the net worth, its history, the accounts
const RANGES = [['30', '1M'], ['91', '3M'], ['365', '1Y'], ['1825', '5Y']];
export async function showOverview(page) {
  const days = store.get('range') || '365';
  const nw = await api(`api/networth?days=${days}`);
  const hist = nw.history || [];
  const first = hist.length ? hist[0].value : null;
  const change = first != null ? nw.netWorth - first : null;
  const segs = h('div', { class: 'segs' }, RANGES.map(([d, l]) => h('button', { class: d === days ? 'on' : null, onclick: () => { store.set('range', d); onRoute(); } }, l)));
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Overview'), h('span', { class: 'grow' }), segs,
    canAdd() ? h('button', { class: 'pillbtn addacct', onclick: () => accountDialog() }, icon('add'), h('span', null, 'Account')) : null));
  put(page, flagNote());
  put(page, await lowNote());
  put(page, syncNote());
  put(page, h('div', { class: 'hero' },
    h('div', null, h('div', { class: 'lbl' }, 'Net worth'), h('div', { class: 'big num' }, money(nw.netWorth, nw.currency))),
    change != null ? h('div', { class: `chg num ${tone(change)}` }, `${money(change, nw.currency, { sign: true })} ${first ? `(${pct(change / Math.abs(first) * 100)})` : ''}`, h('small', { class: 'muted' }, ` over ${RANGES.find(([d]) => d === days)[1]}`)) : null));
  put(page, lineChart(hist));
  put(page, h('div', { class: 'cards' },
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Assets'), h('div', { class: 'val num' }, money(nw.assets, nw.currency))),
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Owed'), h('div', { class: 'val num neg' }, money(nw.liabilities, nw.currency)))));
  const max = Math.max(1, ...nw.byGroup.map((g) => Math.abs(g.value)));
  if (nw.byGroup.length) put(page, h('div', { class: 'box' }, h('h2', null, icon('pie'), 'By group'), h('div', { class: 'bars' }, nw.byGroup.map((g) => bar(g.label, g.value, max, { hueVar: GROUP_LOOK[g.group][1], cur: nw.currency })))));
  const accts = S.accounts.filter((a) => !a.hidden);
  if (!accts.length) {
    put(page, h('div', { class: 'empty' }, icon('bank'), h('p', null, 'No accounts yet.'),
      h('p', { class: 'muted' }, S.user.role === 'admin' ? 'Connect Monarch Money in Settings › Money, or add an account by hand.' : 'They come from Monarch Money, or are added by hand.')));
    return;
  }
  put(page, h('div', { class: 'groups' }, byGroup(accts).map((g) => {
    const total = g.list.filter((a) => a.inNetWorth && !a.closed).reduce((s, a) => s + (a.estimate != null ? (a.isAsset ? a.estimate : -a.estimate) : a.value), 0);
    return h('section', { class: 'group', style: { '--hue': `var(${GROUP_LOOK[g.group][1]})` } },
      h('header', null, icon(GROUP_LOOK[g.group][0]), h('span', { class: 'grow' }, g.label), amt(total, CUR(), { plain: true })),
      h('ul', { class: 'rows' }, g.list.map(acctRow)));
  })));
}
/** Who sees a private account, in a few words ("you alone", "you and Sam", "Alex and you"). */
export function seenBy(a) {
  const me = S.user ? S.user.id : null;
  const names = (a.people || []).map((p) => (p.id === me ? 'you' : p.name));
  if (names.length <= 1) return names[0] === 'you' ? 'you alone' : `${names[0] || 'its owner'} alone`;
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}
export const privTag = (a) => (a.household ? null : h('span', { class: 'tag priv', title: `Private: seen by ${seenBy(a)}, nobody else` },
  (a.people || []).length > 1 ? 'Shared' : 'Private'));
function acctRow(a) {
  const shown = a.estimate != null ? a.estimate : a.balance;
  return h('li', { class: a.closed || !a.inNetWorth ? 'off' : null }, h('a', { href: `#/account/${a.id}` },
    h('span', { class: 'main' }, h('b', null, a.name), h('small', null, [a.institution, a.subtype, a.mask ? `…${a.mask}` : null].filter(Boolean).join(' · ') || kindLabel(a.kind))),
    privTag(a),
    behind(a) ? h('span', { class: 'tag warn', title: behindText(a.bank) }, icon('warning', 'xs'), a.bank.stale === 'old' ? 'Behind' : 'Link broken') : null,
    a.estimate != null ? h('span', { class: 'tag est', title: 'Estimated from the last value and its yearly change' }, 'Est.') : null,
    !followsTx(a) && !THINGS.includes(a.kind) && a.kind !== 'investment' ? h('span', { class: 'tag', title: 'Its value alone is followed, not its transactions' }, 'Value') : null,
    h('span', { class: 'end' }, h('span', { class: `num ${a.isAsset ? '' : 'neg'}` }, money(a.isAsset ? shown : -Math.abs(shown), a.currency)),
      a.currency !== CUR() ? h('small', { class: 'muted num' }, money(a.value, CUR())) : a.equity != null ? h('small', { class: 'muted num' }, `Equity ${money(a.equity)}`) : null)));
}
function flagNote() {
  const n = S.sum && S.sum.recurringFlags;
  if (!n) return null;
  return h('div', { class: 'note warnnote' }, icon('warning', 's'),
    h('span', { class: 'grow' }, n === 1 ? 'A recurring transaction needs a look: a payment that did not come, or an amount that changed.'
      : `${n} recurring transactions need a look: payments that did not come, or amounts that changed.`),
    h('a', { class: 'pillbtn primary', href: '#/recurring' }, 'Review'));
}
function syncNote() {
  const m = S.sum && S.sum.monarch;
  if (!m || !m.configured) return null;
  const admin = S.user.role === 'admin';
  const out = [];
  if (m.newAccounts && admin) {
    out.push(h('div', { class: 'note warnnote' }, icon('warning', 's'),
      h('span', { class: 'grow' }, m.newAccounts === 1 ? 'Monarch Money reports an account ioMoney does not know. Is it new, or one you have that was made again in Monarch?'
        : `Monarch Money reports ${m.newAccounts} accounts ioMoney does not know. Are they new, or ones you have that were made again in Monarch?`),
      h('button', { class: 'pillbtn primary', onclick: () => newAccountsDialog() }, 'Review')));
  }
  if (m.stale && m.stale.length) {
    const one = m.stale.length === 1;
    out.push(h('div', { class: 'note warnnote behindnote' }, icon('warning', 's'),
      h('div', { class: 'grow' },
        h('div', null, one ? 'Monarch Money may have lost its link to the bank for this account:' : `Monarch Money may have lost its link to the bank for ${m.stale.length} accounts:`),
        h('ul', null, m.stale.map((x) => h('li', null, h('a', { class: 'lnk', href: `#/account/${x.id}` }, x.name), x.institution ? ` (${x.institution})` : '', `: ${behindText(x)}`))),
        h('small', { class: 'muted' }, `Check ${one ? 'its' : 'their'} connection in Monarch Money (Settings › Institutions); the next sync here picks up the change.`))));
  }
  if (m.running) {
    if (admin) watchSync();
    out.push(h('p', { class: 'muted small syncing', style: { margin: '-8px 0 12px' } }, h('span', { class: 'spin' }), ' Syncing with Monarch Money: ', h('span', { 'data-syncstage': '' }, 'under way')));
  } else {
    const stale = m.lastGood && (Date.now() - new Date(m.lastGood).getTime()) > 2 * 86400e3;
    out.push(h('p', { class: `muted small ${stale ? 'warn' : ''}`, style: { margin: '-8px 0 12px' } }, icon('sync', 'xs'), ` Monarch Money synced ${ago(m.lastGood)}`,
      admin ? [' · ', h('a', { class: 'lnk', href: '#/settings/money' }, 'Settings')] : null));
  }
  return out;
}

// ------------------------------------------------------------------ the Monarch sync: in the background, followed here
let syncPoll = null;
export const syncLabel = (p) => (p && p.stage ? `${p.stage}${p.count ? ` (${p.count.toLocaleString()})` : ''}` : 'under way');
/** Follow a running sync (admins): its stage on the page every two seconds, and how it went at the end. A first sync
    of two years takes minutes, longer than a request waits, so it runs on in the server and is followed from here. */
export function watchSync() {
  if (syncPoll) return;
  const tick = async () => {
    let st;
    try { st = await api('api/monarch'); } catch { syncPoll = setTimeout(tick, 5000); return; }
    document.querySelectorAll('[data-syncstage]').forEach((el) => { el.textContent = syncLabel(st.progress); });
    if (st.running) { syncPoll = setTimeout(tick, 2000); return; }
    syncPoll = null;
    if (st.last) toast(st.last.ok ? `Synced: ${st.last.message}` : `The sync did not work: ${st.last.message}`);
    await refreshSummary();
    if (!document.querySelector('.dialog-back')) onRoute();
  };
  syncPoll = setTimeout(tick, 1500);
}
export async function startSync(full, btn) {
  if (btn) { btn.disabled = true; btn.lastChild.textContent = 'Starting…'; }
  try {
    const r = await api('api/monarch/sync', { method: 'POST', json: { full, wait: 5 } });
    if (r.running) toast('Syncing in the background: this page shows how it goes');
    else toast(r.ok ? `Synced: ${r.message}` : r.message);
  } catch (e) { fail(e); }
  await refreshSummary(); onRoute();
}

/** One Monarch account's two years of transactions (and its history, its holdings) fetched again; what was changed
    here stays, what Monarch no longer has (or hides) goes. */
export async function resyncAccount(a) {
  const back = h('select', { class: 't' }, h('option', { value: '2' }, 'The past 2 years'), h('option', { value: '5' }, 'The past 5 years'), h('option', { value: '0' }, 'Everything Monarch has'));
  const body = h('div', null, h('p', null, `Fetch ${a.name}’s transactions from Monarch Money again. Your changes here (categories, notes, payees) stay; what Monarch no longer has, or hides, is removed here.`),
    fld('How far back', back));
  if (!await dialog('Sync this account again', body, [{ label: 'Cancel', value: false }, { label: 'Sync it', value: true, primary: true }])) return;
  try {
    const r = await api('api/monarch/sync', { method: 'POST', json: { accountId: a.id, years: +back.value, wait: 20 } });
    if (r.running) toast('Syncing in the background: Settings › Money shows how it goes');
    else toast(r.message);
  } catch (e) { fail(e); }
  await refreshSummary(); onRoute();
}
/** The accounts Monarch reported that ioMoney did not know: one at a time, new or an account here (the likeliest
    chosen); "Later" leaves the rest waiting. */
export async function newAccountsDialog() {
  let items;
  try { items = (await api('api/monarch/new')).items || []; } catch (e) { fail(e); return; }
  for (const [i, x] of items.entries()) {
    const name = `pick-${x.externalId}`;
    const radio = (value, checked, ...label) => h('label', { class: 'pick' }, h('input', { type: 'radio', name, value, checked: checked ? true : null }), h('span', null, ...label));
    const desc = (a) => [a.institution, a.kind ? kindLabel(a.kind) : null, a.mask ? `…${a.mask}` : null].filter(Boolean).join(' · ');
    const body = h('div', { class: 'newacct' },
      h('div', { class: 'box', style: { margin: '0 0 14px' } }, h('b', null, x.name), h('div', { class: 'muted small' }, desc(x), x.closed ? ' · closed in Monarch' : ''),
        h('div', { class: 'num' }, money(x.balance))),
      h('p', { class: 'muted small' }, 'When a bank’s link breaks, an account is often deleted and made again in Monarch Money, with a new id. Say which it is, so its account and transactions are not here twice. Its transactions wait until then.'),
      h('div', { class: 'picks' }, radio('new', !x.likely, h('b', null, 'A new account'), h('small', null, 'Added here with its history and transactions, as the household’s')),
        radio('mine', false, h('b', null, 'A new account of mine alone'), h('small', null, 'Added as your private account: nobody else sees it until you say who may')),
        x.candidates.map((c) => radio(String(c.id), c.id === x.likely, h('b', null, c.name), h('small', null, [desc(c), money(c.balance), c.gone ? 'no longer in Monarch' : c.source === 'manual' ? 'added by hand' : null].filter(Boolean).join(' · '))))));
    const ok = await dialog(items.length > 1 ? `New in Monarch Money (${i + 1} of ${items.length})` : 'New in Monarch Money', body,
      [{ label: 'Later', value: false }, { label: 'Save', value: true, primary: true }], 'wide');
    if (!ok) break;
    const v = body.querySelector(`input[name="${name}"]:checked`).value;
    try {
      await api(`api/monarch/new/${encodeURIComponent(x.externalId)}`, { method: 'POST', json: v === 'new' || v === 'mine' ? { as: 'new', private: v === 'mine' } : { as: 'existing', accountId: +v } });
      toast(v === 'new' || v === 'mine' ? `${x.name} comes in with this sync` : 'Its transactions are matched with this sync, none twice');
    } catch (e) { fail(e); break; }
  }
  await refreshSummary(); onRoute();
}

/* One account: its history, transactions, holdings or values; the forecast and the payoff; what is known of it; who
   sees it. */
import { confirmDialog, dialog, fail, icon, popMenu, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { ago, amt, api, behind, behindText, copyText, CUR, fld, fmtDay, followsTx, groups, inp, KIND_LOOK, kindLabel, linkUi, may, money, S, store, THINGS, today } from './core.js';
import { lineChart } from './charts.js';
import { onRoute } from './main.js';
import { privTag, resyncAccount, seenBy } from './overview.js';
import { drawHoldings, holdingDialog } from './portfolio.js';
import { importDialog, showReconcile } from './reconcile.js';
import { refreshSummary } from './shell.js';
import { txDialog, txList } from './transactions.js';

// ------------------------------------------------------------------ one account
export async function showAccount(page, r) {
  const a = await api(`api/accounts/${r.id}`);
  document.title = `${a.name} · ioMoney`;
  if (r.tab === 'reconcile') { await showReconcile(page, a); return; }
  const thing = THINGS.includes(a.kind);
  const tx = followsTx(a);
  const valued = thing || (!tx && a.kind !== 'investment');  // a value now and then, not transactions
  const shown = a.estimate != null ? a.estimate : a.balance;
  const menu = h('button', { class: 'iconbtn', title: 'More', 'aria-label': 'More', onclick: (e) => popMenu(e.currentTarget, [
    a.writable ? ['edit', 'Rename', () => renameAccount(a)] : null,
    a.writable ? ['tune', 'Edit', () => accountDialog(a)] : null,
    a.writable && !thing ? ['bank', 'Bank details', () => infoDialog(a)] : null,
    a.writable && a.source === 'manual' && valued ? ['add', 'Add a value', () => valueDialog(a)] : null,
    a.writable && a.source === 'manual' && a.kind === 'investment' ? ['add', 'Add a holding', () => holdingDialog(null, a.id)] : null,
    a.writable && tx ? ['add', 'Add a transaction', () => txDialog(null, a)] : null,
    tx ? ['receipt', 'Its transactions', `#/transactions?account=${a.id}`] : null,
    tx && a.writable ? ['check', 'Reconcile with a statement', `#/account/${a.id}/reconcile`] : null,
    tx && a.writable && a.source === 'manual' ? ['upload', 'Import a bank file', () => importDialog(a)] : null,
    a.source === 'monarch' && may('admin') ? ['sync', 'Sync this account again', () => resyncAccount(a)] : null,
    a.writable && a.bank && a.bank.linked && !a.closed ? (a.bank.quiet ? ['warning', 'Flag it when the bank link is behind', () => quietBank(a, false)]
      : ['warning', 'Don’t flag its bank link', () => quietBank(a, true)]) : null,
    a.writable && a.source === 'manual' ? ['delete', 'Delete', () => removeAccount(a)] : null,
  ]) }, icon('more'));
  put(page, h('div', { class: 'pagehead' }, h('span', { class: 'sic', style: { '--hue': `var(${KIND_LOOK[a.kind][1]})`, color: 'var(--hue)' } }, icon(KIND_LOOK[a.kind][0])),
    h('h1', null, a.name), a.writable ? h('button', { class: 'iconbtn rename', title: 'Rename', 'aria-label': 'Rename', onclick: () => renameAccount(a) }, icon('edit', 's')) : null, privTag(a), a.hidden ? h('span', { class: 'tag' }, 'Hidden') : null,
    a.closed ? h('span', { class: 'tag' }, 'Closed') : null,
    !tx && !thing ? h('span', { class: 'tag', title: 'Its value alone is followed, not its transactions (Edit to change)' }, 'Value only') : null,
    h('span', { class: 'grow' }), menu));
  put(page, h('div', { class: 'hero' },
    h('div', null, h('div', { class: 'lbl' }, [kindLabel(a.kind), a.institution, a.subtype].filter(Boolean).join(' · ')),
      h('div', { class: `big num ${a.isAsset ? '' : 'neg'}` }, money(a.isAsset ? shown : -Math.abs(shown), a.currency))),
    a.estimate != null ? h('div', { class: 'chg muted' }, h('span', { class: 'tag est' }, 'Estimated'), ` from ${money(a.balance, a.currency)} and ${a.details.yearlyRate}% a year`) : null,
    a.equity != null ? h('div', { class: 'chg' }, 'Equity ', amt(a.equity), h('small', { class: 'muted' }, ` after ${a.loan.name} (${money(a.loan.balance, a.loan.currency)})`)) : null,
    a.currency !== CUR() ? h('div', { class: 'chg muted num' }, money(a.value, CUR())) : null));
  if (a.source === 'monarch') {
    const b = a.bank;
    if (behind(a)) put(page, h('div', { class: 'note warnnote' }, icon('warning', 's'), h('span', { class: 'grow' }, `${behindText(b)}. Its balance and transactions may be out of date: check its connection in Monarch Money (Settings › Institutions).`)));
    put(page, h('p', { class: 'muted small', style: { margin: '-6px 0 12px' } }, icon('sync', 'xs'), ` From Monarch Money, updated ${ago(a.balanceAt)}`,
      b && b.linked && b.refreshedAt && !behind(a) ? ` · Monarch last heard from the bank ${ago(b.refreshedAt)}` : null,
      b && b.quiet ? ' · not flagged when behind' : null));
  }
  const days = store.get('range') || '365';
  const hist = await api(`api/accounts/${a.id}/history?days=${days}`);
  put(page, lineChart((hist.items || []).map((p) => ({ ...p, value: a.isAsset ? p.value : -p.value }))));
  if (thing) {
    const d = a.details || {};
    const facts = [['Address', d.address], ['Year', d.year], ['Make', d.make], ['Model', d.model], ['VIN', d.vin], ['Mileage', d.mileage],
      ['Bought on', d.boughtOn ? fmtDay(d.boughtOn, true) : null], ['Bought for', d.boughtFor != null ? money(d.boughtFor, a.currency) : null],
      ['Yearly change', d.yearlyRate != null ? `${d.yearlyRate}%` : null], ['Loan', a.loan ? h('a', { class: 'lnk', href: `#/account/${a.loan.id}` }, a.loan.name) : null]].filter(([, v]) => v != null && v !== '');
    if (facts.length || d.notes) put(page, h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Details'), h('div', { class: 'kvs' }, facts.flatMap(([k, v]) => [h('span', null, k), h('span', null, v)])), d.notes ? h('p', { class: 'notes' }, d.notes) : null));
  }
  if (a.kind === 'cash' && tx && !a.closed) put(page, await forecastBox(a));
  if (a.kind === 'loan' && !a.closed) put(page, await payoffBox(a));
  if (!thing) put(page, await infoBox(a));
  if (a.kind === 'investment') await drawHoldings(page, a.id, a);
  if (valued) {
    const vals = (await api(`api/accounts/${a.id}/values`)).items || [];
    put(page, h('div', { class: 'box' }, h('h2', null, icon('trend'), 'Values', h('span', { class: 'grow' }),
      a.writable && a.source === 'manual' ? h('button', { class: 'pillbtn tiny', onclick: () => valueDialog(a) }, icon('add', 'xs'), 'Add') : null),
      vals.length ? h('ul', { class: 'rows' }, vals.filter((v) => v.source !== 'estimate' || v === vals[0]).slice(0, 40).map((v) => h('li', null, h('div', { class: 'r' },
        h('span', { class: 'day' }, fmtDay(v.day)), h('span', { class: 'main' }, h('b', null, v.note || { manual: 'Typed in', sync: a.source === 'monarch' ? 'From Monarch Money' : 'Its holdings', estimate: 'Estimate' }[v.source] || v.source), h('small', null, new Date(`${v.day}T12:00:00`).getFullYear())),
        h('span', { class: 'num' }, money(v.value, a.currency)),
        a.writable && a.source === 'manual' && v.source !== 'sync' ? h('button', { class: 'iconbtn', title: 'Remove this value', onclick: async () => { if (await confirmDialog('Remove the value', `Remove the value of ${fmtDay(v.day, true)}?`, 'Remove', true)) { await api(`api/accounts/${a.id}/values/${v.day}`, { method: 'DELETE' }); onRoute(); } } }, icon('delete', 's')) : null)))) : h('p', { class: 'muted' }, 'No values kept yet.')));
  }
  if (thing) put(page, linkedBox(a.id));
  if (tx) {
    const t = await api(`api/transactions?account=${a.id}&limit=50`);
    put(page, h('h2', null, 'Recent transactions'), txList(t.items, false),
      t.total > t.items.length ? h('div', { class: 'more' }, h('a', { class: 'pillbtn', href: `#/transactions?account=${a.id}` }, `All ${t.total}`)) : null);
  }
}
/** "Forecast" on a cash account's page: where its balance goes over the coming weeks from its recurring transactions
    and steady transfers, the lowest point against the balance it should not go under, and what is to come. */
async function forecastBox(a) {
  const days = store.get('fcdays') || '60';
  let f;
  try { f = await api(`api/accounts/${a.id}/forecast?days=${days}`); } catch { return null; }
  const segs = h('div', { class: 'segs' }, [['30', '30 days'], ['60', '60 days'], ['90', '90 days']].map(([d, l]) => h('button', { class: d === days ? 'on' : null, onclick: () => { store.set('fcdays', d); onRoute(); } }, l)));
  const floorBtn = a.writable ? h('button', { class: 'pillbtn tiny', onclick: () => floorDialog(a) }, icon('edit', 'xs'), f.floor != null ? `Keep above ${money(f.floor, f.currency)}` : 'Set a lowest balance') : (f.floor != null ? h('span', { class: 'muted small' }, `Keep above ${money(f.floor, f.currency)}`) : null);
  const head = h('h2', null, icon('trend'), 'Forecast', h('span', { class: 'grow' }), floorBtn, segs);
  if (!f.events.length) {
    return h('div', { class: 'box forecast' }, head, h('p', { class: 'muted' }, 'Nothing known to come: the forecast uses the recurring transactions kept for this account (Recurring page) and the transfers it makes at a steady pace.',
      f.leftOut.length ? ` Left out, as ${f.leftOut.length === 1 ? 'its' : 'their'} last payment did not come: ${f.leftOut.join(', ')}.` : '',
      f.unassigned ? ` ${f.unassigned} recurring transaction${f.unassigned === 1 ? ' is' : 's are'} kept for any account: give ${f.unassigned === 1 ? 'it' : 'them'} this account to count ${f.unassigned === 1 ? 'it' : 'them'}.` : ''));
  }
  const under = f.floor != null ? `under ${money(f.floor, f.currency)}` : 'under zero';
  const lowLine = f.below
    ? h('div', { class: 'note warnnote' }, icon('warning', 's'), h('span', { class: 'grow' }, `${f.belowOn === today() ? `It is ${under} now` : `It would go ${under} on ${fmtDay(f.belowOn, true)}`}; the lowest point is ${money(f.low.value, f.currency)} on ${fmtDay(f.low.day, true)}.`))
    : h('p', { class: 'muted small' }, `Lowest point: ${money(f.low.value, f.currency)} on ${fmtDay(f.low.day, true)} · ${money(f.end, f.currency)} after ${f.days} days`);
  const row = (e) => h('li', null, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(e.day)),
    h('span', { class: 'main' }, h('b', null, e.name, e.late ? h('span', { class: 'tag warn', title: 'It was due a few days ago and has not been seen yet: expected now' }, 'Late') : null),
      h('small', null, { recurring: 'Recurring', subscription: 'Subscription', transfer: 'Transfer at a steady pace' }[e.kind])),
    h('span', { class: `num ${e.amount < 0 ? '' : 'pos'}` }, `${e.approximate ? '≈ ' : ''}${money(e.amount, f.currency)}`),
    h('span', { class: `num bal ${e.balance < (f.floor != null ? f.floor : 0) ? 'neg' : 'muted'}` }, money(e.balance, f.currency))));
  return h('div', { class: 'box forecast' }, head, lowLine, lineChart(f.points, { height: 160, cur: f.currency }),
    h('ul', { class: 'rows fc' }, h('li', { class: 'fchead' }, h('div', { class: 'r' }, h('span', { class: 'day' }, 'Day'), h('span', { class: 'main' }, 'To come'), h('span', { class: 'num' }, 'Amount'), h('span', { class: 'num bal' }, 'Balance'))), f.events.map(row)),
    h('p', { class: 'muted small' }, 'Everyday spending is not counted: this is the most the account will hold.',
      f.leftOut.length ? ` Left out, as ${f.leftOut.length === 1 ? 'its' : 'their'} last payment did not come: ${f.leftOut.join(', ')}.` : '',
      f.unassigned ? ` ${f.unassigned} recurring transaction${f.unassigned === 1 ? '' : 's'} kept for any account ${f.unassigned === 1 ? 'is' : 'are'} left out.` : ''));
}
/** "Payoff" on a loan's page: from its interest rate and monthly payment, when it is paid off and the interest
    still to pay; with more paid a month, what that saves. */
async function payoffBox(a) {
  let p;
  try { p = await api(`api/accounts/${a.id}/payoff`); } catch { return null; }
  const edit = a.writable ? h('button', { class: 'pillbtn tiny', onclick: () => loanDialog(a, p) }, icon('edit', 'xs'), 'Rate and payment') : null;
  const head = h('h2', null, icon('loan'), 'Payoff', h('span', { class: 'grow' }), edit);
  if (p.needs.length) {
    return h('div', { class: 'box payoff' }, head, h('p', { class: 'muted' }, p.needs[0] === 'rate' ? 'Give the loan’s interest rate to see when it is paid off and the interest still to pay.'
      : 'Give what is paid a month: its balance has no history yet to work it out from.'));
  }
  const span = (m) => (m >= 12 ? `${Math.floor(m / 12)} year${m >= 24 ? 's' : ''}${m % 12 ? ` ${m % 12} month${m % 12 === 1 ? '' : 's'}` : ''}` : `${m} month${m === 1 ? '' : 's'}`);
  const monthOf = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const stat = (l, v, sub) => h('div', { class: 'stat' }, h('div', { class: 'lbl' }, l), h('div', { class: 'val num' }, v), sub ? h('small', { class: 'muted' }, sub) : null);
  const cards = h('div', { class: 'cards' },
    stat('Rate', `${p.rate}%`, 'a year'),
    stat('Payment', `${p.paymentEstimated ? '≈ ' : ''}${money(p.payment, p.currency)}`, p.paymentEstimated ? 'a month, from how the balance went down' : 'a month'),
    p.never ? stat('Paid off', 'Never', 'the payment does not cover the interest') : stat('Paid off', monthOf(p.payoff), `in ${span(p.months)}`),
    p.never ? null : stat('Interest left', money(p.interest, p.currency), `${money(p.total, p.currency)} in all`));
  const extra = inp(store.get(`extra${a.id}`) || '', { inputmode: 'decimal', placeholder: '100', style: { maxWidth: '120px' } });
  const result = h('p', { class: 'extraout' });
  const run = async () => {
    const v = extra.value.trim();
    store.set(`extra${a.id}`, v);
    if (!v || !(parseFloat(v) > 0)) { result.replaceChildren(); return; }
    try {
      const x = (await api(`api/accounts/${a.id}/payoff?extra=${encodeURIComponent(v)}`)).extra;
      if (!x || x.never) { result.textContent = 'Even so, the payment does not cover the interest.'; return; }
      put(result, h('b', null, `Paid off ${monthOf(x.payoff)}`), p.never ? ` (in ${span(x.months)}), with ${money(x.interest, p.currency)} of interest.`
        : [` · ${span(x.savedMonths)} sooner · `, h('span', { class: 'num pos' }, money(x.savedInterest, p.currency)), ' less interest']);
    } catch (e) { result.textContent = e.message || String(e); }
  };
  let timer = null;
  extra.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { result.replaceChildren(); run(); }, 350); });
  if (extra.value) run();
  return h('div', { class: 'box payoff' }, head, cards,
    h('div', { class: 'extrarow' }, h('label', null, 'Paying', extra, 'more a month'), result));
}
async function loanDialog(a, p) {
  const d = a.details || {};
  const rate = inp(d.rate != null ? d.rate : '', { inputmode: 'decimal', placeholder: '6.25' });
  const pay = inp(d.payment != null ? d.payment : '', { inputmode: 'decimal', placeholder: p && p.paymentEstimated ? `about ${p.payment}` : '' });
  const body = h('div', null, h('div', { class: 'grid' }, fld('Interest rate (% a year)', rate), fld('Monthly payment', pay)),
    h('p', { class: 'muted small' }, 'The payment without what goes to escrow (taxes, insurance). Left empty, it is worked out from how the balance went down over the past three months.'));
  setTimeout(() => rate.focus(), 50);
  if (!await dialog(`${a.name}: rate and payment`, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try { await api(`api/accounts/${a.id}`, { method: 'PATCH', json: { details: { rate: rate.value.trim(), payment: pay.value.trim() } } }); await refreshSummary(); toast('Saved'); onRoute(); } catch (e) { fail(e); }
}
async function floorDialog(a) {
  const v = inp(a.details && a.details.floor != null ? a.details.floor : '', { inputmode: 'decimal', placeholder: '500' });
  const body = h('div', null, fld('Lowest balance', v, true), h('p', { class: 'muted small' }, 'The forecast warns, here and on the overview, when the balance would go under it. Left empty: under zero.'));
  setTimeout(() => v.focus(), 50);
  if (!await dialog(`${a.name}: keep above`, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try { await api(`api/accounts/${a.id}`, { method: 'PATCH', json: { details: { floor: v.value.trim() } } }); await refreshSummary(); toast('Saved'); onRoute(); } catch (e) { fail(e); }
}
/** The overview: the cash accounts that would go under their lowest balance in the next 30 days. */
export async function lowNote() {
  let w = [];
  try { w = (await api('api/forecast?days=30')).items || []; } catch { return null; }
  return w.map((x) => h('div', { class: 'note warnnote' }, icon('warning', 's'),
    h('span', { class: 'grow' }, h('a', { class: 'lnk', href: `#/account/${x.accountId}` }, x.name), `${x.belowOn === today() ? ' is under' : ' would go under'} ${x.floor != null ? money(x.floor, x.currency) : 'zero'}${x.belowOn === today() ? ' now' : ` on ${fmtDay(x.belowOn, true)}`} (lowest: ${money(x.low.value, x.currency)} on ${fmtDay(x.low.day, true)}), counting what is known to come.`)));
}
async function quietBank(a, quiet) {
  try { await api(`api/accounts/${a.id}`, { method: 'PATCH', json: { flagStale: !quiet } }); await refreshSummary(); toast(quiet ? 'It won’t be flagged' : 'It will be flagged when behind'); onRoute(); } catch (e) { fail(e); }
}
// what is kept to deal with the account's bank: [field, label, how it is typed in]; the numbers are shown hidden
const INFO = [['accountNumber', 'Account number', { autocomplete: 'off', spellcheck: 'false' }], ['routingNumber', 'Routing number', { inputmode: 'numeric', autocomplete: 'off' }],
  ['iban', 'IBAN', { autocomplete: 'off', spellcheck: 'false' }], ['swift', 'SWIFT / BIC', { maxlength: 11, autocomplete: 'off' }],
  ['phone', 'Customer service', { type: 'tel', placeholder: '1-800-…' }], ['phoneAbroad', 'From abroad', { type: 'tel' }],
  ['website', 'Website', { type: 'url', placeholder: 'https://…' }], ['email', 'Email', { type: 'email' }], ['username', 'Sign-in name', { autocomplete: 'off' }],
  ['openedOn', 'Opened on', { type: 'date' }], ['address', 'Mailing address', null], ['notes', 'Notes', null]];
const INFO_SECRET = ['accountNumber', 'routingNumber', 'iban'];
/** "Bank details" on an account's page: its numbers (hidden until shown), customer service and the rest. */
async function infoBox(a) {
  let info = {};
  try { info = await api(`api/accounts/${a.id}/info`); } catch { return null; }
  const have = INFO.filter(([k]) => info[k]);
  if (!have.length && !a.writable) return null;
  const val = (k, v) => {
    if (INFO_SECRET.includes(k)) {
      const tail = v.replace(/\s/g, '').slice(-4);
      const shown = h('span', { class: 'num' }, `•••• ${tail}`);
      let open = false;
      return h('span', { class: 'secret' }, shown,
        h('button', { class: 'iconbtn', title: 'Show', 'aria-label': 'Show', onclick: (e) => { open = !open; shown.textContent = open ? v : `•••• ${tail}`; e.currentTarget.title = open ? 'Hide' : 'Show'; } }, icon('eye', 's')),
        h('button', { class: 'iconbtn', title: 'Copy', 'aria-label': 'Copy', onclick: () => copyText(v.replace(/\s/g, '')) }, icon('copy', 's')));
    }
    if (k === 'phone' || k === 'phoneAbroad') return h('a', { class: 'lnk', href: `tel:${v.replace(/[^0-9+]/g, '')}` }, v);
    if (k === 'website') return h('a', { class: 'lnk', href: v, target: '_blank', rel: 'noopener noreferrer' }, v.replace(/^https?:\/\//i, '').replace(/\/$/, ''));
    if (k === 'email') return h('a', { class: 'lnk', href: `mailto:${v}` }, v);
    if (k === 'openedOn') return fmtDay(v, true);
    if (k === 'swift' || k === 'username') return h('span', { class: 'secret' }, v, h('button', { class: 'iconbtn', title: 'Copy', 'aria-label': 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));
    return v;
  };
  return h('div', { class: 'box' }, h('h2', null, icon('bank'), 'Bank details', h('span', { class: 'grow' }),
    a.writable ? h('button', { class: 'pillbtn tiny', onclick: () => infoDialog(a, info) }, icon(have.length ? 'edit' : 'add', 'xs'), have.length ? 'Edit' : 'Add') : null),
  have.length ? h('div', { class: 'kvs info' }, have.filter(([k]) => k !== 'notes' && k !== 'address').flatMap(([k, l]) => [h('span', null, l), h('span', null, val(k, info[k]))]),
    info.address ? [h('span', null, 'Mailing address'), h('span', { class: 'pre' }, info.address)] : null) : h('p', { class: 'muted small' }, 'Account and routing numbers, customer service and the like, to have at hand.'),
  info.notes ? h('p', { class: 'notes' }, info.notes) : null);
}
/** Change the bank details of an account (one from Monarch Money too: they are kept here alone). */
async function infoDialog(a, info) {
  if (!info) { try { info = await api(`api/accounts/${a.id}/info`); } catch (e) { fail(e); return; } }
  const f = Object.fromEntries(INFO.map(([k, , attrs]) => [k, k === 'address' || k === 'notes'
    ? h('textarea', { class: 't', rows: k === 'notes' ? 3 : 2 }, info[k] || '') : inp(info[k], attrs || {})]));
  const body = h('div', null, h('div', { class: 'grid' }, INFO.map(([k, l]) => fld(l, f[k], k === 'address' || k === 'notes' || k === 'website'))),
    h('p', { class: 'muted small' }, 'Seen by whoever sees this account; the numbers stay hidden until shown, and are never given to AI assistants (MCP). Keep passwords in a password manager, not here.'));
  if (!await dialog(`Bank details: ${a.name}`, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }], 'wide')) return;
  const b = Object.fromEntries(INFO.map(([k]) => [k, f[k].value.trim()]).filter(([k, v]) => v !== (info[k] || '')));
  if (!Object.keys(b).length) return;
  try { await api(`api/accounts/${a.id}/info`, { method: 'PUT', json: b }); toast('Saved'); onRoute(); } catch (e) { fail(e); }
}
/** "Linked" under a house or a car: the events, tasks, notes, contacts and photos of the other apps linked to it. */
/** A new name for an account (one from Monarch Money too: the name here stays through the syncs). */
async function renameAccount(a) {
  const name = inp(a.name, { maxlength: 255 });
  const body = h('div', null, fld('Name', name, true), a.source === 'monarch' ? h('p', { class: 'muted small' }, 'Monarch Money keeps its own name; this one stays here through the syncs.') : null);
  setTimeout(() => { name.focus(); name.select(); }, 50);
  name.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); name.closest('.dialog')?.querySelector('button.primary')?.click(); } });
  if (!await dialog('Rename the account', body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try { await api(`api/accounts/${a.id}`, { method: 'PATCH', json: { name: name.value } }); await refreshSummary(); toast('Renamed'); onRoute(); } catch (e) { fail(e); }
}
function linkedBox(id) {
  const el = h('div', { class: 'linked' });
  (async () => {
    let ui;
    try { ui = await linkUi(); } catch { return; }
    ui.mount(el, { kind: 'asset', id, toast });
  })();
  return el;
}
async function removeAccount(a) {
  if (!await confirmDialog('Delete the account', `Delete ${a.name} with its transactions, holdings and values? It cannot be brought back.`, 'Delete', true)) return;
  try { await api(`api/accounts/${a.id}`, { method: 'DELETE' }); toast('Deleted'); await refreshSummary(); location.hash = '#/'; } catch (e) { fail(e); }
}
/** Add an account, or change one: what an account from Monarch takes is its name, hidden, in the net worth, its
    details and its loan. */
export async function accountDialog(a) {
  const isNew = !a;
  a = a || { kind: 'cash', currency: CUR(), inNetWorth: true, household: may('household'), details: {}, source: 'manual' };
  const monarch = a.source === 'monarch';
  const f = {
    name: inp(a.name, { placeholder: 'Checking, Our house, Honda Civic' }),
    kind: h('select', { class: 't', disabled: monarch ? true : null }, groups().map((g) => h('optgroup', { label: g.label },
      (S.sum.kinds || []).filter((k) => g.kinds.includes(k.kind)).map((k) => h('option', { value: k.kind, selected: k.kind === a.kind ? true : null }, k.label))))),
    track: h('select', { class: 't' }, h('option', { value: 'transactions' }, 'Its transactions'), h('option', { value: 'value' }, 'Its value only')),
    balance: inp(a.balance, { inputmode: 'decimal', disabled: monarch ? true : null }),
    currency: inp(a.currency, { maxlength: 3, style: { textTransform: 'uppercase' }, disabled: monarch ? true : null }),
    institution: inp(a.institution, { disabled: monarch ? true : null }),
    inNetWorth: h('input', { type: 'checkbox', checked: a.inNetWorth ? true : null }),
    hidden: h('input', { type: 'checkbox', checked: a.hidden ? true : null }),
  };
  const who = await whoSees(a, isNew);
  const d = a.details || {};
  const det = { address: inp(d.address), year: inp(d.year, { inputmode: 'numeric', maxlength: 4 }), make: inp(d.make), model: inp(d.model), vin: inp(d.vin),
    mileage: inp(d.mileage, { inputmode: 'numeric' }), boughtOn: inp(d.boughtOn, { type: 'date' }), boughtFor: inp(d.boughtFor, { inputmode: 'decimal' }),
    yearlyRate: inp(d.yearlyRate, { inputmode: 'decimal', placeholder: '3 (a house), -15 (a car)' }), notes: h('textarea', { class: 't', rows: 2 }, d.notes || '') };
  const loans = S.accounts.filter((x) => ['loan', 'other_liability'].includes(x.kind));
  const loan = h('select', { class: 't' }, h('option', { value: '' }, 'None'), loans.map((l) => h('option', { value: l.id, selected: a.loan && a.loan.id === l.id ? true : null }, l.name)));
  const thingBox = h('div', { class: 'grid' });
  const drawThing = () => {
    const k = f.kind.value;
    thingBox.replaceChildren(...(THINGS.includes(k) ? [
      k === 'property' ? fld('Address', det.address, true) : null,
      k === 'vehicle' ? [fld('Year', det.year), fld('Make', det.make), fld('Model', det.model), fld('VIN', det.vin), fld('Mileage', det.mileage)] : null,
      fld('Bought on', det.boughtOn), fld('Bought for', det.boughtFor),
      !monarch ? fld('Yearly change (%)', det.yearlyRate) : null, fld('Loan against it', loan), fld('Notes', det.notes, true)] : []).flat().filter(Boolean));
  };
  const balLabel = fld('Balance', f.balance);
  // what is followed: the kind's usual (transactions for a bank account or a card, the value for the rest) until chosen
  const usualTrack = () => ((S.sum.kinds || []).find((k) => k.kind === f.kind.value) || {}).track || 'value';
  let trackChosen = !isNew;
  f.track.value = a.track || usualTrack();
  f.track.onchange = () => { trackChosen = true; };
  const trackNote = h('p', { class: 'muted small', style: { margin: '4px 0 0' } });
  const drawTrack = () => {
    if (!trackChosen) f.track.value = usualTrack();
    trackNote.textContent = f.track.value === 'value'
      ? 'Only its balance or value is kept, as you type it in now and then (or as Monarch Money has it); its transactions stay out of the lists and the spending.'
      : monarch ? 'Its transactions come from Monarch Money and count in the spending.' : 'You add its transactions, and each one moves its balance.';
  };
  f.track.addEventListener('change', drawTrack);
  const drawKind = () => { drawThing(); drawTrack(); balLabel.firstChild.textContent = THINGS.includes(f.kind.value) ? 'Value' : f.kind.value === 'investment' ? 'Balance (or what its holdings are worth)' : 'Balance'; };
  f.kind.onchange = drawKind; drawKind();
  const body = h('div', null, h('div', { class: 'grid' },
    fld('Name', f.name, true), fld('Kind', f.kind), balLabel, fld('Currency', f.currency), fld('Institution', f.institution),
    h('label', { class: 'field wide' }, h('span', null, 'Follow'), f.track, trackNote)),
  thingBox,
  h('div', { class: 'chiprow', style: { marginTop: '12px', gap: '16px' } },
    h('label', { class: 'check' }, f.inNetWorth, 'Counts in the net worth'), h('label', { class: 'check' }, f.hidden, 'Hidden')),
  who.el,
  monarch ? h('p', { class: 'muted small' }, 'This account comes from Monarch Money, which keeps its balance and transactions up to date.') : null);
  const ok = await dialog(isNew ? 'Add an account' : 'Edit the account', body, [{ label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }], 'wide');
  if (!ok) return;
  const b = { name: f.name.value, inNetWorth: f.inNetWorth.checked, hidden: f.hidden.checked, track: f.track.value };
  if (!monarch) Object.assign(b, { kind: f.kind.value, balance: f.balance.value || 0, currency: f.currency.value.toUpperCase(), institution: f.institution.value });
  Object.assign(b, who.value());
  if (THINGS.includes(f.kind.value)) {
    b.details = Object.fromEntries(Object.entries(det).filter(([k]) => !(monarch && k === 'yearlyRate')).map(([k, e]) => [k, e.value.trim()]));
    b.loanId = loan.value ? +loan.value : null;
  }
  try {
    const r = await api(isNew ? 'api/accounts' : `api/accounts/${a.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    toast(isNew ? 'Added' : 'Saved'); await refreshSummary();
    if (isNew) location.hash = `#/account/${r.id}`; else onRoute();
  } catch (e) { fail(e); }
}
/** Who sees an account, in its dialog: everyone with a role here (the household's) or only the people ticked (a
    private one: its owner always, and those they tick). Only the owner of a private account changes who sees it; an
    editor can make one of the household's private (theirs, then). {el, value(): the fields to send}. */
async function whoSees(a, isNew) {
  const me = S.user ? S.user.id : null;
  const mine = isNew || a.household || a.mine;  // a private one of someone else: only shown
  const canHousehold = may('household') && (isNew || a.household || a.mine);
  const canPrivate = isNew ? may('own') : a.household ? may('household') : a.mine;
  if (!isNew && !a.household && !a.mine) {
    return { el: h('p', { class: 'muted small', style: { marginTop: '12px' } }, icon('lock', 'xs'), ` Private: seen by ${seenBy(a)}. Only its owner changes who sees it.`), value: () => ({}) };
  }
  if (!canHousehold && !canPrivate) return { el: null, value: () => ({}) };
  let people = [];
  try { people = (await api('api/people')).items || []; } catch (e) { /* the list stays empty: only the owner */ }
  const owner = !isNew && !a.household ? a.people[0].id : me;
  const have = new Set((a.people || []).map((p) => p.id));
  const name = 'who-' + Math.random().toString(36).slice(2);
  const all = h('input', { type: 'radio', name, value: 'all', checked: (isNew ? canHousehold : a.household) ? true : null, disabled: canHousehold ? null : true });
  const some = h('input', { type: 'radio', name, value: 'some', checked: (isNew ? !canHousehold : !a.household) ? true : null, disabled: canPrivate ? null : true });
  const ticks = people.map((p) => ({ p, box: h('input', { type: 'checkbox', checked: p.id === owner || have.has(p.id) ? true : null, disabled: p.id === owner ? true : null }) }));
  const list = h('div', { class: 'chiprow', style: { gap: '14px', margin: '6px 0 0 24px' } },
    ticks.map(({ p, box }) => h('label', { class: 'check' }, box, p.id === owner ? `${p.id === me ? 'You' : p.name} (owner)` : p.id === me ? 'You' : p.name)));
  const draw = () => { list.style.display = some.checked ? '' : 'none'; };
  all.onchange = draw; some.onchange = draw; draw();
  const el = h('div', { class: 'whosees', style: { marginTop: '14px' } }, h('b', null, 'Who sees it'),
    h('label', { class: 'check', style: { display: 'flex', marginTop: '6px' } }, all, 'Everyone with a role in ioMoney (the household’s)'),
    h('label', { class: 'check', style: { display: 'flex', marginTop: '4px' } }, some, 'Only the people ticked'),
    list,
    h('p', { class: 'muted small', style: { margin: '6px 0 0' } }, 'Nobody else sees a private account, its balance or its transactions, an admin included; the totals each person sees leave it out.'));
  return {
    el,
    value: () => {
      const out = {};
      if (canHousehold || isNew) out.household = all.checked;
      if (some.checked) out.people = ticks.filter((t) => t.box.checked && t.p.id !== owner).map((t) => t.p.id);
      if (!isNew && !a.household && some.checked) delete out.household;  // stays private: only who sees it changes
      return mine ? out : {};
    },
  };
}
async function valueDialog(a) {
  const v = inp('', { inputmode: 'decimal', placeholder: money(a.estimate != null ? a.estimate : a.balance, a.currency) });
  const d = inp(today(), { type: 'date', max: today() });
  const n = inp('', { placeholder: 'Appraisal, Zillow, KBB, sale price of a neighbour…' });
  const ok = await dialog(`What ${a.name} is worth`, h('div', { class: 'grid' }, fld('Value', v), fld('On', d), fld('Where it comes from', n, true)), [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }]);
  if (!ok) return;
  try { await api(`api/accounts/${a.id}/values`, { method: 'POST', json: { value: v.value, day: d.value, note: n.value } }); toast('Added'); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
}

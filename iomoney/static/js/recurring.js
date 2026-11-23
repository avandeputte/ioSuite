/* Recurring: the bills and the money that comes in regularly. */
import { confirmDialog, dialog, fail, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, copyText, CUR, fld, fmtDay, followsTx, inp, money, S, today } from './core.js';
import { onRoute } from './main.js';
import { refreshSummary } from './shell.js';
import { categories } from './transactions.js';

// ------------------------------------------------------------------ recurring: bills and money coming in regularly
/** The household's recurring transactions (what ioCalendar shows on their days), and what ioMoney found in the
    transactions that looks recurring: Add, or Not recurring. */
export async function showRecurring(page) {
  const d = await api('api/recurring');
  const w = d.writable;
  S.freqs = d.frequencies;
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Recurring'), h('span', { class: 'grow' }),
    w ? h('button', { class: 'pillbtn', onclick: () => recurringDialog() }, icon('add'), h('span', null, 'Recurring')) : null));
  put(page, h('p', { class: 'muted' }, 'Bills, subscriptions and paychecks: what comes back at a steady pace. ioCalendar shows each on the day it is due, ticked once paid. ',
    'ioMoney looks for them in the transactions; add the ones that are, or add one by hand.'));
  const money2 = (x) => h('span', { class: `num ${x.amount < 0 ? '' : 'pos'}` }, `${x.approximate ? '≈ ' : ''}${money(x.amount, x.currency)}`);
  const row = (x) => h('li', null, h('div', { class: 'r', role: w ? 'button' : null, tabindex: w ? 0 : null, onclick: w ? () => recurringDialog(x) : null },
    h('span', { class: 'main' }, h('b', null, x.name, x.flag ? h('span', { class: 'tag warn', title: flagText(x) }, icon('warning', 'xs'), x.flag.kind === 'missed' ? (x.flow === 'out' ? 'Not paid' : 'Missing') : 'Amount changed') : null), h('small', null, [x.frequencyLabel, x.account || 'Any account', x.category, x.last ? `last ${fmtDay(x.last.day, x.last.day.slice(0, 4) !== today().slice(0, 4))} ${money(x.last.amount, x.currency)}` : 'not seen yet'].filter(Boolean).join(' · '))),
    h('span', { class: 'when' }, x.next ? `next ${fmtDay(x.next, true)}` : ''),
    h('span', { class: 'amt' }, money2(x))), x.provider ? providerLine(x.provider) : null);
  const monthly = (xs) => xs.reduce((s, x) => s + Math.abs(x.perMonth), 0);
  const subs = d.items.filter((x) => x.subscription);
  const bills = d.items.filter((x) => !x.subscription && x.flow === 'out');
  const income = d.items.filter((x) => !x.subscription && x.flow === 'in');
  if (!d.items.length) put(page, h('div', { class: 'empty' }, icon('repeat'), h('p', null, 'None in the list yet.'), h('p', { class: 'muted' }, d.found.length ? 'Add the ones found below.' : 'Add one by hand.')));
  else put(page, h('p', { class: 'sumline' }, `${d.items.length} recurring · out about `, h('span', { class: 'num' }, money(monthly(subs) + monthly(bills), CUR())), ' a month · in about ', h('span', { class: 'num pos' }, money(monthly(income), CUR())), ' a month'));
  const section = (title, ic, xs, note, empty) => {
    if (!xs.length && !empty) return;
    put(page, h('h2', { class: 'recurhead' }, icon(ic), h('span', null, `${title} (${xs.length})`), h('span', { class: 'grow' }), xs.length ? note : null));
    put(page, xs.length ? h('ul', { class: 'rows recur' }, xs.map(row)) : h('p', { class: 'muted' }, empty));
  };
  // what is off: a payment that did not come, an amount that changed
  const flagged = d.items.filter((x) => x.flag);
  if (flagged.length) {
    put(page, h('h2', { class: 'recurhead' }, icon('warning'), h('span', null, `To check (${flagged.length})`)));
    put(page, h('ul', { class: 'rows recur flagged' }, flagged.map((x) => {
      const f = x.flag;
      const act = (label, fn, cls) => h('button', { class: `pillbtn tiny ${cls || ''}`, onclick: async (e) => { e.stopPropagation(); try { await fn(); await refreshSummary(); onRoute(); } catch (er) { fail(er); } } }, label);
      const ok = () => api(`api/recurring/${x.id}/ok`, { method: 'POST', json: { kind: f.kind, day: f.day } });
      const acts = !x.writable ? null : f.kind === 'changed'
        ? [act(`Use ${money(Math.abs(f.to), x.currency)}`, () => api(`api/recurring/${x.id}`, { method: 'PATCH', json: { amount: Math.abs(f.to) } }), 'primary'), act('Dismiss', ok)]
        : [act('Dismiss', ok), act('It stopped', async () => { if (await confirmDialog('Remove it', `Remove ${x.name} from the recurring transactions?`, 'Remove', true)) await api(`api/recurring/${x.id}`, { method: 'DELETE' }); })];
      return h('li', null, h('div', { class: 'r' },
        h('span', { class: 'main' }, h('b', null, x.name), h('small', null, flagText(x))),
        h('span', { class: 'amt' }, money2(x)), acts ? h('span', { class: 'end acts', style: { flexDirection: 'row', gap: '6px' } }, acts) : null));
    })));
  }
  const subsFound = d.found.filter((x) => x.subscription).length;
  section('Subscriptions', 'play', subs, h('span', { class: 'muted small' }, h('span', { class: 'num' }, money(monthly(subs), CUR())), ' a month · ', h('span', { class: 'num' }, money(monthly(subs) * 12, CUR())), ' a year'),
    subsFound ? `None yet. ${subsFound} found in the transactions below ${subsFound === 1 ? 'is' : 'are'} marked Subscription: Add ${subsFound === 1 ? 'it' : 'them'} here.`
      : 'None yet. Netflix, Spotify, iCloud and the like land here once added; mark any recurring one as a subscription, or open a transaction and choose Make recurring.');
  section('Bills', 'repeat', bills, h('span', { class: 'muted small' }, h('span', { class: 'num' }, money(monthly(bills), CUR())), ' a month'));
  section('Money coming in', 'download', income, h('span', { class: 'muted small' }, h('span', { class: 'num pos' }, money(monthly(income), CUR())), ' a month'));
  if (d.found.length) {
    put(page, h('h2', { class: 'recurhead' }, icon('search'), h('span', null, `Found in the transactions (${d.found.length})`)));
    put(page, h('ul', { class: 'rows recur found' }, d.found.map((x) => {
      const add = h('button', { class: 'pillbtn primary tiny' }, icon('add', 'xs'), 'Add');
      const not = h('button', { class: 'pillbtn tiny' }, 'Not recurring');
      add.onclick = async () => { try { await api('api/recurring', { method: 'POST', json: { found: x.key } }); toast('Added'); onRoute(); } catch (e) { fail(e); } };
      not.onclick = async () => { try { await api('api/recurring/not', { method: 'POST', json: { key: x.key } }); add.closest('li').remove(); } catch (e) { fail(e); } };
      return h('li', null, h('div', { class: 'r' },
        h('span', { class: 'main' }, h('b', null, x.name, x.subscription ? h('span', { class: 'tag' }, 'Subscription') : null), h('small', null, [x.frequencyLabel, x.account, x.category, `${x.count} times, last ${fmtDay(x.day, true)}`].filter(Boolean).join(' · '))),
        h('span', { class: 'when' }, x.next ? `next ${fmtDay(x.next, true)}` : ''),
        h('span', { class: 'amt' }, money2(x)), w ? h('span', { class: 'end acts', style: { flexDirection: 'row', gap: '6px' } }, add, not) : null));
    })));
  }
}
/** Under a bill on the Recurring page: the account number with its provider (to copy when calling them), their phone,
    website and note. */
function providerLine(p) {
  const stop = (e) => e.stopPropagation();
  const bits = [];
  if (p.accountNumber) bits.push(h('span', { class: 'secret' }, h('span', { class: 'muted' }, 'Account '), h('span', { class: 'num' }, p.accountNumber),
    h('button', { class: 'iconbtn', title: 'Copy the account number', 'aria-label': 'Copy the account number', onclick: (e) => { stop(e); copyText(p.accountNumber); } }, icon('copy', 's'))));
  if (p.phone) bits.push(h('a', { class: 'lnk', href: `tel:${p.phone.replace(/[^0-9+]/g, '')}`, onclick: stop }, p.phone));
  if (p.website) bits.push(h('a', { class: 'lnk', href: p.website, target: '_blank', rel: 'noopener noreferrer', onclick: stop }, p.website.replace(/^https?:\/\//i, '').replace(/\/$/, '')));
  if (p.note) bits.push(h('span', { class: 'muted' }, p.note));
  return h('div', { class: 'provider small' }, bits);
}
/** What a recurring transaction's flag says: the payment that did not come, or the amount that changed. */
function flagText(x) {
  const f = x.flag;
  if (f.kind === 'changed') {
    const up = Math.abs(f.to) > Math.abs(f.from);
    return `${x.flow === 'out' ? (up ? 'Went up' : 'Came down') : (up ? 'More than usual' : 'Less than usual')}: ${money(Math.abs(f.to), x.currency)} on ${fmtDay(f.day, true)}, ${x.approximate ? 'usually about' : 'was'} ${money(Math.abs(f.from), x.currency)}`;
  }
  return `${x.flow === 'out' ? 'Not paid' : 'Did not come'}: expected about ${fmtDay(f.expected, true)}, last seen ${fmtDay(f.since, true)}`;
}
/** Add a recurring transaction by hand, or change or remove one. */
export async function recurringDialog(x, preset) {
  const isNew = !x;
  x = x || preset || { flow: 'out', frequency: 'monthly', day: today(), approximate: false };
  const cats = await categories();
  const freqs = S.freqs || [];
  const f = { name: inp(x.name, { placeholder: 'Power bill, Netflix, Paycheck' }), pattern: inp(x.pattern, { placeholder: 'the payee’s name or words of the bank’s text' }),
    account: h('select', { class: 't' }, h('option', { value: '' }, 'Any account'), S.accounts.filter(followsTx).map((a) => h('option', { value: a.id, selected: a.id === x.accountId ? true : null }, a.name))),
    flow: h('select', { class: 't' }, h('option', { value: 'out', selected: x.flow === 'out' ? true : null }, 'Money out (a bill)'), h('option', { value: 'in', selected: x.flow === 'in' ? true : null }, 'Money in (a paycheck)')),
    amount: inp(x.amount != null ? Math.abs(x.amount) : '', { inputmode: 'decimal' }), approximate: h('input', { type: 'checkbox', checked: x.approximate ? true : null }),
    subscription: h('input', { type: 'checkbox', checked: x.subscription ? true : null }),
    frequency: h('select', { class: 't' }, freqs.map((q) => h('option', { value: q.value, selected: q.value === x.frequency ? true : null }, q.label))),
    day: inp(x.day, { type: 'date' }), category: inp(x.category, { list: 'reccats' }) };
  const pv = x.provider || {};
  const pf = { accountNumber: inp(pv.accountNumber, { autocomplete: 'off', spellcheck: 'false', maxlength: 128, placeholder: 'on their bills' }),
    phone: inp(pv.phone, { type: 'tel', maxlength: 64, placeholder: '1-800-…' }), website: inp(pv.website, { type: 'url', maxlength: 255, placeholder: 'https://…' }),
    note: inp(pv.note, { maxlength: 500, placeholder: 'meter number, service address…' }) };
  const body = h('div', null, h('datalist', { id: 'reccats' }, cats.map((c) => h('option', { value: c.category }))),
    h('div', { class: 'grid' }, fld('Name', f.name, true), fld('Its payee or bank’s text has', f.pattern, true), fld('Account', f.account), fld('Way', f.flow),
      fld('Usual amount', f.amount), fld('How often', f.frequency), fld('A day it falls on', f.day), fld('Category', f.category)),
    h('label', { class: 'check', style: { marginTop: '10px' } }, f.approximate, 'The amount varies (a payment within a third of it counts)'),
    h('label', { class: 'check', style: { marginTop: '6px' } }, f.subscription, isNew ? 'A subscription to a service (Netflix, Spotify, iCloud…; a known one is marked on its own)' : 'A subscription to a service (shown under Subscriptions)'),
    h('h3', { class: 'sub', style: { marginTop: '16px' } }, 'With the provider'),
    h('div', { class: 'grid' }, fld('Account number', pf.accountNumber), fld('Phone', pf.phone), fld('Website', pf.website), fld('Note', pf.note)),
    h('p', { class: 'muted small' }, 'Your account or customer number with the power company, the water board, the internet provider… Seen by whoever sees this recurring transaction (and its account), on ioCalendar’s bill card too. No passwords or PINs here.'));
  const btns = [!isNew ? { label: 'Remove', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  if (isNew && preset) body.prepend(h('p', { class: 'muted small', style: { marginTop: 0 } }, preset.count > 1
    ? `From this transaction and the ${preset.count - 1} other${preset.count === 2 ? '' : 's'} like it in the past year: check how often and the amount.`
    : 'From this transaction, the only one like it in the past year: check how often it comes back.'));
  const ok = await dialog(isNew ? (preset ? 'Make it recurring' : 'Add a recurring transaction') : x.name, body, btns, 'wide');
  if (ok === 'delete') {
    if (!await confirmDialog('Remove it', `Remove ${x.name} from the recurring transactions? Its transactions stay.`, 'Remove', true)) return;
    try { await api(`api/recurring/${x.id}`, { method: 'DELETE' }); toast('Removed'); onRoute(); } catch (e) { fail(e); } return;
  }
  if (!ok) return;
  const b = { name: f.name.value, pattern: f.pattern.value || f.name.value, accountId: f.account.value ? +f.account.value : null, flow: f.flow.value,
    amount: f.amount.value, approximate: f.approximate.checked, frequency: f.frequency.value, day: f.day.value, category: f.category.value };
  if (!isNew || preset || f.subscription.checked) b.subscription = f.subscription.checked;
  const prov = Object.fromEntries(Object.entries(pf).map(([k, el]) => [k, el.value.trim()]).filter(([k, v]) => v !== (pv[k] || '')));
  if (Object.keys(prov).length) b.provider = prov;
  try { await api(isNew ? 'api/recurring' : `api/recurring/${x.id}`, { method: isNew ? 'POST' : 'PATCH', json: b }); toast(isNew ? 'Added' : 'Saved'); onRoute(); } catch (e) { fail(e); }
}

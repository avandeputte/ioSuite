/* Rules (rename and categorize as transactions come in) and transfers between accounts. */
import { confirmDialog, dialog, fail, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { amt, api, fld, fmtDay, followsTx, inp, may, money, S, store } from './core.js';
import { onRoute, route } from './main.js';
import { drawUpkeep } from './tidy.js';
import { categories, txDialog } from './transactions.js';

// ------------------------------------------------------------------ rules: rename and categorize as they come in
const RULE_FIELD = { either: 'The payee or the bank’s text', merchant: 'The payee', description: 'The bank’s text' };
const RULE_HOW = { contains: 'contains', is: 'is', starts: 'starts with' };
function ruleWhen(x) {
  const bits = [`${RULE_FIELD[x.field]} ${RULE_HOW[x.how]} “${x.pattern}”`];
  if (x.account) bits.push(`in ${x.account}`);
  if (x.flow) bits.push(x.flow === 'out' ? 'money out' : 'money in');
  if (x.amountMin != null && x.amountMax != null) bits.push(`${money(x.amountMin)} to ${money(x.amountMax)}`);
  else if (x.amountMin != null) bits.push(`${money(x.amountMin)} or more`);
  else if (x.amountMax != null) bits.push(`up to ${money(x.amountMax)}`);
  return bits.join(' · ');
}
function ruleThen(x) {
  return [x.setMerchant ? `Rename to “${x.setMerchant}”` : null, x.setCategory ? `Category ${x.setCategory}` : null,
    x.setHidden === true ? 'Hide it' : x.setHidden === false ? 'Show it' : null].filter(Boolean).join(' · ');
}
export async function showRules(page) {
  const d = await api('api/rules');
  const items = d.items || [];
  const w = d.writable;
  const apply = async () => { try { const r = await api('api/rules/apply', { method: 'POST' }); toast(`${r.changed} transaction${r.changed === 1 ? '' : 's'} changed`); } catch (e) { fail(e); } };
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Rules'), h('span', { class: 'grow' }),
    w && items.length ? h('button', { class: 'pillbtn', onclick: apply, title: 'Run every rule over the transactions there are now' }, icon('sync'), h('span', null, 'Apply now')) : null,
    w ? h('button', { class: 'pillbtn', onclick: () => ruleDialog() }, icon('add'), h('span', null, 'Rule')) : null));
  put(page, h('p', { class: 'muted' }, 'Rules rename the payee, set the category or hide a transaction when it comes in from Monarch Money or is added here. ',
    'They are tried from the top: for each of the three, the first rule that matches wins. A transaction you changed by hand stays as you left it.'));
  if (!items.length) {
    put(page, h('div', { class: 'empty' }, icon('tune'), h('p', null, 'No rules yet.'),
      h('p', { class: 'muted' }, w ? 'Add one here, or open a transaction and choose Make a rule.' : 'Editors add them.')));
  }
  const move = async (i, by) => {
    const ids = items.map((x) => x.id); const [x] = ids.splice(i, 1); ids.splice(i + by, 0, x);
    try { await api('api/rules/order', { method: 'PUT', json: { ids } }); onRoute(); } catch (e) { fail(e); }
  };
  const sug = h('div');
  put(page, sug);
  put(page, h('ul', { class: 'rows rules' }, items.map((x, i) => h('li', { class: x.enabled ? null : 'off', 'data-rule': x.id }, h('div', { class: 'r' },
    h('span', { class: 'n' }, i + 1),
    h('span', { class: 'main' }, h('b', null, ruleThen(x)), h('small', null, ruleWhen(x), h('span', { class: 'upk' }))),
    !x.enabled ? h('span', { class: 'tag' }, 'Off') : null,
    w ? h('span', { class: 'end acts' },
      h('button', { class: 'iconbtn', title: 'Tried earlier', disabled: i === 0 ? true : null, onclick: () => move(i, -1) }, icon('prev', 's up')),
      h('button', { class: 'iconbtn', title: 'Tried later', disabled: i === items.length - 1 ? true : null, onclick: () => move(i, 1) }, icon('next', 's down')),
      h('button', { class: 'iconbtn', title: 'Edit', onclick: () => ruleDialog(x) }, icon('edit', 's'))) : null)))));
  api('api/rules/upkeep').then((u) => drawUpkeep(page, sug, u)).catch(() => {});  // what each rule does: counted apart, it takes a moment
  await drawTransferRules(page);
}
/** The transfer rules: in this account, a payee like this is a transfer with that account. ioMoney learns one each
    time it finds a transfer by itself; editors add, change and delete them. */
async function drawTransferRules(page) {
  const d = await api('api/transfer-rules');
  const items = d.items || [];
  const w = d.writable;
  const linkNow = () => transferMaintenance();
  put(page, h('div', { class: 'pagehead', style: { marginTop: '28px' } }, h('h2', { class: 'h1ish' }, icon('link'), 'Transfers'), h('span', { class: 'grow' }),
    w ? h('button', { class: 'pillbtn', onclick: linkNow, title: 'Look for transfers among every transaction not linked yet' }, icon('sync'), h('span', null, 'Link transfers now')) : null,
    w ? h('button', { class: 'pillbtn', onclick: () => transferRuleDialog() }, icon('add'), h('span', null, 'Transfer rule')) : null));
  put(page, h('p', { class: 'muted' }, 'Money that leaves one of your accounts and arrives in another (to savings, a card’s payment, a loan’s payment) is one transfer, linked and left out of the spending. ',
    'ioMoney links the two halves when the amounts match, the days are close and the payee or category says it is a transfer; each one it finds teaches it a rule, so the next is found even a few days later. ',
    'Open a transaction to link or unlink it by hand.'));
  if (!items.length) { put(page, h('p', { class: 'muted small' }, 'No transfer rules yet.')); return; }
  put(page, h('ul', { class: 'rows rules' }, items.map((x) => h('li', null, h('div', { class: 'r' },
    h('span', { class: 'main' }, h('b', null, `${x.account || '?'} ⇄ ${x.other || '?'}`),
      h('small', null, `In ${x.account || '?'}, the payee “${x.pattern}”, up to ${x.days} day${x.days === 1 ? '' : 's'} apart`)),
    x.source === 'learned' ? h('span', { class: 'tag', title: 'Learned from a transfer ioMoney found' }, 'Learned') : null,
    w ? h('span', { class: 'end acts' }, h('button', { class: 'iconbtn', title: 'Edit', onclick: () => transferRuleDialog(x) }, icon('edit', 's'))) : null)))));
}
/** The maintenance: go through every transaction and link the transfers (card, bank and loan payments), then show
    what still looks like one but was not linked on its own page, to check. */
export function transferMaintenance() { location.hash = '#/transfers?run=1'; }
const WHY = [['', 'Any reason'], ['as likely', 'As likely as another'], ['nothing says', 'Nothing says it is a transfer'], ['days apart', 'Too many days apart']];
/** Transfers to check: the same amount out of one account and into another within two weeks, not linked: each with
    both sides in full, why it was not linked, and Link or Not a transfer. ?run=1 first links what it can. */
export async function showTransfers(page, r) {
  let ran = null;
  if (r.q.run) {
    toast('Going through every transaction…');
    ran = await api('api/transfers/link', { method: 'POST' });
    history.replaceState(null, '', '#/transfers');
  }
  const items = ran ? ran.possible : ((await api('api/transfers/possible')).items || []);
  const f = { why: store.get('tfWhy') || '', acct: store.get('tfAcct') || '', q: '', sort: store.get('tfSort') || 'day' };
  put(page, h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: '#/rules', title: 'Rules', 'aria-label': 'Rules' }, icon('prev')),
    h('h1', null, 'Transfers to check'), h('span', { class: 'grow' }),
    may('write') ? h('button', { class: 'pillbtn', onclick: () => { location.hash = '#/transfers?run=1'; }, title: 'Go through every transaction not linked yet' }, icon('sync'), h('span', null, 'Link transfers now')) : null));
  if (ran) put(page, h('p', { class: 'banner ok' }, icon('check', 's'), ` ${ran.linked} transfer${ran.linked === 1 ? '' : 's'} linked`, ran.learned ? `, ${ran.learned} transfer rule${ran.learned === 1 ? '' : 's'} learned` : '', '.'));
  put(page, h('p', { class: 'muted' }, 'The same amount out of one account and into another, within two weeks, that ioMoney did not link by itself. ',
    'Link the ones that are one transfer; Not a transfer takes a pair off this list for good.'));
  if (!items.length) { put(page, h('div', { class: 'empty' }, icon('link'), h('p', null, 'Nothing left to check.'))); return; }
  const accts = [...new Map(items.flatMap((p) => [p.out, p.in]).filter((t) => t.accountId).map((t) => [t.accountId, t.account])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const sel = (opts, v, on) => { const e = h('select', { class: 't' }, opts.map(([k, l]) => h('option', { value: k, selected: k === v ? true : null }, l))); e.onchange = () => on(e.value); return e; };
  const count = h('span', { class: 'muted small' });
  const list = h('div', { class: 'tfx' });
  const gone = new Set();  // transactions linked or set aside here: their other pairs leave the list
  const side = (t) => h('div', { class: 'side' },
    h('div', { class: 'acct' }, t.accountId ? h('a', { class: 'lnk', href: `#/account/${t.accountId}` }, t.account) : (t.account || 'Someone’s private account')),
    h('div', { class: 'meta' }, fmtDay(t.day, true), t.category ? h('span', { class: 'tag' }, t.category) : null),
    h('button', { class: 'payee', title: 'Open the transaction', onclick: () => txDialog(t) }, t.merchant || t.description || '—'),
    t.description && t.description !== t.merchant ? h('div', { class: 'bank' }, t.description) : null);
  const draw = () => {
    const q = f.q.trim().toLowerCase();
    let shown = items.filter((p) => !gone.has(p.out.id) && !gone.has(p.in.id) && (!f.why || p.why.includes(f.why))
      && (!f.acct || String(p.out.accountId) === f.acct || String(p.in.accountId) === f.acct)
      && (!q || [p.out, p.in].some((t) => [t.merchant, t.description, t.account, t.category].some((x) => (x || '').toLowerCase().includes(q))) || String(Math.abs(p.out.amount)).includes(q)));
    // pairs that share a transaction are one choice (a tie): kept together, the choice said once
    const root = new Map();
    const find = (x) => { while (root.get(x) !== x) x = root.get(x); return x; };
    for (const p of shown) {
      for (const k of [`o${p.out.id}`, `i${p.in.id}`]) if (!root.has(k)) root.set(k, k);
      root.set(find(`o${p.out.id}`), find(`i${p.in.id}`));
    }
    const groups = new Map();
    for (const p of shown) { const g = find(`o${p.out.id}`); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(p); }
    const day = (p) => (p.out.day > p.in.day ? p.out.day : p.in.day);
    const gday = (g) => g.map(day).sort().pop();
    const gamt = (g) => Math.abs(g[0].out.amount);
    const sorted = [...groups.values()].sort(f.sort === 'amount' ? (a, b) => gamt(b) - gamt(a) || gday(b).localeCompare(gday(a))
      : (a, b) => gday(b).localeCompare(gday(a)) || gamt(b) - gamt(a));
    count.textContent = `${shown.length} of ${items.length - [...items].filter((p) => gone.has(p.out.id) || gone.has(p.in.id)).length}`;
    const same = (a, b) => a.accountId === b.accountId && a.day === b.day && a.amount === b.amount && (a.merchant || '') === (b.merchant || '') && (a.description || '') === (b.description || '');
    const twins = (g) => {  // the same transaction twice on one side: a duplicate from the bank or Monarch Money
      const seen = (side) => [...new Map(g.map((p) => [p[side].id, p[side]])).values()];
      return ['out', 'in'].map((sd) => seen(sd)).find((ts) => ts.length > 1 && ts.every((t) => same(t, ts[0])));
    };
    const tieNote = (g) => {
      const dup = twins(g);
      if (dup) return h('div', { class: 'tfnote' }, icon('warning', 'xs'), ` ${dup.length} identical transactions in ${dup[0].account || 'one account'} on ${fmtDay(dup[0].day, true)} (“${dup[0].merchant || dup[0].description || ''}”): most likely a duplicate from the bank or Monarch Money. Link one; then open the other to check it.`);
      return h('div', { class: 'tfnote' }, `${g.length} ways to pair these, each as likely: link the right one.`);
    };
    const rowOf = (p) => {
      const apart = Math.round(Math.abs(new Date(p.out.day) - new Date(p.in.day)) / 864e5);
      const can = p.out.writable && p.in.writable;
      const link = h('button', { class: 'pillbtn primary' }, icon('link', 'xs'), 'Link');
      const not = h('button', { class: 'pillbtn' }, 'Not a transfer');
      link.onclick = async () => { try { await api(`api/transactions/${p.out.id}/transfer`, { method: 'PUT', json: { with: p.in.id } }); gone.add(p.out.id); gone.add(p.in.id); toast('Linked'); draw(); } catch (e) { fail(e); } };
      not.onclick = async () => { try { await api('api/transfers/not', { method: 'POST', json: { outId: p.out.id, inId: p.in.id } }); items.splice(items.indexOf(p), 1); draw(); } catch (e) { fail(e); } };
      return h('div', { class: 'tfr' }, h('div', { class: 'amt num' }, money(Math.abs(p.out.amount), p.out.currency)),
        side(p.out), side(p.in), h('div', { class: 'apart' }, apart === 0 ? 'Same day' : `${apart} day${apart === 1 ? '' : 's'}`),
        h('div', { class: 'why' }, p.why), h('div', { class: 'acts' }, can ? [link, not] : null));
    };
    list.replaceChildren(h('div', { class: 'tfh' }, h('span', null, 'Amount'), h('span', null, 'Out of'), h('span', null, 'Into'), h('span', null, 'Apart'), h('span', null, 'Not linked because'), h('span')),
      ...sorted.map((g) => (g.length > 1 ? h('div', { class: 'tfg' }, tieNote(g), g.map(rowOf)) : rowOf(g[0]))));
  };
  const search = inp('', { type: 'search', placeholder: 'Payee, account, amount…' });
  search.oninput = () => { f.q = search.value; draw(); };
  put(page, h('div', { class: 'filters tff' }, search,
    sel([['', 'Every account'], ...accts.map(([id, n]) => [String(id), n])], f.acct, (v) => { f.acct = v; store.set('tfAcct', v); draw(); }),
    sel(WHY, f.why, (v) => { f.why = v; store.set('tfWhy', v); draw(); }),
    sel([['day', 'Newest first'], ['amount', 'Largest first']], f.sort, (v) => { f.sort = v; store.set('tfSort', v); draw(); }), count), list);
  draw();
}
async function transferRuleDialog(x) {
  const isNew = !x;
  x = x || { days: 5 };
  const acctSel = (v) => h('select', { class: 't' }, h('option', { value: '' }, 'Choose…'), S.accounts.filter(followsTx).map((a) => h('option', { value: a.id, selected: a.id === v ? true : null }, a.name)));
  const f = { account: acctSel(x.accountId), pattern: inp(x.pattern, { placeholder: 'ally bank, payment thank you' }), other: acctSel(x.otherId),
    days: inp(x.days, { type: 'number', min: 0, max: 31, style: { width: '90px' } }) };
  const body = h('div', null, h('div', { class: 'grid' }, fld('In the account', f.account), fld('A payee or bank’s text with', f.pattern),
    fld('Is a transfer with', f.other), fld('At most this many days apart', f.days)));
  const btns = [!isNew ? { label: 'Delete', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  const ok = await dialog(isNew ? 'Add a transfer rule' : 'Edit the transfer rule', body, btns, 'wide');
  if (ok === 'delete') { try { await api(`api/transfer-rules/${x.id}`, { method: 'DELETE' }); toast('Deleted'); onRoute(); } catch (e) { fail(e); } return; }
  if (!ok) return;
  const b = { accountId: +f.account.value || null, pattern: f.pattern.value, otherId: +f.other.value || null, days: f.days.value };
  try {
    const r = await api(isNew ? 'api/transfer-rules' : `api/transfer-rules/${x.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    toast(`${isNew ? 'Added' : 'Saved'}${r.linked ? `: ${r.linked} transfer${r.linked === 1 ? '' : 's'} linked` : ''}`); onRoute();
  } catch (e) { fail(e); }
}
/** Add a rule, or change one. As it is typed, the transactions it matches are counted, with the newest few. */
export async function ruleDialog(x, preset) {
  const isNew = !x;
  x = x || { field: 'either', how: 'contains', enabled: true, ...(preset || {}) };
  const cats = await categories();
  const sel = (opts, v) => h('select', { class: 't' }, Object.entries(opts).map(([k, l]) => h('option', { value: k, selected: k === (v || '') ? true : null }, l)));
  const f = {
    field: sel(RULE_FIELD, x.field), how: sel(RULE_HOW, x.how), pattern: inp(x.pattern, { placeholder: 'AMZN, Shell, PAYPAL *NETFLIX' }),
    account: h('select', { class: 't' }, h('option', { value: '' }, 'Any account'), S.accounts.filter(followsTx).map((a) => h('option', { value: a.id, selected: a.id === x.accountId ? true : null }, a.name))),
    flow: sel({ '': 'In or out', out: 'Money out', in: 'Money in' }, x.flow), amountMin: inp(x.amountMin, { inputmode: 'decimal', placeholder: 'Any' }),
    amountMax: inp(x.amountMax, { inputmode: 'decimal', placeholder: 'Any' }),
    setMerchant: inp(x.setMerchant, { placeholder: 'Leave the payee as it is' }), setCategory: inp(x.setCategory, { list: 'rulecats', placeholder: 'Leave the category as it is' }),
    setHidden: sel({ '': 'Leave it as it is', true: 'Hide it (left out of the sums)', false: 'Show it' }, x.setHidden == null ? '' : String(x.setHidden)),
    enabled: h('input', { type: 'checkbox', checked: x.enabled ? true : null }), apply: h('input', { type: 'checkbox', checked: true }),
  };
  const found = h('div', { class: 'rulefound muted small' });
  const when = () => ({ field: f.field.value, how: f.how.value, pattern: f.pattern.value, accountId: f.account.value ? +f.account.value : null,
    flow: f.flow.value || null, amountMin: f.amountMin.value || null, amountMax: f.amountMax.value || null });
  let tm, seq = 0;
  const look = () => {
    clearTimeout(tm);
    tm = setTimeout(async () => {
      const n = ++seq;
      if (!f.pattern.value.trim()) { found.replaceChildren(); return; }
      try {
        const r = await api('api/rules/test', { method: 'POST', json: when() });
        if (n !== seq) return;
        found.replaceChildren(h('p', null, r.count ? `Matches ${r.count} transaction${r.count === 1 ? '' : 's'}${r.edited ? ` (${r.edited} changed by hand stay as they are)` : ''}:` : 'Matches no transaction yet.'),
          r.sample.length ? h('ul', { class: 'rows flat' }, r.sample.map((t) => h('li', null, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(t.day)),
            h('span', { class: 'main' }, h('b', null, t.merchant || t.description || '(no payee)'), h('small', null, [t.description !== t.merchant ? t.description : null, t.category, t.account].filter(Boolean).join(' · '))),
            h('span', { class: 'end' }, amt(t.amount, t.currency)))))) : null);
      } catch (e) { if (n === seq) found.replaceChildren(h('p', { class: 'warn' }, e.message || String(e))); }
    }, 300);
  };
  for (const k of ['field', 'how', 'pattern', 'account', 'flow', 'amountMin', 'amountMax']) f[k].addEventListener(f[k].tagName === 'SELECT' ? 'change' : 'input', look);
  look();
  const body = h('div', null, h('datalist', { id: 'rulecats' }, cats.map((c) => h('option', { value: c.category }))),
    h('h3', { class: 'sub' }, 'When'),
    h('div', { class: 'grid' }, fld('Look in', f.field), fld('Match', f.how), fld('The words', f.pattern, true),
      fld('Account', f.account), fld('Direction', f.flow), fld('From (amount)', f.amountMin), fld('Up to', f.amountMax)),
    found,
    h('h3', { class: 'sub' }, 'Then'),
    h('div', { class: 'grid' }, fld('Rename the payee to', f.setMerchant, true), fld('Set the category to', f.setCategory), fld('Hidden', f.setHidden)),
    h('div', { class: 'chiprow', style: { marginTop: '12px', gap: '16px' } }, h('label', { class: 'check' }, f.enabled, 'On'),
      h('label', { class: 'check' }, f.apply, 'Also change the transactions there are now')));
  const btns = [!isNew ? { label: 'Delete', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  const ok = await dialog(isNew ? 'Add a rule' : 'Edit the rule', body, btns, 'wide');
  clearTimeout(tm); seq++;
  if (ok === 'delete') {
    if (!await confirmDialog('Delete the rule', 'The transactions it changed keep their payee and category until Monarch Money sends them again.', 'Delete', true)) return;
    try { await api(`api/rules/${x.id}`, { method: 'DELETE' }); toast('Deleted'); onRoute(); } catch (e) { fail(e); }
    return;
  }
  if (!ok) return;
  const b = { ...when(), setMerchant: f.setMerchant.value, setCategory: f.setCategory.value,
    setHidden: f.setHidden.value === '' ? null : f.setHidden.value === 'true', enabled: f.enabled.checked, apply: f.apply.checked };
  try {
    const r = await api(isNew ? 'api/rules' : `api/rules/${x.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    S.cats = [];
    toast(r.changed != null ? `${isNew ? 'Added' : 'Saved'}: ${r.changed} transaction${r.changed === 1 ? '' : 's'} changed` : (isNew ? 'Added' : 'Saved'));
    if (route().view === 'rules' || route().view === 'transactions' || route().view === 'account') onRoute(); else location.hash = '#/rules';
  } catch (e) { fail(e); }
}

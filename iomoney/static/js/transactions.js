/* Transactions: the list with its filters and saved searches, one transaction (its receipts, its split, its
   transfer, what is linked to it), and its history. */
import { closeDialogs, confirmDialog, dialog, fail, fill, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { amt, api, dateOf, fld, fmtDay, fmtMonth, followsTx, inp, linkUi, may, money, S, shiftMonth, store, thisMonth, today } from './core.js';
import { onRoute, route } from './main.js';
import { recurringDialog } from './recurring.js';
import { ruleDialog } from './rules.js';
import { drawNav, refreshSummary, sameSearch } from './shell.js';
import { agoSec, drawBulk } from './tidy.js';

// ------------------------------------------------------------------ transactions
export async function categories() {
  if (!S.cats.length) { try { S.cats = (await api('api/categories')).items || []; } catch { S.cats = []; } }
  return S.cats;
}
/** #/transaction/12 (a link from another app's item, say): the transactions of its account and month, with it open. */
export async function showTransaction(page, r) {
  const t = await api(`api/transactions/${r.id}`);
  const q = { account: String(t.accountId), month: t.day.slice(0, 7) };
  history.replaceState(null, '', `#/transactions?${new URLSearchParams(q)}`);
  await showTransactions(page, { view: 'transactions', q });
  txDialog(t);
}
/** The transactions, one row each: date, payee, notes, category (or where a transfer went) and amount (and the
    account, where the list mixes them). On a phone the notes and the account give way, the category goes under the payee. */
const fmtTxDay = (s) => { const d = dateOf(s); return d.toLocaleDateString(undefined, d.getFullYear() === new Date().getFullYear() ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: '2-digit' }); };
function txCat(t) {
  if (t.transfer) return h('span', { class: 'xfer', title: `A transfer ${t.amount < 0 ? 'to' : 'from'} ${t.transfer.account}${t.transfer.how === 'hand' ? ' (linked by hand)' : ''}` }, icon('link', 'xs'), `${t.amount < 0 ? 'To' : 'From'} ${t.transfer.account}`);
  if (t.splits && t.splits.length) return h('span', { class: 'split', title: t.splits.map((p) => `${p.category || 'Uncategorized'} ${money(p.amount, t.currency)}`).join(' · ') }, icon('split', 'xs'), [...new Set(t.splits.map((p) => p.category || 'Uncategorized'))].join(', '));
  return t.category ? h('span', null, t.category) : h('span', { class: 'muted' }, 'Uncategorized');
}
export function txList(items, showAccount = true, showBank = store.get('txbank') === '1', opt = {}) {
  if (!items.length) return h('p', { class: 'muted' }, 'No transactions.');
  const cls = `rows flat txs ${showAccount ? 'withacct' : ''} ${showBank ? 'withbank' : ''} ${opt.picked ? 'sel' : ''}`;
  const boxes = [];
  const pick = (t) => {  // a tick to change several at once (opt.picked: the ids ticked; opt.onPick: after each change)
    if (!opt.picked) return null;
    if (!t.writable) return h('span', { class: 's' });
    const b = h('input', { type: 'checkbox', 'aria-label': 'Select', checked: opt.picked.has(t.id) ? true : null, onclick: (e) => e.stopPropagation(),
      onchange: () => { if (b.checked) opt.picked.add(t.id); else opt.picked.delete(t.id); b.closest('li').classList.toggle('picked', b.checked); opt.onPick(); } });
    boxes.push([t, b]);
    return h('span', { class: 's', onclick: (e) => e.stopPropagation() }, b);
  };
  const all = opt.picked ? h('input', { type: 'checkbox', title: 'Select all shown', 'aria-label': 'Select all shown', onchange: (e) => {
    for (const [t, b] of boxes) { b.checked = e.target.checked; b.closest('li').classList.toggle('picked', b.checked); if (b.checked) opt.picked.add(t.id); else opt.picked.delete(t.id); }
    opt.onPick();
  } }) : null;
  return h('ul', { class: cls },
    h('li', { class: 'txhead' }, h('div', { class: 'r tx' }, opt.picked ? h('span', { class: 's' }, all) : null, h('span', { class: 'd' }, 'Date'), h('span', { class: 'p' }, 'Payee'),
      showBank ? h('span', { class: 'b' }, 'At the bank') : null, h('span', { class: 'n' }, 'Notes'), h('span', { class: 'c' }, 'Category'), showAccount ? h('span', { class: 'a' }, 'Account') : null, h('span', { class: 'm' }, 'Amount'), h('span', { class: 'rc', title: opt.review ? 'Reviewed' : 'Reconciled' }, '✓'))),
    items.map((t) => h('li', { class: t.hidden ? 'off' : null }, h('div', { class: 'r tx', role: 'button', tabindex: 0, onclick: () => txDialog(t),
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) txDialog(t); } },
      pick(t),
      h('span', { class: 'd' }, fmtTxDay(t.day)),
      h('span', { class: 'p' }, h('b', null, t.merchant || t.description || '(no payee)'),
        t.recurring ? h('span', { class: 'rec', title: `Recurring: ${t.recurring.name}${t.recurring.subscription ? ' (a subscription)' : ''}` }, icon(t.recurring.subscription ? 'play' : 'repeat', 'xs')) : null,
        t.receipts && t.receipts.length ? h('span', { class: 'rcp', title: t.receipts.length === 1 ? 'A receipt is kept with it' : `${t.receipts.length} receipts are kept with it` }, icon('attach', 'xs')) : null,
        (t.tags || []).map((x) => h('span', { class: 'tag tg' }, x)),
        h('small', { class: 'cs' }, txCat(t))),
      showBank ? h('span', { class: 'b', title: t.description || null }, t.description || '') : null,
      h('span', { class: 'n', title: t.notes || null }, t.notes || ''),
      h('span', { class: 'c' }, txCat(t)),
      showAccount ? h('span', { class: 'a' }, t.account) : null,
      h('span', { class: 'm' }, amt(t.amount, t.currency)),
      h('span', { class: 'rc' }, opt.review ? reviewTick(t, opt) : recTick(t))))));
}
/** On the Needs a look page: the tick that says a transaction was looked at; it leaves the list. */
function reviewTick(t, opt) {
  const b = h('button', { class: 'tick', title: 'Looked at: take it off this list', 'aria-label': 'Reviewed', disabled: t.writable ? null : true }, icon('check', 's'));
  b.onclick = async (e) => {
    e.stopPropagation();
    try {
      const r = await api('api/transactions/review', { method: 'POST', json: { ids: [t.id] } });
      if (opt.picked) opt.picked.delete(t.id);
      b.closest('li').remove();
      if (S.sum) S.sum.review = r.left;
      drawNav();
      if (opt.onReviewed) opt.onReviewed(r.left);
    } catch (x) { fail(x); }
  };
  return b;
}
/** The reconciled tick of a transaction: a click marks it (or unmarks it) without opening it. */
function recTick(t) {
  const b = h('button', { class: `tick ${t.reconciled ? 'on' : ''}`, title: t.reconciled ? 'Reconciled (click to undo)' : 'Not reconciled (click to mark)',
    'aria-label': 'Reconciled', 'aria-pressed': t.reconciled ? 'true' : 'false', disabled: t.writable ? null : true }, icon('check', 's'));
  b.onclick = async (e) => {
    e.stopPropagation();
    try {
      await api('api/transactions/reconcile', { method: 'POST', json: { ids: [t.id], reconciled: !t.reconciled } });
      t.reconciled = !t.reconciled; b.classList.toggle('on', t.reconciled); b.setAttribute('aria-pressed', String(t.reconciled));
      b.title = t.reconciled ? 'Reconciled (click to undo)' : 'Not reconciled (click to mark)';
    } catch (x) { fail(x); }
  };
  return b;
}
export async function showTransactions(page, r) {
  const q = r.q || {};
  const limit = 100, offset = +(q.offset || 0);
  const params = new URLSearchParams({ limit, offset });
  for (const k of ['q', 'account', 'category', 'month', 'flow']) if (q[k]) params.set(k, q[k]);
  if (q.rec) params.set('reconciled', q.rec);
  if (q.rcp) params.set('receipt', q.rcp);
  if (q.amt) params.set('amount', q.amt);
  if (q.hid) params.set('hidden', 'true');
  if (q.tag) params.set('tag', q.tag);
  if (q.rev) params.set('review', q.rev);
  const [d, cats, tags] = await Promise.all([api(`api/transactions?${params}`), categories(), tagList()]);
  const go = (changes) => { const n = { ...q, ...changes }; delete n.offset; for (const k of Object.keys(n)) if (!n[k]) delete n[k]; location.hash = `#/transactions?${new URLSearchParams(n)}`; };
  const search = h('input', { class: 't', type: 'search', placeholder: 'Payee, category, notes, $amount…', value: q.q || '' });
  let tm; search.oninput = () => { clearTimeout(tm); tm = setTimeout(() => go({ q: search.value.trim() }), 350); };
  const amount = h('input', { class: 't amtq', type: 'search', inputmode: 'decimal', placeholder: 'Amount: 280 or 100-200', 'aria-label': 'Amount (exact, or a range like 100-200, >500, <20)',
    title: 'Money out or in alike: 280 exactly, 100-200, >500 or <20', value: q.amt || '' });
  let tma; amount.oninput = () => { clearTimeout(tma); tma = setTimeout(() => go({ amt: amount.value.trim() }), 500); };
  const sel = (k, opts, label) => h('select', { class: 't', 'aria-label': label, onchange: (e) => go({ [k]: e.target.value }) }, opts.map(([v, l]) => h('option', { value: v, selected: String(q[k] || '') === String(v) ? true : null }, l)));
  const months = [['', 'Any time']]; for (let i = 0; i < 24; i++) { const m = shiftMonth(thisMonth(), -i); months.push([m, fmtMonth(m)]); }
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Transactions'), h('span', { class: 'grow' }),
    h('a', { class: 'pillbtn', href: '#/categories', title: 'Add, rename, regroup or delete categories' }, icon('list'), h('span', null, 'Categories')),
    h('a', { class: 'pillbtn', href: '#/rules', title: 'Rules that rename and categorize transactions' }, icon('tune'), h('span', null, 'Rules')),
    S.accounts.some((a) => a.writable && followsTx(a)) ? h('button', { class: 'pillbtn', onclick: () => txDialog() }, icon('add'), h('span', null, 'Transaction')) : null));
  put(page, savedRow(q));
  put(page, h('div', { class: 'filters' }, search, amount,
    sel('account', [['', 'Every account'], ...S.accounts.filter(followsTx).map((a) => [a.id, a.name])], 'Account'),
    sel('category', [['', 'Every category'], ['-', 'Uncategorized'], ...cats.map((c) => [c.category, c.category])], 'Category'),
    sel('month', months, 'Month'), sel('flow', [['', 'In and out'], ['out', 'Money out'], ['in', 'Money in']], 'Direction'),
    sel('rec', [['', 'Reconciled or not'], ['no', 'Not reconciled'], ['yes', 'Reconciled']], 'Reconciled'),
    sel('rcp', [['', 'With or without a receipt'], ['yes', 'With a receipt'], ['no', 'Without a receipt']], 'Receipts'),
    sel('hid', [['', 'Without the hidden'], ['1', 'With the hidden (dimmed)']], 'Hidden transactions'),
    tags.length || q.tag ? sel('tag', [['', 'Any tag'], ...[...new Set([...tags.map((x) => x.tag), q.tag].filter(Boolean))].map((x) => [x, `Tag: ${x}`])], 'Tag') : null,
    sel('rev', [['', 'Looked at or not'], ['yes', 'Needs a look']], 'Needs a look'),
    h('label', { class: 'check', title: 'Show the bank’s own text for each transaction' },
      h('input', { type: 'checkbox', checked: store.get('txbank') === '1' ? true : null, onchange: (e) => { store.set('txbank', e.target.checked ? '1' : '0'); onRoute(); } }), 'At the bank column')));
  const markable = d.items.filter((t) => t.writable && !t.reconciled);
  const markAll = async () => {
    if (!await confirmDialog('Mark them reconciled', `Mark the ${markable.length} transaction${markable.length === 1 ? '' : 's'} shown here as reconciled?`, 'Mark')) return;
    try { const r = await api('api/transactions/reconcile', { method: 'POST', json: { ids: markable.map((t) => t.id), reconciled: true } }); toast(`${r.changed} marked reconciled`); onRoute(); } catch (e) { fail(e); }
  };
  put(page, h('p', { class: 'sumline' }, `${d.total} transaction${d.total === 1 ? '' : 's'} · `, amt(d.sum),
    q.rec === 'no' && markable.length ? [' · ', h('button', { class: 'lnk', onclick: markAll }, `Mark these ${markable.length} reconciled`)] : null));
  const picked = new Set();
  const bar = h('div', { class: 'bulkbar', hidden: true });
  put(page, txList(d.items, true, undefined, { picked, onPick: () => drawBulk(bar, picked, d.items, !!q.rev) }), bar);
  if (d.total > offset + limit || offset) {
    put(page, h('div', { class: 'more' }, offset ? h('a', { class: 'pillbtn', href: `#/transactions?${new URLSearchParams({ ...q, offset: Math.max(0, offset - limit) })}` }, 'Newer') : null,
      d.total > offset + limit ? h('a', { class: 'pillbtn', href: `#/transactions?${new URLSearchParams({ ...q, offset: offset + limit })}` }, 'Older') : null));
  }
}
/** One transaction: its category, payee, notes and hidden (and in a manual account its date and amount); or a new
    one in a manual account. */
export async function txDialog(t, account) {
  const isNew = !t;
  const cats = await categories();
  const manualAccts = S.accounts.filter((a) => a.writable && followsTx(a));  // any account that follows its transactions
  t = t || { day: today(), source: 'manual', writable: true, accountId: (account || manualAccts[0] || {}).id };
  const ro = !t.writable;
  const manual = t.source === 'manual';
  const dl = h('datalist', { id: 'catlist' }, cats.map((c) => h('option', { value: c.category })));
  const f = { merchant: inp(t.merchant, { disabled: ro ? true : null }), category: inp(t.category, { list: 'catlist', disabled: ro ? true : null }),
    notes: h('textarea', { class: 't', rows: 2, disabled: ro ? true : null }, t.notes || ''), hidden: h('input', { type: 'checkbox', checked: t.hidden ? true : null, disabled: ro ? true : null }),
    reconciled: h('input', { type: 'checkbox', checked: t.reconciled ? true : null, disabled: ro ? true : null }),
    day: inp(t.day, { type: 'date', disabled: ro || !manual ? true : null }), amount: inp(t.amount, { inputmode: 'decimal', placeholder: '-12.50 out, 100 in', disabled: ro || !manual ? true : null }),
    account: h('select', { class: 't', disabled: !isNew ? true : null }, (isNew ? manualAccts : S.accounts).map((a) => h('option', { value: a.id, selected: a.id === t.accountId ? true : null }, a.name))),
    tags: inp((t.ownTags || []).join(', '), { placeholder: 'trip, reimbursable, tax', disabled: ro ? true : null }) };
  // its tags: the household's own, typed here; the ones Monarch Money sends are shown beside them
  const theirs = (t.tags || []).filter((x) => !(t.ownTags || []).some((o) => o.toLowerCase() === x.toLowerCase()));
  const known = ro ? [] : (await tagList()).filter((x) => x.own && !(t.tags || []).some((y) => y.toLowerCase() === x.tag.toLowerCase())).sort((a, b) => b.count - a.count).slice(0, 8);
  const tagsNow = () => [...new Set(f.tags.value.split(',').map((x) => x.trim().replace(/^#/, '')).filter(Boolean))];
  const tagHints = h('div', { class: 'taghints' }, theirs.length ? h('span', { class: 'muted small' }, 'From Monarch Money: ', theirs.map((x) => h('span', { class: 'tag tg' }, x))) : null,
    known.map((x) => h('button', { class: 'tag tg add', title: 'Add this tag', onclick: () => { if (!tagsNow().some((y) => y.toLowerCase() === x.tag.toLowerCase())) f.tags.value = [...tagsNow(), x.tag].join(', '); } }, icon('add', 'xs'), x.tag)));
  // split over categories: its parts, or the way to split it
  const parts = t.splits || [];
  const sbox = isNew ? null : parts.length
    ? h('div', { class: 'splitbox' }, h('div', { class: 'splithead' }, icon('split', 's'), h('b', null, 'Split over categories'), h('span', { class: 'grow' }),
      !ro ? h('button', { class: 'pillbtn tiny', onclick: () => { closeDialogs(); splitDialog(t); } }, 'Change') : null),
      h('ul', null, parts.map((p) => h('li', null, h('span', null, p.category || 'Uncategorized', p.notes ? h('small', { class: 'muted' }, ` ${p.notes}`) : null), h('span', { class: 'num' }, money(p.amount, t.currency))))),
      Math.abs(parts.reduce((x, p) => x + p.amount, 0) - t.amount) > 0.004 ? h('p', { class: 'muted small warn' }, `The parts no longer add up to ${money(t.amount, t.currency)}: the rest counts under ${t.category || 'no category'}.`) : null)
    : (!ro && t.amount ? h('button', { class: 'lnkbtn', onclick: () => { closeDialogs(); splitDialog(t); } }, icon('split', 'xs'), 'Split over categories') : null);
  const xbox = isNew ? null : h('div', { class: 'xferbox' });
  let moved = false;
  if (xbox) drawTransfer(xbox, t, () => { moved = true; });
  const rbox = isNew ? null : h('div', { class: 'rcbox' });
  if (rbox) drawReceipts(rbox, t, () => { moved = true; });
  const lbox = isNew ? null : linkedTx(t);
  const body = h('div', null, dl, h('div', { class: 'grid' }, fld('Payee', f.merchant, true), fld('Amount', f.amount), fld('Date', f.day), fld('Category', f.category), fld('Account', f.account), fld('Notes', f.notes, true), fld('Tags', f.tags, true)), tagHints,
    h('div', { class: 'chiprow', style: { marginTop: '10px', gap: '18px' } }, h('label', { class: 'check' }, f.hidden, 'Hidden: left out of the sums'),
      !isNew ? h('label', { class: 'check' }, f.reconciled, 'Reconciled with the statement') : null), sbox, xbox, rbox, lbox, isNew ? null : historyBox(t),
    t.description && t.description !== t.merchant ? h('p', { class: 'muted small' }, 'At the bank: ', t.description) : null,
    t.source === 'monarch' ? h('p', { class: 'muted small' }, 'From Monarch Money. A change here stays here: Monarch itself is not changed.') : null,
    isNew ? h('p', { class: 'muted small' }, 'Added here, by hand. In an account from Monarch Money it stays beside Monarch’s own transactions, and the balance stays Monarch’s.') : null);
  const btns = ro ? [{ label: 'Close', value: false }] : [
    !isNew && manual ? { label: 'Delete', value: 'delete', danger: true } : null,
    !isNew && may('household') ? { label: 'Make a rule', value: 'rule' } : null,
    !isNew ? { label: t.recurring ? 'Recurring…' : 'Make recurring', value: 'recur' } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  const ok = await dialog(isNew ? 'Add a transaction' : (t.merchant || 'Transaction'), body, btns, 'wide');
  if (ok === 'delete') { try { await api(`api/transactions/${t.id}`, { method: 'DELETE' }); toast('Deleted'); onRoute(); } catch (e) { fail(e); } return; }
  if (ok === 'recur') {  // the recurring one it is, or one to add from it (how often and the amount from those like it)
    try {
      const d = await api(`api/transactions/${t.id}/recurring`);
      S.freqs = d.frequencies;
      if (d.item) recurringDialog(d.item);
      else if (!d.writable) toast('Only editors add the household’s recurring transactions');
      else recurringDialog(null, d.suggestion);
    } catch (e) { fail(e); }
    return;
  }
  if (ok === 'rule') {  // the same payee next time: what was typed here, for every transaction like this one
    const name = t.merchant || t.description || '';
    ruleDialog(null, { pattern: name, field: t.merchant ? 'merchant' : 'description',
      setMerchant: f.merchant.value.trim() !== name ? f.merchant.value.trim() : null, setCategory: f.category.value.trim() || t.category });
    return;
  }
  if (!ok) { if (moved) onRoute(); return; }
  const b = { merchant: f.merchant.value, category: f.category.value, notes: f.notes.value, hidden: f.hidden.checked };
  if (!isNew && f.reconciled.checked !== !!t.reconciled) b.reconciled = f.reconciled.checked;
  if (manual) Object.assign(b, { day: f.day.value, amount: f.amount.value });
  const low = (xs) => xs.map((x) => x.toLowerCase()).sort().join('|');
  if (isNew ? tagsNow().length : low(tagsNow()) !== low(t.ownTags || [])) { b.tags = tagsNow(); S.tags = null; }
  try {
    await api(isNew ? `api/accounts/${f.account.value}/transactions` : `api/transactions/${t.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    S.cats = []; toast(isNew ? 'Added' : 'Saved'); if (route().view === 'review') await refreshSummary(); onRoute();
  } catch (e) { fail(e); }
}

/** A picture from a phone's camera is far larger than a receipt needs: one over a megabyte is made smaller (its
    long side 2000 points, a JPEG) before it is sent; anything else, and a picture the browser cannot draw, goes as it is. */
async function shrunk(f) {
  if (!/^image\/(jpeg|png|webp)$/.test(f.type) || f.size < 1200000) return { body: f, name: f.name };
  try {
    const bmp = await createImageBitmap(f, { imageOrientation: 'from-image' });
    const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
    const c = h('canvas', { width: Math.round(bmp.width * k), height: Math.round(bmp.height * k) });
    const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise((done) => c.toBlob(done, 'image/jpeg', 0.82));
    if (blob && blob.size < f.size) return { body: blob, name: f.name.replace(/\.[^.]*$/, '') + '.jpg' };
  } catch { /* sent as it is */ }
  return { body: f, name: f.name };
}
const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
/** In a transaction's dialog: its receipts (pictures and PDFs), each opened with a click; whoever may change the
    transaction adds one (picked, taken with the phone, or dropped here) and removes one. */
function drawReceipts(box, t, changed) {
  const list = t.receipts || [];
  const can = !!t.writable;
  const send = async (files) => {
    let n = 0;
    box.classList.add('busy');
    for (const f of files) {
      try {
        const { body, name } = await shrunk(f);
        const r = await api(`api/transactions/${t.id}/receipts?name=${encodeURIComponent(name)}`, { method: 'POST', body, headers: { 'Content-Type': 'application/octet-stream' } });
        t.receipts = [...(t.receipts || []), r]; n += 1;
      } catch (e) { fail(e); }
    }
    box.classList.remove('busy');
    if (n) { changed(); toast(n === 1 ? 'Receipt kept' : `${n} receipts kept`); }
    drawReceipts(box, t, changed);
  };
  const pick = h('input', { type: 'file', accept: 'image/*,application/pdf', multiple: true, hidden: true, onchange: (e) => { if (e.target.files.length) send([...e.target.files]); } });
  const remove = async (r) => {
    if (!await confirmDialog('Remove the receipt', `Remove ${r.name}? It cannot be brought back.`, 'Remove', true)) return;
    try { await api(`api/receipts/${r.id}`, { method: 'DELETE' }); t.receipts = t.receipts.filter((x) => x.id !== r.id); changed(); drawReceipts(box, t, changed); } catch (e) { fail(e); }
  };
  if (!list.length && !can) { box.replaceChildren(); return; }
  box.replaceChildren(h('div', { class: 'splithead' }, icon('attach', 's'), h('b', null, list.length > 1 ? 'Receipts' : 'Receipt'), h('span', { class: 'grow' }),
    can ? h('button', { class: 'pillbtn tiny', title: 'A picture or a PDF, up to 20 MB', onclick: () => pick.click() }, icon('add', 'xs'), 'Add') : null, pick),
    list.length ? h('ul', { class: 'rcps' }, list.map((r) => h('li', null,
      h('a', { class: 'rcpfile', href: r.url, target: '_blank', rel: 'noopener', title: `Open ${r.name}` },
        /^image\/(jpeg|png|gif|webp)$/.test(r.mime) ? h('img', { src: r.url, alt: '', loading: 'lazy' }) : h('span', { class: 'rcpic' }, icon(r.mime === 'application/pdf' ? 'receipt' : 'attach')),
        h('span', { class: 'rcpname' }, h('b', null, r.name), h('small', { class: 'muted' }, fmtSize(r.size)))),
      can ? h('button', { class: 'iconbtn', title: 'Remove this receipt', 'aria-label': `Remove ${r.name}`, onclick: () => remove(r) }, icon('delete', 's')) : null)))
      : h('p', { class: 'muted small' }, 'None kept yet: add a picture of the receipt or the PDF of the invoice, or drop it here.'));
  if (can && !box.ondragover) {
    box.ondragover = (e) => { if ([...(e.dataTransfer?.types || [])].includes('Files')) { e.preventDefault(); box.classList.add('drop'); } };
    box.ondragleave = () => box.classList.remove('drop');
    box.ondrop = (e) => { e.preventDefault(); box.classList.remove('drop'); if (e.dataTransfer.files.length) send([...e.dataTransfer.files]); };
  }
}
/** In a transaction's dialog: what it is linked to in the suite (the thing it paid for in ioThings, with its
    warranty; a note, a contact…), and the picker that links another, opening on the things. */
function linkedTx(t) {
  const el = h('div', { class: 'linked' });
  (async () => {
    let ui;
    try { ui = await linkUi(); } catch { return; }
    ui.mount(el, { kind: 'transaction', id: t.id, toast, first: 'item', canEdit: !!t.writable, onOpen: closeDialogs,
      empty: 'Nothing linked yet. Link the thing this paid for, so its price and warranty sit together; or a note, a contact…' });
  })();
  return el;
}

/** Split a transaction over categories: its parts, each with its share, a category and a note; what is left to
    give out is shown as the amounts are typed, and it saves once nothing is. */
async function splitDialog(t) {
  const cats = await categories();
  const total = Math.abs(t.amount);
  const cents = (v) => Math.round((parseFloat(String(v).replace(/[,$\s]/g, '')) || 0) * 100);
  const list = h('div', { class: 'splitrows' });
  const left = h('p', { class: 'splitleft' });
  const rows = [];
  const update = () => {
    const rest = Math.round(total * 100) - rows.reduce((x, r) => x + Math.abs(cents(r.amount.value)), 0);
    left.textContent = rest === 0 ? 'Everything is given out.' : rest > 0 ? `${money(rest / 100, t.currency)} left to give out` : `${money(-rest / 100, t.currency)} too much`;
    left.classList.toggle('warn', rest !== 0);
    return rest;
  };
  const addRow = (p = {}) => {
    const r = { amount: inp(p.amount != null ? Math.abs(p.amount).toFixed(2) : '', { inputmode: 'decimal', placeholder: '0.00', 'aria-label': 'Amount' }),
      category: inp(p.category, { list: 'splitcats', placeholder: 'Category', 'aria-label': 'Category' }), notes: inp(p.notes, { placeholder: 'Note', maxlength: 255, 'aria-label': 'Note' }) };
    r.el = h('div', { class: 'splitrow' }, r.amount, r.category, r.notes,
      h('button', { class: 'iconbtn', title: 'Remove this part', 'aria-label': 'Remove this part', onclick: () => { rows.splice(rows.indexOf(r), 1); r.el.remove(); update(); } }, icon('delete', 's')));
    r.amount.addEventListener('input', update);
    // the last part takes what is left when its amount is entered empty
    r.amount.addEventListener('focus', () => { if (!r.amount.value) { const rest = update(); if (rest > 0) { r.amount.value = (rest / 100).toFixed(2); r.amount.select(); update(); } } });
    rows.push(r); list.append(r.el);
  };
  if (t.splits && t.splits.length) t.splits.forEach(addRow);
  else { addRow({ amount: total, category: t.category }); addRow(); }
  update();
  const body = h('div', null, h('datalist', { id: 'splitcats' }, cats.map((c) => h('option', { value: c.category }))),
    h('p', { class: 'muted small' }, `${t.merchant || t.description || 'This transaction'}, ${fmtDay(t.day, true)}: ${money(t.amount, t.currency)}. The spending by category counts the parts in its place.`),
    list, h('div', { class: 'splitfoot' }, h('button', { class: 'pillbtn tiny', onclick: () => { addRow(); update(); } }, icon('add', 'xs'), 'Part'), left));
  const had = t.splits && t.splits.length;
  const ok = await dialog('Split over categories', body, [had ? { label: 'Make it whole', value: 'whole', danger: true } : null, { label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }].filter(Boolean), 'wide');
  if (!ok) return;
  const items = ok === 'whole' ? [] : rows.filter((r) => cents(r.amount.value)).map((r) => ({ amount: Math.abs(cents(r.amount.value)) / 100, category: r.category.value.trim() || null, notes: r.notes.value.trim() || null }));
  try {
    const n = await api(`api/transactions/${t.id}/splits`, { method: 'PUT', json: { items } });
    S.cats = []; toast(n.splits.length ? 'Split' : 'Whole again'); onRoute();
  } catch (e) { fail(e); Object.assign(t, { splits: ok === 'whole' ? t.splits : items.map((p) => ({ ...p, amount: (t.amount < 0 ? -1 : 1) * p.amount })) }); splitDialog(t); }
}

/** In a transaction's dialog: the other half of its transfer (with Unlink), or the transactions that could be it
    (the same amount the other way in another account, within two weeks), each with Link. */
async function drawTransfer(box, t, changed) {
  let d;
  try { d = await api(`api/transactions/${t.id}/transfer`); } catch { return; }
  const w = t.writable;
  const act = async (fn) => { try { await fn(); changed(); drawTransfer(box, t, changed); } catch (e) { fail(e); } };
  if (d.other) {
    const o = d.other;
    fill(box, h('h3', { class: 'sub' }, icon('link', 's'), 'Transfer'),
      h('div', { class: 'xferline' }, h('span', { class: 'grow' }, `${t.amount < 0 ? 'To' : 'From'} `, h('b', null, o.account || 'an account you do not see'), ` on ${fmtDay(o.day, true)}`,
        h('small', { class: 'muted' }, o.how === 'hand' ? ' · linked by hand' : o.how === 'rule' ? ' · linked by a transfer rule' : ' · found by ioMoney')),
        w ? h('button', { class: 'pillbtn', onclick: () => act(() => api(`api/transactions/${t.id}/transfer`, { method: 'DELETE' })) }, 'Unlink') : null),
      h('p', { class: 'muted small' }, 'A transfer between your own accounts is left out of the spending and the cash flow.'));
    return;
  }
  if (!d.candidates.length || !w) { fill(box); return; }
  fill(box, h('h3', { class: 'sub' }, icon('link', 's'), 'Is it a transfer?'),
    h('p', { class: 'muted small' }, 'These are the same amount the other way, in another account. Link the one that is the other half:'),
    h('ul', { class: 'rows flat' }, d.candidates.map((c) => h('li', null, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(c.day)),
      h('span', { class: 'main' }, h('b', null, c.account), h('small', null, [c.merchant || c.description, c.category].filter(Boolean).join(' · '))),
      h('span', { class: 'end' }, amt(c.amount, c.currency)),
      h('button', { class: 'pillbtn', onclick: () => act(() => api(`api/transactions/${t.id}/transfer`, { method: 'PUT', json: { with: c.id } })) }, 'Link'))))));
}

// ------------------------------------------------------------------ tags, a saved search, a transaction's history
/** Every tag the transactions have (Monarch's and the household's own), kept until one changes. */
export async function tagList() {
  if (!S.tags) { try { S.tags = (await api('api/tags')).items || []; } catch { S.tags = []; } }
  return S.tags;
}

/** Above the filters: this person's saved searches (the one shown now marked, with the way to forget it), and "Save
    this search" when filters are set that no saved search has. */
function savedRow(q) {
  const now = new URLSearchParams(Object.entries(q).filter(([k, v]) => k !== 'offset' && v));
  const has = [...now].length > 0;
  if (!S.searches.length && !has) return null;
  const mine = S.searches.find((x) => sameSearch(x.query, now));
  const save = async () => {
    const name = inp('', { maxlength: 64, placeholder: 'Reimbursable, Card over $500…', list: 'savednames' });
    const ok = await dialog('Save this search', h('div', null, h('datalist', { id: 'savednames' }, S.searches.map((x) => h('option', { value: x.name }))),
      h('div', { class: 'grid' }, fld('Name', name, true)),
      h('p', { class: 'muted small' }, 'Kept for you alone, in the sidebar under Transactions: the filters, not what they found. A name you already use takes this search instead.')),
    [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }]);
    if (!ok) return;
    try { await api('api/searches', { method: 'POST', json: { name: name.value, query: String(now) } }); await refreshSummary(); toast('Saved'); onRoute(); } catch (e) { fail(e); }
  };
  const forget = async (x) => {
    if (!await confirmDialog('Forget the search', `Forget “${x.name}”? The transactions stay.`, 'Forget', true)) return;
    try { await api(`api/searches/${x.id}`, { method: 'DELETE' }); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
  };
  return h('div', { class: 'saved' }, S.searches.map((x) => h('span', { class: `schip ${x === mine ? 'on' : ''}` },
    h('a', { href: `#/transactions?${x.query}` }, icon('bookmark', 'xs'), x.name),
    x === mine ? h('button', { title: 'Forget this search', 'aria-label': 'Forget this search', onclick: () => forget(x) }, icon('close', 'xs')) : null)),
  has && !mine ? h('button', { class: 'schip new', onclick: save }, icon('add', 'xs'), 'Save this search') : null,
  has ? h('a', { class: 'lnk small', href: '#/transactions' }, 'Clear the filters') : null);
}

/** A change kept for a transaction, as words: "category: Shopping, was Groceries". */
const histVal = (f, v) => (v == null || v === '' || (Array.isArray(v) && !v.length) ? 'nothing' : f === 'hidden' ? (v ? 'yes' : 'no')
  : Array.isArray(v) ? v.join(', ') : f === 'date' ? fmtDay(v, true) : String(v));
export const histFields = (c) => c.fields.map((x) => h('span', { class: 'hf' }, h('i', null, x.field), ' ', h('b', null, histVal(x.field, x.after)), h('small', null, ` was ${histVal(x.field, x.before)}`)));
export const HIST_WHAT = { hand: 'Changed', bulk: 'Changed with others', undo: 'Taken back', reset: 'Back to Monarch’s own' };
/** "History" in a transaction's dialog: what was changed on it by hand, by whom and when, each with its way back; and
    for one from Monarch Money that was changed here, the way back to Monarch's own. Fetched when opened. */
function historyBox(t) {
  const list = h('div', { class: 'hist' });
  const box = h('details', { class: 'histbox' }, h('summary', null, icon('history', 'xs'), 'History'), list);
  const after = async (fn, done) => { try { await fn(); S.cats = []; S.tags = null; toast(done); closeDialogs(); await refreshSummary(); onRoute(); } catch (e) { fail(e); } };
  const reset = t.writable && t.source === 'monarch' && t.edited ? h('button', { class: 'lnkbtn', onclick: async () => {
    if (!await confirmDialog('Back to Monarch’s own', 'Undo everything changed here on this transaction (its payee, category, notes, tags and split)? The rules apply to it again, and the next sync refreshes it from Monarch Money.', 'Put it back')) return;
    after(() => api(`api/transactions/${t.id}/reset`, { method: 'POST' }), 'Back to Monarch’s own');
  } }, icon('undo', 'xs'), 'Back to Monarch’s own') : null;
  let got = false;
  box.addEventListener('toggle', async () => {
    if (!box.open || got) return;
    got = true;
    try {
      const items = (await api(`api/transactions/${t.id}/changes`)).items || [];
      fill(list, items.length ? h('ul', null, items.map((c) => h('li', { class: c.undone ? 'undone' : null },
        h('div', { class: 'hw' }, h('span', null, [HIST_WHAT[c.what] || c.what, c.by, agoSec(c.secondsAgo)].filter(Boolean).join(' · ')), c.undone ? h('span', { class: 'tag' }, 'Taken back') : null,
          t.writable && !c.undone && c.what !== 'undo' ? h('button', { class: 'lnk small', onclick: () => after(() => api('api/changes/undo', { method: 'POST', json: { id: c.id } }), 'Taken back') }, 'Undo') : null),
        h('div', { class: 'hfs' }, histFields(c)))))
        : h('p', { class: 'muted small' }, t.edited ? 'Changed here before changes were kept.' : 'Not changed by hand.'), reset);
    } catch (e) { fill(list, h('p', { class: 'muted small' }, e.message || String(e))); }
  });
  return box;
}

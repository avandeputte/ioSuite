/* Tidy up: review, payees, tags, duplicates, what changed, upkeep. */
import { confirmDialog, dialog, fail, fill, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { amt, api, fld, fmtDay, followsTx, inp, money, S, store, today } from './core.js';
import { onRoute } from './main.js';
import { importDialog } from './reconcile.js';
import { refreshSummary } from './shell.js';
import { categories, HIST_WHAT, histFields, tagList, txDialog, txList } from './transactions.js';

// ------------------------------------------------------------------ putting the data in order
export const plural = (n, one, many) => `${n.toLocaleString()} ${n === 1 ? one : (many || `${one}s`)}`;
export const agoSec = (s) => (s == null ? '' : s < 90 ? 'just now' : s < 5400 ? `${Math.round(s / 60)} minutes ago` : s < 129600 ? `${Math.round(s / 3600)} hours ago` : `${Math.round(s / 86400)} days ago`);
export const tidyBack = () => h('a', { class: 'iconbtn', href: '#/tidy', title: 'Tidy up', 'aria-label': 'Tidy up' }, icon('prev'));

/** The bar that comes up once transactions are ticked: the same change to all of them (category, payee, tags, hidden,
    reconciled, looked at), with Undo right after. review: on the Needs a look page. */
export function drawBulk(bar, picked, items, review) {
  const n = picked.size;
  bar.hidden = !n;
  if (!n) { bar.replaceChildren(); return; }
  const rows = items.filter((t) => picked.has(t.id));
  const run = async (set, done) => {
    try {
      const r = await api('api/transactions/bulk', { method: 'POST', json: { ids: [...picked], set } });
      S.cats = []; S.tags = null;
      await refreshSummary();
      const kept = Object.keys(set).some((k) => !['reconciled', 'reviewed'].includes(k));  // those two are no change to the transaction itself
      toast(`${plural(r.changed, 'transaction')} ${done}`, kept && r.changed ? ['Undo', async () => {
        try { const b = await api('api/changes/undo', { method: 'POST', json: { batch: r.batch } }); S.cats = []; S.tags = null; toast(`${plural(b.undone, 'transaction')} put back`); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
      }] : null);
      onRoute();
    } catch (e) { fail(e); }
  };
  const ask = async (title, label, field, ok = 'Change') => (await dialog(title, h('div', null, h('div', { class: 'grid' }, fld(label, field, true)),
    h('p', { class: 'muted small' }, `For the ${plural(n, 'transaction')} ticked. Undo takes it back.`)), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: true }])) === true;
  const category = async () => {
    const cats = await categories();
    const f = inp('', { list: 'bulkcats', placeholder: 'Groceries' });
    const dl = h('datalist', { id: 'bulkcats' }, cats.map((c) => h('option', { value: c.category })));
    if (!await ask('Set the category', 'Category', h('span', null, dl, f)) || !f.value.trim()) return;
    run({ category: f.value.trim() }, 'categorized');
  };
  const payee = async () => {
    const f = inp('', { maxlength: 255, placeholder: 'The payee’s name' });
    if (!await ask('Set the payee', 'Payee', f) || !f.value.trim()) return;
    run({ merchant: f.value.trim() }, 'renamed');
  };
  const tag = async () => {
    const known = (await tagList()).filter((x) => x.own);
    const own = [...new Map(rows.flatMap((t) => t.ownTags || []).map((x) => [x.toLowerCase(), x])).values()].sort((a, b) => a.localeCompare(b));
    const add = inp('', { list: 'bulktags', placeholder: 'trip, reimbursable' });
    const off = h('select', { class: 't' }, h('option', { value: '' }, 'None'), own.map((x) => h('option', { value: x }, x)));
    const ok = await dialog('Tag them', h('div', null, h('datalist', { id: 'bulktags' }, known.map((x) => h('option', { value: x.tag }))),
      h('div', { class: 'grid' }, fld('Add the tags', add, true), own.length ? fld('Take off the tag', off, true) : null),
      h('p', { class: 'muted small' }, `For the ${plural(n, 'transaction')} ticked. Undo takes it back.`)), [{ label: 'Cancel', value: false }, { label: 'Change', value: true, primary: true }]);
    const tags = add.value.split(',').map((x) => x.trim().replace(/^#/, '')).filter(Boolean);
    if (!ok || (!tags.length && !off.value)) return;
    run({ ...(tags.length ? { addTags: tags } : {}), ...(off.value ? { removeTags: [off.value] } : {}) }, 'tagged');
  };
  const allHidden = rows.length && rows.every((t) => t.hidden);
  const allRec = rows.length && rows.every((t) => t.reconciled);
  const btn = (ic, label, fn, title) => h('button', { class: 'pillbtn tiny', onclick: fn, title: title || null }, icon(ic, 'xs'), label);
  fill(bar, h('b', null, `${n} ticked`),
    btn('list', 'Category', category), btn('store', 'Payee', payee), btn('label', 'Tags', tag),
    btn('eye', allHidden ? 'Show' : 'Hide', () => run({ hidden: !allHidden }, allHidden ? 'shown' : 'hidden'), 'A hidden transaction is left out of the sums'),
    btn('check', allRec ? 'Not reconciled' : 'Reconciled', () => run({ reconciled: !allRec }, allRec ? 'no longer reconciled' : 'marked reconciled')),
    review ? btn('doneAll', 'Looked at', () => run({ reviewed: true }, 'looked at'), 'Take them off this list as they are') : null,
    h('span', { class: 'grow' }),
    h('button', { class: 'iconbtn', title: 'Untick them', 'aria-label': 'Untick them', onclick: () => { picked.clear(); onRoute(); } }, icon('close', 's')));
}

/** Choose one of the accounts (for the statement to reconcile, the file to import). */
async function pickAccount(title, accts, text) {
  if (!accts.length) { toast(text); return null; }
  if (accts.length === 1) return accts[0];
  const sel = h('select', { class: 't' }, accts.map((a) => h('option', { value: a.id }, a.name)));
  const ok = await dialog(title, h('div', { class: 'grid' }, fld('Account', sel, true)), [{ label: 'Cancel', value: false }, { label: 'Next', value: true, primary: true }]);
  return ok ? accts.find((a) => a.id === +sel.value) : null;
}

/** Tidy up: everything that keeps the transactions right, each with how much there is to do. */
export async function showTidy(page) {
  const d = await api('api/tidy');
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Tidy up')));
  put(page, h('p', { class: 'muted' }, 'What keeps the transactions right: the ones to look at, the ones kept twice, the accounts that do not add up, and the lists behind them.'));
  const tile = (to, ic, hueVar, title, text, n, warn) => {
    const kids = [h('span', { class: 'sic' }, icon(ic)), h('span', { class: 'tt' }, h('b', null, title, n ? h('span', { class: `n ${warn ? 'warn' : ''}` }, n.toLocaleString()) : null), h('small', null, text))];
    return typeof to === 'string' ? h('a', { class: 'tidytile', href: to, style: { '--hue': `var(${hueVar})` } }, kids)
      : h('button', { class: 'tidytile', onclick: to, style: { '--hue': `var(${hueVar})` } }, kids);
  };
  const txAccts = S.accounts.filter((a) => followsTx(a) && a.writable && !a.closed);
  const reconcile = async () => { const a = await pickAccount('Reconcile with a statement', txAccts, 'No account of yours follows its transactions'); if (a) location.hash = `#/account/${a.id}/reconcile`; };
  const imp = async () => { const a = await pickAccount('Import a bank file', txAccts.filter((x) => x.source === 'manual'), 'A bank file goes into an account kept by hand: add one first'); if (a) importDialog(a); };
  put(page, h('h2', { class: 'recurhead' }, icon('warning'), h('span', null, 'To check')), h('div', { class: 'tidygrid' },
    tile('#/review', 'doneAll', '--c-blue', 'Needs a look', 'New transactions, and the ones without a category', d.review, true),
    tile('#/duplicates', 'copy', '--c-rose', 'Likely duplicates', 'The same transaction kept twice', d.duplicates, true),
    tile('#/transfers', 'link', '--c-teal', 'Transfers to check', 'The same amount out of one account and into another, not linked', d.transfers, true),
    tile('#/balance', 'scale', '--c-amber', 'Balance check', 'Does each account’s balance agree with its transactions?', d.balanceGaps, true)));
  put(page, h('h2', { class: 'recurhead' }, icon('list'), h('span', null, 'The lists')), h('div', { class: 'tidygrid' },
    tile('#/payees', 'store', '--c-indigo', 'Payees', 'Rename or merge them, give each its usual category', d.payees),
    tile('#/categories', 'label', '--c-purple', 'Categories and tags', 'Add, rename, merge or delete them', d.tags),
    tile('#/rules', 'tune', '--c-teal', 'Rules', 'What each rule does, the ones that do nothing, the ones missing'),
    tile('#/changes', 'history', '--c-slate', 'Recent changes', 'What was changed by hand, each with its way back')));
  put(page, h('h2', { class: 'recurhead' }, icon('bank'), h('span', null, 'Against the bank')), h('div', { class: 'tidygrid' },
    tile(reconcile, 'check', '--c-green', 'Reconcile with a statement', 'Tick an account’s transactions off against the bank’s statement, by hand or from its PDF or CSV file'),
    tile(imp, 'upload', '--c-orange', 'Import a bank file', 'CSV, OFX or QFX into an account kept by hand')));
}

/** Needs a look: what came in since someone last looked, and what has no category. A tick takes one off as it is;
    saving a change does too; several ticked are changed together. */
export async function showReview(page) {
  const d = await api('api/transactions?review=yes&limit=300');
  const can = d.items.some((t) => t.writable);
  const sum = h('p', { class: 'sumline' });
  const say = (n) => { sum.textContent = n ? `${plural(n, 'transaction')} to look at${n > d.items.length ? `, the latest ${d.items.length} shown` : ''}` : ''; };
  const markAll = async () => {
    if (!await confirmDialog('Mark all looked at', `Take all ${plural(d.total, 'transaction')} off this list as they are?`, 'Mark them')) return;
    try { const r = await api('api/transactions/review', { method: 'POST', json: { all: true } }); toast(`${plural(r.changed, 'transaction')} looked at`); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
  };
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Needs a look'), h('span', { class: 'grow' }),
    can ? h('button', { class: 'pillbtn', onclick: markAll }, icon('doneAll'), h('span', null, 'All looked at')) : null));
  put(page, h('p', { class: 'muted' }, 'The transactions that came in since this list was first opened and nobody looked at yet, and the ones without a category. ',
    'Open one to correct it (saving takes it off the list), tick it at the right as it is, or tick several at the left and change them together.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('doneAll'), h('p', null, 'Nothing needs a look.'))); return; }
  say(d.total);
  const picked = new Set();
  const bar = h('div', { class: 'bulkbar', hidden: true });
  put(page, sum, txList(d.items, true, undefined, { picked, onPick: () => drawBulk(bar, picked, d.items, true), review: true,
    onReviewed: (left) => { say(left); drawBulk(bar, picked, d.items, true); if (!left) onRoute(); } }), bar);
}

/** The payees: how many transactions and how much each, its usual category; editors rename one (into another: the two
    are one) and give it its category, kept as rules. */
export async function showPayees(page) {
  const [d, cats] = await Promise.all([api('api/payees?limit=2000'), categories()]);
  const w = d.writable;
  const f = { q: '', sort: store.get('paySort') || 'count' };
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Payees')));
  put(page, h('p', { class: 'muted' }, 'Everyone the transactions were paid to or came from. ',
    w ? 'Rename a payee, or give it the name of another to make the two one; give it its usual category. Both are kept as rules, so what comes in later follows.' : 'Editors rename and merge them and set their usual category.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('store'), h('p', null, 'No payees yet.'))); return; }
  const count = h('span', { class: 'muted small' });
  const list = h('ul', { class: 'rows flat payees' });
  const SHOWN = 400;
  const sorts = { count: (a, b) => b.count - a.count || a.payee.localeCompare(b.payee), name: (a, b) => a.payee.localeCompare(b.payee),
    total: (a, b) => Math.abs(b.total) - Math.abs(a.total), mixed: (a, b) => b.categories - a.categories || b.count - a.count, last: (a, b) => b.last.localeCompare(a.last) };
  const draw = () => {
    const q = f.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const shown = d.items.filter((p) => q.every((x) => p.payee.toLowerCase().includes(x) || (p.category || '').toLowerCase().includes(x))).sort(sorts[f.sort]);
    count.textContent = `${shown.length.toLocaleString()} of ${d.total.toLocaleString()}${shown.length > SHOWN ? `, the first ${SHOWN} shown` : ''}`;
    fill(list, shown.slice(0, SHOWN).map((p) => h('li', null, h('div', { class: 'r', role: w ? 'button' : null, tabindex: w ? 0 : null, onclick: w ? () => payeeDialog(p, d.items, cats) : null },
      h('span', { class: 'main' }, h('b', null, p.payee), h('small', null, h('span', { class: 'pcn' }, `${p.count} · `), `last ${fmtDay(p.last, p.last.slice(0, 4) !== today().slice(0, 4))}`)),
      h('span', { class: 'pc' }, p.rule ? h('span', { title: 'A rule gives it this category' }, icon('tune', 'xs'), p.rule.category) : (p.category || h('span', { class: 'muted' }, 'Uncategorized')),
        p.categories > 1 ? h('span', { class: 'tag warn', title: 'Its transactions are in several categories' }, `${p.categories} categories`) : null),
      h('a', { class: 'lnk small pn', href: `#/transactions?${new URLSearchParams({ q: p.payee })}`, onclick: (e) => e.stopPropagation() }, plural(p.count, 'transaction')),
      h('span', { class: 'pt' }, amt(p.total))))));
  };
  const search = inp('', { type: 'search', placeholder: 'Payee or category…' });
  let tm; search.oninput = () => { clearTimeout(tm); tm = setTimeout(() => { f.q = search.value; draw(); }, 150); };
  const sort = h('select', { class: 't', 'aria-label': 'Order', onchange: (e) => { f.sort = e.target.value; store.set('paySort', f.sort); draw(); } },
    [['count', 'Most used first'], ['name', 'By name'], ['total', 'Largest total first'], ['last', 'Latest first'], ['mixed', 'Several categories first']].map(([v, l]) => h('option', { value: v, selected: v === f.sort ? true : null }, l)));
  put(page, h('div', { class: 'filters' }, search, sort, count), list);
  draw();
}
async function payeeDialog(p, all, cats) {
  const f = { name: inp(p.payee, { maxlength: 255, list: 'payeenames' }), category: inp(p.rule ? p.rule.category : '', { list: 'payeecats', placeholder: p.category ? `Mostly ${p.category} now` : 'Groceries' }),
    all: h('input', { type: 'checkbox' }) };
  const body = h('div', null, h('datalist', { id: 'payeenames' }, all.filter((x) => x !== p).slice(0, 1500).map((x) => h('option', { value: x.payee }))),
    h('datalist', { id: 'payeecats' }, cats.map((c) => h('option', { value: c.category }))),
    h('div', { class: 'grid' }, fld('Name', f.name, true), fld('Its usual category', f.category, true)),
    h('label', { class: 'check', style: { marginTop: '10px' } }, f.all, 'Give the category to the ones categorized by hand too'),
    h('p', { class: 'muted small' }, `${plural(p.count, 'transaction')}, ${money(p.total)} in all. Give it the name of another payee to make the two one. The name and the category are kept as rules (on the Rules page).`));
  if (!await dialog(p.payee, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }], 'wide')) return;
  const name = f.name.value.trim(), cat = f.category.value.trim();
  try {
    let said = 'Nothing changed';
    if (name && name !== p.payee) {
      const other = all.find((x) => x !== p && x.payee.toLowerCase() === name.toLowerCase());
      if (other && !await confirmDialog('Make the two one', `Rename ${p.payee} to ${other.payee}? Its ${plural(p.count, 'transaction')} join the ${other.count} there, now and from here on.`, 'Merge')) return;
      const r = await api('api/payees/rename', { method: 'POST', json: { name: p.payee, newName: other ? other.payee : name } });
      said = `${plural(r.changed, 'transaction')} renamed`;
    }
    if (cat && (f.all.checked || !p.rule || p.rule.category !== cat)) {
      const r = await api('api/payees/category', { method: 'POST', json: { name: name || p.payee, category: cat, all: f.all.checked } });
      said = `${said === 'Nothing changed' ? '' : `${said}; `}${plural(r.changed, 'transaction')} categorized`;
    }
    S.cats = []; toast(said); onRoute();
  } catch (e) { fail(e); }
}

/** The tags, under the categories: each with how many transactions and how much; editors rename (or merge) and delete
    the household's own. */
export async function drawTags(page) {
  let d; try { d = await api('api/tags'); } catch { return; }
  S.tags = d.items;
  put(page, h('div', { class: 'pagehead', style: { marginTop: '28px' } }, h('h2', { class: 'h1ish' }, icon('label'), 'Tags')));
  put(page, h('p', { class: 'muted' }, 'A tag says what a transaction is part of, whatever its category: a trip, what is to be paid back, what counts for the taxes. ',
    'Type them on a transaction, or tick several transactions and tag them together. The tags Monarch Money sends are shown too; those are changed in Monarch.'));
  if (!d.items.length) { put(page, h('p', { class: 'muted small' }, 'No tags yet.')); return; }
  put(page, h('ul', { class: 'rows flat tagrows' }, d.items.map((x) => {
    const edit = d.writable && x.own;
    return h('li', null, h('div', { class: 'r', role: edit ? 'button' : null, tabindex: edit ? 0 : null, onclick: edit ? () => tagDialog(x, d.items) : null },
      h('span', { class: 'main' }, h('b', null, h('span', { class: 'tag tg' }, x.tag), !x.own ? h('span', { class: 'tag', title: 'Sent by Monarch Money: changed there' }, 'Monarch') : null)),
      h('a', { class: 'lnk small', href: `#/transactions?${new URLSearchParams({ tag: x.tag })}`, onclick: (e) => e.stopPropagation() }, plural(x.count, 'transaction')),
      h('span', { class: 'pt' }, amt(x.total))));
  })));
}
async function tagDialog(x, all) {
  const name = inp(x.tag, { maxlength: 64, list: 'tagnames' });
  const body = h('div', null, h('datalist', { id: 'tagnames' }, all.filter((y) => y.own && y !== x).map((y) => h('option', { value: y.tag }))),
    h('div', { class: 'grid' }, fld('Name', name, true)), h('p', { class: 'muted small' }, `On ${plural(x.count, 'transaction')}. Give it the name of another tag to make the two one.`));
  const ok = await dialog(`Tag ${x.tag}`, body, [{ label: 'Delete', value: 'delete', danger: true }, { label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }]);
  try {
    if (ok === 'delete') {
      if (!await confirmDialog('Delete the tag', `Take “${x.tag}” off its ${plural(x.count, 'transaction')}? The transactions stay.`, 'Delete', true)) return;
      await api('api/tags/delete', { method: 'POST', json: { name: x.tag } });
    } else if (ok && name.value.trim() && name.value.trim() !== x.tag) await api('api/tags', { method: 'PUT', json: { name: x.tag, newName: name.value } });
    else return;
    S.tags = null; toast(ok === 'delete' ? 'Deleted' : 'Saved'); onRoute();
  } catch (e) { fail(e); }
}

/** Likely duplicates: the same account and amount, at most three days apart, and alike. Keep one and hide (or, added
    here, delete) the other, or say they are two. */
export async function showDuplicates(page) {
  const d = await api('api/duplicates');
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Likely duplicates')));
  put(page, h('p', { class: 'muted' }, 'Transactions in one account, of the same amount, at most three days apart, that look like one kept twice. ',
    'Keep one and hide the other (a hidden transaction is left out of every sum; one added here can be deleted), or say they are different: those are not shown again.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('copy'), h('p', null, 'No likely duplicates.'))); return; }
  const count = h('p', { class: 'sumline' });
  const list = h('div', { class: 'dups' });
  const say = () => {
    const n = list.children.length;
    count.textContent = n ? `${plural(n, 'likely duplicate')} to check` : '';
    if (S.sum && !n) refreshSummary();
    if (!n) fill(list, h('div', { class: 'empty' }, icon('check'), h('p', null, 'All checked.')));
  };
  const group = (g) => {
    const el = h('div', { class: 'dupg' });
    const left = () => { if (el.querySelectorAll('.dupr').length < 2) { el.remove(); say(); } };
    const row = (t) => {
      const r = h('div', { class: 'dupr' });
      const act = (label, fn, cls) => h('button', { class: `pillbtn tiny ${cls || ''}`, onclick: async (e) => { e.stopPropagation(); try { if (await fn() === false) return; r.remove(); left(); } catch (x) { fail(x); } } }, label);
      put(r, h('span', { class: 'd' }, fmtDay(t.day, true)),
        h('button', { class: 'p', title: 'Open the transaction', onclick: () => txDialog(t) }, h('b', null, t.merchant || t.description || '(no payee)'),
          t.description && t.description !== t.merchant ? h('small', null, t.description) : null),
        h('span', { class: 'k' }, h('span', { class: 'tag' }, t.source === 'manual' ? 'Added here' : 'Monarch'),
          t.reconciled ? h('span', { class: 'tag', title: 'Checked against a statement' }, 'Reconciled') : null, t.edited ? h('span', { class: 'tag' }, 'Changed here') : null,
          t.transfer ? h('span', { class: 'tag' }, 'Transfer') : null, t.category ? h('span', { class: 'muted small' }, t.category) : null),
        h('span', { class: 'm' }, amt(t.amount, t.currency)),
        h('span', { class: 'acts' }, !t.writable ? null : [act('Hide', () => api(`api/transactions/${t.id}`, { method: 'PATCH', json: { hidden: true } })),
          t.source === 'manual' ? act('Delete', async () => { if (!await confirmDialog('Delete it', 'Delete this transaction? This cannot be undone.', 'Delete', true)) return false; await api(`api/transactions/${t.id}`, { method: 'DELETE' }); }, 'danger') : null]));
      return r;
    };
    put(el, h('div', { class: 'duph' }, h('b', null, g.items[0].account), h('span', { class: 'muted small' }, g.whyText), h('span', { class: 'grow' }),
      g.items.every((t) => t.writable) ? h('button', { class: 'pillbtn tiny', onclick: async () => {
        try { await api('api/duplicates/not', { method: 'POST', json: { ids: g.items.map((t) => t.id) } }); el.remove(); say(); } catch (x) { fail(x); }
      } }, 'They are different') : null), g.items.map(row));
    return el;
  };
  put(list, d.items.map(group));
  put(page, count, list);
  say();
}

/** Recent changes: what was changed by hand, the latest first, a change to many at once as one line; each with Undo. */
export async function showChanges(page) {
  const d = await api('api/changes?limit=100');
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Recent changes')));
  put(page, h('p', { class: 'muted' }, 'What was changed by hand on the transactions, the latest first; a change to many at once is one line. Undo puts the fields back as they were. ',
    'Kept for 400 days. What the rules and the syncs change is not listed.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('history'), h('p', null, 'No changes yet.'))); return; }
  const undo = async (g) => {
    try { const r = await api('api/changes/undo', { method: 'POST', json: g.batch ? { batch: g.batch } : { id: g.id } }); S.cats = []; S.tags = null; toast(`${plural(r.undone, 'transaction')} put back`); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
  };
  put(page, h('ul', { class: 'rows flat changes' }, d.items.map((g) => {
    const c = g.changes[0], t = c.transaction;
    const title = g.count === 1 ? h('a', { class: 'lnk', href: `#/transaction/${t.id}` }, `${t.payee || '(no payee)'} · ${fmtDay(t.day, true)} · ${money(t.amount, t.currency)}`)
      : `${g.count} transactions at once: ${g.changes.map((x) => x.transaction.payee || '(no payee)').filter((x, i, xs) => xs.indexOf(x) === i).join(', ')}${g.count > g.changes.length ? '…' : ''}`;
    return h('li', { class: g.undone ? 'off' : null }, h('div', { class: 'r' },
      h('span', { class: 'main' }, h('b', null, title), h('small', null, [HIST_WHAT[g.what] || g.what, g.by, agoSec(g.secondsAgo), g.count === 1 ? t.account : null].filter(Boolean).join(' · ')),
        h('span', { class: 'hfs' }, histFields(c))),
      g.undone ? h('span', { class: 'tag' }, 'Taken back') : null,
      g.canUndo ? h('button', { class: 'pillbtn tiny', onclick: () => undo(g) }, icon('undo', 'xs'), 'Undo') : null));
  })));
}

/** On the Rules page: beside each rule what it did to the transactions of the past two years (and whether it does
    nothing), and above the list the rules that seem to be missing. */
export function drawUpkeep(page, sug, u) {
  for (const r of u.rules) {
    const el = page.querySelector(`li[data-rule="${r.id}"] .upk`);
    if (!el) continue;
    if (r.note === 'never' || r.note === 'behind') fill(el, ' ', h('span', { class: 'tag warn', title: r.noteText }, icon('warning', 'xs'), r.note === 'never' ? 'Matches nothing' : 'Never decides'));
    else if (r.note !== 'off') fill(el, ` · ${plural(r.matched, 'transaction')}${r.last ? `, the last on ${fmtDay(r.last, true)}` : ''}`);
  }
  if (!u.suggestions.length) return;
  fill(sug, h('div', { class: 'box sugbox' }, h('h2', null, icon('tune'), 'Rules you seem to be missing'),
    h('p', { class: 'muted small' }, 'Payees you gave the same category by hand several times, with no rule that does it.'),
    h('ul', { class: 'rows' }, u.suggestions.map((x) => {
      const li = h('li');
      const add = async () => { try { const r = await api('api/payees/category', { method: 'POST', json: { name: x.payee, category: x.category } }); S.cats = []; toast(`Rule added; ${plural(r.changed, 'transaction')} changed`); onRoute(); } catch (e) { fail(e); } };
      const not = async () => { try { await api('api/rules/suggestions/not', { method: 'POST', json: { key: x.key } }); li.remove(); if (!sug.querySelector('li')) sug.replaceChildren(); } catch (e) { fail(e); } };
      put(li, h('div', { class: 'r' }, h('span', { class: 'main' }, h('b', null, `${x.payee}: ${x.category}`),
        h('small', null, `Set by hand ${x.count} times${x.wouldChange ? `; ${plural(x.wouldChange, 'more transaction')} would follow` : ''}`)),
      u.writable ? h('span', { class: 'end acts', style: { flexDirection: 'row', gap: '6px' } }, h('button', { class: 'pillbtn primary tiny', onclick: add }, icon('add', 'xs'), 'Add the rule'), h('button', { class: 'pillbtn tiny', onclick: not }, 'No thanks')) : null));
      return li;
    }))));
}

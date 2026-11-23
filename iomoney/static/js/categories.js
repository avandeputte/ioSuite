/* The categories, and spending by category and month by month. */
import { confirmDialog, dialog, fail, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, fld, fmtMonth, inp, money, S, shiftMonth, thisMonth, tone } from './core.js';
import { bar, flowChart } from './charts.js';
import { onRoute } from './main.js';
import { drawTags } from './tidy.js';

// ------------------------------------------------------------------ categories
/** Every category by group: add one, rename it (into another: merged), move it to another group, delete it (its
    transactions moved to another or left without one). What Monarch sends later follows. */
export async function showCategories(page) {
  const d = await api('api/categories');
  const w = d.writable;
  S.cats = d.items;
  put(page, h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: '#/transactions', title: 'Transactions', 'aria-label': 'Transactions' }, icon('prev')),
    h('h1', null, 'Categories'), h('span', { class: 'grow' }),
    w ? h('button', { class: 'pillbtn', onclick: () => categoryDialog(null, d.items) }, icon('add'), h('span', null, 'Category')) : null));
  put(page, h('p', { class: 'muted' }, 'The categories of the transactions, by group. A category renamed, merged into another or deleted here stays so: what Monarch Money sends later under the old name comes in under the new one.'));
  const groups = new Map();
  for (const c of d.items) { const g = c.group || 'No group'; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(c); }
  for (const [g, list] of groups) {
    put(page, h('div', { class: 'catgrp' }, h('h3', null, g), h('ul', { class: 'rows' }, list.map((c) => h('li', null,
      h('div', { class: 'r', role: w ? 'button' : null, tabindex: w ? 0 : null, onclick: w ? () => categoryDialog(c, d.items) : null },
        h('span', { class: 'main' }, h('b', null, c.category)),
        h('a', { class: 'lnk small', href: `#/transactions?${new URLSearchParams({ category: c.category })}`, onclick: (e) => e.stopPropagation() }, `${c.count} transaction${c.count === 1 ? '' : 's'}`)))))));
  }
  await drawTags(page);
}
async function categoryDialog(c, all) {
  const isNew = !c;
  const groups = [...new Set(all.map((x) => x.group).filter(Boolean))].sort();
  const f = { name: inp(c ? c.category : '', { maxlength: 128, list: isNew ? null : 'catnames' }), group: inp(c ? c.group : '', { list: 'catgroups', placeholder: 'Food & Dining, Bills & Utilities…' }) };
  const body = h('div', null, h('datalist', { id: 'catgroups' }, groups.map((g) => h('option', { value: g }))),
    h('datalist', { id: 'catnames' }, all.filter((x) => !c || x.category !== c.category).map((x) => h('option', { value: x.category }))),
    h('div', { class: 'grid' }, fld('Name', f.name), fld('Group', f.group)),
    !isNew ? h('p', { class: 'muted small' }, `${c.count} transaction${c.count === 1 ? '' : 's'}. Give it the name of another category to merge the two.`) : null);
  const btns = [!isNew ? { label: 'Delete', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  const ok = await dialog(isNew ? 'Add a category' : c.category, body, btns);
  if (ok === 'delete') {
    const to = h('select', { class: 't' }, h('option', { value: '' }, 'No category'), all.filter((x) => x.category !== c.category).map((x) => h('option', { value: x.category }, x.category)));
    const go = await dialog(`Delete ${c.category}`, h('div', null, h('p', null, `Its ${c.count} transaction${c.count === 1 ? '' : 's'} (and the rules and recurring transactions that set it) move to:`), fld('Category', to)),
      [{ label: 'Cancel', value: false }, { label: 'Delete', value: true, danger: true }]);
    if (!go) return;
    try { const r = await api('api/categories/delete', { method: 'POST', json: { name: c.category, moveTo: to.value || null } }); S.cats = []; toast(`Deleted; ${r.moved} moved`); onRoute(); } catch (e) { fail(e); }
    return;
  }
  if (!ok) return;
  try {
    if (isNew) await api('api/categories', { method: 'POST', json: { name: f.name.value, group: f.group.value } });
    else {
      const merge = all.some((x) => x.category === f.name.value.trim() && x.category !== c.category);
      if (merge && !await confirmDialog('Merge the categories', `Merge ${c.category} into ${f.name.value.trim()}? Its ${c.count} transactions move there.`, 'Merge')) return;
      await api('api/categories', { method: 'PUT', json: { name: c.category, newName: f.name.value, group: f.group.value } });
    }
    S.cats = []; toast(isNew ? 'Added' : 'Saved'); onRoute();
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ spending: by category, and month by month
export async function showSpending(page, r) {
  const m = r.month;
  const [s, cf] = await Promise.all([api(`api/spending?month=${m}`), api('api/cashflow?months=12')]);
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Spending'), h('span', { class: 'grow' }),
    h('a', { class: 'iconbtn', href: `#/spending/${shiftMonth(m, -1)}`, title: 'The month before' }, icon('prev')),
    h('b', { style: { minWidth: '140px', textAlign: 'center' } }, fmtMonth(m)),
    m < thisMonth() ? h('a', { class: 'iconbtn', href: `#/spending/${shiftMonth(m, 1)}`, title: 'The month after' }, icon('next')) : h('span', { class: 'iconbtn' })));
  put(page, h('div', { class: 'cards' },
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Money out'), h('div', { class: 'val num neg' }, money(s.spent, s.currency))),
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Money in'), h('div', { class: 'val num pos' }, money(s.income, s.currency))),
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Left over'), h('div', { class: `val num ${tone(s.net)}` }, money(s.net, s.currency)))));
  const outs = s.categories.filter((c) => c.spent > c.income).map((c) => ({ ...c, v: c.spent - c.income }));
  const max = Math.max(1, ...outs.map((c) => c.v));
  put(page, h('div', { class: 'box' }, h('h2', null, icon('pie'), 'Where it went'),
    outs.length ? h('div', { class: 'bars' }, outs.map((c) => bar(c.category || 'Uncategorized', c.v, max, { cur: s.currency, sub: c.group && c.group !== c.category ? c.group : null, hueVar: '--c-rose',
      href: `#/transactions?${new URLSearchParams({ month: m, category: c.category || '-' })}` }))) : h('p', { class: 'muted' }, 'Nothing spent this month (transfers between your own accounts are left out).')));
  put(page, h('div', { class: 'box' }, h('h2', null, icon('trend'), 'The past twelve months'),
    h('div', { class: 'legend' }, h('span', null, h('i', { style: { background: 'var(--ok)' } }), 'In'), h('span', null, h('i', { style: { background: 'var(--danger)' } }), 'Out')),
    flowChart(cf.items, { cur: cf.currency })));
}

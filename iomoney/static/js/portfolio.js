/* The portfolio with its quotes, and the house and the cars with their loans. */
import { confirmDialog, dialog, fail, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { ago, api, canAdd, CUR, fld, HOLDING_LABEL, inp, KIND_LOOK, money, pct, qty, S, store, tone } from './core.js';
import { accountDialog } from './account.js';
import { bar, lineChart } from './charts.js';
import { onRoute } from './main.js';
import { refreshSummary } from './shell.js';

// ------------------------------------------------------------------ the portfolio
export async function drawHoldings(page, accountId, account) {
  const p = await api(`api/portfolio${accountId ? `?account=${accountId}` : ''}`);
  if (!accountId) {
    put(page, h('div', { class: 'hero' },
      h('div', null, h('div', { class: 'lbl' }, 'Portfolio'), h('div', { class: 'big num' }, money(p.value, p.currency))),
      p.dayChange != null ? h('div', { class: `chg num ${tone(p.dayChange)}` }, `${money(p.dayChange, p.currency, { sign: true })} (${pct(p.dayChangePct)})`, h('small', { class: 'muted' }, ' today')) : null,
      p.gain != null ? h('div', { class: `chg num ${tone(p.gain)}` }, `${money(p.gain, p.currency, { sign: true })}`, h('small', { class: 'muted' }, ' over cost')) : null));
    const days = store.get('range') || '365';
    const hist = await api(`api/networth?days=${days}&kind=investment`);
    put(page, lineChart(hist.history));
    const max = Math.max(1, ...p.allocation.map((a) => a.value));
    if (p.allocation.length > 1) put(page, h('div', { class: 'box' }, h('h2', null, icon('pie'), 'Allocation'), h('div', { class: 'bars' }, p.allocation.map((a) => bar(HOLDING_LABEL[a.kind] || a.kind, a.value, max, { cur: p.currency, hueVar: '--c-indigo', sub: p.value ? `${(a.value / p.value * 100).toFixed(1)}%` : null })))));
  }
  const byAccount = !accountId && store.get('bysymbol') !== '1';
  const rows = accountId || byAccount ? p.items : p.bySymbol;
  const head = h('div', { class: 'pagehead' }, h('h2', { style: { margin: 0 } }, 'Holdings'), h('span', { class: 'grow' }),
    !accountId ? h('div', { class: 'segs' }, h('button', { class: byAccount ? 'on' : null, onclick: () => { store.set('bysymbol', '0'); onRoute(); } }, 'By account'), h('button', { class: !byAccount ? 'on' : null, onclick: () => { store.set('bysymbol', '1'); onRoute(); } }, 'By symbol')) : null,
    h('button', { class: 'pillbtn tiny', onclick: refreshQuotes }, icon('sync', 'xs'), 'Quotes'),
    (account ? account.writable && account.source === 'manual' : S.accounts.some((a) => a.kind === 'investment' && a.source === 'manual' && a.writable)) ? h('button', { class: 'pillbtn tiny', onclick: () => holdingDialog(null, accountId) }, icon('add', 'xs'), 'Holding') : null);
  put(page, head);
  if (!rows.length) { put(page, h('p', { class: 'muted' }, accountId ? 'Nothing held here.' : 'No holdings yet: they come with Monarch Money’s investment accounts, or add a manual investment account and what it holds.')); return; }
  const th = (l, r) => h('th', { class: r ? 'r' : null }, l);
  const table = h('table', { class: 't' }, h('thead', null, h('tr', null, th('Symbol'), th('Name'), !accountId && byAccount ? th('Account') : null, th('Shares', 1), th('Price', 1), th('Today', 1), th('Value', 1), accountId || byAccount ? th('Gain', 1) : null)),
    h('tbody', null, rows.map((x) => h('tr', { class: x.id && x.writable ? 'click' : null, onclick: x.id && x.writable ? () => holdingDialog(x) : null, title: x.quoteError ? `No quote: ${x.quoteError}` : null },
      h('td', { class: 'sym' }, x.symbol || '—', x.quoteError ? [' ', icon('warning', 'xs warn')] : null), h('td', { class: 'nm' }, x.name || ''),
      !accountId && byAccount ? h('td', null, x.account) : null,
      h('td', { class: 'r num' }, qty(x.shares)), h('td', { class: 'r num' }, x.price != null ? money(x.price, x.currency) : '—'),
      h('td', { class: `r num ${tone(x.dayChangePct)}` }, x.dayChangePct != null ? pct(x.dayChangePct) : ''),
      h('td', { class: 'r num' }, money(x.homeValue, CUR())),
      accountId || byAccount ? h('td', { class: `r num ${tone(x.gain)}` }, x.gain != null ? money(x.gain, CUR(), { sign: true }) : '') : null))));
  put(page, h('div', { class: 'tablewrap' }, table));
}
export async function showPortfolio(page) {
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Portfolio')));
  await drawHoldings(page, null);
}
async function refreshQuotes() {
  toast('Asking for the latest quotes…');
  try { const r = await api('api/quotes/refresh', { method: 'POST' }); toast(r.failed ? `${r.asked} quotes asked, ${r.failed} not found` : 'Quotes up to date'); onRoute(); } catch (e) { fail(e); }
}
export async function holdingDialog(x, accountId) {
  const isNew = !x;
  const accts = S.accounts.filter((a) => a.kind === 'investment' && a.source === 'manual' && a.writable);
  if (isNew && !accts.length) { toast('Add a manual investment account first (Add an account, kind Investments)'); return; }
  x = x || { kind: 'stock', accountId: accountId || accts[0].id };
  const f = { account: h('select', { class: 't', disabled: !isNew ? true : null }, accts.map((a) => h('option', { value: a.id, selected: a.id === x.accountId ? true : null }, a.name))),
    symbol: inp(x.symbol, { placeholder: 'AAPL, VWCE.DE, BTC-USD', style: { textTransform: 'uppercase' }, disabled: !isNew ? true : null }),
    shares: inp(x.shares, { inputmode: 'decimal' }), costBasis: inp(x.costBasis, { inputmode: 'decimal', placeholder: 'What you paid for all of them' }),
    kind: h('select', { class: 't', disabled: !isNew ? true : null }, (S.sum.holdingKinds || []).map((k) => h('option', { value: k, selected: k === x.kind ? true : null }, HOLDING_LABEL[k] || k))),
    name: inp(x.name, { placeholder: 'For something without a symbol' }), price: inp(x.quoted ? '' : x.price, { inputmode: 'decimal', placeholder: 'Without a symbol: its price' }) };
  const body = h('div', null, h('div', { class: 'grid' }, fld('Account', f.account, true), fld('Symbol', f.symbol), fld('Kind', f.kind), fld('Shares', f.shares), fld('Cost basis', f.costBasis), fld('Name', f.name), fld('Price', f.price)),
    h('p', { class: 'muted small' }, 'A symbol as Yahoo Finance writes it: AAPL on Nasdaq, VWCE.DE on Xetra, VOD.L in London, BTC-USD for bitcoin. Quotes follow on their own.'));
  const ok = await dialog(isNew ? 'Add a holding' : (x.symbol || x.name), body, [!isNew ? { label: 'Delete', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean), 'wide');
  if (ok === 'delete') { if (await confirmDialog('Delete the holding', `Delete ${x.symbol || x.name}?`, 'Delete', true)) { try { await api(`api/holdings/${x.id}`, { method: 'DELETE' }); toast('Deleted'); onRoute(); } catch (e) { fail(e); } } return; }
  if (!ok) return;
  const b = { shares: f.shares.value, costBasis: f.costBasis.value, name: f.name.value };
  if (f.price.value.trim()) b.price = f.price.value;
  if (isNew) Object.assign(b, { symbol: f.symbol.value, kind: f.kind.value });
  try {
    await api(isNew ? `api/accounts/${f.account.value}/holdings` : `api/holdings/${x.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    toast(isNew ? 'Added' : 'Saved'); await refreshSummary(); onRoute();
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ house and cars
export async function showAssets(page) {
  const things = (await api('api/accounts?things=true')).items || [];
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Assets'), h('span', { class: 'grow' }),
    canAdd() ? h('button', { class: 'pillbtn', onclick: () => accountDialog(null) }, icon('add'), h('span', null, 'Add')) : null));
  if (!things.length) {
    put(page, h('div', { class: 'empty' }, icon('home'), h('p', null, 'No real estate or vehicles here yet.'),
      h('p', { class: 'muted' }, 'Add them in Monarch Money (real estate from Zillow, vehicles) and they come along with the next sync, or add them here by hand with their value.')));
    return;
  }
  const total = things.filter((a) => a.inNetWorth && !a.closed).reduce((s, a) => s + (a.equity != null ? a.equity : (a.estimate != null ? a.estimate : a.balance) * (a.value / (a.balance || 1) || 1)), 0);
  put(page, h('div', { class: 'hero' }, h('div', null, h('div', { class: 'lbl' }, 'Worth, after their loans'), h('div', { class: 'big num' }, money(total)))));
  put(page, h('div', { class: 'things' }, things.map((a) => {
    const d = a.details || {};
    const v = a.estimate != null ? a.estimate : a.balance;
    return h('a', { class: 'thing', href: `#/account/${a.id}`, style: { '--hue': `var(${KIND_LOOK[a.kind][1]})` } },
      h('div', { class: 'top' }, h('span', { class: 'sic' }, icon(KIND_LOOK[a.kind][0])), h('h3', null, a.name),
        a.source === 'monarch' ? h('span', { class: 'tag', title: 'Its value comes from Monarch Money' }, 'Monarch') : a.estimate != null ? h('span', { class: 'tag est' }, 'Est.') : null),
      h('div', { class: 'val num' }, money(v, a.currency)),
      h('div', { class: 'kvs' },
        d.address ? [h('span', null, 'Address'), h('span', null, d.address)] : null,
        d.make || d.model ? [h('span', null, 'Car'), h('span', null, [d.year, d.make, d.model].filter(Boolean).join(' '))] : null,
        a.loan ? [h('span', null, a.loan.name), h('span', { class: 'num neg' }, money(-Math.abs(a.loan.balance), a.loan.currency))] : null,
        a.equity != null ? [h('span', null, 'Equity'), h('span', { class: `num ${tone(a.equity)}` }, money(a.equity))] : null,
        d.boughtFor != null ? [h('span', null, 'Bought for'), h('span', { class: 'num' }, money(d.boughtFor, a.currency), d.boughtOn ? ` in ${d.boughtOn.slice(0, 4)}` : '')] : null,
        [h('span', null, 'Updated'), h('span', null, ago(a.balanceAt))]));
  })));
}

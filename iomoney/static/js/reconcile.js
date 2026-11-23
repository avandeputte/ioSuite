/* A bank's own file against an account: reconcile, import; and the balance check. */
import { confirmDialog, dialog, fail, fill, icon, put, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { amt, api, dateOf, fld, fmtDay, fmtMonth, followsTx, inp, may, money, S, today } from './core.js';
import { onRoute } from './main.js';
import { resyncAccount } from './overview.js';
import { refreshSummary } from './shell.js';
import { plural, tidyBack } from './tidy.js';
import { txDialog } from './transactions.js';

// ------------------------------------------------------------------ reconcile an account against the bank's file
/** #/account/3/reconcile: an account against the bank's statement. The statement's days and its two balances; the
    transactions of those days to tick off; done when the ticked ones add up to what the balance moved by. */
export async function showReconcile(page, a) {
  const d = await api(`api/accounts/${a.id}/statements`);
  const w = d.writable;
  const iso = (x) => x.toLocaleDateString('sv');
  let end = today();
  if (d.next.start) { const e = dateOf(d.next.start); e.setMonth(e.getMonth() + 1); e.setDate(e.getDate() - 1); if (iso(e) < end) end = iso(e); }
  const f = { start: inp(d.next.start || '', { type: 'date' }), end: inp(end, { type: 'date' }), opening: inp(d.next.opening == null ? '' : d.next.opening, { inputmode: 'decimal' }),
    closing: inp('', { inputmode: 'decimal', placeholder: 'as the statement says' }) };
  const num = (v) => { const x = parseFloat(String(v).replace(/[^0-9.-]/g, '')); return Number.isNaN(x) ? null : x; };
  const cents = (v) => Math.round(v * 100);
  put(page, h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/account/${a.id}`, title: a.name, 'aria-label': a.name }, icon('prev')), h('h1', null, `Reconcile ${a.name}`)));
  put(page, h('p', { class: 'muted' }, 'Take the bank’s statement: its first and last day, and the balance at its start and at its end. Tick each transaction the statement shows. ',
    'When the ticked ones add up to what the balance moved by, the account agrees with the bank up to that day.',
    d.isAsset ? null : ' What is owed counts as a positive balance here, so a purchase makes it go up.'));
  // the bank's own file held against the account: the statement's PDF, or a CSV, OFX or QFX file from its website
  let cmp = null, found = new Set(), extra = new Set();
  const cmpbox = h('div', { class: 'cmpbox' });
  const pick = h('input', { type: 'file', accept: '.pdf,.csv,.ofx,.qfx,.qbo,.txt,application/pdf,text/csv', hidden: true,
    onchange: (e) => { const x = e.target.files[0]; e.target.value = ''; if (x) read({ aid: a.id, file: x }); } });
  const pickBtn = h('button', { class: 'pillbtn', onclick: () => pick.click() }, icon('upload', 'xs'), 'Compare with the bank’s file');
  put(page, h('div', { class: 'box' }, h('div', { class: 'grid' }, fld('First day', f.start), fld('Last day', f.end), fld(d.isAsset ? 'Balance at the start' : 'Owed at the start', f.opening), fld(d.isAsset ? 'Balance at the end' : 'Owed at the end', f.closing)),
    h('div', { class: 'cmppick' }, pickBtn, pick, h('span', { class: 'muted small' }, 'The statement’s PDF, or a CSV, OFX or QFX file from the bank’s website: its days and balances are filled in, what it shows is ticked, and what differs is listed. The file is read and not kept.'))), cmpbox);
  const lines = h('div');
  const bar = h('div', { class: 'bulkbar recbar' });
  put(page, lines, bar);
  let items = [], sign = 1; const ticked = new Set();
  const summary = () => {
    const sum = items.filter((t) => ticked.has(t.id)).reduce((s, t) => s + cents(t.amount), 0);
    const o = num(f.opening.value), c = num(f.closing.value);
    const moved = o == null || c == null ? null : cents(c) - cents(o);
    const diff = moved == null ? null : moved - sign * sum;
    const finish = async () => {
      if (diff && !await confirmDialog('Finish with a difference', `The transactions ticked do not add up to the statement: ${money(Math.abs(diff) / 100, a.currency)} is left. Keep the statement as it is anyway?`, 'Finish anyway')) return;
      try {
        const r = await api(`api/accounts/${a.id}/statements`, { method: 'POST', json: { start: f.start.value, end: f.end.value, opening: o, closing: c, ids: [...ticked], anyway: !!diff } });
        S.recFile = null; toast(`${plural(r.reconciled, 'transaction')} reconciled`); onRoute();
      } catch (e) { fail(e); }
    };
    fill(bar, h('span', null, `${ticked.size} of ${items.length} ticked: `, h('b', { class: 'num' }, money(sum / 100, a.currency))),
      h('span', null, 'The statement moved by ', h('b', { class: 'num' }, moved == null ? '…' : money(sign * moved / 100, a.currency))),
      h('span', { class: diff === 0 ? 'ok' : 'off' }, 'Difference ', h('b', { class: 'num' }, diff == null ? '…' : money((sign * diff || 0) / 100, a.currency))),
      h('span', { class: 'grow' }),
      w ? h('button', { class: `pillbtn ${diff === 0 ? 'primary' : ''}`, disabled: diff == null || !items.length ? true : null, onclick: finish }, icon('check', 'xs'), diff ? 'Finish anyway' : 'Finish') : null);
  };
  const load = async () => {
    ticked.clear(); items = [];
    if (!f.start.value || !f.end.value) { fill(lines, h('p', { class: 'muted' }, 'Give the statement’s first and last day.')); summary(); return; }
    try {
      const got = await api(`api/accounts/${a.id}/statement?${new URLSearchParams({ start: f.start.value, end: f.end.value })}`);
      items = got.items; sign = got.sign;
      for (const t of items) if (cmp ? found.has(t.id) : t.reconciled && !t.earlier) ticked.add(t.id);  // with the bank's file: what it shows
      const boxes = [];
      const row = (t) => {
        const b = h('input', { type: 'checkbox', checked: ticked.has(t.id) ? true : null, disabled: w ? null : true, 'aria-label': 'On the statement' });
        const li = h('li', { class: ticked.has(t.id) ? 'picked' : null });
        b.onchange = () => { if (b.checked) ticked.add(t.id); else ticked.delete(t.id); li.classList.toggle('picked', b.checked); summary(); };
        boxes.push([t, b, li]);
        put(li, h('label', { class: 'r' }, b, h('span', { class: 'day' }, fmtDay(t.day)),
          h('span', { class: 'main' }, h('b', null, t.merchant || t.description || '(no payee)', t.earlier ? h('span', { class: 'tag', title: 'From before this statement, not ticked off on the one before' }, 'Earlier') : null,
            t.hidden ? h('span', { class: 'tag' }, 'Hidden') : null,
            cmp && extra.has(t.id) ? h('span', { class: 'tag warn', title: 'In the account in these days, but the bank’s file does not show it' }, cmp.kind === 'pdf' ? 'Not on the statement' : 'Not in the file') : null), h('small', null, [t.transfer ? `Transfer ${t.amount < 0 ? 'to' : 'from'} ${t.transfer.account}` : t.category, t.description && t.description !== t.merchant ? t.description : null].filter(Boolean).join(' · '))),
          h('span', { class: 'pt' }, amt(t.amount, t.currency))));
        return li;
      };
      const all = (on) => { for (const [t, b, li] of boxes) { b.checked = on; li.classList.toggle('picked', on); if (on) ticked.add(t.id); else ticked.delete(t.id); } summary(); };
      fill(lines, items.length ? [h('p', { class: 'sumline', style: { marginTop: '4px' } }, `${plural(items.length, 'transaction')} to tick off`,
        w ? [' · ', h('button', { class: 'lnk', onclick: () => all(true) }, 'Tick all'), ' · ', h('button', { class: 'lnk', onclick: () => all(false) }, 'Untick all')] : null),
      h('ul', { class: 'rows flat recon' }, items.map(row))] : h('p', { class: 'muted' }, 'No transactions in these days.'));
    } catch (e) { fill(lines, h('p', { class: 'muted' }, e.message || String(e))); }
    summary();
  };
  /** What the file and the account do not agree on, above the list: the lines the account does not have (to add, or
      with the transaction of another amount that looks like it), the ones it has under another day, and how many
      of its own the file does not show (marked in the list). */
  const drawCmp = () => {
    const r = cmp;
    if (!r) { fill(cmpbox); return; }
    const it = r.kind === 'pdf' ? 'statement' : 'file', onIt = r.kind === 'pdf' ? 'on the statement' : 'in the file';
    const can = w && followsTx(a);
    const again = () => read(S.recFile);
    const post = (x) => api(`api/accounts/${a.id}/transactions`, { method: 'POST', json: x });
    const addOne = async (x) => {
      const g = { merchant: inp(x.text), day: inp(x.day, { type: 'date' }), amount: inp(x.signed ? x.amount : -Math.abs(x.amount), { inputmode: 'decimal', placeholder: '-12.50 out, 100 in' }) };
      const ok = await dialog('Add the transaction', h('div', null, h('div', { class: 'grid' }, fld('Payee', g.merchant, true), fld('Amount', g.amount), fld('Date', g.day)),
        x.signed ? null : h('p', { class: 'muted small' }, 'The statement does not say which way the money went: it is put as money out. Take the minus away for money in.'),
        a.source === 'manual' ? null : h('p', { class: 'muted small' }, 'Added here, by hand, beside Monarch Money’s own. Should Monarch still bring it later, it shows under Likely duplicates.')),
      [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }]);
      if (!ok) return;
      try { await post({ merchant: g.merchant.value, day: g.day.value, amount: g.amount.value }); toast('Added'); await again(); } catch (e) { fail(e); }
    };
    const addAll = async (xs) => {
      if (!await confirmDialog('Add them all', `Add the ${plural(xs.length, 'transaction')} the account does not have, as the ${it} gives them?`, 'Add them')) return;
      let n = 0;
      cmpbox.classList.add('busy');
      try { for (const x of xs) { await post({ merchant: x.text, day: x.day, amount: x.amount }); n += 1; } } catch (e) { fail(e); }
      if (n) toast(`${plural(n, 'transaction')} added`);
      await again();
    };
    const open = async (id) => { try { txDialog(await api(`api/transactions/${id}`)); } catch (e) { fail(e); } };
    const line = (x, note, ...right) => h('li', null, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(x.day)),
      h('span', { class: 'main' }, h('b', null, x.text || '(no text)'), note ? h('small', null, note) : null),
      h('span', { class: 'pt' }, x.signed ? amt(x.amount, a.currency) : h('span', { class: 'num' }, money(x.amount, a.currency))), right));
    const lone = r.missing.filter((x) => !x.differs);
    const here = [...extra].filter((id) => items.some((t) => t.id === id)).length;
    const notes = [
      r.total ? null : 'No lines could be read from it, only its days and balances: tick the transactions by hand.',
      r.adds === true ? 'Its lines add up to its two balances, so all of it was read.' : null,
      r.adds === false ? 'Its lines as read do not add up to its two balances: a line may have been missed or read wrong, so look over the ticks.' : null,
      r.kind === 'pdf' && r.total && r.closing == null ? 'Its balances were not found: type them from the statement.' : null,
      r.worked ? `The ${it} gives no balance: the one at the end is the account’s balance on the day before its first day plus its lines. Check it against the bank’s.` : null,
      r.kind !== 'pdf' && r.closing == null ? 'The file gives no balance, and none is kept for the day before its first day: type the two balances to finish.' : null,
      r.flipped ? 'The file writes money out as a positive number: it was turned around.' : null,
      r.problems ? `${plural(r.problems, 'row')} of the file could not be read.` : null];
    const order = r.guessed && r.dateOrder !== 'ymd' ? h('p', { class: 'muted small' }, `Its dates read both ways: they were taken as ${r.dateOrder === 'mdy' ? 'month, then day' : 'day, then month'}. `,
      h('button', { class: 'lnk', onclick: () => read({ ...S.recFile, order: r.dateOrder === 'mdy' ? 'dmy' : 'mdy' }) }, r.dateOrder === 'mdy' ? 'Read them as day, then month' : 'Read them as month, then day')) : null;
    const agree = r.total && !r.missingCount && !r.elsewhere.length && !here;
    fill(cmpbox, h('div', { class: 'box' },
      h('div', { class: 'cmphead' }, icon(agree ? 'check' : 'receipt', 's'),
        h('b', null, `${r.name || `The ${it}`}: ${plural(r.total, 'line')}, ${r.matched.length} found here and ticked`), h('span', { class: 'grow' }),
        h('button', { class: 'iconbtn', title: `Put the ${it} away`, 'aria-label': `Put the ${it} away`, onclick: () => { cmp = null; S.recFile = null; drawCmp(); load(); } }, icon('close', 's'))),
      agree ? h('p', { class: 'cmpok' }, `Everything ${onIt} is in the account, and everything in the account in these days is ${onIt}.`) : null,
      notes.filter(Boolean).map((x) => h('p', { class: 'muted small' }, x)), order,
      r.missingCount ? [h('h3', null, `${r.kind === 'pdf' ? 'On the statement' : 'In the file'}, not here (${r.missingCount})`, can && lone.length > 1 && lone.every((x) => x.signed) ? h('button', { class: 'pillbtn tiny', onclick: () => addAll(lone) }, icon('add', 'xs'), `Add the ${lone.length}`) : null),
        h('ul', { class: 'rows flat cmprows' }, r.missing.map((x) => (x.differs
          ? line(x, [`Here for ${money(x.differs.amount, a.currency)}: ${x.differs.name || '(no payee)'}, ${fmtDay(x.differs.day)}`], h('button', { class: 'pillbtn tiny', onclick: () => open(x.differs.id) }, 'Open'))
          : line(x, null, can ? h('button', { class: 'pillbtn tiny', onclick: () => addOne(x) }, icon('add', 'xs'), 'Add') : null)))),
        r.missingCount > r.missing.length ? h('p', { class: 'muted small' }, `The first ${r.missing.length} are shown.`) : null] : null,
      r.elsewhere.length ? [h('h3', null, `Here, outside these days (${r.elsewhere.length})`),
        h('ul', { class: 'rows flat cmprows' }, r.elsewhere.map((x) => line(x, `Here on ${fmtDay(x.at)}, ${x.why} the ${it}’s ${x.why === 'before' ? 'first' : 'last'} day`,
          h('button', { class: 'pillbtn tiny', onclick: () => open(x.id) }, 'Open'))))] : null,
      here ? h('p', { class: 'cmpextra' }, h('span', { class: 'tag warn' }, r.kind === 'pdf' ? 'Not on the statement' : 'Not in the file'),
        ` ${plural(here, 'transaction')} of these days ${here === 1 ? 'is' : 'are'} in the account but not ${onIt}: marked below and left unticked.`) : null));
  };
  const read = async (src) => {
    S.recFile = src;
    pickBtn.disabled = true; cmpbox.classList.add('busy');
    try {
      const q = new URLSearchParams({ name: src.file.name });
      if (src.order) q.set('order', src.order);
      const r = await api(`api/accounts/${a.id}/statement/read?${q}`, { method: 'POST', body: src.file, headers: { 'Content-Type': 'application/octet-stream' } });
      cmp = r; found = new Set(r.matched); extra = new Set(r.extra);
      if (r.start) f.start.value = r.start;
      if (r.end) f.end.value = r.end;
      if (r.opening != null) f.opening.value = r.opening;
      if (r.closing != null) f.closing.value = r.closing;
      await load(); drawCmp();
    } catch (e) { S.recFile = null; fail(e); }
    pickBtn.disabled = false; cmpbox.classList.remove('busy');
  };
  f.start.onchange = load; f.end.onchange = load; f.opening.oninput = summary; f.closing.oninput = summary;
  await load();
  if (S.recFile && S.recFile.aid === a.id) await read(S.recFile);  // back from a transaction changed here: the file once more
  else S.recFile = null;
  if (d.items.length) {
    put(page, h('h2', { class: 'recurhead' }, icon('history'), h('span', null, 'Statements reconciled')), h('ul', { class: 'rows flat' }, d.items.map((s) => h('li', null, h('div', { class: 'r' },
      h('span', { class: 'main' }, h('b', null, `${fmtDay(s.start, true)} to ${fmtDay(s.end, true)}`),
        h('small', null, `${money(s.opening, a.currency)} to ${money(s.closing, a.currency)}`, s.difference ? ` · finished with ${money(Math.abs(s.difference), a.currency)} left` : '')),
      s.difference ? h('span', { class: 'tag warn' }, 'With a difference') : null,
      w ? h('button', { class: 'iconbtn', title: 'Forget this statement (its transactions stay reconciled)', onclick: async () => {
        if (!await confirmDialog('Forget the statement', 'Forget this statement? Its transactions stay reconciled.', 'Forget', true)) return;
        try { await api(`api/statements/${s.id}`, { method: 'DELETE' }); onRoute(); } catch (e) { fail(e); }
      } }, icon('delete', 's')) : null)))));
  }
}

// ------------------------------------------------------------------ the balance check
/** The balance check: for each cash account and card from Monarch Money, whether its balance moved by what its
    transactions add up to; where it did not, by how much, which way, and in which days the gap appeared. */
export async function showBalance(page) {
  const d = await api('api/balance-check');
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Balance check')));
  put(page, h('p', { class: 'muted' }, `Over the past ${d.days} days, each account’s balance at the bank should have moved by exactly what its transactions here add up to. `,
    'Where it did not, a transaction is missing here or kept twice. This looks at the cash accounts and cards Monarch Money keeps with a bank behind them. ',
    'Every transaction Monarch Money sends counts. One of the past week that the bank’s balance does not show yet is named and not flagged.'));
  const openTx = async (id) => { try { txDialog(await api(`api/transactions/${id}`)); } catch (e) { fail(e); } };
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('scale'), h('p', null, 'No accounts to check.'))); return; }
  const post = async (x, gap) => { try { await api(`api/balance-check/${x.id}/ok`, { method: 'POST', json: { gap } }); await refreshSummary(); onRoute(); } catch (e) { fail(e); } };
  const TAGS = { ok: ['Agrees', 'ok'], waiting: ['Agrees but for the latest ones', 'ok'], accepted: ['Accepted as it is', ''], unknown: ['Too little history yet', ''] };
  for (const x of d.items) {
    const acct = S.accounts.find((a) => a.id === x.id);
    const can = acct && acct.writable;
    const cur = x.currency;
    const head = h('div', { class: 'balh' }, h('a', { class: 'lnk', href: `#/account/${x.id}` }, h('b', null, x.name)), x.institution ? h('span', { class: 'muted small' }, x.institution) : null, h('span', { class: 'grow' }),
      x.status === 'gap' ? h('span', { class: 'tag warn' }, icon('warning', 'xs'), `Off by ${money(Math.abs(x.gap), cur)}`) : h('span', { class: `tag ${TAGS[x.status][1]}` }, TAGS[x.status][0]));
    const facts = x.status === 'unknown' ? h('p', { class: 'muted small' }, 'Monarch Money has not yet sent two balances for this account to compare.')
      : h('p', { class: 'muted small' }, `Since ${fmtDay(x.from, true)} the balance went from ${money(x.opening, cur)} to ${money(x.balance, cur)}; the ${plural(x.count, 'transaction')} here add up to ${money(x.moved, cur)}.`,
        x.status === 'accepted' ? ` Off by ${money(Math.abs(x.gap), cur)}, accepted as it is.` : '');
    const box = h('div', { class: `box balc ${x.status}` }, head, facts);
    // the past week's ones the bank's balance does not show yet, when they are the whole of the difference
    const named = (list) => list.map((t, i) => [i ? ', ' : '', h('button', { class: 'lnk', onclick: () => openTx(t.id) }, `${t.name || '(no payee)'} (${fmtDay(t.day)}, ${money(t.amount, cur)})`)]);
    if (x.status === 'waiting') put(box, h('p', { class: 'small' }, `The difference of ${money(Math.abs(x.gap), cur)} is exactly `, x.waiting.length === 1 ? 'this transaction' : `these ${x.waiting.length} transactions`,
      ' of the past week, which the bank’s balance does not show yet: ', named(x.waiting), '.'));
    if (x.status === 'gap') {
      const outMissing = x.isAsset ? x.gap < 0 : x.gap > 0;
      const what = x.isAsset ? 'The balance' : 'What is owed';
      put(box, h('p', null, `${what} is ${money(Math.abs(x.gap), cur)} ${x.gap < 0 ? 'lower' : 'higher'} than these transactions explain: `,
        outMissing ? 'money out is missing here, or money in is kept twice.' : 'money in is missing here, or money out is kept twice.'));
      if (x.weeks.length) {
        put(box, h('p', { class: 'muted small', style: { margin: '10px 0 2px' } }, 'The weeks in which the two moved apart, and by how much (weeks that cancel each other out, a matter of dates, are left out):'));
        put(box, h('ul', { class: 'balw' }, x.weeks.map((k) => h('li', null, h('span', null, `${fmtDay(k.from)} to ${fmtDay(k.to, true)}`), h('span', { class: 'num' }, `${k.change > 0 ? '+' : ''}${money(k.change, cur)}`),
          h('a', { class: 'lnk small', href: `#/transactions?${new URLSearchParams({ account: x.id, month: k.to.slice(0, 7), hid: '1' })}` }, `The transactions of ${fmtMonth(k.to.slice(0, 7))}`)))));
      }
      put(box, h('p', { class: 'muted small' }, 'Things to try: look for it among the ', h('a', { class: 'lnk', href: '#/duplicates' }, 'likely duplicates'),
        '; a transaction hidden in Monarch Money is not kept here and shows as a gap; syncing the account again fetches what the bank link dropped.'));
    }
    const acts = [x.status === 'gap' && can ? h('button', { class: 'pillbtn tiny', onclick: () => post(x, x.gap), title: 'Not flagged again while the gap stays the same' }, 'It is fine as it is') : null,
      x.status === 'accepted' && can ? h('button', { class: 'pillbtn tiny', onclick: () => post(x, null) }, 'Flag it again') : null,
      x.status === 'gap' && acct && may('admin') ? h('button', { class: 'pillbtn tiny', onclick: () => resyncAccount(acct) }, icon('sync', 'xs'), 'Sync this account again') : null,
      x.status === 'gap' && can ? h('a', { class: 'pillbtn tiny', href: `#/account/${x.id}/reconcile` }, icon('check', 'xs'), 'Reconcile with a statement') : null].filter(Boolean);
    if (acts.length) put(box, h('div', { class: 'chiprow', style: { marginTop: '10px' } }, acts));
    put(page, box);
  }
}

// ------------------------------------------------------------------ import transactions from a file
/** A bank's file (CSV, OFX, QFX) into an account kept by hand: choose it, see what it holds (for a CSV file which
    column is what), then bring in what the account does not have yet. */
const IMPORT_FIELDS = [['date', 'Date'], ['amount', 'Amount'], ['debit', 'Money out'], ['credit', 'Money in'], ['type', 'Debit or credit'], ['payee', 'Payee'], ['notes', 'Notes'], ['category', 'Category']];
export async function importDialog(a) {
  const file = h('input', { type: 'file', accept: '.csv,.ofx,.qfx,.qbo,.txt,text/csv' });
  const ok = await dialog(`Import a bank file into ${a.name}`, h('div', null,
    h('p', { class: 'muted' }, 'A file of transactions from the bank’s website: CSV, OFX or QFX (Quicken). What the account has already is left out.'), file),
  [{ label: 'Cancel', value: false }, { label: 'Next', value: true, primary: true }]);
  if (!ok) return;
  const fl = file.files[0];
  if (!fl) { toast('Choose a file first'); return; }
  if (fl.size > 20 * 1048576) { toast('That file is over 20 MB'); return; }
  const buf = await fl.arrayBuffer();
  let text; try { text = new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch { text = new TextDecoder('windows-1252').decode(buf); }
  const o = { mapping: null, dateOrder: null, flip: false, duplicates: false, balance: 'move', cols: false };
  const send = (preview) => api(`api/accounts/${a.id}/import`, { method: 'POST', json: { name: fl.name, text, preview, flip: o.flip, duplicates: o.duplicates, balance: o.balance,
    ...(o.mapping ? { mapping: o.mapping } : {}), ...(o.dateOrder ? { dateOrder: o.dateOrder } : {}) } });
  let p;
  try { p = await send(true); } catch (e) { fail(e); return; }
  const box = h('div', { class: 'impbox' });
  const again = async () => { try { p = await send(true); } catch (e) { fail(e); } draw(); };
  const draw = () => {
    const adds = o.duplicates ? p.total : p.new;
    const csv = p.kind === 'csv';
    const colSel = (k) => h('select', { class: 't', onchange: (e) => { o.mapping = { ...(o.mapping || p.mapping) }; if (e.target.value === '') delete o.mapping[k]; else o.mapping[k] = +e.target.value; again(); } },
      h('option', { value: '' }, 'Not in the file'), p.columns.map((c, i) => h('option', { value: i, selected: p.mapping[k] === i ? true : null }, `${c || `Column ${i + 1}`}${p.sample[0] && p.sample[0][i] ? ` (${String(p.sample[0][i]).slice(0, 18)})` : ''}`)));
    fill(box,
      p.needs ? h('p', { class: 'note warnnote' }, icon('warning', 's'), h('span', null, `${p.needs}.`))
        : h('p', null, `${plural(p.total, 'transaction')} in the file`, p.from ? `, ${fmtDay(p.from, true)} to ${fmtDay(p.to, true)}` : '', ': ', h('b', null, `${p.new} new`), p.duplicates ? `, ${p.duplicates} the account has already` : '', '.'),
      p.problemCount ? h('p', { class: 'muted small warn' }, `${plural(p.problemCount, 'line')} could not be read: `, p.problems.slice(0, 3).map((x) => `line ${x.line} (${x.why})`).join('; '), p.problemCount > 3 ? '…' : '') : null,
      csv ? h('details', { class: 'impcols', open: o.cols || p.needs ? true : null, ontoggle: (e) => { o.cols = e.target.open; } }, h('summary', null, 'Which column is what'),
        h('div', { class: 'grid' }, IMPORT_FIELDS.map(([k, l]) => fld(l, colSel(k))))) : null,
      csv ? h('div', { class: 'grid' }, fld(`Dates are written${p.guessed ? ' (a guess: check the first rows)' : ''}`, h('select', { class: 't', onchange: (e) => { o.dateOrder = e.target.value; again(); } },
        [['mdy', 'Month, day, year'], ['dmy', 'Day, month, year'], ['ymd', 'Year, month, day']].map(([v, l]) => h('option', { value: v, selected: p.dateOrder === v ? true : null }, l))), true)) : null,
      h('label', { class: 'check', style: { marginTop: '10px' } }, h('input', { type: 'checkbox', checked: o.flip ? true : null, onchange: (e) => { o.flip = e.target.checked; again(); } }), 'Money out is written as a positive number in this file (a card’s export often is)'),
      p.rows.length ? h('ul', { class: 'rows flat improws' }, p.rows.map((r) => h('li', { class: r.new ? null : 'off' }, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(r.day)),
        h('span', { class: 'main' }, h('b', null, r.payee || '(no payee)'), h('small', null, [r.category, r.notes].filter(Boolean).join(' · '))), r.new ? null : h('span', { class: 'tag' }, 'Already there'),
        h('span', { class: 'pt' }, amt(r.amount, a.currency)))))) : null,
      p.total > p.rows.length ? h('p', { class: 'muted small' }, `…and ${p.total - p.rows.length} more.`) : null,
      p.duplicates ? h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: o.duplicates ? true : null, onchange: (e) => { o.duplicates = e.target.checked; again(); } }), `Bring in the ${p.duplicates} the account has already too`) : null,
      !p.needs ? h('div', { class: 'grid', style: { marginTop: '10px' } }, fld(`The account’s balance (now ${money(a.balance, a.currency)})`, h('select', { class: 't', onchange: (e) => { o.balance = e.target.value; } },
        [['move', `Moves by what comes in (${money(p.sum, a.currency)})`], ['keep', 'Stays as it is'], p.fileBalance != null ? ['file', `Becomes the file’s balance (${money(p.fileBalance, a.currency)})`] : null].filter(Boolean)
          .map(([v, l]) => h('option', { value: v, selected: o.balance === v ? true : null }, l))), true)) : null,
      h('p', { class: 'muted small' }, adds ? `${plural(adds, 'transaction')} will come in. The rules apply to them, and transfers are linked.` : 'Nothing to bring in.'));
  };
  for (;;) {
    draw();
    if (!await dialog(`Import ${fl.name}`, box, [{ label: 'Cancel', value: false }, { label: 'Import', value: true, primary: true }], 'wide')) return;
    if (p.needs) { toast(p.needs); continue; }
    if (!(o.duplicates ? p.total : p.new)) { toast('Nothing to bring in'); return; }
    break;
  }
  try {
    const r = await send(false);
    S.cats = []; toast(`${plural(r.added, 'transaction')} imported`);
    await refreshSummary();
    if (location.hash === `#/account/${a.id}`) onRoute(); else location.hash = `#/account/${a.id}`;
  } catch (e) { fail(e); }
}

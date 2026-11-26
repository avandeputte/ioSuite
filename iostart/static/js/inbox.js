/* The Inbox page (#/inbox): mail sent or forwarded to the suite's mailbox (iostart/inbox/__init__.py).

   What could be filed by itself is filed (a receipt on its ioMoney transaction, papers in ioDocs, an invitation in
   ioCalendar) and listed under Done; the rest waits here, each with why, to be filed with a tap or let go. Your
   addresses: the other addresses you send from. Mailbox (suite admins): the mailbox the suite reads. */
import { addIcons, confirmDialog, dialog, fail, fill, fld, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, S } from './core.js';

addIcons({
  mail: 'M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z',
  attach: 'M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5a2.5 2.5 0 0 1 5 0v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5a2.5 2.5 0 0 0 5 0V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z',
});
const KIND = { receipt: ['receipt', 'Receipt'], document: ['doc', 'Papers'], invite: ['event', 'Invitation'], other: ['mail', 'Mail'] };
const APP = { iomoney: 'ioMoney', iodocs: 'ioDocs', iocalendar: 'ioCalendar' };

/** "10:42", "Mon", "12 Nov": when, short. */
function when(at) {
  const d = new Date(at * 1000), now = new Date();
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (now - d < 6 * 86400000) return d.toLocaleDateString([], { weekday: 'short' });
  return d.toLocaleDateString([], d.getFullYear() === now.getFullYear() ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' });
}
const money = (v) => (v == null ? '' : Math.abs(+v).toFixed(2));
const filedLine = (f) => (f ? h('span', null, f.auto ? 'Filed by itself' : 'Filed', ` in ${APP[f.app] || f.app}: `,
  f.url ? h('a', { href: f.url, target: '_blank', rel: 'noopener', onclick: (e) => e.stopPropagation() }, f.label) : f.label) : null);

export async function showInbox(page, r) {
  const st = { show: r.b === 'done' ? 'done' : 'waiting', data: null };
  const list = h('div', { class: 'ibrows' }), intro = h('div'), seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Show' });
  const tools = h('span', { class: 'ibtools' });
  page.append(h('div', { class: 'pagehead' },
    h('a', { class: 'iconbtn', href: '#/', title: 'Back to the start page', 'aria-label': 'Back to the start page' }, icon('left')),
    h('h1', null, 'Inbox'), seg, tools), intro, list);

  async function load() {
    try { st.data = await api(`api/inbox?show=${st.show}`); } catch (e) { fail(e); return; }
    draw();
  }
  function draw() {
    const d = st.data;
    history.replaceState(null, '', st.show === 'done' ? '#/inbox/done' : '#/inbox');
    seg.replaceChildren(...[['waiting', `To file${d.waiting ? ` (${d.waiting})` : ''}`], ['done', 'Done']].map(([k, t]) =>
      h('button', { class: st.show === k ? 'on' : '', onclick: () => { st.show = k; load(); } }, t)));
    fill(tools,  // (fill leaves out what is not there; replaceChildren would write the word "null")
      h('button', { class: 'iconbtn', title: 'Your addresses', 'aria-label': 'Your addresses', onclick: () => yourAddresses() }, icon('person', 's')),
      d.suiteAdmin ? h('button', { class: 'iconbtn', title: 'The mailbox the suite reads', 'aria-label': 'Mailbox', onclick: () => mailbox() }, icon('settings', 's')) : null,
      d.suiteAdmin && d.mailbox.ready ? h('button', { class: 'iconbtn', title: 'Look for new mail now', 'aria-label': 'Look for new mail now', onclick: (e) => checkNow(e.currentTarget) }, icon('update', 's')) : null);
    const m = d.mailbox;
    intro.replaceChildren(m.ready
      ? h('p', { class: 'muted small ibhint' }, 'Send or forward mail to ', m.address ? h('b', null, m.address) : 'the suite\'s mailbox',
        '. Receipts go on their ioMoney transaction, papers to ioDocs, invitations to ioCalendar.',
        m.address ? [' To say where, add ', ...['+money', '+docs', '+calendar'].flatMap((t, i) => [i ? ', ' : '', h('code', null, t)]), ' to the name (',
          h('code', null, m.address.replace('@', '+docs@')), '), or ', h('code', null, '+inbox'), ' to keep it here.'] : null)
      : h('div', { class: 'box' }, h('h2', null, icon('mail'), 'The suite\'s mailbox'),
        h('p', null, 'Mail forwarded to one mailbox lands where it belongs: a receipt on its ioMoney transaction, a PDF in ioDocs, an invitation in ioCalendar. The rest waits here.'),
        d.suiteAdmin ? h('button', { class: 'pillbtn primary', onclick: () => mailbox() }, icon('settings', 's'), 'Set up the mailbox')
          : h('p', { class: 'muted' }, 'A suite admin sets up the mailbox.')));
    if (!d.items.length) {
      list.replaceChildren(h('div', { class: 'empty' }, st.show === 'done' ? 'Nothing filed in the last 30 days.' : m.ready ? 'Nothing to file. All sorted.' : ''));
      return;
    }
    list.replaceChildren(...d.items.map((it) => {
      const [ic, label] = KIND[it.kind] || KIND.other;
      return h('button', { class: `ibrow${it.person == null ? ' nobody' : ''}`, onclick: () => openItem(it.id) },
        h('span', { class: 'ibic', title: label }, icon(ic, 's')),
        h('span', { class: 'ibmain' },
          h('span', { class: 'ibsubj' }, it.subject),
          h('span', { class: 'ibfrom muted small' }, it.name || it.from, it.kind === 'receipt' && it.guess.amount ? ` · ${money(it.guess.amount)}` : ''),
          it.status === 'filed' ? h('span', { class: 'ibnote small' }, filedLine(it.filed))
            : it.status === 'gone' ? h('span', { class: 'ibnote muted small' }, 'Let go')
              : it.note ? h('span', { class: 'ibnote muted small' }, it.note) : null),
        h('span', { class: 'ibwhen muted small' }, when(it.received)));
    }));
  }

  async function openItem(id) {
    let it;
    try { it = await api(`api/inbox/${id}`); } catch (e) { fail(e); return; }
    const d = st.data, out = h('div', { class: 'ibact' });
    const done = (msg) => { document.querySelector('.dialog-back')?.close?.(null); if (msg) toast(msg); load(); };
    const call = async (path, body) => { try { const x = await api(`api/inbox/${id}/${path}`, { method: 'POST', json: body || {} }); return x; } catch (e) { fail(e); return null; } };
    const fileTo = async (body, what) => { const x = await call('file', body); if (x) done(`Filed: ${(x.filed || {}).label || what}`); };

    async function pickTransaction() {
      out.replaceChildren(h('span', { class: 'muted small' }, 'Looking in ioMoney…'));
      let got;
      try { got = await api(`api/inbox/${id}/matches`); } catch (e) { out.replaceChildren(h('span', { class: 'err' }, e.message)); return; }
      out.replaceChildren(h('h3', null, it.guess.amount ? `Transactions of ${money(it.guess.amount)} around ${it.guess.day}` : 'Transactions'),
        ...(got.items.length ? got.items.map((t) => h('button', { class: 'ibmatch', onclick: () => fileTo({ to: 'money', transaction: t.id }, 'the transaction') },
          h('b', null, t.merchant || '(no payee)'), h('span', { class: 'muted small' }, [t.day, t.account, money(t.amount)].filter(Boolean).join(' · ')),
          t.receipts ? h('span', { class: 'muted small' }, `${t.receipts} receipt${t.receipts > 1 ? 's' : ''} kept already`) : null))
          : [h('p', { class: 'muted small' }, 'No transaction of this amount around then. It may not have come from the bank yet: it is tried again every hour for ten days.')]));
    }
    async function pickCalendar() {
      out.replaceChildren(h('span', { class: 'muted small' }, 'Looking in ioCalendar…'));
      let got;
      try { got = await api('api/inbox/calendars'); } catch (e) { out.replaceChildren(h('span', { class: 'err' }, e.message)); return; }
      const sel = h('select', { class: 't' }, got.items.map((c) => h('option', { value: c.id, selected: c.mine ? true : null }, c.name)));
      out.replaceChildren(h('div', { class: 'multi' }, fld('Calendar', sel), h('button', { class: 'pillbtn primary noic', onclick: () => fileTo({ to: 'calendar', calendar: +sel.value }, 'the event') }, 'Add')));
    }

    const mine = it.person != null && it.person === S.user.id;
    const papers = it.files.filter((f) => f.mime !== 'text/calendar');
    const acts = [];
    if (it.status === 'waiting' && mine) {
      acts.push(h('button', { class: 'pillbtn', onclick: pickTransaction }, icon('receipt', 's'), 'On a transaction'));
      if (papers.length) acts.push(h('button', { class: 'pillbtn', onclick: () => fileTo({ to: 'docs' }, 'in ioDocs') }, icon('doc', 's'), 'Keep in ioDocs'));
      if (it.invite || it.files.some((f) => f.mime === 'text/calendar')) acts.push(h('button', { class: 'pillbtn', onclick: pickCalendar }, icon('event', 's'), 'Add to ioCalendar'));
      acts.push(h('button', { class: 'pillbtn', onclick: async () => { if (await call('let-go')) done('Let go'); } }, icon('check', 's'), 'Nothing to file'));
    }
    if (it.status === 'waiting' && it.person == null && d.suiteAdmin) {
      const who = h('select', { class: 't' }, h('option', { value: '' }, 'Give it to…'), d.people.map((p) => h('option', { value: p.id }, p.name)));
      who.onchange = async () => { if (who.value && await call('give', { person: +who.value })) done('Given'); };
      acts.push(who, h('button', { class: 'pillbtn', onclick: async () => { if (await call('let-go')) done('Let go'); } }, icon('check', 's'), 'Let go'));
    }
    if (it.status !== 'waiting') acts.push(h('button', { class: 'pillbtn', onclick: async () => { if (await call('back')) done('Back in To file'); } }, icon('history', 's'), 'Back to To file'));
    acts.push(h('button', { class: 'pillbtn danger', onclick: async () => {
      if (!await confirmDialog('Delete this message', 'It goes from the Inbox at once, with its files. What was filed stays where it went.', 'Delete', true)) return;
      try { await api(`api/inbox/${id}`, { method: 'DELETE' }); done('Deleted'); } catch (e) { fail(e); }
    } }, icon('delete', 's'), 'Delete'));

    const sent = new Date((it.sent || it.received) * 1000);
    dialog(it.subject, h('div', { class: 'ibitem' },
      h('div', { class: 'muted small' }, `${it.name ? `${it.name} <${it.from}>` : it.from} · ${sent.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}`),
      it.person == null ? h('p', { class: 'small ibwarn' }, icon('warn', 's'), 'From an address nobody in the family has. Give it to someone (it is theirs to file then), or let it go.') : null,
      !it.trusted && it.person != null ? h('p', { class: 'muted small' }, 'The mail server could not vouch for the sender, so nothing was filed by itself.') : null,
      it.status === 'filed' ? h('p', { class: 'small' }, filedLine(it.filed)) : it.note && it.person != null ? h('p', { class: 'small ibwarn' }, it.note) : null,
      papers.length || it.files.length ? h('div', { class: 'ibfiles' }, it.files.map((f) => h('a', { class: 'pillbtn noic', href: f.url, target: '_blank', rel: 'noopener' }, icon('attach', 's'), f.name))) : null,
      h('pre', { class: 'ibtext' }, it.text || '(no text)'),
      h('div', { class: 'ibacts' }, acts), out), [{ label: 'Close', value: null }], 'wide ibdialog');
  }

  async function yourAddresses() {
    let me;
    try { me = await api('api/inbox/me'); } catch (e) { fail(e); return; }
    const addrs = h('textarea', { class: 't', rows: 3, placeholder: 'one per line' }, me.addresses.join('\n'));
    const auto = h('input', { type: 'checkbox', checked: me.auto ? true : null });
    let cals = [];
    try { cals = (await api('api/inbox/calendars')).items; } catch { /* no ioCalendar */ }
    const cal = h('select', { class: 't' }, h('option', { value: '' }, 'My own (the first)'), cals.map((c) => h('option', { value: c.id, selected: c.id === me.calendar ? true : null }, c.name)));
    await dialog('Your addresses', h('div', null,
      h('p', { class: 'muted small' }, 'Mail from these addresses is yours: nobody else sees it. ', me.email ? ['Your account\'s address, ', h('b', null, me.email), ', counts too.'] : 'Your account has no address yet (Settings › Account).',
        (me.card || []).length ? [' So do the addresses on your own card in ioContact: ', me.card.join(', '), '.'] : ' So do the addresses on your own card in ioContact, once a card there is marked “This is me”.'),
      fld('Other addresses you send from', addrs),
      h('label', { class: 'check' }, auto, ' File what is clear by itself (only when the mail server vouches that it is from you)'),
      cals.length ? fld('Invitations go to', cal) : null),
    [{ label: 'Cancel', value: null }, { label: 'Save', primary: true, value: async () => {
      await api('api/inbox/me', { method: 'PUT', json: { addresses: addrs.value, auto: auto.checked, ...(cals.length ? { calendar: cal.value ? +cal.value : null } : {}) } });
      toast('Saved'); return true;
    } }], '', { wait: true });
  }

  async function mailbox() {
    let m;
    try { m = await api('api/inbox/mailbox'); } catch (e) { fail(e); return; }
    const host = h('input', { class: 't', value: m.host, placeholder: 'imap.gmail.com', autocomplete: 'off' });
    const port = h('input', { class: 't', type: 'number', value: m.port, min: 1, max: 65535 });
    const user = h('input', { class: 't', value: m.user, placeholder: 'family.inbox@gmail.com', autocomplete: 'off' });
    const pw = h('input', { class: 't', type: 'password', placeholder: m.passwordSet ? '(kept)' : 'an app password', autocomplete: 'new-password' });
    const folder = h('input', { class: 't', value: m.folder });
    const on = h('input', { type: 'checkbox', checked: m.on ? true : null });
    const s = m.state || {};
    await dialog('The suite\'s mailbox', h('div', null,
      h('p', { class: 'muted small' }, 'A mailbox of its own for the family (a new Gmail or Fastmail address will do), read over IMAP every five minutes. Its messages stay there, marked read. The password is kept with the suite\'s keys and tokens.'),
      h('div', { class: 'grid' }, fld('Mail server (IMAP)', host), fld('Port', port, '993: over TLS'), fld('User name', user, 'usually the address'), fld('Password', pw), fld('Folder', folder)),
      h('label', { class: 'check' }, on, ' Read it'),
      s.checkedAt ? h('p', { class: `small ${s.error ? 'err' : 'muted'}` }, `Last look ${new Date(s.checkedAt * 1000).toLocaleString()}: ${s.error || 'fine'}`) : null),
    [{ label: 'Cancel', value: null }, { label: 'Save', primary: true, value: async () => {
      const got = await api('api/inbox/mailbox', { method: 'PUT', json: { host: host.value.trim(), port: +port.value || 993, user: user.value.trim(), folder: folder.value.trim() || 'INBOX', on: on.checked, ...(pw.value ? { password: pw.value } : {}) } });
      if (got.ready) { try { const c = await api('api/inbox/mailbox/check', { method: 'POST' }); toast(`Saved. ${c.kept} new message${c.kept === 1 ? '' : 's'}.`); } catch (e) { toast(`Saved, but: ${e.message}`); } } else toast('Saved');
      return true;
    } }], 'wide', { wait: true });
    load();
  }

  async function checkNow(btn) {
    btn.disabled = true;
    try { const c = await api('api/inbox/mailbox/check', { method: 'POST' }); toast(c.kept ? `${c.kept} new message${c.kept === 1 ? '' : 's'}` : 'Nothing new'); } catch (e) { fail(e); }
    btn.disabled = false;
    load();
  }

  await load();
  S.refresh = load;  // the page stays fresh while it stays open (main.js liveRefresh)
}

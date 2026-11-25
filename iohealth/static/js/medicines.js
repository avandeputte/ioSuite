import { TZ, empty, h, isoDate, loading, pages, resetPage, showError } from './core.js';
import { pageTitle } from './shell.js';
import { card } from './charts.js';
import { dialog, toast } from './shell.js';

/** A dialog whose buttons do something and stay open when that fails: the suite's dialog (frame.js), where a button's
 *  value may be a function and an answer of undefined keeps the dialog. `action` gives false to stay. */
const formDialog = (title, body, buttons) => dialog(title, body, buttons.filter(Boolean).map((b) => ({
  label: b.label, primary: b.primary, danger: b.danger,
  value: b.action ? async () => ((await b.action()) === false ? undefined : true) : (b.value ?? null),
})), '', { wait: true });

// ---------- medicines and allergies: the doses of the day to tick, the medicines, the last 30 days, the allergies ----------
// Everything here is the signed-in person's own (iohealth/meds.py). Times are the person's local times; the server
// sends the reminders at those times in the zone it last saw (this browser's, sent as tz with every request).

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];  // Python's weekday order, as the server keeps them
export const SEVERITY = { severe: 'Severe', moderate: 'Moderate', mild: 'Mild', '': '' };

/** el.replaceChildren(), leaving out what is null or false (a part not shown). */
export const fill = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false));

export async function medApi(path, { method = 'GET', body, params = {} } = {}) {
  const q = new URLSearchParams({ ...params, tz: TZ });
  const r = await fetch(`api/${path}?${q}`, { method, credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || data.detail || r.statusText);
  return data;
}

const fmtSlot = (slot) => {
  const [hh, mm] = slot.split(':').map(Number);
  return new Date(2000, 0, 1, hh, mm).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};
const fmtClock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const list = (xs) => xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`;

/** "08:00 and 20:00, every day", "Mon, Wed and Fri at 08:00", "When needed". */
export function schedule(m) {
  if (m.asNeeded) return 'When needed';
  const days = m.days.length === 7 ? 'every day' : m.days.join('') === '01234' ? 'weekdays' : m.days.join('') === '56' ? 'weekends' : list(m.days.map((d) => WEEKDAYS[d]));
  return `${list(m.times.map(fmtSlot))}, ${days}`;
}

/** How often, without the hours, for the printed emergency card (the hours are for the reminders, and may change):
    "once a day", "twice a day", "once a week", "once a day on weekdays", "when needed". */
export function howOften(m) {
  if (m.asNeeded) return 'when needed';
  const n = m.times.length, times = n === 1 ? 'once' : n === 2 ? 'twice' : `${['three', 'four', 'five', 'six'][n - 3] || n} times`;
  if (m.days.length === 7) return `${times} a day`;
  if (m.days.length === 1) return n === 1 ? 'once a week' : `${times} a day, one day a week`;
  const days = m.days.join('') === '01234' ? 'weekdays' : m.days.join('') === '56' ? 'weekends' : list(m.days.map((d) => WEEKDAYS[d]));
  return `${times} a day on ${days}`;
}

export const stillTaken = (m, day = isoDate(new Date())) => (!m.startOn || m.startOn <= day) && (!m.endOn || day <= m.endOn) && (!m.stoppedOn || day < m.stoppedOn);

pages.medicines = async (main, _arg, params) => {
  let day = params.get('date') || isoDate(new Date());
  const todayCard = card(null), medsCard = card(null), allergyCard = card(null), historyCard = card(null);
  fill(main, pageTitle('pill', 'green', 'Medicines'),
    h('div', { class: 'grid cols-2' }, todayCard, h('div', {}, medsCard, allergyCard)), historyCard,
    h('p', { class: 'small muted noprint' }, 'Only you see your medicines and allergies. A reminder comes at each time on the devices where you turned on ',
      h('a', { href: '#/settings/account' }, 'Medicine reminders'), ' (Settings › Account › Notifications). They go on your ',
      h('a', { href: '#/emergency' }, 'emergency card'), '.'));
  let data;
  async function load() {
    resetPage();
    try { data = await medApi('medicines', { params: { date: day } }); } catch (e) { showError(todayCard, e); return; }
    drawToday(); drawMeds(); drawAllergies();
  }

  function drawToday() {
    const d = data.day, isToday = d.date === isoDate(new Date());
    const shift = (n) => { const x = new Date(d.date + 'T12:00'); x.setDate(x.getDate() + n); day = isoDate(x); history.replaceState(null, '', isToday && n === 0 ? '#/medicines' : `#/medicines?date=${day}`); load(); };
    const title = isToday ? 'Today' : new Date(d.date + 'T12:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
    const rows = d.doses.map((x) => doseRow(x, d.date));
    const extra = d.asNeeded.map((x) => h('div', { class: 'dose' },
      h('div', { class: 'dose-time muted' }, '—'),
      h('div', { class: 'dose-what' }, h('b', {}, x.name), x.dose ? ` ${x.dose}` : '', h('div', { class: 'small muted' }, 'When needed',
        x.taken.length ? ` · taken at ${list(x.taken.map((t) => fmtClock(t.at)))}` : '', x.note ? ` · ${x.note}` : '')),
      isToday ? h('button', { onclick: async () => { await medApi(`medicines/${x.medicine}/doses`, { method: 'POST', body: {} }); toast(`${x.name}: taken now`); load(); } }, 'Took one') : null));
    const done = d.doses.filter((x) => x.taken).length;
    fill(todayCard, 
      h('div', { class: 'row spread' }, h('h2', { style: { margin: 0 } }, title, d.doses.length ? h('span', { class: 'muted', style: { fontWeight: 400 } }, `  ${done} of ${d.doses.length} taken`) : null),
        h('div', { class: 'seg noprint' }, h('button', { title: 'The day before', onclick: () => shift(-1) }, '‹'), h('button', { title: 'Today', onclick: () => { day = isoDate(new Date()); history.replaceState(null, '', '#/medicines'); load(); } }, 'Today'),
          h('button', { title: 'The day after', disabled: isToday || null, onclick: () => shift(1) }, '›'))),
      rows.length || extra.length ? h('div', { class: 'doses' }, rows, extra) : empty(data.medicines.length ? 'Nothing due this day.' : 'Add the medicines you take, and tick each dose here as you take it.'));
  }

  function doseRow(x, date) {
    const tick = async (body) => { await medApi(`medicines/${x.medicine}/doses`, { method: 'POST', body: { day: date, slot: x.slot, ...body } }); load(); };
    const late = !x.taken && !x.skipped && x.at * 1000 < Date.now();
    const state = x.taken ? h('span', { class: 'dose-state good' }, `✓ Taken ${fmtClock(x.taken)}`) : x.skipped ? h('span', { class: 'dose-state muted' }, 'Skipped') : null;
    return h('div', { class: 'dose' + (x.taken ? ' taken' : '') + (x.skipped ? ' skipped' : '') + (late ? ' late' : '') },
      h('div', { class: 'dose-time num' }, fmtSlot(x.slot)),
      h('div', { class: 'dose-what' }, h('b', {}, x.name), x.dose ? ` ${x.dose}` : '', x.note ? h('div', { class: 'small muted' }, x.note) : null),
      state,
      x.taken || x.skipped
        ? h('button', { class: 'small-btn noprint', title: 'Not ticked after all', onclick: () => tick({ taken: false, skipped: false }) }, 'Undo')
        : h('div', { class: 'row noprint', style: { gap: '6px', flexWrap: 'nowrap' } },
          h('button', { class: 'small-btn', onclick: () => tick({ taken: false, skipped: true }) }, 'Skip'),
          h('button', { class: 'primary', onclick: () => tick({ taken: true }) }, '✓ Taken')));
  }

  function drawMeds() {
    const now = data.medicines.filter((m) => stillTaken(m)), before = data.medicines.filter((m) => !stillTaken(m));
    const row = (m) => h('div', { class: 'record click', role: 'button', tabindex: 0, onclick: () => editMedicine(m, load), onkeydown: (e) => { if (e.key === 'Enter') editMedicine(m, load); } },
      h('div', {}, h('b', {}, m.name), m.dose ? ` ${m.dose}` : '', h('div', { class: 'small muted' }, schedule(m), m.reason ? ` · ${m.reason}` : '',
        m.stoppedOn ? ` · stopped ${new Date(m.stoppedOn + 'T12:00').toLocaleDateString()}` : m.endOn && !stillTaken(m) ? ` · ended ${new Date(m.endOn + 'T12:00').toLocaleDateString()}` : '')),
      h('div', { class: 'row', style: { gap: '4px' } }, !m.remind && !m.asNeeded ? h('span', { class: 'badge' }, 'no reminder') : null, !m.onCard ? h('span', { class: 'badge' }, 'not on the card') : null));
    fill(medsCard, 
      h('div', { class: 'row spread' }, h('h2', { style: { margin: 0 } }, 'Your medicines'), h('button', { class: 'noprint', onclick: () => editMedicine(null, load) }, '+ Add')),
      now.length ? h('div', { style: { marginTop: '8px' } }, now.map(row)) : empty('No medicines yet.'),
      before.length ? h('details', { style: { marginTop: '10px' } }, h('summary', { class: 'muted' }, `Stopped (${before.length})`), before.map(row)) : null);
    drawHistory();
  }

  function drawAllergies() {
    const row = (a) => h('div', { class: 'record click', role: 'button', tabindex: 0, onclick: () => editAllergy(a, load), onkeydown: (e) => { if (e.key === 'Enter') editAllergy(a, load); } },
      h('div', {}, h('b', {}, a.name), a.reaction || a.note ? h('div', { class: 'small muted' }, [a.reaction, a.note].filter(Boolean).join(' · ')) : null),
      a.severity ? h('span', { class: `sev sev-${a.severity}` }, SEVERITY[a.severity]) : null);
    fill(allergyCard, 
      h('div', { class: 'row spread' }, h('h2', { style: { margin: 0 } }, 'Allergies'), h('button', { class: 'noprint', onclick: () => editAllergy(null, load) }, '+ Add')),
      data.allergies.length ? h('div', { style: { marginTop: '8px' } }, data.allergies.map(row)) : empty('No allergies written down.'));
  }

  async function drawHistory() {
    if (!data.medicines.some((m) => !m.asNeeded)) { historyCard.hidden = true; return; }
    historyCard.hidden = false;
    loading(historyCard);
    let hist;
    try { hist = await medApi('medicines/history', { params: { days: 30 } }); } catch (e) { showError(historyCard, e); return; }
    const ids = [...new Set(hist.days.flatMap((d) => d.medicines.map((m) => m.medicine)))];
    const rows = ids.map((id) => {
      let due = 0, taken = 0;
      const cells = hist.days.map((d) => {
        const m = d.medicines.find((x) => x.medicine === id);
        if (!m) return h('i', { class: 'hc none', title: `${d.date}: not due` });
        const future = d.date === hist.to && m.taken < m.due;  // today, still to come
        if (!future) { due += m.due; taken += m.taken; }
        const cls = m.taken >= m.due ? 'all' : future ? 'none' : m.taken ? 'some' : m.skipped >= m.due ? 'skip' : 'miss';
        return h('i', { class: `hc ${cls}`, title: `${new Date(d.date + 'T12:00').toLocaleDateString()}: ${m.taken} of ${m.due} taken${m.skipped ? `, ${m.skipped} skipped` : ''}` });
      });
      return h('div', { class: 'hrow' }, h('div', { class: 'hname' }, hist.names[id] || '?'), h('div', { class: 'hcells' }, cells),
        h('div', { class: 'hpct num muted' }, due ? `${Math.round(taken / due * 100)}%` : '—'));
    });
    fill(historyCard, h('h2', {}, 'The last 30 days'), rows.length ? h('div', { class: 'hist' }, rows) : empty('Nothing was due.'),
      h('div', { class: 'legend' }, h('span', {}, h('i', { class: 'hc all' }), 'all taken'), h('span', {}, h('i', { class: 'hc some' }), 'some'),
        h('span', {}, h('i', { class: 'hc miss' }), 'not ticked'), h('span', {}, h('i', { class: 'hc skip' }), 'skipped')));
  }

  load();
};

// ---------- the dialogs ----------

const field = (label, input, hint) => h('label', { class: 'fld' }, h('span', { class: 'fl' }, label), input, hint ? h('span', { class: 'small muted' }, hint) : null);

export function editMedicine(m, done) {
  const v = m || { name: '', dose: '', reason: '', note: '', times: ['08:00'], days: [0, 1, 2, 3, 4, 5, 6], asNeeded: false, startOn: null, endOn: null, remind: true, onCard: true, stoppedOn: null };
  const name = h('input', { type: 'text', value: v.name, maxlength: 128, placeholder: 'Lisinopril', required: true });
  const dose = h('input', { type: 'text', value: v.dose, maxlength: 64, placeholder: '10 mg, 1 tablet' });
  const reason = h('input', { type: 'text', value: v.reason, maxlength: 128, placeholder: 'Blood pressure' });
  const note = h('input', { type: 'text', value: v.note, maxlength: 255, placeholder: 'With food' });
  let times = v.asNeeded ? ['08:00'] : [...v.times], days = new Set(v.days), asNeeded = v.asNeeded;
  const timesBox = h('div', { class: 'times' }), daysBox = h('div', { class: 'row', style: { gap: '4px' } });
  const remind = h('input', { type: 'checkbox', checked: v.remind });
  const onCard = h('input', { type: 'checkbox', checked: v.onCard });
  const start = h('input', { type: 'date', value: v.startOn || '' }), end = h('input', { type: 'date', value: v.endOn || '' });
  const when = h('div', { class: 'seg' });
  const setTimes = h('div', {});
  const drawWhen = () => {
    fill(when, ...[[false, 'At set times'], [true, 'When needed']].map(([k, l]) => h('button', { type: 'button', class: asNeeded === k ? 'on' : '', onclick: () => { asNeeded = k; drawWhen(); } }, l)));
    setTimes.hidden = asNeeded;
    fill(timesBox, ...times.map((t, i) => h('span', { class: 'timechip' },
      h('input', { type: 'time', value: t, onchange: (e) => { times[i] = e.target.value; } }),
      times.length > 1 ? h('button', { type: 'button', class: 'small-btn', title: 'Remove this time', onclick: () => { times.splice(i, 1); drawWhen(); } }, '×') : null)),
    times.length < 8 ? h('button', { type: 'button', class: 'small-btn', onclick: () => { times.push(times.length ? '20:00' : '08:00'); drawWhen(); } }, '+ time') : null);
    fill(daysBox, ...WEEKDAYS.map((d, i) => h('button', { type: 'button', class: 'chip' + (days.has(i) ? ' on' : ''), onclick: () => { days.has(i) ? days.delete(i) : days.add(i); if (!days.size) days.add(i); drawWhen(); } }, d)));
  };
  drawWhen();
  setTimes.append(field('Times', timesBox), field('Days', daysBox), h('label', { class: 'row check' }, remind, 'Remind me at these times'));
  const err = h('p', { class: 'error', hidden: true });
  const body = h('div', { class: 'form' }, field('Name', name), h('div', { class: 'two' }, field('Dose', dose), field('What for', reason)),
    field('Note', note), field('When', when), setTimes, h('div', { class: 'two' }, field('Starts', start), field('Ends', end, 'Left empty: no end')),
    h('label', { class: 'row check' }, onCard, 'On my emergency card'), err);
  const payload = () => ({ name: name.value, dose: dose.value, reason: reason.value, note: note.value, times: asNeeded ? [] : times.filter(Boolean),
    days: [...days].sort(), startOn: start.value || null, endOn: end.value || null, remind: remind.checked, onCard: onCard.checked });
  const send = async (path, method, b) => {
    try { await medApi(path, { method, body: b }); done(); return true; } catch (e) { err.textContent = e.message; err.hidden = false; return false; }
  };
  const today = isoDate(new Date());
  return formDialog(m ? m.name : 'Add a medicine', body, [
    m ? { label: 'Delete', danger: true, action: async () => {
      if (await dialog(`Delete ${m.name}?`, h('p', {}, 'It goes with every dose ticked. To keep that, stop taking it instead.'), [{ label: 'Cancel', value: false }, { label: 'Delete', danger: true, value: true }]) !== true) return false;
      return send(`medicines/${m.id}`, 'DELETE');
    } } : null,
    m && stillTaken(m) ? { label: 'Stopped taking it', action: () => send(`medicines/${m.id}`, 'PATCH', { ...payload(), stoppedOn: today }) } : null,
    m && m.stoppedOn ? { label: 'Taking it again', action: () => send(`medicines/${m.id}`, 'PATCH', { ...payload(), stoppedOn: null }) } : null,
    { label: 'Cancel' },
    { label: m ? 'Save' : 'Add', primary: true, action: () => (name.value.trim() ? send(m ? `medicines/${m.id}` : 'medicines', m ? 'PATCH' : 'POST', payload()) : (name.focus(), false)) },
  ]);
}

export function editAllergy(a, done) {
  const v = a || { name: '', reaction: '', severity: '', note: '' };
  const name = h('input', { type: 'text', value: v.name, maxlength: 128, placeholder: 'Penicillin, peanuts, bee stings' });
  const reaction = h('input', { type: 'text', value: v.reaction, maxlength: 255, placeholder: 'Hives, swelling, anaphylaxis' });
  const note = h('input', { type: 'text', value: v.note, maxlength: 255, placeholder: 'EpiPen in the bag' });
  let severity = v.severity;
  const sev = h('div', { class: 'seg' });
  const drawSev = () => fill(sev, ...[['', 'Not said'], ['mild', 'Mild'], ['moderate', 'Moderate'], ['severe', 'Severe']].map(([k, l]) =>
    h('button', { type: 'button', class: severity === k ? 'on' : '', onclick: () => { severity = k; drawSev(); } }, l)));
  drawSev();
  const err = h('p', { class: 'error', hidden: true });
  const send = async (path, method, b) => {
    try { await medApi(path, { method, body: b }); done(); return true; } catch (e) { err.textContent = e.message; err.hidden = false; return false; }
  };
  return formDialog(a ? a.name : 'Add an allergy', h('div', { class: 'form' }, field('Allergic to', name), field('Reaction', reaction), field('How bad', sev), field('Note', note), err), [
    a ? { label: 'Delete', danger: true, action: () => send(`allergies/${a.id}`, 'DELETE') } : null,
    { label: 'Cancel' },
    { label: a ? 'Save' : 'Add', primary: true, action: () => (name.value.trim() ? send(a ? `allergies/${a.id}` : 'allergies', a ? 'PATCH' : 'POST',
      { name: name.value, reaction: reaction.value, severity, note: note.value }) : (name.focus(), false)) },
  ]);
}

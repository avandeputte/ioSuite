import { empty, h, pages, showError } from './core.js';
import { pageTitle } from './shell.js';
import { card } from './charts.js';
import { SEVERITY, fill, howOften, medApi } from './medicines.js';

// ---------- the emergency card: a wallet-size card to print, cut out and fold ----------
// Front: name, date of birth, blood type, allergies, conditions, organ donation. Back: medicines, doctors, people to
// call, health insurance. The doctors and people come from ioContact and the insurance from ioDocs, read as you
// (iohealth/emergency.py), so the card only shows what you see there.

const MAX = 4;
const BLOOD = ['', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const fmtDay = (d) => new Date(d + 'T12:00').toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });

/** The card itself, both sides, at its printed size (85.6 × 54 mm a side). */
export function cardSheet(c) {
  const sec = (title, ...kids) => h('div', { class: 'ec-sec' }, h('div', { class: 'ec-h' }, title), ...kids);
  const allergies = c.allergies.length
    ? c.allergies.map((a) => h('div', { class: 'ec-line' + (a.severity === 'severe' ? ' ec-bad' : '') }, h('b', {}, a.name),
      [a.severity && SEVERITY[a.severity].toLowerCase(), a.reaction].filter(Boolean).length ? ` (${[a.severity && SEVERITY[a.severity].toLowerCase(), a.reaction].filter(Boolean).join(': ')})` : ''))
    : [h('div', { class: 'ec-line' }, 'No known allergies')];
  const front = h('div', { class: 'ec-side ec-front' },
    h('div', { class: 'ec-band' }, h('span', { class: 'ec-cross' }, '+'), 'Emergency medical information'),
    h('div', { class: 'ec-body' },
      h('div', { class: 'ec-name' }, c.person.name || ''),
      h('div', { class: 'ec-facts' }, c.person.born ? h('span', {}, `Born ${fmtDay(c.person.born)}`) : null,
        c.bloodType ? h('span', {}, 'Blood type ', h('b', {}, c.bloodType)) : null,
        c.organDonor ? h('span', {}, `Organ donor: ${c.organDonor}`) : null),
      sec('Allergies', allergies),
      c.conditions ? sec('Conditions', h('div', { class: 'ec-line' }, c.conditions)) : null,
      c.notes ? sec('Also', h('div', { class: 'ec-line' }, c.notes)) : null));
  const found = (xs) => xs.filter((x) => x.found);
  const who = (x, org = true) => h('div', { class: 'ec-line' }, h('b', {}, x.name), org && x.org ? `, ${x.org}` : '', x.relation ? `, ${x.relation.toLowerCase()}` : '', x.phone ? h('span', { class: 'ec-tel' }, ` ${x.phone}`) : null);
  const back = h('div', { class: 'ec-side ec-back' },
    h('div', { class: 'ec-body' },
      sec('Medicines', c.medicines.length ? c.medicines.map((m) => h('div', { class: 'ec-line' }, h('b', {}, m.name), m.dose ? ` ${m.dose}` : '', h('span', { class: 'ec-dim' }, ` ${howOften(m)}`)))
        : h('div', { class: 'ec-line' }, 'None')),
      found(c.doctors).length ? sec(found(c.doctors).length > 1 ? 'Doctors' : 'Doctor', found(c.doctors).map((x) => who(x))) : null,
      found(c.contacts).length ? sec('In an emergency, call', found(c.contacts).map((x) => who(x, false))) : null,
      found(c.documents).length ? sec('Insurance', found(c.documents).map((d) => h('div', { class: 'ec-line' }, h('b', {}, d.issuer || d.title),
        d.number ? ` · ${d.number}` : '', d.fields.map((f) => ` · ${f.name} ${f.value}`)))) : null),
    h('div', { class: 'ec-foot' }, `Updated ${fmtDay(c.printed)}`));
  return h('div', { class: 'ec-sheet' }, h('div', { class: 'ec-card' }, front, back),
    h('p', { class: 'ec-how' }, 'Cut along the outer edge, fold along the middle line, and keep it with your ID.'));
}

function overflowing(sheet) {
  return [...sheet.querySelectorAll('.ec-body')].some((b) => b.scrollHeight > b.clientHeight + 1);
}

function printCard() {
  const root = document.documentElement;
  root.classList.add('print-card');
  window.addEventListener('afterprint', () => root.classList.remove('print-card'), { once: true });
  window.print();
}

pages.emergency = async (main) => {
  const preview = h('div', { class: 'ec-preview' }), warn = h('p', { class: 'error noprint', hidden: true }, 'There is more than fits on the card: what does not fit is cut off. Shorten the conditions or the note, or take some medicines off the card (on the Medicines page).');
  const aboutCard = card('About you'), peopleCard = card(null), docsCard = card(null), fromCard = card('From the Medicines page');
  fill(main, 
    h('div', { class: 'row spread' }, pageTitle('badge', 'rose', 'Emergency card'), h('button', { class: 'primary noprint', onclick: printCard }, 'Print the card')),
    card(null, preview, warn),
    h('div', { class: 'grid cols-2 noprint', style: { marginTop: '16px' } }, h('div', {}, aboutCard, fromCard), h('div', {}, peopleCard, docsCard)));
  let c;
  const save = async (b) => { try { await medApi('emergency', { method: 'PUT', body: b }); } catch (e) { alertIn(aboutCard, e); return; } await load(); };
  async function load() {
    try { c = await medApi('emergency'); } catch (e) { showError(preview, e); return; }
    fill(preview, cardSheet(c));
    warn.hidden = !overflowing(preview);
    drawAbout(); drawFrom(); drawPeople(); drawDocs();
  }

  function drawAbout() {
    if (aboutCard.dataset.drawn) return;  // the fields keep what is being typed
    aboutCard.dataset.drawn = '1';
    const k = c.kept;
    const blood = h('select', { onchange: (e) => save({ bloodType: e.target.value }) }, BLOOD.map((b) => h('option', { value: b, selected: (k.bloodType || c.bloodType) === b }, b || 'Not said')));
    const donor = h('select', { onchange: (e) => save({ organDonor: e.target.value }) }, [['', 'Not said'], ['yes', 'Yes'], ['no', 'No']].map(([v, l]) => h('option', { value: v, selected: k.organDonor === v }, l)));
    const text = (key, ph) => h('textarea', { rows: 2, maxlength: 600, placeholder: ph, onchange: (e) => save({ [key]: e.target.value }) }, k[key]);
    aboutCard.append(...[h('div', { class: 'form' },
      h('div', { class: 'two' }, h('label', { class: 'fld' }, h('span', { class: 'fl' }, 'Blood type'), blood), h('label', { class: 'fld' }, h('span', { class: 'fl' }, 'Organ donor'), donor)),
      h('label', { class: 'fld' }, h('span', { class: 'fl' }, 'Conditions'), text('conditions', 'Type 2 diabetes, asthma, pacemaker')),
      h('label', { class: 'fld' }, h('span', { class: 'fl' }, 'Anything else'), text('notes', 'Wears contact lenses; speaks Dutch and English'))),
    c.person.born ? null : h('p', { class: 'small muted' }, 'Your date of birth comes from the Health app on your iPhone once it has synced.')].filter(Boolean));
  }

  function drawFrom() {
    fill(fromCard, h('h2', {}, 'From the Medicines page'),
      h('p', { class: 'small', style: { marginTop: 0 } }, `${c.allergies.length || 'No'} allerg${c.allergies.length === 1 ? 'y' : 'ies'} and ${c.medicines.length || 'no'} medicine${c.medicines.length === 1 ? '' : 's'} on the card. `,
        h('a', { href: '#/medicines' }, 'Change them →')),
      h('p', { class: 'small muted' }, 'A medicine you take goes on the card unless you untick “On my emergency card” on it.'));
  }

  // doctors and people to call, from ioContact
  function drawPeople() {
    const app = c.apps.iocontact;
    if (!app.on) { fill(peopleCard, h('h2', {}, 'Doctors and people to call'), empty('ioContact is not part of the suite: add it to put your doctor and the people to call on the card.')); return; }
    const problem = c.problems.find((p) => p.app === 'iocontact');
    fill(peopleCard, h('h2', {}, 'Doctors and people to call'),
      problem ? h('p', { class: 'error small' }, problem.message) : null,
      mine(), picked('Doctors', 'doctors', c.doctors), picked('In an emergency, call', 'contacts', c.contacts),
      h('p', { class: 'small muted' }, 'From ', app.url ? h('a', { href: app.url, target: '_blank', rel: 'noopener' }, 'ioContact') : 'ioContact', ': the name and first phone number of each contact you pick, and for the people to call what they are to you, where your own card there says so.'));
  }

  // which card in ioContact is the person themselves: their full name and what the people to call are to them come from it
  function mine() {
    const box = h('div', { class: 'picks' });
    const setMe = async (id) => { try { await medApi('emergency/me', { method: 'PUT', body: { contactId: id } }); } catch (e) { alertIn(peopleCard, e); return; } await load(); };
    box.append(h('h3', {}, 'You'));
    if (c.me) {
      box.append(h('div', { class: 'pick' }, h('span', {}, h('b', {}, c.me.name), h('span', { class: 'muted' }, ' · your own card in ioContact')),
        h('button', { class: 'small-btn', title: 'This card is not me', onclick: () => setMe(null) }, '×')));
      return box;
    }
    const results = h('div', { class: 'results' });
    let timer;
    const q = h('input', { type: 'search', placeholder: 'Find your own card…', oninput: () => { clearTimeout(timer); timer = setTimeout(find, 250); } });
    async function find() {
      if (!q.value.trim()) { fill(results); return; }
      try {
        const r = await medApi('emergency/contacts', { params: { q: q.value } });
        fill(results, ...(r.items.length ? r.items.slice(0, 8).map((x) => h('button', { class: 'result', onclick: () => setMe(x.id) },
          h('b', {}, x.name), x.org ? `, ${x.org}` : '', x.phone ? h('span', { class: 'muted' }, ` · ${x.phone}`) : '')) : [h('p', { class: 'small muted' }, 'No contact found.')]));
      } catch (e) { fill(results, h('p', { class: 'error small' }, e.message)); }
    }
    box.append(h('p', { class: 'small muted' }, 'Pick your own card in ioContact: the card then carries your full name, and says what each person to call is to you (wife, son) from the relations on it.'), q, results);
    return box;
  }

  function picked(title, key, items) {
    const ids = c.kept[key];
    const box = h('div', { class: 'picks' });
    box.append(h('h3', {}, title), ...items.map((x) => h('div', { class: 'pick' + (x.found ? '' : ' gone') },
      x.found ? h('span', {}, h('b', {}, x.name), x.org ? `, ${x.org}` : '', x.relation ? `, ${x.relation.toLowerCase()}` : '', x.phone ? h('span', { class: 'muted' }, ` · ${x.phone}`) : h('span', { class: 'muted' }, ' · no phone number'))
        : h('span', { class: 'muted' }, x.found === false ? 'A contact you no longer see in ioContact' : 'ioContact did not answer'),
      h('button', { class: 'small-btn', title: 'Take it off the card', onclick: () => save({ [key]: ids.filter((i) => i !== x.id) }) }, '×'))));
    if (ids.length < MAX) {
      const results = h('div', { class: 'results' });
      let timer;
      const q = h('input', { type: 'search', placeholder: 'Find a contact…', oninput: () => { clearTimeout(timer); timer = setTimeout(find, 250); } });
      async function find() {
        if (!q.value.trim()) { fill(results, ); return; }
        try {
          const r = await medApi('emergency/contacts', { params: { q: q.value } });
          fill(results, ...(r.items.length ? r.items.filter((x) => !ids.includes(x.id)).slice(0, 8).map((x) => h('button', { class: 'result', onclick: () => save({ [key]: [...ids, x.id] }) },
            h('b', {}, x.name), x.org ? `, ${x.org}` : '', x.phone ? h('span', { class: 'muted' }, ` · ${x.phone}`) : '')) : [h('p', { class: 'small muted' }, 'No contact found.')]));
        } catch (e) { fill(results, h('p', { class: 'error small' }, e.message)); }
      }
      box.append(q, results);
    }
    return box;
  }

  // insurance, from ioDocs
  async function drawDocs() {
    const app = c.apps.iodocs;
    if (!app.on) { fill(docsCard, h('h2', {}, 'Insurance'), empty('ioDocs is not part of the suite: add it to put your health insurance on the card.')); return; }
    const ids = c.kept.documents;
    const problem = c.problems.find((p) => p.app === 'iodocs');
    const list = h('div', { class: 'picks' }, h('p', { class: 'muted small' }, 'Loading your papers…'));
    fill(docsCard, h('h2', {}, 'Insurance'), problem ? h('p', { class: 'error small' }, problem.message) : null, list,
      h('p', { class: 'small muted' }, 'Your papers in ', app.url ? h('a', { href: app.url, target: '_blank', rel: 'noopener' }, 'ioDocs') : 'ioDocs', ', health insurance first. The card shows the insurer, the number and the first details of each one you tick.'));
    let items;
    try { items = (await medApi('emergency/documents')).items; } catch (e) { fill(list, h('p', { class: 'error small' }, e.message)); return; }
    const gone = c.documents.filter((d) => !d.found && !items.some((x) => x.id === d.id));
    fill(list, 
      ...(items.length ? items.map((d) => h('label', { class: 'row check pickdoc' }, h('input', { type: 'checkbox', checked: ids.includes(d.id), disabled: !ids.includes(d.id) && ids.length >= MAX,
        onchange: (e) => save({ documents: e.target.checked ? [...ids, d.id] : ids.filter((i) => i !== d.id) }) }),
        h('span', {}, h('b', {}, d.title), h('span', { class: 'muted' }, [d.issuer, d.number].filter(Boolean).length ? ` · ${[d.issuer, d.number].filter(Boolean).join(' · ')}` : '')),
        d.suggested ? h('span', { class: 'badge' }, 'health') : null)) : [h('p', { class: 'small muted' }, 'No papers of yours in ioDocs yet.')]),
      ...gone.map((d) => h('div', { class: 'pick gone' }, h('span', { class: 'muted' }, 'A paper you no longer see in ioDocs'),
        h('button', { class: 'small-btn', onclick: () => save({ documents: ids.filter((i) => i !== d.id) }) }, '×'))));
  }

  function alertIn(el, e) { el.append(h('p', { class: 'error small' }, e.message)); }
  load();
};

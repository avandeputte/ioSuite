/* When a thing shows: a rule on a tile, a card, a block, a section, a badge or a page (iostart/layout.py _when). */
import { dialog } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, S } from './core.js';

// ------------------------------------------------------------------ a rule: the screen, the hour, the day, a Home Assistant state
/* {screen: [phone|tablet|wide], from: "HH:MM", to: "HH:MM", days: [0-6, Sunday 0], content: true, ha: {id, state, not}}.
   Every part it names must hold. "content" (only while it has something to say) is not decided here: the card itself
   says when it has nothing (core.js quiet), and whoever placed it keeps it off the page meanwhile. */
export const SCREENS = { phone: 'Phones', tablet: 'Tablets', wide: 'Wide screens' };
/** Which of the three this window is now: narrower than 640px, up to 1100px, wider. */
export const screenNow = () => (innerWidth < 640 ? 'phone' : innerWidth <= 1100 ? 'tablet' : 'wide');
const minutes = (hhmm) => +hhmm.slice(0, 2) * 60 + +hhmm.slice(3);
/** What Home Assistant says of an entity now, as far as the page knows (S.ha: the Home card's entities); null: unknown. */
const haState = (id) => { const t = S.ha && (S.ha.items || []).find((x) => x.id === id); return t ? String(t.state) : null; };

/** Whether the rule holds right now. A state the page cannot know (Home Assistant away, an entity no longer picked)
    counts as not holding, so the thing stays off rather than showing when it should not. */
export function whenOk(w, now = new Date()) {
  if (!w) return true;
  if (w.screen && !w.screen.includes(screenNow())) return false;
  if (w.days && !w.days.includes(now.getDay())) return false;
  if (w.from && w.to) {
    const t = now.getHours() * 60 + now.getMinutes(), a = minutes(w.from), b = minutes(w.to);
    if (a < b ? t < a || t >= b : t >= b && t < a) return false;  // the earlier `to`: through the night
  }
  if (w.ha) {
    const st = haState(w.ha.id);
    if (st == null || (st === w.ha.state) === !!w.ha.not) return false;
  }
  return true;
}
/** Whether a rule looks at Home Assistant (then the page listens to it). */
export const usesHa = (w) => !!(w && w.ha);

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const clock = (hhmm) => { const d = new Date(); d.setHours(+hhmm.slice(0, 2), +hhmm.slice(3), 0, 0); return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); };
function daysText(days) {
  const s = days.join('');
  if (s === '12345') return 'weekdays';
  if (s === '06') return 'weekends';
  // a run of days in a row as "Mon to Thu", else each by name
  const run = days.every((d, i) => !i || d === days[i - 1] + 1);
  return run && days.length > 2 ? `${DAYS[days[0]]} to ${DAYS[days.at(-1)]}` : days.map((d) => DAYS[d]).join(', ');
}
/** A rule in a few words: "Phones · weekdays · 6:00 AM to 9:00 AM · only with something to show". '' for none. */
export function whenText(w) {
  if (!w) return '';
  const ha = w.ha && (((S.ha && S.ha.items) || []).find((x) => x.id === w.ha.id) || { name: w.ha.id });
  return [w.screen ? w.screen.map((k) => SCREENS[k]).join(' and ') : null, w.days ? daysText(w.days) : null,
    w.from ? `${clock(w.from)} to ${clock(w.to)}` : null, w.content ? 'only with something to show' : null,
    ha ? `while ${ha.name} is ${w.ha.not ? 'not ' : ''}${w.ha.state}` : null].filter(Boolean).join(' · ');
}

/** The dialog that sets a rule. Resolves with {when: the rule, or null for always}, or undefined when put away.
    content: whether "only while it has something to show" makes sense for the thing. */
export async function whenDialog(name, w, { content = true } = {}) {
  w = w || {};
  const screens = Object.entries(SCREENS).map(([k, t]) => ({ k, t, box: h('input', { type: 'checkbox', checked: !w.screen || w.screen.includes(k) }) }));
  const days = DAYS.map((t, d) => ({ d, box: h('button', { class: !w.days || w.days.includes(d) ? 'on' : '', 'aria-pressed': String(!w.days || w.days.includes(d)), onclick: (e) => { const on = !e.currentTarget.classList.contains('on'); e.currentTarget.classList.toggle('on', on); e.currentTarget.setAttribute('aria-pressed', String(on)); } }, t) }));
  const from = h('input', { class: 't', type: 'time', value: w.from || '', 'aria-label': 'From' }), to = h('input', { class: 't', type: 'time', value: w.to || '', 'aria-label': 'To' });
  const some = h('input', { type: 'checkbox', checked: !!w.content });
  // a Home Assistant state: one of the entities an admin picked for the page (the only ones the page is told about)
  let ha = S.ha;
  if (ha == null) { try { const d = await api('api/ha'); ha = S.ha = d.enabled ? d : false; } catch { ha = false; } }
  const items = (ha && ha.items) || [];
  const known = !w.ha || items.some((x) => x.id === w.ha.id);
  const entity = h('select', { class: 't' }, h('option', { value: '' }, 'Whatever Home Assistant says'), items.map((x) => h('option', { value: x.id, selected: w.ha && w.ha.id === x.id ? true : null }, x.name)),
    known ? null : h('option', { value: w.ha.id, selected: true }, `${w.ha.id} (no longer picked)`));
  const is = h('select', { class: 't' }, h('option', { value: '' }, 'is'), h('option', { value: 'not', selected: w.ha && w.ha.not ? true : null }, 'is not'));
  const state = h('input', { class: 't', value: (w.ha && w.ha.state) || 'on', maxlength: 40, placeholder: 'on', 'aria-label': 'State', list: 'whenstates' });
  const states = h('datalist', { id: 'whenstates' });
  const haRow = h('div', { class: 'whenha' }, entity, is, state, states);
  const haDraw = () => {
    const t = items.find((x) => x.id === entity.value);
    is.hidden = state.hidden = !entity.value;
    states.replaceChildren(...[...new Set([t && t.state, 'on', 'off', 'home', 'not_home', 'open', 'closed', 'locked', 'unlocked'].filter(Boolean))].map((v) => h('option', { value: v })));
    if (t && !w.ha) state.title = `It says “${t.state}” now`;
  };
  entity.onchange = haDraw; haDraw();
  const body = h('div', { class: 'whenform' },
    h('p', { class: 'muted small' }, 'It shows when everything set here holds. Left as it comes, a part rules nothing out.'),
    h('h3', null, 'On'), h('div', { class: 'whenrow' }, screens.map((s) => h('label', { class: 'check' }, s.box, s.t))),
    h('h3', null, 'On these days'), h('div', { class: 'seg whendays' }, days.map((d) => d.box)),
    h('h3', null, 'Between'), h('div', { class: 'whenrow' }, from, h('span', { class: 'muted' }, 'and'), to, h('button', { class: 'lnk small', onclick: () => { from.value = ''; to.value = ''; } }, 'All day')),
    content ? [h('h3', null, 'And'), h('label', { class: 'check' }, some, 'Only while it has something to show')] : null,
    items.length || w.ha ? [h('h3', null, 'While, in Home Assistant'), haRow] : null);
  const read = () => {
    const out = {}, sc = screens.filter((s) => s.box.checked).map((s) => s.k), ds = days.filter((d) => d.box.classList.contains('on')).map((d) => d.d);
    if (!sc.length) throw new Error('Tick at least one kind of screen');
    if (!ds.length) throw new Error('Pick at least one day');
    if (!!from.value !== !!to.value) throw new Error('A time to start and a time to end, or neither');
    if (from.value && from.value === to.value) throw new Error('Two different times, please');
    if (sc.length < screens.length) out.screen = sc;
    if (ds.length < 7) out.days = ds;
    if (from.value) { out.from = from.value.slice(0, 5); out.to = to.value.slice(0, 5); }
    if (content && some.checked) out.content = true;
    if (entity.value) out.ha = { id: entity.value, state: state.value.trim() || 'on', ...(is.value ? { not: true } : {}) };
    return { when: Object.keys(out).length ? out : null };
  };
  return (await dialog(`When ${name} shows`, body, [{ label: 'Always', value: () => ({ when: null }) }, { label: 'Cancel', value: () => null }, { label: 'Done', value: read, primary: true }], '', { wait: true })) || undefined;
}

/* Who added an item and who changed it, the same in every io app: one quiet line under the item ("Added by Alex with
   the web page (Safari on Mac) · Nov 21, 9:14 PM · changed by Sam with CalDAV (iPhone) yesterday, 8:02 AM") and, behind
   it, the item's last changes. It talks to /api/changes/* next to it (iosuite_shared.stamp), which answers only to
   whoever may see the item. The "Linked" panel (related-panel.js) mounts it under itself, so every item with that
   panel has it; an app can mount it on its own too:

     const ch = await import(new URL('api/changes/ui.js', document.baseURI).href);
     const line = ch.mount(el, { kind: 'event', id: 12 });   // draws into el (nothing while nothing is recorded)
     line.reload();                                           // after the app saved the item
*/
import { h, api, styles as kitStyles } from '../auth/ui.js';

const CSS = `
.iosv.ch { margin: 14px 0 0; font-size: 12px; color: var(--sv-fg2); line-height: 1.45; }
.iosv.ch:empty { display: none; }
.iosv .ch-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px; }
.iosv .ch-line > span { min-width: 0; overflow-wrap: anywhere; }
.iosv .ch-more { font: inherit; font-size: 12px; border: 0; background: none; color: var(--sv-accent); cursor: pointer; padding: 0; }
.iosv .ch-more:hover { text-decoration: underline; }
.iosv .ch-list { list-style: none; margin: 8px 0 0; padding: 0 0 0 10px; border-left: 2px solid var(--sv-line); display: flex; flex-direction: column; gap: 6px; }
.iosv .ch-list li { overflow-wrap: anywhere; }
.iosv .ch-list b { font-weight: 600; color: var(--sv-fg); }
.iosv .ch-when { white-space: nowrap; }
`;
function styles() {
  kitStyles();
  if (document.getElementById('iosv-ch-css')) return;
  document.head.append(h('style', { id: 'iosv-ch-css' }, CSS));
}

/** "9:14 PM" today, "yesterday, 9:14 PM", "Nov 21, 9:14 PM" this year, "Nov 21, 2025" before. */
export function when(sec) {
  const d = new Date(sec * 1000), now = new Date();
  const time = d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff === 0) return `today, ${time}`;
  if (diff === 1) return `yesterday, ${time}`;
  if (d.getFullYear() === now.getFullYear()) return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}, ${time}`;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

const WORD = { added: 'Added', changed: 'Changed', deleted: 'Deleted' };
const by = (x) => x.by || (x.client === 'auto' || x.client === 'sync' ? '' : 'someone');
const said = (verb, x) => [verb, by(x) ? ` by ${by(x)}` : '', x.how ? ` with ${x.how}` : ''].join('');

export function mount(el, opts = {}) {
  styles();
  const { kind, id } = opts;
  let rec = null, open = false;
  el.classList.add('iosv', 'ch');
  const draw = () => {
    el.replaceChildren();
    if (!rec || (!rec.added && !rec.changed && !(rec.history || []).length)) return;
    const parts = [];
    if (rec.added) parts.push(h('span', null, said('Added', rec.added), ' · ', h('span', { class: 'ch-when' }, when(rec.added.at))));
    if (rec.changed && !(rec.added && rec.changed.at === rec.added.at)) {
      parts.push(h('span', null, said(rec.added ? 'Changed' : 'Last changed', rec.changed), ' · ', h('span', { class: 'ch-when' }, when(rec.changed.at))));
    }
    const hist = rec.history || [];
    if (hist.length > 1 || (hist.length && !parts.length)) {
      parts.push(h('button', { class: 'ch-more', type: 'button', 'aria-expanded': String(open), onclick: () => { open = !open; draw(); } },
        open ? 'Hide history' : `History (${hist.length})`));
    }
    el.append(h('div', { class: 'ch-line' }, parts));
    if (open) {
      el.append(h('ul', { class: 'ch-list' }, hist.map((x) => h('li', null,
        h('b', null, WORD[x.action] || x.action), x.what ? ` (${x.what})` : '', by(x) ? ` by ${by(x)}` : '', x.how ? ` with ${x.how}` : '',
        x.from ? `, ${x.from}` : '', ' · ', h('span', { class: 'ch-when' }, when(x.at))))));
    }
  };
  const load = async () => {
    if (kind == null || id == null || id === '') { rec = null; draw(); return; }
    try { rec = await api(`changes/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`); } catch { rec = null; }
    draw();
  };
  load();
  return { reload: load };
}

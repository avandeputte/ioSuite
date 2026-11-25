/* What every part of the page uses: the helpers (api, $, the icons), the app's state (S), numbers and dates, a
   labelled field, and the sign-in screen. It takes nothing from the other modules, so it is ready before any of them. */
import * as frame from '../../api/auth/frame.js';
import { addIcons, icon, toast } from '../../api/auth/frame.js';
import { client, h } from '../../api/auth/ui.js';

export const api = client(document.baseURI, { signIn: () => showSignIn() });

// ------------------------------------------------------------------ helpers
export const $ = (s, el = document) => el.querySelector(s);
addIcons({
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  pie: 'M11 2v20c-5.07-.5-9-4.79-9-10s3.93-9.5 9-10zm2.03 0v8.99H22c-.47-4.74-4.24-8.52-8.97-8.99zm0 11.01V22c4.74-.47 8.5-4.25 8.97-8.99h-8.97z',
  trend: 'M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z',
  car: 'M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z',
  bank: 'M4 10v7h3v-7H4zm6 0v7h3v-7h-3zM2 22h19v-3H2v3zm14-12v7h3v-7h-3zm-4.5-9L2 6v2h19V6l-9.5-5z',
  card: 'M20 4H4c-1.11 0-1.99.89-1.99 2L2 18c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z',
  attach: 'M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5a2.5 2.5 0 0 1 5 0v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5a2.5 2.5 0 0 0 5 0V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z',
  split: 'M14 4l2.29 2.29-2.88 2.88 1.42 1.42 2.88-2.88L20 10V4h-6zm-4 0H4v6l2.29-2.29 4.71 4.7V20h2v-8.41l-5.29-5.3L10 4z',
  loan: 'M19 14V6c0-1.1-.9-2-2-2H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zm-9-1c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm13-6v11c0 1.1-.9 2-2 2H4v-2h17V7h2z',
  gem: 'M12 2 2 9l10 13L22 9 12 2zm0 3.2L18.6 9H5.4L12 5.2z',
  sync: 'M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z',
  warning: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z',
  play: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z',
  repeat: 'M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z',
  eye: 'M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z',
  tidy: 'M20 3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM10 17H5v-2h5v2zm0-4H5v-2h5v2zm0-4H5V7h5v2zm4.82 6L12 12.16l1.41-1.41 1.41 1.42L17.99 9l1.42 1.42L14.82 15z',
  label: 'M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z',
  undo: 'M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z',
  store: 'M20 4H4v2h16V4zm1 10v-2l-1-5H4l-1 5v2h1v6h10v-6h4v6h2v-6h1zm-9 4H6v-4h6v4z',
  bookmark: 'M17 3H7c-1.1 0-1.99.9-1.99 2L5 21l7-3 7 3V5c0-1.1-.9-2-2-2z',
  scale: 'M13 7.83c.85-.3 1.53-.98 1.83-1.83H18l-3 7c0 1.66 1.57 3 3.5 3s3.5-1.34 3.5-3l-3-7h2V4h-6.17c-.41-1.17-1.52-2-2.83-2s-2.42.83-2.83 2H3v2h2l-3 7c0 1.66 1.57 3 3.5 3S9 14.66 9 13L6 6h3.17c.3.85.98 1.53 1.83 1.83V19H2v2h20v-2h-9V7.83zM20.37 13h-3.74l1.87-4.36L20.37 13zm-13 0H3.63L5.5 8.64 7.37 13zM12 6c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1z',
  doneAll: 'M18 7l-1.41-1.41-6.34 6.34 1.41 1.41L18 7zm4.24-1.41L11.66 16.17 7.48 12l-1.41 1.41L11.66 19l12-12-1.42-1.41zM.41 13.41L6 19l1.41-1.41L1.83 12 .41 13.41z',
  phone: 'M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z',
});

export const store = frame.storeFor('iomoney');
let related = null;
/** The suite's Linked panel (api/related/ui.js), fetched the first time one is shown. */
export async function linkUi() { return (related = related || await import(new URL('api/related/ui.js', document.baseURI).href)); }

// ------------------------------------------------------------------ state
export const S = { status: {}, user: null, suite: [], settings: {}, sum: null, accounts: [], cats: [], searches: [], tags: null };
export const may = (k) => !!(S.sum && S.sum.may && S.sum.may[k]);
export const canAdd = () => may('own') || may('household');
export const CUR = () => (S.sum && S.sum.currency) || 'USD';

// ------------------------------------------------------------------ numbers and dates
export const fmts = {};
/** An amount in a currency, as the browser's language writes it: $1,234.50, -€12.00. */
export function money(v, cur = CUR(), opts = {}) {
  if (v == null || Number.isNaN(+v)) return '—';
  const key = `${cur}:${opts.whole ? 1 : 0}:${opts.sign ? 1 : 0}`;
  try {
    fmts[key] = fmts[key] || new Intl.NumberFormat(undefined, { style: 'currency', currency: cur, minimumFractionDigits: opts.whole ? 0 : 2, maximumFractionDigits: opts.whole ? 0 : 2, signDisplay: opts.sign ? 'exceptZero' : 'auto' });
    return fmts[key].format(+v);
  } catch { return `${(+v).toFixed(opts.whole ? 0 : 2)} ${cur}`; }
}
export const pct = (v, sign = true) => (v == null ? '' : `${sign && v > 0 ? '+' : ''}${(+v).toFixed(2)}%`);
export const qty = (v) => (v == null ? '' : (+v).toLocaleString(undefined, { maximumFractionDigits: 6 }));
export const tone = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
export const amt = (v, cur, opts) => h('span', { class: `num ${opts && opts.plain ? '' : tone(v)}` }, money(v, cur, opts));
export const today = () => new Date().toLocaleDateString('sv');  // YYYY-MM-DD in the viewer's time zone
export const thisMonth = () => today().slice(0, 7);
export const dateOf = (s) => new Date(`${s}T12:00:00`);
export const fmtDay = (s, long = false) => (s ? dateOf(s).toLocaleDateString(undefined, long ? { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' } : { day: 'numeric', month: 'short' }) : '');
export const fmtMonth = (m) => new Date(`${m}-15T12:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
export const shiftMonth = (m, n) => { const d = new Date(`${m}-15T12:00:00`); d.setMonth(d.getMonth() + n); return d.toISOString().slice(0, 7); };
export const ago = (iso) => {
  if (!iso) return 'never';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  return s < 90 ? 'just now' : s < 5400 ? `${Math.round(s / 60)} minutes ago` : s < 129600 ? `${Math.round(s / 3600)} hours ago` : `${Math.round(s / 86400)} days ago`;
};

// the kinds of accounts: icon and colour
export const KIND_LOOK = { cash: ['bank', '--c-green'], investment: ['trend', '--c-indigo'], property: ['home', '--c-orange'], vehicle: ['car', '--c-teal'],
  other_asset: ['gem', '--c-purple'], credit: ['card', '--c-rose'], loan: ['loan', '--c-amber'], other_liability: ['loan', '--c-slate'] };
export const kindLabel = (k) => ((S.sum && S.sum.kinds) || []).find((x) => x.kind === k)?.label || k;
/* The accounts are shown in five groups, in this order: Cash, Investments, Credit cards, Loans, Assets (the house, the
   cars, other things of value). The names and the kinds in each come from the server (api/summary). */
export const GROUP_LOOK = { cash: ['bank', '--c-green'], investment: ['trend', '--c-indigo'], credit: ['card', '--c-rose'], loan: ['loan', '--c-amber'], asset: ['home', '--c-orange'] };
export const groups = () => (S.sum && S.sum.groups) || [];
export const byGroup = (accts) => groups().map((g) => ({ ...g, list: accts.filter((a) => g.kinds.includes(a.kind)) })).filter((g) => g.list.length);
export const followsTx = (a) => a.track === 'transactions';
export const THINGS = ['property', 'vehicle', 'other_asset'];
export const HOLDING_LABEL = { stock: 'Stocks', etf: 'ETFs', fund: 'Funds', bond: 'Bonds', crypto: 'Crypto', cash: 'Cash', option: 'Options', other: 'Other' };

// ------------------------------------------------------------------ sign-in
export function showSignIn() { frame.signInScreen({ api, name: 'Money', first: !S.status.usersExist }); }

// ------------------------------------------------------------------ a labelled field, text to the clipboard
export async function copyText(v) { try { await navigator.clipboard.writeText(v); toast('Copied'); } catch { toast('Could not copy'); } }

export const fld = (l, e, wide) => h('label', { class: `field ${wide ? 'wide' : ''}` }, h('span', null, l), e);
export const inp = (v, attrs = {}) => h('input', { class: 't', value: v == null ? '' : v, ...attrs });

// ------------------------------------------------------------------ an account whose bank has not answered for a while
/** An account whose link to its bank Monarch Money reports as cut, needing its sign-in fixed or over two days behind:
    a warning mark (with why) on its row. */
export const behind = (a) => (a.bank && a.bank.stale ? a.bank : null);
export function behindMark(el, a) {
  const b = behind(a);
  if (b) { el.classList.add('behind'); el.title = `${a.name}: ${b.why}`; el.append(h('span', { class: 'bwarn', 'aria-label': b.why }, icon('warning', 'xs'))); }
  return el;
}
export function behindText(b) {
  if (b.stale === 'disconnected') return `Monarch Money's link to the bank was cut${b.disconnectedAt ? ` ${ago(b.disconnectedAt)}` : ''}`;
  if (b.stale === 'update') return 'Monarch Money needs the bank sign-in fixed';
  return `Monarch Money last heard from the bank ${ago(b.refreshedAt)}`;
}

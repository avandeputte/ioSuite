/* The account panels, the same in every io app, and the small kit the Server panel shares (h, api, the styles):
   Settings › Account (display name, email, password), the Appearance and Units rows of Settings › Display, and the
   signed-in account's own app passwords (below it on Settings › Account). They talk to /api/auth/* next to them.

     const ui = await import(new URL('api/auth/ui.js', document.baseURI).href);
     await ui.mountAccount(el, { toast });                         // Settings › Account
     el.append(ui.themeRow(frame.themeChoice(), frame.applyTheme));  // the suite's one appearance choice
     el.append(ui.unitsRow(current, (k) => applyUnits(k)));         // 'auto' | 'metric' | 'imperial'
     await ui.mountAppPasswords(el, { toast, syncOnly: 'Calendar apps only (CalDAV)' });
     await ui.mountNotifications(el, { toast });                   // also part of mountAccount: this device, what to get
     await ui.mountFeeds(el, { toast, title, intro });             // the app's subscription links (/api/feeds), each shown once
     await ui.signIn({ name, password });                           // the sign-in screen: asks for the two-step code when the account has it on
     el.append(ui.passkeyButton((me) => location.reload()));        // "Sign in with a passkey", shown only where somebody has one

   Settings › Account also offers the account's own estate planning PDF (downloadEstate, which the Suite admin panel
   uses for anyone).

   ui.box(icon, title, ...kids) and ui.row(label, hint, control) build the app's own boxes in the same look.
*/
const API = new URL('../', import.meta.url);   // .../api/

export const ICONS = {
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  log: 'M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
  restart: 'M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  key: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  theme: 'M12 3a9 9 0 1 0 0 18c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01-.23-.26-.38-.61-.38-.99 0-.83.67-1.5 1.5-1.5H16c2.76 0 5-2.24 5-5 0-4.42-4.03-8-9-8zm-5.5 9c-.83 0-1.5-.67-1.5-1.5S5.67 9 6.5 9 8 9.67 8 10.5 7.33 12 6.5 12zm3-4C8.67 8 8 7.33 8 6.5S8.67 5 9.5 5s1.5.67 1.5 1.5S10.33 8 9.5 8zm5 0c-.83 0-1.5-.67-1.5-1.5S13.67 5 14.5 5s1.5.67 1.5 1.5S15.33 8 14.5 8zm3 4c-.83 0-1.5-.67-1.5-1.5S16.67 9 17.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z',
  devices: 'M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  shield: 'M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z',
  bell: 'M12 22c1.1 0 2-.9 2-2h-4a2 2 0 0 0 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z',
};
export const icon = (n) => { const s = document.createElement('span'); s.className = 'sv-ic'; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith('--')) el.style.setProperty(sk, sv); else el.style[sk] = sv; }
    else if (k === 'checked') el.checked = !!v;
    else if (k === 'value') el.value = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (k) => { if (k == null || k === false) return; if (Array.isArray(k)) k.forEach(add); else el.append(k instanceof Node ? k : String(k)); };
  kids.forEach(add);
  return el;
}

/* fetch relative to `base`: { json } is sent as a JSON body (POST unless a method is given), an error answer throws its
   detail, a JSON answer comes back parsed and anything else as text. The panels make theirs with
   client(new URL('./', import.meta.url)); an app's page with client(document.baseURI, { signIn }), where signIn shows
   its sign-in screen when a request other than api/status or api/auth/… is answered 401. */
export function client(base, { signIn } = {}) {
  return async (path, opts = {}) => {
    const o = { credentials: 'same-origin', ...opts, headers: { ...(opts.headers || {}) } };
    if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers['Content-Type'] = 'application/json'; o.method = o.method || 'POST'; delete o.json; }
    const r = await fetch(new URL(path, base), o);
    if (r.status === 401 && signIn && !String(path).startsWith('api/auth') && path !== 'api/status') { signIn(); throw new Error('Sign in first'); }
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : (j.error || JSON.stringify(j.detail)); } catch { /* not JSON */ }
      throw new Error(msg || `Error ${r.status}`);
    }
    return (r.headers.get('content-type') || '').includes('json') ? r.json() : r.text();
  };
}
export const api = client(API);

export const safeUrl = (u) => /^(https?:\/\/|mailto:)/i.test(u || '');  // a link that is a link (never javascript:)

/* The "Set up" choice of an Apple profile form: this app only, or every app that syncs (iosuite_shared's suite profile),
   offered when the account may use two or more of them (null otherwise). Picking one points the form at the profile
   it downloads and hides the fields marked data-own, which only this app's own profile has. */
export function profileScope(apps, own, attrs = {}) {
  if (!apps || apps.length < 2) return null;
  const names = apps.map((a) => a.name);
  const pick = (e) => {
    const f = e.target.form, all = e.target.value === 'suite';
    f.action = all ? 'api/apple-profile/suite' : 'api/apple-profile';
    f.querySelectorAll('[data-own]').forEach((x) => { x.hidden = all; });
  };
  return h('select', { ...attrs, name: 'scope', onchange: pick },
    h('option', { value: 'app' }, `${own} only`),
    h('option', { value: 'suite' }, `All apps: ${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`));
}

// ------------------------------------------------------------------ styles (once per page)
const CSS = `
.iosv, .iosv-back { --sv-fg: var(--fg, var(--text, #202124)); --sv-fg2: var(--fg2, var(--muted, #5f6368)); --sv-line: var(--line, #dadce0);
  --sv-bg: var(--card, var(--bg, #fff)); --sv-bg2: var(--bg2, color-mix(in srgb, var(--sv-fg) 7%, var(--sv-bg)));
  --sv-accent: var(--accent, var(--link, #1a73e8)); --sv-accent-bg: var(--accent-bg, color-mix(in srgb, var(--sv-accent) 14%, transparent));
  --sv-brand: var(--brand, var(--sv-accent)); --sv-danger: var(--danger, #d93025); color: var(--sv-fg); font-size: 14px; line-height: 1.45; }
.iosv *, .iosv-back * { box-sizing: border-box; }
.iosv .sv-ic { display: inline-flex; width: 20px; height: 20px; flex: none; }
.iosv .sv-ic svg { width: 100%; height: 100%; fill: currentColor; }
.iosv .sv-muted { color: var(--sv-fg2); }
.iosv .sv-small { font-size: 12px; }
.iosv .sv-warn { color: var(--sv-danger); }
.iosv .sv-box { border: 1px solid var(--sv-line); border-radius: 16px; padding: 16px 20px; margin-bottom: 16px; background: var(--card, transparent); }
.iosv .sv-box h2 { margin: 0 0 6px; font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.iosv .sv-box h2 .sv-ic { color: var(--sv-brand); }
.iosv .sv-box p { margin: 6px 0; }
.iosv a { color: var(--sv-accent); }
.iosv .sv-kv { display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--sv-line); }
.iosv .sv-kv:last-of-type { border-bottom: 0; }
.iosv .sv-kv > span:first-child { flex: 0 0 140px; color: var(--sv-fg2); }
.iosv .sv-kv > span:last-child { min-width: 0; overflow-wrap: anywhere; }
.iosv .sv-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
.iosv .sv-in { font: inherit; color: inherit; height: 36px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--sv-line); background: var(--sv-bg); min-width: 0; margin: 0; }
.iosv input.sv-in { flex: 1; max-width: 240px; }
.iosv .sv-btn, .iosv-back .sv-btn { font: inherit; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px; border-radius: 999px; color: var(--sv-fg2);
  border: 1px solid var(--sv-line); background: none; cursor: pointer; flex: none; white-space: nowrap; text-decoration: none; }
.iosv .sv-btn .sv-ic { width: 18px; height: 18px; margin-left: -4px; }
.iosv .sv-btn:hover, .iosv-back .sv-btn:hover { background: var(--sv-accent-bg); color: var(--sv-accent); border-color: transparent; }
.iosv .sv-btn.primary, .iosv-back .sv-btn.primary { background: var(--sv-brand); color: #fff; border-color: transparent; }
.iosv .sv-btn[disabled] { opacity: .5; pointer-events: none; }
.iosv label.sv-check { display: flex; gap: 8px; align-items: flex-start; margin: 6px 0; }
.iosv label.sv-check input { margin-top: 3px; accent-color: var(--sv-brand); }
.iosv pre.sv-log { font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--sv-bg2);
  border-radius: 8px; padding: 10px 12px; margin: 8px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.iosv-back { position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 16px; }
.iosv-back .sv-dialog { background: var(--sv-bg); border-radius: 16px; padding: 20px 22px; width: 100%; max-width: 460px; box-shadow: 0 2px 12px rgba(0,0,0,.4); }
.iosv-back .sv-dialog h2 { margin: 0 0 10px; font-size: 18px; font-weight: 500; }
.iosv-back .sv-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
.iosv-back.sv-top { z-index: 5000; }
.iosv-back .sv-dialog p { margin: 6px 0; }
.iosv-back .sv-dialog .sv-in { width: 100%; max-width: none; margin: 6px 0; }
.iosv-back .sv-dialog .sv-err { color: var(--sv-danger); min-height: 1.3em; font-size: 13px; }
.iosv-back .sv-qr { display: flex; justify-content: center; margin: 10px 0; }
.iosv-back .sv-qr svg { width: 190px; height: 190px; border-radius: 8px; }
.iosv-back .sv-codes { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font: 14px ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--sv-bg2); border-radius: 8px; padding: 12px 16px; margin: 10px 0; user-select: all; }
.iosv.sv-passkey { margin: 10px 0 0; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.iosv.sv-passkey[hidden] { display: none; }
.iosv-toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: #323232; color: #fff; padding: 12px 18px; border-radius: 8px; z-index: 1001; font-size: 14px; max-width: calc(100vw - 32px); }
/* settings rows (label and hint on the left, the control on the right), segmented choices, tables */
.iosv .sv-srow { display: flex; gap: 16px; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--sv-line); flex-wrap: wrap; }
.iosv .sv-srow:last-child { border-bottom: 0; }
.iosv .sv-srow > div:first-child { min-width: 200px; flex: 1; }
.iosv .sv-seg { display: inline-flex; border: 1px solid var(--sv-line); border-radius: 999px; overflow: hidden; }
.iosv .sv-seg button { font: inherit; border: 0; background: none; color: var(--sv-fg2); padding: 6px 14px; cursor: pointer; }
.iosv .sv-seg button + button { border-left: 1px solid var(--sv-line); }
.iosv .sv-seg button.on { background: var(--sv-accent-bg); color: var(--sv-accent); }
.iosv .sv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px 16px; margin: 8px 0; }
.iosv label.sv-field { display: flex; flex-direction: column; gap: 4px; }
.iosv label.sv-field > span { font-size: 12px; color: var(--sv-fg2); }
.iosv label.sv-field input.sv-in { max-width: none; flex: none; }
.iosv table.sv-t { width: 100%; border-collapse: collapse; margin: 8px 0; }
.iosv table.sv-t th, .iosv table.sv-t td { text-align: left; padding: 6px 8px 6px 0; border-bottom: 1px solid var(--sv-line); font-size: 13px; }
.iosv table.sv-t th { color: var(--sv-fg2); font-weight: 500; }
.iosv code.sv-code { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--sv-bg2); padding: 4px 8px; border-radius: 6px; overflow-wrap: anywhere; user-select: all; }
@media (max-width: 560px) { .iosv .sv-kv { flex-direction: column; gap: 2px; } .iosv .sv-kv > span:first-child { flex: none; } }
`;
export function styles() {
  if (document.getElementById('iosv-css')) return;
  document.head.append(h('style', { id: 'iosv-css' }, CSS));
}

let toastTimer;
let showToast = (msg) => {
  let t = document.querySelector('.iosv-toast');
  if (!t) { t = h('div', { class: 'iosv-toast', role: 'status' }); document.body.append(t); }
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
};
/** The app's own toast, when it passes one (mount(el, {toast})); else the panels' own. */
export const setToast = (fn) => { if (fn) showToast = fn; };
export const toast = (msg) => showToast(msg);
export const fail = (e) => toast(e.message || String(e));

export function confirmDialog(title, text, ok) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'iosv-back iosv' });
    const close = (v) => { back.remove(); removeEventListener('keydown', esc); resolve(v); };
    const esc = (e) => { if (e.key === 'Escape') close(false); };
    addEventListener('keydown', esc);
    back.addEventListener('click', (e) => { if (e.target === back) close(false); });
    back.append(h('div', { class: 'sv-dialog', role: 'dialog', 'aria-label': title }, h('h2', null, title), h('p', null, text),
      h('div', { class: 'sv-btns' }, h('button', { class: 'sv-btn', onclick: () => close(false) }, 'Cancel'),
        h('button', { class: 'sv-btn primary', onclick: () => close(true) }, ok))));
    document.body.append(back);
    back.querySelector('.primary').focus();
  });
}


/* A small dialog with fields: resolves with what ok() returns (ok may throw: the message is shown and the dialog
   stays), or null when closed. kids: the fields; top: above an app's own sign-in screen. */
function formDialog(title, kids, okLabel, ok, { top = false, cancel = 'Cancel' } = {}) {
  styles();
  return new Promise((resolve) => {
    const back = h('div', { class: `iosv-back iosv${top ? ' sv-top' : ''}` });
    const err = h('div', { class: 'sv-err', role: 'alert' });
    const close = (v) => { back.remove(); removeEventListener('keydown', esc, true); resolve(v); };
    const esc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(null); } };
    addEventListener('keydown', esc, true);
    const go = h('button', { class: 'sv-btn primary', type: 'submit' }, okLabel);
    const submit = async (e) => {
      e.preventDefault();
      go.disabled = true; err.textContent = '';
      try { const v = await ok(); if (v !== undefined) close(v); } catch (x) { err.textContent = x.message || String(x); } finally { go.disabled = false; }
    };
    back.append(h('form', { class: 'sv-dialog', role: 'dialog', 'aria-label': title, onsubmit: submit, onkeydown: (e) => e.stopPropagation() },
      h('h2', null, title), kids, err,
      h('div', { class: 'sv-btns' }, cancel ? h('button', { class: 'sv-btn', type: 'button', onclick: () => close(null) }, cancel) : null, go)));
    document.body.append(back);
    (back.querySelector('input') || go).focus();
  });
}

// ------------------------------------------------------------------ the sign-in screen (every app's own draws it)
/** Sign in with a name and password: POST api/auth/login. When the account has two-step sign-in on, a dialog asks
 *  for the code from the code app (or a recovery code) and the sign-in is sent again with it. Resolves with the
 *  answer ({user, settings}); throws an Error with the message to show. */
export async function signIn(body) {
  let code = '', said = '';
  for (;;) {
    const r = await fetch(new URL('auth/login', API), { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(code ? { ...body, code } : body) });
    const j = await r.json().catch(() => ({}));
    if (r.ok) return j;
    const msg = typeof j.detail === 'string' ? j.detail : (r.statusText || `Error ${r.status}`);
    if (!(r.status === 401 && j.twoStep)) throw new Error(msg);
    said = code ? msg : '';
    const inp = h('input', { class: 'sv-in', inputmode: 'numeric', autocomplete: 'one-time-code', placeholder: '6-digit code', 'aria-label': 'Code' });
    code = await formDialog('Two-step sign-in', [h('p', null, 'Enter the code from your code app.'), inp,
      said ? h('div', { class: 'sv-err' }, said) : null,
      h('p', { class: 'sv-muted sv-small' }, 'No phone at hand? Type one of your recovery codes instead.')],
    'Sign in', () => { const v = inp.value.trim(); if (!v) throw new Error('Type the code'); return v; }, { top: true });
    if (code == null) throw new Error('Sign-in needs the code');
  }
}

const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
/** Whether this browser can make and use passkeys here (they need an https page, or localhost). */
export const passkeysWork = () => !!(window.isSecureContext && window.PublicKeyCredential && navigator.credentials);

/** "Sign in with a passkey" for a sign-in screen: an element that stays hidden unless somebody has a passkey for
 *  this address and the browser can use one. done(me) is called once signed in (me: {user, settings}). */
export function passkeyButton(done) {
  styles();
  const err = h('div', { class: 'sv-warn sv-small', role: 'alert' });
  const btn = h('button', { type: 'button', class: 'sv-btn', onclick: async () => {
    btn.disabled = true; err.textContent = '';
    try {
      const o = await api('auth/login/passkey/begin', { json: {} });
      const c = await navigator.credentials.get({ publicKey: { challenge: fromB64u(o.challenge), rpId: o.rpId, userVerification: o.userVerification, timeout: o.timeout } });
      const me = await api('auth/login/passkey', { json: { id: b64u(c.rawId), clientDataJSON: b64u(c.response.clientDataJSON),
        authenticatorData: b64u(c.response.authenticatorData), signature: b64u(c.response.signature) } });
      await done(me);
    } catch (e) { if (e.name !== 'NotAllowedError' && e.name !== 'AbortError') err.textContent = e.message || String(e); } finally { btn.disabled = false; }
  } }, icon('key'), 'Sign in with a passkey');
  const wrap = h('div', { class: 'iosv sv-passkey', hidden: true }, btn, err);
  if (passkeysWork()) api('auth/login/passkey').then((r) => { wrap.hidden = !r.available; }).catch(() => {});
  return wrap;
}

// ------------------------------------------------------------------ building blocks
/** A box as every Settings tab draws one: an icon, a title, then its rows. */
export function box(ic, title, ...kids) {
  styles();
  return h('div', { class: 'iosv' }, h('div', { class: 'sv-box' }, h('h2', null, ic ? icon(ic) : null, title), ...kids));
}
/** A settings row: the label (and a short hint) on the left, the control on the right. */
export const row = (label, hint, control) => h('div', { class: 'sv-srow' }, h('div', null, h('b', null, label), hint ? h('div', { class: 'sv-muted sv-small' }, hint) : null), control);
const field = (label, input) => h('label', { class: 'sv-field' }, h('span', null, label), input);
const when = (t) => (t ? new Date(t * 1000).toLocaleDateString() : '');

/** Segmented choices that save at once: [[value, label], ...]. */
export function segmented(choices, current, onPick) {
  const seg = h('div', { class: 'sv-seg', role: 'radiogroup' }, choices.map(([v, l]) => h('button', { type: 'button', class: v === current ? 'on' : '', role: 'radio', 'aria-checked': String(v === current),
    onclick: async (e) => {
      const b = e.currentTarget;
      for (const x of seg.children) { x.classList.toggle('on', x === b); x.setAttribute('aria-checked', String(x === b)); }
      try { await onPick(v); } catch (err) { fail(err); }
    } }, l)));
  return seg;
}
const saveSetting = (body) => api('auth/settings', { json: body }).then(() => toast('Saved'));

// ------------------------------------------------------------------ Settings › Display
/** Appearance: Light, Dark or System. One choice for the whole suite, kept with the account: apply(value) is the
 *  app's applyTheme (frame.js), which keeps it in this browser and with the account, so every app follows it. */
export const themeRow = (current, apply) => row('Theme', 'Saved with your account, for every app in the suite.',
  segmented([['light', 'Light'], ['dark', 'Dark'], ['system', 'System']], current || 'system', (v) => { apply(v); toast('Saved'); }));
/** Units: Automatic (from the browser's region), Kilometres or Miles, saved with the account (or by save(value)). */
export const unitsRow = (current, apply, save) => row('Units', 'Automatic follows your region.',
  segmented([['auto', 'Automatic'], ['metric', 'Kilometres'], ['imperial', 'Miles']], current || 'auto', async (v) => { apply(v); if (save) { await save(v); toast('Saved'); } else await saveSetting({ units: v }); }));
/** Whether the browser's region signs its roads in miles (the US and its territories, the UK, Liberia, Myanmar): what
 *  units 'auto' means. */
const MILE_REGIONS = ['US', 'PR', 'GU', 'VI', 'AS', 'MP', 'UM', 'GB', 'LR', 'MM'];
export function regionUsesMiles(lang = navigator.language) {
  try { const l = new Intl.Locale(lang || 'en-US'); return MILE_REGIONS.includes(l.region || l.maximize().region); } catch { return false; }
}

// ------------------------------------------------------------------ Settings › Account
/** Display name and email (saved when a field is left), and the password. opts: toast, onSaved(user). */
export async function mountAccount(el, opts = {}) {
  styles(); setToast(opts.toast);
  el.classList.add('iosv');
  const me = await api('auth/me');
  const u = me.user;
  const save = (k) => async (e) => {
    if (e.target.value === (u[k] || '')) return;
    try { const r = await api('auth/me', { method: 'PATCH', json: { [k]: e.target.value } }); Object.assign(u, r.user); toast('Saved'); if (opts.onSaved) opts.onSaved(r.user); } catch (err) { fail(err); }
  };
  const dn = h('input', { class: 'sv-in', value: u.displayName || '', onchange: save('displayName') });
  const em = h('input', { class: 'sv-in', type: 'email', value: u.email || '', onchange: save('email') });
  const cur = h('input', { class: 'sv-in', type: 'password', autocomplete: 'current-password' });
  const nw = h('input', { class: 'sv-in', type: 'password', autocomplete: 'new-password' });
  el.replaceChildren(
    h('div', { class: 'sv-box' }, h('h2', null, icon('person'), 'You'),
      h('p', { class: 'sv-muted sv-small' }, `${u.name} · ${u.suiteAdmin ? 'suite admin' : u.role}. One account for every io app.`),
      h('div', { class: 'sv-grid' }, field('Display name', dn), field('Email (for sign-in at a proxy)', em))),
    h('div', { class: 'sv-box' }, h('h2', null, icon('key'), 'Password'),
      u.passwordless ? h('p', { class: 'sv-muted' }, 'This account signs in with one click and has no password. A suite admin can give it one.')
        : me.viaProxy ? h('p', { class: 'sv-muted' }, 'You signed in at the proxy; change the password there.')
          : [h('div', { class: 'sv-grid' }, field('Current password', cur), field('New password (8 or more)', nw)),
            h('div', { class: 'sv-row' }, h('button', { class: 'sv-btn', onclick: async () => {
              try { await api('auth/password', { json: { current: cur.value, password: nw.value } }); cur.value = nw.value = ''; toast('Password changed; your other sessions are signed out'); } catch (e) { fail(e); }
            } }, 'Change password'))]));
  if (!u.passwordless) {
    const ways = h('div');
    el.append(ways);
    await mountSignInWays(ways, opts).catch(() => ways.remove());
  }
  el.append(h('div', { class: 'sv-box' }, h('h2', null, icon('download'), 'Estate planning'),
    h('p', { class: 'sv-muted' }, 'One PDF of what the family would need if something happened to you: your contact details and your relatives’, your documents with their scans, your accounts and your things, from every app of the suite. Keep it somewhere safe.'),
    h('div', { class: 'sv-row' }, h('button', { class: 'sv-btn', onclick: (e) => downloadEstate(u.id, e.currentTarget) }, icon('download'), 'Make the PDF'))));
  const notes = h('div');
  el.append(notes);
  await mountNotifications(notes, opts).catch(() => notes.remove());
}

/** The estate planning PDF of an account (iosuite_shared.estate), downloaded: every app is asked, so it can take a
    while; the button says so meanwhile. A suite admin may make anyone's, a person their own. */
export async function downloadEstate(uid, button) {
  const was = button ? [...button.childNodes] : [];
  if (button) { button.disabled = true; button.textContent = 'Asking every app…'; }
  try {
    const r = await fetch(new URL(`auth/estate/${uid}/pdf`, API), { credentials: 'same-origin' });
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); if (typeof j.detail === 'string') msg = j.detail; } catch { /* not JSON */ }
      throw new Error(msg || `Error ${r.status}`);
    }
    const name = (/filename="([^"]+)"/.exec(r.headers.get('content-disposition') || '') || [])[1] || 'Estate-planning.pdf';
    const url = URL.createObjectURL(await r.blob());
    const a = h('a', { href: url, download: name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    toast('Estate planning PDF made');
  } catch (e) { fail(e); } finally {
    if (button) { button.disabled = false; button.replaceChildren(...was); }
  }
}

// ------------------------------------------------------------------ Settings › Account: passkeys and two-step sign-in
const deviceName = () => {
  const ua = navigator.userAgent;
  if (/iPhone/.test(ua)) return 'iPhone';
  if (/iPad/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) return 'iPad';
  if (/Android/.test(ua)) return 'Android phone';
  if (/Mac/.test(ua)) return 'Mac';
  if (/Windows/.test(ua)) return 'Windows PC';
  return 'This device';
};
const passwordField = () => h('input', { class: 'sv-in', type: 'password', autocomplete: 'current-password', placeholder: 'Your password', 'aria-label': 'Your password' });

/** Sign-in, part of mountAccount: both off until the person turns them on. Passkeys (add on this device, list, remove)
 *  and two-step sign-in (a code app's codes after the password; recovery codes shown once). opts: toast. */
export async function mountSignInWays(el, opts = {}) {
  styles(); setToast(opts.toast);
  el.classList.add('iosv');
  let info = await api('auth/sign-in');
  if (!info.available) { el.remove(); return; }
  const body = h('div');

  const addPasskey = async () => {
    const pw = passwordField(), label = h('input', { class: 'sv-in', value: deviceName(), 'aria-label': 'Name' });
    const got = await formDialog('Add a passkey', [
      h('p', null, 'This device, or your password manager, keeps the passkey; you then sign in with Face ID, Touch ID, a fingerprint or its PIN instead of typing your password.'),
      field('Your password, to confirm it is you', pw), field('A name for this passkey', label)],
    'Continue', async () => {
      const o = await api('auth/passkeys/begin', { json: { password: pw.value } });
      const c = await navigator.credentials.create({ publicKey: { ...o, challenge: fromB64u(o.challenge), user: { ...o.user, id: fromB64u(o.user.id) },
        excludeCredentials: o.excludeCredentials.map((x) => ({ ...x, id: fromB64u(x.id) })) } }).catch((e) => {
        throw new Error(e.name === 'InvalidStateError' ? 'This device already has a passkey for your account' : e.name === 'NotAllowedError' ? 'No passkey was made' : (e.message || String(e)));
      });
      const key = c.response.getPublicKey && c.response.getPublicKey();
      if (!key) throw new Error('This browser is too old for passkeys here; update it and try again');
      return api('auth/passkeys', { json: { label: label.value.trim(), clientDataJSON: b64u(c.response.clientDataJSON),
        authenticatorData: b64u(c.response.getAuthenticatorData()), publicKey: b64u(key), alg: c.response.getPublicKeyAlgorithm() } });
    });
    if (got) { info = got; draw(); toast('Passkey added'); }
  };

  const turnOn = async () => {
    const pw = passwordField();
    const made = await formDialog('Turn on two-step sign-in', [
      h('p', null, 'After your password, the sign-in screen will ask for a 6-digit code from a code app on your phone (Apple Passwords, Google Authenticator, 1Password and the like).'),
      field('Your password, to confirm it is you', pw)], 'Continue', () => api('auth/two-step/begin', { json: { password: pw.value } }));
    if (!made) return;
    const qr = h('div', { class: 'sv-qr' }); qr.innerHTML = made.qr;  // the server's own drawing of the code
    const code = h('input', { class: 'sv-in', inputmode: 'numeric', autocomplete: 'one-time-code', placeholder: '6-digit code', 'aria-label': 'Code' });
    const on = await formDialog('Scan this with your code app', [qr,
      h('p', { class: 'sv-muted sv-small' }, 'Or type this key into it:'), h('p', null, h('code', { class: 'sv-code' }, made.secret.replace(/(.{4})/g, '$1 ').trim())),
      h('p', { class: 'sv-small' }, h('a', { href: made.uri }, 'Open in a code app on this device')),
      field('Then type the code it shows', code)], 'Turn on', () => api('auth/two-step', { json: { code: code.value } }));
    if (!on) return;
    info = on; draw();
    await formDialog('Keep these recovery codes', [
      h('p', null, 'Two-step sign-in is on. If your phone is ever lost, each of these codes signs you in once in place of a code. They are shown only now: print them or keep them in a safe place.'),
      h('div', { class: 'sv-codes' }, on.recovery.map((c) => h('span', null, c))),
      h('div', { class: 'sv-row' }, h('button', { class: 'sv-btn', type: 'button', onclick: async () => {
        try { await navigator.clipboard.writeText(on.recovery.join('\n')); toast('Copied'); } catch { toast('Select them and copy'); }
      } }, 'Copy'))], 'I have kept them', () => true, { cancel: null });
  };

  const turnOff = async () => {
    const pw = passwordField();
    const off = await formDialog('Turn off two-step sign-in', [h('p', null, 'Your password alone will sign you in again.'), field('Your password, to confirm it is you', pw)],
      'Turn off', () => api('auth/two-step/off', { json: { password: pw.value } }));
    if (off) { info = off; draw(); toast('Two-step sign-in is off'); }
  };

  const draw = () => {
    const two = info.twoStep;
    const here = info.passkeys.filter((p) => p.here).length;
    const list = info.passkeys.length ? h('table', { class: 'sv-t' }, h('tr', null, h('th', null, 'Passkey'), h('th', null, 'Added'), h('th', null, 'Last used'), h('th')),
      info.passkeys.map((p) => h('tr', null, h('td', null, p.label, p.here ? null : h('div', { class: 'sv-muted sv-small' }, `for ${p.rpId}`)), h('td', null, when(p.created)),
        h('td', null, p.lastUsed ? when(p.lastUsed) : 'never'),
        h('td', { style: 'text-align:right' }, h('button', { class: 'sv-btn', onclick: async () => {
          if (!await confirmDialog('Remove passkey', `Remove “${p.label}”? It no longer signs you in; your password still does.`, 'Remove')) return;
          try { info = await api(`auth/passkeys/${p.id}`, { method: 'DELETE' }); draw(); } catch (e) { fail(e); }
        } }, 'Remove'))))) : null;
    body.replaceChildren(
      row('Passkeys', !passkeysWork() ? 'Sign in with Face ID, Touch ID or a fingerprint instead of your password. Passkeys need an https address; this one is not.'
        : here ? 'On: the sign-in screen offers “Sign in with a passkey”.' : 'Off. Sign in with Face ID, Touch ID, a fingerprint or a security key instead of typing your password.',
      passkeysWork() ? h('button', { class: 'sv-btn', onclick: () => addPasskey().catch(fail) }, 'Add a passkey') : null),
      ...(list ? [list] : []),  // replaceChildren writes a null out as the word "null"
      row('Two-step sign-in', two.on ? `On since ${when(two.since)}: a code from your code app after your password. ${two.recoveryLeft} recovery code${two.recoveryLeft === 1 ? '' : 's'} left. Calendar, contacts and other sync apps sign in with an app password.`
        : 'Off. A 6-digit code from a code app after your password. Sync apps (calendar, contacts) then need an app password instead of your password.',
      two.on ? h('button', { class: 'sv-btn', onclick: () => turnOff().catch(fail) }, 'Turn off') : h('button', { class: 'sv-btn', onclick: () => turnOn().catch(fail) }, 'Turn on')));
  };
  el.replaceChildren(h('div', { class: 'sv-box' }, h('h2', null, icon('shield'), 'Sign-in'),
    h('p', { class: 'sv-muted sv-small' }, 'Optional, for your account only, in every io app. Nothing changes until you turn one on.'), body));
  draw();
}

// ------------------------------------------------------------------ Settings › Account: notifications
const SW = new URL('auth/push/sw.js', API);
const SCOPE = new URL('auth/push/', API);
const fromB64u = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
const sameKey = (buf, key) => { if (!buf) return false; const a = new Uint8Array(buf), b = fromB64u(key); return a.length === b.length && a.every((x, i) => x === b[i]); };
const sha256 = async (s) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map((b) => b.toString(16).padStart(2, '0')).join('');
const standalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
const appleMobile = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const MORNING_KINDS = ['tasks', 'birthdays', 'health_week', 'health_usual'];

async function workerRegistration(create) {
  let reg = await navigator.serviceWorker.getRegistration(SCOPE.href);
  if (!reg && create) reg = await navigator.serviceWorker.register(SW.href, { scope: SCOPE.href });
  if (!reg) return null;
  const w = reg.installing || reg.waiting;
  if (!reg.active && w) await new Promise((ok) => w.addEventListener('statechange', () => { if (w.state === 'activated') ok(); }));
  return reg;
}

/** Notifications: turn them on or off on this device (any app of the suite reaches it), what this account gets (on
 *  every device), the morning time of the morning summaries, the devices, a test. opts: toast. */
export async function mountNotifications(el, opts = {}) {
  styles(); setToast(opts.toast);
  el.classList.add('iosv');
  const can = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window && window.isSecureContext;
  let info = await api('auth/push');
  let sub = null, hash = '';
  const body = h('div');
  const read = async () => {
    if (!can) return;
    const reg = await navigator.serviceWorker.getRegistration(SCOPE.href);
    sub = reg ? await reg.pushManager.getSubscription() : null;
    hash = sub ? await sha256(sub.endpoint) : '';
  };
  const save = async (path, init) => { info = await api(path, init); draw(); };
  const turnOn = async () => {
    if (await Notification.requestPermission() !== 'granted') { toast('Notifications are blocked for this site; allow them in the browser’s settings'); draw(); return; }
    const reg = await workerRegistration(true);
    let s = await reg.pushManager.getSubscription();
    if (s && !sameKey(s.options && s.options.applicationServerKey, info.key)) { await s.unsubscribe(); s = null; }
    s = s || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: fromB64u(info.key) });
    await save('auth/push/devices', { json: { subscription: s.toJSON(), standalone: standalone() } });
    await read(); draw();
    toast('Notifications are on for this device');
  };
  const turnOff = async () => {
    const here = info.devices.find((d) => d.endpointHash === hash);
    if (sub) await sub.unsubscribe().catch(() => {});
    if (here) info = await api(`auth/push/devices/${here.id}`, { method: 'DELETE' });
    await read(); draw();
    toast('Notifications are off for this device');
  };
  const busy = (fn) => async (e) => { const b = e.currentTarget; b.disabled = true; try { await fn(); } catch (err) { fail(err); } finally { b.disabled = false; } };

  const draw = () => {
    const here = info.devices.find((d) => d.endpointHash === hash);
    let device;
    if (!can) {
      device = h('p', { class: 'sv-muted' }, appleMobile() && !standalone()
        ? 'On an iPhone or iPad, add this app to the Home Screen first (Share › Add to Home Screen), open it from there and turn notifications on in it.'
        : 'This browser cannot show notifications here (they need an https address).');
    } else if (Notification.permission === 'denied') {
      device = h('p', { class: 'sv-warn' }, 'Notifications are blocked for this site. Allow them in the browser’s site settings, then come back here.');
    } else {
      device = row('This device', here ? `On: ${here.label}.` : 'Off. One app per device is enough: every app’s notifications arrive through it.',
        here ? h('button', { class: 'sv-btn', onclick: busy(turnOff) }, 'Turn off') : h('button', { class: 'sv-btn primary', onclick: busy(turnOn) }, 'Turn on'));
    }
    const kinds = info.kinds.length ? h('div', null, h('p', { class: 'sv-small sv-muted', style: 'margin-top:12px' }, 'What you get, on every device:'),
      info.kinds.map((k) => h('label', { class: 'sv-check' }, h('input', { type: 'checkbox', checked: k.on,
        onchange: async (e) => { try { await save('auth/push/prefs', { method: 'PUT', json: { kinds: { [k.kind]: e.target.checked } } }); toast('Saved'); } catch (err) { fail(err); } } }),
      h('span', null, h('b', null, k.label), h('span', { class: 'sv-muted sv-small' }, ` · ${k.hint}`))))) : null;
    const morning = info.kinds.some((k) => MORNING_KINDS.includes(k.kind)) ? row('Morning summary', 'When the tasks and birthdays of the day, and the Monday health summary, arrive.',
      h('input', { class: 'sv-in', type: 'time', step: 300, value: info.morning, style: 'max-width:130px',
        onchange: async (e) => { try { await save('auth/push/prefs', { method: 'PUT', json: { morning: e.target.value } }); toast('Saved'); } catch (err) { fail(err); } } })) : null;
    const list = info.devices.length ? h('table', { class: 'sv-t' }, h('tr', null, h('th', null, 'Device'), h('th', null, 'Turned on in'), h('th', null, 'Last delivered'), h('th')),
      info.devices.map((d) => h('tr', null, h('td', null, d.label, d.endpointHash === hash ? h('span', { class: 'sv-muted' }, ' (this one)') : null), h('td', null, d.appName || '—'),
        h('td', null, d.lastOk ? when(d.lastOk) : 'not yet'),
        h('td', { style: 'text-align:right' }, h('button', { class: 'sv-btn', onclick: busy(async () => {
          if (d.endpointHash === hash) return turnOff();
          await save(`auth/push/devices/${d.id}`, { method: 'DELETE' });
        }) }, 'Remove'))))) : null;
    const test = info.devices.length ? h('div', { class: 'sv-row' }, h('button', { class: 'sv-btn', onclick: busy(async () => {
      const r = await api('auth/push/test', { json: {} });
      toast(r.sent ? `Sent to ${r.sent} of ${r.devices} device${r.devices === 1 ? '' : 's'}` : 'No device took it; turn notifications on again there');
      info = await api('auth/push'); draw();
    }) }, 'Send a test')) : null;
    body.replaceChildren(device, kinds, morning, list, test);
  };
  el.replaceChildren(h('div', { class: 'sv-box' }, h('h2', null, icon('bell'), 'Notifications'), body));
  await read();
  draw();
}

// ------------------------------------------------------------------ Settings › Account: app passwords
/** The signed-in account's app passwords here: make one (shown once), list, revoke. opts: toast, syncOnly (the label of
 *  the sync-only choice, e.g. 'Calendar apps only (CalDAV)'; offered when the app has sync protocols), onChange(). */
export async function mountAppPasswords(el, opts = {}) {
  styles(); setToast(opts.toast);
  el.classList.add('iosv');
  const me = await api('auth/me');
  if (me.user.passwordless) {
    el.replaceChildren(h('div', { class: 'sv-box' }, h('h2', null, icon('key'), 'App passwords'), h('p', { class: 'sv-muted' }, 'A one-click account cannot have app passwords. A suite admin can give it a password first.')));
    return;
  }
  const label = h('input', { class: 'sv-in', placeholder: 'Name, e.g. Alex’s iPhone', 'aria-label': 'Name' });
  const shown = h('div'), list = h('div');
  let scopes = [''];
  const sync = h('input', { type: 'checkbox', checked: true });
  const scopeText = (s) => (s ? (opts.syncOnly || 'Sync apps only') : 'Everything');
  const draw = async () => {
    const r = await api('auth/app-passwords');
    scopes = r.scopes || [''];
    syncRow.hidden = !(opts.syncOnly && scopes.includes('dav'));
    list.replaceChildren(r.items.length ? h('table', { class: 'sv-t' }, h('tr', null, h('th', null, 'Name'), syncRow.hidden ? null : h('th', null, 'Works for'), h('th', null, 'Made'), h('th', null, 'Last used'), h('th')),
      r.items.map((p) => h('tr', null, h('td', null, p.label), syncRow.hidden ? null : h('td', null, scopeText(p.scope)), h('td', null, when(p.created)), h('td', null, p.lastUsed ? when(p.lastUsed) : 'never'),
        h('td', { style: 'text-align:right' }, h('button', { class: 'sv-btn', onclick: async () => {
          if (!await confirmDialog('Revoke app password', `Revoke “${p.label}”? Whatever uses it stops signing in.`, 'Revoke')) return;
          try { await api(`auth/app-passwords/${p.id}`, { method: 'DELETE' }); draw(); if (opts.onChange) opts.onChange(); } catch (e) { fail(e); }
        } }, 'Revoke'))))) : h('p', { class: 'sv-muted' }, 'No app passwords yet.'));
  };
  const syncRow = h('label', { class: 'sv-check' }, sync, ` ${opts.syncOnly || ''}`);
  el.replaceChildren(h('div', { class: 'sv-box' }, h('h2', null, icon('key'), 'App passwords'),
    h('p', { class: 'sv-muted' }, 'One per app or device, used with your user name instead of your password. Revoke one without touching the others.'),
    h('div', { class: 'sv-row' }, label, h('button', { class: 'sv-btn primary', onclick: async () => {
      try {
        const r = await api('auth/app-passwords', { json: { label: label.value.trim() || 'Device', scope: !syncRow.hidden && sync.checked ? 'dav' : '' } });
        shown.replaceChildren(h('p', null, h('b', null, 'Copy it now, it is shown only once: '), h('code', { class: 'sv-code' }, r.password)));
        label.value = ''; draw(); if (opts.onChange) opts.onChange();
      } catch (e) { fail(e); }
    } }, 'New app password')), syncRow, shown, list));
  await draw();
}

/** The signed-in person's subscription links of this app (iosuite_shared.feeds: /api/feeds): an address with a secret,
    for apps that cannot sign in. A new one is shown once, with every address the app makes from it; each is named and
    stopped by itself. opts: { toast, title, intro, icon, open: 'Open in my calendar app' (the first address, as webcal://) }. */
export async function mountFeeds(el, opts = {}) {
  styles(); setToast(opts.toast);
  el.classList.add('iosv');
  const label = h('input', { class: 'sv-in', placeholder: 'Name, e.g. Kitchen tablet', 'aria-label': 'Name' });
  const shown = h('div'), list = h('div');
  const draw = (items) => list.replaceChildren(items.length ? h('table', { class: 'sv-t' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Made'), h('th', null, 'Last used'), h('th')),
    items.map((f) => h('tr', null, h('td', null, f.label), h('td', null, when(f.created)), h('td', null, f.lastUsed ? when(f.lastUsed) : 'never'),
      h('td', { style: 'text-align:right' }, h('button', { class: 'sv-btn', onclick: async () => {
        if (!await confirmDialog('Stop subscription link', `Stop “${f.label}”? Calendars subscribed with it stop updating.`, 'Stop')) return;
        try { await api(`feeds/${f.id}`, { method: 'DELETE' }); draw((await api('feeds')).feeds); } catch (e) { fail(e); }
      } }, 'Stop'))))) : h('p', { class: 'sv-muted' }, 'No subscription links yet.'));
  el.replaceChildren(h('div', { class: 'sv-box' }, h('h2', null, icon(opts.icon || 'devices'), opts.title || 'Subscribe (read-only)'),
    h('p', { class: 'sv-muted' }, opts.intro || 'For apps that cannot sign in. Anyone with a link can read what it shows, so make one per app or device and stop it when it is no longer used.'),
    h('div', { class: 'sv-row' }, label, h('button', { class: 'sv-btn primary', onclick: async () => {
      try {
        const r = await api('feeds', { json: { label: label.value.trim() } });
        const first = r.links[0];
        shown.replaceChildren(h('p', null, h('b', null, 'Copy the address now, it is shown only once.')),
          ...r.links.map((l) => h('div', { class: 'sv-row' }, h('span', { style: 'min-width:120px' }, l.name), h('code', { class: 'sv-code' }, l.url))),
          first && opts.open !== false ? h('p', null, h('a', { class: 'sv-btn', href: first.url.replace(/^https?:/, 'webcal:') }, opts.open || 'Open in my calendar app')) : null);
        label.value = ''; draw(r.feeds);
      } catch (e) { fail(e); }
    } }, 'New link')), shown, list));
  draw((await api('feeds')).feeds);
}

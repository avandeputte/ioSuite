/* Kitchen timers: started from the search box, counting down on the start page and the wall display. */
import { fail, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { $, api, pad2, S } from './core.js';

// ------------------------------------------------------------------ kitchen timers
/* "timer 10m pasta", "pasta timer 1h30", "egg timer 6 min", "timer 90s": a timer for the whole family, kept by the
   server (iostart/timers.py). Every start page and the wall display show the running ones counting down (anyone can add
   a minute or dismiss one); when one ends, the page that started it and the wall display ring, and whoever started
   it gets a notification on their phone. The page asks the server every 15 seconds, so a timer started on the phone
   shows on the kitchen tablet. */
export function parseTimer(q) {
  const words = q.trim().split(/\s+/);
  if (!words.some((w) => /^timer$/i.test(w))) return null;
  let secs = 0, found = false;
  const label = [];
  const UNIT = { h: 3600, hr: 3600, hrs: 3600, hour: 3600, hours: 3600, m: 60, min: 60, mins: 60, minute: 60, minutes: 60, s: 1, sec: 1, secs: 1, second: 1, seconds: 1 };
  for (let i = 0; i < words.length; i++) {
    const w = words[i].toLowerCase(), nx = (words[i + 1] || '').toLowerCase();
    let m;
    if (/^(timer|for|a|an|set|start|of)$/.test(w)) continue;
    if ((m = w.match(/^(\d+)h(?:(\d+)m?)?$/))) { secs += +m[1] * 3600 + +(m[2] || 0) * 60; found = true; continue; }
    if ((m = w.match(/^(\d+)m(?:(\d+)s?)?$/))) { secs += +m[1] * 60 + +(m[2] || 0); found = true; continue; }
    if ((m = w.match(/^(\d+(?:[.,]\d+)?)(h|hrs?|hours?|m|mins?|minutes?|s|secs?|seconds?)$/))) { secs += +m[1].replace(',', '.') * UNIT[m[2]]; found = true; continue; }
    if ((m = w.match(/^(\d+):(\d{2})(?::(\d{2}))?$/))) { secs += m[3] ? +m[1] * 3600 + +m[2] * 60 + +m[3] : +m[1] * 60 + +m[2]; found = true; continue; }
    if ((m = w.match(/^(\d+(?:[.,]\d+)?)$/)) && UNIT[nx]) { secs += +m[1].replace(',', '.') * UNIT[nx]; i++; found = true; continue; }
    if (w === 'and' && found) continue;
    label.push(words[i]);
  }
  secs = Math.round(secs);
  if (!found || secs < 1 || secs > 86400) return null;
  const text = label.join(' ').trim();
  return { seconds: secs, label: text ? text[0].toUpperCase() + text.slice(1) : 'Timer' };
}
export function timerLength(s) {
  const h_ = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return [h_ ? `${h_} h` : '', m ? `${m} min` : '', sec ? `${sec} s` : ''].filter(Boolean).join(' ');
}
const T = { items: [], skew: 0, els: new Set(), tick: null, poll: null, rang: new Set(), audio: null, ringing: null };
const timerMine = () => { try { return new Set(JSON.parse(sessionStorage.getItem('iostart.timers') || '[]')); } catch { return new Set(); } };
function timerKeep(id) { const s = timerMine(); s.add(id); try { sessionStorage.setItem('iostart.timers', JSON.stringify([...s].slice(-30))); } catch { /* private mode: it still rings while the page is open */ } }
const timerLeft = (t) => Math.ceil((t.endsAt * 1000 - (Date.now() + T.skew)) / 1000);
const clockOf = (s) => { const a = Math.max(0, s), h_ = Math.floor(a / 3600), m = Math.floor((a % 3600) / 60), sec = a % 60; return h_ ? `${h_}:${pad2(m)}:${pad2(sec)}` : `${m}:${pad2(sec)}`; };
async function timersLoad() {
  try { const d = await api('api/timers'); T.skew = d.now * 1000 - Date.now(); T.items = d.items || []; } catch { /* the next round */ }
  timersPaint();
}
export async function timerStart(t) {
  timerSound(true);  // a tap or Enter: the moment a browser lets the page make a sound later
  try {
    const got = await api('api/timers', { method: 'POST', json: { seconds: t.seconds, label: t.label } });
    timerKeep(got.id); toast(`Timer: ${got.label}, ${timerLength(got.seconds)}`);
    $('.search .q') && ($('.search .q').value = '');
    await timersLoad();
  } catch (e) { fail(e); }
}
async function timerAct(t, what) {
  timerSound(true);
  try {
    if (what === 'more') await api(`api/timers/${t.id}/more`, { method: 'POST', json: { seconds: 60 } });
    else await api(`api/timers/${t.id}`, { method: 'DELETE' });
  } catch (e) { fail(e); }
  T.rang.delete(t.id); await timersLoad();
}
/** The page's sound: made (and let out) on a tap, a short beep three times for a timer that ended. */
function timerSound(prime) {
  try {
    T.audio = T.audio || new (window.AudioContext || window.webkitAudioContext)();
    if (T.audio.state === 'suspended') T.audio.resume();
    if (prime) return;
    const a = T.audio, t0 = a.currentTime;
    for (let k = 0; k < 3; k++) {
      const o = a.createOscillator(), g = a.createGain();
      o.frequency.value = 880; o.connect(g); g.connect(a.destination);
      g.gain.setValueAtTime(0.0001, t0 + k * 0.35); g.gain.exponentialRampToValueAtTime(0.4, t0 + k * 0.35 + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + k * 0.35 + 0.25);
      o.start(t0 + k * 0.35); o.stop(t0 + k * 0.35 + 0.3);
    }
  } catch { /* no sound here: the chip still turns red */ }
}
function timersPaint() {
  for (const el of [...T.els]) if (!el.isConnected) T.els.delete(el);
  const mine = timerMine(), me = S.user && S.user.id;
  const wall = [...T.els].some((el) => el.dataset.wall);
  let ring = false;
  for (const el of T.els) {
    el.replaceChildren(...T.items.map((t) => {
      const left = timerLeft(t), done = left <= 0;
      return h('div', { class: `timer${done ? ' done' : ''}`, title: `${t.label}: ${timerLength(t.seconds)}${t.by ? `, started by ${t.by}` : ''}` },
        icon('timer', 's'), h('span', { class: 'tlabel' }, t.label),
        h('span', { class: 'tleft' }, done ? 'Done' : clockOf(left)),
        t.byId !== me && t.by ? h('span', { class: 'tby muted small' }, t.by) : null,
        h('button', { class: 'tbtn', title: done ? 'One more minute' : 'A minute more', onclick: () => timerAct(t, 'more') }, '+1'),
        h('button', { class: 'tbtn', title: done ? 'Dismiss' : 'Stop the timer', 'aria-label': 'Dismiss', onclick: () => timerAct(t, 'dismiss') }, icon('close', 's')));
    }));
    el.hidden = !T.items.length;
  }
  for (const t of T.items) {
    if (timerLeft(t) > 0) { T.rang.delete(t.id); continue; }
    // a timer that ends rings where it was started and on the wall display, for a minute or until it is dismissed
    if ((mine.has(t.id) || wall) && timerLeft(t) > -60) ring = true;
  }
  if (ring && !T.ringing) { timerSound(); T.ringing = setInterval(() => { if (!T.items.some((t) => timerLeft(t) <= 0 && timerLeft(t) > -60 && (timerMine().has(t.id) || [...T.els].some((el) => el.dataset.wall)))) { clearInterval(T.ringing); T.ringing = null; } else timerSound(); }, 2500); }
  if (!ring && T.ringing) { clearInterval(T.ringing); T.ringing = null; }
  clearInterval(T.tick); T.tick = T.items.length && T.els.size ? setInterval(timersPaint, 1000) : null;
}
/** A place that shows the family's timers (the home page under the search box, the wall display). */
export function timersBlock(wall = false) {
  const el = h('div', { class: wall ? 'walltimers' : 'timers', hidden: true, ...(wall ? { 'data-wall': '1' } : {}) });
  T.els.add(el);
  if (!T.poll) T.poll = setInterval(() => { for (const x of [...T.els]) if (!x.isConnected) T.els.delete(x); if (!T.els.size) { clearInterval(T.poll); T.poll = null; } else if (!document.hidden) timersLoad(); }, 15000);
  timersLoad();
  return el;
}

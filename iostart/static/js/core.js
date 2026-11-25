/* What every part of the page uses: the helpers (api, $, the icons), the page's state (S), reordering by dragging,
   and the sign-in screen. It takes nothing from the other modules, so it is ready before any of them. */
import * as frame from '../../api/auth/frame.js';
import { addIcons, initials } from '../../api/auth/frame.js';
import { client, h } from '../../api/auth/ui.js';

export const store = frame.storeFor('iostart');  // what this browser remembers for the app
export const api = client(document.baseURI, { signIn: () => showSignIn() });

// ------------------------------------------------------------------ helpers
export const $ = (s, el = document) => el.querySelector(s);
addIcons({
  warn: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
  rss: 'M6.18 15.64a2.18 2.18 0 1 1 0 4.36 2.18 2.18 0 0 1 0-4.36zM4 4.44A15.56 15.56 0 0 1 19.56 20h-2.83A12.73 12.73 0 0 0 4 7.27V4.44zm0 5.66a9.9 9.9 0 0 1 9.9 9.9h-2.83A7.07 7.07 0 0 0 4 12.93V10.1z',
  star: 'M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z',
  doneall: 'm18 7-1.41-1.41-6.34 6.34 1.41 1.41L18 7zm4.24-1.41L11.66 16.17 7.48 12l-1.41 1.41L11.66 19l12-12-1.42-1.41zM.41 13.41 6 19l1.41-1.41L1.83 12 .41 13.41z',
  unread: 'M22 8.98V18c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2h10.1c-.06.32-.1.66-.1 1s.04.68.1 1H4l8 5 3.67-2.29c.47.43 1.02.76 1.63.98L12 13 4 8v10h16V9.9c.74-.15 1.42-.48 2-.92zM16 5c0 1.66 1.34 3 3 3s3-1.34 3-3-1.34-3-3-3-3 1.34-3 3z',
  doc: 'M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
  box: 'M20 2H4c-1 0-2 .9-2 2v3.01c0 .72.43 1.34 1 1.69V20c0 1.1 1.1 2 2 2h14c.9 0 2-.9 2-2V8.7c.57-.35 1-.97 1-1.69V4c0-1.1-1-2-2-2zm-5 12H9v-2h6v2zm5-7H4V4l16-.02V7z',
  timer: 'M15 1H9v2h6V1zm-4 13h2V8h-2v6zm8.03-6.61 1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A8.962 8.962 0 0 0 12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9 9-4.03 9-9c0-2.12-.74-4.07-1.97-5.61zM12 20c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z',
  calc: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5.97 4.06L14.09 6l1.41 1.41L16.91 6l1.06 1.06-1.41 1.41 1.41 1.41-1.06 1.06-1.41-1.4-1.41 1.41-1.06-1.06 1.41-1.41-1.41-1.42zm-6.78.66h5v1.5h-5v-1.5zM11.5 16h-2v2H8v-2H6v-1.5h2v-2h1.5v2h2V16zm6.5 1.25h-5v-1.5h5v1.5zm0-2.5h-5v-1.5h5v1.5z',
  key: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  apps: 'M4 8h4V4H4v4zm6 12h4v-4h-4v4zm-6 0h4v-4H4v4zm0-6h4v-4H4v4zm6 0h4v-4h-4v4zm6-10v4h4V4h-4zm-6 4h4V4h-4v4zm6 6h4v-4h-4v4zm0 6h4v-4h-4v4z',
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  cloud: 'M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z',
  note: 'M3 18h12v-2H3v2zM3 6v2h18V6H3zm0 7h18v-2H3v2z',
  up: 'M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z',
  down: 'M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z',
  eye: 'M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z',
  eyeoff: 'M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46A11.804 11.804 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z',
  move: 'M10 9h4V6h3l-5-5-5 5h3v3zm-1 1H6V7l-5 5 5 5v-3h3v-4zm14 2-5-5v3h-3v4h3v3l5-5zm-9 3h-4v3H7l5 5 5-5h-3v-3z',
  grip: 'M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  wall: 'M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 1.99-.9 1.99-2L23 5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z',
  image: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z',
  fullscreen: 'M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z',
  task: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z',
  recipe: 'M11 9H9V2H7v7H5V2H3v7c0 2.12 1.66 3.84 3.75 3.97V22h2.5v-9.03C11.34 12.84 13 11.12 13 9V2h-2v7zm5-3v8h2.5v8H21V2c-2.76 0-5 2.24-5 4z',
  event: 'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
  web: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
  bulb: 'M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z',
  power: 'M13 3h-2v10h2V3zm4.83 2.17-1.42 1.42A6.92 6.92 0 0 1 19 12c0 3.87-3.13 7-7 7A6.995 6.995 0 0 1 7.58 6.58L6.17 5.17A8.932 8.932 0 0 0 3 12a9 9 0 0 0 18 0c0-2.74-1.23-5.18-3.17-6.83z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM9 8V6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9z',
  unlock: 'M12 17c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm6-9h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6h1.9c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm0 12H6V10h12v10z',
  door: 'M19 19V4c0-1.1-.9-2-2-2H7c-1.1 0-2 .9-2 2v15H3v2h18v-2h-2zm-4-6h-2v-2h2v2z',
  thermo: 'M15 13V5c0-1.66-1.34-3-3-3S9 3.34 9 5v8c-1.21.91-2 2.37-2 4 0 2.76 2.24 5 5 5s5-2.24 5-5c0-1.63-.79-3.09-2-4zm-4-8c0-.55.45-1 1-1s1 .45 1 1h-1v1h1v2h-1v1h1v2h-2V5z',
  warn: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
  play: 'M8 5v14l11-7z',
  blind: 'M20 19V3H4v16H2v2h20v-2h-2zM6 5h12v2H6V5zm0 4h12v2H6V9zm0 4h12v2H6v-2zm0 6v-2h12v2H6z',
  fan: 'M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2zm0-9c-1.5 0-3 .9-3 3 0 1.7.9 3.4 2 5.3-1.9-1-3.6-1.3-5.3-1.3-2.1 0-3.7 1.5-3.7 3s1.6 3 3.7 3c1.7 0 3.4-.3 5.3-1.3-1.1 1.9-2 3.6-2 5.3 0 2.1 1.5 3 3 3s3-.9 3-3c0-1.7-.9-3.4-2-5.3 1.9 1 3.6 1.3 5.3 1.3 2.1 0 3.7-1.5 3.7-3s-1.6-3-3.7-3c-1.7 0-3.4.3-5.3 1.3 1.1-1.9 2-3.6 2-5.3 0-2.1-1.5-3-3-3z',
  bolt: 'M7 2v11h3v9l7-12h-4l4-8z',
  battery: 'M15.67 4H14V2h-4v2H8.33C7.6 4 7 4.6 7 5.33v15.33C7 21.4 7.6 22 8.33 22h7.33c.74 0 1.34-.6 1.34-1.33V5.33C17 4.6 16.4 4 15.67 4zM15 18H9v-6h6v6z',
  folder: 'M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z',
  phone: 'M15.5 1h-8A2.5 2.5 0 0 0 5 3.5v17A2.5 2.5 0 0 0 7.5 23h8a2.5 2.5 0 0 0 2.5-2.5v-17A2.5 2.5 0 0 0 15.5 1zm-4 21c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm4.5-4H7V4h9v14z',
  more: 'M6 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm12 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-6 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  left: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  right: 'M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6z',
  place: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 0 1 0-5 2.5 2.5 0 0 1 0 5z',
  broom: 'M19.36 2.72 20.78 4.14 15.06 9.85c1.08 1.6 1.4 3.52.92 5.18L9.61 8.66c1.66-.48 3.58-.16 5.18.92l4.57-6.86zM5.93 17.57c-2.01-2.01-3.24-4.41-3.58-6.65l4.88-2.09 7.44 7.44-2.09 4.88c-2.24-.34-4.64-1.57-6.65-3.58z',
  tabs: 'M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z',
  server: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
});

/** An item's picture, through this page (the suite's /api/suite/items/{kind}/{id}/image of its app). */
export const itemImage = (app, kind, id, p) => `api/widgets/${app}/image/${kind}/${encodeURIComponent(id)}${p ? `?p=${encodeURIComponent(p)}` : ''}`;
/** A contact's face as ioContact shows it: its own photo, else its face in ioPix (when linked), else its initials. */
export function contactFace(c, lazy = true) {
  const src = c.hasPhoto || c.iopixPersonId ? itemImage('iocontact', 'contact', c.id) : null;
  return h('span', { class: 'face' }, src ? h('img', { src, alt: '', loading: lazy ? 'lazy' : undefined, onerror: (e) => e.target.replaceWith(initials(c.name)) }) : initials(c.name));
}
/** An app's name as the apps write it: "io" in gold, the rest in the app's colour. */
/* The weather: AccuWeather's icon numbers (1-44) drawn with a handful of glyphs. */
const WX = {
  sun: '<circle cx="12" cy="12" r="4.2"/><g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/></g>',
  moon: '<path d="M14.5 3.5a8.5 8.5 0 1 0 6 14.5 7 7 0 0 1-6-14.5z"/>',
  cloud: '<path d="M18.5 19H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 9.5 4.75 4.75 0 0 1 18.5 19z"/>',
  partly: '<circle cx="8" cy="8" r="3.4"/><g stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 1.8v1.6M1.8 8h1.6M3.6 3.6l1.1 1.1M12.4 3.6l-1.1 1.1"/></g><path d="M19 20.5H9.5a3.8 3.8 0 0 1-.6-7.55A5 5 0 0 1 18.4 12 4 4 0 0 1 19 20.5z"/>',
  partlyNight: '<path d="M9.2 2.2a5.2 5.2 0 1 0 4.1 8.6 4.4 4.4 0 0 1-4.1-8.6z"/><path d="M19 20.5H9.5a3.8 3.8 0 0 1-.6-7.55A5 5 0 0 1 18.4 12 4 4 0 0 1 19 20.5z"/>',
  rain: '<path d="M18.5 15H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 5.5 4.75 4.75 0 0 1 18.5 15z"/><g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8.5 17.5l-1 3M12.5 17.5l-1 3M16.5 17.5l-1 3"/></g>',
  storm: '<path d="M18.5 14H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 4.5 4.75 4.75 0 0 1 18.5 14z"/><path d="M12.5 13.5 9 19h3l-1 4.5 4.5-6.5h-3l1.5-3.5z"/>',
  snow: '<path d="M18.5 14H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 4.5 4.75 4.75 0 0 1 18.5 14z"/><g fill="currentColor"><circle cx="8.5" cy="18" r="1.3"/><circle cx="12.5" cy="20.5" r="1.3"/><circle cx="16.5" cy="18" r="1.3"/></g>',
  fog: '<g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 9h16M3 13h18M5 17h14"/></g>',
  wind: '<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 9h11a2.5 2.5 0 1 0-2.5-2.5M3 14h15a2.5 2.5 0 1 1-2.5 2.5M3 19h7"/></g>',
  hot: '<circle cx="12" cy="12" r="4.2"/><g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5"/></g>',
};
const WX_MAP = { 1: 'sun', 2: 'sun', 3: 'partly', 4: 'partly', 5: 'partly', 6: 'cloud', 7: 'cloud', 8: 'cloud', 11: 'fog', 12: 'rain', 13: 'rain', 14: 'partly', 15: 'storm', 16: 'storm', 17: 'partly',
  18: 'rain', 19: 'snow', 20: 'snow', 21: 'snow', 22: 'snow', 23: 'snow', 24: 'snow', 25: 'snow', 26: 'rain', 29: 'snow', 30: 'hot', 31: 'snow', 32: 'wind',
  33: 'moon', 34: 'moon', 35: 'partlyNight', 36: 'partlyNight', 37: 'fog', 38: 'cloud', 39: 'rain', 40: 'rain', 41: 'storm', 42: 'storm', 43: 'snow', 44: 'snow' };
export const wxIcon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'wx ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24">${WX[WX_MAP[n] || 'cloud']}</svg>`; return s; };
export const degF = (c) => (c == null ? null : c * 9 / 5 + 32);
export const fmtTemp = (v) => (v == null ? '–' : `${Math.round(v)}°`);
/** A bookmark's icon as homepage reads it: a full address, or a file name from the dashboard-icons collection. */
const bmIconUrl = (icon) => { if (!icon) return ''; if (/^https?:\/\//.test(icon)) return icon; const m = icon.match(/^([\w.-]+)\.(png|svg|webp)$/); return m ? `https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/${m[2]}/${m[1]}.${m[2]}` : ''; };
/** What to show for a link: the icon uploaded for it (served by this page) wins over the icon field. */
export const bmIcon = (l) => l.iconUrl || bmIconUrl(l.icon) || l.siteIcon || '';  // its own, else the site's (fetched by the server)
/** Links whose site icon the server is still fetching (iconPending): ask again shortly, a few times, and put the
 *  icons that arrived in place of the badges. `again` reads the links anew. */
export function bmIconsLater(el, links, again, n = 0) {
  if (n >= 4 || !links.some((l) => l.iconPending)) return;
  setTimeout(async () => {
    if (!el.isConnected) return;
    let now; try { now = await again(); } catch { return; }
    if (!el.isConnected) return;
    for (const l of now) {
      const ic = l.siteIcon && !l.iconPending ? el.querySelector(`[data-id="${l.id}"] > .bmic`) : null;
      if (ic && !ic.querySelector('img')) ic.replaceChildren(h('img', { src: l.siteIcon, alt: '', onerror: (e) => { e.target.replaceWith(l.abbr); } }));
    }
    bmIconsLater(el, now, again, n + 1);
  }, 2500 + n * 2500);
}
export const bmFlat = (items) => items.flatMap((x) => (x.type === 'folder' ? bmFlat(x.items) : [x]));

export const appName = (name, color) => h('span', { class: 'nm', style: { '--c': color } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'ap' }, name.replace(/^io/, '')));

// ------------------------------------------------------------------ state
export const S = { status: {}, user: null, settings: {}, apps: [] };

// ------------------------------------------------------------------ reordering by dragging
/** Reorder by dragging `handle` (mouse, pen or touch, through pointer events): `item` follows the pointer and the
    others make room; it can land in any of `lists()` (direct children matching `items`). `done(fromList, toList)` runs
    when the order changed. The handle also answers ArrowUp/ArrowDown from the keyboard, within its list. */
export function dragSort(handle, item, o) {
  handle.style.touchAction = 'none';
  const kids = (list) => [...list.children].filter((x) => x.matches(o.items));
  handle.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
    e.preventDefault();
    const list = item.parentNode, sib = e.key === 'ArrowUp' ? item.previousElementSibling : item.nextElementSibling;
    if (!sib || !sib.matches(o.items)) return;
    list.insertBefore(item, e.key === 'ArrowUp' ? sib : sib.nextSibling);
    o.done(list, list);
  });
  handle.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const from = item.parentNode, before = item.nextSibling;
    o.root.classList.add(o.sorting);  // groups fold to their headers while one is dragged
    item.classList.add('dragging');
    const top0 = item.getBoundingClientRect().top;
    const off = Math.min(e.clientY - top0, item.offsetHeight / 2);
    let y = e.clientY, scroll = 0;
    const place = () => {
      item.style.transform = '';
      const lists = o.lists();
      // the list under the pointer, else the nearest one
      let best = lists[0], dist = Infinity;
      for (const l of lists) {
        const r = l.getBoundingClientRect();
        const d = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
        if (d < dist) { dist = d; best = l; }
      }
      if (best) {
        const next = kids(best).find((k) => k !== item && y < k.getBoundingClientRect().top + k.offsetHeight / 2);
        if (next) { if (next !== item.nextElementSibling || item.parentNode !== best) best.insertBefore(item, next); }
        else if (item.parentNode !== best || kids(best).at(-1) !== item) best.append(item);
      }
      item.style.transform = `translateY(${y - off - item.getBoundingClientRect().top}px)`;
    };
    const tick = setInterval(() => { if (scroll) { window.scrollBy(0, scroll); place(); } }, 16);
    const still = (ev) => ev.preventDefault();
    const move = (ev) => {
      if (ev.pointerId !== e.pointerId) return;
      y = ev.clientY;
      scroll = y < 60 ? -12 : y > window.innerHeight - 60 ? 12 : 0;
      place();
    };
    const end = (ev) => {
      if (ev.pointerId !== e.pointerId) return;
      clearInterval(tick);
      removeEventListener('pointermove', move);
      removeEventListener('pointerup', end);
      removeEventListener('pointercancel', end);
      removeEventListener('touchmove', still);
      item.classList.remove('dragging');
      item.style.transform = '';
      o.root.classList.remove(o.sorting);
      if (ev.type === 'pointercancel') { from.insertBefore(item, before); return; }
      if (item.parentNode !== from || item.nextSibling !== before) o.done(from, item.parentNode);
    };
    // on the window, not the handle: moving the item in the page drops a pointer capture
    addEventListener('pointermove', move);
    addEventListener('pointerup', end);
    addEventListener('pointercancel', end);
    addEventListener('touchmove', still, { passive: false });  // no page scroll under the finger (iOS)
  });
}

// ------------------------------------------------------------------ sign-in
export function showSignIn() { frame.signInScreen({ api, name: 'Suite', first: !S.status.usersExist }); }

// ------------------------------------------------------------------ small things more than one part uses
/* /bookmarks is the Bookmarks page as an app of its own (its own name, icon and manifest: "Add to Home Screen" on an
   iPhone, "Install" on a desktop): the same page, opening on the bookmarks, with the start page a tap on the brand away. */
export const BM_APP = /\/bookmarks\/?$/.test(location.pathname);
export const dayKey = () => new Date().toDateString();

/* Type, and the box lists the bookmarks that match, what the apps find for this viewer (ioContact's people,
   ioCalendar's events, ioTask's tasks, ioRecipe's recipes, ioNote's notes, ioThings' things, ioDocs' documents, Home Assistant's things), and a row per app that searches
   itself (each opens on its own results). Arrows pick a row, Enter opens it, Escape clears. */
// Lower case without accents, so "celia" finds "Célia" (and "Celia" finds "célia"); a few letters NFD does not split.
const FOLD = { ß: 'ss', æ: 'ae', œ: 'oe', ø: 'o', ł: 'l', đ: 'd', ð: 'd', þ: 'th', ı: 'i' };
export const fold = (s) => String(s || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/[ßæœøłđðþı]/g, (c) => FOLD[c]);
/** An amount as the viewer's language writes money: "€42.50", "-$1,200.00"; without a currency, the number alone. */
export function money(v, cur, opts = {}) {
  if (v == null || isNaN(v)) return '';
  try { return new Intl.NumberFormat([], cur ? { style: 'currency', currency: cur, ...opts } : { minimumFractionDigits: 2, maximumFractionDigits: 2, ...opts }).format(v); } catch { return `${(+v).toFixed(2)}${cur ? ` ${cur}` : ''}`; }
}
export const pad2 = (n) => String(n).padStart(2, '0');
export const viewerTz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch { return ''; } };

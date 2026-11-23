/* The Feeds page (#/news) and the start page's Headlines card: the reader (iostart/news/__init__.py).

   Three panes on a wide screen (your feeds, the articles, the one being read), one at a time on a phone. The page
   keeps its place in the address (#/news/f/12, #/news/d/Tech, #/news/starred, #/news/a/<article>) without redrawing
   itself for it. */
import { confirmDialog, dialog, fail, fld, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, S } from './core.js';

/** "5 min", "3 h", "2 d", "12 Nov": how long ago, short. */
function ago(at) {
  const s = Date.now() / 1000 - at;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `${Math.round(s / 3600)} h`;
  if (s < 7 * 86400) return `${Math.round(s / 86400)} d`;
  const d = new Date(at * 1000);
  return d.toLocaleDateString([], d.getFullYear() === new Date().getFullYear() ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' });
}
const feedIcon = (f) => (f && f.icon ? h('img', { class: 'nwico', src: f.icon, alt: '', loading: 'lazy' }) : h('span', { class: 'nwico nwico-none' }, icon('rss', 's')));

// ------------------------------------------------------------------ the start page's card

/** The newest unread headlines of the feeds the person keeps on the start page; nothing at all for someone who
    follows no feed (the gear menu's Feeds is where to start). */
export async function drawNewsCard(el, keep = false) {
  let d;
  try { d = await api('api/news/card?n=8'); } catch { d = { feeds: 0, items: [], unread: 0 }; }
  if (!el.isConnected) return;
  el.hidden = !d.feeds && !keep;  // keep: the page is being arranged, and the card has to be there to be moved or taken off
  if (!d.feeds) { el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, 'Headlines')), h('div', { class: 'muted small' }, 'The newest articles of the feeds you follow (gear menu, Feeds).')); return; }
  const head = h('div', { class: 'wghead' }, h('span', null, 'Headlines'),
    h('a', { class: 'showall', href: '#/news', title: 'Open the reader' }, d.unread > d.items.length ? `${d.unread} unread` : 'All feeds'));
  const rows = d.items.map((it) => h('a', { class: 'nwline', href: `#/news/a/${it.id}`, title: it.text || it.title },
    h('span', { class: 'nwline-title' }, it.title), h('span', { class: 'nwline-by muted' }, `${it.feed} · ${ago(it.at)}`)));
  el.replaceChildren(head, h('div', { class: 'rows nwlines' }, rows.length ? rows : h('div', { class: 'muted small' }, 'Nothing new. You have read it all.')));
}

// ------------------------------------------------------------------ the page

export async function showNews(page, r) {
  if (!['member', 'editor', 'admin'].includes(S.user.role)) {
    page.append(h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: '#/', title: 'Back to the start page', 'aria-label': 'Back to the start page' }, icon('left')), h('h1', null, 'Feeds')),
      h('div', { class: 'empty' }, 'A viewer cannot follow feeds. Ask an admin to make you a member.'));
    return;
  }
  // what is shown: scope {kind: all | starred | feed | folder, id}, show: unread | all, q; the article open; the panes
  const st = { scope: { kind: 'all' }, show: 'unread', q: '', over: { feeds: [], folders: [], unread: 0, starred: 0 }, items: [], next: null, open: null, loading: false, seq: 0 };
  if (r.b === 'f' && r.c) st.scope = { kind: 'feed', id: +r.c };
  else if (r.b === 'd' && r.c) st.scope = { kind: 'folder', id: r.c };
  else if (r.b === 'starred') st.scope = { kind: 'starred' };

  const side = h('nav', { class: 'nwside', 'aria-label': 'Your feeds' }), list = h('div', { class: 'nwlist' }), art = h('article', { class: 'nwart' });
  const root = h('div', { class: 'news', 'data-pane': 'list' }, side, list, art);
  const pane = (p) => { root.dataset.pane = p; };
  page.classList.add('newspage');
  page.append(h('div', { class: 'pagehead nwhead' },
    h('a', { class: 'iconbtn', href: '#/', title: 'Back to the start page', 'aria-label': 'Back to the start page' }, icon('left')),
    h('h1', null, 'Feeds'),
    h('button', { class: 'pillbtn nwfeedsbtn', onclick: () => pane(root.dataset.pane === 'side' ? 'list' : 'side') }, icon('folder', 's'), 'Your feeds'),
    h('button', { class: 'pillbtn primary nwadd', onclick: () => follow() }, icon('add', 's'), 'Follow'),
    h('button', { class: 'iconbtn', title: 'Look for new articles now', 'aria-label': 'Look for new articles now', onclick: (e) => refreshNow(e.currentTarget) }, icon('update', 's')),
    moreMenu()), root);

  const place = () => {  // the address follows what is shown, without the page being drawn again for it
    const s = st.scope, hash = st.open ? `#/news/a/${st.open.id}` : s.kind === 'feed' ? `#/news/f/${s.id}` : s.kind === 'folder' ? `#/news/d/${encodeURIComponent(s.id)}` : s.kind === 'starred' ? '#/news/starred' : '#/news';
    if (location.hash !== hash) history.replaceState(null, '', hash);
  };
  const feedOf = (id) => st.over.feeds.find((f) => f.id === id);
  const scopeName = () => { const s = st.scope; return s.kind === 'feed' ? (feedOf(s.id) || {}).title || 'Feed' : s.kind === 'folder' ? s.id : s.kind === 'starred' ? 'Starred' : 'All feeds'; };
  const scopeQuery = () => { const s = st.scope, p = new URLSearchParams({ show: s.kind === 'starred' ? 'starred' : st.q ? 'all' : st.show });
    if (s.kind === 'feed') p.set('feed', s.id); if (s.kind === 'folder') p.set('folder', s.id); if (st.q) p.set('q', st.q); return p; };

  // ---- the feeds
  async function loadOver() { st.over = await api('api/news'); drawSide(); }
  function drawSide() {
    const o = st.over, s = st.scope;
    const row = (on, kids, go, extra) => h('div', { class: `nwrow${on ? ' on' : ''}` }, h('button', { class: 'nwrow-go', onclick: go }, kids), extra);
    const count = (n) => (n ? h('span', { class: 'nwcount' }, n > 999 ? '999+' : n) : null);
    const pick = (scope) => () => { st.scope = scope; st.open = null; st.q = ''; pane('list'); drawSide(); loadItems(); };
    const feedRow = (f) => row(s.kind === 'feed' && s.id === f.id, [feedIcon(f), h('span', { class: 'nwname' }, f.title),
      f.error ? h('span', { class: 'nwerr', title: `Not read the last time: ${f.error}` }, icon('warn', 's')) : null, count(f.unread)], pick({ kind: 'feed', id: f.id }),
      h('button', { class: 'iconbtn nwedit', title: `Rename, move or stop following ${f.title}`, 'aria-label': `Edit ${f.title}`, onclick: () => editFeed(f) }, icon('more', 's')));
    const loose = o.feeds.filter((f) => !f.folder);
    side.replaceChildren(...[
      row(s.kind === 'all', [icon('rss', 's'), h('span', { class: 'nwname' }, 'All feeds'), count(o.unread)], pick({ kind: 'all' })),
      row(s.kind === 'starred', [icon('star', 's'), h('span', { class: 'nwname' }, 'Starred'), o.starred ? h('span', { class: 'nwcount quiet' }, o.starred) : null], pick({ kind: 'starred' })),
      o.folders.map((name) => { const fs = o.feeds.filter((f) => f.folder === name);
        return [row(s.kind === 'folder' && s.id === name, [icon('folder', 's'), h('span', { class: 'nwname nwfolder' }, name), count(fs.reduce((n, f) => n + f.unread, 0))], pick({ kind: 'folder', id: name }),
          h('button', { class: 'iconbtn nwedit', title: `Rename the folder ${name}`, 'aria-label': `Rename the folder ${name}`, onclick: () => renameFolder(name) }, icon('edit', 's'))),
        h('div', { class: 'nwin' }, fs.map(feedRow))]; }),
      loose.length && o.folders.length ? h('div', { class: 'nwsep' }) : null, loose.map(feedRow),
      o.feeds.length ? null : h('div', { class: 'muted small nwnone' }, 'No feeds yet. Follow a site to start.')].flat(Infinity).filter(Boolean));
  }

  // ---- the articles
  const listHead = h('div', { class: 'nwlhead' }), rows = h('div', { class: 'nwrows' }), tail = h('div', { class: 'nwtail' });
  list.append(listHead, rows, tail);
  const q = h('input', { class: 't nwq', type: 'search', placeholder: 'Search the articles', autocomplete: 'off', enterkeyhint: 'search', 'aria-label': 'Search the articles' });
  let qTimer;
  q.addEventListener('input', () => { clearTimeout(qTimer); qTimer = setTimeout(() => { st.q = q.value.trim(); loadItems(); }, 250); });
  function drawListHead() {
    const starred = st.scope.kind === 'starred';
    const tab = (v, label) => h('button', { class: `nwtab${st.show === v ? ' on' : ''}`, onclick: () => { st.show = v; loadItems(); } }, label);
    if (q.value.trim() !== st.q) q.value = st.q;
    listHead.replaceChildren(h('div', { class: 'nwltitle' }, h('h2', null, scopeName()),
      starred || st.q ? null : h('div', { class: 'nwtabs', role: 'group', 'aria-label': 'Which articles' }, tab('unread', 'Unread'), tab('all', 'All')),
      starred ? null : h('button', { class: 'iconbtn', title: 'Mark all of these as read', 'aria-label': 'Mark all of these as read', onclick: markAll }, icon('doneall', 's'))),
    h('div', { class: 'bmsearch nwsearch' }, icon('search', 's'), q));
  }
  const itemRow = (it) => {
    const el = h('button', { class: `nwitem${it.read ? ' read' : ''}${st.open && st.open.id === it.id ? ' on' : ''}`, 'data-id': it.id, onclick: () => openItem(it) },
      h('span', { class: 'nwitem-main' }, h('span', { class: 'nwitem-title' }, it.starred ? icon('star', 's') : null, it.title),
        h('span', { class: 'nwitem-by muted' }, `${it.feed} · ${ago(it.at)}`), it.text ? h('span', { class: 'nwitem-text muted' }, it.text) : null),
      it.image ? h('img', { class: 'nwthumb', src: it.image, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer', onerror: (e) => e.target.remove() }) : null);
    return el;
  };
  async function loadItems(more = false) {
    const seq = ++st.seq;
    if (!more) { st.items = []; st.next = null; rows.replaceChildren(); tail.replaceChildren(h('div', { class: 'muted small' }, 'Loading…')); drawListHead(); place(); }
    st.loading = true;
    const p = scopeQuery();
    if (more && st.next) p.set('before', st.next);
    let got;
    try { got = await api(`api/news/items?${p}`); } catch (e) { if (seq === st.seq) { st.loading = false; tail.replaceChildren(h('div', { class: 'muted small' }, e.message)); } return; }
    if (seq !== st.seq || !list.isConnected) return;
    st.loading = false; st.next = got.next;
    st.items.push(...got.items);
    rows.append(...got.items.map(itemRow));
    const none = st.q ? 'No article has those words.' : st.scope.kind === 'starred' ? 'Nothing starred yet. The star on an article keeps it here.' : !st.over.feeds.length ? 'Follow a site, and its articles come here.'
      : st.show === 'unread' ? 'Nothing new. You have read it all.' : 'No articles yet.';
    tail.replaceChildren(st.items.length ? (st.next ? h('button', { class: 'pillbtn noic', onclick: () => loadItems(true) }, 'More') : h('div', { class: 'muted small' }, 'That is all.')) : h('div', { class: 'empty' }, none));
  }
  new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting) && st.next && !st.loading) loadItems(true); }, { root: list, rootMargin: '300px' }).observe(tail);

  const rowOf = (id) => rows.querySelector(`.nwitem[data-id="${id}"]`);
  /** Counts on the left, after an article changed between read and not read. */
  function bump(it, by) { const f = feedOf(it.feedId); if (f) f.unread = Math.max(0, f.unread + by); st.over.unread = Math.max(0, st.over.unread + by); drawSide(); }
  async function setRead(it, read) {
    if (it.read === read) return;
    it.read = read; bump(it, read ? -1 : 1);
    const el = rowOf(it.id); if (el) el.classList.toggle('read', read);
    try { await api('api/news/items/mark', { json: { ids: [it.id], read } }); } catch (e) { fail(e); }
  }
  async function setStar(it, on) {
    it.starred = on; st.over.starred = Math.max(0, st.over.starred + (on ? 1 : -1)); drawSide();
    const el = rowOf(it.id); if (el) el.replaceWith(itemRow(it));
    if (st.open && st.open.id === it.id) drawArticle(st.open);
    try { await api('api/news/items/mark', { json: { ids: [it.id], starred: on } }); } catch (e) { fail(e); }
  }
  async function markAll() {
    const s = st.scope, top = st.items.reduce((m, it) => Math.max(m, it.id), 0);
    if (!st.over.unread) return;
    if (s.kind === 'all' && st.over.unread > 30 && !await confirmDialog('Mark everything as read?', `${st.over.unread} articles in all your feeds will count as read.`, 'Mark as read')) return;
    try {
      // up to the newest article this page shows: what arrived meanwhile stays unread (the whole scope when the page lists none)
      await api('api/news/read', { json: { ...(s.kind === 'feed' ? { feed: s.id } : s.kind === 'folder' ? { folder: s.id } : {}), ...(top ? { upto: top } : {}) } });
      await loadOver(); await loadItems();
    } catch (e) { fail(e); }
  }

  // ---- the article
  function drawArticle(a) {
    const it = st.items.find((x) => x.id === a.id) || a, i = st.items.findIndex((x) => x.id === a.id);
    const step = (d) => { const n = st.items[i + d]; if (n) openItem(n); };
    const body = h('div', { class: 'nwbody' });
    body.innerHTML = a.html || '';  // cleaned by the server (iostart/news/read.py): only an article's tags, links and pictures to http(s)
    for (const img of body.querySelectorAll('img')) img.addEventListener('error', () => img.remove());
    const lead = a.image && !body.querySelector('img') ? h('img', { class: 'nwlead', src: a.image, alt: '', referrerpolicy: 'no-referrer', onerror: (e) => e.target.remove() }) : null;
    art.replaceChildren(
      h('div', { class: 'nwbar' },
        h('button', { class: 'iconbtn nwback', title: 'Back to the list', 'aria-label': 'Back to the list', onclick: closeItem }, icon('left')),
        h('button', { class: `iconbtn${it.starred ? ' nwstarred' : ''}`, title: it.starred ? 'Take the star off' : 'Star: keep this article', 'aria-label': 'Star', 'aria-pressed': String(!!it.starred), onclick: () => setStar(it, !it.starred) }, icon('star')),
        h('button', { class: 'iconbtn', title: 'Mark as not read', 'aria-label': 'Mark as not read', onclick: () => { setRead(it, false); closeItem(); } }, icon('unread')),
        a.link ? h('a', { class: 'pillbtn nwopen', href: a.link, target: '_blank', rel: 'noopener noreferrer' }, icon('tabs', 's'), 'Open the page') : null,
        h('span', { class: 'nwsp' }),
        h('button', { class: 'iconbtn', title: 'The article before (k)', 'aria-label': 'The article before', disabled: i <= 0, onclick: () => step(-1) }, icon('up')),
        h('button', { class: 'iconbtn', title: 'The next article (j)', 'aria-label': 'The next article', disabled: i < 0 || i >= st.items.length - 1, onclick: () => step(1) }, icon('down'))),
      h('div', { class: 'nwread' },
        h('h1', null, a.link ? h('a', { href: a.link, target: '_blank', rel: 'noopener noreferrer' }, a.title) : a.title),
        h('div', { class: 'nwmeta muted' }, [a.feed, a.author, new Date(a.at * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })].filter(Boolean).join(' · ')),
        a.audio ? h('audio', { class: 'nwaudio', src: a.audio, controls: true, preload: 'none' }) : null,
        lead, body));
    art.scrollTop = 0;
  }
  async function openItem(it) {
    for (const el of rows.querySelectorAll('.nwitem.on')) el.classList.remove('on');
    const el = rowOf(it.id); if (el) { el.classList.add('on'); el.scrollIntoView({ block: 'nearest' }); }
    let a;
    try { a = await api(`api/news/items/${it.id}`); } catch (e) { fail(e); return; }
    st.open = a; pane('art'); place();
    drawArticle(a);
    setRead(st.items.find((x) => x.id === it.id) || it, true);
  }
  function closeItem() {
    st.open = null; pane('list'); place();
    for (const el of rows.querySelectorAll('.nwitem.on')) el.classList.remove('on');
    art.replaceChildren(h('div', { class: 'empty nwpick' }, 'Pick an article to read it here.'));
  }

  // ---- following, changing, the file of feeds
  const folderField = (v) => { const id = 'nwfolders', inp = h('input', { class: 't', value: v || '', list: id, placeholder: 'None', maxlength: 100 });
    return [inp, h('datalist', { id }, st.over.folders.map((f) => h('option', { value: f })))]; };
  async function follow() {
    const url = h('input', { class: 't', type: 'url', inputmode: 'url', placeholder: 'example.com', autocapitalize: 'off', spellcheck: 'false' }), [folder, dl] = folderField(st.scope.kind === 'folder' ? st.scope.id : '');
    const ok = await dialog('Follow a site', h('div', null, h('p', { class: 'muted small' }, 'The address of a site, a blog, a YouTube channel or a podcast. The feed is found for you when the site has one.'),
      fld('Address', url), fld('Folder', folder), dl), [{ label: 'Cancel', value: false }, { label: 'Follow', value: true, primary: true }]);
    if (!ok || !url.value.trim()) return;
    toast('Looking for the feed…');
    try {
      const got = await api('api/news/feeds', { json: { url: url.value.trim(), folder: folder.value } });
      toast(got.new ? `Following ${got.feed.title}` : `You follow ${got.feed.title} already`);
      st.scope = { kind: 'feed', id: got.feed.id }; st.open = null; st.show = 'unread';
      await loadOver(); await loadItems();
    } catch (e) { fail(e); }
  }
  async function editFeed(f) {
    const name = h('input', { class: 't', value: f.title, placeholder: f.feedTitle || '' }), [folder, dl] = folderField(f.folder);
    const start = h('input', { type: 'checkbox', checked: f.onStart });
    const what = await dialog(f.title, h('div', null, fld('Name', name), fld('Folder', folder), dl,
      h('label', { class: 'check' }, start, 'Its headlines on the start page'),
      h('p', { class: 'muted small nwaddr' }, f.url), f.error ? h('p', { class: 'small nwerrline' }, `Not read the last time: ${f.error}`) : null),
    [{ label: 'Stop following', value: 'remove', danger: true }, { label: 'Cancel', value: false }, { label: 'Save', value: 'save', primary: true }]);
    try {
      if (what === 'remove') {
        if (!await confirmDialog(`Stop following ${f.title}?`, 'Its articles go from your reader, the starred ones too.', 'Stop following', true)) return;
        await api(`api/news/feeds/${f.id}`, { method: 'DELETE' });
        if (st.scope.kind === 'feed' && st.scope.id === f.id) st.scope = { kind: 'all' };
      } else if (what === 'save') {
        await api(`api/news/feeds/${f.id}`, { method: 'PATCH', json: { title: name.value.trim() === (f.feedTitle || '') ? '' : name.value, folder: folder.value, onStart: start.checked } });
      } else return;
      await loadOver(); await loadItems();
    } catch (e) { fail(e); }
  }
  async function renameFolder(name) {
    const to = h('input', { class: 't', value: name, maxlength: 100 });
    const ok = await dialog('Rename the folder', h('div', null, fld('Name', to), h('p', { class: 'muted small' }, 'Without a name, its feeds leave the folder.')),
      [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }]);
    if (!ok || to.value.trim() === name) return;
    try {
      await api('api/news/folders/rename', { json: { from: name, to: to.value } });
      if (st.scope.kind === 'folder' && st.scope.id === name) st.scope = to.value.trim() ? { kind: 'folder', id: to.value.trim() } : { kind: 'all' };
      await loadOver(); await loadItems();
    } catch (e) { fail(e); }
  }
  async function refreshNow(btn) {
    if (btn) btn.disabled = true;
    try {
      const got = await api(st.scope.kind === 'feed' ? `api/news/feeds/${st.scope.id}/refresh` : 'api/news/refresh', { method: 'POST' });
      toast(got.new ? `${got.new} new article${got.new === 1 ? '' : 's'}` : 'Nothing new');
      await loadOver(); if (got.new && !st.open) await loadItems();
    } catch (e) { fail(e); }
    if (btn) btn.disabled = false;
  }
  function moreMenu() {
    const file = h('input', { type: 'file', accept: '.opml,.xml,text/xml,text/x-opml', hidden: true, onchange: async () => {
      const f = file.files[0]; file.value = '';
      if (!f) return;
      try {
        const got = await api('api/news/opml', { method: 'POST', body: f, headers: { 'Content-Type': 'text/x-opml' } });
        toast(got.added ? `Following ${got.added} more feed${got.added === 1 ? '' : 's'}. Their articles arrive over the next minutes.` : 'You follow all of these already');
        await loadOver(); await loadItems();
      } catch (e) { fail(e); }
    } });
    let menu = null;
    const wrap = h('span', { class: 'nwmore' });
    const close = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
    const outside = (e) => { if (menu && !wrap.contains(e.target)) close(); };
    const btn = h('button', { class: 'iconbtn', title: 'Import and export', 'aria-label': 'Import and export', onclick: () => {
      if (menu) return close();
      menu = h('div', { class: 'menu' },
        h('button', { class: 'mi', onclick: () => { close(); file.click(); } }, icon('add', 's'), 'Import feeds from another reader (OPML)'),
        h('a', { class: 'mi', href: 'api/news/opml', download: 'iostart-feeds.opml', onclick: close }, icon('download', 's'), 'Export your feeds (OPML)'));
      wrap.append(menu); setTimeout(() => document.addEventListener('click', outside), 0);
    } }, icon('more', 's'));
    wrap.append(btn, file);
    return wrap;
  }

  // ---- keys: j / k the next and the one before, s star, m read or not, o the page itself, Escape back to the list
  const onKey = (e) => {
    if (!root.isConnected) { document.removeEventListener('keydown', onKey); return; }
    if (e.metaKey || e.ctrlKey || e.altKey || document.querySelector('.dialog-back') || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target.tagName || ''))) return;
    const i = st.open ? st.items.findIndex((x) => x.id === st.open.id) : -1, it = i >= 0 ? st.items[i] : null;
    if (e.key === 'j' || e.key === 'k') { const n = st.items[i < 0 ? 0 : i + (e.key === 'j' ? 1 : -1)]; if (n) { e.preventDefault(); openItem(n); } }
    else if (e.key === 's' && it) setStar(it, !it.starred);
    else if (e.key === 'm' && it) setRead(it, !it.read);
    else if (e.key === 'o' && st.open && st.open.link) window.open(st.open.link, '_blank', 'noopener');
    else if (e.key === 'Escape' && st.open) closeItem();
  };
  document.addEventListener('keydown', onKey);

  closeItem();
  try { await loadOver(); } catch (e) { fail(e); }
  await loadItems();
  if (r.b === 'a' && r.c) { const it = st.items.find((x) => String(x.id) === r.c) || { id: +r.c }; if (it.id) await openItem(it); }
  // back on the tab: the counts as they are now (the list stays, so what is being read does not jump)
  S.refresh = () => { loadOver().catch(() => {}); };
}

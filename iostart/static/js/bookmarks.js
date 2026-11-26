/* The Bookmarks page (#/bookmarks): the tree, what of it is on the start page, sync, Tidy up, files in and out. */
import { confirmDialog, dialog, fail, fld, icon, toast } from '../../api/auth/frame.js';
import { h } from '../../api/auth/ui.js';
import { api, BM_APP, bmFlat, bmIcon, bmIconsLater, dragSort, fold, S } from './core.js';

// ------------------------------------------------------------------ the Bookmarks page (#/bookmarks)
/* The Bookmarks page (#/bookmarks, from the start page and the gear menu): the whole tree (folders in folders, as a
   browser keeps them), what of it is on the start page (the house on a folder or on a single link), the addresses a
   sync app needs, and files in and out. Each person sees their own bookmarks and the shared ones (the people icon);
   members, editors and admins keep their own, and the start page's admins share them and change the shared ones. */
export async function showBookmarks(page) {
  const canEdit = ['member', 'editor', 'admin'].includes(S.user.role);
  const body = h('div');
  // the search box: as you type, the links that match (name, address, description, folder), wherever they are
  const q = h('input', { class: 't bmq', type: 'search', placeholder: 'Search the bookmarks', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', enterkeyhint: 'search', 'aria-label': 'Search the bookmarks' });
  q.addEventListener('input', () => body.bmPaint && body.bmPaint());
  q.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && q.value) { e.stopPropagation(); q.value = ''; body.bmPaint && body.bmPaint(); }
    if (e.key === 'Enter') { const a = body.querySelector('.bmrow a.bmname'); if (a) { e.preventDefault(); a.click(); } }  // the first match
  });
  body.bmQuery = () => q.value.trim();
  page.append(h('div', { class: 'pagehead bmpagehead' },
    BM_APP ? null : h('a', { class: 'iconbtn', href: '#/', title: 'Back to the start page', 'aria-label': 'Back to the start page' }, icon('left')),
    h('h1', null, 'Bookmarks'),
    canEdit ? h('button', { class: 'pillbtn primary bmaddtop', onclick: () => body.bmAdd && body.bmAdd() }, icon('add', 's'), 'Link') : null,
    canEdit ? h('button', { class: 'pillbtn bmtidybtn', title: 'Links that no longer work, and the same address kept twice', 'aria-label': 'Tidy up the bookmarks', onclick: () => bmTidy(tidy, () => body.bmDraw && body.bmDraw()) }, icon('broom', 's'), h('span', null, 'Tidy up')) : null,
    h('a', { class: 'iconbtn', href: '#/settings/bookmarks', title: 'Sync with browsers, on a phone, import and export (Settings › Bookmarks)', 'aria-label': 'Bookmark settings' }, icon('settings', 's')),
    h('div', { class: 'bmsearch' }, icon('search', 's'), q)));
  const tidy = h('div', { class: 'bmtidyhost', hidden: true });
  page.append(tidy, body);
  await setBookmarks(body);
  // back to the app (from a tab it opened, or the home screen): the tree as it is now, as the start page does
  S.refresh = () => body.bmDraw && body.bmDraw();
}
/** Running as an app from the home screen (or installed), without the browser around it. */
const standalone = () => navigator.standalone === true || matchMedia('(display-mode: standalone)').matches;
const bmOpen = new Set();  // the folders unfolded, kept while the page is open
async function setBookmarks(el) {
  let tree = null;
  const draw = async () => {
    tree = await api('api/bookmarks/tree');
    if (!el.isConnected) return;
    paint();
    const mine = el.bmDrawn = {};  // a later draw makes the wait for icons of this one moot
    bmIconsLater(el, bmFlat(tree.items), async () => (el.bmDrawn === mine ? bmFlat((await api('api/bookmarks/tree')).items) : []));
  };
  // the search box redraws from the tree in hand; changes fetch it again (draw)
  const paint = () => {
    if (!tree || !el.isConnected) return;
    const canEdit = !!tree.canEdit, canShare = !!tree.canShare;
    const query = el.bmQuery ? fold(el.bmQuery()) : '';
    const call = async (path, opts, msg) => { try { await api(path, opts); if (msg) toast(msg); } catch (e) { fail(e); } await draw(); };
    // every folder, for the "Folder" choice of a link: the top level, then each with its path
    const folders = [{ id: 0, label: 'Top level' }];
    const where = new Map();  // a link's id: its folder and the folder's path, for the search results
    const walk = (items, path, parent) => {
      for (const x of items) {
        if (x.type === 'folder') { folders.push({ id: x.id, label: [...path, x.name].join(' › ') }); walk(x.items, [...path, x.name], x); }
        else where.set(x.id, { f: parent, path: path.join(' › ') });
      }
    };
    walk(tree.items, [], null);
    const few = tree.count <= 60;  // a small tree shows unfolded; a browser's whole menu starts folded
    const isOpen = (f) => bmOpen.has(f.id) || (few && !bmOpen.has(-f.id));
    const linkForm = (gid, l) => {
      const name = h('input', { class: 't', value: l ? l.name : '', placeholder: 'Name' }), href = h('input', { class: 't', value: l ? l.href : '', placeholder: 'https://…' });
      const abbr = h('input', { class: 't', value: l ? l.abbr : '', placeholder: 'Two letters (from the name when empty)', maxlength: 4 });
      const desc = h('input', { class: 't', value: l ? l.customDescription : '', placeholder: 'Line under the name (the host name when empty)' });
      const ic = h('input', { class: 't', value: l ? l.icon : '', placeholder: 'The site\'s own icon when empty; or an image address, or a dashboard-icons name (github.png)' });
      const grp = h('select', { class: 't' }, folders.map((x) => h('option', { value: x.id, selected: x.id === gid ? true : null }, x.label)));
      // an icon of your own (an SVG, or a PNG), kept in the database: it wins over the icon field
      const file = h('input', { type: 'file', accept: '.svg,.png,image/svg+xml,image/png', class: 't' });
      const drop = h('input', { type: 'checkbox' });
      const upload = h('div', { class: 'upload' }, l && l.iconUrl ? h('img', { src: l.iconUrl, alt: '', class: 'bmprev' }) : null, file,
        l && l.iconUrl ? h('label', { class: 'small' }, drop, ' Remove the uploaded icon') : null);
      Object.assign(href, { type: 'url', inputMode: 'url', autocapitalize: 'off', spellcheck: false }); href.setAttribute('autocorrect', 'off');
      name.placeholder = 'Name (the site\'s address when empty)';
      // what a phone rarely needs folds away: open when the link already has some of it
      const more = h('details', { class: 'bmmoreform', open: l && (l.customDescription || l.icon || l.iconUrl) ? true : null },
        h('summary', { class: 'muted small' }, 'Abbreviation, description and icon'),
        h('div', { class: 'grid' }, fld('Abbreviation', abbr), fld('Description', desc), fld('Icon', ic), h('div', { class: 'field' }, h('span', null, 'Upload an icon (SVG is best, or PNG)'), upload)));
      const hostOf = (u) => { try { return new URL(/^[a-z][a-z0-9+.-]*:/i.test(u) ? u : `https://${u}`).hostname.replace(/^www\./, ''); } catch { return u; } };
      return { body: h('div', null, h('div', { class: 'grid' }, fld('Address', href), fld('Name', name), fld('Folder', grp)), more),
        value: () => ({ name: name.value.trim() || hostOf(href.value.trim()), href: href.value.trim(), abbr: abbr.value, description: desc.value, icon: ic.value, groupId: +grp.value }), file: () => file.files[0], drop: () => drop.checked };
    };
    const editLink = async (gid, l) => {
      const f = linkForm(gid, l);
      const v = await dialog(l ? 'Change the link' : 'New link', f.body, [{ label: 'Cancel', value: null }, { label: l ? 'Save' : 'Add', value: () => ({ link: f.value(), file: f.file(), drop: f.drop() }), primary: true }]);
      if (!v) return;
      try {
        const saved = await api(l ? `api/bookmarks/links/${l.id}` : `api/bookmarks/groups/${v.link.groupId}/links`, { method: l ? 'PATCH' : 'POST', json: v.link });
        if (v.file) await api(`api/bookmarks/links/${saved.id}/icon`, { method: 'PUT', body: v.file, headers: { 'Content-Type': v.file.type || 'application/octet-stream' } });
        else if (v.drop) await api(`api/bookmarks/links/${saved.id}/icon`, { method: 'DELETE' });
        toast('Saved');
      } catch (e) { fail(e); }
      await draw();
    };
    const newFolder = async (parentId) => {
      const i = h('input', { class: 't', placeholder: 'Name, e.g. Developer' });
      const st = h('input', { type: 'checkbox', checked: true });
      const v = await dialog('New folder', h('div', null, fld('Name', i), h('label', { class: 'check' }, st, 'Show it on the start page')), [{ label: 'Cancel', value: null }, { label: 'Add', value: () => ({ name: i.value, start: st.checked }), primary: true }]);
      if (v && v.name.trim()) { bmOpen.add(parentId); await call('api/bookmarks/groups', { method: 'POST', json: { ...v, parentId } }, 'Folder made'); }
    };
    const grip = (title, kind, x) => (canEdit && x.canChange ? h('button', { class: 'iconbtn grip', title, 'aria-label': title, 'data-kind': kind }, icon('grip', 's'))
      : canEdit ? h('span', { class: 'gripgap' }) : null);
    // shared with everyone: a toggle for the start page's admins, a mark for everyone else
    const shareAct = (x, path) => ({ label: x.shared ? 'Stop sharing (yours only)' : 'Share with everyone', icon: 'people', hidden: !canShare,
      run: () => call(path, { method: 'PATCH', json: { shared: !x.shared } }, x.shared ? 'Yours only now' : 'Shared with everyone') });
    const share = (x, path) => (canShare
      ? h('button', { class: `iconbtn bmshare${x.shared ? ' on' : ''}`, title: x.shared ? 'Shared with everyone: click to make it yours only' : 'Yours only: click to share it with everyone', 'aria-label': 'Shared with everyone', 'aria-pressed': x.shared ? 'true' : 'false', onclick: shareAct(x, path).run }, icon('people', 's'))
      : x.shared ? h('span', { class: 'bmshared', title: 'Shared with everyone, kept by an admin' }, icon('people', 's')) : null);
    // the house: lit when the folder (its links, as a group) or the link is on the start page
    const house = (on, title, click, disabled) => h('button', { class: `iconbtn bmstart${on ? ' on' : ''}`, title, 'aria-label': title, 'aria-pressed': on ? 'true' : 'false', disabled: disabled ? true : null, onclick: click }, icon('home', 's'));
    // a link's and a folder's tools: buttons in the row, or (on a phone) behind one ⋯ button, as a list to tap
    const linkActions = (l, f) => {
      const a = {
        open: { label: 'Open', icon: 'web', run: () => window.open(l.href, '_blank', 'noreferrer'), hidden: !l.linkable },
        start: { label: l.onStart ? 'Take it off the start page' : 'Show it on the start page', icon: 'home', disabled: !l.linkable, run: () => {
          const want = !l.onStart;  // as its folder when that already says so, else this link's own choice
          call(`api/bookmarks/links/${l.id}`, { method: 'PATCH', json: { start: want === !!(f && f.start) ? null : want } });
        } },
        share: shareAct(l, `api/bookmarks/links/${l.id}`),
        change: { label: 'Change', icon: 'edit', run: () => editLink(f ? f.id : 0, l), hidden: !l.canChange },
        copy: { label: 'Copy the address', icon: 'copy', run: async () => { try { await navigator.clipboard.writeText(l.href); toast('Copied'); } catch { toast(l.href); } } },
        del: { label: 'Delete', icon: 'delete', danger: true, hidden: !l.canChange, run: async () => { if (await confirmDialog('Delete the link', `Delete "${l.name || l.href}"? ${l.shared ? 'It is shared: everyone loses it, and so do the browsers that sync.' : 'Browsers that sync lose it too.'}`, 'Delete', true)) call(`api/bookmarks/links/${l.id}`, { method: 'DELETE' }, 'Deleted'); } },
      };
      return Object.assign(Object.values(a).filter((x) => !x.hidden), a);
    };
    const moreBtn = (title, actions) => h('button', { class: 'iconbtn bmmore', title: 'More', 'aria-label': `More: ${title}`, onclick: () => sheet(title, actions) }, icon('more', 's'));
    const linkRow = (l, f, path) => h('div', { class: `bmrow${l.onStart ? '' : ' off'}`, 'data-id': l.id }, path === undefined ? grip('Drag to move the link', 'link', l) : null,
      h('span', { class: 'bmic' }, bmIcon(l) ? h('img', { src: bmIcon(l), alt: '', onerror: (e) => { e.target.replaceWith(l.abbr); } }) : l.abbr), l.linkable ? h('a', { class: 'bmname', href: l.href, target: '_blank', rel: 'noreferrer', title: l.href }, l.name || l.href) : h('span', { class: 'bmname', title: l.href }, l.name || l.href),
      h('span', { class: 'muted small bmdesc' }, path === undefined ? l.description : path || 'Top level'),
      !canEdit && !l.shared ? null : h('span', { class: 'bmtools' },
        share(l, `api/bookmarks/links/${l.id}`),
        house(l.onStart, !l.linkable ? 'Only web addresses can go on the start page' : (l.onStart ? 'On the start page: click to take it off' : 'Not on the start page: click to show it') + (l.shared && !canShare ? ' (yours only)' : ''), linkActions(l, f).start.run, !l.linkable),
        l.canChange ? h('button', { class: 'iconbtn', title: 'Change', onclick: () => editLink(f ? f.id : 0, l) }, icon('edit', 's')) : null,
        l.canChange ? h('button', { class: 'iconbtn', title: 'Delete', onclick: linkActions(l, f).del.run }, icon('delete', 's')) : null),
      l.shared ? h('span', { class: 'bmsharedtag', title: 'Shared with everyone' }, icon('people', 's')) : null,
      canEdit || l.shared ? moreBtn(l.name || l.href, linkActions(l, f)) : null);
    const count = (f) => f.items.reduce((n, x) => n + (x.type === 'folder' ? count(x) : 1), 0);
    const folderActions = (f, n) => [
      { label: f.start ? 'Take it off the start page' : 'Show it on the start page', icon: 'home', run: () => call(`api/bookmarks/groups/${f.id}`, { method: 'PATCH', json: { start: !f.start } }) },
      shareAct(f, `api/bookmarks/groups/${f.id}`),
      { label: `Open all ${f.items.filter((x) => x.type === 'bookmark' && x.linkable).length} in tabs`, icon: 'tabs', hidden: f.items.filter((x) => x.type === 'bookmark' && x.linkable).length < 2, run: () => openAll(f.name, f.items.filter((x) => x.type === 'bookmark' && x.linkable)) },
      { label: 'Add a link', icon: 'add', hidden: !canEdit, run: () => { bmOpen.add(f.id); bmOpen.delete(-f.id); editLink(f.id, null); } },
      { label: 'Add a folder inside', icon: 'folder', hidden: !canEdit, run: () => { bmOpen.delete(-f.id); newFolder(f.id); } },
      { label: 'Rename', icon: 'edit', hidden: !f.canChange, run: async () => { const i = h('input', { class: 't', value: f.name }); const v = await dialog('Rename the folder', i, [{ label: 'Cancel', value: null }, { label: 'Save', value: () => i.value, primary: true }]); if (v) call(`api/bookmarks/groups/${f.id}`, { method: 'PATCH', json: { name: v } }, 'Saved'); } },
      { label: 'Delete the folder', icon: 'delete', danger: true, hidden: !f.canChange, run: async () => { if (await confirmDialog('Delete the folder', `Delete "${f.name}" and the ${n} link(s) in it? ${f.shared ? 'It is shared: everyone loses it (what others added of their own in it stays theirs), and so do the browsers that sync.' : 'Browsers that sync lose them too.'}`, 'Delete', true)) call(`api/bookmarks/groups/${f.id}`, { method: 'DELETE' }, 'Deleted'); } },
    ].filter((a) => !a.hidden);
    const folderBox = (f) => {
      const open = isOpen(f), n = count(f), acts = folderActions(f, n);
      return h('div', { class: `bmedit${open ? '' : ' shut'}`, 'data-id': f.id },
        h('div', { class: 'bmhead' }, grip('Drag to move the folder', 'group', f),
          h('button', { class: 'bmfold', 'aria-expanded': open ? 'true' : 'false', title: open ? 'Fold' : 'Unfold', onclick: () => { if (open) { bmOpen.delete(f.id); bmOpen.add(-f.id); } else { bmOpen.add(f.id); bmOpen.delete(-f.id); } paint(); } },
            icon(open ? 'down' : 'right', 's'), icon('folder', 's'), h('b', null, f.name || '(no name)'), h('span', { class: 'muted small' }, `${n}`)),
          !canEdit && !f.shared ? null : h('span', { class: 'bmtools' },
            share(f, `api/bookmarks/groups/${f.id}`),
            house(f.start, (f.start ? 'On the start page, as a group with its links: click to take it off' : 'Not on the start page: click to show it as a group') + (f.shared && !canShare ? ' (yours only)' : ''), acts[0].run),
            ...acts.slice(1).filter((a) => a.icon !== 'people').map((a) => h('button', { class: 'iconbtn', title: a.label, onclick: a.run }, icon(a.icon, 's')))),
          f.shared ? h('span', { class: 'bmsharedtag', title: 'Shared with everyone' }, icon('people', 's')) : null,
          canEdit || f.shared ? moreBtn(f.name || 'Folder', acts) : null),
        open ? level(f.items, f) : null);
    };
    // a folder's links, then the folders inside it (each list takes what is dragged into it)
    const level = (items, f) => h('div', { class: 'bmlevel' },
      h('div', { class: 'bmlinks', 'data-gid': f ? f.id : 0 }, items.filter((x) => x.type === 'bookmark').map((l) => linkRow(l, f))),
      h('div', { class: 'bmsubs', 'data-gid': f ? f.id : 0 }, items.filter((x) => x.type === 'folder').map(folderBox)));
    const results = () => {
      const found = bmFlat(tree.items).filter((l) => fold(`${l.name} ${l.href} ${l.description || ''} ${where.get(l.id)?.path || ''}`).includes(query));
      return found.length ? h('div', { class: 'bmresults' }, found.slice(0, 200).map((l) => linkRow(l, where.get(l.id)?.f || null, where.get(l.id)?.path || '')))
        : h('p', { class: 'muted' }, 'No bookmark matches.');
    };
    el.bmAdd = () => editLink(0, null);
    el.replaceChildren(
      h('div', { class: 'box bmtree' }, h('h2', null, icon('link'), query ? 'Found' : 'Bookmarks'),
        h('p', { class: 'muted' }, (canEdit ? 'Your bookmarks and the shared ones, in folders as a browser keeps them. Yours are yours alone; the shared ones (the people icon) everyone sees. The house says what is on the start page: on a folder it shows the folder as a group with its links, on a link it shows or hides just that one. Everything here syncs to your browsers, on the start page or not. Drag a folder or a link by its handle to move it.'
          : 'The shared bookmarks, in folders as a browser keeps them. The house says what is on your start page.')
          + (canShare ? ' The people icon shares a folder or a link with everyone (what you add in a shared folder is shared too); only the start page\'s admins change the shared ones.' : canEdit ? ' The shared ones are kept by an admin: you can add links of your own in a shared folder, and take shared ones off your own start page.' : '')),
        query ? results() : tree.items.length ? h('div', { class: 'bmgroups' }, level(tree.items, null)) : h('p', { class: 'muted' }, 'No bookmarks yet.'),
        !canEdit || query ? null : h('div', { class: 'multi', style: 'margin-top:12px' },
          h('button', { class: 'pillbtn primary', onclick: () => newFolder(0) }, icon('add', 's'), 'Folder'),
          h('button', { class: 'pillbtn', onclick: () => editLink(0, null) }, icon('add', 's'), 'Link'))));
    const root = el.querySelector('.bmgroups');
    if (!root || !canEdit) return;
    // drag the grip (mouse, pen or finger): a link lands in any folder's links, a folder among any folder's folders
    const save = (list) => call(`api/bookmarks/groups/${list.dataset.gid}/order`, { method: 'POST', json: { ids: [...list.children].filter((x) => x.dataset.id).map((x) => +x.dataset.id) } });
    for (const g of root.querySelectorAll('.grip')) {
      const group = g.dataset.kind === 'group', item = g.closest(group ? '.bmedit' : '.bmrow');
      dragSort(g, item, {
        root, lists: () => [...root.querySelectorAll(group ? '.bmsubs' : '.bmlinks')].filter((l) => !item.contains(l)), items: group ? '.bmedit' : '.bmrow', sorting: group ? 'sorting-groups' : 'sorting-links',
        done: (from, to) => save(to),
      });
    }
  };
  el.bmDraw = draw; el.bmPaint = paint;
  await draw();
}

/** Every link of a folder, each in a tab of its own. A browser lets a page open one tab per click and stops the rest
    unless pop-ups are allowed for it: the ones it stopped are counted and said. */
export async function openAll(name, links) {
  const web = links.filter((l) => /^https?:\/\//i.test(l.href));
  if (!web.length) { toast('No web address to open'); return; }
  if (web.length > 8 && !await confirmDialog('Open all', `Open the ${web.length} links of “${name}”, each in a tab of its own?`, 'Open')) return;
  let stopped = 0;
  for (const l of web) {
    const w = window.open(l.href, '_blank');
    if (w) { try { w.opener = null; } catch { /* another site already */ } } else stopped += 1;
  }
  if (stopped) toast(`The browser stopped ${stopped} of ${web.length}: allow pop-ups for this page to open them all`);
}

/* Tidy up (the broom on the Bookmarks page): the links that no longer work and the same address kept more than once,
   in a box above the tree. The server asks every address in the background (iostart/bookmarks/check.py); the box follows
   it and lists what it found: nothing answering, a page that is gone, a page that moved for good (its new address
   one click away). Nothing is deleted or changed without a click here. */
function bmTidy(el, changed) {
  if (!el.hidden) { el.hidden = true; el.replaceChildren(); clearTimeout(el.bmTimer); return; }  // the broom again: away
  el.hidden = false;
  let check = null, dup = null, busy = false;
  const STATE = { dead: 'No answer', gone: 'Page gone', moved: 'Moved' };
  const later = (ms) => { clearTimeout(el.bmTimer); el.bmTimer = setTimeout(load, ms); };
  const load = async () => {
    if (!el.isConnected || el.hidden) return;
    try { [check, dup] = await Promise.all([api('api/bookmarks/check'), api('api/bookmarks/duplicates')]); } catch (e) { fail(e); return; }
    paint();
    if (check.running) later(1500);
  };
  const run = async () => { try { check = await api('api/bookmarks/check', { method: 'POST' }); } catch (e) { fail(e); return; } paint(); later(1000); };
  // one after another: each is its own change to the tree, which the browsers that sync then follow
  const each = async (items, call, done) => {
    if (busy) return;
    busy = true; paint();
    let n = 0;
    for (const x of items) { try { await call(x); n += 1; } catch (e) { fail(e); break; } }
    busy = false;
    if (n) toast(done(n));
    await load(); changed();
  };
  const remove = (items) => each(items, (x) => api(`api/bookmarks/links/${x.id}`, { method: 'DELETE' }), (n) => (n === 1 ? 'Deleted' : `Deleted ${n} links`));
  const follow = (items) => each(items, (x) => api(`api/bookmarks/links/${x.id}`, { method: 'PATCH', json: { href: x.to } }), (n) => (n === 1 ? 'Address updated' : `Updated ${n} addresses`));
  const plural = (n, one, many) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
  const row = (x, lead, tools) => h('div', { class: 'bmrow tidyrow' }, lead,
    h('a', { class: 'bmname', href: x.href, target: '_blank', rel: 'noreferrer', title: x.href }, x.name || x.href),
    h('span', { class: 'muted small bmdesc' }, x.path || 'Top level'),
    x.shared ? h('span', { class: 'bmsharedtag', title: 'Shared with everyone' }, icon('people', 's')) : null, h('span', { class: 'bmtools' }, tools));
  const del = (x) => (x.canChange ? h('button', { class: 'iconbtn', title: 'Delete this link', 'aria-label': `Delete ${x.name || x.href}`, disabled: busy ? true : null, onclick: () => remove([x]) }, icon('delete', 's')) : null);
  const paint = () => {
    const found = check.items || [], broken = found.filter((x) => x.state !== 'moved'), moved = found.filter((x) => x.state === 'moved');
    const mine = (list) => list.filter((x) => x.canChange);
    const when = check.checkedAt ? new Date(check.checkedAt * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : '';
    const links = h('div', { class: 'tidysec' }, h('h3', null, 'Links that no longer work'),
      check.running ? h('div', { class: 'tidyrun' }, h('progress', { max: Math.max(1, check.total), value: check.done }), h('span', { class: 'muted small' }, `Asked ${check.done.toLocaleString()} of ${plural(check.total, 'address', 'addresses')}…`))
        : h('div', { class: 'multi' },
          h('span', { class: 'muted' }, check.checkedAt ? (found.length ? `${plural(check.total, 'address', 'addresses')} asked ${when}: ${plural(found.length, 'link needs', 'links need')} a look.` : `${plural(check.total, 'address', 'addresses')} asked ${when}: every one of them answers.`)
            : 'The server asks every address whether it still answers: a minute or two for a few hundred links. Nothing is changed until you say so.'),
          h('button', { class: `pillbtn${check.checkedAt ? '' : ' primary'}`, disabled: busy ? true : null, onclick: run }, icon('update', 's'), check.checkedAt ? 'Check again' : 'Check the links')),
      broken.length ? [broken.map((x) => row(x, h('span', { class: `tidystate ${x.state}`, title: x.state === 'dead' ? (x.status ? `The server answered with an error (${x.status})` : 'Nothing answered at this address') : `The site says this page is not there (${x.status})` }, STATE[x.state]), del(x))),
        check.offline ? h('p', { class: 'warn' }, 'Most addresses gave no answer at all. That usually means this server cannot reach the internet right now, not that the links are dead: check its connection and its DNS, then check again.') : null,
        mine(broken).length > 1 && !check.offline ? h('div', { class: 'multi tidyall' }, h('button', { class: 'pillbtn danger', disabled: busy ? true : null, onclick: async () => {
          if (await confirmDialog('Delete the links that no longer work', `Delete these ${mine(broken).length} links? A site that is only down today would be lost too: open the ones you are not sure of first. Browsers that sync lose them as well.`, 'Delete', true)) remove(mine(broken)); } }, icon('delete', 's'), `Delete all ${mine(broken).length}`)) : null] : null,
      moved.length ? [h('h4', null, 'Moved to a new address'), moved.map((x) => row(x, h('span', { class: 'tidystate moved', title: `The site says this page moved for good (${x.status})` }, STATE.moved),
        [h('span', { class: 'muted small tidyto', title: x.to }, `→ ${x.to.replace(/^https?:\/\//, '')}`),
          x.canChange ? h('button', { class: 'iconbtn', title: 'Keep the new address', 'aria-label': `Keep the new address of ${x.name || x.href}`, disabled: busy ? true : null, onclick: async (e) => {
            // on a phone the row has no room for the new address: it is shown before it is kept
            const to = e.currentTarget.parentNode.querySelector('.tidyto');
            if (to && to.offsetParent === null && !await confirmDialog('Keep the new address', `“${x.name || x.href}” moved to ${x.to}`, 'Keep it')) return;
            follow([x]); } }, icon('check', 's')) : null, del(x)])),
        mine(moved).length > 1 ? h('div', { class: 'multi tidyall' }, h('button', { class: 'pillbtn', disabled: busy ? true : null, onclick: () => follow(mine(moved)) }, icon('check', 's'), `Keep all ${mine(moved).length} new addresses`)) : null] : null);
    const extra = dup.groups.flatMap((g) => g.links.slice(1)).filter((x) => x.canChange);
    const twice = h('div', { class: 'tidysec' }, h('h3', null, 'The same address more than once'),
      dup.groups.length ? [h('p', { class: 'muted' }, `${plural(dup.groups.length, 'address is', 'addresses are')} kept more than once. The first of each stays (the one on the start page, or the shared one); delete the copies you do not need.`),
        dup.groups.map((g) => h('div', { class: 'tidydup' }, h('div', { class: 'muted small tidyhref', title: g.href }, g.href.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')), g.links.map((x, i) => row(x, h('span', { class: `tidystate ${i ? 'copy' : 'keep'}` }, i ? 'Copy' : 'Keep'), del(x))))),
        extra.length > 1 ? h('div', { class: 'multi tidyall' }, h('button', { class: 'pillbtn danger', disabled: busy ? true : null, onclick: async () => {
          if (await confirmDialog('Delete the copies', `Delete the ${extra.length} extra copies and keep the first of each address? Browsers that sync lose them too.`, 'Delete', true)) remove(extra); } }, icon('delete', 's'), `Delete the ${extra.length} copies`)) : null]
        : h('p', { class: 'muted' }, 'No address is kept twice.'));
    el.replaceChildren(h('div', { class: 'box bmtidy' },
      h('h2', null, icon('broom'), 'Tidy up', h('button', { class: 'iconbtn tidyclose', title: 'Close', 'aria-label': 'Close', onclick: () => bmTidy(el, changed) }, icon('close', 's'))), links, twice));
  };
  el.replaceChildren(h('div', { class: 'box bmtidy' }, h('h2', null, icon('broom'), 'Tidy up'), h('p', { class: 'muted' }, 'Looking…')));
  load();
}

/** Settings › Bookmarks: syncing with browsers (the extension), the Bookmarks app on a phone, and
 * files in and out. The Bookmarks page itself is only the tree. */
export async function setBookmarkSettings(el) {
  const [tree, sync] = await Promise.all([api('api/bookmarks/tree'), api('api/bookmarks/sync')]);
  const canEdit = !!tree.canEdit;
  const copy = (text) => h('button', { class: 'iconbtn', title: 'Copy', onclick: async () => { try { await navigator.clipboard.writeText(text); toast('Copied'); } catch { toast(text); } } }, icon('copy', 's'));
  const addr = (label, text) => h('div', { class: 'bmaddr' }, h('span', { class: 'muted small' }, label), h('code', null, text), copy(text));
  const file = h('input', { type: 'file', accept: '.html,.htm,.xbel,.xml,text/html', class: 't' });
  const importFile = async () => {
    const f = file.files[0];
    if (!f) { toast('Choose a bookmarks file first'); return; }
    try { const r = await api('api/bookmarks/import', { method: 'POST', json: { file: await f.text() } }); toast(`Added ${r.links} link(s) in ${r.groups} folder(s)`); file.value = ''; } catch (e) { fail(e); }
  };
  el.append(
  h('div', { class: 'box' }, h('h2', null, icon('update'), 'Sync with browsers'),
      h('p', { class: 'muted' }, 'The ioStart Bookmarks extension keeps a browser\'s own bookmarks the same as these, both ways: the bookmarks bar is the folder "Bookmarks bar" here, Firefox\'s bookmarks menu the folder "Bookmarks menu", and Other bookmarks everything else at the top (in Vivaldi, which keeps one tree: the folder set as its bookmark bar, and the rest of its Bookmarks). What is added, changed or deleted here or in one browser is so in every browser, within a minute. It signs in with one click.'),
      h('div', { class: 'multi' },
        h('a', { class: 'pillbtn primary', href: 'https://chromewebstore.google.com/detail/iosuite-bookmarks/nldealkpbjiholobfadimblcmdlphkoe', target: '_blank', rel: 'noopener' }, icon('download', 's'), 'Chrome Web Store (Chrome, Edge, Vivaldi, Brave)'),
        h('a', { class: 'pillbtn', href: 'https://github.com/avandeputte/iosuite/releases?q=extension', target: '_blank', rel: 'noopener' }, 'For Firefox'),
        !sync.extension ? null : h('a', { class: 'pillbtn', href: 'api/bookmarks/extension.zip', download: '' }, `.zip ${sync.extension}`)),
      h('p', { class: 'muted small' }, 'Chromium browsers: add it from the Chrome Web Store; it keeps itself up to date. Firefox: open the signed .xpi file of the release. The .zip is for loading it unpacked (chrome://extensions, Developer mode, Load unpacked). Then type the address below in the extension and say yes.'),
      sync.server ? addr('Address for the extension and the ioStart app', sync.server) : null),
    standalone() ? null : h('div', { class: 'box' }, h('h2', null, icon('phone'), 'On a phone'),
      h('p', { class: 'muted' }, 'These bookmarks as an app of their own, with an icon on the home screen: on an iPhone or iPad open the address below (Safari, or Vivaldi, Chrome, Edge or Firefox), tap Share, then Add to Home Screen. On Android or a desktop browser, choose Install (or Add to Home screen) in the browser\'s menu.'),
      addr('Bookmarks app', new URL('bookmarks', document.baseURI).href)),
    h('div', { class: 'box' }, h('h2', null, icon('download'), canEdit ? 'Import and export' : 'Export'),
      canEdit ? h('p', { class: 'muted' }, 'A bookmarks file exported from a browser (HTML) or an XBEL file is added at the top level; pick what goes on the start page afterwards.') : null,
      canEdit ? h('div', { class: 'multi' }, file, h('button', { class: 'pillbtn noic', onclick: importFile }, 'Import')) : null,
      h('p', { class: 'multi' }, h('a', { class: 'pillbtn', href: 'api/bookmarks/export.html', download: 'bookmarks.html' }, icon('download', 's'), 'Export for a browser (HTML)'),
        h('a', { class: 'pillbtn', href: 'api/bookmarks/export.xbel', download: 'bookmarks.xbel' }, icon('download', 's'), 'Export XBEL'))));
}

/** A short list of things to do, each a full-width row to tap (a phone's stand-in for a row of small buttons). */
function sheet(title, actions) {
  const back = h('div', { class: 'dialog-back sheetback' });
  const close = () => back.remove();
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  back.append(h('div', { class: 'dialog sheet', role: 'dialog', 'aria-label': title },
    h('div', { class: 'sheettitle muted small' }, title),
    ...actions.filter((a) => !a.hidden).map((a) => h('button', { class: `sheetrow${a.danger ? ' danger' : ''}`, disabled: a.disabled ? true : null, onclick: () => { close(); a.run(); } }, icon(a.icon, 's'), a.label)),
    h('button', { class: 'sheetrow cancel', onclick: close }, 'Cancel')));
  document.body.append(back);
}

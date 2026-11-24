# ioStart Bookmarks

A browser extension (Chrome, Edge and other Chromium browsers; Firefox) that keeps the browser's own bookmarks the same
as the ioStart page's bookmarks, both ways.

- The bookmarks bar ↔ the top-level folder **Bookmarks bar** (also found as "Bookmarks Toolbar" or "Favorites bar").
- Firefox's bookmarks menu ↔ the top-level folder **Bookmarks menu** (a folder in Other bookmarks in Chrome and Edge).
- Other bookmarks ↔ everything else at the top level.
- Vivaldi keeps one tree, "Bookmarks": the folder set as its bookmark bar ↔ **Bookmarks bar** (a folder "Bookmarks
  bar" is made when none is set: right-click it › *Set as Bookmark Bar Folder*), and the rest of "Bookmarks", Speed
  Dial folders included, ↔ everything else at the top level. Its Trash does not sync: what goes there is deleted on
  the start page. Vivaldi's hidden "Other Bookmarks" folder is left alone.

It syncs a few seconds after a bookmark changes in the browser, every minute (one small request: "did anything
change?"), and when the browser starts. Deletes travel both ways. The first sync either brings both sides together
(folders matched by name, links by address, nothing doubled) or takes the start page's bookmarks as they are.

## Install

**Chrome, Edge, Vivaldi, Brave and other Chromium browsers**: install it from the Chrome Web Store:
**[ioSuite Bookmarks on the Chrome Web Store](https://chromewebstore.google.com/detail/iosuite-bookmarks/nldealkpbjiholobfadimblcmdlphkoe)**. The browser keeps it up to date.

For a build of your own (or a version not yet in the store): download the .zip from the start page's Bookmarks page
(or a release), unpack it, open `chrome://extensions` (`edge://extensions`, `vivaldi://extensions`), turn on
*Developer mode*, *Load unpacked*, pick the folder. Keep the folder where it is: the browser loads the extension from
it. To update, replace the folder's contents and press the reload arrow on the extension's card.

**Firefox**: open the signed `.xpi` of a release (`extension-v…` in the repository's releases). Firefox only keeps
extensions Mozilla has signed; unsigned, it can be tried until the next restart from `about:debugging` › *This
Firefox* › *Load Temporary Add-on* (pick `manifest.json`).

Then type the start page's address (or the address your server has for devices, when it has one of its own), your
name and password there, choose how the first sync goes, and *Sign in*. An account with two-step sign-in is asked
for its code as well. What you typed is sent once and not kept: the extension gets an app password of its own, for
sync only (Settings › Account on the start page lists and removes it; *Sign out* here removes it too). The browser
asks once whether the extension may reach that one address; it has no access to any other site.

*Ask the start page instead* signs in without typing a password here: a tab opens at the start page, where you are
signed in already (or sign in as you do there, with a passkey or through your proxy), and you say yes. It needs the
start page's pages to be reachable from where the browser is.

## Signing and the stores

- **Firefox, signed for yourself** (not listed anywhere): make an API key at
  <https://addons.mozilla.org/developers/addon/api/key/> and put it in the repository's secrets as `AMO_JWT_ISSUER`
  and `AMO_JWT_SECRET`. The workflow `Browser extension` then has Mozilla sign each new version and attaches the
  `.xpi` to the release.
- **Chrome Web Store** (Chrome, Edge, Vivaldi, Brave and Opera install from it): [published](https://chromewebstore.google.com/detail/iosuite-bookmarks/nldealkpbjiholobfadimblcmdlphkoe);
  `docs/extension/STORE.md` has the steps, every text the forms ask for, the screenshots and the privacy policy.

## Files

`manifest.json` (Manifest V3, one for both browsers), `sync.js` (the sync engine; no browser globals, so
`tests/extension/e2e.js` runs it in node against the app), `background.js` (when to sync), `options.*` (sign in,
state), `popup.*`, `lib.js`, `style.css`, `icons/`. A new version: bump `version` in `manifest.json`.

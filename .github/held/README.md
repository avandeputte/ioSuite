# Workflows that publish, not switched on yet

These are complete, and GitHub does not run them from this folder. They publish things people and devices pick up
(the browser extension to the stores; the wall display's firmware; the
website), and
the first repository (avandeputte/iosuite) still publishes the same. Move a file to `.github/workflows/` to switch it on:

| File | What it publishes | Before switching it on |
|---|---|---|
| `extension.yml` | the ioStart Bookmarks extension: a release, the signed .xpi, the Chrome Web Store | the repository secrets of the first repository (AMO, Chrome Web Store) |
| `tab5-wall.yml` | the wall display's firmware, release `wall-latest` | `devices/tab5-wall/main/ota.c` names the repository the devices update from |
| `docs.yml` | the website iosuite.iothing.net: builds `docs/` and deploys it to Cloudflare | the Cloudflare secrets (`docs/CLOUDFLARE.md`); the first repository's `docs.yml` switched off, or both deploy the same site |

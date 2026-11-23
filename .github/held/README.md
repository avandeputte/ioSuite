# Workflows that publish, not switched on yet

These are complete, and GitHub does not run them from this folder. They publish things people and devices pick up
(a version and a release per push, the image; the browser extension to the stores; the wall display's firmware), and
the first repository (avandeputte/iosuite) still publishes the same. Move a file to `.github/workflows/` to switch it on:

| File | What it publishes | Before switching it on |
|---|---|---|
| `version.yml` | raises the suite's version after a push to main, makes the release, starts the image build (`image.yml`) | nothing |
| `extension.yml` | the ioStart Bookmarks extension: a release, the signed .xpi, the Chrome Web Store | the repository secrets of the first repository (AMO, Chrome Web Store) |
| `tab5-wall.yml` | the wall display's firmware, release `wall-latest` | `devices/tab5-wall/main/ota.c` names the repository the devices update from |

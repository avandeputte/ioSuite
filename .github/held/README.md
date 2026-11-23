# Workflows that publish, not switched on yet

This one is complete, and GitHub does not run it from this folder. It publishes what people pick up (the browser
extension, to the stores), and the first repository (now avandeputte/iosuite-old, archived) published the same. The
website's workflow, `docs.yml`, and the wall display's firmware, `tab5-wall.yml`, were switched on on 2026-11-23.
Move the file to `.github/workflows/` to switch it on:

| File | What it publishes | Before switching it on |
|---|---|---|
| `extension.yml` | the ioStart Bookmarks extension: a release, the signed .xpi, the Chrome Web Store | the repository secrets of the first repository (AMO, Chrome Web Store) |

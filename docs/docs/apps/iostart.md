---
description: ioStart, the start page of the ioThing suite.
---

# ioStart <small>start page</small>

A self-hosted home page for the family: a tile per installed app, with what matters today on it. **It is optional**:
every app works without it. It earns its place once you run two or more apps.

[The ioStart page on the website, with more screenshots →](https://iosuite.iothing.net/ioStart/)
{ .md-button }

![The ioStart start page: a tile per app with today on it, birthdays, the week ahead and bookmarks](../img/iostart.jpg)

## What it does

- **A tile per app**, found by itself: every app registers in the suite's list of apps, so there is nothing to type.
  An app that isn't installed has no tile.
- **A glimpse of each app**: ioPix's photos from this day in earlier years, ioCalendar's rest of today, ioTask's tasks due today, ioHealth's
  steps, rings and sleep, ioMoney's bills due this week (with a warning when an account is about to run low or a bank
  link is behind), ioDocs' documents to renew; each person sees only what that app shows them.
- **The week ahead**: a Birthdays card (ioContact) and a This week card (ioCalendar).
- **A search box** (⌘K / Ctrl-K) across the apps and bookmarks (people, events, tasks, recipes, notes, things,
  payees and transactions, the people, albums and places of your photos), asked all at once and ranked together with
  the best matches first, the web as a fallback, and **Quick add**:
  "dinner fri 19:00" makes an event, "t buy milk sat" a task, "n the gate code is 4411" a note.
- **Tidy up** on the Bookmarks page: finds the links that no longer work, the ones that moved (the new address is one
  click away) and the same address kept twice.
- **Weather** (AccuWeather, a free key), **Home Assistant** entities you can switch from the page, and **bookmarks**.
- **A wall display** for a tablet: photos behind a big clock, the weather, today's and the coming days' events.
- **Your own page**: each person hides and orders tiles and cards.
- **One MCP server for the whole suite** (off until a suite admin turns it on under Settings › Apps): connect an AI
  assistant here once and it gets every app's tools, each app still deciding what you may do there. See
  [AI assistants](../run/assistants.md).
- **The suite's address**: the start page answers at the address itself and every app in a folder of it
  (`…/calendar/`, `…/notes/`), so one name and one certificate reach them all. See
  [Reverse proxy and HTTPS](../run/reverse-proxy.md#one-address-for-the-suite).

## Bookmarks in your browser

The **ioStart Bookmarks** extension keeps a browser's own bookmarks the same as the start page's, both ways: the
bookmarks bar, Other bookmarks (and Firefox's bookmarks menu) match folders on the start page, and an add, change or
delete in one browser reaches every other browser within a minute.

- **Chrome, Edge, Vivaldi, Brave, Opera**: [install it from the Chrome Web Store](https://chromewebstore.google.com/detail/iosuite-bookmarks/nldealkpbjiholobfadimblcmdlphkoe).
- **Firefox**: open the signed `.xpi` of the newest `extension-v…` [release](https://github.com/avandeputte/iosuite-old/releases?q=extension).

Then type the start page's address in the extension (away from home: the suite's
[address for devices](../reference/configuration.md#the-three-ports)), choose how the first sync goes, and sign in: it gets an app
password of its own, for bookmark sync only. What it sends and keeps: [privacy policy](../privacy/iostart-bookmarks.md).

## With the other apps

ioStart is all about them: it shows a tile and widgets for each app it finds, asks each app with the viewer's own
sign-in, and leaves a tile as it was when its app is down.

## Install

ioStart is the suite's start page, and it answers at the suite's address itself. A server installed with the [installer](../start/linux-mac.md), [Docker](../start/docker.md) or [Proxmox](../start/proxmox.md) runs it unless you untick it.

| | |
| --- | --- |
| Address | the suite's address itself (`https://home.example.com/`) |
| Devices | bookmark sync at `/dav/…` (the browser extension, the iPhone app), widgets, e-ink screens and the wall display at `/api/…`, at the [address for devices](../reference/configuration.md#the-three-ports) |
| MCP | `/mcp` at the address for MCP ([AI assistants](../run/assistants.md)) |
| Source | [iosuite/iostart](https://github.com/avandeputte/iosuite/tree/main/iostart) |

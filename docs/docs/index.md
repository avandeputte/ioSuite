---
title: The ioThing suite
description: Self-hosted apps for the family, in one program. Run one of them, or all of them.
---

# The ioThing suite

Small self-hosted apps for the family. ioSuite is **one program** that runs the apps you tick: one of them, a few,
or all thirteen, each in a folder of the suite's address.

| App | What it is | Where | Source |
| --- | --- | --- | --- |
| [ioStart](apps/iostart.md) | The start page: a tile per app, search, weather, bookmarks | `/` | [iostart](https://github.com/avandeputte/iosuite/tree/main/iostart) |
| [ioPix](apps/iopix.md) | Photos: a web app for a photo library, with or without digiKam | `/pix/` | [iopix](https://github.com/avandeputte/iosuite/tree/main/iopix) |
| [ioNote](apps/ionote.md) | Notes, clipboard snippets and screenshots, with Mac and iPhone apps | `/notes/` | [ionote](https://github.com/avandeputte/iosuite/tree/main/ionote) |
| [ioCalendar](apps/iocalendar.md) | The family calendar, over CalDAV on every phone | `/calendar/` | [iocalendar](https://github.com/avandeputte/iosuite/tree/main/iocalendar) |
| [ioTask](apps/iotask.md) | The family's task lists, in Apple Reminders and every tasks app over CalDAV | `/tasks/` | [iotask](https://github.com/avandeputte/iosuite/tree/main/iotask) |
| [ioRecipe](apps/iorecipe.md) | The family's recipes, with photos and import from the web | `/recipes/` | [iorecipe](https://github.com/avandeputte/iosuite/tree/main/iorecipe) |
| [ioThings](apps/iothings.md) | Everything you own: manuals, warranties, upkeep; imports Homebox | `/things/` | [iothings](https://github.com/avandeputte/iosuite/tree/main/iothings) |
| [ioMoney](apps/iomoney.md) | The household's finances: Monarch Money's accounts and transactions, the portfolio, the house and the cars | `/money/` | [iomoney](https://github.com/avandeputte/iosuite/tree/main/iomoney) |
| [ioDocs](apps/iodocs.md) | The family's papers: passports, licenses, policies, certificates; reads scans, reminds before they expire | `/docs/` | [iodocs](https://github.com/avandeputte/iosuite/tree/main/iodocs) |
| [ioContact](apps/iocontact.md) | Contacts for the family, over CardDAV and LDAP | `/contacts/` | [iocontact](https://github.com/avandeputte/iosuite/tree/main/iocontact) |
| [ioHealth](apps/iohealth.md) | Apple Health data in your own database, with a fitness web app | `/health/` | [iohealth](https://github.com/avandeputte/iosuite/tree/main/iohealth) |

Two **admin tools** come with the suite, for the person who runs the servers. Only suite admins see them:

| Tool | What it is | Where | Source |
| --- | --- | --- | --- |
| [ioDNS](apps/iodns.md) | One list of the house's DNS names, kept in sync on AdGuard Home, Pi-hole, UniFi and Cloudflare | `/dns/` | [iodns](https://github.com/avandeputte/iosuite/tree/main/iodns) |
| [ioBackup](apps/iobackup.md) | Scheduled backups of the MariaDB databases to a folder or Google Drive, and restores of exactly what you pick | `/backup/` | [iobackup](https://github.com/avandeputte/iosuite/tree/main/iobackup) |

!!! tip "You don't need the whole suite"
    The program runs the apps you tick and nothing of the others. If all you want is a photo app, tick ioPix and
    stop there: nothing else is required, and nothing is missing. Add another app later, or never.
    [One app or all of them](start/one-or-all.md) explains what changes when you do.

## What they have in common

- **One program, one service**: a small web server (Python, FastAPI) that holds every app you run, each with its own
  single-page web app: light and dark, a real phone layout, installable on a home screen. All thirteen run in about
  250 MB of memory. Heavy work (ioPix's scans) can run in a
  [copy of its own](start/several-apps.md), on the same machine or another, and it is still one suite.
- **One address**: the start page at the address itself, every app in its folder (`/calendar/`, `/notes/`), and a
  name of its own for any app that should have one. Three ports keep the kinds of traffic apart: the pages, phones
  and devices, AI assistants. See [Configuration](reference/configuration.md#the-three-ports).
- **A database per app** on one MariaDB or MySQL server, plus the **Shared ioSuite database** for the accounts and
  the settings, all under one login. See [Databases](reference/databases.md).
- **No settings files to edit**: one small file per machine says where the database is and which apps run there.
  Everything else is under Settings, in the browser.
- **One installer**: a line on any Linux server or Mac, a Proxmox VE container, or one Docker image (amd64 and
  arm64). Run it again to add or remove an app. See [Requirements](start/requirements.md).
- **The same Settings**: Account and Display for everyone; People, Apps, Servers and Keys for suite admins (who may
  sign in and with which role, the apps and all their settings, updates and the certificate, the log, and the keys).
- **One version, one update**: a daily check, then one **Update** button under Settings › Servers › Updates.
  See [Updates](run/updates.md).
- **An MCP server** in ioPix, ioNote, ioCalendar, ioTask, ioRecipe, ioThings, ioMoney, ioDocs and ioContact, so an AI
  assistant such as Claude can work with them as you, with an app password; ioStart's passes on every app's tools
  through one connection. See [AI assistants](run/assistants.md).
- **Free and open source**, GPL-3.0-or-later.

## Where to start

1. [One app or all of them](start/one-or-all.md): decide what you need.
2. [Requirements](start/requirements.md): a database server and somewhere to run the program.
3. Install it: [one line on any Linux server or Mac](start/linux-mac.md), [Proxmox VE](start/proxmox.md) or
   [Docker](start/docker.md).
4. [First run](start/first-run.md): sign in, make accounts, put it behind HTTPS.

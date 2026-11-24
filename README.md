# ioSuite

*Self-hosted apps for the family, with one sign-in: one program that runs the apps it is told to.*

This repository is ioSuite as **one program**. The thirteen apps are packages of it; a copy of the program runs the
ones it is told to, and several copies against the same Shared ioSuite database are one suite (ioPix on a server of
its own, the rest on another, say). It follows [avandeputte/iosuite-old](https://github.com/avandeputte/iosuite-old), where
every app was a program and a service of its own.

## Install

On any Linux machine, one command installs the program, asks for the database server, the apps and the first admin,
and starts the service; run it again at any time to add or remove apps:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash
```

| | |
| --- | --- |
| [Any Linux or Mac](docs/docs/start/linux-mac.md) | the command above, its questions and its options (`--apps`, `--add`, `--remove`, `--mariadb`, `--yes`) |
| [Docker](docs/docs/start/docker.md) | [docker-compose.yml](docker-compose.yml): MariaDB and one container that runs every app (the image `ghcr.io/avandeputte/iosuite`) |
| [Proxmox VE](docs/docs/start/proxmox.md) | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/proxmox/ct/iosuite.sh)"` on the host: a container with the suite in it |
| [One app or all of them](docs/docs/start/one-or-all.md) | every app works alone; the others add to it when they are there |
| [Several copies and several servers](docs/docs/start/several-apps.md) | ioPix apart from the rest, on the same machine or another |

The whole guide is in [docs/docs/](docs/docs/index.md): first run, accounts and roles, reverse proxy and HTTPS,
Cloudflare, AI assistants (MCP), updates, configuration, and a page for each app.

## The apps

| Package | App | What it is | Folder |
|---|---|---|---|
| [`iostart/`](iostart/) | ioStart | the start page: a tile per app, bookmarks, feeds, wall and e-ink screens | `/` |
| [`iocalendar/`](iocalendar/) | ioCalendar | the family calendar, CalDAV | `/calendar/` |
| [`iotask/`](iotask/) | ioTask | task lists, CalDAV for reminders apps | `/tasks/` |
| [`iocontact/`](iocontact/) | ioContact | contacts, CardDAV, LDAP | `/contacts/` |
| [`ionote/`](ionote/) | ioNote | notes | `/notes/` |
| [`iorecipe/`](iorecipe/) | ioRecipe | recipes | `/recipes/` |
| [`iothings/`](iothings/) | ioThings | everything you own: where it is, warranties, manuals, receipts, upkeep | `/things/` |
| [`iomoney/`](iomoney/) | ioMoney | household finances | `/money/` |
| [`iodocs/`](iodocs/) | ioDocs | family papers: passports, licenses, policies, certificates | `/docs/` |
| [`iohealth/`](iohealth/) | ioHealth | health data from the iPhone | `/health/` |
| [`iopix/`](iopix/) | ioPix | the photo library, with or without digiKam | `/pix/` |
| [`iodns/`](iodns/) | ioDNS | admin tool: the DNS console | `/dns/` |
| [`iobackup/`](iobackup/) | ioBackup | admin tool: database backups | `/backup/` |
| [`iosuite_shared/`](iosuite_shared/) | | what every app uses: accounts, sign-in, roles, settings, the host, the `iosuite` command | |
| [`iosuite_demo/`](iosuite_demo/) | | the demo data (a made-up family of four) | |

## One program, the apps it is told to

```sh
iosuite serve                      # the apps the machine's file names (APPS; none named: every app installed)
iosuite serve --apps iopix         # a copy of its own for ioPix, or any one app alone
```

Each app keeps its own database; every database is reached with the one login of the Shared ioSuite database.

The work most likely to crash or to eat memory (reading text off scans and photos, a license's barcode, decoding
pictures people upload, making the ioThings inventory PDF and the estate PDF) runs in a helper process beside the
copy (`iosuite_shared/helper.py`). If it crashes, that one upload or PDF fails and the copy carries on; the helper ends
when it has nothing to do, so the memory it took goes back. Each copy has its own and never asks another server's.
`HELPER=off` in the machine's file does the work inside the copy instead.

ioPix's analysis (thumbnails, faces, search, captions: the jobs that load models) has a process of its own for the
same reason, with rules of its own (its progress, a cancel, how much memory it may take). Both are started, ended and
watched by the same code: `iosuite_shared/child.py` (a process beside the copy) and `iosuite_shared/memory.py` (what
the server may use, what a process holds). ioPix's queue is itself one of the copy's jobs, "analysis" under
**Settings › Servers › Jobs**, run when something is queued.

## Three ports

A copy listens on three ports, so a firewall or a reverse proxy can treat each kind of traffic on its own:

| Door | Port | What comes in |
|---|---|---|
| pages | 80 (`PORT`) | the pages people open and what the pages ask for (the session cookie, passkeys, a reverse proxy's sign-in) |
| devices | 8443 (`SYNC_PORT`) | phones and native apps, and nothing else: CalDAV, CardDAV, calendar subscriptions, bookmark sync, ioHealth's uploads, and of each app's API the calls its native apps make (its manifest's `devices`). App passwords and tokens only: no cookies, no pages, no reference of the API |
| MCP | 8444 (`MCP_PORT`) | MCP clients: `/mcp` and nothing else |

On every port an app answers both at a name of its own (`https://calendar.example.com/`) and in its folder at the
suite's address (`https://home.example.com/calendar/`). The pages' port answers the other two's paths as well; the
other two refuse what is not theirs. A wall display, an e-ink screen or a script is given the pages' address: an app
password is taken for an app's `/api/` there, from inside the network and from outside; signing in by a session or
changing an account with one from outside is not.

For HTTPS, put a reverse proxy in front, or let the suite do it: under **Settings › Servers › Certificate**
(or `iosuite cert --on`) it asks Let's Encrypt for a certificate for its names, renews it, and answers HTTPS itself,
the pages on port 443 (`HTTPS_PORT`) and devices and MCP on the ports they have, which go on answering plain HTTP as
well.

## Settings

One small file per machine, `config.env` in the program folder, says how to reach the Shared ioSuite database and what
this machine runs:

```sh
IOSUITE_DB_HOST=127.0.0.1
IOSUITE_DB_NAME=iosuite
IOSUITE_DB_USER=iosuite
IOSUITE_DB_PASSWORD=…
APPS=iostart,iocalendar,iotask      # empty: every app installed
# PORT=80  SYNC_PORT=8443  MCP_PORT=8444  HTTPS_PORT=443  HOST=…  DATA_DIR=…  LOG_FILE=…  TLS_CERT_FILE=…  TLS_KEY_FILE=…
```

Everything else is kept in the Shared ioSuite database and set under **Settings › Apps › All settings**, or
from a shell when the pages cannot be reached:

```sh
iosuite settings                   # what may be set, with the value stored now
iosuite set suite PUBLIC_URL https://home.example.com
iosuite set iopix PHOTOS_ROOT /srv/photos
iosuite apps                       # which apps this machine runs, and where each answers
```

## One job runner

A copy runs the background work of all its apps — reminders, syncs, housekeeping — from one runner, so a job is never
started twice over itself and two heavy jobs (a scan, an index, a backup) never run at the same moment. Suite admins
see every job under **Settings › Servers › Jobs**: what it is, which server runs it, when it last ran, how long that
took, what it said, and **Run now**. With several servers, each job belongs to the one that runs its app and Run now
reaches it there. The looks every few seconds (a kitchen timer that ended, a backup that was asked for, ioPix's index
and scan) are jobs of this runner too, not threads of their own, and one thread per copy watches for an update or a
restart that was asked for, whatever the number of apps.

## One live-refresh connection

A page holds one connection (`GET /api/live`, server-sent events) and hears the changes of every app of the suite on
it, so a task ticked off in ioTask refreshes the start page's Today card, a photo added in ioPix refreshes the strip,
and an event moved in ioCalendar refreshes a calendar open in another tab. An app needs no code for it: every request
that changed something says so, through the API or from a device that syncs (CalDAV, CardDAV); what arrives another
way says it in one line (`live.changed`): a tool called over MCP, an upload from the phone, what a job brought in. An
app's own page keeps itself up to date with `keepFresh` (`iosuite_shared/static/live.js`), which waits while a dialog
is open or something is being typed. The lines go through the Shared ioSuite database (`ios_changes`, a few minutes deep),
so a change made on one server reaches a page served by another, and a copy with nobody looking at it asks for
nothing. A line says only which app's what changed, and when: never what changed, so it is safe for any signed-in
page, and a line addressed to one person reaches only that person's own pages.

## One Settings area

Every setting of every app is in one place: **Settings › Apps › All settings**, with a section for the suite and one
per app, in whichever app you happen to have open. There is no settings file per app — a machine keeps one short file
that says where the Shared ioSuite database is and which apps it runs — and no second place to look: people and
roles, each app's default role and addresses, the keys, the jobs, the log and the certificate are tabs of that same
area, and **Its settings** on an app's row opens the few screens that app alone has.

## One MCP server

An assistant connects once, at the start page's `/mcp`, and gets every app's tools (`iocalendar_add_event`,
`iotask_add_task`…), each call carried out as the person who signed in, with the role they hold in that app. An app
in the same copy of the program is asked inside the program, with no request of its own to make; an app on another
server is reached over the network. The switches are per app, under **Settings › Apps**.

## One log

A copy writes one log (`<DATA_DIR>/iosuite.log`, 20 MB at most with four older ones kept), every line marked with the
app it came from. Suite admins read it under **Settings › Servers › Logs**, from any app: filtered to the app
it was opened from, or every app on one timeline; with several copies, every copy's lines merged by time.

## One shape for every app

An app is a folder beside the others: `app.json` says what it is (its name, port, folder, colour, settings, what it
serves to phones and devices), `db.py` holds its tables, `main.py` what is its own — its description, its jobs, its
body limits, its routes — and hands the rest to `iosuite_shared.application.create`, which starts every app the same
way: the tables and the accounts, the demo data while that switch is on, the jobs, who is asking, the routes every
app answers (`/api/auth`, `/api/status`, `/api/live`, `/api/suite`…), the MCP endpoint, the page. The database
helpers (`iosuite_shared.db.AppDatabase`), the accounts as an app sees them (`iosuite_shared.users.AppUsers`) and
what a local MCP server and its diagnostics say (`iosuite_shared.mcp`) are kept once as well.

Each app's page is a page of its own, and what the pages all did in the same words is one script and one style
sheet the suite serves beside them: `iosuite_shared/static/frame.js` (the icons most of them draw, the note at the
foot of the page, dialogs, the menus, the menu of the suite's apps, the account's menu, the sign-in screen, the
sidebar, the theme), `account-panel.js` (`h()`, the client, Settings › Account) and `base.css`. A page imports
them from its own app (`api/auth/frame.js`), so it works the same on whichever server the app runs. A page's own
script has no build step: `static/app.js` starts it, and where it is more than one file the modules are in
`static/js/` by subject (`core.js`: the helpers and the page's state; `main.js`: the routes and the start; then a
module per page or part of the page).

What two or three apps need in the same way is in the shared library too, not in each of them: family members as
tags on events and tasks (`iosuite_shared.family.Tags`), files kept in an app's database (`stored.py`: ioDocs,
ioThings, ioMoney's receipts), the server's time zone (`zones.py`), and another app asked on the viewer's behalf
(`links.App`: the tasks, bills and papers on the calendar, the shopping list, a thing's upkeep). The map library
(Leaflet, for ioPix and ioHealth) is there once as well (`iosuite_shared/static/public`), and each app serves it in
its own `/static`. Outbound HTTP is one client library, `httpx2`.

The pages' scripts and style sheets go out compressed, and a browser that still has one is told so (304) instead of
being sent it again. The page names `app.js`, `app.css` and `base.css` with a mark of what is in them
(`static/app.js?v=3f9c01ab7e`, `iosuite_shared/pages.py`), and a file asked for by its own mark is kept by the
browser and by Cloudflare for good; the modules a script imports by name are asked for each time, so an update never
pairs one with another from the version before.

## From a checkout

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite
python3 -m venv .venv && .venv/bin/pip install -e ".[all]"
.venv/bin/iosuite install --no-service     # asks what the installer asks, writes config.env, makes the tables and the admin
.venv/bin/iosuite serve
```

The tests need a MariaDB of their own (a Docker container they start, or `IOSUITE_TEST_DB=host:port:user:password`):

```sh
.venv/bin/pip install -e ".[all,test]"
.venv/bin/python -m pytest iosuite_shared/tests iocalendar/tests
```

## What else is here

| | |
| --- | --- |
| [`install.sh`](install.sh), [`update.sh`](update.sh) | the installer and the update, for a machine that runs the suite as a service |
| [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) | the container image and a stack that uses it |
| [`proxmox/`](proxmox/) | the Proxmox VE scripts (community-scripts layout) |
| [`cloudflare/edge-auth/`](cloudflare/edge-auth/) | an optional Cloudflare Worker that checks app passwords before a request reaches the server |
| [`devices/`](devices/) | firmware for the wall display |
| [`tools/`](tools/) | checks that run against a live suite (`smoke.py`, `twocopies.py`) and the measurements (`measure.py`); nothing imports them |
| [`docs/`](docs/) | the guide and the website |

## License

GPL-3.0-or-later: see [LICENSE](LICENSE).

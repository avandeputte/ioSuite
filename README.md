# ioSuite

*Self-hosted apps for the family, with one sign-in: one program that runs the apps it is told to.*

This repository is ioSuite as **one program**. The thirteen apps are packages of it; a copy of the program runs the
ones it is told to, and several copies against the same Shared ioSuite database are one suite (ioPix on a server of
its own, the rest on another, say). It follows [avandeputte/iosuite](https://github.com/avandeputte/iosuite), where
every app was a program and a service of its own.

> **Work in progress.** The apps, the host and the settings are here; the installer, the update script, the Docker
> image and the converter for an existing install are still to come. Until then this is run from a checkout (below).

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
iosuite serve --apps iopix         # a copy of its own for ioPix
python -m iocalendar               # one app alone
```

Each app keeps its own database; every database is reached with the one login of the Shared ioSuite database.

## Three ports

A copy listens on three ports, so a firewall or a reverse proxy can treat each kind of traffic on its own:

| Door | Port | What comes in |
|---|---|---|
| pages | 80 (`PORT`) | the pages people open and what the pages ask for (the session cookie, passkeys, a reverse proxy's sign-in) |
| devices | 8443 (`SYNC_PORT`) | phones, native apps and devices: CalDAV, CardDAV, calendar subscriptions, bookmark sync, ioHealth's uploads, each app's API for native apps and widgets. App passwords and tokens only: no cookies, no sign-in, no pages |
| MCP | 8444 (`MCP_PORT`) | MCP clients: `/mcp` and nothing else |

On every port an app answers both at a name of its own (`https://calendar.example.com/`) and in its folder at the
suite's address (`https://home.example.com/calendar/`). A request that comes in by the wrong port is sent to the
right one.

## Settings

One small file per machine, `config.env` in the program folder, says how to reach the Shared ioSuite database and what
this machine runs:

```sh
IOSUITE_DB_HOST=127.0.0.1
IOSUITE_DB_NAME=iosuite
IOSUITE_DB_USER=iosuite
IOSUITE_DB_PASSWORD=…
APPS=iostart,iocalendar,iotask      # empty: every app installed
# PORT=80  SYNC_PORT=8443  MCP_PORT=8444  HOST=…  DATA_DIR=…  LOG_FILE=…  TLS_CERT_FILE=…  TLS_KEY_FILE=…
```

Everything else is kept in the Shared ioSuite database and set under **Settings › Global settings › Settings**, or
from a shell when the pages cannot be reached:

```sh
iosuite settings                   # what may be set, with the value stored now
iosuite set suite PUBLIC_URL https://home.example.com
iosuite set iopix PHOTOS_ROOT /srv/photos
iosuite apps                       # which apps this machine runs, and where each answers
```

## One log

A copy writes one log (`<DATA_DIR>/iosuite.log`, 20 MB at most with four older ones kept), every line marked with the
app it came from. Suite admins read it under **Settings › Global settings › Logs**, from any app: filtered to the app
it was opened from, or every app on one timeline; with several copies, every copy's lines merged by time.

## From a checkout

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[all]"
cp config.env.example config.env    # the database and the apps of this machine
.venv/bin/iosuite provision --admin root    # the databases and the one login (asks for root's password)
.venv/bin/iosuite init && .venv/bin/iosuite admin alex
.venv/bin/iosuite serve
```

The tests need a MariaDB of their own (Docker, or `IOSUITE_TEST_DB=host:port:user:password`):
`python -m pytest iosuite_shared/tests iocalendar/tests`.

## License

GPL-3.0-or-later: see [LICENSE](LICENSE).

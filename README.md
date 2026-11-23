# ioSuite

*Self-hosted apps for the family, with one sign-in: one program that runs the apps it is told to.*

This repository is ioSuite as **one program**. The thirteen apps are packages of it; a copy of the program runs the
ones it is told to, and several copies against the same Shared ioSuite database are one suite (ioPix on a server of
its own, the rest on another, say). It follows [avandeputte/iosuite](https://github.com/avandeputte/iosuite), where
every app was a program and a service of its own; [`tools/convert/`](tools/convert/) moves such an install here.

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
iosuite serve --apps iopix         # a copy of its own for ioPix
python -m iocalendar               # one app alone
```

Each app keeps its own database; every database is reached with the one login of the Shared ioSuite database.

The work most likely to crash or to eat memory (reading text off scans and photos, a license's barcode, decoding
pictures people upload, making the ioThings inventory PDF and the estate PDF) runs in a helper process beside the
copy (`iosuite_shared/helper.py`). If it crashes, that one upload or PDF fails and the copy carries on; the helper ends
when it has nothing to do, so the memory it took goes back. Each copy has its own and never asks another server's.
`HELPER=off` in the machine's file does the work inside the copy instead.

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

## One log

A copy writes one log (`<DATA_DIR>/iosuite.log`, 20 MB at most with four older ones kept), every line marked with the
app it came from. Suite admins read it under **Settings › Servers › Logs**, from any app: filtered to the app
it was opened from, or every app on one timeline; with several copies, every copy's lines merged by time.

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
| [`tools/convert/`](tools/convert/) | moves an install of the first ioSuite to this program; run once, apart from the program |
| [`docs/`](docs/) | the guide and the website |

## License

GPL-3.0-or-later: see [LICENSE](LICENSE).

---
description: The machine's file (config.env), the settings kept in the Shared ioSuite database, the three ports and the iosuite command.
---

# Configuration

ioSuite is one program. A machine that runs it has **one small file**, `config.env` in the program folder
(`/opt/iosuite/config.env`), which says how to reach the Shared ioSuite database and which apps this machine runs.
**Everything else is kept in the Shared ioSuite database** and changed in the browser, under
**Settings › Apps › All settings** in any app, or with the `iosuite set` command. There is no settings file per
app.

## The machine's file

`KEY=value` lines, `#` for comments. The installer writes it; `config.env.example` in the program folder lists every
line. A variable already in the environment (a container's, a service's) wins over the file. The file holds the
database password: it is readable by its owner only.

```sh
# the Shared ioSuite database; every app's own database is on the same server, under the same login
IOSUITE_DB_HOST=db.example.lan
IOSUITE_DB_PORT=3306
IOSUITE_DB_NAME=iosuite
IOSUITE_DB_USER=iosuite
IOSUITE_DB_PASSWORD=…

APPS=iostart,iocalendar,iotask     # what this machine runs (empty: every app)

HOST=                              # where it listens (empty: every address of the machine)
PORT=80                            # the pages
SYNC_PORT=8443                     # phones, native apps and devices (off: not opened)
MCP_PORT=8444                      # MCP clients (off: not opened)

INTERNAL_URL=http://192.168.1.151  # where the suite's other machines call this one (default: its LAN address)
HTTPS_PORT=443                     # the pages over HTTPS, once there is a certificate (off: this machine stays without)
TLS_CERT_FILE=…  TLS_KEY_FILE=…    # a certificate of your own, instead of the one the suite asks for
DATA_DIR=/opt/iosuite/data         # what the apps write on their own, each in a folder of its name
LOG_FILE=/opt/iosuite/data/iosuite.log   # the one log (off: the journal only)
DB_CONNECTIONS=60                  # the most database connections this copy holds at once, all apps together
HELPER=on                          # heavy work in a helper process beside the copy (off: inside the copy)
HELPER_MEMORY_MB=2048              # the most the helper may hold (default: half the machine's or container's memory)
ADMIN_USER=…  ADMIN_PASSWORD=…     # the first admin, on an empty Shared ioSuite database
```

Only the five `IOSUITE_DB_*` lines are needed. Restart the service after changing the file
(`systemctl restart iosuite`).

`HOST` is every address of the machine by default:

| `HOST` | The program listens on |
| --- | --- |
| `127.0.0.1` | this machine only: for a reverse proxy on the same server, which is then the only way in |
| `192.168.1.151` | that one address, when the machine has several |
| `127.0.0.1,192.168.1.151` | each address named |

In Docker, leave `HOST` alone and publish the ports where you want them instead (`ports: ["127.0.0.1:80:80"]`).

## Database connections

A copy holds at most `DB_CONNECTIONS` connections to the database server at once, for all of its apps together (60
unless the file says otherwise). When all are in use, a request waits for one, up to twenty seconds, instead of asking
the database server for more than it gives: MariaDB allows 151 in all, by default, and answers the rest with an
error. A request that waited in vain is answered `503` with `Retry-After`.

Idle connections are closed after two minutes, and an app that needs one while the copy is at its allowance gets the
longest-idle one of another app. The helper process and ioPix's job process are processes of their own, each with a
quarter of that allowance beside the copy's. With several copies on one database server, their allowances add up: keep the sum
under the server's `max_connections`, or raise that.

## The helper process

Some work runs compiled libraries on what people upload: reading the text on a scan or a photo (Tesseract in ioDocs
and ioRecipe, RapidOCR in ioNote), a license's barcode (ioDocs), decoding a picture to keep or to make its small copy
(ioDocs, ioNote, ioRecipe, ioThings), and making the big PDFs (ioThings' inventory for the insurer, the estate PDF).
A copy runs its apps in one process, so a crash in that work would stop every app of the copy. Instead it runs in a
helper process beside the copy:

- a crash there fails only that upload or that PDF, with a message saying so; the next one starts a new helper;
- it is stopped when it takes longer than its time, when it holds more than `HELPER_MEMORY_MB`, and the system stops
  it first when memory runs out;
- it starts when there is work and ends after a minute and a half without, so a model it loaded (ioNote's text
  reader, a few hundred MB) does not stay in memory;
- each copy has its own, on its own machine: an app never asks another server's helper, so running some apps on one
  server and others on another works as before.

It reads the same machine's file and settings as the copy, and its log lines go to the copy's log. `HELPER=off` runs
the work inside the copy, as before. ioPix keeps its own job process for its AI models and makes its thumbnails itself.

## The three ports

A copy of the program opens three ports, so that each kind of traffic can have firewall rules of its own:

| Port | Who comes in | Signed in with |
| --- | --- | --- |
| `PORT` (80) | people, in a browser: the pages and what the pages ask for | the session cookie, a passkey, the proxy's sign-in |
| `SYNC_PORT` (8443) | phones, native apps and devices: CalDAV and CardDAV, calendar feeds, bookmark sync, the iPhone apps and widgets, ioHealth's uploads, e-ink screens, the wall display, scripts that use the API | an app password or a token; cookies are not read here |
| `MCP_PORT` (8444) | AI assistants (MCP) | an app password |

The app is chosen the same way on all three: by its own host name (`calendar.example.com`) or by its folder at the
suite's address (`home.example.com/calendar/`); both work at the same time. A request that arrives at the wrong port
is sent on to the right one, and a device given the pages' address is answered there: an app password is taken for an
app's `/api/` on the pages' port as well. ioContact's LDAP directory keeps its own port (3890).

With [a certificate](../run/https.md) the pages are also answered over HTTPS, on `HTTPS_PORT` (443), and the ports
for devices and MCP answer HTTPS as well as plain HTTP.

## Settings in the database

Under **Settings › Apps › All settings** (suite admins), with a section for the whole suite and one per app.
A change takes effect when the app starts again; the screen has a Restart button. The whole suite's:

| Setting | What it is |
| --- | --- |
| `PUBLIC_URL` | the suite's address as people type it (`https://home.example.com`); empty: the address it is reached at |
| `SYNC_URL`, `MCP_URL` | the same for devices and for MCP clients, when a reverse proxy gives them an address of their own; empty: the address asked, with that port |
| `COOKIE_DOMAIN` | one sign-in for every app under this domain (`example.com`), for apps on host names of their own |
| `TZ` | the time zone (`Europe/Brussels`) |
| `KEEP_DELETED_DAYS` | how long what a deletion leaves behind is kept (90) |
| `MCP_USER` | the account a local MCP client (stdio) acts as |

Every app has `PUBLIC_URL`, `SYNC_URL` and `MCP_URL` of its own (an address of its own beside its folder:
`https://calendar.example.com`), `DATA_DIR` and `DB_NAME`, and then what only it needs: the photos folder and digiKam
for ioPix, the LDAP port for ioContact, the backup folder for ioBackup. The screen lists them with what each is for.

`KEEP_DELETED_DAYS` is for the apps that phones and other devices sync with. A deleted event (ioCalendar), task
(ioTask) or contact (ioContact) leaves a marker, so a device learns of the deletion at its next sync; the marker goes
after this many days, and a device that stayed away longer starts its sync over. ioNote keeps the text of a deleted
note and its change log that long (the trash shows 30 days); after that an empty marker stays.

Three more places hold what is not a plain setting, all in the same database:

- **Settings › People**: people, roles, app passwords, sign-in at the proxy and the addresses of your reverse proxies.
- **Settings › Apps › The apps**: each app's default role, whether it requires sign-in, whether an assistant may
  use it, the three addresses it answers at, and **Its settings**, which opens the screens that app alone has
  (ioPix's models, ioCalendar's holidays, ioMoney's rules).
- **Settings › Keys**: the keys for services outside the suite. They can be written, never read back.
- **Settings › Servers › Certificate**: [the suite's own certificate](../run/https.md), for HTTPS without a reverse proxy.

## The `iosuite` command

For when the pages cannot be reached (a wrong address stored, say), and for scripts. On a server installed as root it
is on the path; otherwise it is `.venv/bin/iosuite` in the program folder.

```sh
iosuite apps                                  # the suite's apps: which this machine runs, where each answers
iosuite settings [APP]                        # every setting with the value stored now
iosuite set suite PUBLIC_URL https://home.example.com
iosuite set iopix PHOTOS_ROOT /srv/photos     # an empty value puts the default back
iosuite install                               # add or remove apps on this machine (see Getting started)
iosuite list                                  # every account and its roles
iosuite admin NAME                            # make NAME an admin
iosuite password NAME                         # set an account's password
iosuite sign-in-reset NAME                    # two-step sign-in off, passkeys removed (a lost phone)
iosuite cert                                  # the suite's own certificate: what is stored; --on, --off, --now
iosuite serve                                 # run the apps until stopped (what the service does)
```

## The jobs

The apps' background work — reminders, syncs and housekeeping — is run by **one job runner per server**, not by a
timer of its own per job. Suite admins see every job under **Settings › Servers › Jobs**: what it is, the app it
belongs to, how often it runs, the server that runs it, when it last ran, how long that took and what it said, with
**Run now** for its next turn. A job whose last run failed is marked and tried again at its next turn.

Two things follow from one runner: a job is never started again while its last run is still going, and jobs marked
heavy (a scan, an index, a backup) wait for each other, so a server never has two of them at the same moment. When
the suite runs on several servers, each job belongs to the server that runs its app, and **Run now** reaches it
there: the screen is the same whether the apps share a server or not.

The looks that happen every few seconds are jobs of the same runner: a kitchen timer that ended, a backup that was
asked for or is due, ioPix's index and its scan of the photo folders, the feeds, the e-ink screens that are pushed
to. Such a look that finds nothing to do asks the database for little or nothing, and its line on the screen is
written once a minute rather than at every look; what is asked for in a page (a backup, a scan) starts at once. A
server that nobody uses asks the database server about two questions a second, for all of its apps together.

## Pages that refresh themselves

A page of any app holds **one live-refresh connection** (`GET /api/live`, server-sent events) and hears on it what
changed in every app of the suite, so a page refreshes the moment there is a reason to instead of asking again on a
timer. A task ticked off in ioTask refreshes the start page's Today card; an event moved in ioCalendar refreshes a
calendar open in another tab; a photo added in ioPix refreshes the start page's strip.

Every app's own page listens too, and draws what it shows again when something of that app changed somewhere else:
a calendar or a contact saved on a phone (CalDAV, CardDAV), a task an assistant added over MCP, a sync from the
iPhone's Health app, new transactions from Monarch Money, a subscribed calendar that was read again, photos that
appeared on the disk, another person, another tab. A page is never drawn again under what somebody is doing: while a
dialog is open, something is being typed, or a form is on the page, it waits.

Nothing has to be configured, and an app needs no code of its own for the usual case: every request that changed
something says so. The lines travel through the Shared ioSuite database (`ios_changes`, kept a few minutes), so a change made on one
server reaches a page served by another, and a copy nobody has a page open on asks for nothing.

A line says only which app's what changed, and when — never what changed — so it is safe for any signed-in page, and
a line addressed to one person is given only to that person's own pages. The connection is dropped while a tab is
hidden and opened again when it comes back, and the browser reconnects by itself when a server restarts.

## The log

A copy keeps one log for all its apps (`data/iosuite.log`), each line marked with the app it came from. Suite admins
read it under **Settings › Servers › Logs**: filtered by app, level and time, searched, followed live, and
downloaded. When the suite runs as several copies the screen shows them on one timeline and says which server a line
came from.

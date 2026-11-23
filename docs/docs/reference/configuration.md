---
description: The machine's file (config.env), the settings kept in the Shared ioSuite database, the three ports and the iosuite command.
---

# Configuration

ioSuite is one program. A machine that runs it has **one small file**, `config.env` in the program folder
(`/opt/iosuite/config.env`), which says how to reach the Shared ioSuite database and which apps this machine runs.
**Everything else is kept in the Shared ioSuite database** and changed in the browser, under
**Settings › Global settings › Settings** in any app, or with the `iosuite set` command. There is no settings file per
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

## The three ports

A copy of the program opens three ports, so that each kind of traffic can have firewall rules of its own:

| Port | Who comes in | Signed in with |
| --- | --- | --- |
| `PORT` (80) | people, in a browser: the pages and what the pages ask for | the session cookie, a passkey, the proxy's sign-in |
| `SYNC_PORT` (8443) | phones, native apps and devices: CalDAV and CardDAV, calendar feeds, bookmark sync, the iPhone apps and widgets, ioHealth's uploads, e-ink screens, the wall display, scripts that use the API | an app password or a token; cookies are not read here |
| `MCP_PORT` (8444) | AI assistants (MCP) | an app password |

The app is chosen the same way on all three: by its own host name (`calendar.example.com`) or by its folder at the
suite's address (`home.example.com/calendar/`); both work at the same time. A request that arrives at the wrong port
is sent on to the right one. ioContact's LDAP directory keeps its own port (3890).

With [a certificate](../run/https.md) the pages are also answered over HTTPS, on `HTTPS_PORT` (443), and the ports
for devices and MCP answer HTTPS as well as plain HTTP.

## Settings in the database

Under **Settings › Global settings › Settings** (suite admins), with a section for the whole suite and one per app.
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

- **Settings › Security**: people, roles, app passwords, sign-in at the proxy and the addresses of your reverse proxies.
- **Settings › Global settings › Apps**: each app's default role and whether it requires sign-in.
- **Settings › Global settings › Keys and tokens**: the keys for services outside the suite. They can be written, never read back.
- **Settings › Global settings › Certificate**: [the suite's own certificate](../run/https.md), for HTTPS without a reverse proxy.

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

## The log

A copy keeps one log for all its apps (`data/iosuite.log`), each line marked with the app it came from. Suite admins
read it under **Settings › Global settings › Logs**: filtered by app, level and time, searched, followed live, and
downloaded. When the suite runs as several copies the screen shows them on one timeline and says which server a line
came from.

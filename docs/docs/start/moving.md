---
description: Move an install of the first ioSuite, where every app was a program of its own, to the one program, with its data, its settings and its addresses.
---

# Moving from the first ioSuite

The first ioSuite ([avandeputte/iosuite](https://github.com/avandeputte/iosuite)) ran every app as a program of its
own: a folder, a `config.env`, a service and a port each. A converter moves such an install to the one program. It is
a tool apart, in `tools/convert/`, that is run once; nothing in the program depends on it.

The databases stay where they are, so the move takes minutes whatever their size. Nothing of the old install is
deleted, so going back is one command.

## What changes

| | The first ioSuite | Afterwards |
| --- | --- | --- |
| The program | `/opt/<app>/app` for each app, each with its own Python environment | `/opt/iosuite`, one environment |
| Services | one for each app | `iosuite` |
| Settings | each app's `config.env` | one short `config.env` for the machine; the rest in the Shared ioSuite database, changed under Settings |
| Databases | one for each app, and the Shared ioSuite database | the same ones, as they are |
| Database logins | one for each app | the suite's one login, given the rights on each app's database |
| Data folders | `/opt/<app>/app/data` | `/opt/iosuite/data/<app>` |
| Ports | one for each app | three for the suite: the pages, devices, MCP |
| Keys an old file still held | `config.env` | Settings › Suite › Keys and tokens |

It reads an install made by the first ioSuite's installer on Linux, on one machine or on several. An install in
Docker containers is not covered.

## Before you start

- **Update the old suite** to 3.44.0 or later, from any app's Settings › Server › Update. The program expects the
  databases as that version left them, and the converter refuses an older one.
- **Back up the databases**, with ioBackup or `mysqldump`. The converter does not touch what the apps stored, but a
  backup is what makes any change to a server safe.
- Have the password of a **MariaDB administrator** at hand, unless MariaDB is on the same machine: root there needs
  none. It is used once, to give the suite's login the rights on each app's database, and is not kept.

## The move

On the machine that runs the old apps, as root.

**1. Fetch the program** beside the old install. This sets nothing up and stops nothing:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite2/main/install.sh | bash -s -- --fetch
```

**2. See what the move would do.** This changes nothing:

```sh
/opt/iosuite/.venv/bin/python /opt/iosuite/tools/convert/convert.py
```

It lists the old apps it found, the settings it will store, the data folders, the services, and what you will change
in your reverse proxy afterwards. What stands in the way is listed last, under **In the way**: an app older than
3.44.0, an app's database on another server than the Shared ioSuite database, a port the program needs that something
else holds. Nothing can be moved until that list is empty.

**3. Move:**

```sh
/opt/iosuite/.venv/bin/python /opt/iosuite/tools/convert/convert.py --apply
```

In this order, it:

1. writes the machine's `config.env`: the Shared ioSuite database, the apps found, where the program listens;
2. gives the suite's login the rights on each app's database;
3. stores what the old files said as settings in the Shared ioSuite database: each app's own address, its
   database's name, its own settings, and the keys an old file still held;
4. installs the Python packages the apps need, while the old apps still run;
5. stops the old services, copies each app's data folder, makes the service `iosuite` and starts it;
6. asks every app whether it answers, and only then switches the old services off.

The apps are away during step 5, for the time the copy of the data folders takes. When the program does not come up,
or one app does not answer, the old services are started again and the converter says what went wrong. Running it
again goes on from where it stopped.

## What you change afterwards

The converter's last lines say this for your install, with your addresses.

**In the reverse proxy or the tunnel.** Every address now goes to one machine's three ports. For each address the old
install had, three rules, the rules for paths above the rule for everything else:

| Paths | To port |
| --- | --- |
| The paths phones and devices use (`/dav`, `/.well-known/`, `/ics/`, `/v1/`, in the app's folder where it has one) | 8443 |
| `/mcp`, and each app's `/<folder>/mcp` | 8444 |
| Everything else | 80 |

With these rules, phones, calendar and contact accounts, the iPhone apps and MCP clients keep the addresses they
have, and nobody sets anything up again. Until the rules are there, the pages work and phones do not sync from
outside your network. [Reverse proxy and HTTPS](../run/reverse-proxy.md) and
[Cloudflare Tunnel and Access](../run/cloudflare.md) have examples for Caddy, nginx and Cloudflare.

**Addresses by the server's name.** An app that was reached as `http://SERVER:PORT/` is now in its folder,
`http://SERVER/calendar/`, and for devices at `http://SERVER:8443/calendar/`. An app with a name of its own
(`https://calendar.example.com`) keeps that name; it also answers in its folder at the suite's address.

**Settings an old file held** are under each app's Settings from now on, and the keys under Settings › Suite › Keys and
tokens. The old `config.env` files are no longer read.

## Options

| Option | What it does |
| --- | --- |
| `--from DIR` | where the old apps are, each in `DIR/<app>/app`. By default `/opt` and `~/iosuite`. Can be given more than once |
| `--apps APP,APP` | only these of the apps found |
| `--db-admin USER` | a MariaDB administrator for the rights. Its password is read from `DB_ADMIN_PASSWORD`, or asked |
| `--data copy` | each app's data folder is copied into the program's (the default); the old one stays as a spare |
| `--data move` | it is moved, which needs no second copy's worth of disk |
| `--data stay` | it stays where it is, and the app is told where under Settings. For a large folder on a disk of its own |
| `--device-address URL` | one address for phones and devices (`https://sync.example.com`) instead of each app's old address. Every phone and device is then set up again with it |
| `--mcp-address URL` | the same, for MCP clients |
| `--port N`, `--sync-port N`, `--mcp-port N` | other ports than 80, 8443 and 8444 |
| `--host ADDR` | the address the program listens on, when not the old apps' |
| `--user USER` | the account the service runs as. By default the one the old services ran as |
| `--no-service` | make no service and stop none: stop the old apps yourself first, and start the program yourself |
| `--wait SECONDS` | how long the apps get to answer before the old services are started again (120) |

A folder the old file named itself (`DATA_DIR`, ioPix's `PHOTOS_ROOT`, ioBackup's `BACKUP_DIR`) always stays where it
is. The photos are never copied.

## Apps on several machines

Run the three steps on each machine that has old apps. Each machine gets a copy of the program with its own apps,
against the same Shared ioSuite database, and together they are one suite, as described in
[Several copies and several servers](several-apps.md). Start with the machine that runs the start page: the suite's
address comes from its file, and what the suite says already (its sign-in domain, its time zone) is kept when the
other machines are moved.

When you would rather bring an app from another machine onto this one, copy its old `config.env` here and name it:

```sh
/opt/iosuite/.venv/bin/python /opt/iosuite/tools/convert/convert.py --config iopix=/root/iopix-config.env
```

Its settings are stored like the others'. Its service is on the other machine and its data folder too: stop the one
and bring the other across yourself.

## Going back

```sh
systemctl disable --now iosuite
systemctl enable --now iostart iocalendar iotask    # the old services: the converter's last lines name yours
```

The old folders, files and logins are as they were. With `--data move`, move the data folders back first; the
converter prints the commands. What the family added in the meantime is in the same databases, so the old apps
show it too.

Once you are content, remove the old install: each old app's folder under `/opt` and its
`/etc/systemd/system/<app>.service`. Keep a data folder that stayed where it was.

---
description: Run ioSuite as one copy, as several copies on one machine, or on several servers, and move an app from one to another.
---

# Several copies and several servers

A **copy** is one running process of the program with its own list of apps. Most households need one. Two reasons to
have more:

- **ioPix apart from the rest.** A scan of a large photo library and the AI models are heavy. In a copy of its own, a
  busy ioPix cannot slow the calendar down, and it can be restarted, or run out of memory, without the other apps
  noticing.
- **Apps where their data is.** ioPix on the machine that has the photos, the rest on a small server.

However many copies there are, it is one suite: they read the same Shared ioSuite database, so the accounts, the
sign-in, the settings, the start page's tiles, the menus and the log screen are the same everywhere.

## One copy (the default)

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash
```

One service (`iosuite`), one process, every app you ticked, on ports 80, 8443 and 8444.

## A second copy on the same machine

```sh
iosuite install --copy pix --apps iopix
```

This makes a copy named `pix` that runs ioPix, as a service of its own (`iosuite-pix`), and takes ioPix out of the
main copy. Both use the same program folder and the same Python environment, and are updated together. The copy has:

| | Main copy | The copy `pix` |
| --- | --- | --- |
| Its file | `/opt/iosuite/config.env` | `/opt/iosuite/copies/pix/config.env` |
| Service | `iosuite` | `iosuite-pix` |
| Ports (pages, devices, MCP) | 80, 8443, 8444 | 8081, 8082, 8083 (`--port`, `--sync-port`, `--mcp-port` for others) |
| Log | `data/iosuite.log` | `data/iosuite-pix.log` |

**People keep using the main copy's address.** A request for `/pix/` that arrives at the main copy is passed across
to the copy that runs ioPix, with the person's sign-in, so nothing changes in the browser, in bookmarks or in a
reverse proxy. The copy's own ports are there for the main copy to call, and for you to look at it directly.

```sh
iosuite apps                      # which copy runs each app, and where each answers
iosuite install --copy pix --add iodocs     # move another app into the copy
iosuite install --remove-copy pix           # the copy goes; its apps' data stays
iosuite install --add iopix                 # and ioPix runs in the main copy again
```

## On several servers

Install the program on each server and give every one the **same Shared ioSuite database**; say on each which apps it
runs. The database login must be allowed to connect from each of them.

```sh
# the small server: everything but ioPix
curl -fsSL …/install.sh | bash -s -- --db db.lan --apps iostart,iocalendar,iotask,iocontact,ionote
# the server with the photos
curl -fsSL …/install.sh | bash -s -- --db db.lan --apps iopix --set iopix.PHOTOS_ROOT=/srv/photos
```

The second installer finds the accounts and the settings that are there. Each server writes in
the suite's list of apps which apps it runs and at which address inside your network, and that is how the others find
it: a request for an app that runs on the other server is passed across. So one public address is enough for the
whole suite, pointed at either server (the one with the start page is the natural choice).

The servers call each other at their addresses inside the network. A server that cannot tell its own (in a container
behind a bridge, say) is told in its file: `INTERNAL_URL=http://192.168.1.152`.

Settings › Servers › Updates updates all of them: each server sees the request in the Shared ioSuite database
and runs its own update. `update.sh` in the program folder does one server by hand.

### Moving an app to another server

1. On the new server: `iosuite install --add iodocs` (or tick it in the list). It finds the app's database and uses it
   as it is.
2. On the old server: `iosuite install --remove iodocs`.

Nothing is copied or converted: the app's data is in its database, which does not move. An app that keeps files in a
data folder (ioPix's thumbnails and models, ioNote's and ioBackup's work folders) builds them again or needs the folder
copied: `<DATA_DIR>/<app>`. ioPix also needs its photos folder on the new server.

## Docker

One container is one copy. The [Docker Compose builder](https://iosuite.iothing.net/compose/) writes a stack with one
container for the suite, or with ioPix in a second container of the same image; see [Docker](docker.md).

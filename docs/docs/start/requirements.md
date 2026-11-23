---
description: What ioSuite needs to run.
---

# Requirements

## A database server

The suite keeps its data in **MariaDB or MySQL**: a database for each app you run, and the **Shared ioSuite
database** (`iosuite`) with the accounts, roles, app passwords and every setting. They are on one server, under one
login. More in [Databases](../reference/databases.md).

The databases don't have to exist beforehand. The installer asks for a MariaDB / MySQL **administrator** (for example
`root`): give one and it creates the databases and the login. Nothing is dropped, and the administrator's password is
used once and not written anywhere. On a server without MariaDB, `--mariadb` installs it first (Debian, Ubuntu). The
Docker stack brings a MariaDB of its own.

The login must be allowed to connect from where the program runs (a container has an address of its own).

## Somewhere to run it

Pick one.

| Way | What it takes | Guide |
| --- | --- | --- |
| **Proxmox VE** | a Proxmox VE host. One command creates an unprivileged Debian 13 container and installs the suite inside | [Proxmox VE](proxmox.md) |
| **Docker** | Docker with Compose, amd64 or arm64. One image, public on `ghcr.io/avandeputte/iosuite2` | [Docker](docker.md) |
| **Any Linux** | Python 3.10 or later. One command fetches the program, makes its environment and a systemd service | [Any Linux or Mac](linux-mac.md) |

The suite is one program: a server runs one process for all the apps you chose. That process holds about 100 MB with
two apps and about 250 MB with all thirteen, plus what ioPix needs while it works on photos. A container with 2 CPUs
and 2 GB of memory is plenty without ioPix. With ioPix and its AI features (content search, faces, objects, text in
photos) give it 4 CPUs and 4 GB, and a few GB of disk for the models, or run ioPix as a copy of its own
([Several copies](several-apps.md)).

## Three ports

| Port | For |
| --- | --- |
| 80 | the pages, in a browser |
| 8443 | phones, native apps and devices (calendars and contacts, bookmark sync, the iPhone apps, e-ink screens) |
| 8444 | AI assistants (MCP) |

Each can be another port, or not opened at all; see [Configuration](../reference/configuration.md#the-three-ports).
ioContact also serves an LDAP directory, on port 3890.

## For use outside your home network

A reverse proxy that terminates HTTPS (Caddy, nginx, HAProxy, Traefik) or a Cloudflare Tunnel, and a domain. Phones
want HTTPS for CalDAV and CardDAV accounts away from home. See [Reverse proxy and HTTPS](../run/reverse-proxy.md).

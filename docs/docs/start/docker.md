---
description: Run ioSuite with Docker Compose from one image, and the builder that writes the stack file for you.
---

# Docker

The suite is **one image**, public for amd64 and arm64:

| Image | What is in it |
| --- | --- |
| `ghcr.io/avandeputte/iosuite2:latest` | every app |
| `ghcr.io/avandeputte/iosuite2:ai` | the same with ioPix's AI packages (content search, objects, text in photos); amd64 |

A container runs the apps its `APPS` variable names (empty: all of them). Every version of the suite is tagged as
well (`v4.0.0`, `v4.0.0-ai`), if you'd rather pin one than follow `latest`.

## Build your stack

The [Docker Compose builder](https://iosuite.iothing.net/compose/) asks which apps you want, whether MariaDB goes in
the stack or you already run a server, the first admin, whether ioPix gets a container of its own, and how the suite
is reached (plain HTTP, a Caddy container that gets the certificates, or your own reverse proxy). It writes one
`docker-compose.yml` with nothing left to edit:

```sh
docker compose up -d
docker compose logs iosuite   # what was set up (its first lines, up to ok)
```

The container sets the stack up before it serves, at every start (`iosuite stack`): it makes the databases and the
login that are missing, the tables and the first admin, and writes what the file says (the suite's address, the
reverse proxy's addresses, the photos folder) into the Shared ioSuite database, so there is nothing to click
afterwards. What a suite admin changes under Settings later stays until the file says something new, and a setting the
file no longer says goes back to its default. The page works in
your browser alone: nothing you type is sent anywhere. To add or remove an app later, open your file on the page
again; it holds its own answers. Ticking *Fill it with demo data* adds a made-up family with something in every app
([Demo data](demo.md)).

The data lives in one folder of the server that you choose (`/opt/iosuite` unless you say otherwise), not in Docker
volumes: `db` for MariaDB, `data` for what the apps write on their own and the log, `caddy` when Caddy is in the
stack. The suite writes as user 1000, so its folder is made and given to that user once, before the first start; the
file and the page's steps hold the one command for it:

```sh
sudo mkdir -p /opt/iosuite/data && sudo chown 1000:1000 /opt/iosuite/data
```

MariaDB and Caddy see to their own folders. A folder Docker makes by itself belongs to root, and the suite can't
write there.

## By hand

[`docker-compose.yml`](https://github.com/avandeputte/iosuite2/blob/main/docker-compose.yml) in the repository is the
same stack with every app: a MariaDB and one container for the suite.

```sh
curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite2/main/docker-compose.yml
# set the passwords, the admin, the photos folder and the time zone (the CHANGE ME lines), then
docker compose up -d
```

The suite answers on port 80: the start page at `/`, every app in its folder (`/calendar/`, `/notes/`). Phones,
native apps and devices use port 8443, MCP clients port 8444, ioContact's LDAP directory port 389.

- **Fewer apps:** `APPS: iostart,iocalendar,iotask`.
- **A setting:** a `--set=APP.NAME=VALUE` line in the container's command (`--set=suite.PUBLIC_URL=https://home.example.com`),
  or Settings › Global settings › Settings once it runs.
- **ioPix in a container of its own**, so that its scans never slow the others: the second service at the end of the
  file, the same image with `APPS: iopix`. It is reached through the first container, at the same addresses as
  before, so nothing of it needs publishing.
- **A database server you already run:** remove the `db` service, set `IOSUITE_DB_HOST` to it, and either create the
  databases and the login yourself ([Databases](../reference/databases.md#creating-them)) and drop `--db-admin=root`,
  or leave it and give `DB_ADMIN_PASSWORD` an administrator's password.

The stack works in Dockge or Portainer too. The image has a health check, and holds no data of its own: a container
can be replaced at will.

**A new stack file on an old database.** MariaDB keeps the root password it was first started with, so a stack file
made again (new passwords) on the database of an earlier one is refused: the container's log says *Access denied for
user 'root'*. Start over by stopping the stack and emptying the `db` folder of its data folder; it deletes the stack's
data. Or keep the data by putting the earlier passwords back (open the earlier file in the builder).

## Updating

```sh
docker compose pull && docker compose up -d
```

In a container, pulling the image takes the place of the web app's **Update**.

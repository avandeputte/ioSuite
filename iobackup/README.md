# ioBackup

*The database backups of ioSuite ([ioStart](../iostart/), [ioCalendar](../iocalendar/),
[ioContact](../iocontact/), [ioNote](../ionote/), [ioPix](../iopix/),
[ioHealth](../iohealth/), [ioTask](../iotask/), [ioDNS](../iodns/)).*

Backs up the MariaDB server the suite's apps keep their data on (and any other MariaDB or Galera server) on demand or
on a schedule, to a folder or Google Drive, keeps the newest *N* backups of each job, and **restores exactly what you
pick**: whole databases, single tables or views, stored routines, events, users and roles, onto the same server or
another, under the same name or a new one. An admin tool of the suite, for suite admins only: the gear menu of the
ioStart start page lists it for them, nobody else sees it. FastAPI and a single-page vanilla JS app, built the same
way as the other io apps, signed in with the suite's shared accounts ([`iosuite_shared`](../iosuite_shared/)),
with its own settings in MariaDB / MySQL. It grew out of [mariadb-backup](https://github.com/avandeputte/mariadb-backup),
whose backup files it reads and writes unchanged.

## What it does

- **Servers**: the MariaDB servers to back up and restore onto, by host and port or a socket on the same machine.
  *Test* shows the version, whether it is a Galera node and in which state, and its databases. *The suite's own
  database server* fills in the address the apps use.
- **Destinations**: a folder (a local disk, a mounted NAS share) or Google Drive (your own account with a device code,
  or a service account in a Shared Drive).
- **Backup jobs**: a server, *all databases* (new ones are picked up by themselves) or a list, with or without users and
  grants, a destination, a schedule (every few hours, daily, weekly, monthly, a cron expression, or on demand only) and
  **how many backups to keep**: after each good backup the older ones of that job beyond that number are deleted
  from the destination; 0 keeps them all.
- **Run now** on any job, or wait for the schedule. Every run, scheduled or by hand, is in **Activity** with its log,
  live while it runs, and can be cancelled.
- **Backups**: each destination's backups, to verify (every piece against its checksum), download, delete, or
  **restore**: tick databases (everything, or pick tables, views, routines, events), optionally under another name,
  tick users and roles, pick the server and the options (structure only, replace existing users, carry on past
  errors), review what it would overwrite there, and confirm.
- **Stored files as files**: the photos, scans, receipts and attachments the suite's apps keep in their databases are
  also written out as plain files in each backup, to open without restoring anything (see below). *Download as .zip*
  on a backup gives just those.

Access: suite admins only (a backup holds everybody's data). Everybody else has no access, whatever role or default
role says, and ioBackup takes no roles. The servers' passwords and the Google
keys are kept with the suite's keys and tokens (start page: Settings › Keys), never shown
back.

## What a backup is

One file, `<job>-<YYYYmmdd-HHMMSS>.mdbk.tar`, holding:

* one consistent `mariadb-dump --single-transaction` of all the job's databases (one snapshot across them), split into
  a gzip file per object so any piece can be restored on its own;
* `accounts.json`: every user (`SHOW CREATE USER`) and role with its grants;
* `manifest.json`: what is in it, the source server and its version, and a SHA-256 of every piece;
* `files/`: the files the apps keep in their databases, as plain files (on by default; a job's *The files the apps
  keep in their databases* turns it off). An app is recognised by its tables, whatever its database is called:

  | App | Where its files go |
  | --- | --- |
  | ioThings | `files/ioThings/<thing>/<file>` (manuals, receipts, warranties named `Manual - …`, `Receipt - …`) |
  | ioDocs | `files/ioDocs/<document>/<file>`, archived ones under `Archived/` |
  | ioMoney | `files/ioMoney/<year>/<day> <merchant> <amount> - <file>` |
  | ioNote | `files/ioNote/<person>/<note title>/Picture.<ext>` and the note's attachments |
  | ioRecipe | `files/ioRecipe/<recipe>/Photo 1.jpg`, `Step 3.jpg` |
  | ioStart | `files/ioStart/Bookmark icons/<bookmark>.svg` |

  They are read just after the dump, in one transaction per database; the dump stays what a restore reads, and the
  bytes are the same. Two things of the same name get `Name (2)`. Any archive tool opens the backup to get at them
  (`tar -xf Nightly-20261103-020000.mdbk.tar files`, or double-click it on a Mac), and so does
  `python3 -m app.offline files Nightly-20261103-020000.mdbk.tar -o files`. This makes a backup larger by about the
  size of those files, which are in the dump as well.

It is plain SQL inside a plain tar, readable without ioBackup, and `iobackup/offline.py` restores it on any machine with
Python 3 and the MariaDB client, with no web app, database or settings (for when the machine that ran ioBackup is gone):

```sh
python3 -m app.offline list    Nightly-20261103-020000.mdbk.tar
python3 -m app.offline verify  Nightly-20261103-020000.mdbk.tar
python3 -m app.offline restore Nightly-20261103-020000.mdbk.tar --all -H db1 -u root -p
python3 -m app.offline restore Nightly-20261103-020000.mdbk.tar --db notes.nts_notes --rename notes=notes_old -H db1 -u root -p
python3 -m app.offline restore Nightly-20261103-020000.mdbk.tar --db notes --sql-out notes.sql   # just write the SQL
```

The `mysql` system database is not dumped; users, roles and grants are exported logically instead, which is what moves
cleanly between versions and servers. Server settings (`my.cnf`), plugins and binary logs are not part of a backup.
ioBackup's own settings live in its database (`iobackup`): back that up too, with any job on the same server.

## Galera

* Back up from one node. With *take this node out of flow control* on (the job's more options), the node sets
  `wsrep_desync=ON` while it dumps, so a long dump does not hold the cluster back, and turns it off again afterwards,
  also when the backup fails. The user then needs `SUPER`.
* Only InnoDB is covered by the snapshot and replicated by Galera; tables in other engines are named in the run's log
  and in the server's test.
* Dumps are taken with `--skip-add-locks`, so a restore never issues `LOCK TABLES`. Restore onto any one node: tables,
  rows, users and grants replicate to the rest of the cluster.

## Google Drive

**Your Google account.** Once, in the [Google Cloud console](https://console.cloud.google.com/): make (or pick) a
project, turn on the **Google Drive API**, set up the OAuth consent screen (External; add yourself as a test user, or
publish it) and make an **OAuth client ID** of the type **TVs and Limited Input devices**. In ioBackup, add a Google
Drive destination with that client ID and secret and a folder name, then **Sign in with Google**: open the address
shown on any device and type the code. ioBackup asks only for `drive.file`: it sees the folder and files it makes and
nothing else in your Drive. A consent screen left in *Testing* gives sign-ins that Google ends after 7 days: publish it
(`drive.file` needs no verification).

**A service account**, for a Google Workspace Shared Drive: make a service account and a JSON key, add the service
account to the Shared Drive as a Content manager, and give the ID of a folder in it. A service account has no storage
of its own, so a folder in a personal My Drive does not work.

Uploads are resumable and retried; a restore from Drive downloads the backup first (`CACHE_DIR`).

## Privileges

For backups:

```sql
CREATE USER 'iobackup'@'app-host' IDENTIFIED BY '...';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES, SHOW DATABASES ON *.* TO 'iobackup'@'app-host';
-- Galera desync also needs: GRANT SUPER ON *.* TO 'iobackup'@'app-host';
```

`app-host` is the machine the app runs on (`localhost` when MariaDB is on the same machine); a user for any host (`'%'`)
with a password someone could guess is what to avoid. The installers make the user this way when given a MariaDB administrator.

A restore makes databases, users and grants: add the server you restore onto with an administrator's account (root…).
Stop the apps whose database you restore over, and start them again after.

## Run

ioBackup is one of the apps of [ioSuite](../README.md), one program that runs the apps it is told to. Install the suite
with ioBackup in it, alone or with the others, on any Linux machine:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --apps iobackup
```

It asks for the MariaDB server, the first admin and the suite's address, then starts the service; leave `--apps` out
for the list of every app, to tick. On a server that already runs the suite:

```sh
iosuite install --add iobackup       # --remove iobackup stops running it; what it stored stays
```

In Docker, name it in `APPS` in the stack file ([docker-compose.yml](../docker-compose.yml); empty there: every app); on
Proxmox VE, tick it in the list the container's script shows. The guide has each way in full:
[any Linux or Mac](../docs/docs/start/linux-mac.md), [Docker](../docs/docs/start/docker.md), [Proxmox VE](../docs/docs/start/proxmox.md)
and [one app or all of them](../docs/docs/start/one-or-all.md).

| | |
| --- | --- |
| Address | `/backup/` at the suite's address (`https://home.example.com/backup/`), and a name of its own if you give it one |
| Database | `iobackup`, beside the Shared ioSuite database (the accounts and every setting), both under the suite's one login; the tables are made on the first start and brought up to date by later versions by themselves |
| On the server | the MariaDB client programs (`mariadb-dump`, `mariadb`); the installer, the Proxmox script and the container image have them |

Local backups go to the folder `BACKUP_DIR` names (`/var/backups/iobackup`; `/backups` in the Docker stack): put it on another disk than the database. In a Proxmox container, mount a disk or a NAS share there (`pct set <id> -mp0 /mnt/backups,mp=/var/backups/iobackup`).

From a shell, in the program folder (`/opt/iosuite` when installed as root):

```sh
.venv/bin/python -m iobackup.cli check     # connect to the databases and say what is there
.venv/bin/python -m iobackup.cli jobs      # the jobs, with their schedule and next run
.venv/bin/python -m iobackup.cli run JOB   # back up now (the job's name or number), here, without the web app; prints the log
.venv/bin/python -m iobackup.cli runs      # the last runs
```

Accounts are the suite's: `iosuite admin NAME --app iobackup` makes someone an admin of ioBackup only (`iosuite admin NAME`: of
the whole suite), `iosuite password NAME` sets a password; see [Accounts and roles](../docs/docs/run/accounts.md).

## Configuration

ioBackup has no file of settings. The machine's one file (`config.env` in the program folder) says how to reach the Shared
ioSuite database and which apps run here; everything else is kept in that database. Suite admins change it under
**Settings › Apps › All settings**, which has a section for the whole suite and one for ioBackup, or from a shell;
a change applies when the app starts again:

```sh
iosuite settings iobackup        # what may be set, with the value stored now
iosuite set iobackup PUBLIC_URL https://backup.example.com    # no value: back to the default
```

| Setting | Meaning |
| --- | --- |
| `PUBLIC_URL`, `SYNC_URL`, `MCP_URL` | an address of its own for the pages, for devices and for MCP clients (`https://backup.example.com`), beside its folder at the suite's address |
| `DATA_DIR` | where the app writes on its own (`iobackup/` in the machine's `DATA_DIR`) |
| `DB_NAME` | the name of its database (`iobackup`) |
| `BACKUP_DIR` | suggested backup folder (`/var/backups/iobackup`). The folder a new local destination suggests |
| `WORK_DIR` | work folder. Where a backup is put together before it is stored (room for two compressed backups). Empty: in the data folder |
| `CACHE_DIR` | cache folder. Where a backup read from Google Drive is kept while it is restored. Empty: in the data folder |
| `BACKGROUND` | run the queue and the schedule (`1` or `0`; on by default). Off: nothing runs and no schedule fires; backups are only taken from a shell |

The suite's own settings (its address, the domain the sign-in is shared on, the time zone, how long deletions are kept), the
machine's file and the three ports are in the guide's [Configuration](../docs/docs/reference/configuration.md).

Schedules run in `TZ` (or the host's time zone). The servers, destinations and jobs are set in the app itself.

## API

The paths below are ioBackup's own: at the suite's address they are inside its folder (`https://home.example.com/backup/api/…`), at a name of its own they are as written. A script signs in with an app password at the pages' address. The [address for devices](../docs/docs/reference/configuration.md#the-three-ports) (port 8443), the one to open to the internet for phones and native apps, serves nothing of ioBackup. MCP clients use the address for MCP (port 8444).

Everything the web app does is a JSON API under `/api/` (documented at `/api/docs`), open to any client signed in with
the user name and an app password (HTTP Basic or a bearer token): `GET /api/overview`, `POST /api/jobs/<id>/run`,
`GET /api/runs`, `GET /api/runs/<id>` (with its log), `GET /api/destinations/<id>/backups`,
`POST /api/destinations/<id>/backups/<name>/verify`, `POST .../preview` and `POST .../restore` (`{serverId, plan}`).

## Tests

```sh
pip install -e '.[all,test]'          # in the program folder, once
python -m pytest iobackup/tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

The dump splitting, the schedules and Google Drive (against a stand-in of its API) are tested without a database; the
API tests need a MariaDB (a Docker container, or the server `IOSUITE_TEST_DB` names) and the MariaDB client, and take
real backups of scratch databases there and restore them. `tests/integration.sh` loads a fixture with every kind of
object, backs it up, drops everything, restores it and compares.

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](../LICENSE).

---
description: Install ioSuite on any Linux machine with one command, and add or remove apps later.
---

# Any Linux or Mac

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash
```

As root this puts the program in `/opt/iosuite` and runs it as a systemd service; as another user, in `~/iosuite`
(`--into DIR` for another folder). It needs Python 3.10 or later, and installs it on Debian, Ubuntu and Fedora when it
is missing.

## What it asks

- **the apps** this machine runs: a list to tick, every app by default;
- **the database server**, the name of the Shared ioSuite database and the suite's login (`iosuite`, `iosuite`);
- **a MariaDB administrator**, optional, who creates the databases and the login for you;
- **the first admin**: a name and a password (or none: the first account is then made in the browser);
- **the suite's address** behind your reverse proxy, if you have one (`https://home.example.com`);
- what an app cannot guess: ioPix asks for the folder with the photos, and for digiKam's database folder if you use digiKam.

Then it installs the Python packages the chosen apps need and the system packages some of them use (exiftool and
ffmpeg for ioPix, tesseract for ioDocs and ioRecipe), writes `config.env` (readable by its owner only), creates the
tables and the admin, and starts the service. The suite answers on port 80.

## Run it again

The same command, or `iosuite install`, shows the list of apps with the ones that run here ticked. Tick and untick to
add and remove apps. Nothing an app stored is deleted when it is removed: its database stays, and adding it again
finds it.

```sh
iosuite install                         # the list, to tick and untick
iosuite install --add iomoney,iodocs    # run these too
iosuite install --remove iodns          # stop running it
iosuite install --list                  # what this machine runs
```

## Without questions

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh \
  | ADMIN_PASSWORD=… bash -s -- --yes --mariadb --admin alex
```

That is a complete suite on a blank Debian or Ubuntu server, MariaDB included. The options:

| Option | What it sets |
| --- | --- |
| `--apps LIST` or `all`, `--add LIST`, `--remove LIST` | the apps this machine runs |
| `--db HOST[:PORT]`, `--db-name NAME`, `--db-user USER` | the database server, the Shared ioSuite database, the login |
| `--db-admin USER` | a MariaDB administrator who creates the databases and the login |
| `--mariadb` | install MariaDB on this machine first |
| `--admin NAME` | the first admin |
| `--address URL` | the suite's address |
| `--set APP.NAME=VALUE` | any setting: `--set iopix.PHOTOS_ROOT=/srv/photos`, `--set suite.TZ=Europe/Brussels` |
| `--host ADDR`, `--port N`, `--sync-port N`, `--mcp-port N` | where it listens |
| `--extras LIST` | optional sets of Python packages: `iopix-ai`, `iorecipe-ai` |
| `--user USER`, `--service`, `--no-service` | the service's account; a systemd service or not |

Passwords never go on the command line: `IOSUITE_DB_PASSWORD` (the suite's login), `DB_ADMIN_PASSWORD` (the MariaDB
administrator) and `ADMIN_PASSWORD` (the first admin) in the environment.

## Without a service

On a Mac, or with `--no-service`, nothing is started for you:

```sh
~/iosuite/.venv/bin/iosuite serve
```

## From a checkout

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite
python3 -m venv .venv && .venv/bin/pip install -e ".[all]"
.venv/bin/iosuite install --no-service
.venv/bin/iosuite serve
```

## Accounts from the command line

```sh
iosuite list                              # the accounts and their roles
ADMIN_PASSWORD=… iosuite admin alex       # make alex an admin
iosuite password alex
```

See [Accounts and roles](../run/accounts.md) and [the `iosuite` command](../reference/configuration.md#the-iosuite-command).

# Moving from the first ioSuite

The first ioSuite ([avandeputte/iosuite](https://github.com/avandeputte/iosuite)) ran every app as a program of its
own: a folder, a `config.env`, a service and a port each. `convert.py` moves such an install to this one program.

It is apart from the program on purpose. Nothing imports it, the program holds no code for the old layout, and it is
run once.

## Use

On the machine that runs the old apps, as root:

```sh
# 1. the program, beside the old install: sets nothing up, stops nothing
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --fetch
# 2. what the move would do: changes nothing
/opt/iosuite/.venv/bin/python /opt/iosuite/tools/convert/convert.py
# 3. the move
/opt/iosuite/.venv/bin/python /opt/iosuite/tools/convert/convert.py --apply
```

Update the old suite to 3.44.0 or later first, and back its databases up. `convert.py --help` lists the options;
the guide's page [Moving from the first ioSuite](../../docs/docs/start/moving.md) walks through it.

## What it does

1. Reads the old install: each `/opt/<app>/app/config.env`, its service, its data folder.
2. Writes this program's one file for the machine (`config.env`): the Shared ioSuite database, the apps found, where
   it listens.
3. Gives the suite's one login the rights on each app's database (`--db-admin`, a MariaDB administrator). The
   databases themselves are not changed, copied or renamed.
4. Stores what the old files said as settings in the Shared ioSuite database: each app's own address, its database's
   name, its own settings. Keys an old file still held go to Keys and tokens.
5. Installs the packages, stops the old services, copies each app's data folder (`--data move` or `--data stay` for a
   large one), and has `iosuite install` make the one service.
6. Asks every app whether it answers, and only then switches the old services off. When the program does not come
   up, the old services are started again.

Nothing of the old install is deleted. Going back is `systemctl disable --now iosuite` and starting the old services
again; the last lines the converter prints say so with their names.

Phones, devices and MCP clients keep their addresses when the reverse proxy sends the paths they use to the port for
devices (8443) and `/mcp` to the port for MCP (8444). The converter prints those rules for the addresses it found.

## What it does not cover

- An install of the first ioSuite in Docker containers.
- An old suite older than 3.44.0: update it first.
- An app whose database is on another server than the Shared ioSuite database: the one program keeps every database
  on one server. The converter says how to bring it across.

## The files

| | |
| --- | --- |
| `convert.py` | the converter |
| `test_convert.py` | its tests: what it reads, what it plans, what `--apply` does to the services, with nothing real touched |
| `rehearse.py` | a rehearsal of the whole move: makes an install of the first ioSuite from a checkout of its code, fills it with the demo family, moves it, and holds what every app lists afterwards to what it listed before |

```sh
python -m pytest tools/convert
IOSUITE_TEST_DB=127.0.0.1:3306:root:PASSWORD python tools/convert/rehearse.py --old /path/to/a/checkout/of/the/first/ioSuite
```

With `--service`, as root on a scratch machine with systemd, the rehearsal is made the way a server is moved: the old
apps run as services, a first move is made to fail and must put them back, the second makes the service `iosuite` and
switches the old ones off, and going back is the two commands the converter prints. Never on a machine that runs
ioSuite: it makes and removes the services.

The checks on GitHub run the tests and both rehearsals on every change (`.github/workflows/tests.yml`, the job
`move`).

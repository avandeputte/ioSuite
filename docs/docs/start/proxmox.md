---
description: Install ioSuite in a Proxmox VE container with one command.
---

# Proxmox VE (LXC)

On the Proxmox VE host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite2/main/proxmox/ct/iosuite.sh)"
```

The script follows the layout of the Proxmox VE community scripts. It asks the framework's usual questions (the
container's id, storage, resources, network), then two that only the host can answer:

- **a folder of photos on the host**, for ioPix: it is bind-mounted into the container at `/mnt/photos`. Leave it empty
  when you don't install ioPix or have no photos on this host.
- **the folder with digiKam's `digikam4.db`**, if you use digiKam with its SQLite database: mounted at
  `/mnt/digikamDB`. Empty for no digiKam; a digiKam database on a MySQL server is set in Settings afterwards.

It creates an unprivileged Debian 13 container (2 CPUs, 2 GB of memory and 12 GB of disk; 4 CPUs, 4 GB and 24 GB when
photos are mounted) and then runs **the suite's own installer inside it, on your terminal**: the apps to run, the
database server, the first admin. Those questions are described under [Any Linux or Mac](linux-mac.md#what-it-asks).
When it ends, the suite answers at the container's address on port 80.

The container needs a MariaDB or MySQL server to reach. Answer the administrator question to have the databases and
the login made for you, or add `--mariadb` (below) to put MariaDB in the container itself.

## Later

```sh
pct enter 105          # the container's id
iosuite install        # the list of apps: tick and untick
```

Updating: **Settings › Global settings › Updates** in any app, or `update` in the container's console as with every
community script, or `sh /opt/iosuite/update.sh`.

## Without questions

The installer's options go in `IOSUITE_INSTALL`, the two folders in `IOSUITE_PHOTOS` and `IOSUITE_DIGIKAM`, and the
passwords in the environment; the framework's own answers have their usual `var_*` variables.

```sh
IOSUITE_PHOTOS=/mnt/photos IOSUITE_DIGIKAM="" ADMIN_PASSWORD=… \
IOSUITE_INSTALL="--yes --mariadb --admin alex" \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite2/main/proxmox/ct/iosuite.sh)"
```

The passwords go into the container in a file only root reads, removed once read, never as arguments.

## ioPix in a container of its own

Run the script a second time for a second container, mount the photos into that one, and tell its installer to run
only ioPix against the same database: `IOSUITE_INSTALL="--apps iopix --db db.lan"`. Take ioPix out of the first
container with `iosuite install --remove iopix`. See [Several copies and several servers](several-apps.md).

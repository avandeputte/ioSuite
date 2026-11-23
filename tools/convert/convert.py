#!/usr/bin/env python3
"""Move an install of the first ioSuite (avandeputte/iosuite: every app a program of its own, with its own folder,
config.env and service) to this one program.

    curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --fetch
    /opt/iosuite/.venv/bin/python /opt/iosuite/tools/convert/convert.py              # what it would do: changes nothing
    /opt/iosuite/.venv/bin/python /opt/iosuite/tools/convert/convert.py --apply      # do it

It reads the old install (each /opt/<app>/app/config.env, the service, the data folder) and:

  1. writes this program's one file for the machine (config.env): the Shared ioSuite database, the apps found, where
     it listens;
  2. gives the suite's one login the rights on each app's database (--db-admin: a MariaDB administrator; root on the
     database's own machine needs no password);
  3. stores what the old files said as settings in the Shared ioSuite database: each app's own address, its
     database's name, its own settings, the keys an old file still held;
  4. installs the packages the apps need, then stops the old services, copies each app's data folder (--data move |
     stay), and has `iosuite install` make the one service: the apps are away for the time the copy takes;
  5. checks that every app answers, then switches the old services off. When the new program does not come up,
     the old services are started again.

Nothing of the old install is deleted: its folders, its config.env files and its databases stay as they are, so
going back is stopping one service and starting the old ones (the last lines it prints say how).

    --from DIR            where the old apps are, each in DIR/<app>/app (default /opt, or ~/iosuite); repeatable
    --config APP=FILE     an old app that is not on this machine: its config.env, copied here (its data is not moved
                          and its service not stopped: do both yourself); repeatable
    --apps APP,APP        only these of the apps found
    --db-admin USER       a MariaDB administrator for the rights (password from DB_ADMIN_PASSWORD, else asked)
    --data copy|move|stay each app's data folder: copied into the program's (default), moved there, or left where it
                          is and named in Settings (a folder the old file named itself always stays)
    --device-address URL  an address of its own for phones and devices (https://sync.example.com) instead of each
                          app's old address; --mcp-address URL the same for MCP clients
    --port N, --sync-port N, --mcp-port N, --host ADDR, --user USER, --no-service     passed to `iosuite install`
    --wait SECONDS        how long the apps get to answer before the old services are started again (120)

Not part of the program: nothing imports it, and it is run once.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from iosuite_shared import catalog, config, install

PORTED_FROM = (3, 44, 0)  # the old suite's version this program was made from: its databases are as that version left them
LOCAL = ("127.0.0.1", "localhost", "::1")
# What an old app read from its file as a stand-in and this program keeps in the database only:
#   (the old name, where it goes, wins): where is ("key", name) for Keys and tokens, or ("own", table, name) for a row
#   of the app's own settings table; wins: the old file's value was used whatever the database held
CARRIED = {
    "iostart": [("HA_URL", ("own", "prt_settings", "ha_url"), True), ("HA_TOKEN", ("key", "ha_token"), True),
                ("ACCUWEATHER_API_KEY", ("key", "accuweather_key"), True),
                ("ACCUWEATHER_LOCATION", ("own", "prt_settings", "accuweather_location"), True)],
    "iopix": [("GOOGLE_MAPS_API_KEY", ("key", "google_maps_key"), False), ("GOOGLE_SERVER_KEY", ("key", "google_server_key"), False),
              ("DIGIKAM_DB_PASSWORD", ("own", "pix_settings", "db_password"), False)],
}
# What is no longer said per app, and why (shown once, for the names an old file has)
GONE = {
    "PORT": "the suite has three ports for every app",
    "LOG_FILE": "a copy has one log",
    "UPDATE_CHECK": "the suite is updated as one program",
    "ADMIN_USER": "the accounts are there", "ADMIN_PASSWORD": "the accounts are there",
    "DB_HOST": "the suite's one login", "DB_PORT": "the suite's one login", "DB_USER": "the suite's one login",
    "DB_PASSWORD": "the suite's one login", "DB_TYPE": "the suite's one login",
    "HF_HUB_OFFLINE": "ioPix sets it itself",
}
EXTRAS = {"iopix-ai": ("iopix", "fastembed"), "iorecipe-ai": ("iorecipe", "llama_cpp")}  # extra: (app, a package of it)


def say(msg: str) -> None:
    print(f"\n\033[1;34m==>\033[0m {msg}" if sys.stdout.isatty() else f"\n==> {msg}")


def die(msg: str):
    raise SystemExit(f"error: {msg}")


def _within(path: Path, root: Path) -> bool:
    """Whether a folder lies inside another (both as they are on disk)."""
    try:
        return path.resolve() == root.resolve() or root.resolve() in path.resolve().parents
    except OSError:
        return False


# ---- reading the old install
def old_app(key: str, folder: Path = None, file: Path = None, run=subprocess.run, unit_dir: Path = install.UNIT_DIR) -> dict:
    """One old app: its folder (None: only its config.env was brought here), what its file says, its service, its data."""
    file = Path(file or folder / "config.env")
    cfg = install.read_env(file)
    out = {"key": key, "folder": folder, "file": file, "cfg": cfg, "version": None, "unit": None, "active": False,
           "user": None, "data": None, "data_named": False, "extras": []}
    if folder is None:
        return out
    for init in (folder / "shared" / "iosuite_shared" / "__init__.py", folder.parent / "shared" / "iosuite_shared" / "__init__.py"):
        try:
            m = re.search(r'^__version__\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"), re.M)
        except OSError:
            continue
        if m:
            out["version"] = m.group(1)
            break
    unit = unit_dir / f"{key}.service"
    if unit.exists():
        out["unit"] = key
        m = re.search(r"^User=(\S+)", unit.read_text(encoding="utf-8", errors="replace"), re.M)
        out["user"] = m.group(1) if m else "root"
        if shutil.which("systemctl"):
            out["active"] = run(["systemctl", "is-active", "-q", key]).returncode == 0
    named = cfg.get("DATA_DIR")
    data = (folder / named).resolve() if named else folder / "data"
    # A data folder the old file named is kept where it is and named in Settings, but only when it lies outside the
    # old install (a disk of its own: the photos, the backups). One inside it (DATA_DIR=/opt/iopix/data, or ../data)
    # moves with everything else: the old folder is the old program's, and the one service may not even read it.
    out["data"] = data if data.is_dir() else None
    out["data_named"] = bool(named) and not _within(data, folder.parent if folder.name == "app" else folder)
    for extra, (app, package) in EXTRAS.items():
        if app == key and list(folder.glob(f".venv/lib/python*/site-packages/{package}")):
            out["extras"].append(extra)
    return out


def find(dirs, configs=(), only=None, **kw) -> list:
    """The old apps in these folders (DIR/<app>/app/config.env, or DIR/<app>/config.env in a checkout) and the ones
    whose file alone was brought here ("iocalendar=/tmp/iocalendar.env"), in the suite's order."""
    found = {}
    for d in dirs:
        for key in catalog.APPS:
            for folder in (Path(d) / key / "app", Path(d) / key):
                if key not in found and (folder / "config.env").is_file():
                    found[key] = old_app(key, folder.resolve(), **kw)
    for item in configs:
        key, _, file = item.partition("=")
        key = key.strip().lower()
        if key not in catalog.APPS:
            die(f"--config {item}: {key} is not an app of the suite")
        if not Path(file).is_file():
            die(f"--config {item}: no such file")
        found[key] = old_app(key, None, Path(file), **kw)
    return [found[k] for k in catalog.install_order() if k in found and (not only or k in only)]


def shared_of(c: dict) -> dict:
    """The Shared ioSuite database an old file names (by default on the server of the app's own database)."""
    return {"host": c.get("IOSUITE_DB_HOST") or c.get("DB_HOST") or "127.0.0.1", "port": str(c.get("IOSUITE_DB_PORT") or c.get("DB_PORT") or 3306),
            "name": c.get("IOSUITE_DB_NAME") or "iosuite", "user": c.get("IOSUITE_DB_USER") or "iosuite", "password": c.get("IOSUITE_DB_PASSWORD") or ""}


def own_of(key: str, c: dict) -> dict:
    return {"host": c.get("DB_HOST") or "127.0.0.1", "port": str(c.get("DB_PORT") or 3306), "name": c.get("DB_NAME") or key, "user": c.get("DB_USER") or key}


def _server(d: dict) -> tuple:
    h = d["host"].lower()
    return ("127.0.0.1" if h in LOCAL else h, str(d["port"]))


def _version(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


def _size(folder: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def human(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("bytes", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def _agree(olds: list, name: str, first: str = "iostart"):
    """A value every old file should say the same: the start page's, else the one most say; and who says otherwise."""
    said = {o["key"]: o["cfg"].get(name) for o in olds if o["cfg"].get(name)}
    if not said:
        return None, []
    values = list(said.values())
    best = said.get(first) or max(set(values), key=values.count)
    return best, [k for k, v in said.items() if v != best]


def _address(url: str) -> str:
    """An address as the old files wrote it, without a trailing slash; '' when it is not one."""
    url = (url or "").strip().rstrip("/")
    return url if re.match(r"^https?://[^\s/]+", url) else ""


def _has_folder(url: str) -> bool:
    return bool(urlsplit(url).path.strip("/"))


# ---- the plan
def plan(olds: list, base: Path, data: str = "copy", device_address: str = "", mcp_address: str = "", new_data: Path = None) -> dict:
    """What moving these old apps into the program at `base` does, without doing any of it:
        {apps, machine: {the machine's file}, settings: [(app or 'suite', name, value)], carried: [(app, where, value, wins, old name)],
         data: [(app, from, to, how, bytes)], units: [(unit, active)], databases: [names], user, extras, notes, problems,
         old: {app: {address, port}}}"""
    p = {"apps": [o["key"] for o in olds], "machine": {}, "settings": [], "carried": [], "data": [], "units": [], "databases": [],
         "user": None, "extras": [], "notes": [], "problems": [], "old": {}, "folders": [], "gone": {}}
    if not olds:
        p["problems"].append("no app of the first ioSuite was found (looked for <app>/app/config.env): name the folder with --from")
        return p
    names = {o["key"]: catalog.name_of(o["key"]) for o in olds}

    # the Shared ioSuite database: one for every app, and every app's own database on its server
    shared = [shared_of(o["cfg"]) for o in olds]
    first = next((s for o, s in zip(olds, shared) if o["key"] == "iostart"), shared[0])
    for o, s in zip(olds, shared):
        if (_server(s), s["name"], s["user"]) != (_server(first), first["name"], first["user"]):
            p["problems"].append(f"{names[o['key']]} is of another suite: its Shared ioSuite database is {s['host']}:{s['port']}/{s['name']}, "
                                 f"the others' {first['host']}:{first['port']}/{first['name']} (leave it out with --apps, and move it apart)")
        elif s["password"] != first["password"]:
            p["problems"].append(f"{o['file']}: IOSUITE_DB_PASSWORD is not the one the other apps have")
        own = own_of(o["key"], o["cfg"])
        if _server(own) != _server(first):
            p["problems"].append(f"{names[o['key']]}'s database {own['name']} is on {own['host']}:{own['port']}, the Shared ioSuite database on "
                                 f"{first['host']}:{first['port']}: the one program keeps every database on one server. Move it there first "
                                 f"(mysqldump {own['name']} | mysql on the other server), put the new server in {o['file']}, and run this again")
        p["databases"].append(own["name"])
        if own["name"] != o["key"]:
            p["settings"].append((o["key"], "DB_NAME", own["name"]))
    if not first["password"]:
        p["problems"].append("no old file says the password of the Shared ioSuite database (IOSUITE_DB_PASSWORD)")
    p["machine"] = {"IOSUITE_DB_HOST": first["host"], "IOSUITE_DB_PORT": first["port"], "IOSUITE_DB_NAME": first["name"],
                    "IOSUITE_DB_USER": first["user"], "IOSUITE_DB_PASSWORD": first["password"], "APPS": ",".join(p["apps"])}

    # where it listens: as the start page did, else as every app did
    host, others = _agree(olds, "HOST")
    if host and not (others and "iostart" not in p["apps"]):
        p["machine"]["HOST"] = host
    elif others:
        p["notes"].append("the old apps listened on different addresses (HOST): the program listens on every address; say otherwise with --host")
    for name in ("TLS_CERT_FILE", "TLS_KEY_FILE"):
        value, others = _agree(olds, name)
        if value:
            p["machine"][name] = value
            if others:
                p["notes"].append(f"{name}: the start page's is taken ({value}); {', '.join(names[k] for k in others)} had another")
    internal, _ = _agree(olds, "INTERNAL_URL")
    if internal:
        u = urlsplit(internal if "://" in internal else "http://" + internal)
        if u.hostname:
            p["machine"]["INTERNAL_URL"] = f"{u.scheme}://{u.hostname}"

    # the whole suite's settings
    suite_url = _address(next((o["cfg"].get("PUBLIC_URL") for o in olds if o["key"] == "iostart"), ""))
    if suite_url:
        p["settings"].append(("suite", "PUBLIC_URL", suite_url))
    for name in ("COOKIE_DOMAIN", "TZ"):
        value, others = _agree(olds, name)
        if value:
            p["settings"].append(("suite", name, value))
            if others:
                p["notes"].append(f"{name}: {value} for the whole suite; {', '.join(names[k] for k in others)} said otherwise, which is not kept")
    for name in ("KEEP_DELETED_DAYS", "MCP_USER"):  # the suite's, unless the apps differ: then each its own
        value, others = _agree(olds, name)
        if value and not others and len([o for o in olds if o["cfg"].get(name)]) > 1:
            p["settings"].append(("suite", name, value))
        elif value:
            p["settings"] += [(o["key"], name, o["cfg"][name]) for o in olds if o["cfg"].get(name)]

    # each app: its own address, its own settings, what its file still held, its data
    new_data = Path(new_data or base / "data")
    for o in olds:
        key, c, folder = o["key"], o["cfg"], catalog.FOLDERS.get(o["key"])
        url = _address(c.get("PUBLIC_URL"))
        p["old"][key] = {"address": url, "port": c.get("PORT") or "", "host": c.get("HOST") or "", "here": o["folder"] is not None}
        own_name = ""
        if key != "iostart" and suite_url and folder and url == f"{suite_url}/{folder}":
            p["folders"].append((folder, c.get("PORT") or "?"))
        elif key != "iostart" and url:
            if _has_folder(url):
                p["notes"].append(f"{names[key]}'s address {url} is a folder of a site that is not the suite's: not kept; "
                                  f"it answers in its folder at the suite's address")
            else:
                own_name = url
                p["settings"].append((key, "PUBLIC_URL", url))
        at = own_name or (suite_url if key == "iostart" else "")
        if at and not device_address and catalog.APPS[key].get("sync"):
            p["settings"].append(("suite" if key == "iostart" else key, "SYNC_URL", at))
        if at and not mcp_address:
            p["settings"].append(("suite" if key == "iostart" else key, "MCP_URL", at))
        declared = {d["name"]: d for d in catalog.APPS[key].get("settings") or []}
        for name, value in c.items():
            if name in declared:
                if value != "" and value != str(declared[name].get("default", "")):
                    p["settings"].append((key, name, _moved(value, o, new_data / key, data)))
            elif name == "MCP":
                p["notes"].append(f"{names[key]}: MCP={value} in the old file kept its MCP server {'on' if config.as_flag(value) else 'off'} whatever "
                                  f"Settings said; it now follows the switch under its Settings › Server › MCP server")
        for name, where, wins in CARRIED.get(key, []):
            if c.get(name):
                p["carried"].append((key, where, c[name], wins, name))
        size = _size(o["data"]) if o["data"] else 0
        if o["data"] and (size or o["data_named"]):
            if o["data_named"]:
                p["settings"].append((key, "DATA_DIR", str(o["data"])))
                p["data"].append((key, o["data"], o["data"], "named", size))
                p["notes"].append(f"{names[key]}'s data folder {o['data']} is outside the old install, so it stays where it is and "
                                  f"Settings names it: the one service's account has to be able to read and write it "
                                  f"(chown -R <the account> {o['data']})")
            elif data == "stay":
                p["settings"].append((key, "DATA_DIR", str(o["data"])))
                p["data"].append((key, o["data"], o["data"], "stay", size))
            else:
                p["data"].append((key, o["data"], new_data / key, data, size))
        if o["unit"]:
            p["units"].append((o["unit"], o["active"]))
        p["extras"] += o["extras"]
        if o["folder"] is None:
            p["notes"].append(f"{names[key]} is not on this machine: stop it where it runs before this, and bring its data folder to "
                              f"{new_data / key} yourself if it keeps one")
        elif o["version"] and _version(o["version"]) < PORTED_FROM:
            p["problems"].append(f"{names[key]} is at {o['version']}: update the old suite to {'.'.join(map(str, PORTED_FROM))} or newer first "
                                 f"(its Settings › Server › Update), so that its database is as this program expects it")
    newer = sorted({o["version"] for o in olds if o["folder"] is not None and o["version"] and _version(o["version"]) > PORTED_FROM})
    if newer:
        p["notes"].append(f"the old suite is at {', '.join(newer)}, newer than the version this program was made from "
                          f"({'.'.join(map(str, PORTED_FROM))}): what it gained since is not in this program")
    if device_address:
        p["settings"].append(("suite", "SYNC_URL", device_address))
    if mcp_address:
        p["settings"].append(("suite", "MCP_URL", mcp_address))

    # the account the one service runs as: the files the old apps wrote are that account's
    users = {o["key"]: o["user"] for o in olds if o["user"]}
    if users:
        p["user"] = users.get("iopix") or max(set(users.values()), key=list(users.values()).count)
        if len(set(users.values())) > 1:
            p["notes"].append("the old services ran as different accounts (" + ", ".join(f"{names[k]}: {u}" for k, u in users.items())
                              + f"): the one service runs as {p['user']} (--user for another), which must be able to write "
                              "what the apps write outside their data folders (the photos, the backups)")
    gone = {}
    for o in olds:
        for name in o["cfg"]:
            why = GONE.get(name) or ("the suite is updated as one program" if re.fullmatch(r"IO[A-Z]+_(REPO|BRANCH)", name) else None)
            if why:
                gone.setdefault(why, set()).add(name)
    p["gone"] = {why: sorted(ns) for why, ns in gone.items()}
    p["extras"] = sorted(set(p["extras"]))
    return p


def _moved(value: str, o: dict, new_home: Path, how: str) -> str:
    """A setting that names a folder inside the app's old data folder names the same one in its new data folder, when
    the data goes there."""
    if how in ("copy", "move") and o["data"] and not o["data_named"] and value.startswith("/"):
        try:
            return str(new_home / Path(value).resolve().relative_to(o["data"].resolve()))
        except ValueError:
            pass
    return value


def check_settings(p: dict) -> None:
    """Hold every setting to what the program takes (iosuite_shared.admin.clean_setting): one it would refuse becomes a
    note, and is not stored."""
    from iosuite_shared import admin
    from iosuite_shared.errors import Invalid
    kept = []
    for app, name, value in p["settings"]:
        d = config.known("" if app == "suite" else app, name) if app != "suite" else next((x for x in config.declared("") if x["name"] == name), None)
        try:
            if not d:
                raise Invalid("the program has no such setting")
            kept.append((app, name, admin.clean_setting("" if app == "suite" else app, d, value)))
        except Invalid as e:
            p["notes"].append(f"{app}.{name}={value} is not kept: {e}")
    p["settings"] = kept


# ---- saying it
def routes(p: dict) -> list:
    """What a reverse proxy or a tunnel in front of the old apps has to send where now, one entry for each address:
    [{address, was: the old port, devices: [paths for the device port], mcp: [paths for the MCP port]}]. Everything
    else at the address goes to the port of the pages."""
    stored = {(a, n): v for a, n, v in p["settings"]}
    suite_url, out = stored.get(("suite", "PUBLIC_URL")), {}

    def at(address: str, was: str = "") -> dict:
        return out.setdefault(address, {"address": address, "was": was, "devices": [], "mcp": []})
    for key in p["apps"]:
        own = stored.get((key, "PUBLIC_URL")) or (suite_url if key == "iostart" else None)
        if not own:
            continue
        r = at(own, p["old"][key]["port"])
        who = "suite" if key == "iostart" else key
        if stored.get((who, "SYNC_URL")) == own:
            r["devices"] += catalog.APPS[key].get("sync") or []
        if stored.get((who, "MCP_URL")) == own:
            r["mcp"].append("/mcp")
    for key in p["apps"]:  # an app without a name of its own is in its folder at the suite's address: its paths too
        folder = catalog.FOLDERS.get(key)
        if not suite_url or not folder or stored.get((key, "PUBLIC_URL")):
            continue
        if stored.get(("suite", "SYNC_URL")) == suite_url:
            at(suite_url)["devices"] += [f"/{folder}{x}" for x in catalog.APPS[key].get("sync") or []]
        if stored.get(("suite", "MCP_URL")) == suite_url:
            at(suite_url)["mcp"].append(f"/{folder}/mcp")
    return list(out.values())


def show(p: dict, olds: list, base: Path, log=print, ports=(80, 8443, 8444), service: bool = True) -> None:
    names = {k: catalog.name_of(k) for k in p["apps"]}
    say(f"The first ioSuite on this machine: {len(olds)} app(s)")
    for o in olds:
        own = own_of(o["key"], o["cfg"])
        where = o["folder"] or f"elsewhere ({o['file']})"
        unit = f"service {o['unit']} ({'running' if o['active'] else 'stopped'})" if o["unit"] else "no service"
        old = p["old"][o["key"]]
        log(f"  {names[o['key']]:<11} {where}   {unit}   database {own['name']}   port {old['port'] or '?'}"
            + (f"   {old['address']}" if old["address"] else ""))
    say(f"What moving it into {base} does")
    m = p["machine"]
    log(f"  1. The machine's file {base / 'config.env'}: the Shared ioSuite database {m.get('IOSUITE_DB_HOST')}:{m.get('IOSUITE_DB_PORT')}/"
        f"{m.get('IOSUITE_DB_NAME')} (login {m.get('IOSUITE_DB_USER')}), {len(p['apps'])} app(s)"
        + "".join(f", {k}={m[k]}" for k in ("HOST", "INTERNAL_URL", "TLS_CERT_FILE") if m.get(k)))
    log(f"  2. The login {m.get('IOSUITE_DB_USER')} gets the rights on the database(s) {', '.join(p['databases'])}")
    log("  3. Settings stored in the Shared ioSuite database:")
    for app in ["suite", *p["apps"]]:
        mine = [f"{n}={v}" for a, n, v in p["settings"] if a == app]
        if mine:
            log(f"       {'the suite' if app == 'suite' else names[app]}: " + ", ".join(mine))
    for app, where, _value, wins, name in p["carried"]:
        to = f"Keys and tokens ({where[1]})" if where[0] == "key" else f"its own settings ({where[2]})"
        log(f"       {names[app]}: {name} of the old file goes to {to}" + ("" if wins else ", unless one is stored there already"))
    for why, ns in p.get("gone", {}).items():
        log(f"       no longer said per app ({why}): {', '.join(ns)}")
    log("  4. Data folders:" + ("" if p["data"] else " none"))
    for app, src, dst, how, size in p["data"]:
        what = {"copy": f"copied to {dst}", "move": f"moved to {dst}", "stay": "stays there, named in Settings",
                "named": "stays there (the old file named it), named in Settings"}[how]
        log(f"       {names[app]}: {src} ({human(size)}) {what}")
    units = [u for u, _ in p["units"]]
    more = f"; Python packages: {', '.join(p['extras'])} too" if p["extras"] else ""
    if service:
        log(f"  5. The old service(s) are stopped and switched off: {', '.join(units) or 'none here'}; the service iosuite is made and started"
            + (f" as {p['user']}" if p["user"] else "") + more)
        log("  6. Every app is asked whether it answers. When one does not, the old services are started again.")
    else:
        log(f"  5. The program's packages are installed{more}. No service is made or stopped by this run (that takes root on a machine with")
        log("     systemd): stop the old apps before it, and start the program yourself afterwards.")
    log("  Nothing of the old install is deleted.")
    if p["notes"]:
        say("To know")
        for n in p["notes"]:
            log(f"  - {n}")
    afterwards(p, log, ports)
    if p["problems"]:
        say("In the way")
        for n in p["problems"]:
            log(f"  - {n}")


def afterwards(p: dict, log=print, ports=(80, 8443, 8444)) -> None:
    """What the person changes outside the suite once it has moved."""
    names = {k: catalog.name_of(k) for k in p["apps"]}
    stored = {(a, n): v for a, n, v in p["settings"]}
    say("What you change afterwards")
    table = routes(p)
    if table:
        log("  In the reverse proxy or the tunnel in front of the suite (the guide: Reverse proxy and HTTPS, Cloudflare Tunnel")
        log("  and Access), every address now goes to this machine's three ports:")
        for r in table:
            log(f"    {r['address']}")
            if r["devices"]:
                log(f"        {'  '.join(r['devices'])}   to port {ports[1]}")
            if r["mcp"]:
                shown = r["mcp"] if len(r["mcp"]) < 4 else ["/mcp" if "/mcp" in r["mcp"] else r["mcp"][0], "every app's /<folder>/mcp"]
                log(f"        {'  '.join(shown)}   to port {ports[2]}")
            log(f"        everything else   to port {ports[0]}" + (f"   (it went to port {r['was']})" if r["was"] else ""))
        log("  The rules for paths go above the rule for everything else. With them, phones, devices and MCP clients keep the")
        log("  addresses they have. Until they are there, the pages work and phones do not sync from outside your network.")
    if p["folders"]:
        log("  The rules that sent a folder to an app's own port go: " + ", ".join(f"/{f} (port {port})" for f, port in p["folders"])
            + f". Every folder is at port {ports[0]} now.")
    plain = [k for k in p["apps"] if not stored.get((k, "PUBLIC_URL"))]
    if plain:
        log(f"  By the server's own address, the apps were at a port each and are in a folder each now, on port {ports[0]}:")
        root = "http://SERVER" + ("" if ports[0] == 80 else f":{ports[0]}")
        for k in plain:
            folder = catalog.FOLDERS.get(k)
            log(f"    {names[k]:<11} http://SERVER:{p['old'][k]['port'] or '?'}/   is now   {root}/{folder + '/' if folder else ''}"
                + (f"   and for devices   http://SERVER:{ports[1]}/{folder + '/' if folder else ''}" if catalog.APPS[k].get("sync") else ""))
    for name, what, port in (("SYNC_URL", "Phones, native apps and devices", ports[1]), ("MCP_URL", "MCP clients", ports[2])):
        if stored.get(("suite", name)) and stored.get(("suite", name)) != stored.get(("suite", "PUBLIC_URL")):
            log(f"  {what} get a new address, {stored[('suite', name)]} (to port {port} of this machine): each one is set up "
                f"again with it, the app's folder after it ({stored[('suite', name)]}/calendar/dav/).")
    if "iocontact" in p["apps"]:
        log("  ioContact's LDAP directory stays on its port.")


# ---- doing it
def can_use(t: dict, names: list) -> list:
    """The databases among these the suite's login cannot open."""
    import pymysql
    out = []
    for name in names:
        try:
            pymysql.connect(host=t["host"], port=int(t["port"]), user=t["user"], password=t["password"], database=name, connect_timeout=10).close()
        except Exception:  # noqa: BLE001
            out.append(name)
    return out


FROM_FILES = ("COOKIE_DOMAIN", "TZ", "KEEP_DELETED_DAYS", "MCP_USER")  # the suite's settings read from whichever old files a machine has


def suite_says(name: str) -> str:
    """What the suite has stored under this name already."""
    from iosuite_shared import db
    return db.get_setting(name, "", "") or ""


def carry(p: dict, log=print) -> None:
    """What the old files still held, into Keys and tokens and the apps' own settings tables."""
    import pymysql
    from iosuite_shared import credentials, db
    for app, where, value, wins, name in p["carried"]:
        if where[0] == "key":
            if wins or not credentials.get(app, where[1]):
                credentials.put(app, where[1], value, by="convert")
                log(f"  {app}: {name} is in Keys and tokens ({where[1]})")
            continue
        database = db.get_setting("DB_NAME", None, app) or app
        try:
            con = pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=config.DB_PASSWORD, database=database,
                                  connect_timeout=10, autocommit=True)
            with con.cursor() as cur:
                cur.execute(f"SELECT value FROM `{where[1]}` WHERE name = %s", (where[2],))
                row = cur.fetchone()
                if wins or not (row and row[0]):
                    cur.execute(f"INSERT INTO `{where[1]}` (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (where[2], value))
                    log(f"  {app}: {name} is in its own settings ({where[2]})")
            con.close()
        except Exception as e:  # noqa: BLE001
            log(f"  note: {app}: {name} could not be stored ({str(e)[:120]}): enter it in the app's Settings")


def _give_to(path: Path, user: str, log=print) -> None:
    """The one service's account owns what it is to write: the files the old apps wrote are their own accounts', and
    with several of those (iopix as iopix, the rest as root) the one service could not read half of them."""
    if not user or not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    try:
        for q in [path, *path.rglob("*")]:
            shutil.chown(q, user=user)
    except (OSError, LookupError, KeyError) as e:  # noqa: BLE001
        log(f"  note: {path} could not be given to {user} ({str(e)[:120]}): chown -R {user} {path}")


def move_data(p: dict, log=print) -> list:
    """Copy or move the data folders; the (from, to) pairs moved, for going back."""
    moved = []
    for app, src, dst, how, _size_ in p["data"]:
        if how not in ("copy", "move"):
            continue
        dst = Path(dst)
        if dst.exists() and any(dst.iterdir()):
            log(f"  {app}: {dst} holds something already: left as it is ({src} is not {'copied' if how == 'copy' else 'moved'})")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if how == "move":
            if dst.exists():
                dst.rmdir()
            shutil.move(str(src), str(dst))
            moved.append((src, dst))
        else:
            shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.log", "*.log.[0-9]*"))
        _give_to(dst, p.get("user") or "", log)
        log(f"  {app}: {src} {'moved' if how == 'move' else 'copied'} to {dst}")
    return moved


def answers(p: dict, port: int, host: str = "", wait: int = 120, log=print) -> list:
    """Ask every app's status at the program's own address; the apps that do not answer within `wait` seconds."""
    at = next((h for h in (host or "").split(",") if h and h not in ("0.0.0.0", "::")), "127.0.0.1").strip("[]")
    root = f"http://{'[' + at + ']' if ':' in at else at}{'' if port == 80 else ':' + str(port)}"

    def ok(path: str) -> bool:
        try:
            with urllib.request.urlopen(root + path, timeout=5) as r:
                return r.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False
    until = time.time() + wait
    left = list(p["apps"])
    while time.time() < until:
        if ok("/-/status"):
            left = [k for k in left if not ok(f"/{catalog.FOLDERS[k]}/api/status" if catalog.FOLDERS.get(k) else "/api/status")]
            if not left:
                return []
        time.sleep(2)
    return left


def listening(p: dict, port_open=install.listening) -> list:
    """The old apps of this machine whose port still answers: they are running."""
    out = []
    for key in p["apps"]:
        old = p["old"][key]
        at = next((h for h in (old["host"] or "").split(",") if h and h not in ("0.0.0.0", "::")), "127.0.0.1").strip("[]")
        if old["here"] and old["port"] and port_open(at, old["port"]):
            out.append(key)
    return out


def taken(p: dict, ports: tuple, host: str = "", port_open=install.listening) -> list:
    """The program's ports that something else than an old app of this machine holds (a reverse proxy on port 80, say):
    an old app's port is free once the app is stopped."""
    at = next((h for h in (host or "").split(",") if h and h not in ("0.0.0.0", "::")), "127.0.0.1").strip("[]")
    old = {str(p["old"][k]["port"]) for k in p["apps"] if p["old"][k]["here"]}
    return [n for n in ports if n and str(n) not in old and port_open(at, n)]


def apply(p: dict, a, base: Path, run=subprocess.run, log=print, systemd: bool = None, ask=getpass.getpass, check=answers, port_open=install.listening) -> int:
    from iosuite_shared import admin, db, provision, users
    if systemd is None:
        systemd = os.geteuid() == 0 and shutil.which("systemctl") is not None and Path("/run/systemd/system").exists()
    service = systemd and not a.no_service
    if not service:
        running = listening(p, port_open)
        if running:
            die(f"{', '.join(catalog.name_of(k) for k in running)} of the old install still run(s), and this run cannot stop services "
                f"(root on a machine with systemd can): stop the old apps first")
    file = base / "config.env"
    was = install.read_env(file)
    if was.get("IOSUITE_DB_PASSWORD") and (was.get("IOSUITE_DB_HOST"), was.get("IOSUITE_DB_NAME")) != (p["machine"]["IOSUITE_DB_HOST"], p["machine"]["IOSUITE_DB_NAME"]):
        die(f"{file} is of another suite already (its Shared ioSuite database is {was.get('IOSUITE_DB_HOST')}/{was.get('IOSUITE_DB_NAME')})")

    say("The machine's file")
    apps = [k for k in catalog.install_order() if k in set(p["apps"]) | set(install.apps_of(was) if was.get("APPS") else [])]
    changes = {**p["machine"], "APPS": ",".join(apps)}
    for name, value in (("HOST", a.host), ("PORT", a.port), ("SYNC_PORT", a.sync_port), ("MCP_PORT", a.mcp_port)):
        if value is not None:
            changes[name] = value
    install.write_env(file, changes, install.HEADER)
    for k, v in changes.items():
        os.environ[k] = str(v)
    config.load_file(file)
    log(f"  {file}")

    say("The databases")
    t = provision.target()
    locked = can_use(t, p["databases"])
    admin_user = a.db_admin or ("root" if locked and install.is_local(t["host"]) and os.geteuid() == 0 else None)
    if admin_user:
        password = os.environ.get("DB_ADMIN_PASSWORD") or ""
        if not password and not (install.is_local(t["host"]) and admin_user == "root" and os.geteuid() == 0):
            password = ask(f"MariaDB password for {admin_user}: ")
        provision.run(admin_user, password, p["databases"], t, connect=install.admin_connect(admin_user, password), log=log,
                      client=a.client_host, check=lambda t: None)
        locked = can_use(t, p["databases"])
    if locked:
        die(f"the login {t['user']} cannot open the database(s) {', '.join(locked)}: run this again with --db-admin USER (a MariaDB "
            f"administrator), or give it the rights yourself: GRANT ALL PRIVILEGES ON `NAME`.* TO '{t['user']}'@'HOST'")
    if not users.init():
        die(f"the Shared ioSuite database cannot be reached ({config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}): {db.error}")
    log(f"  the login {t['user']} opens {', '.join(p['databases'])}")

    say("Settings")
    for app, name, value in p["settings"]:
        # a machine without the start page, moved after the one that has it: what the suite says already stays
        there = suite_says(name) if app == "suite" and "iostart" not in p["apps"] and name in FROM_FILES else ""
        if there:
            log(f"  suite.{name} stays {there}" + ("" if there == value else f" (the apps of this machine said {value})"))
            continue
        admin.set_setting(admin.SUITE if app == "suite" else app, name, value)
        log(f"  {app}.{name} = {value}")
    carry(p, log)

    # what takes minutes is done while the old apps still run: `iosuite install` below then finds the packages there
    say("Packages")
    extras = install.extras_for(apps, p["extras"])
    if extras != ((base / "EXTRAS").read_text().strip() if (base / "EXTRAS").exists() else None):
        install.pip_install(base, extras, run, log)
    else:
        log(f"  Python packages: {extras} (there already)")
    install.apt_install(install.missing_system(apps, run), run, log)

    stopped = [u for u, active in p["units"] if active] if service else []
    moved = []

    def back(why: str):
        if service:
            run(["systemctl", "disable", "-q", "--now", install.unit_name()])
        for src, dst in moved:
            if not Path(src).exists():
                shutil.move(str(dst), str(src))
        for u in stopped:
            run(["systemctl", "start", u])
        die(f"{why}\n  The old service(s) run again ({', '.join(stopped) or 'none were running'}); nothing of the old install was changed. "
            f"What was set up so far stays in {base} and the Shared ioSuite database, and running this again goes on from it.")

    if stopped:
        say("Stopping the old services")
        for u in stopped:
            run(["systemctl", "stop", u])
            log(f"  {u}")
    running = listening(p, port_open)
    if running:
        back(f"{', '.join(catalog.name_of(k) for k in running)} of the old install still run(s) without a service of this machine: stop them, and run this again.")
    try:
        say("Data")
        moved = move_data(p, log)
        say("The program: its tables, its service")
        cmd = [sys.executable, "-m", "iosuite_shared.cli", "install", "--apps", ",".join(apps), "--yes", "--service" if service else "--no-service"]
        extras = ",".join(p["extras"])
        cmd += ["--extras", extras] if extras else []
        user = a.user or p["user"]
        cmd += ["--user", user] if user and service else []
        done = run(cmd, env={**os.environ, "IOSUITE_CONFIG": str(file)}, cwd=str(base))  # in the folder: its own code, whatever folder this was started in
    except (OSError, shutil.Error) as e:
        back(f"it stopped: {e}")
    if done.returncode:
        back("`iosuite install` did not finish (its own lines above say why).")
    if not service:
        say("Done, but for starting it")
        log(f"  Start it with {base}/.venv/bin/iosuite serve (this run makes no service), then switch the old apps' services off.")
        afterwards(p, log, (config.PORT, config.SYNC_PORT, config.MCP_PORT))
        return 0
    say("Does every app answer?")
    silent = check(p, config.PORT, config.HOST, wait=int(getattr(a, "wait", None) or 120), log=log)
    if silent:
        back(f"{', '.join(catalog.name_of(k) for k in silent)} did not answer within two minutes (journalctl -u {install.unit_name()} -n 80 says why).")
    log(f"  yes: {', '.join(catalog.name_of(k) for k in p['apps'])}")
    for u, _active in p["units"]:
        run(["systemctl", "disable", "-q", u])
    say("Moved")
    log(f"  ioSuite runs as one program in {base} (service {install.unit_name()}); the old services are stopped and switched off.")
    afterwards(p, log, (config.PORT, config.SYNC_PORT, config.MCP_PORT))
    units = " ".join(u for u, _ in p["units"])
    say("Going back, and cleaning up")
    log(f"  Back to the old install: systemctl disable --now {install.unit_name()} && systemctl enable --now {units}")
    if moved:
        log("  (and move the data folders back first: " + "; ".join(f"mv {dst} {src}" for src, dst in moved) + ")")
    stayed = [str(src) for _app, src, _dst, how, _n in p["data"] if how in ("stay", "named")]
    log("  Once you are content, the old folders and services can go: each old app's folder and its /etc/systemd/system/<app>.service"
        + (f" (not a data folder that stayed where it was: {', '.join(stayed)})" if stayed else "") + ".")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n\n".join(__doc__.split("\n\n")[1:]))
    ap.add_argument("--from", dest="dirs", action="append", default=[], metavar="DIR")
    ap.add_argument("--config", dest="configs", action="append", default=[], metavar="APP=FILE")
    ap.add_argument("--apps", default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db-admin", default=None)
    ap.add_argument("--client-host", default=None)
    ap.add_argument("--data", choices=("copy", "move", "stay"), default="copy")
    ap.add_argument("--device-address", default="")
    ap.add_argument("--mcp-address", default="")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", default=None)
    ap.add_argument("--sync-port", default=None)
    ap.add_argument("--mcp-port", default=None)
    ap.add_argument("--user", default=None)
    ap.add_argument("--no-service", action="store_true")
    ap.add_argument("--wait", default=None, metavar="SECONDS")
    a = ap.parse_args(argv)
    base = Path(config.BASE)
    dirs = a.dirs or [d for d in ("/opt", str(Path.home() / "iosuite")) if Path(d).is_dir()]
    only = install.parse_apps(a.apps) if a.apps else None
    olds = find(dirs, a.configs, only)
    p = plan(olds, base, a.data, a.device_address.rstrip("/"), a.mcp_address.rstrip("/"),
             new_data=install.read_env(base / "config.env").get("DATA_DIR") or None)
    check_settings(p)
    ports = tuple(install.port_of(v, d) for v, d in ((a.port, 80 if os.geteuid() == 0 else 8080), (a.sync_port, 8443), (a.mcp_port, 8444)))
    systemd = os.geteuid() == 0 and shutil.which("systemctl") is not None and Path("/run/systemd/system").exists()
    if p["apps"] and not install.read_env(base / "config.env").get("IOSUITE_DB_PASSWORD"):  # (set up already: the program holds them itself)
        flags = dict(zip(ports, ("--port", "--sync-port", "--mcp-port")))
        for n in taken(p, ports, a.host or p["machine"].get("HOST") or ""):
            p["problems"].append(f"port {n} is in use on this machine by something that is not an old app (a reverse proxy?): "
                                 f"give the program another with {flags[n]} N, and send the proxy there")
    show(p, olds, base, ports=ports, service=systemd and not a.no_service)
    if p["problems"]:
        return 1
    if not a.apply:
        say("Nothing was changed. Run it again with --apply to move the suite.")
        return 0
    return apply(p, a, base)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""A rehearsal of the move: an install of the first ioSuite is made from its code, filled with its demo data, moved
with convert.py, and what every app lists is compared before and after.

    IOSUITE_TEST_DB=127.0.0.1:3306:root:PASSWORD python tools/convert/rehearse.py --old /path/to/a/checkout/of/avandeputte/iosuite

IOSUITE_TEST_DB names a MariaDB administrator (as the tests do: host:port:user:password; root on this machine may
leave the password empty). Everything is made in a scratch folder (--work DIR to keep it) and in databases and
logins named rh_…, dropped afterwards (--keep leaves them). The Python that runs this must hold the packages of
every app (pip install -e ".[all]"): the old apps run on them too.

What it does:
  1. lays the old install out as its installer did (<work>/old/<app>/app with config.env, shared/, data/), each app
     with a database and a login of its own, and starts every old app once: its tables, its demo data;
  2. asks every old app for its lists, as one of the demo family;
  3. copies this program beside it (<work>/new) and runs convert.py --apply there;
  4. starts the one program, asks the same lists in the apps' folders and holds them to the old ones, and looks for
     the settings and the keys the old files held;
  5. starts an old app again: going back still works.

With --service, as root on a scratch machine with systemd (never one that runs ioSuite: it makes and removes the
services <app> and iosuite), the move is made the way a server makes it: the old apps run as services, the program
is laid out as install.sh --fetch lays it out (an environment of its own, the packages installed by the move), a
first move is made to fail (an address the machine does not have) and must leave the old services running and the
data where it was, the second stops the old services, makes the service iosuite and switches the old ones off, and
going back is the two commands the converter prints.

Not part of the program: nothing imports it. The checks on GitHub run it both ways (.github/workflows/tests.yml).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]  # this program's folder
LOGIN = ("morgan", "calloway")              # one of the demo family
PORTS = (18080, 18443, 18444)               # the one program's, for the rehearsal
ASK = {  # what each app is asked for: lists the demo data fills
    "iostart": ["/api/bookmarks/tree"], "ionote": ["/api/notes", "/api/folders", "/api/tags"],
    "iocalendar": ["/api/calendars", "/api/members", "/api/occurrences?start=2026-01-01&end=2026-12-31"],
    "iotask": ["/api/lists", "/api/tasks"], "iorecipe": ["/api/recipes", "/api/books"],
    "iothings": ["/api/items", "/api/locations", "/api/labels"], "iomoney": ["/api/accounts", "/api/categories", "/api/payees"],
    "iodocs": ["/api/documents"], "iocontact": ["/api/contacts", "/api/books"], "iohealth": ["/api/workouts", "/api/types"],
    "iodns": ["/api/entries"], "iobackup": ["/api/overview"], "iopix": ["/api/folders", "/api/people/list"],
}
# what the old files say beyond the usual, to see it arrive: settings, an address of its own, keys
OWN = {
    "iostart": ["PUBLIC_URL=https://home.example.test", "ACCUWEATHER_API_KEY=old-weather-key", "HA_URL=http://ha.example.test:8123", "HA_FEED=0"],
    "iocalendar": ["PUBLIC_URL=https://calendar.example.test", "HOLIDAYS_COUNTRY=BE", "KEEP_DELETED_DAYS=45"],
    "iotask": ["PUBLIC_URL=https://home.example.test/tasks"],
    "ionote": ["MAX_IMAGE_MB=12"],
    "iobackup": ["BACKGROUND=0"], "iodns": ["BACKGROUND=0"],
    "iopix": ["DB_TYPE=mysql", "DIGIKAM_DB_TYPE=none", "DIGIKAM_CHECK=none", "GOOGLE_MAPS_API_KEY=old-maps-key", "AUTO_MODELS=0", "PREWARM=0"],
}
UNIT = """[Unit]
Description={name} (a rehearsal of the move)
After=network-online.target

[Service]
Type=simple
User=root
EnvironmentFile={folder}/config.env
Environment=PYTHONPATH={folder}/shared
WorkingDirectory={folder}
ExecStart={python} -m app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
UNITS = Path("/etc/systemd/system")
NOWHERE = "203.0.113.9"  # an address no machine has (TEST-NET-3): a program told to listen there does not come up
bad: list = []


def check(what: str, ok: bool, more: str = "") -> None:
    print(f"{'ok  ' if ok else 'NOT '} {what}{'' if ok or not more else ': ' + more}", flush=True)
    if not ok:
        bad.append(what)


def ask(url: str, cookie: str = None, data: dict = None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), r.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as e:
        return e.code, e.read(), []
    except Exception as e:  # noqa: BLE001
        return 0, str(e).encode(), []


def sign_in(root: str):
    code, _body, cookies = ask(root + "/api/auth/login", data={"name": LOGIN[0], "password": LOGIN[1]})
    return "; ".join(c.split(";")[0] for c in cookies) if code == 200 else None


def gist(v, out=None) -> dict:
    """What a list says, whatever addresses and times it carries: every name and title in it, and how many things."""
    out = out if out is not None else {"names": [], "n": 0}
    if isinstance(v, dict):
        for k, x in v.items():
            if k in ("name", "title", "summary", "label") and isinstance(x, str):
                out["names"].append(x)
            gist(x, out)
    elif isinstance(v, list):
        out["n"] += len(v)
        for x in v:
            gist(x, out)
    return out


def take(root: str, cookie: str, paths: list) -> dict:
    got = {}
    for p in paths:
        code, body, _ = ask(root + p, cookie)
        try:
            g = gist(json.loads(body))
            got[p] = [code, g["n"], sorted(g["names"])]
        except ValueError:
            got[p] = [code, -1, [body[:80].decode("utf-8", "replace")]]
    return got


def wait(url: str, seconds: int = 90, proc=None) -> bool:
    until = time.time() + seconds
    while time.time() < until:
        if ask(url)[0] == 200:
            return True
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(1)
    return False


def stop(proc) -> None:
    proc.terminate()
    try:
        proc.wait(30)
    except subprocess.TimeoutExpired:
        proc.kill()


def systemctl(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", *args], capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--old", required=True, help="a checkout of the first repository (avandeputte/iosuite)")
    ap.add_argument("--work", default=None, help="the scratch folder (kept); by default a temporary one, removed")
    ap.add_argument("--apps", default="", help="only these apps (default: every app)")
    ap.add_argument("--keep", action="store_true", help="leave the rh_ databases and logins")
    ap.add_argument("--service", action="store_true", help="as root on a scratch machine with systemd: the old apps as services, a move that fails, the move, going back")
    ap.add_argument("--environment", action="store_true", help="the program in a Python environment of its own, as install.sh --fetch makes it (with --service always)")
    a = ap.parse_args()
    sys.path.insert(0, str(HERE))
    from iosuite_shared import catalog, install
    src = Path(a.old).resolve()
    apps = [k for k in catalog.install_order() if (not a.apps or k in a.apps.split(",")) and (src / k / "config.env.example").is_file()]
    if not apps or not (src / "shared" / "iosuite_shared").is_dir():
        raise SystemExit(f"{src} is not a checkout of the first ioSuite (no <app>/config.env.example, or no shared/)")
    svc, own = a.service, a.service or a.environment
    if svc and (os.geteuid() != 0 or not shutil.which("systemctl") or not Path("/run/systemd/system").exists()):
        raise SystemExit("--service takes root on a machine with systemd")
    there = [n for n in ("iosuite", *apps) if (UNITS / f"{n}.service").exists()]
    if svc and there:
        raise SystemExit(f"this machine has the service(s) {', '.join(there)}: --service is for a scratch machine, it makes and removes them")
    host, port, user, password = (os.environ.get("IOSUITE_TEST_DB") or "127.0.0.1:3306:root:").split(":", 3)
    admin = install.admin_connect(user, password)(host, port)
    work = Path(a.work or tempfile.mkdtemp(prefix="iosuite-rehearse-")).resolve()
    old, new = work / "old", work / "new"
    for d in (old, new):
        shutil.rmtree(d, ignore_errors=True)
    names = ["rh_iosuite"] + [f"rh_{k}" for k in apps]

    def sql(statement: str, args=None):
        with admin.cursor() as cur:
            cur.execute(statement, args)
            return cur.fetchall()

    def drop():
        for n in names:
            sql(f"DROP DATABASE IF EXISTS `{n}`")
            for h in ("%", "localhost", "127.0.0.1"):
                sql(f"DROP USER IF EXISTS `{'rh_suite' if n == 'rh_iosuite' else n}`@%s", (h,))
    drop()
    procs = []
    try:
        # ---- 1. the old install
        print(f"== the first ioSuite, from {src}, in {old}: {len(apps)} app(s)", flush=True)
        for n in names:
            login = "rh_suite" if n == "rh_iosuite" else n
            sql(f"CREATE DATABASE `{n}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            sql(f"CREATE USER `{login}`@%s IDENTIFIED BY %s", ("%", f"pw-{login}"))
            sql(f"GRANT ALL PRIVILEGES ON `{n}`.* TO `{login}`@%s", ("%",))
        photos = work / "photos"
        photos.mkdir(parents=True, exist_ok=True)
        ports = {}
        for k in apps:
            folder = old / k / "app"
            top = str(src / k)  # the code only: not a config.env or a data folder the checkout was run with
            shutil.copytree(src / k, folder, ignore=lambda d, found: [n for n in found if n in ("__pycache__", ".venv") or n.endswith(".egg-info")
                                                                      or (d == top and n in ("config.env", "data"))])
            shutil.copytree(src / "shared", folder / "shared", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            ports[k] = re.search(r"^PORT=(\d+)", (src / k / "config.env.example").read_text(), re.M).group(1)
            lines = [f"DB_HOST={host}", f"DB_PORT={port}", f"DB_NAME=rh_{k}", f"DB_USER=rh_{k}", f"DB_PASSWORD=pw-rh_{k}",
                     "IOSUITE_DB_NAME=rh_iosuite", "IOSUITE_DB_USER=rh_suite", "IOSUITE_DB_PASSWORD=pw-rh_suite",
                     "HOST=127.0.0.1", f"PORT={ports[k]}", "COOKIE_DOMAIN=example.test", "TZ=Europe/Brussels", "UPDATE_CHECK=0", "LOG_FILE=",
                     *OWN.get(k, [])]
            if k == "iopix":
                lines.append(f"PHOTOS_ROOT={photos}")
            if k == "iobackup":
                lines.append(f"BACKUP_DIR={work / 'backups'}")
            (folder / "config.env").write_text("\n".join(lines) + "\n")

        def old_app(k: str, **env):
            folder = old / k / "app"
            return subprocess.Popen([sys.executable, "-m", "app"], cwd=folder, stdout=open(old / k / "run.log", "a"), stderr=subprocess.STDOUT,
                                    env={**os.environ, "PYTHONPATH": str(folder / "shared"), **env})

        def old_cli(k: str, *args):
            folder = old / k / "app"
            return subprocess.run([sys.executable, "-m", "iosuite_shared.cli", "--config", ".", *args], cwd=folder, capture_output=True, text=True,
                                  env={**os.environ, "PYTHONPATH": str(folder / "shared")})
        for step in ("init", "demo"):
            done = old_cli(apps[0], step)
            if done.returncode:
                raise SystemExit(f"the old suite's `iosuite-shared {step}` failed:\n{done.stdout}{done.stderr}")
        for k in apps:  # each app once: its tables, its demo data, its row in the suite's list of apps
            proc = old_app(k, DEMO_PACKAGE=str(src / "demo"))
            procs.append(proc)
            up = wait(f"http://127.0.0.1:{ports[k]}/api/status", 120, proc)
            until = time.time() + 90
            while up and time.time() < until and not sql("SELECT 1 FROM rh_iosuite.ios_settings WHERE app = %s AND name = 'demo_seeded'", (k,)):
                time.sleep(1)
            stop(proc)
            procs.remove(proc)
            check(f"the old {catalog.name_of(k)} starts", up, f"see {old / k / 'run.log'}")
        if bad:
            return 1

        # ---- 2. what the old apps list, once every one of them has been there
        before = {}
        for k in apps:
            root = f"http://127.0.0.1:{ports[k]}"
            proc = old_app(k)
            procs.append(proc)
            cookie = sign_in(root) if wait(root + "/api/status", 120, proc) else None
            before[k] = take(root, cookie, ASK[k]) if cookie else {}
            stop(proc)
            procs.remove(proc)
            check(f"the old {catalog.name_of(k)} lists its demo data", bool(cookie) and all(v[0] == 200 for v in before[k].values())
                  and any(v[1] > 0 for v in before[k].values()),
                  f"signed in: {bool(cookie)}, {[(p, v[0], v[1]) for p, v in before[k].items()]}; see {old / k / 'run.log'}")
        if bad:
            return 1
        if svc:  # the old apps as the services their installer made, running: the move has them to stop
            for k in apps:
                (UNITS / f"{k}.service").write_text(UNIT.format(name=catalog.name_of(k), folder=old / k / "app", python=sys.executable))
            systemctl("daemon-reload")
            systemctl("enable", "-q", "--now", *apps)
            up = [k for k in apps if wait(f"http://127.0.0.1:{ports[k]}/api/status", 120)]
            check("the old apps run as services", up == apps, f"not {', '.join(k for k in apps if k not in up)}; journalctl -u <app>")
            if bad:
                return 1

        # ---- 3. the move
        print(f"== convert.py --apply, into {new}", flush=True)
        new.mkdir()
        for item in sorted(HERE.iterdir()):
            if item.name in ("config.env", "data", "copies", ".venv", ".git", ".github", "docs", "devices", "proxmox", "node_modules", ".pytest_cache",
                             "COMMIT", "FILES", "EXTRAS", "SERVICES") or item.name.endswith(".egg-info"):
                continue
            (shutil.copytree if item.is_dir() else shutil.copy2)(item, new / item.name, **({"ignore": shutil.ignore_patterns("__pycache__")} if item.is_dir() else {}))
        env = {**os.environ, "DB_ADMIN_PASSWORD": password}
        for k in ("APPS", "HOST", "PORT", "SYNC_PORT", "MCP_PORT", "DATA_DIR", "LOG_FILE", "INTERNAL_URL", "PYTHONPATH", "IOSUITE_CONFIG"):
            env.pop(k, None)
        if own:  # as install.sh --fetch leaves it: an environment of its own with the suite's own packages; the move installs the apps'
            python = str(new / ".venv" / "bin" / "python")
            made = subprocess.run([sys.executable, "-m", "venv", str(new / ".venv")], capture_output=True, text=True)
            if made.returncode == 0:
                made = subprocess.run([python, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-e", str(new)], capture_output=True, text=True)
            check("the program's own environment is made", made.returncode == 0, (made.stdout + made.stderr)[-2000:])
            if bad:
                return 1
        else:    # this Python holds the packages already (`iosuite install` then installs none), and runs the folder's code
            python = sys.executable
            (new / "EXTRAS").write_text(install.extras_for(apps) + "\n")
            env.update(PYTHONPATH=str(new), IOSUITE_CONFIG=str(new / "config.env"))

        def convert(log_name: str, *more) -> subprocess.CompletedProcess:
            cmd = [python, str(new / "tools" / "convert" / "convert.py"), "--from", str(old), "--apply", "--db-admin", user, "--client-host", "%",
                   "--port", str(PORTS[0]), "--sync-port", str(PORTS[1]), "--mcp-port", str(PORTS[2]), *more]
            if a.apps:
                cmd += ["--apps", ",".join(apps)]
            done = subprocess.run(cmd, env=env, cwd=work if own else new, capture_output=True, text=True)
            (work / log_name).write_text(done.stdout + done.stderr)
            return done

        if svc:  # a move that cannot come up: the old services must run again, and a data folder that was moved must be back
            held = [k for k in apps if (old / k / "app" / "data").is_dir() and any((old / k / "app" / "data").iterdir())]
            done = convert("convert-fails.log", "--host", NOWHERE, "--wait", "20", "--data", "move")
            said = done.stdout + done.stderr
            check("a move that cannot come up stops, and says the old services run again", done.returncode != 0 and "The old service(s) run again" in said, said[-3000:])
            check("the old services run again", all(systemctl("is-active", "-q", k).returncode == 0 for k in apps)
                  and wait(f"http://127.0.0.1:{ports[apps[0]]}/api/status", 120), systemctl("is-active", *apps).stdout)
            check("the service iosuite is not left behind", systemctl("is-active", "-q", "iosuite").returncode != 0 and systemctl("is-enabled", "-q", "iosuite").returncode != 0)
            check("a data folder that was moved is back", all((old / k / "app" / "data").is_dir() and any((old / k / "app" / "data").iterdir()) for k in held),
                  f"{', '.join(held) or 'no app had one'}")
            if bad:
                return 1
            done = convert("convert.log", "--host", "127.0.0.1")
        else:
            done = convert("convert.log", "--no-service")
        check("convert.py --apply finishes", done.returncode == 0, (done.stdout + done.stderr)[-3000:])
        if bad:
            return 1

        # ---- 4. the one program
        print("== the one program", flush=True)
        root = f"http://127.0.0.1:{PORTS[0]}"
        if svc:
            serve = None
            check("the service iosuite runs, and the old services are stopped and switched off",
                  systemctl("is-active", "-q", "iosuite").returncode == 0
                  and not any(systemctl("is-active", "-q", k).returncode == 0 or systemctl("is-enabled", "-q", k).returncode == 0 for k in apps),
                  systemctl("is-active", "iosuite", *apps).stdout.replace("\n", " "))
        else:
            serve = subprocess.Popen([python, "-m", "iosuite_shared.cli", "serve"], cwd=new, env=env, stdout=open(work / "serve.log", "w"), stderr=subprocess.STDOUT)
            procs.append(serve)
        check("it starts", wait(root + "/-/status", 180, serve), f"see {work / 'serve.log'}" if serve else "journalctl -u iosuite")
        cookie = sign_in(root) if not bad else None
        check("the demo family signs in", bool(cookie))
        for k in apps if cookie else []:
            folder = catalog.FOLDERS.get(k)
            after = take(root + (f"/{folder}" if folder else ""), cookie, ASK[k])
            differ = [f"{p}: {after[p][:2]} was {before[k][p][:2]}" for p in ASK[k] if after[p] != before[k][p]]
            check(f"{catalog.name_of(k)} lists what it listed before ({sum(v[1] for v in after.values())} thing(s))", not differ, "; ".join(differ))
        if "iostart" in apps and cookie:  # the old start page listed only the apps with an address stored; now each has its folder
            code, body, _ = ask(root + "/api/apps", cookie)
            listed = gist(json.loads(body) if code == 200 else [])["n"]
            check("the start page lists every other app", listed >= len(apps) - 1, f"{code}, {listed} of {len(apps) - 1}")
        stored = {(r[0], r[1]): r[2] for r in sql("SELECT app, name, value FROM rh_iosuite.ios_settings")}
        keys = {(r[0], r[1]): r[2] for r in sql("SELECT app, name, value FROM rh_iosuite.ios_credentials")}
        if "iocalendar" in apps:
            check("ioCalendar keeps its own address and its settings",
                  (stored.get(("iocalendar", "PUBLIC_URL")), stored.get(("iocalendar", "HOLIDAYS_COUNTRY")), stored.get(("iocalendar", "KEEP_DELETED_DAYS")),
                   stored.get(("iocalendar", "DB_NAME"))) == ("https://calendar.example.test", "BE", "45", "rh_iocalendar"), str({k: v for k, v in stored.items() if k[0] == "iocalendar"}))
        if "iostart" in apps:
            check("the suite's address, sign-in domain and time zone are the start page's",
                  (stored.get(("", "PUBLIC_URL")), stored.get(("", "COOKIE_DOMAIN")), stored.get(("", "TZ"))) == ("https://home.example.test", "example.test", "Europe/Brussels"))
            check("the weather key of the old file is in Keys and tokens", keys.get(("iostart", "accuweather_key")) == "old-weather-key")
            check("Home Assistant's address of the old file is in ioStart's settings",
                  sql("SELECT value FROM rh_iostart.prt_settings WHERE name = 'ha_url'") == (("http://ha.example.test:8123",),))
        if "iotask" in apps and "iostart" in apps:
            check("an address that was the app's folder at the suite's is not stored as its own", ("iotask", "PUBLIC_URL") not in stored)
        if "iopix" in apps:
            check("the maps key of the old file is in Keys and tokens", keys.get(("iopix", "google_maps_key")) == "old-maps-key")
        # ---- 5. going back
        k = apps[0]
        root = f"http://127.0.0.1:{ports[k]}"
        if svc:  # the two commands the converter's last lines give
            said = (work / "convert.log").read_text()
            check("the converter says how to go back", f"systemctl disable --now iosuite && systemctl enable --now {' '.join(apps)}" in said, said[-1500:])
            systemctl("disable", "-q", "--now", "iosuite")
            systemctl("enable", "-q", "--now", *apps)
            proc = None
        else:
            stop(serve)
            procs.remove(serve)
            proc = old_app(k)
            procs.append(proc)
        up = wait(root + "/api/status", 120, proc)
        cookie = sign_in(root) if up else None
        check(f"the old {catalog.name_of(k)} starts again afterwards, and lists the same", bool(cookie) and take(root, cookie, ASK[k]) == before[k])
        if proc:
            stop(proc)
            procs.remove(proc)
    finally:
        for proc in procs:
            stop(proc)
        if svc:  # the services this made, and their files
            systemctl("disable", "-q", "--now", "iosuite", *apps)
            for n in ("iosuite", *apps):
                (UNITS / f"{n}.service").unlink(missing_ok=True)
            systemctl("daemon-reload")
        if not a.keep:
            drop()
        if not a.work and not bad:
            shutil.rmtree(work, ignore_errors=True)
    print("the move keeps everything" if not bad else f"{len(bad)} thing(s) not as they should be (the scratch folder: {work})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

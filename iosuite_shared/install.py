"""`iosuite install`: set this machine up, and change what it runs afterwards.

install.sh (the one line from the website) fetches the program into its folder, makes its Python environment and
hands over to this command; run again at any time, the same command changes what the machine runs:

    iosuite install                              a new machine: asks its questions; later: the list of apps, to tick and untick
    iosuite install --add iotask,ionote          run these apps here too
    iosuite install --remove iodns               stop running them here (their databases and data stay)
    iosuite install --apps iostart,iocalendar    exactly these (all: every app)
    iosuite install --list                       what this machine runs
    iosuite install --copy pix --apps iopix      a second copy of the program on this machine, with ports of its own
                                                 (ioPix's long scans then never slow the others; both are one suite)
    iosuite install --remove-copy pix

What a new machine is asked, each with an option to answer it ahead (--yes: no questions at all):

    --db HOST[:PORT]        the MariaDB / MySQL server (127.0.0.1:3306); --db-name, --db-user: the Shared ioSuite
                            database and the suite's one login (iosuite, iosuite); its password from
                            IOSUITE_DB_PASSWORD, else asked (made up when --db-admin creates the login)
    --db-admin USER         a MariaDB administrator who creates the databases and the login (its password from
                            DB_ADMIN_PASSWORD, else asked; root on this machine needs none); --client-host: the host
                            the login is made for (iosuite_shared.provision)
    --mariadb               install MariaDB on this machine first (apt), when it has no database server
    --admin NAME            the first admin (password from ADMIN_PASSWORD, else asked; empty: made in the browser)
    --address URL           the suite's address (https://home.example.com): Settings › Apps › All settings
    --set APP.NAME=VALUE    a setting to store (iopix.PHOTOS_ROOT=/srv/photos, suite.TZ=Europe/Brussels); repeatable. An
                            app added just now asks for the few it cannot guess (ioPix: the photos folder) unless given
    --host, --port, --sync-port, --mcp-port     where it listens (every address; 80, 8443, 8444; off: not opened)
    --extras LIST           optional sets of Python packages beside the apps' own (iopix-ai, iorecipe-ai)
    --user USER             the account the service runs as (default: the owner of the program folder), created when missing
    --service | --no-service    run as a systemd service (the default as root), or start it by hand

The machine's file (config.env; a second copy's: copies/<name>/config.env) holds only how to reach the Shared ioSuite
database, the apps and the ports. Everything else is a setting in that database (`iosuite set`, Settings).
Beside it the installer keeps EXTRAS (the Python extras installed, which update.sh refreshes) and SERVICES (the
systemd units of this folder, which update.sh restarts).
"""
from __future__ import annotations

import getpass
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

NAME = re.compile(r"^[a-z][a-z0-9-]{0,20}$")
UNIT_DIR = Path("/etc/systemd/system")
SOCKETS = ("/run/mysqld/mysqld.sock", "/var/run/mysqld/mysqld.sock", "/var/lib/mysql/mysql.sock", "/tmp/mysql.sock")
COPY_PORTS = (8081, 8082, 8083)  # a second copy's doors, when none are given (a third: ten higher, and so on)


def say(msg: str) -> None:
    print(f"\n\033[1;34m==>\033[0m {msg}" if sys.stdout.isatty() else f"\n==> {msg}")


def die(msg: str):
    raise SystemExit(f"error: {msg}")


# ---- the machine's file
def read_env(path) -> dict:
    """KEY=value lines of a machine's file (comments and blank lines left out; quotes taken off)."""
    out = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def write_env(path, changes: dict, header: str = "") -> None:
    """Set these keys in a machine's file, keeping its other lines and its comments (None: the key is taken out).
    A new file begins with `header`. Only its owner reads it: it holds the database password."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = [x for x in header.splitlines()]
    left = dict(changes)
    out = []
    for line in lines:
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in left:
            v = left.pop(m.group(1))
            if v is not None:
                out.append(f"{m.group(1)}={v}")
            continue
        out.append(line)
    out += [f"{k}={v}" for k, v in left.items() if v is not None]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".new")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, path)


HEADER = """# The machine's file: how this machine reaches the Shared ioSuite database, and what it runs.
# Everything else is kept in the Shared ioSuite database: Settings › Apps › All settings, or `iosuite set`.
# Written by `iosuite install`; run it again to change the apps."""


# ---- which apps, which packages
def parse_apps(spec: str) -> list:
    """The app keys a list names (commas or spaces; all: every app), in the suite's order; SystemExit on one that is not an app."""
    from iosuite_shared import catalog
    asked = [x.strip().lower() for x in re.split(r"[,\s]+", spec or "") if x.strip()]
    if "all" in asked:
        return catalog.install_order()
    unknown = [a for a in asked if a not in catalog.APPS]
    if unknown:
        die(f"no such app: {', '.join(unknown)} (the suite's apps: {', '.join(catalog.install_order())})")
    return [k for k in catalog.install_order() if k in asked]


def apps_of(cfg: dict) -> list:
    """The apps a machine's file names (APPS empty: every app)."""
    from iosuite_shared import catalog
    named = [x.strip().lower() for x in re.split(r"[,\s]+", cfg.get("APPS") or "") if x.strip()]
    return [k for k in catalog.install_order() if k in named] if named else catalog.install_order()


def apps_line(apps: list) -> str:
    """APPS for these apps: empty when they are all of them (an app that joins the suite later runs here too)."""
    from iosuite_shared import catalog
    return "" if set(apps) >= set(catalog.APPS) else ",".join(apps)


def extras_for(apps: list, more=()) -> str:
    """The pip extras for these apps and the optional sets chosen beside them: iostart,iocalendar,iopix-ai."""
    from iosuite_shared import catalog
    if set(apps) >= set(catalog.APPS) and not more:
        return "all"
    allowed = {x for m in catalog.APPS.values() for x in m.get("extras") or ()}
    bad = [x for x in more if x not in allowed]
    if bad:
        die(f"no such set of packages: {', '.join(bad)} (there are: {', '.join(sorted(allowed)) or 'none'})")
    return ",".join(dict.fromkeys(["all"] if set(apps) >= set(catalog.APPS) else list(apps)) | dict.fromkeys(more))


def system_packages(apps: list) -> list:
    """The system packages (apt names) these apps ask for (their app.json: "system")."""
    from iosuite_shared import catalog
    out = []
    for a in apps:
        for p in (catalog.APPS.get(a) or {}).get("system") or ():
            if re.fullmatch(r"[a-z0-9][a-z0-9.+-]*", p) and p not in out:
                out.append(p)
    return out


def missing_system(apps: list, run=subprocess.run) -> list:
    """Those of them that are not installed (dpkg); none where there is no dpkg. A library that newer Debian and
    Ubuntu renamed with t64 at its end (libglib2.0-0t64) is the one asked for."""
    if not shutil.which("dpkg"):
        return []

    def there(p):
        return any(run(["dpkg", "-s", name], capture_output=True).returncode == 0 for name in (p, p + "t64"))
    return [p for p in system_packages(apps) if not there(p)]


# ---- every copy of this folder
def copies(base: Path) -> dict:
    """{name: its machine's file} of the copies of the program in this folder: '' is the main one (config.env)."""
    out = {}
    if (base / "config.env").exists():
        out[""] = base / "config.env"
    for p in sorted((base / "copies").glob("*/config.env")):
        if NAME.match(p.parent.name):
            out[p.parent.name] = p
    return out


def unit_name(copy: str = "") -> str:
    return f"iosuite-{copy}" if copy else "iosuite"


def all_apps(base: Path) -> list:
    """Every app some copy of this folder runs (what the one Python environment has to hold)."""
    from iosuite_shared import catalog
    seen = set()
    for f in copies(base).values():
        seen.update(apps_of(read_env(f)))
    return [k for k in catalog.install_order() if k in seen]


def unit(base: Path, user: str, copy: str = "", heavy: bool = False) -> str:
    """The systemd unit of a copy. It may open ports below 1024 whoever it runs as, and is started again whenever it
    ends: that is how an update and Settings' Restart start it on the new code."""
    env = f"Environment=IOSUITE_CONFIG={base}/copies/{copy}/config.env\n" if copy else ""
    more = ("# CPU-heavy background jobs run in this service; keep it below interactive work\nNice=5\n"
            "# a job that the system ends for memory does not take the service with it\nOOMPolicy=continue\n") if heavy else ""
    return f"""[Unit]
Description=ioSuite{f' ({copy})' if copy else ''}
After=network-online.target mariadb.service mysql.service
Wants=network-online.target

[Service]
Type=simple
User={user}
WorkingDirectory={base}
{env}Environment=PYTHONUNBUFFERED=1
ExecStart={base}/.venv/bin/iosuite serve
Restart=always
RestartSec=2
TimeoutStopSec=20
AmbientCapabilities=CAP_NET_BIND_SERVICE
LimitNOFILE=65536
{more}
[Install]
WantedBy=multi-user.target
"""


# ---- asking
class Asker:
    """Questions at the keyboard; with --yes (or no keyboard) every question takes its default."""

    def __init__(self, quiet: bool, ask=input, secret=getpass.getpass):
        self.quiet = quiet or not sys.stdin.isatty()
        self._ask, self._secret = ask, secret

    def text(self, question: str, default: str = "") -> str:
        if self.quiet:
            return default
        got = self._ask(f"{question}{f' [{default}]' if default else ''}: ").strip()
        return got or default

    def yes(self, question: str, default: bool = True) -> bool:
        if self.quiet:
            return default
        got = self._ask(f"{question} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        return default if not got else got in ("y", "yes")

    def password(self, question: str) -> str:
        return "" if self.quiet else self._secret(f"{question}: ")


def table(here: list, want: list) -> str:
    """The list of apps as the installer shows it: a number each, [x] the ones that run here."""
    from iosuite_shared import catalog
    lines = []
    for i, k in enumerate(catalog.install_order(), 1):
        m = catalog.APPS[k]
        mark = "x" if k in want else " "
        note = "" if (k in want) == (k in here) else ("   (to add)" if k in want else "   (to remove)")
        about = m.get("aside") or m["description"]
        more = f", {m['otherPorts']}" if m.get("otherPorts") else ""
        lines.append(f"  {i:2} [{mark}] {m['name']:12} {about}{more}{note}")
    return "\n".join(lines)


def choose(here: list, asker: Asker, log=print) -> list:
    """Tick and untick apps by their numbers until Enter; the apps wanted."""
    from iosuite_shared import catalog
    order = catalog.install_order()
    want = list(here)
    if asker.quiet:
        return want
    while True:
        log(table(here, want))
        got = asker.text("Numbers to tick or untick (a: all), Enter when the list is right")
        if not got:
            return [k for k in order if k in want]
        if got.lower() in ("a", "all"):
            want = list(order)
            continue
        for part in re.split(r"[,\s]+", got):
            if part.isdigit() and 1 <= int(part) <= len(order):
                k = order[int(part) - 1]
                want.remove(k) if k in want else want.append(k)
            elif part:
                log(f"  {part}: a number from 1 to {len(order)}")


# ---- the steps
def sh(cmd: list, **kw):
    return subprocess.run(cmd, **kw)


def pip_install(base: Path, extras: str, run=sh, log=print) -> None:
    """The Python packages of these extras into the folder's environment (uv when it is there: much faster)."""
    target = f"{base}[{extras}]" if extras else str(base)
    py = str(base / ".venv" / "bin" / "python")
    cmd = ["uv", "pip", "install", "-q", "-p", py, "-e", target] if shutil.which("uv") else [py, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-e", target]
    log(f"  Python packages: {extras or 'the suite’s own'}")
    if run(cmd).returncode != 0:
        die("installing the Python packages failed (see above); nothing else was changed")
    (base / "EXTRAS").write_text(extras + "\n")


def apt_install(pkgs: list, run=sh, log=print) -> bool:
    """Install system packages when this is root on a machine with apt; False (and a note) when it could not."""
    if not pkgs:
        return True
    if os.geteuid() != 0 or not shutil.which("apt-get"):
        log(f"  note: the system packages {' '.join(pkgs)} are missing; as root: apt-get install -y {' '.join(pkgs)}")
        return False
    log(f"  system packages: {' '.join(pkgs)}")
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    cmd = ["apt-get", "install", "-y", "-qq", "--no-install-recommends", *pkgs]
    if run(cmd, env=env, stdout=subprocess.DEVNULL).returncode != 0:
        run(["apt-get", "update", "-qq"], env=env, stdout=subprocess.DEVNULL)
        if run(cmd, env=env, stdout=subprocess.DEVNULL).returncode != 0:
            log(f"  note: the system packages {' '.join(pkgs)} could not be installed; as root: apt-get install -y {' '.join(pkgs)}")
            return False
    return True


def listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            return True
    except OSError:
        return False


def is_local(host: str) -> bool:
    return (host or "").lower() in ("127.0.0.1", "localhost", "::1")


def admin_connect(admin: str, password: str):
    """How the MariaDB administrator connects: with its password, or, as root on this machine with none, through
    the server's socket (how Debian's MariaDB lets root in)."""
    import pymysql

    def connect(host, port):
        if not password and is_local(host):
            for s in SOCKETS:
                if os.path.exists(s):
                    return pymysql.connect(unix_socket=s, user=admin, connect_timeout=10, autocommit=True)
        return pymysql.connect(host=host, port=int(port), user=admin, password=password, connect_timeout=10, autocommit=True)
    return connect


def ensure_user(user: str, run=sh, log=print) -> None:
    """The account the service runs as, made as a system account when it is missing."""
    import pwd
    try:
        pwd.getpwnam(user)
        return
    except KeyError:
        pass
    log(f"  the account {user} (a system account, no sign-in)")
    if run(["useradd", "--system", "--user-group", "--no-create-home", "--shell", "/usr/sbin/nologin", user]).returncode != 0:
        die(f"could not create the account {user}")


def owner_of(path: Path) -> str:
    import pwd
    try:
        return pwd.getpwuid(path.stat().st_uid).pw_name
    except (OSError, KeyError):
        return "root"


def write_services(base: Path, user: str, run=sh, log=print, unit_dir: Path = UNIT_DIR) -> list:
    """A systemd unit for every copy of this folder, enabled; SERVICES lists them for update.sh. The units written."""
    names = []
    for copy, f in copies(base).items():
        name = unit_name(copy)
        text = unit(base, user, copy, heavy="iopix" in apps_of(read_env(f)))
        path = unit_dir / f"{name}.service"
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
        names.append(name)
    (base / "SERVICES").write_text("".join(n + "\n" for n in names))
    run(["systemctl", "daemon-reload"])
    for n in names:
        run(["systemctl", "enable", "-q", n])
    return names


def restart(names: list, run=sh, log=print, wait: float = 3) -> None:
    import time
    for n in names:
        run(["systemctl", "restart", n])
    time.sleep(wait if run is sh else 0)
    for n in names:
        if run(["systemctl", "is-active", "-q", n]).returncode != 0:
            die(f"the service {n} did not start: journalctl -u {n} -n 50")
        log(f"  {n} is running")


def chown(base: Path, user: str, run=sh) -> None:
    """Everything the service writes is its account's: the folder (the updater replaces the code), the environment,
    the machine's files and the data."""
    if os.geteuid() == 0 and user != owner_of(base):
        run(["chown", "-R", f"{user}:", str(base)])


def port_of(value, default: int) -> int:
    v = str(value if value is not None else "").strip().lower()
    if v in ("off", "none", "no"):
        return 0
    if v == "":
        return default
    if not v.isdigit() or int(v) > 65535:
        die(f"a port is a number up to 65535, or off: {value}")
    return int(v)


def clash(base: Path, copy: str, ports: tuple, host: str) -> str:
    """The copy of this folder that already has one of these ports on the same addresses ('' : none)."""
    for other, f in copies(base).items():
        if other == copy:
            continue
        c = read_env(f)
        if (c.get("HOST") or "") != (host or "") and c.get("HOST") and host:
            continue
        theirs = {port_of(c.get("PORT"), 80), port_of(c.get("SYNC_PORT"), 8443), port_of(c.get("MCP_PORT"), 8444)} - {0}
        if theirs & (set(ports) - {0}):
            return other or "the main copy"
    return ""


def add_parser(sub):
    p = sub.add_parser("install", help="set this machine up, or change the apps it runs (asks what it is not told)")
    p.add_argument("--apps", default=None, help="exactly these apps (all: every app)")
    p.add_argument("--add", default=None, help="run these apps here too")
    p.add_argument("--remove", default=None, help="stop running these apps here (their databases and data stay)")
    p.add_argument("--list", action="store_true", help="only show what this machine runs")
    p.add_argument("--copy", default="", help="a second copy of the program on this machine, by name (pix), with apps and ports of its own")
    p.add_argument("--remove-copy", default=None, help="take a second copy away (its apps' databases and data stay)")
    p.add_argument("--extras", default=None, help="optional sets of Python packages beside the apps' own (iopix-ai, iorecipe-ai)")
    p.add_argument("--db", default=None, help="the MariaDB / MySQL server: HOST[:PORT] (default 127.0.0.1:3306)")
    p.add_argument("--db-name", default=None, help="the Shared ioSuite database (default iosuite)")
    p.add_argument("--db-user", default=None, help="the suite's one login (default iosuite; its password from IOSUITE_DB_PASSWORD, else asked)")
    p.add_argument("--db-admin", default=None, help="a MariaDB administrator who creates the databases and the login (password from DB_ADMIN_PASSWORD, else asked)")
    p.add_argument("--client-host", default=None, help="with --db-admin: the host the login is made for (default: this machine as the server sees it)")
    p.add_argument("--mariadb", action="store_true", help="install MariaDB on this machine first when it has no database server (apt)")
    p.add_argument("--admin", default=None, help="the first admin's name (password from ADMIN_PASSWORD, else asked)")
    p.add_argument("--address", default=None, help="the suite's address (https://home.example.com)")
    p.add_argument("--set", action="append", default=[], metavar="APP.NAME=VALUE", help="a setting to store (iopix.PHOTOS_ROOT=/srv/photos, suite.TZ=Europe/Brussels); repeatable")
    p.add_argument("--host", default=None, help="the addresses it listens on (default: every address; 127.0.0.1: behind a reverse proxy here)")
    p.add_argument("--port", default=None, help="the port of the pages (default 80)")
    p.add_argument("--sync-port", default=None, help="the port for phones, native apps and devices (default 8443; off: not opened)")
    p.add_argument("--mcp-port", default=None, help="the port for MCP clients (default 8444; off: not opened)")
    p.add_argument("--user", default=None, help="the account the service runs as (default: the owner of the program folder)")
    p.add_argument("--service", dest="service", action="store_true", default=None, help="run as a systemd service (the default as root)")
    p.add_argument("--no-service", dest="service", action="store_false", help="no service: start it by hand (iosuite serve)")
    p.add_argument("--yes", action="store_true", help="no questions: every one takes its default")
    return p


def show(base: Path, log=print) -> None:
    from iosuite_shared import catalog
    found = copies(base)
    if not found:
        log(f"ioSuite is not set up in {base} yet")
        return
    for copy, f in found.items():
        c = read_env(f)
        ports = [f"{n} {port_of(c.get(k), d) or 'off'}" for n, k, d in (("pages", "PORT", 80), ("devices", "SYNC_PORT", 8443), ("MCP", "MCP_PORT", 8444))]
        log(f"{unit_name(copy)}: {', '.join(catalog.name_of(a) for a in apps_of(c))}")
        log(f"    {f}   ({', '.join(ports)})")


def main(a, log=print, run=sh, ask=input, secret=getpass.getpass, unit_dir: Path = UNIT_DIR, base: Path = None, systemd: bool = None) -> int:
    from iosuite_shared import catalog, config
    base = Path(base or config.BASE)
    if a.list:
        show(base, log)
        return 0
    asker = Asker(a.yes, ask, secret)
    if systemd is None:
        systemd = os.geteuid() == 0 and shutil.which("systemctl") is not None and Path("/run/systemd/system").exists()
    service = systemd if a.service is None else a.service
    if service and not systemd:
        die("--service needs root on a machine with systemd")

    if a.remove_copy is not None:
        return remove_copy(a.remove_copy, base, service, log, run, unit_dir)
    if a.copy and not NAME.match(a.copy):
        die(f"--copy {a.copy}: a short name in small letters (pix)")
    if a.copy and "" not in copies(base):
        die("this machine has no ioSuite yet: set the main copy up first (iosuite install), then add a second one")
    file = base / "copies" / a.copy / "config.env" if a.copy else base / "config.env"
    cfg = read_env(file)
    main_cfg = read_env(base / "config.env") if a.copy else cfg
    new = not a.copy and not cfg.get("IOSUITE_DB_PASSWORD")  # a second copy is of the same suite: the main copy's database

    # ---- which apps
    here = [] if not file.exists() else apps_of(cfg)
    if a.apps is not None:
        want = parse_apps(a.apps)
    elif a.add or a.remove:
        want = [k for k in catalog.install_order() if (k in here or k in parse_apps(a.add or "")) and k not in parse_apps(a.remove or "")]
    elif a.copy and not file.exists():
        want = [k for k in catalog.install_order() if catalog.APPS[k].get("apart")]
    elif new:
        say("The apps of this machine")
        want = choose(catalog.install_order(), asker, log)
    else:
        say(f"ioSuite on this machine ({base})")
        show(base, log)
        want = choose(here, asker, log)
    if not want:
        die("no app left to run here: name at least one (to take a second copy away: --remove-copy NAME)")
    for other, f in copies(base).items():  # an app runs in one copy of a machine
        if other == a.copy:
            continue
        theirs = apps_of(read_env(f))
        both = [k for k in want if k in theirs]
        if not both:
            continue
        if a.copy:  # a second copy takes its apps from the copy that had them
            left = [k for k in theirs if k not in both]
            if not left:
                die(f"{', '.join(both)}: that would leave {unit_name(other)} without an app")
            write_env(f, {"APPS": ",".join(left)})
        else:  # the main copy never runs what a second copy runs
            want = [k for k in want if k not in both]
    if not want:
        die("every app named runs in another copy of this machine already")

    changes: dict = {"APPS": apps_line(want)}
    # ---- where it listens
    defaults = (80, 8443, 8444) if os.geteuid() == 0 else (8080, 8443, 8444)
    if a.copy and not file.exists():
        n = len([c for c in copies(base) if c])
        defaults = tuple(p + 10 * n for p in COPY_PORTS)
    ports = (port_of(a.port if a.port is not None else cfg.get("PORT"), defaults[0]),
             port_of(a.sync_port if a.sync_port is not None else cfg.get("SYNC_PORT"), defaults[1]),
             port_of(a.mcp_port if a.mcp_port is not None else cfg.get("MCP_PORT"), defaults[2]))
    host = a.host if a.host is not None else cfg.get("HOST") or ""
    taken = clash(base, a.copy, ports, host)
    if taken:
        die(f"the ports {', '.join(str(p) for p in ports if p)} are {taken}'s on this machine: give others (--port, --sync-port, --mcp-port)")
    for key, value, default in (("PORT", ports[0], 80), ("SYNC_PORT", ports[1], 8443), ("MCP_PORT", ports[2], 8444)):
        if value != default or key in cfg:
            changes[key] = value or "off"
    if a.host is not None:
        changes["HOST"] = a.host or None
    if a.copy:  # its own log beside the main one (the data folder is shared: each app has a folder of its own in it)
        changes.update({k: v for k, v in main_cfg.items() if k.startswith("IOSUITE_DB_") or k in ("TLS_CERT_FILE", "TLS_KEY_FILE")})
        data = Path(main_cfg.get("DATA_DIR") or base / "data")
        changes.setdefault("DATA_DIR", str(data))
        changes["LOG_FILE"] = cfg.get("LOG_FILE") or str(data / f"iosuite-{a.copy}.log")

    # ---- the database
    db_admin, db_admin_password, made_password = a.db_admin, os.environ.get("DB_ADMIN_PASSWORD") or "", False
    if new:
        say("The database")
        server = a.db or asker.text("MariaDB / MySQL server (host or host:port)", "127.0.0.1:3306")
        dbhost, _, dbport = server.partition(":")
        dbport = dbport or "3306"
        if is_local(dbhost) and not listening(dbhost, dbport) and os.geteuid() == 0 and shutil.which("apt-get"):
            if a.mariadb or (not asker.quiet and asker.yes("No database server answers on this machine. Install MariaDB here?")):
                say("Installing MariaDB")
                apt_install(["mariadb-server"], run, log)
                run(["systemctl", "enable", "-q", "--now", "mariadb"])
                db_admin = db_admin or "root"
        name = a.db_name or asker.text("The Shared ioSuite database", "iosuite")
        user = a.db_user or asker.text("The suite's login", "iosuite")
        if db_admin is None and not asker.quiet:
            db_admin = asker.text("A MariaDB administrator who may create the databases and the login (root; empty: they exist already)", "") or None
        if db_admin and not db_admin_password and not (is_local(dbhost) and db_admin == "root" and os.geteuid() == 0):
            db_admin_password = asker.password(f"Password of {db_admin}")
        password = os.environ.get("IOSUITE_DB_PASSWORD") or ""
        if not password and db_admin:
            password, made_password = secrets.token_urlsafe(18), True
        if not password:
            password = asker.password(f"Password of the login {user}")
        if not password:
            die("the suite's login needs a password: IOSUITE_DB_PASSWORD in the environment, or --db-admin to have the login made")
        changes.update({"IOSUITE_DB_HOST": dbhost, "IOSUITE_DB_PORT": dbport, "IOSUITE_DB_NAME": name, "IOSUITE_DB_USER": user, "IOSUITE_DB_PASSWORD": password})
    write_env(file, changes, HEADER)
    cfg = read_env(file)
    for k, v in changes.items():  # from here on this process reads the machine's file as it now is
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, str(v))
    config.load_file(file)

    # ---- the packages, for every copy of this folder (one environment)
    say("Packages")
    chosen = [x for x in re.split(r"[,\s]+", a.extras or "") if x]
    kept = [x for x in (base / "EXTRAS").read_text().strip().split(",") if "-" in x] if (base / "EXTRAS").exists() and a.extras is None else []
    extras = extras_for(all_apps(base), list(dict.fromkeys(chosen + kept)))
    was = (base / "EXTRAS").read_text().strip() if (base / "EXTRAS").exists() else None
    if extras != was:
        pip_install(base, extras, run, log)
    else:
        log(f"  Python packages: {extras} (as before)")
    apt_install(missing_system(all_apps(base), run), run, log)

    # ---- the databases, the tables, the first admin
    from iosuite_shared import admin, db, provision, stack, users
    if db_admin:
        say("Databases")
        t = provision.target()
        names = provision.databases(all_apps(base))
        provision.run(db_admin, db_admin_password, names, t, connect=admin_connect(db_admin, db_admin_password), log=log, client=a.client_host,
                      check=lambda t: __import__("pymysql").connect(host=t["host"], port=int(t["port"]), user=t["user"], password=t["password"],
                                                                    database=t["name"], connect_timeout=10).close())
    if not users.init():
        die(f"the Shared ioSuite database cannot be reached ({config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}): {db.error}\n"
            f"  create it and the login first, or run this again with --db-admin USER; the answers so far are kept in {file}")
    if new and not users.any_users():
        say("The first admin")
        name = a.admin if a.admin is not None else asker.text("Admin user name (empty: made in the browser on the first visit)", "")
        if name:
            pw = os.environ.get("ADMIN_PASSWORD") or asker.password(f"Password for {name} (8 characters or more)")
            if pw:
                try:
                    users.create(name, pw, suite_admin=True)
                    log(f"  {name} is a suite admin")
                except ValueError as e:
                    log(f"  note: {e}; make the admin in the browser on the first visit")
            else:
                log("  no password given: the admin is made in the browser on the first visit")
    address = a.address if a.address is not None else (asker.text("The suite's address behind your reverse proxy, e.g. https://home.example.com (empty: the address it is reached at)", "")
                                                       if new else None)
    if address or a.address is not None:  # an empty answer changes nothing; --address '' takes it away
        try:
            got = admin.set_setting(admin.SUITE, "PUBLIC_URL", address)
            log(f"  the suite's address: {got['value'] or 'the address it is reached at'}")
        except ValueError as e:
            die(str(e))
    # settings given on the command line, then what an app added just now asks for (ioPix: where the photos are)
    given = stack.parse_set(a.set)
    for key, value in given.items():
        app, name = key.split(".", 1)
        try:
            got = admin.set_setting(admin.SUITE if app in ("suite", "_suite") else app, name, value)
            log(f"  {key} = {got['value'] or '(the default)'}")
        except (LookupError, ValueError) as e:
            die(f"--set {key}: {str(e).strip(chr(39))}")
    for k in want:
        for q in ([] if k in here else catalog.APPS[k].get("ask") or []):
            if f"{k}.{q['name']}" in given or db.get_setting(q["name"], None, k) not in (None, ""):
                continue
            answer = asker.text(q["question"], "")
            if answer:
                try:
                    for name, value in {q["name"]: answer, **(q.get("also") or {})}.items():
                        admin.set_setting(k, name, value)
                    log(f"  {k}.{q['name']} = {answer}")
                except (LookupError, ValueError) as e:
                    log(f"  note: {e}; set it under Settings › Apps › All settings")
    # an app this copy no longer runs leaves the suite's list, unless another copy has taken it up
    from iosuite_shared import suite
    for k in here:
        if k not in want:
            r = suite.get(k)
            if r and r.get("copy") in (None, suite.copy_name()):
                suite.forget(k)

    # ---- the service
    names = []
    if service:
        say("The service")
        user = a.user or owner_of(base)
        ensure_user(user, run, log)
        for d in {Path(read_env(f).get("DATA_DIR") or base / "data") for f in copies(base).values()}:
            d.mkdir(parents=True, exist_ok=True)
            if os.geteuid() == 0:
                run(["chown", "-R", f"{user}:", str(d)])
        chown(base, user, run)
        if os.geteuid() == 0:
            for f in copies(base).values():
                run(["chown", f"{user}:", str(f)])
        names = write_services(base, user, run, log, unit_dir)
        restart(names, run, log)
    say("Done")
    show(base, log)
    if made_password:
        log(f"  the login's password was made up; it is in {file} (other machines of the suite need the same one)")
    where = cfg.get("INTERNAL_URL") or f"http://{socket.gethostname()}{'' if ports[0] in (80, 0) else f':{ports[0]}'}"
    if service:
        log(f"\nioSuite answers at {where}/   (the log: journalctl -u {unit_name(a.copy)} -f, or Settings › Servers › Logs)")
    else:
        log(f"\nStart it with: {'IOSUITE_CONFIG=' + str(file) + ' ' if a.copy else ''}{base}/.venv/bin/iosuite serve   (then {where}/)")
    log("Run `iosuite install` again at any time to change the apps of this machine.")
    return 0


def remove_copy(name: str, base: Path, service: bool, log=print, run=sh, unit_dir: Path = UNIT_DIR) -> int:
    if not NAME.match(name or "") or name not in copies(base):
        die(f"no copy {name!r} here (there are: {', '.join(c for c in copies(base) if c) or 'none beside the main one'})")
    unit_file = unit_dir / f"{unit_name(name)}.service"
    if service or unit_file.exists():
        run(["systemctl", "disable", "-q", "--now", unit_name(name)])
        if unit_file.exists():
            unit_file.unlink()
        run(["systemctl", "daemon-reload"])
    shutil.rmtree(base / "copies" / name)
    if (base / "SERVICES").exists():
        (base / "SERVICES").write_text("".join(unit_name(c) + "\n" for c in copies(base)))
    log(f"the copy {name} is gone; its apps' databases and data are kept. To run them in the main copy: iosuite install --add APP")
    return 0


if __name__ == "__main__":  # python -m iosuite_shared.install missing-system: for update.sh
    if sys.argv[1:] == ["missing-system"]:
        from iosuite_shared import config as _config
        print(" ".join(missing_system(all_apps(Path(_config.BASE)))))

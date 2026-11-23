"""Settings: one short file per machine, everything else in the Shared ioSuite database.

**The machine's file** is `config.env` in the program folder (IOSUITE_CONFIG names another one; in a container the
environment is the file). KEY=value lines, # comments; a variable already in the environment wins. It holds only what
cannot be read from the database, and is the same on every machine but for the list of apps:

    IOSUITE_DB_HOST, _PORT, _NAME, _USER, _PASSWORD   how to reach the Shared ioSuite database (needed before anything else)
    APPS                                              which apps this machine runs (iostart,iocalendar,…; empty: all installed)
    HOST                                              where the server listens (iosuite_shared.serve); every address by default
    PORT, SYNC_PORT, MCP_PORT                         the three doors of a copy (iosuite_shared.doors): the pages (80), what
                                                      devices and native apps sync with (8443), MCP (8444); 0 or off: not opened
    INTERNAL_URL                                      where the other machines of the suite call this copy (http://192.168.1.151);
                                                      empty: this machine's LAN address (a container has to say it)
    TLS_CERT_FILE, TLS_KEY_FILE                       HTTPS served directly instead of behind a reverse proxy: both files
    DATA_DIR                                          where the apps write on their own: <DATA_DIR>/<app> (default: data/ in the program folder)
    LOG_FILE                                          the copy's one log (default: <DATA_DIR>/iosuite.log; off: none)
    ADMIN_USER, ADMIN_PASSWORD                        the first admin, made on a first start with no accounts
    IOSUITE_REPO, IOSUITE_BRANCH                      what the update follows (development)

**Everything else** is a row of ios_settings in the Shared ioSuite database: for one app, or for the whole suite (app
''), which every app falls back to. An app reads its own once, as it starts (`settings(app)`), so a change takes
effect at the next start; people change them under Settings › Suite › Apps, and `iosuite set` writes one straight to
the database when the page cannot be reached. `declared(app)` lists the ones a person may set, for that screen and
that command.
"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # the program folder: this library and every app's package
FILE_NAME = "config.env"
FILE = None  # the machine's file load_file read (Path), once it has


def load_file(path=None) -> Path:
    """Read the machine's file into the environment (variables already set win), and the settings below again.
    `path`: the file, or a folder holding config.env; by default IOSUITE_CONFIG, else config.env in the program folder."""
    global FILE
    p = Path(path or os.environ.get("IOSUITE_CONFIG") or BASE / FILE_NAME).expanduser()
    if p.is_dir():
        p = p / FILE_NAME
    FILE = p
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                if k and k not in os.environ:
                    os.environ[k] = v
    _read()
    return p


def env(name: str, default: str = "") -> str:
    """A variable of the machine's file, stripped; `default` when it is unset or empty."""
    v = os.environ.get(name)
    return v.strip() if v is not None and v.strip() != "" else default


FLAG_ON, FLAG_OFF = ("1", "true", "yes", "on"), ("0", "false", "no", "off")


def as_flag(v, default: bool = False) -> bool:
    """An on/off value: 1, true, yes, on (any case) are on; 0, false, no, off are off; anything else: default."""
    v = str(v if v is not None else "").strip().lower()
    return True if v in FLAG_ON else False if v in FLAG_OFF else default


def apps_named(value: str) -> list:
    """The app keys a list names (commas or spaces), in its order, each once."""
    out = []
    for a in (value or "").replace(",", " ").split():
        if a.lower() not in out:
            out.append(a.lower())
    return out


PREFIX = "IOSUITE_DB_"


def _port(name: str, default: int) -> int:
    """A door's port from the machine's file: a number, or 0 (also: off, none) for a door that is not opened."""
    v = env(name).lower()
    if v in ("off", "none", "no"):
        return 0
    try:
        n = int(v) if v else default
    except ValueError:
        raise SystemExit(f"{name}={v}: a port number, or off")
    if not 0 <= n < 65536:
        raise SystemExit(f"{name}={v}: a port number, or off")
    return n


def _read():
    """The machine's settings, from the environment as it is now."""
    global DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, HOST, TLS_CERT_FILE, TLS_KEY_FILE, DATA_DIR, APPS
    global ADMIN_USER, ADMIN_PASSWORD, REPO, BRANCH, PORT, SYNC_PORT, MCP_PORT, INTERNAL_URL, LOG_FILE
    # The Shared ioSuite database: accounts, sessions, roles, app passwords, every setting and the list of apps. No
    # default password: the installer writes one into the file, a container gets it from its environment.
    DB_HOST = env(PREFIX + "HOST", "127.0.0.1")
    DB_PORT = int(env(PREFIX + "PORT", "3306"))
    DB_NAME = env(PREFIX + "NAME", "iosuite")
    DB_USER = env(PREFIX + "USER", "iosuite")
    DB_PASSWORD = os.environ.get(PREFIX + "PASSWORD", "")
    HOST = env("HOST", "0.0.0.0")
    # the three doors of a copy (iosuite_shared.doors): 0 where one is not opened
    PORT, SYNC_PORT, MCP_PORT = _port("PORT", 80), _port("SYNC_PORT", 8443), _port("MCP_PORT", 8444)
    INTERNAL_URL = env("INTERNAL_URL").rstrip("/")
    TLS_CERT_FILE, TLS_KEY_FILE = env("TLS_CERT_FILE"), env("TLS_KEY_FILE")
    DATA_DIR = Path(env("DATA_DIR", str(BASE / "data"))).expanduser().resolve()
    named = env("LOG_FILE")
    LOG_FILE = None if named.lower() in ("off", "none", "0") else Path(named or DATA_DIR / "iosuite.log").expanduser().resolve()
    APPS = apps_named(env("APPS"))
    # the first admin on an empty database (containers, installers)
    ADMIN_USER = env("ADMIN_USER")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    REPO = env("IOSUITE_REPO", "avandeputte/iosuite2")
    BRANCH = env("IOSUITE_BRANCH", "main")


load_file()


# ---- the settings kept in the Shared ioSuite database
UNREAD: dict = {}  # app -> why its settings could not be read at start (the database was away): it runs on the defaults


class Settings:
    """One app's stored settings as they were when it started: its own, else the whole suite's, else the default."""

    def __init__(self, app: str, values: dict = None):
        self.app = app
        self.mine, self.suite = _stored(app) if values is None else (dict(values), {})
        self.values = {**self.suite, **self.mine}

    def own(self, name: str, default: str = "") -> str:
        """The value stored for this app itself, never the whole suite's (its own address, beside the suite's)."""
        v = self.mine.get(name)
        return v.strip() if v is not None and v.strip() != "" else default

    def of_suite(self, name: str, default: str = "") -> str:
        """The value stored for the whole suite, whatever this app stores under the same name."""
        v = self.suite.get(name)
        return v.strip() if v is not None and v.strip() != "" else default

    def get(self, name: str, default: str = "") -> str:
        v = self.values.get(name)
        return v.strip() if v is not None and v.strip() != "" else default

    def raw(self, name: str):
        """The value as stored, None when there is none (a setting whose empty value means something)."""
        return self.values.get(name)

    def flag(self, name: str, default: bool = False) -> bool:
        return as_flag(self.values.get(name), default)

    def int(self, name: str, default: int) -> int:
        v = self.get(name)
        try:
            return int(v) if v else default
        except ValueError:
            return default


def _stored(app: str) -> tuple:
    """({the app's own settings}, {the whole suite's})."""
    from iosuite_shared import db
    try:
        db.init()
        rows = db.q("SELECT app, name, value FROM ios_settings WHERE app IN (%s, '')", (app,))
    except Exception as e:  # noqa: BLE001  the database is away: the defaults, and the host starts the copy again once it answers
        UNREAD[app] = str(e)[:200]
        print(f"{app}: the Shared ioSuite database does not answer ({str(e)[:120]}): starting on the default settings", file=sys.stderr)
        return {}, {}
    UNREAD.pop(app, None)
    return {r["name"]: r["value"] for r in rows if r["app"] == app}, {r["name"]: r["value"] for r in rows if r["app"] == ""}


def settings(app: str) -> Settings:
    """The app's stored settings, read now (once, by its config module)."""
    return Settings(app)


def suite_setting(name: str, default: str = "") -> str:
    """A setting of the whole suite, as it is now (cached a few seconds); the default while the database is away."""
    from iosuite_shared import db
    try:
        return (db.get_setting(name, "") or "").strip() or default
    except Exception:  # noqa: BLE001
        return default


def cookie_domain() -> str:
    """The domain the session cookie is shared on (no leading dot): every host under it gets the same cookie."""
    return suite_setting("COOKIE_DOMAIN").lstrip(".").lower()


# ---- the settings every app reads the same way
OF_APP: dict = {}  # app -> what standard() gave it (Auth and the host read the address and the port from here)


def standard(app: str, app_dir, stored: Settings = None) -> dict:
    """The settings every app of the suite has, for the app's config module
    (`globals().update(shared.standard("iocalendar", APP_DIR, s))`):

      APP_DIR               the app's package folder
      DATA_DIR              the stored DATA_DIR, else <the machine's DATA_DIR>/<app>: what the app writes on its own (made when missing)
      STATIC_DIR            APP_DIR/static: the web app's files, served under /static/
      LOG_FILE              the copy's one log (the machine's; None when there is none)
      HOST, PORT            where the copy listens (the machine's): its addresses, and the port of the pages
      FOLDER                the app's folder on an address the suite shares ("/calendar"; "" for the start page)
      PUBLIC_URL            the address people reach the app at: its own (PUBLIC_URL stored for it:
                            https://calendar.example.com), else its folder at the suite's (https://home.example.com/calendar);
                            empty: the one it is reached at
      PUBLIC_URLS           both of those that are set: a request is answered with links in the style it came in on
      SYNC_URL, MCP_URL     the same for the app's sync and MCP doors (iosuite_shared.doors): its own, else its folder at
                            the suite's; empty: the address asked, with that door's port
      BASE_URL              PUBLIC_URL, else http://localhost:PORT/folder (the links in MCP results)
      TLS_CERT_FILE, TLS_KEY_FILE   the machine's: HTTPS served directly instead of behind a reverse proxy
      KEEP_DELETED_DAYS     how long what was deleted is kept before it is purged for good (90)
      MCP_USER              the account `python -m <app>.mcp` (stdio) acts as
      ADMIN_USER, ADMIN_PASSWORD    the first admin account, created on a first start with no accounts"""
    from iosuite_shared import catalog
    s = stored or settings(app)
    _time_zone(s.get("TZ"))
    app_dir = Path(app_dir).resolve()
    data_dir = Path(s.own("DATA_DIR", str(DATA_DIR / app))).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    folder = "/" + catalog.FOLDERS[app] if catalog.FOLDERS.get(app) else ""
    own, shared_ = s.own("PUBLIC_URL").rstrip("/"), s.of_suite("PUBLIC_URL").rstrip("/")
    urls = [u for u in (own, shared_ + folder if shared_ else "") if u]
    public_url = urls[0] if urls else ""
    local = f"http://localhost{'' if PORT == 80 else f':{PORT}'}{folder}"
    out = {"APP_DIR": app_dir, "DATA_DIR": data_dir, "STATIC_DIR": app_dir / "static", "LOG_FILE": LOG_FILE,
           "HOST": HOST, "PORT": PORT, "FOLDER": folder, "PUBLIC_URL": public_url, "PUBLIC_URLS": urls, "OWN_URL": own,
           "BASE_URL": public_url or local,
           "TLS_CERT_FILE": TLS_CERT_FILE, "TLS_KEY_FILE": TLS_KEY_FILE,
           "KEEP_DELETED_DAYS": max(1, s.int("KEEP_DELETED_DAYS", 90)), "MCP_USER": s.get("MCP_USER"),
           "ADMIN_USER": ADMIN_USER, "ADMIN_PASSWORD": ADMIN_PASSWORD}
    for door in ("SYNC", "MCP"):  # the app's address at the other two doors (iosuite_shared.doors), the same way
        mine, whole = s.own(f"{door}_URL").rstrip("/"), s.of_suite(f"{door}_URL").rstrip("/")
        both = [u for u in (mine, whole + folder if whole else "") if u]
        out.update({f"{door}_URL": both[0] if both else "", f"{door}_URLS": both, f"{door}_URL_OWN": mine})
    OF_APP[app] = out
    return out


def _time_zone(tz: str) -> None:
    """The suite's TZ is the process's (every app of a copy shares it), unless the environment already names one: the
    apps and the libraries they use read TZ the usual way."""
    if tz and not os.environ.get("TZ"):
        os.environ["TZ"] = tz
        try:
            import time
            time.tzset()
        except AttributeError:  # not on this platform
            pass


def own_db(app: str, stored: Settings = None, default_name: str = None) -> dict:
    """The app's own MariaDB as {host, port, database, user, password}: a database of its own beside the Shared
    ioSuite database, on the same server and under the same login, named after the app unless DB_NAME is stored for it."""
    s = stored or settings(app)
    return {"host": DB_HOST, "port": DB_PORT, "database": s.get("DB_NAME", default_name or app), "user": DB_USER, "password": DB_PASSWORD}


# ---- what a person may set: Settings › Suite › Apps, and `iosuite set`
# {name, label, hint, type: text | number | switch | choice, default?, choices?}; an app's own are in its app.json ("settings")
COMMON = [
    {"name": "PUBLIC_URL", "label": "Its own address", "type": "text",
     "hint": "An address of its own (https://calendar.example.com), beside its folder at the suite's address. Empty: the folder only."},
    {"name": "SYNC_URL", "label": "Its own address for devices", "type": "text",
     "hint": "Where phones, native apps and devices reach its sync door (https://calendar-sync.example.com). Empty: the suite's, or the address asked with the sync port."},
    {"name": "MCP_URL", "label": "Its own address for MCP", "type": "text",
     "hint": "Where MCP clients reach its MCP door. Empty: the suite's, or the address asked with the MCP port."},
    {"name": "DATA_DIR", "label": "Data folder", "type": "text",
     "hint": "Where it writes on its own (files it keeps, caches). Empty: a folder named after it in the machine's data folder."},
    {"name": "DB_NAME", "label": "Database", "type": "text", "hint": "The name of its own database. Empty: the app's name."},
]
SUITE = [
    {"name": "PUBLIC_URL", "label": "The suite's address", "type": "text",
     "hint": "One address for every app (https://home.example.com): the start page answers there and each app in its folder (/calendar/). Empty: the address it is reached at."},
    {"name": "SYNC_URL", "label": "The suite's address for devices", "type": "text",
     "hint": "Where phones, native apps and devices reach the sync door (https://sync.example.com, or https://home.example.com:8443). Empty: the address asked, with the sync port."},
    {"name": "MCP_URL", "label": "The suite's address for MCP", "type": "text",
     "hint": "Where MCP clients reach the MCP door (https://mcp.example.com). Empty: the address asked, with the MCP port."},
    {"name": "COOKIE_DOMAIN", "label": "Sign-in domain", "type": "text",
     "hint": "The domain the sign-in is shared on (example.com): signed in at one app under it, signed in at all of them. Empty: each address on its own."},
    {"name": "TZ", "label": "Time zone", "type": "text", "hint": "Europe/Brussels, America/New_York… Empty: the server's own."},
    {"name": "KEEP_DELETED_DAYS", "label": "Days deleted items are kept", "type": "number", "default": "90",
     "hint": "How long the marker of a deleted item is kept for the apps that sync, before it is gone for good."},
    {"name": "MCP_USER", "label": "Account for a local MCP client", "type": "text",
     "hint": "The account `python -m <app>.mcp` (stdio) acts as."},
]


def declared(app: str = "") -> list:
    """The settings of one app ('' : the whole suite's, which every app falls back to), for the screen and the command."""
    if not app:
        return [dict(d) for d in SUITE]
    from iosuite_shared import catalog
    own = (catalog.APPS.get(app) or {}).get("settings") or []
    return [dict(d) for d in COMMON] + [dict(d) for d in own]


def known(app: str, name: str) -> dict | None:
    """The declaration of a setting an app reads: its own, a common one, or one of the suite's set for it alone."""
    for d in declared(app) + (declared("") if app else []):
        if d["name"] == name:
            return d
    return None

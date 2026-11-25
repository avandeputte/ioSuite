"""An app of the suite, declared once: what every app's access.py, auth.py, users.py and config.py wired up in the
same words is made here from the app's manifest (<app>/app.json, iosuite_shared.catalog).

An app's package says one line (<app>/__init__.py):

    from iosuite_shared import __version__, app as _app
    __getattr__ = _app.declare(__name__)

and the rest of the app, and anything else, asks the package for what it needs:

    from iotask import access, auth, users, updater     # made when first asked for, once

  auth      its iosuite_shared.fastapi.Auth: the manifest's `access` set on it (writeRole, proxyExempt, davScope), what
            the person keeps here (<app>/persondata.py: of), its part of the estate PDF (<app>/estate.py: data, file),
            and what the app hangs on it itself (<app>/hooks.py: setup(auth), for an app that has something to do when
            an account changes, or adds fields to the accounts it serves)
  access    auth.access: the markers a route declares (public, signed_in, admin...). An app with markers of its own
            keeps an access.py, which is then what `from <app> import access` gives
  users     the suite's accounts as this app sees them (iosuite_shared.users.AppUsers, with the manifest's
            access.defaultRole); an app with more to say about its accounts keeps a users.py
  updater   the copy's one (iosuite_shared.updates.copy)
  mcp_switch, mcp_enabled   its MCP switch in the Shared ioSuite database (the manifest's `mcp` says what an
            assistant may do there)
  suite_app the App itself: `prepare` (its tables and the accounts, what it does before anything else at a start
            and before a command of its command line), `limit_for` (the manifest's `bodies`), `counts` (what it has
            in its tables: <app>/db.py), its manifest

Nothing is made at import: a package that is only looked into (the installer reading a schema, a backup file read
without the suite) never reaches the Shared ioSuite database. What a name gives is kept, so every caller holds the
same object.

The app's settings stay in its config.py, which is now only what is its own: one line gives it the names every app
has (iosuite_shared.config.of_app), and the manifest's `limits` are its MAX_<NAME>_BYTES.
"""
import fnmatch
import importlib
import threading
from functools import cached_property
from pathlib import Path

from iosuite_shared import catalog

MIB = 1024 * 1024
_APPS: dict = {}
_lock = threading.RLock()
NAMES = ("auth", "access", "users", "updater", "mcp_switch", "mcp_enabled", "suite_app")


class App:
    def __init__(self, key: str, folder=None):
        self.key = key
        self.dir = Path(folder) if folder else catalog.ROOT / key
        self.manifest = catalog.APPS.get(key) or {}

    def __repr__(self) -> str:
        return f"<App {self.key}>"

    def has(self, module: str) -> bool:
        """Whether the app's package has that module (a file or a folder)."""
        return (self.dir / f"{module}.py").is_file() or (self.dir / module / "__init__.py").is_file()

    def module(self, name: str):
        return importlib.import_module(f"{self.key}.{name}")

    @cached_property
    def config(self):
        return self.module("config")

    @cached_property
    def auth(self):
        from iosuite_shared import __version__, apppasswords
        from iosuite_shared.fastapi import Auth
        config = self.config  # read first: its addresses are what the suite's list of apps gets
        a = Auth(self.key, version=__version__, public_url=config.PUBLIC_URL or None)
        said = self.manifest.get("access") or {}
        if said.get("writeRole"):
            a.write_role = said["writeRole"]
        if "proxyExempt" in said:
            a.deny_exempt = tuple(said["proxyExempt"])
        if "davScope" in said:
            a.scope_paths = {apppasswords.DAV: tuple(said["davScope"])}
        if self.has("persondata"):
            a.person_data = lambda user_id, remove: self.module("persondata").of(user_id, remove)
        if self.has("estate"):
            estate = self.module("estate")  # its signature says whether it wants to know who asks (iosuite_shared.estate)
            a.estate_data = estate.data
            if hasattr(estate, "file"):
                a.estate_file = estate.file
        if self.has("hooks"):
            self.module("hooks").setup(a)
        return a

    @cached_property
    def access(self):
        return self.auth.access

    @cached_property
    def users(self):
        from iosuite_shared.users import AppUsers
        return AppUsers(self.key, default_role=(self.manifest.get("access") or {}).get("defaultRole"))

    @property
    def updater(self):
        from iosuite_shared import updates
        return updates.copy()

    @cached_property
    def mcp_switch(self):
        from iosuite_shared import mcp
        return mcp.Switch(self.key, self.manifest.get("mcp") or "")

    @property
    def mcp_enabled(self):
        return self.mcp_switch.enabled

    @property
    def suite_app(self):
        return self

    @cached_property
    def counts(self):
        """What the app has in its tables, by name (<app>/db.py: counts), or None where it says nothing. One place
        for `iosuite <app> check` and the app's diagnostics tool to read them from."""
        return getattr(self.module("db"), "counts", None) if self.has("db") else None

    # ---- what the app does before anything else
    @cached_property
    def prepare(self) -> tuple:
        """Its tables (<app>/db.py: migrate, or init) and the suite's accounts, in that order."""
        steps = []
        if self.has("db"):
            db = self.module("db")
            steps.append(getattr(db, "migrate", None) or db.init)
        users = self.module("users") if self.has("users") else self.users
        steps.append(users.init)
        return tuple(steps)

    # ---- how large a request body may be
    def limits(self, stored=None) -> dict:
        """The manifest's `limits` in bytes, by name: {"json": 2, "file": {"setting": "MAX_FILE_MB", "default": 100}}
        are MiB, the second read from the app's stored settings."""
        out = {}
        for name, v in (self.manifest.get("limits") or {}).items():
            if isinstance(v, dict):
                v = stored.int(v["setting"], int(v["default"])) if stored is not None else v["default"]
            out[name] = int(float(v) * MIB)
        return out

    def limit_for(self, path: str, ctype: str) -> int:
        """What the body cap lets through for a request (iosuite_shared.access.BodyCap): the first of the manifest's
        `bodies` whose `path` and `type` (shell patterns; either may be left out) fit names the limit, else `json`."""
        for rule in self.manifest.get("bodies") or ():
            if fnmatch.fnmatchcase(path, rule.get("path", "*")) and fnmatch.fnmatchcase(ctype, rule.get("type", "*")):
                return getattr(self.config, limit_name(rule["limit"]))
        return self.config.MAX_JSON_BYTES


def limit_name(name: str) -> str:
    return f"MAX_{name.upper()}_BYTES"


def of(key: str) -> App:
    """The App of that key, the same one for everyone who asks."""
    with _lock:
        if key not in _APPS:
            _APPS[key] = App(key)
        return _APPS[key]


def declare(package: str):
    """The module-level __getattr__ of an app's package: NAMES, each made when first asked for. A name the package has
    a module for (an access.py of its own) is that module's, so this never answers for it."""
    key = package.split(".")[0]

    def __getattr__(name: str):
        if name in NAMES:
            app = of(key)
            if not app.has(name):
                with _lock:
                    return getattr(app, name)
        raise AttributeError(f"module {package!r} has no attribute {name!r}")
    return __getattr__

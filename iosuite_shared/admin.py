"""Suite administration: everything in the Shared ioSuite database, seen and changed from one place by a suite admin.

Accounts (with their role in every app), app passwords of every account in every app, sessions, the keys and tokens
every app keeps (iosuite_shared.credentials; never their values), and the suite's apps with the per-app access settings
(default_role, require_login: on unless turned off, always on in an admin tool), the settings the apps read as they
start, their addresses door by door, and the log of every copy on one timeline. `Auth.admin_router()` serves it at
/api/suite-admin/* (suite admins only); every app's Settings › People, Apps, Servers and Keys are its screen.

The apps are the registered ones (ios_apps) plus any app key that only shows up in roles, settings or app passwords
(an app that is not installed any more, or has not started since the registry came in).
"""
import re
import time

from iosuite_shared import apppasswords, config, credentials, db, passkeys, sessions, suite, twostep, users
from iosuite_shared.errors import Invalid

APP_KEY = re.compile(r"^[a-z0-9_-]{1,32}$")
DEFAULT_ROLES = ("none", "viewer", "member", "editor")  # what an app gives an account without a role there ("admin" by default is never wanted)
PHOTO_APP = "iopix"  # the app whose People an account can be linked to: the person in photos, its face the account's picture


def clean_app(app) -> str:
    app = str(app or "").strip().lower()
    if not APP_KEY.match(app) or app.startswith("_"):
        raise Invalid("Unknown app")
    return app


def _forget_caches():
    users.invalidate()
    sessions.invalidate()
    apppasswords.forget()
    from iosuite_shared import proxyauth
    proxyauth.forget_identities()


# ---- apps
def apps() -> list:
    """Every app the database knows: the registry's fields (registered: False for one known only from its data), its
    defaultRole and requireLogin, and how many explicit roles and app passwords it has."""
    reg = {a["app"]: a for a in suite.apps()}
    keys = set(reg)
    for sql in ("SELECT DISTINCT app FROM ios_user_roles", "SELECT DISTINCT app FROM ios_app_passwords",
                "SELECT DISTINCT app FROM ios_settings WHERE app != '' AND LEFT(app, 1) != '_'", "SELECT DISTINCT app FROM ios_credentials WHERE app != ''"):
        keys |= {r["app"] for r in db.q(sql)}
    roles = {r["app"]: r["n"] for r in db.q("SELECT app, count(*) AS n FROM ios_user_roles GROUP BY app")}
    pws = {r["app"]: r["n"] for r in db.q("SELECT app, count(*) AS n FROM ios_app_passwords GROUP BY app")}
    creds = {r["app"]: r["n"] for r in db.q("SELECT app, count(*) AS n FROM ios_credentials WHERE name NOT LIKE 'link\\_%' GROUP BY app")}
    from iosuite_shared import mcp as shared_mcp
    mcp_switches = shared_mcp.switches()          # {app: on} as stored ("" : the suite's switch)
    suite_mcp = mcp_switches.pop("", False)
    out = []
    for k in keys:
        a = dict(reg.get(k) or {"app": k, "name": k, "description": None, "version": None, "color": None, "icon": None, "url": None,
                                "lastSeen": None})
        a["registered"] = k in reg
        a["defaultRole"] = users.default_role(k)  # none in an admin tool, which is for suite admins only
        a["requireLogin"] = users.sign_in_required(k)  # always in an admin tool
        a["roles"], a["appPasswords"], a["credentials"] = roles.get(k, 0), pws.get(k, 0), creds.get(k, 0)
        a["mcp"] = mcp_switches.get(k)      # None: it follows the suite's switch
        a["mcpOn"] = mcp_switches.get(k, suite_mcp)
        out.append(a)
    return sorted(out, key=lambda a: (not a["registered"], (a["name"] or a["app"]).lower(), a["app"]))


def set_app(app: str, default_role=None, require_login=None, mcp="keep") -> dict:
    """Change an app's access settings (None: unchanged). mcp: True/False for its MCP server, None to follow the
    suite's switch, "keep" to leave it as it is."""
    app = clean_app(app)
    if mcp != "keep":
        from iosuite_shared import mcp as shared_mcp
        shared_mcp.set_for(app, mcp)
    if default_role is not None:
        if suite.is_admin_tool(app):
            raise Invalid("An admin tool is for suite admins only; it has no default role")
        if default_role not in DEFAULT_ROLES:
            raise Invalid("The default role is none, viewer, member or editor")
        db.set_setting("default_role", "" if default_role == users.DEFAULT_ROLE else default_role, app)  # member is the default: no row
    if require_login is not None:
        if not require_login and suite.is_admin_tool(app):
            raise Invalid("An admin tool always requires sign-in")
        db.set_setting("require_login", "" if require_login else "0", app)  # on is the default: no row
    _forget_caches()
    return next((a for a in apps() if a["app"] == app), {"app": app})


def forget_app(app: str, data: bool = False) -> bool:
    """Take an app off the registry; with data, also its roles, its access settings, its app passwords and its keys and
    tokens (an app that was uninstalled for good). It registers again if it starts."""
    app = clean_app(app)
    gone = suite.forget(app)
    db.ex("DELETE FROM ios_updates WHERE app = %s", (app,))  # what it said about its version; it writes it again if it starts
    if data:
        for pid, uid in [(r["id"], r["user_id"]) for r in db.q("SELECT id, user_id FROM ios_app_passwords WHERE app = %s", (app,))]:
            apppasswords.delete(uid, pid)
        gone = (db.ex("DELETE FROM ios_user_roles WHERE app = %s", (app,)) > 0) or gone
        gone = (db.ex("DELETE FROM ios_settings WHERE app = %s", (app,)) > 0) or gone
        gone = (credentials.remove(app) > 0) or gone
        _forget_caches()
    return gone


# ---- accounts
def accounts() -> list:
    """Every account people use (never the apps' own service accounts, which the suite manages itself): the shared fields, `roles` (the explicit role per app), `effective` (the role it holds in every
    known app: the row, else the app's default; suite admin: admin; admin tool: none for the others; passwordless: member
    at most), its number of app
    passwords and sessions, and when it was last seen in any session."""
    keys = [a["app"] for a in apps()]
    pw = {r["user_id"]: r["n"] for r in db.q("SELECT user_id, count(*) AS n FROM ios_app_passwords GROUP BY user_id")}
    now = int(time.time())
    ses = {r["user_id"]: r for r in db.q("SELECT user_id, count(*) AS n, max(coalesce(last_seen_at, renewed_at)) AS seen "
                                         "FROM ios_sessions WHERE expires_at > %s GROUP BY user_id", (now,))}
    roles = {}
    for r in db.q("SELECT user_id, app, role FROM ios_user_roles"):
        roles.setdefault(r["user_id"], {})[r["app"]] = r["role"]
    defaults = {k: users.default_role(k) for k in keys}
    tools = suite.admin_tools()
    photo = {r["user_id"]: db.json_load(r["value"]) for r in db.q(
        "SELECT user_id, value FROM ios_user_data WHERE app = %s AND name = 'person'", (PHOTO_APP,))}
    two, keys_of = twostep.counts(), passkeys.counts()
    out = []
    for u in users.list_users():
        mine = roles.get(u["id"], {})
        eff = {}
        for k in keys:
            eff[k] = users.effective(mine.get(k, defaults[k]), u["suiteAdmin"], u["passwordless"], k in tools)
        s = ses.get(u["id"]) or {}
        out.append({**u, "roles": mine, "effective": eff, "appPasswords": pw.get(u["id"], 0), "sessions": int(s.get("n") or 0),
                    "lastSeen": s.get("seen"), "photoPerson": photo.get(u["id"]), "twoStep": u["id"] in two, "passkeys": keys_of.get(u["id"], 0)})
    return sorted(out, key=lambda u: u["name"].lower())


def person(user_id: int) -> dict | None:
    """The account, when it is one people use; None for no account or an app's own service account (users.service_account),
    which the suite makes and looks after itself, so this panel never shows or changes it."""
    u = users.get(user_id)
    return u if u and not u.get("service") else None


def account(user_id: int) -> dict | None:
    return next((u for u in accounts() if u["id"] == user_id), None)


def set_roles(me, user_id: int, roles: dict):
    """{app: role | None}: None (or "default") removes the row, so the app's default role applies."""
    if not isinstance(roles, dict):
        raise Invalid("roles is {app: role}")
    for app, role in roles.items():
        app = clean_app(app)
        if role in (None, "", "default"):
            db.ex("DELETE FROM ios_user_roles WHERE user_id = %s AND app = %s", (user_id, app))
        elif suite.is_admin_tool(app):
            raise Invalid(f"{(suite.get(app) or {}).get('name') or app} is an admin tool, for suite admins only")
        else:
            users.update(user_id, role=str(role), app=app)  # the checks: a known role, a password for more than member


def create(me, body: dict) -> dict:
    roles = body.get("roles") or {}
    u = users.create(str(body.get("name", ""))[:64], str(body.get("password") or "")[:1024], email=str(body.get("email") or ""),
                     display_name=str(body.get("displayName") or ""), suite_admin=bool(body.get("suiteAdmin")))
    try:
        if body.get("listed") is not None:
            users.update(u["id"], listed=bool(body["listed"]))
        set_roles(me, u["id"], roles)
        if body.get("photoPerson"):
            set_photo_person(u["id"], body["photoPerson"])
    except ValueError:
        users.delete(u["id"])
        raise
    _forget_caches()
    return account(u["id"])


def update(me, user_id: int, body: dict) -> dict:
    """Change an account: name, displayName, email, listed, suiteAdmin, password ('' removes it: one-click, member at most),
    roles {app: role | None}, photoPerson (the person in ioPix's People, a tag id; None unlinks), resetSignIn (true:
    two-step sign-in off and the passkeys removed, for someone who lost their phone; the password is what is left)."""
    if not person(user_id):
        raise LookupError("No such user")
    own = bool(me) and me.get("id") == user_id
    if own and body.get("suiteAdmin") is False:
        raise Invalid("You cannot take away your own suite admin while signed in; another suite admin can")
    if own and body.get("password") == "":
        raise Invalid("You cannot remove your own password")
    pw = body.get("password")
    users.update(user_id, name=body.get("name"), email=body.get("email"), display_name=body.get("displayName"),
                 listed=None if body.get("listed") is None else bool(body["listed"]),
                 suite_admin=None if body.get("suiteAdmin") is None else bool(body["suiteAdmin"]),
                 password=None if pw is None else str(pw)[:1024])
    if body.get("roles") is not None:
        set_roles(me, user_id, body["roles"])
    if "photoPerson" in body:
        set_photo_person(user_id, body["photoPerson"])
    if body.get("resetSignIn"):
        reset_sign_in(user_id)
    _forget_caches()
    return account(user_id)


def reset_sign_in(user_id: int):
    """Two-step sign-in off and every passkey removed: the account signs in with its password alone again."""
    twostep.disable(user_id)
    passkeys.remove_all(user_id)


# ---- the person in photos: an account linked to someone in ioPix's People. Kept here, as ioPix's "person" value of
# the account (ios_user_data); ioPix shows that face on its sign-in screen and menu, and "Photos of me".
def set_photo_person(user_id: int, person):
    if person in (None, "", 0):
        users.set_value(user_id, PHOTO_APP, "person", None)
        return
    try:
        person = int(person)
    except (TypeError, ValueError):
        raise Invalid("photoPerson is a person id from ioPix's People")
    users.set_value(user_id, PHOTO_APP, "person", person)


def photo_people(reader: str) -> dict:
    """The people in ioPix's People, read from ioPix as the reader (iosuite_shared.links):
    {available, people: [{id, name, photos}], error?}. Not available while ioPix is not in the suite."""
    from iosuite_shared import links
    if not links.available(PHOTO_APP):
        return {"available": False, "people": []}
    try:
        r = links.json(reader, PHOTO_APP, "/api/people/list")
    except Exception as e:  # noqa: BLE001  ioPix is away, or older than its /api/people/list
        return {"available": True, "people": [], "error": f"ioPix did not answer: {e}"}
    return {"available": True, "people": [p for p in (r.get("people") if isinstance(r, dict) else r) or [] if isinstance(p, dict)]}


def photo_face(reader: str, person: int) -> bytes:
    """The face ioPix shows for a person (a JPEG). LookupError when there is none."""
    from iosuite_shared import links
    import urllib.error
    try:
        with links.get(reader, PHOTO_APP, f"/face/{int(person)}", accept="image/jpeg") as r:
            return r.read()
    except (RuntimeError, urllib.error.URLError, OSError) as e:
        raise LookupError(f"No face: {e}")


def check_delete(me, user_id: int):
    """Raises when the account cannot be deleted (before anything of the person's goes: persondata.delete_account)."""
    if not person(user_id):
        raise LookupError("No such user")
    if me and me.get("id") == user_id:
        raise Invalid("You cannot delete your own account while signed in")
    users.check_delete(user_id)


def delete(me, user_id: int):
    """The account alone, with what the Shared ioSuite database keeps for it; the panel deletes it with the person's
    data in every app (persondata.delete_account)."""
    check_delete(me, user_id)
    users.delete(user_id)
    _forget_caches()


# ---- app passwords
# What people's app passwords can be: everything, or sync only. READ is the service accounts' own (iosuite_shared.links).
PERSON_SCOPES = ("", apppasswords.DAV)


def app_passwords(user_id: int = None, app: str = None) -> list:
    """Every app password of the accounts people use (never the secret; the service accounts' own are left out): id, userId, userName, app, appName, label, scope ('' everything, 'dav' sync only), created, lastUsed."""
    where, args = ["u.service IS NULL"], []
    if user_id is not None:
        where.append("p.user_id = %s"); args.append(user_id)
    if app:
        where.append("p.app = %s"); args.append(clean_app(app))
    rows = db.q("SELECT p.id, p.user_id, p.app, p.label, p.scope, p.created_at, p.last_used_at, u.name, u.display_name, a.name AS app_name "
                "FROM ios_app_passwords p JOIN ios_users u ON u.id = p.user_id LEFT JOIN ios_apps a ON a.app = p.app"
                + " WHERE " + " AND ".join(where) + " ORDER BY lower(u.name), p.app, p.created_at", tuple(args))
    return [{"id": r["id"], "userId": r["user_id"], "userName": r["name"], "displayName": r["display_name"] or r["name"], "app": r["app"],
             "appName": r["app_name"] or r["app"], "label": r["label"], "scope": r["scope"] or "", "created": r["created_at"], "lastUsed": r["last_used_at"]} for r in rows]


def new_app_password(user_id: int, app: str, label: str, scope: str = "") -> dict:
    """A new app password for an account in an app (shown once)."""
    u = person(user_id)
    if not u:
        raise LookupError("No such user")
    if scope not in PERSON_SCOPES:
        raise Invalid(f"Unknown app password scope: {scope!r}")
    if u["passwordless"]:
        raise Invalid("A one-click account cannot have app passwords; give it a password first")
    app = clean_app(app)
    pw = apppasswords.create(user_id, app, (label or "Device").strip()[:128] or "Device", scope or "")
    return {"password": pw, "name": u["name"], "app": app, "scope": scope or ""}


def set_app_password_scope(pid: int, scope: str):
    """Change what an app password reaches: '' everything, 'dav' the app's sync protocols only."""
    r = db.one("SELECT p.app, p.prefix FROM ios_app_passwords p JOIN ios_users u ON u.id = p.user_id WHERE p.id = %s AND u.service IS NULL", (pid,))
    if not r:
        raise LookupError("No such app password")
    if (scope or "") not in PERSON_SCOPES:
        raise Invalid(f"Unknown app password scope: {scope!r}")
    apppasswords.set_scope(r["app"], r["prefix"], scope or "")
    apppasswords.forget()


def revoke_app_password(pid: int):
    r = db.one("SELECT p.user_id FROM ios_app_passwords p JOIN ios_users u ON u.id = p.user_id WHERE p.id = %s AND u.service IS NULL", (pid,))
    if not r:
        raise LookupError("No such app password")
    apppasswords.delete(r["user_id"], pid)


# ---- keys and tokens
SUITE = "_suite"  # the whole suite's keys (app '') in the addresses: /api/suite-admin/keys/_suite/<name>


def _suite_keys():
    from iosuite_shared import certs, links
    credentials.declare("", [*links.SUITE_KEYS, *certs.KEYS])  # the whole suite's: listed before any app needed them


def _key_app(app) -> str:
    return "" if app in ("", SUITE) else clean_app(app)


def keys(app: str = None) -> list:
    """Every key and token the apps keep (never the value): see credentials.listing. The whole suite's have app ''."""
    _suite_keys()
    return credentials.listing(None if app is None else _key_app(app))


def set_key(me, app: str, name: str, value) -> dict:
    """Replace a key's value ('' or None clears it). Only keys an app declared can be set here (not the app
    passwords iosuite_shared.links keeps: revoke those as app passwords)."""
    app, name = _key_app(app), str(name or "")
    _suite_keys()
    if name.startswith(("link_", "made_")) or not db.one("SELECT 1 AS x FROM ios_credentials WHERE app = %s AND name = %s", (app, name)):
        raise LookupError("No such key")
    if value is not None and not isinstance(value, str):
        raise Invalid("The value is text")
    credentials.put(app, name, value, by=(me or {}).get("name"))
    return next(k for k in credentials.listing(app) if k["name"] == name)


# ---- sessions
def end_sessions(user_id: int, session_id: str = None):
    if not person(user_id):
        raise LookupError("No such user")
    if session_id:
        sessions.end_one(user_id, session_id)
    else:
        sessions.end_all(user_id)


# ---- addresses: where every app answers, door by door (iosuite_shared.doors)
DOOR_SETTING = {"web": "PUBLIC_URL", "sync": "SYNC_URL", "mcp": "MCP_URL"}


def addresses() -> dict:
    """{suite: {web, sync, mcp}, ports: {web, sync, mcp}, https, apps: [{app, name, folder, copy, internal, web, sync, mcp}]}:
    the suite's own address at each door (None: the address asked, with that door's port), this copy's ports (https:
    the ports it answers HTTPS at, None while it serves no certificate), and for every app the addresses it has at
    each door: its own (a hostname of its own) and its folder at the suite's."""
    stored = db.settings_of("")
    whole = {d: (stored.get(k) or "").strip().rstrip("/") or None for d, k in DOOR_SETTING.items()}
    out = []
    for a in suite.apps():
        folder = suite.folder_of(a["app"]) or ""
        own = {"web": a.get("configuredUrl"), "sync": a.get("syncUrl"), "mcp": a.get("mcpUrl")}
        row = {"app": a["app"], "name": a["name"], "folder": folder, "copy": a.get("copy"), "internal": a.get("internalUrl")}
        for d in DOOR_SETTING:
            both = [(own[d] or "").rstrip("/"), f"{whole[d]}/{folder}".rstrip("/") if whole[d] else ""]
            row[d] = [u + ("/mcp" if d == "mcp" else "") for u in both if u]
        out.append(row)
    from iosuite_shared import certs
    return {"suite": whole, "ports": {"web": config.PORT, "sync": config.SYNC_PORT, "mcp": config.MCP_PORT}, "copy": suite.copy_name(),
            "https": {"web": certs.PAGES_PORT, "sync": config.SYNC_PORT, "mcp": config.MCP_PORT} if certs.serving() else None,
            "apps": sorted(out, key=lambda r: (r["name"] or r["app"]).lower())}


# ---- settings: what the apps read as they start (iosuite_shared.config), kept in ios_settings
ADDRESS = re.compile(r"^https?://[^\s/?#]+(/[^\s?#]*)?$", re.I)


def _with_value(d: dict, mine: dict, whole: dict = None) -> dict:
    out = dict(d)
    out["value"] = mine.get(d["name"]) or ""
    if whole is not None and whole.get(d["name"]):
        out["suite"] = whole[d["name"]]  # what it falls back to while it has none of its own
    return out


def settings() -> dict:
    """{suite: [setting], apps: [{app, name, copy, settings: [setting]}]}: every setting a person may set, with the
    value stored now ('' : none, the default applies). setting: {name, label, hint, type, default?, choices?, value,
    suite? (the whole suite's value an app without its own falls back to)}."""
    from iosuite_shared import catalog
    whole = db.settings_of("")
    names = {d["name"] for d in config.declared("")}
    out = []
    for a in suite.apps():
        if a["app"] not in catalog.APPS:
            continue
        mine = db.settings_of(a["app"])
        out.append({"app": a["app"], "name": a["name"], "copy": a.get("copy"),
                    "settings": [_with_value(d, mine, whole if d["name"] in names and d["name"] not in DOOR_SETTING.values() else None)
                                 for d in config.declared(a["app"])]})
    return {"suite": [_with_value(d, whole) for d in config.declared("")],
            "apps": sorted(out, key=lambda r: (r["name"] or r["app"]).lower())}


def clean_setting(app: str, d: dict, value) -> str:
    """The value as it is stored ('' : none), or Invalid saying what it has to be."""
    v = str(value if value is not None else "").strip()
    if v == "":
        return ""
    kind = d.get("type") or "text"
    if isinstance(value, bool) or kind == "switch":
        if isinstance(value, bool):
            return "1" if value else "0"
        if v.lower() not in config.FLAG_ON + config.FLAG_OFF:
            raise Invalid(f"{d['name']} is on or off")
        return "1" if config.as_flag(v) else "0"
    if kind == "number":
        try:
            int(v)
        except ValueError:
            raise Invalid(f"{d['name']} is a whole number")
    if kind == "choice" and v not in [c[0] if isinstance(c, (list, tuple)) else c for c in d.get("choices") or []]:
        raise Invalid(f"{d['name']} is one of: " + ", ".join(str(c[0] if isinstance(c, (list, tuple)) else c) for c in d.get("choices") or []))
    if d["name"] in DOOR_SETTING.values():
        v = v.rstrip("/")
        m = ADDRESS.match(v)
        if not m:
            raise Invalid(f"{d['name']} is an address: https://name.example.com")
        if app and m.group(1):
            raise Invalid(f"An app's own address has no folder ({v}): the folders are at the suite's address")
    if d["name"] == "COOKIE_DOMAIN":
        v = v.lstrip(".").lower()
    if len(v) > 2000:
        raise Invalid("Too long")
    return v


def set_setting(app: str, name: str, value) -> dict:
    """Store one setting for an app ('' : the whole suite), or with '' / None remove it so the default applies again.
    Only settings the app declares (iosuite_shared.config.declared). It takes effect when the app starts again."""
    from iosuite_shared import catalog
    app = "" if app in ("", SUITE) else clean_app(app)
    if app and app not in catalog.APPS:
        raise LookupError("No such app")
    name = str(name or "").strip()
    d = config.known(app, name) if app else next((x for x in config.declared("") if x["name"] == name), None)
    if not d:
        raise LookupError(f"No such setting: {name}")
    v = clean_setting(app, d, value)
    db.set_setting(name, v, app)
    suite.invalidate()
    return {"app": app, "name": name, "value": v}


# ---- the log: every copy's one log, on one timeline (iosuite_shared.logs)
LOG_PATH = "/api/suite-admin/logs"
LOG_ASK_S = 6


def log_copies() -> dict:
    """{copy name: [app keys]} of the copies of the suite other than this one, from the list of apps."""
    here, out = suite.copy_name(), {}
    for a in suite.apps():
        c = a.get("copy")
        if c and c != here:
            out.setdefault(c, []).append(a["app"])
    return out


def _marked(got: dict) -> list:
    """A copy's lines, each with its copy; a line without a time (the piece began inside a record) takes its neighbour's."""
    lines = got.get("lines") or []
    for i, r in enumerate(lines):
        r["copy"] = got.get("copy")
        if not r.get("ts"):
            r["ts"] = next((x["ts"] for x in lines[i + 1:] if x.get("ts")), 0.0) or (lines[i - 1]["ts"] if i else 0.0)
    return lines


def logs(request=None, after: dict = None, limit: int = 300, **filters) -> dict:
    """The suite's log, oldest first: this copy's lines and those of every other copy (asked with the viewer's own
    sign-in at an app that copy runs), merged by time:
        {here, lines: [{ts, time, level, app, logger, text, copy}], cursors: {copy: cursor}, more,
         copies: [{copy, apps, file, size, reachable, note}], apps: [{app, name}]}
    filters: app, level, contains, requests, since, until (iosuite_shared.logs.read). `after`: the cursors of an
    earlier answer: only what was written since. A copy that does not answer is in copies with reachable False."""
    from concurrent.futures import ThreadPoolExecutor
    from iosuite_shared import catalog, links, logs as log
    after = after if isinstance(after, dict) else {}
    limit = max(1, min(int(limit or 300), 5000))
    mine = log.read(limit=limit, after=str(after.get(suite.copy_name()) or ""), **filters)
    registered = {a["app"]: a for a in suite.apps()}
    local = [k for k, a in registered.items() if a.get("copy") in (None, mine["copy"])]
    copies = [{"copy": mine["copy"], "apps": sorted(local), "file": mine["file"], "size": mine["size"], "reachable": True, "note": mine.get("note")}]
    lines, cursors, more = _marked(mine), {mine["copy"]: mine["cursor"]}, mine["more"]
    others = log_copies()

    def ask(item):
        copy, apps = item
        params = {k: v for k, v in {**filters, "limit": limit, "local": 1, "after": after.get(copy) or ""}.items() if v not in (None, "", False)}
        if params.get("requests") is True:
            params["requests"] = 1
        why = None
        for k in apps:  # any app of that copy answers for its log
            try:
                return copy, apps, links.as_viewer(request, k, LOG_PATH, params=params, timeout=LOG_ASK_S, patient=True), None
            except Exception as e:  # noqa: BLE001
                why = e
        return copy, apps, None, why

    if others:
        with ThreadPoolExecutor(max_workers=min(8, len(others))) as pool:
            for copy, apps, got, why in pool.map(ask, sorted(others.items())):
                if got is None or not isinstance(got, dict):
                    copies.append({"copy": copy, "apps": sorted(apps), "file": "", "size": 0, "reachable": False,
                                   "note": f"did not answer ({type(why).__name__ if why else 'no answer'})"})
                    if after.get(copy):
                        cursors[copy] = after[copy]
                    continue
                got["copy"] = copy
                copies.append({"copy": copy, "apps": sorted(apps), "file": got.get("file") or "", "size": got.get("size") or 0,
                               "reachable": True, "note": got.get("note")})
                lines += _marked(got)
                cursors[copy] = got.get("cursor") or ""
                more = more or bool(got.get("more"))
        lines.sort(key=lambda r: r["ts"])  # stable: a copy's own lines keep their order
        if len(lines) > limit and not after:
            lines, more = lines[-limit:], True
    names = [{"app": k, "name": (registered.get(k) or {}).get("name") or v.get("name") or k} for k, v in catalog.APPS.items() if k in registered]
    return {"here": mine["copy"], "lines": lines, "cursors": cursors, "more": more, "copies": copies,
            "apps": sorted(names, key=lambda a: a["name"].lower())}


def overview() -> dict:
    from iosuite_shared import mcp as shared_mcp
    return {"apps": apps(), "users": accounts(), "roles": list(users.ROLES), "defaultRoles": list(DEFAULT_ROLES),
            "scopes": list(PERSON_SCOPES), "mcpSuite": shared_mcp.switches().get("", False)}

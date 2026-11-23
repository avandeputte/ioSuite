"""Who made or changed an item, with what, and from where: the record kept for every item of the suite.

Each item (an event, a task, a contact, a note, a recipe, a thing, a document, a transaction, a house or a car, a
photo: the kinds of the apps' manifests) gets two things in the Shared ioSuite database:

    ios_item_stamps    one row per item: who added it and when, through what, and who changed it last
    ios_item_changes   its history: one row per change (added, changed, deleted), the last KEEP of each item, for
                       DAYS days, with the address the change came from

"Who" is the account. "With what" is the client, told from the door and the path the request came in by and from
what the client says it is:

    web      the pages, in a browser ("Safari on Mac")
    app      a native app or a widget on the device door (its User-Agent names it: "ioStart app")
    dav      CalDAV or CardDAV (a phone's Calendar, Reminders or Contacts, Thunderbird, DAVx5)
    mcp      an MCP client (Claude, say)
    api      anything else signed in with an app password (a script, curl)
    import   a file read in (Homebox CSV, a bank statement)
    sync     the app fetching from outside (Monarch, a subscribed calendar)
    auto     the app itself (a rule, a recurring bill, the demo data, another app's service account)

"From where" is what can honestly be known: the app password's name when one signed the request in ("iPhone
calendar"), else the browser or the device; and the address, with whether it came through Cloudflare. When another
app of the suite asks on the person's behalf (the start page's quick add, the suite's one MCP server, the wall
display), it says so in X-IoSuite-On-Behalf (links.viewer_headers), and the record names the start page as well as
the person's own client; that header is believed only from inside the network.

Auth.resolve() calls begin() for every request, which puts the stamp in a context variable; an app's code that
writes an item calls touch() (or touch_many()) after the write, and nothing else. Work that is nobody's request (a
sync, an import from the command line, the demo data) runs inside job(). touch() never raises: an item is saved
whether or not its record could be.

Who may read the record is who may see the item: router() asks the item's own app for it as the viewer (the same
way the "Linked" panel does: iosuite_shared.related.get) and answers 404 otherwise, admins included. The address is
shown only to the person who made the change and to suite admins; everyone else sees "at home" or "away from home".
"""
from __future__ import annotations

import contextvars
import functools
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace

from iosuite_shared import catalog, db

log = logging.getLogger("iosuite_shared.stamp")

KEEP = 20            # changes kept per item
DAYS = 90            # and for how long
HEADER = "X-IoSuite-On-Behalf"
CLIENTS = ("web", "app", "dav", "mcp", "api", "import", "sync", "auto")
_PURGE_S = 3600
_purged = {"at": 0.0}
_lock = threading.Lock()


@dataclass(frozen=True)
class Stamp:
    """Who acts, with what (client: one of CLIENTS), where (the app password's name, the browser, the job), from which
    address (ip, cloudflare: it came through Cloudflare, outside: from outside the network), and through which other
    app of the suite (via: "iostart" for the start page's quick add)."""
    user_id: int | None = None
    name: str = ""
    client: str = "auto"
    where: str = ""
    ip: str = ""
    cloudflare: bool = False
    outside: bool = False
    via: str = ""


CURRENT: contextvars.ContextVar[Stamp | None] = contextvars.ContextVar("iosuite_stamp", default=None)


def current() -> Stamp | None:
    return CURRENT.get()


# ------------------------------------------------------------------ the stamp of a request

_BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Vivaldi", "Vivaldi"), ("Firefox/", "Firefox"), ("FxiOS", "Firefox"),
             ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
_SYSTEMS = (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Mac OS X", "Mac"), ("Macintosh", "Mac"),
            ("Windows", "Windows"), ("CrOS", "ChromeOS"), ("Linux", "Linux"))


def device(user_agent: str) -> str:
    """'Safari on iPhone', 'Firefox on Windows', or '' when the User-Agent does not say."""
    ua = user_agent or ""
    b = next((n for k, n in _BROWSERS if k in ua), "")
    s = next((n for k, n in _SYSTEMS if k in ua), "")
    return f"{b} on {s}" if b and s else b or s


def _product(token: str) -> str:
    """A native app's name from its User-Agent's product token ('iostart' → 'ioStart app')."""
    token = (token or "").strip().lower()
    if token in catalog.APPS:
        return f"{catalog.name_of(token)} app"
    return token[:40]


def _native(origin: dict) -> bool:
    """A native app or a widget: one of the suite's own apps by name, or an app on Apple's or Android's HTTP stack.
    A script (curl, Python) is not one: it counts as 'api'."""
    ua, token = origin.get("user_agent") or "", str(origin.get("client") or "")
    return token in catalog.APPS or any(k in ua for k in ("CFNetwork", "Darwin/", "okhttp", "Dalvik"))


def _on_behalf(request, trusted: bool) -> dict | None:
    """What another app of the suite said about the person it asks for (X-IoSuite-On-Behalf), from inside only."""
    raw = request.headers.get(HEADER.lower())
    if not raw or not trusted:
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(d, dict) or str(d.get("app") or "") not in catalog.APPS:
        return None
    return d


def of_request(request, user: dict | None, outside: bool) -> Stamp:
    """The stamp of a request that is signed in as user (None: nobody yet)."""
    from iosuite_shared import doors
    door = doors.of(request)
    path = request.url.path
    origin = getattr(request.state, "origin", None) or {}
    ip, cf = str(origin.get("ip") or "")[:64], bool(origin.get("cloudflare"))
    ap = (user or {}).get("app_password") or {}
    trusted = bool(request.scope.get("iosuite.inside")) or not outside
    behalf = _on_behalf(request, trusted)
    uid = (user or {}).get("id")
    name = (user or {}).get("displayName") or (user or {}).get("name") or ""
    if (user or {}).get("service"):  # another app's own account (links' service accounts): the app itself
        app = str(user["service"])
        return Stamp(None, catalog.name_of(app) if app in catalog.APPS else app, "auto", "", ip, cf, outside, app if app in catalog.APPS else "")
    if behalf:
        return Stamp(uid, name, str(behalf.get("client") or "web") if behalf.get("client") in CLIENTS else "web",
                      str(behalf.get("where") or "")[:191], str(behalf.get("ip") or "")[:64], bool(behalf.get("cloudflare")),
                      bool(behalf.get("outside")), str(behalf["app"]))
    if door == doors.MCP or path == "/mcp" or path.startswith("/mcp/"):
        client, where = "mcp", ap.get("label") or ""
    elif path.startswith(("/dav", "/.well-known/")):
        client, where = "dav", ap.get("label") or device(origin.get("user_agent") or "")
    elif origin.get("client") == "web":
        client, where = "web", device(origin.get("user_agent") or "")
    elif _native(origin):
        client, where = "app", ap.get("label") or _product(origin.get("client"))
    else:
        client, where = "api", ap.get("label") or ""
    return Stamp(uid, name, client, str(where)[:191], ip, cf, outside, "")


def begin(request, user: dict | None, outside: bool) -> None:
    """Auth.resolve(): the stamp of this request, for touch() to find."""
    try:
        CURRENT.set(of_request(request, user, outside))
    except Exception as e:  # noqa: BLE001 - the record is a convenience, never a reason to refuse a request
        log.debug("stamp: %s", e)
        CURRENT.set(None)


def passed_on() -> str | None:
    """The X-IoSuite-On-Behalf header for a request made on the current person's behalf (links.viewer_headers), so the
    other app records what the person used and that this app passed it on. None outside a request."""
    from iosuite_shared.host import CURRENT as APP
    s = CURRENT.get()
    app = APP.get() or ""
    if s is None or not app or app not in catalog.APPS or s.user_id is None:
        return None
    if s.via:  # passed on twice: the first app is the one that counts
        app = s.via
    return json.dumps({"app": app, "client": s.client, "where": s.where, "ip": s.ip, "cloudflare": s.cloudflare,
                       "outside": s.outside}, separators=(",", ":"))


@contextmanager
def job(where: str, client: str = "sync", user: dict | None = None):
    """Work that is nobody's request: a sync (client "sync"), an import ("import"), the app itself ("auto"). user: the
    account it is done for, when there is one (an import someone started from the command line)."""
    s = Stamp((user or {}).get("id"), (user or {}).get("displayName") or (user or {}).get("name") or "",
              client if client in CLIENTS else "auto", str(where or "")[:191])
    token = CURRENT.set(s)
    try:
        yield s
    finally:
        CURRENT.reset(token)


@contextmanager
def as_(client: str, where: str = ""):
    """Within a request, this part is done by something else than the person's own hands: a rule the person's save set
    off ("auto", "rule"), a file they uploaded ("import", "Homebox CSV"). Who stays the person."""
    s = CURRENT.get() or Stamp()
    token = CURRENT.set(replace(s, client=client if client in CLIENTS else s.client, where=str(where or s.where)[:191]))
    try:
        yield
    finally:
        CURRENT.reset(token)


# ------------------------------------------------------------------ writing the record

ACTIONS = ("added", "changed", "deleted")
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


def _now() -> int:
    return int(time.time())


def touch(app: str, kind: str, item_id, action: str = "changed", what: str = "") -> None:
    """Record that the current stamp added, changed or deleted this item. what: a few words on what changed ("time,
    place"), never the item's content. Never raises."""
    touch_many(app, kind, [item_id], action, what)


def touch_many(app: str, kind: str, ids, action: str = "changed", what: str = "") -> None:
    ids = [str(i) for i in ids if i is not None and _ID.fullmatch(str(i))]
    if not ids or action not in ACTIONS:
        return
    s = CURRENT.get() or Stamp()
    now = _now()
    what = str(what or "")[:255] or None
    try:
        with db.tx():
            if action == "deleted":
                db.ex(f"DELETE FROM ios_item_stamps WHERE app = %s AND kind = %s AND item IN ({','.join(['%s'] * len(ids))})",
                      (app, kind, *ids))
            else:
                mine = (now, s.user_id, s.name, s.client, s.where, s.via)
                db._db.many(
                    "INSERT INTO ios_item_stamps (app, kind, item, created_at, created_by, created_name, created_client, created_where, created_via, "
                    "updated_at, updated_by, updated_name, updated_client, updated_where, updated_via) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                    "updated_at = VALUES(updated_at), updated_by = VALUES(updated_by), updated_name = VALUES(updated_name), "
                    "updated_client = VALUES(updated_client), updated_where = VALUES(updated_where), updated_via = VALUES(updated_via)",
                    [(app, kind, i, *(mine if action == "added" else (None,) * 6), *mine) for i in ids])
            db._db.many(
                "INSERT INTO ios_item_changes (app, kind, item, at, action, what, user_id, name, client, place, via, ip, cloudflare, outside) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(app, kind, i, now, action, what, s.user_id, s.name, s.client, s.where, s.via, s.ip or None, int(s.cloudflare), int(s.outside))
                 for i in ids])
            if len(ids) <= 50:  # one item's history stays short; a big import is trimmed by the hourly purge
                for i in ids:
                    edge = db.one("SELECT id FROM ios_item_changes WHERE app = %s AND kind = %s AND item = %s ORDER BY id DESC LIMIT 1 OFFSET %s",
                                  (app, kind, i, KEEP - 1))
                    if edge:
                        db.ex("DELETE FROM ios_item_changes WHERE app = %s AND kind = %s AND item = %s AND id < %s", (app, kind, i, edge["id"]))
    except Exception as e:  # noqa: BLE001 - the item is saved either way
        log.warning("could not record that %s %s %s was %s: %s", app, kind, ids[0] if len(ids) == 1 else f"({len(ids)})", action, e)
        return
    _purge_now_and_then()


def records(app: str, kind: str, what: str = "", action: str = "changed", item=None):
    """A function that changes one item, recorded after it returns (touch()): the item is its first argument, or what
    item(*args, **kwargs) says.

        @stamp.records("ionote", "note", "picture", item=lambda uid, *a, **k: uid.upper())
        def put(uid, data, user): ..."""
    def deco(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            out = f(*args, **kwargs)
            try:
                which = item(*args, **kwargs) if item else args[0]
            except Exception:  # noqa: BLE001 - the change is made; only its record is missing
                which = None
            if which is not None:
                touch(app, kind, which, action, what)
            return out
        return wrapped
    return deco


def move(app: str, kind: str, old_id, new_id) -> None:
    """An item got a new id (related.move's twin): its record follows it."""
    try:
        db.ex("UPDATE ios_item_stamps SET item = %s WHERE app = %s AND kind = %s AND item = %s", (str(new_id), app, kind, str(old_id)))
        db.ex("UPDATE ios_item_changes SET item = %s WHERE app = %s AND kind = %s AND item = %s", (str(new_id), app, kind, str(old_id)))
    except Exception as e:  # noqa: BLE001
        log.warning("could not move the record of %s %s %s: %s", app, kind, old_id, e)


def forget(app: str, kind: str, ids) -> None:
    """Items deleted without a word to anyone (a person's private data when their account goes): their record goes
    with them, history and all."""
    ids = [str(i) for i in ids if i is not None]
    for n in range(0, len(ids), 500):
        part = ids[n:n + 500]
        marks = ",".join(["%s"] * len(part))
        try:
            db.ex(f"DELETE FROM ios_item_stamps WHERE app = %s AND kind = %s AND item IN ({marks})", (app, kind, *part))
            db.ex(f"DELETE FROM ios_item_changes WHERE app = %s AND kind = %s AND item IN ({marks})", (app, kind, *part))
        except Exception as e:  # noqa: BLE001
            log.warning("could not forget the record of %d %s %s: %s", len(part), app, kind, e)


def _purge_now_and_then() -> None:
    """Once an hour: changes older than DAYS, and the ones past KEEP of items changed many at a time."""
    if time.monotonic() - _purged["at"] < _PURGE_S or not _lock.acquire(blocking=False):
        return
    try:
        _purged["at"] = time.monotonic()
        purge()
    finally:
        _lock.release()


def purge() -> int:
    n = 0
    try:
        n = db.ex("DELETE FROM ios_item_changes WHERE at < %s", (_now() - DAYS * 86400,)) or 0
        for r in db.q("SELECT app, kind, item FROM ios_item_changes GROUP BY app, kind, item HAVING COUNT(*) > %s LIMIT 1000", (KEEP,)):
            edge = db.one("SELECT id FROM ios_item_changes WHERE app = %s AND kind = %s AND item = %s ORDER BY id DESC LIMIT 1 OFFSET %s",
                          (r["app"], r["kind"], r["item"], KEEP - 1))
            if edge:
                n += db.ex("DELETE FROM ios_item_changes WHERE app = %s AND kind = %s AND item = %s AND id < %s",
                           (r["app"], r["kind"], r["item"], edge["id"])) or 0
    except Exception as e:  # noqa: BLE001
        log.warning("could not trim the items' history: %s", e)
    return n


# ------------------------------------------------------------------ reading it

def how(client: str, where: str = "", via: str = "", app: str = "") -> str:
    """In words: 'the web page (Safari on Mac)', 'CalDAV (iPhone calendar)', 'MCP (Claude) through the start page'."""
    dav = "CardDAV" if app == "iocontact" else "CalDAV"
    base = {"web": "the web page", "app": where or "an app", "dav": dav, "mcp": "MCP", "api": "an app password",
            "import": "an import", "sync": where or "a sync", "auto": where or "the app itself"}.get(client, client or "")
    detail = where if where and client not in ("app", "sync", "auto") else ""
    if client == "api" and where:
        base, detail = f"the app password “{where}”", ""
    elif client in ("mcp", "dav") and where:
        detail = where
    out = f"{base} ({detail})" if detail else base
    if via and via != app:
        out += f" through {'the start page' if via == 'iostart' else catalog.name_of(via)}"
    return out


def _place(r: dict, viewer: dict) -> str:
    """The address to the one who made the change and to suite admins; to everyone else, home or away."""
    mine = viewer and r.get("user_id") is not None and viewer.get("id") == r.get("user_id")
    if (mine or (viewer or {}).get("suiteAdmin")) and r.get("ip"):
        return r["ip"] + (" (through Cloudflare)" if r.get("cloudflare") else "")
    if r.get("ip") or r.get("outside"):
        return "away from home" if r.get("outside") else "at home"
    return ""


def record(app: str, kind: str, item_id, viewer: dict | None = None) -> dict:
    """{added, changed, history}: as kept, for someone already allowed to see the item."""
    item_id = str(item_id)
    s = db.one("SELECT * FROM ios_item_stamps WHERE app = %s AND kind = %s AND item = %s", (app, kind, item_id))
    rows = db.q("SELECT * FROM ios_item_changes WHERE app = %s AND kind = %s AND item = %s ORDER BY id DESC LIMIT %s",
                (app, kind, item_id, KEEP))

    def one(p: str):
        if not s or not s.get(f"{p}_at"):
            return None
        return {"at": s[f"{p}_at"], "by": s.get(f"{p}_name") or "", "byId": s.get(f"{p}_by"), "client": s.get(f"{p}_client") or "",
                "how": how(s.get(f"{p}_client") or "", s.get(f"{p}_where") or "", s.get(f"{p}_via") or "", app)}
    return {"added": one("created"), "changed": one("updated"),
            "history": [{"at": r["at"], "action": r["action"], "what": r.get("what") or "", "by": r.get("name") or "",
                         "byId": r.get("user_id"), "client": r.get("client") or "",
                         "how": how(r.get("client") or "", r.get("place") or "", r.get("via") or "", app),
                         "from": _place(r, viewer or {})} for r in rows]}


def line(app: str, kind: str, item_id) -> dict | None:
    """The short form for an MCP tool or an item's own answer: {addedBy, addedAt, addedWith, changedBy, changedAt,
    changedWith}, or None when nothing was recorded. For someone already allowed to see the item."""
    try:
        s = db.one("SELECT * FROM ios_item_stamps WHERE app = %s AND kind = %s AND item = %s", (app, kind, str(item_id)))
    except Exception:  # noqa: BLE001
        return None
    if not s:
        return None
    out = {}
    for p, k in (("created", "added"), ("updated", "changed")):
        if s.get(f"{p}_at"):
            out[f"{k}By"] = s.get(f"{p}_name") or ""
            out[f"{k}At"] = s[f"{p}_at"]
            out[f"{k}With"] = how(s.get(f"{p}_client") or "", s.get(f"{p}_where") or "", s.get(f"{p}_via") or "", app)
    return out or None


def with_changes(out: dict, app: str, kind: str, item_id) -> dict:
    """An MCP tool's answer about one item, with its record as line() gives it under "changes" (when there is one).
    For a tool that has already checked that the person may see the item."""
    ch = line(app, kind, item_id)
    if ch and isinstance(out, dict):
        out = {**out, "changes": ch}
    return out

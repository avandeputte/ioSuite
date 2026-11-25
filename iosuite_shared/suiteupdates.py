"""Updating the suite: every copy at once, from Settings › Servers › Updates (in any app) or an AI assistant
over the start page's MCP endpoint.

The suite has one version (iosuite_shared.__version__) and one program, which a machine runs as one copy or several,
each with the apps it was given. An update is a copy's: one update.sh, one restart, whichever apps it runs. So the
Shared ioSuite database keeps one row per copy (ios_copies), not per app. A suite admin leaves a request on the rows,
and every copy watches its own (iosuite_shared.updates.Updater.watch): "check" asks GitHub whether there is a newer
version, "update" runs the copy's update.sh, "restart" starts the copy again (changed settings apply at a start). Each
copy writes back what it knows (the installed version and commit, the newest version on GitHub, whether it can update
itself, how the last update went); summary() makes one answer for the suite out of the rows. Which apps a copy runs
is the suite's list of apps (iosuite_shared.suite: each app's row names its copy).

    suiteupdates.summary()                      # {installed, latest, status, behind, failed, apps: [...], copies: [...]}
    suiteupdates.request("update", by="alex")   # every copy that is behind the newest version
"""
import re
import time

from iosuite_shared import db, suite
from iosuite_shared.errors import Invalid

ACTIONS = ("check", "update", "restart")
WATCH_S = 10     # how often a copy looks at its row
BEAT_S = 60      # how often it says it is still there (updated_at)
ALIVE_S = 300    # a row not touched for this long: the copy is not running
STALE_S = 3600   # a request nobody picked up within the hour is dropped: the copy was not running
FIELDS = ("installed", "git_commit", "latest", "status", "state", "message", "can_run", "docker", "checked_at")


def version_tuple(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v or "0")[:3])


def here() -> str:
    """This copy's name, as its apps' rows in the suite's list say it (suite.copy_name)."""
    return suite.copy_name()


def publish(copy: str = None, **fields) -> None:
    """What a copy knows about itself (any of FIELDS), written to its row. Never raises: the database may be away."""
    fields = {k: v for k, v in fields.items() if k in FIELDS}
    try:
        cols = ["copy", "updated_at", *fields]
        vals = [copy if copy is not None else here(), int(time.time()), *fields.values()]
        db.ex(f"INSERT INTO ios_copies ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
              f"ON DUPLICATE KEY UPDATE {', '.join(f'{c} = VALUES({c})' for c in cols[1:])}", tuple(vals))
    except Exception:  # noqa: BLE001
        pass


def claim(copy: str = None) -> str | None:
    """The action waiting for this copy ('check', 'update' or 'restart'), taken off its row so that it runs once;
    None when there is none (or the database is away). The row is written only when there is something to take, so
    a copy's look every few seconds is one statement. A request from before this start that nobody picked up within
    the hour is dropped: what was asked then is not run now."""
    copy = copy if copy is not None else here()
    try:
        r = db.one("SELECT action, requested_at FROM ios_copies WHERE copy = %s AND action IS NOT NULL AND action <> ''", (copy,))
        if not r:
            return None
        n = db.ex("UPDATE ios_copies SET action = NULL WHERE copy = %s AND action = %s", (copy, r["action"]))
        return r["action"] if n and time.time() - (r["requested_at"] or 0) < STALE_S else None
    except Exception:  # noqa: BLE001
        return None


def beat(copy: str = None) -> None:
    """The copy is running: its row says so every minute (updated_at), which is how summary() tells the copies that
    run from the ones that were stopped or removed. Never raises."""
    try:
        db.ex("UPDATE ios_copies SET updated_at = %s WHERE copy = %s", (int(time.time()), copy if copy is not None else here()))
    except Exception:  # noqa: BLE001
        pass


def row(copy: str = None) -> dict | None:
    try:
        return db.one("SELECT * FROM ios_copies WHERE copy = %s", (copy if copy is not None else here(),))
    except Exception:  # noqa: BLE001
        return None


def _state(r: dict | None) -> dict:
    """A copy's row as the screens read it."""
    r = r or {}
    now = time.time()
    pending = r.get("action") if r.get("action") and now - (r.get("requested_at") or 0) < STALE_S else None
    return {"version": r.get("installed"), "commit": r.get("git_commit"),
            "latest": r.get("latest"), "status": r.get("status"),  # current | update | error, from the copy's last check
            "checked": r.get("checked_at"), "canUpdate": bool(r.get("can_run")), "docker": bool(r.get("docker")),
            "state": r.get("state") or None,  # running | ok | failed: the last update
            "message": r.get("message") or None, "pending": pending, "requestedBy": r.get("requested_by") if pending else None,
            "requested": r.get("requested_at") if pending else None, "updated": r.get("updated_at"),
            "watching": bool(r) and now - (r.get("updated_at") or 0) < ALIVE_S}


def overview() -> list:
    """Every registered app with what its copy says: the version and commit, the newest version on GitHub and when
    that was checked, whether the copy can update itself (not in Docker, update.sh present), the last update (state
    running/ok/failed and its message), and a request still waiting (pending). watching False: the copy is not
    running (its row was not touched for five minutes, or it never wrote one)."""
    rows = {r["copy"]: r for r in db.q("SELECT * FROM ios_copies")}
    out = []
    for a in suite.apps():
        s = _state(rows.get(a.get("copy") or ""))
        out.append({"app": a["app"], "name": a["name"], "copy": a.get("copy") or "", **s,
                    "version": s["version"] or a.get("version"), "lastSeen": a.get("lastSeen")})
    return out


def copies(apps: list) -> list:
    """The apps grouped by the copy of the program they run in (what the Updates screen shows). One entry per copy,
    in the suite's order: {copy, apps, names, version, commit, latest, status, state, message, pending, behind,
    canUpdate, docker, watching, updated}."""
    out: dict = {}
    for a in apps:
        c = out.get(a["copy"])
        if c is None:
            c = out[a["copy"]] = {k: a.get(k) for k in ("copy", "version", "commit", "latest", "status", "state", "message", "pending",
                                                        "canUpdate", "docker", "watching")}
            c.update(apps=[], names=[], behind=bool(a.get("behind")), updated=a.get("updated") or 0)
        c["apps"].append(a["app"])
        c["names"].append(a["name"])
    return list(out.values())


def summary() -> dict:
    """The suite as one thing: {installed, latest, status, checked, behind, failed, canUpdate, apps, copies}.
    Only the copies that run count (watching). installed: the version they run (the lowest, when an update left one
    behind); latest: the newest version any of them found on GitHub; behind: the keys of the apps on a copy below
    it; failed: those of them whose copy's last update failed. status: updating (an update is asked for or running),
    update (copies are behind), error (no copy could ask GitHub), current. canUpdate: a copy that is behind can
    update itself (the ones in Docker are updated by pulling the image). apps: overview(), each with `behind` (also
    for an app whose copy is not running: it is asked too, should it be there after all)."""
    apps = overview()
    live = [a for a in apps if a["watching"] and a["version"]]
    known = [a["latest"] for a in live if a["latest"] and a["status"] != "error"]
    latest = max(known, key=version_tuple) if known else None
    for a in apps:
        a["behind"] = bool(latest and a["version"] and version_tuple(a["version"]) < version_tuple(latest))
    behind = [a for a in live if a["behind"]]
    if any(a["pending"] == "update" or a["state"] == "running" for a in live):
        status = "updating"
    elif behind:
        status = "update"
    elif live and all(a["status"] == "error" for a in live):
        status = "error"
    else:
        status = "current"
    return {"installed": min((a["version"] for a in live), key=version_tuple, default=None), "latest": latest, "status": status,
            "checked": max((a["checked"] or 0 for a in live), default=0) or None,
            "behind": [a["app"] for a in behind], "failed": [a["app"] for a in behind if a["state"] == "failed"],
            "canUpdate": any(a["canUpdate"] for a in behind), "apps": apps, "copies": copies(apps)}


def request(action: str, by: str = None, apps=None) -> list:
    """Leave `action` for the copies: 'check' for every copy, 'update' for every copy that is behind the newest
    version, 'restart' for the copies that run the apps named (none: every copy; changed settings apply at a start,
    and an app starts again with the others of its copy). The keys of the apps on the copies asked."""
    if action not in ACTIONS:
        raise Invalid("action must be check, update or restart")
    known = suite.apps()
    if action == "check":
        asked = known
    elif action == "restart":
        named = {a.get("copy") or "" for a in known if not apps or a["app"] in apps}
        asked = [a for a in known if (a.get("copy") or "") in named]
    else:
        asked = [a for a in summary()["apps"] if a["behind"]]
    now = int(time.time())
    for copy in sorted({a.get("copy") or "" for a in asked}):
        db.ex("INSERT INTO ios_copies (copy, action, requested_at, requested_by, updated_at) VALUES (%s, %s, %s, %s, 0) "
              "ON DUPLICATE KEY UPDATE action = VALUES(action), requested_at = VALUES(requested_at), requested_by = VALUES(requested_by)",
              (copy, action, now, (by or "")[:64] or None))
    return sorted(a["app"] for a in asked)


def wait_checked(since: float, timeout: float = 25.0) -> None:
    """Wait (at most `timeout` seconds) until every copy that runs has checked GitHub after `since`."""
    running = {a["copy"] for a in overview() if a["watching"]}
    end = time.time() + timeout
    while time.time() < end:
        rows = {r["copy"]: r for r in db.q("SELECT copy, checked_at FROM ios_copies")}
        if all((rows.get(k) or {}).get("checked_at") and rows[k]["checked_at"] >= int(since) for k in running):
            return
        time.sleep(1)

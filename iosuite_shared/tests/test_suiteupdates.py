"""Updating the suite: a copy of the program is one update, so one row per copy (ios_copies) however many apps it
runs. The request on the row, the copy's Updater picking it up and saying how it went, the suite admin routes and
the MCP tools."""
import asyncio
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import db, mcp as shared_mcp, suite, suiteupdates, updates, users
from iosuite_shared.fastapi import Auth

HOME, NAS = "home", "nas"   # two servers of the suite, each one copy of the program


@pytest.fixture(autouse=True)
def this_copy(monkeypatch):
    """Which copy this process is, as the apps' rows in the suite's list say it (suite.copy_name)."""
    monkeypatch.setattr(suite, "copy_name", lambda: HOME)
    yield


def updater(tmp_path, monkeypatch, where="copy", version="1.0.0", remote="1.1.0", script=None):
    """This copy's Updater, with GitHub answered from here and `where` as its program folder."""
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    root = tmp_path / where
    root.mkdir(exist_ok=True)
    u = updates.Updater(version, root, repo="someone/iosuite", result_file=root / ".update-result")
    u.in_docker = lambda: False

    def get(url, accept=""):
        if "api.github.com" in url:
            return json.dumps({"sha": "abcdef0123456789", "commit": {"committer": {"date": "2026-11-11T01:02:03Z"}, "message": "new"}}).encode()
        return f'__version__ = "{remote}"\n'.encode()
    u._get_url = get
    if script is not None:
        (root / "update.sh").write_text(script)
        (root / ".venv").mkdir(exist_ok=True)
    return u


def test_request_claim_and_summary(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar", version="1.0.0", copy=HOME)
    suite.register("ionote", name="ioNote", version="1.0.0", copy=HOME)
    suite.register("iopix", name="ioPix", version="1.0.0", copy=NAS)
    home = updater(tmp_path, monkeypatch)
    home._said_hello()
    by = {a["app"]: a for a in suiteupdates.overview()}
    # the apps of a copy all read from its one row; the other copy never wrote one, so it is not running
    assert by["iocalendar"]["watching"] and by["iocalendar"]["version"] == "1.0.0" and not by["iocalendar"]["canUpdate"]
    assert by["ionote"]["watching"] and by["ionote"]["commit"] == by["iocalendar"]["commit"]
    assert not by["iopix"]["watching"] and by["iopix"]["version"] == "1.0.0"
    s = suiteupdates.summary()
    assert s["installed"] == "1.0.0" and s["latest"] is None and s["status"] == "current" and s["behind"] == []

    assert suiteupdates.request("check", by="alex") == ["iocalendar", "ionote", "iopix"]
    assert suiteupdates.claim() == "check" and suiteupdates.claim() is None  # taken once, by the copy
    home.serve("check")
    by = {a["app"]: a for a in suiteupdates.overview()}
    assert by["iocalendar"]["latest"] == "1.1.0" and by["iocalendar"]["status"] == "update" and by["iocalendar"]["checked"]
    assert by["iopix"]["pending"] == "check" and not by["iopix"]["watching"]  # asked, still not running

    # the suite: this copy found 1.1.0, so every app below it is behind, those of the copy that never asked too
    s = suiteupdates.summary()
    assert s["installed"] == "1.0.0" and s["latest"] == "1.1.0" and s["status"] == "update" and s["checked"]
    assert s["behind"] == ["iocalendar", "ionote"] and s["failed"] == [] and not s["canUpdate"]
    # an app on a copy that is not running is asked too, should it be there after all
    assert suiteupdates.request("update", by="alex") == ["iocalendar", "ionote", "iopix"]
    assert suiteupdates.summary()["status"] == "updating"
    assert suiteupdates.claim() == "update", "one update for the copy, whichever of its apps are behind"

    # the copy's update failed: its apps are still at 1.0.0, and it is asked again
    suiteupdates.publish(HOME, state="failed", message="pip said no")
    s = suiteupdates.summary()
    assert s["installed"] == "1.0.0" and s["status"] == "update" and s["behind"] == ["iocalendar", "ionote"] == s["failed"]
    assert suiteupdates.request("update") == ["iocalendar", "ionote", "iopix"]
    suiteupdates.claim(), suiteupdates.claim(NAS)
    suiteupdates.publish(HOME, installed="1.1.0", status="current", state="ok")
    suiteupdates.publish(NAS, installed="1.1.0", status="current", state="ok")
    s = suiteupdates.summary()
    assert s["installed"] == "1.1.0" == s["latest"] and s["status"] == "current" and suiteupdates.request("update") == []
    with pytest.raises(ValueError):
        suiteupdates.request("reboot")


def test_a_copy_looks_for_what_is_asked_of_it_with_one_thread_and_one_row(tmp_path, monkeypatch):
    """Every app of a copy had a row of its own and a thread asking the database every ten seconds; the copy has one
    of each, however many apps it runs."""
    for app in ("iocalendar", "ionote", "iotask"):
        suite.register(app, name=app, version="1.0.0", copy=HOME)
    served = []
    u = updater(tmp_path, monkeypatch)
    monkeypatch.setattr(u, "serve", lambda action: served.append(action))
    threads = {u.watch(every=0.05) for _ in range(3)}   # every app of the copy asks for the watch as it starts
    assert len(threads) == 1 and next(iter(threads)).name == "update-watch"
    end = time.time() + 5
    while time.time() < end and not suiteupdates.row():
        time.sleep(0.05)
    assert {a["app"] for a in suiteupdates.overview() if a["watching"]} == {"iocalendar", "ionote", "iotask"}
    assert suiteupdates.request("check", by="alex") == ["iocalendar", "ionote", "iotask"]
    while time.time() < end and not served:
        time.sleep(0.05)
    assert served == ["check"], "one request for the copy, not one per app"
    assert [r["copy"] for r in db.q("SELECT copy FROM ios_copies")] == [HOME]
    before = db.one("SELECT updated_at FROM ios_copies WHERE copy = %s", (HOME,))["updated_at"]
    db.ex("UPDATE ios_copies SET updated_at = 5")
    suiteupdates.beat()
    assert db.one("SELECT updated_at FROM ios_copies WHERE copy = %s", (HOME,))["updated_at"] >= before


def test_a_copy_that_stopped_does_not_hold_the_suite_back():
    suite.register("iocalendar", name="ioCalendar", version="1.1.0", copy=HOME)
    suite.register("iopix", name="ioPix", version="1.0.0", copy=NAS)
    suiteupdates.publish(HOME, installed="1.1.0", latest="1.1.0", status="current")
    suiteupdates.publish(NAS, installed="1.0.0", latest="1.0.0", status="current", state="running")
    db.ex("UPDATE ios_copies SET updated_at = %s WHERE copy = %s", (int(time.time()) - suiteupdates.ALIVE_S - 5, NAS))
    s = suiteupdates.summary()
    by = {a["app"]: a for a in s["apps"]}
    assert not by["iopix"]["watching"] and by["iopix"]["behind"]
    assert s["installed"] == "1.1.0" and s["status"] == "current" and s["behind"] == []
    assert suiteupdates.request("update") == ["iopix"]  # asked all the same, should it be there after all
    # what was asked more than an hour ago is not run when the copy starts again
    db.ex("UPDATE ios_copies SET requested_at = %s WHERE copy = %s", (int(time.time()) - suiteupdates.STALE_S - 5, NAS))
    assert suiteupdates.claim(NAS) is None and db.one("SELECT action FROM ios_copies WHERE copy = %s", (NAS,))["action"] is None
    suiteupdates.beat(NAS)  # it runs again
    assert suiteupdates.summary()["behind"] == ["iopix"]


def test_the_daily_check_is_one_switch_for_the_suite():
    assert updates.auto_check_enabled()
    updates.set_auto_check(False)
    assert not updates.auto_check_enabled() and db.settings_of("") == {"update_check": "0"}
    updates.set_auto_check(True)
    assert updates.auto_check_enabled() and db.settings_of("") == {}


def test_an_update_that_cannot_run_says_why(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar", copy=HOME)
    updater(tmp_path, monkeypatch).serve("update")
    a = suiteupdates.overview()[0]
    assert a["state"] == "failed" and "cannot update itself" in a["message"] and not a["pending"]


def test_an_update_runs_and_the_next_start_says_how_it_went(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar", copy=HOME)
    # update.sh writes its result and (here) does not restart anything
    cal = updater(tmp_path, monkeypatch, script='printf "ok: updated to 1.1.0" > "$IOSUITE_RESULT"\n')
    cal._said_hello()
    assert suiteupdates.overview()[0]["canUpdate"]
    cal.serve("update")
    for _ in range(100):
        if not cal.progress["running"]:
            break
        time.sleep(0.05)
    a = suiteupdates.overview()[0]
    assert a["state"] == "ok" and a["message"] == "updated to 1.1.0"

    # a restart in the middle of update.sh leaves "running": the next start reads the result file
    suiteupdates.publish(HOME, state="running", latest="1.1.0", status="update")
    new = updater(tmp_path, monkeypatch, where="next", version="1.1.0")
    new.result_file = cal.result_file
    new._said_hello()
    a = suiteupdates.overview()[0]
    assert a["state"] == "ok" and a["version"] == "1.1.0" and a["status"] == "current"


def make_app():
    auth = Auth("iostart", register=False)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.admin_router())
    return app


def signed_in(app, name, password):
    c = TestClient(app, base_url="http://home.example.com")
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


def test_the_admin_routes():
    suite.register("iocalendar", name="ioCalendar", copy=HOME)
    users.create("alex", "secret123", suite_admin=True)
    users.create("ed", "secret123", "admin", "iostart")
    app = make_app()
    ed = signed_in(app, "ed", "secret123")
    assert ed.get("/api/suite-admin/updates").status_code == 403  # an app admin is not a suite admin
    c = signed_in(app, "alex", "secret123")
    d = c.get("/api/suite-admin/updates").json()
    assert d["apps"][0]["app"] == "iocalendar" and d["status"] == "current" and d["autoCheck"] is True
    r = c.post("/api/suite-admin/updates", json={"action": "check"}).json()
    assert r["asked"] == ["iocalendar"] and r["apps"][0]["pending"] == "check" and r["apps"][0]["requestedBy"] == "alex"
    suiteupdates.publish(HOME, installed="1.0.0", latest="1.1.0", status="update")
    r = c.post("/api/suite-admin/updates", json={"action": "update"}).json()
    assert r["asked"] == ["iocalendar"] and r["status"] == "updating" and r["latest"] == "1.1.0"
    r = c.post("/api/suite-admin/updates", json={"autoCheck": False}).json()
    assert r["autoCheck"] is False and r["asked"] == [] and not updates.auto_check_enabled()
    assert c.post("/api/suite-admin/updates", json={"action": "reboot"}).status_code == 400
    assert c.post("/api/suite-admin/updates", json={}).status_code == 400


def test_the_mcp_tools():
    from mcp.server.mcpserver.exceptions import ToolError
    suite.register("iocalendar", name="ioCalendar", copy=HOME)
    server = shared_mcp.make_server("iostart", instructions="", app_tools=False)
    shared_mcp.add_suite_update_tools(server)
    alex = users.create("alex", "secret123", suite_admin=True)
    ed = users.create("ed", "secret123", "admin", "iostart")

    def call(user, name, args):
        tok = shared_mcp.current_user.set(user)
        try:
            return asyncio.run(server.call_tool(name, args))
        finally:
            shared_mcp.current_user.reset(tok)
    with pytest.raises(ToolError):
        call(users.get(ed["id"], "iostart"), "update_suite", {})
    assert "newest version" in str(call(users.get(alex["id"], "iostart"), "update_suite", {}))  # nothing is behind
    suiteupdates.publish(HOME, installed="1.0.0", latest="1.1.0", status="update")
    out = call(users.get(alex["id"], "iostart"), "update_suite", {})
    assert "iocalendar" in str(out)
    assert db.one("SELECT action FROM ios_copies WHERE copy = %s", (HOME,))["action"] == "update"
    out = call(users.get(alex["id"], "iostart"), "suite_version", {"check": False})
    assert "iocalendar" in str(out) and "updating" in str(out)


def test_the_restart_that_ends_update_sh_is_not_a_failure(tmp_path, monkeypatch):
    """update.sh writes ok, then restarts the service, which ends the script too (a signal): the update went through."""
    suite.register("iocalendar", name="ioCalendar", copy=HOME)
    cal = updater(tmp_path, monkeypatch, script='printf "ok: updated to 1.1.0" > "$IOSUITE_RESULT"\necho "==> Restarting the service"\nkill -TERM $$\n')
    cal.serve("update")
    for _ in range(100):
        if not cal.progress["running"]:
            break
        time.sleep(0.05)
    assert cal.progress["error"] is None
    # the restart is under way: the row says "running" until the new version starts, so the Updates page keeps
    # following a copy that takes a while to come back (it would otherwise see the old version and stop)
    suiteupdates.publish(HOME, installed="1.0.0", latest="1.1.0", status="update")
    a = suiteupdates.overview()[0]
    assert a["state"] == "running" and a["message"] == "updated to 1.1.0; restarting"
    assert suiteupdates.summary()["status"] == "updating"
    new = updater(tmp_path, monkeypatch, where="next", version="1.1.0")
    new.result_file = cal.result_file
    new._said_hello()
    a = suiteupdates.overview()[0]
    assert a["state"] == "ok" and a["message"] == "updated to 1.1.0" and suiteupdates.summary()["status"] == "current"

    # a row an older version marked failed that way is put right by the next start
    suiteupdates.publish(HOME, state="failed", message="==> Restarting the service")
    cal._said_hello()
    assert suiteupdates.overview()[0]["state"] == "ok"


def test_a_restart_is_asked_of_the_apps_named_and_the_copy_starts_once(tmp_path, monkeypatch):
    """Changed settings apply at a start: a suite admin asks the apps, and a copy starts again once, whichever of its
    apps were asked."""
    for k in ("iocalendar", "iotask"):
        suite.register(k, name=k, copy=HOME)
    suite.register("iopix", name="ioPix", copy=NAS)
    assert suiteupdates.request("restart", "alex", ["iocalendar", "nosuch"]) == ["iocalendar", "iotask"]
    assert suiteupdates.request("restart", "alex") == ["iocalendar", "iopix", "iotask"]
    cal = updater(tmp_path, monkeypatch)
    restarted = []
    monkeypatch.setattr(updates.Updater, "restart", staticmethod(lambda delay=0.5: restarted.append(delay)))
    cal.serve(suiteupdates.claim())
    assert restarted == [0.5]
    assert suiteupdates.claim() is None, "the copy was asked once: it does not start again for each of its apps"
    assert suiteupdates.claim(NAS) == "restart"  # another copy's: still waiting for it
    with pytest.raises(ValueError):
        suiteupdates.request("reboot")


def test_the_lines_are_the_suite_s_servers_not_its_apps(tmp_path, monkeypatch):
    """One copy of the program runs several apps and updates once, so the Updates screen counts servers: the apps of
    a copy are one line, and an app on a server of its own is its own line."""
    for app in ("iocalendar", "iotask"):
        suite.register(app, name=app, version="1.0.0", copy=HOME)
    suite.register("iopix", name="ioPix", version="1.1.0", copy=NAS)
    updater(tmp_path, monkeypatch)._said_hello()
    suiteupdates.publish(HOME, latest="1.1.0", status="update")
    suiteupdates.publish(NAS, installed="1.1.0", git_commit="abcdef0", latest="1.1.0", status="current", state="ok",
                         message="updated to v1.1.0", can_run=1)

    s = suiteupdates.summary()
    by = {c["copy"]: c for c in s["copies"]}
    assert sorted(by) == ["home", "nas"] and s["status"] == "update"
    assert by["home"]["apps"] == ["iocalendar", "iotask"] and by["home"]["version"] == "1.0.0" and by["home"]["behind"]
    assert by["home"]["watching"] and by["home"]["state"] is None
    assert by["nas"]["apps"] == ["iopix"] and not by["nas"]["behind"] and by["nas"]["state"] == "ok"
    # a copy whose update failed says so once, however many apps it runs
    suiteupdates.publish(HOME, state="failed", message="update.sh timed out")
    by = {c["copy"]: c for c in suiteupdates.summary()["copies"]}
    assert by["home"]["state"] == "failed" and by["home"]["message"] == "update.sh timed out"

"""Updating every app from one place: the request in ios_updates, each app's Updater picking it up and saying how it
went, the suite admin routes and the MCP tools."""
import asyncio
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import db, mcp as shared_mcp, suite, suiteupdates, updates, users
from iosuite_shared.fastapi import Auth


@pytest.fixture(autouse=True)
def one_copy():
    """What the apps of a copy share (one update.sh run, one answer from GitHub), as a process starts with it."""
    def reset():
        updates._Copy.members.clear()
        updates._Copy.checked.clear()
        updates._Copy.progress.update(running=False, error=None, log="", started=None, finished=None)
    reset()
    yield
    reset()


def updater(tmp_path, monkeypatch, app="iocalendar", version="1.0.0", remote="1.1.0", script=None):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    root = tmp_path / app
    root.mkdir()
    u = updates.Updater(app, version, root, repo=f"someone/{app}", result_file=root / ".update-result")
    u.in_docker = lambda: False

    def get(url, accept=""):
        if "api.github.com" in url:
            return json.dumps({"sha": "abcdef0123456789", "commit": {"committer": {"date": "2026-11-11T01:02:03Z"}, "message": "new"}}).encode()
        return f'__version__ = "{remote}"\n'.encode()
    u._get_url = get
    if script is not None:
        (root / "update.sh").write_text(script)
        (root / ".venv").mkdir()
    return u


def test_request_claim_and_summary(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar", version="1.0.0")
    suite.register("ionote", name="ioNote", version="1.0.0")
    cal = updater(tmp_path, monkeypatch)
    cal._said_hello()
    by = {a["app"]: a for a in suiteupdates.overview()}
    assert by["iocalendar"]["watching"] and by["iocalendar"]["version"] == "1.0.0" and not by["iocalendar"]["canUpdate"]
    assert not by["ionote"]["watching"] and by["ionote"]["version"] == "1.0.0"  # never wrote its row: not running
    s = suiteupdates.summary()
    assert s["installed"] == "1.0.0" and s["latest"] is None and s["status"] == "current" and s["behind"] == []

    assert suiteupdates.request("check", by="alex") == ["iocalendar", "ionote"]
    assert suiteupdates.claim("iocalendar") == "check" and suiteupdates.claim("iocalendar") is None  # taken once
    cal.serve("check")
    a = {a["app"]: a for a in suiteupdates.overview()}["iocalendar"]
    assert a["latest"] == "1.1.0" and a["status"] == "update" and a["checked"] and a["commit"]
    by = {a["app"]: a for a in suiteupdates.overview()}
    assert by["ionote"]["pending"] == "check" and not by["ionote"]["watching"]  # asked, still not running

    # the suite: one app found 1.1.0, so every app below it is behind, the one that has not asked GitHub itself too
    note = updater(tmp_path, monkeypatch, app="ionote")
    note._said_hello()
    s = suiteupdates.summary()
    assert s["installed"] == "1.0.0" and s["latest"] == "1.1.0" and s["status"] == "update" and s["checked"]
    assert s["behind"] == ["iocalendar", "ionote"] and s["failed"] == [] and not s["canUpdate"]
    assert suiteupdates.request("update", by="alex") == ["iocalendar", "ionote"]
    assert suiteupdates.summary()["status"] == "updating"
    assert suiteupdates.claim("iocalendar") == "update" and suiteupdates.claim("ionote") == "update"

    # one app is on 1.1.0 now, the other failed: the suite is still at 1.0.0, and only that app is asked again
    suiteupdates.publish("iocalendar", installed="1.1.0", status="current", state="ok")
    suiteupdates.publish("ionote", state="failed", message="pip said no")
    s = suiteupdates.summary()
    assert s["installed"] == "1.0.0" and s["status"] == "update" and s["behind"] == ["ionote"] == s["failed"]
    assert suiteupdates.request("update") == ["ionote"]
    suiteupdates.claim("ionote")
    suiteupdates.publish("ionote", installed="1.1.0", status="current", state="ok")
    s = suiteupdates.summary()
    assert s["installed"] == "1.1.0" == s["latest"] and s["status"] == "current" and suiteupdates.request("update") == []
    with pytest.raises(ValueError):
        suiteupdates.request("reboot")


def test_an_app_that_stopped_does_not_hold_the_suite_back(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar", version="1.1.0")
    suite.register("ionote", name="ioNote", version="1.0.0")
    suiteupdates.publish("iocalendar", installed="1.1.0", latest="1.1.0", status="current")
    suiteupdates.publish("ionote", installed="1.0.0", latest="1.0.0", status="current", state="running")
    db.ex("UPDATE ios_updates SET updated_at = %s WHERE app = 'ionote'", (int(time.time()) - suiteupdates.ALIVE_S - 5,))
    s = suiteupdates.summary()
    by = {a["app"]: a for a in s["apps"]}
    assert not by["ionote"]["watching"] and by["ionote"]["behind"]
    assert s["installed"] == "1.1.0" and s["status"] == "current" and s["behind"] == []
    assert suiteupdates.request("update") == ["ionote"]  # asked all the same, should it be there after all
    # what was asked more than an hour ago is not run when the app starts again
    db.ex("UPDATE ios_updates SET requested_at = %s WHERE app = 'ionote'", (int(time.time()) - suiteupdates.STALE_S - 5,))
    assert suiteupdates.claim("ionote") is None and db.one("SELECT action FROM ios_updates WHERE app = 'ionote'")["action"] is None
    suiteupdates.beat("ionote")  # it runs again
    assert suiteupdates.summary()["behind"] == ["ionote"]


def test_the_daily_check_is_one_switch_for_the_suite():
    assert updates.auto_check_enabled()
    updates.set_auto_check(False)
    assert not updates.auto_check_enabled() and db.settings_of("") == {"update_check": "0"}
    updates.set_auto_check(True)
    assert updates.auto_check_enabled() and db.settings_of("") == {}


def test_an_update_that_cannot_run_says_why(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar")
    cal = updater(tmp_path, monkeypatch)
    cal.serve("update")
    a = suiteupdates.overview()[0]
    assert a["state"] == "failed" and "cannot update itself" in a["message"] and not a["pending"]


def test_an_update_runs_and_the_next_start_says_how_it_went(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar")
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
    suiteupdates.publish("iocalendar", state="running", latest="1.1.0", status="update")
    (tmp_path / "next").mkdir()
    new = updater(tmp_path / "next", monkeypatch, version="1.1.0")
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
    suite.register("iocalendar", name="ioCalendar")
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
    suiteupdates.publish("iocalendar", installed="1.0.0", latest="1.1.0", status="update")
    r = c.post("/api/suite-admin/updates", json={"action": "update"}).json()
    assert r["asked"] == ["iocalendar"] and r["status"] == "updating" and r["latest"] == "1.1.0"
    r = c.post("/api/suite-admin/updates", json={"autoCheck": False}).json()
    assert r["autoCheck"] is False and r["asked"] == [] and not updates.auto_check_enabled()
    assert c.post("/api/suite-admin/updates", json={"action": "reboot"}).status_code == 400
    assert c.post("/api/suite-admin/updates", json={}).status_code == 400


def test_the_mcp_tools():
    from mcp.server.mcpserver.exceptions import ToolError
    suite.register("iocalendar", name="ioCalendar")
    server = shared_mcp.make_server("iostart", "ioStart", "1.0", instructions="")
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
    suiteupdates.publish("iocalendar", installed="1.0.0", latest="1.1.0", status="update")
    out = call(users.get(alex["id"], "iostart"), "update_suite", {})
    assert "iocalendar" in str(out)
    assert db.one("SELECT action FROM ios_updates WHERE app = 'iocalendar'")["action"] == "update"
    out = call(users.get(alex["id"], "iostart"), "suite_version", {"check": False})
    assert "iocalendar" in str(out) and "updating" in str(out)


def test_the_restart_that_ends_update_sh_is_not_a_failure(tmp_path, monkeypatch):
    """update.sh writes ok, then restarts the service, which ends the script too (a signal): the update went through."""
    suite.register("iocalendar", name="ioCalendar")
    cal = updater(tmp_path, monkeypatch, script='printf "ok: updated to 1.1.0" > "$IOSUITE_RESULT"\necho "==> Restarting the service"\nkill -TERM $$\n')
    cal.serve("update")
    for _ in range(100):
        if not cal.progress["running"]:
            break
        time.sleep(0.05)
    assert cal.progress["error"] is None
    # the restart is under way: the row says "running" until the new version starts, so the Updates page keeps
    # following an app that takes a while to come back (it would otherwise see the old version and stop)
    suiteupdates.publish("iocalendar", installed="1.0.0", latest="1.1.0", status="update")
    a = suiteupdates.overview()[0]
    assert a["state"] == "running" and a["message"] == "updated to 1.1.0; restarting"
    assert suiteupdates.summary()["status"] == "updating"
    (tmp_path / "next").mkdir()
    new = updater(tmp_path / "next", monkeypatch, version="1.1.0")
    new.result_file = cal.result_file
    new._said_hello()
    a = suiteupdates.overview()[0]
    assert a["state"] == "ok" and a["message"] == "updated to 1.1.0" and suiteupdates.summary()["status"] == "current"

    # a row an older version marked failed that way is put right by the next start
    suiteupdates.publish("iocalendar", state="failed", message="==> Restarting the service")
    cal._said_hello()
    assert suiteupdates.overview()[0]["state"] == "ok"


def test_a_restart_is_asked_of_the_apps_named_and_the_copy_starts_once(tmp_path, monkeypatch):
    """Changed settings apply at a start: a suite admin asks the apps, and a copy starts again once, whichever of its
    apps were asked."""
    for k in ("iocalendar", "iotask", "iopix"):
        suite.register(k, name=k)
    assert suiteupdates.request("restart", "alex", ["iocalendar", "iotask", "nosuch"]) == ["iocalendar", "iotask"]
    assert suiteupdates.request("restart", "alex") == ["iocalendar", "iopix", "iotask"]
    cal = updater(tmp_path, monkeypatch)
    updater(tmp_path, monkeypatch, app="iotask")
    restarted = []
    monkeypatch.setattr(updates.Updater, "restart", staticmethod(lambda delay=0.5: restarted.append(delay)))
    cal.serve(suiteupdates.claim("iocalendar"))
    assert restarted == [0.5]
    assert suiteupdates.claim("iotask") is None, "its request was taken with the copy's: it does not start again a second time"
    assert suiteupdates.claim("iopix") == "restart"  # another copy's: still waiting for it
    with pytest.raises(ValueError):
        suiteupdates.request("reboot")


def test_the_lines_are_the_suite_s_servers_not_its_apps(tmp_path, monkeypatch):
    """One copy of the program runs several apps and updates once, so the Updates screen counts servers: the apps of
    a copy are one line, and an app on a server of its own is its own line."""
    for app in ("iocalendar", "iotask"):
        suite.register(app, name=app, version="1.0.0", copy="home")
    suite.register("iopix", name="ioPix", version="1.0.0", copy="nas")
    for app in ("iocalendar", "iotask"):
        u = updater(tmp_path, monkeypatch, app=app)
        u._said_hello()
        suiteupdates.publish(app, latest="1.1.0", status="update")
    pix = updater(tmp_path, monkeypatch, app="iopix", version="1.1.0")
    pix._said_hello()
    suiteupdates.publish("iopix", latest="1.1.0", status="current", state="ok", message="updated to v1.1.0")

    s = suiteupdates.summary()
    by = {c["copy"]: c for c in s["copies"]}
    assert sorted(by) == ["home", "nas"] and s["status"] == "update"
    assert by["home"]["apps"] == ["iocalendar", "iotask"] and by["home"]["version"] == "1.0.0" and by["home"]["behind"]
    assert by["home"]["watching"] and by["home"]["state"] is None
    assert by["nas"]["apps"] == ["iopix"] and not by["nas"]["behind"] and by["nas"]["state"] == "ok"
    # a copy whose update failed says so once, however many apps it runs
    suiteupdates.publish("iotask", state="failed", message="update.sh timed out")
    by = {c["copy"]: c for c in suiteupdates.summary()["copies"]}
    assert by["home"]["state"] == "failed" and by["home"]["message"] == "update.sh timed out"


def test_how_an_update_of_another_program_went_is_not_shown(tmp_path, monkeypatch):
    """What is in the row may be about the install this one replaced (the first ioSuite, one program per app, its own
    update.sh in its own folder). Its outcome says nothing about what runs here now, so the line is cleared."""
    suite.register("iocalendar", name="ioCalendar", version="1.0.0")
    suiteupdates.publish("iocalendar", installed="0.9.0", git_commit="aaaaaaa", state="failed",
                         message="Command '['sh', '/opt/iocalendar/app/update.sh']' timed out after 1800 seconds")
    u = updater(tmp_path, monkeypatch)
    u.local_commit = lambda: "bbbbbbb"
    u._said_hello()
    a = {a["app"]: a for a in suiteupdates.overview()}["iocalendar"]
    assert a["state"] is None and a["message"] is None and a["version"] == "1.0.0" and a["commit"] == "bbbbbbb"
    # one about this very program is kept: a failed update leaves the commit as it was
    suiteupdates.publish("iocalendar", state="failed", message="update.sh said no")
    u._said_hello()
    a = {a["app"]: a for a in suiteupdates.overview()}["iocalendar"]
    assert a["state"] == "failed" and a["message"] == "update.sh said no"

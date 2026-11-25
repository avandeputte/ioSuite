"""Settings › Apps › All settings: the settings the apps read as they start (kept in the Shared ioSuite database, set on
the screen or with `iosuite set`), the addresses at each door, the restart that makes a change apply, and the log
viewer that puts every copy's log on one timeline (iosuite_shared.admin, its endpoints, iosuite_shared.cli)."""
import argparse
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import admin, cli, config, db, logs, suite, users
from iosuite_shared.fastapi import Auth


def make_app(name="iostart"):
    auth = Auth(name, register=False)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.admin_router())
    return app


def signed_in(app, name, password="secret123"):
    c = TestClient(app, base_url="http://home.example.com")
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


def by_name(items):
    return {d["name"]: d for d in items}


@pytest.fixture
def two_copies(monkeypatch):
    """ioPix on a server of its own (nas), the rest here (home)."""
    monkeypatch.setattr(suite, "copy_name", lambda: "home")
    suite.register("iostart", "ioStart", internal_url="http://10.0.0.5", copy="home")
    suite.register("iocalendar", "ioCalendar", url="https://calendar.example.com", internal_url="http://10.0.0.5/calendar", copy="home")
    suite.register("iopix", "ioPix", internal_url="http://10.0.0.9/pix", copy="nas")


# ---- the settings
def test_the_screen_lists_what_may_be_set_with_what_is_stored(two_copies):
    db.set_setting("TZ", "Europe/Brussels")
    db.set_setting("KEEP_DELETED_DAYS", "30")
    db.set_setting("KEEP_DELETED_DAYS", "7", "iocalendar")
    db.set_setting("HOLIDAYS_COUNTRY", "BE", "iocalendar")
    db.set_setting("default_role", "none", "iocalendar")  # not a setting of this screen
    got = admin.settings()
    whole = by_name(got["suite"])
    assert whole["TZ"]["value"] == "Europe/Brussels" and whole["PUBLIC_URL"]["value"] == "" and whole["KEEP_DELETED_DAYS"]["default"] == "90"
    assert [a["app"] for a in got["apps"]] == ["iocalendar", "iopix", "iostart"] and got["apps"][1]["copy"] == "nas"
    cal = by_name(got["apps"][0]["settings"])
    assert cal["HOLIDAYS_COUNTRY"]["value"] == "BE" and cal["PUBLIC_URL"]["label"] == "Its own address"
    assert "default_role" not in cal and "suite" not in cal["PUBLIC_URL"]  # an app's own address never falls back to the suite's
    pix = by_name(got["apps"][1]["settings"])
    assert pix["DIGIKAM_DB_TYPE"]["choices"] == ["none", "sqlite", "mysql"] and pix["EDITING"]["type"] == "switch" and pix["EDITING"]["value"] == ""


def test_a_setting_is_stored_as_the_apps_read_it(two_copies):
    assert admin.set_setting("iopix", "EDITING", False) == {"app": "iopix", "name": "EDITING", "value": "0"}
    assert admin.set_setting("iopix", "EDITING", "on")["value"] == "1"
    assert admin.set_setting("iopix", "THUMB_HEIGHT", " 480 ")["value"] == "480"
    assert admin.set_setting("iopix", "DIGIKAM_DB_TYPE", "mysql")["value"] == "mysql"
    assert admin.set_setting("_suite", "COOKIE_DOMAIN", ".Example.COM")["value"] == "example.com"
    assert admin.set_setting("", "PUBLIC_URL", "https://home.example.com/")["value"] == "https://home.example.com"
    assert admin.set_setting("_suite", "SYNC_URL", "https://home.example.com:8443/sync")["value"] == "https://home.example.com:8443/sync"
    assert admin.set_setting("iocalendar", "PUBLIC_URL", "https://calendar.example.com/")["value"] == "https://calendar.example.com"
    assert admin.set_setting("iocalendar", "TZ", "Europe/Brussels")["value"] == "Europe/Brussels"  # one of the suite's, for this app alone
    assert db.settings_of("iopix") == {"EDITING": "1", "THUMB_HEIGHT": "480", "DIGIKAM_DB_TYPE": "mysql"}
    assert db.settings_of("")["COOKIE_DOMAIN"] == "example.com" and config.cookie_domain() == "example.com"
    assert admin.set_setting("iopix", "THUMB_HEIGHT", "") == {"app": "iopix", "name": "THUMB_HEIGHT", "value": ""}  # the default again
    assert "THUMB_HEIGHT" not in db.settings_of("iopix")


@pytest.mark.parametrize("app,name,value,says", [
    ("iopix", "EDITING", "perhaps", "on or off"),
    ("iopix", "THUMB_HEIGHT", "tall", "whole number"),
    ("iopix", "DIGIKAM_DB_TYPE", "postgres", "one of: none, sqlite, mysql"),
    ("_suite", "PUBLIC_URL", "home.example.com", "is an address"),
    ("_suite", "PUBLIC_URL", "ftp://home.example.com", "is an address"),
    ("iocalendar", "PUBLIC_URL", "https://home.example.com/calendar", "has no folder"),
    ("iocalendar", "SYNC_URL", "https://sync.example.com/calendar", "has no folder"),
    ("_suite", "TZ", "x" * 2001, "Too long"),
])
def test_a_value_that_cannot_be_is_refused(app, name, value, says):
    with pytest.raises(ValueError, match=says):
        admin.set_setting(app, name, value)
    assert db.settings_of("" if app == "_suite" else app) == {}


def test_only_what_an_app_declares_can_be_set():
    for app, name in (("iocalendar", "THUMB_HEIGHT"), ("_suite", "THUMB_HEIGHT"), ("iocalendar", "default_role"), ("_suite", "auth_proxy_trusted"),
                      ("nosuchapp", "TZ"), ("iocalendar", "")):
        with pytest.raises(LookupError):
            admin.set_setting(app, name, "1")
    assert db.q("SELECT * FROM ios_settings") == []


def test_the_addresses_at_each_door(two_copies, monkeypatch):
    monkeypatch.setattr(config, "PORT", 80)
    monkeypatch.setattr(config, "SYNC_PORT", 8443)
    monkeypatch.setattr(config, "MCP_PORT", 0)
    admin.set_setting("_suite", "PUBLIC_URL", "https://home.example.com")
    admin.set_setting("_suite", "MCP_URL", "https://mcp.example.com")
    got = admin.addresses()
    assert got["suite"] == {"web": "https://home.example.com", "sync": None, "mcp": "https://mcp.example.com"}
    assert got["ports"] == {"web": 80, "sync": 8443, "mcp": 0} and got["copy"] == "home"
    rows = {r["app"]: r for r in got["apps"]}
    assert rows["iocalendar"]["web"] == ["https://calendar.example.com", "https://home.example.com/calendar"]
    assert rows["iocalendar"]["sync"] == [] and rows["iocalendar"]["mcp"] == ["https://mcp.example.com/calendar/mcp"]
    assert rows["iostart"]["web"] == ["https://home.example.com"] and rows["iostart"]["mcp"] == ["https://mcp.example.com/mcp"]
    assert rows["iopix"]["copy"] == "nas" and rows["iopix"]["internal"] == "http://10.0.0.9/pix" and rows["iopix"]["folder"] == "pix"


# ---- the endpoints
def test_only_a_suite_admin_reaches_the_settings_the_restart_and_the_log(two_copies):
    users.create("alex", "secret123", suite_admin=True)
    users.create("ed", "secret123", "admin", "iostart")  # an admin of the app, not of the suite
    app = make_app()
    ed, out = signed_in(app, "ed"), TestClient(app, base_url="http://home.example.com")
    for c, status in ((ed, 403), (out, 401)):
        assert c.get("/api/suite-admin/settings").status_code == status
        assert c.get("/api/suite-admin/addresses").status_code == status
        assert c.get("/api/suite-admin/logs").status_code == status
        assert c.get("/api/suite-admin/logs?local=1").status_code == status
        assert c.put("/api/suite-admin/settings/_suite/TZ", json={"value": "UTC"}).status_code == status
        assert c.post("/api/suite-admin/restart", json={}).status_code == status
    assert db.settings_of("") == {} and db.q("SELECT * FROM ios_copies") == []


def test_setting_and_restarting_from_the_screen(two_copies):
    users.create("alex", "secret123", suite_admin=True)
    c = signed_in(make_app(), "alex")
    assert c.put("/api/suite-admin/settings/_suite/TZ", json={"value": "Europe/Brussels"}).json() == {"app": "", "name": "TZ", "value": "Europe/Brussels"}
    assert c.put("/api/suite-admin/settings/iopix/EDITING", json={"value": False}).json()["value"] == "0"
    got = c.get("/api/suite-admin/settings").json()
    assert by_name(got["suite"])["TZ"]["value"] == "Europe/Brussels"
    assert by_name(next(a for a in got["apps"] if a["app"] == "iopix")["settings"])["EDITING"]["value"] == "0"
    r = c.put("/api/suite-admin/settings/iopix/THUMB_HEIGHT", json={"value": "tall"})
    assert r.status_code == 400 and "whole number" in r.json()["detail"]
    assert c.put("/api/suite-admin/settings/iopix/NOPE", json={"value": "1"}).status_code == 404
    assert c.put("/api/suite-admin/settings/iopix/EDITING", json={"value": ""}).json()["value"] == ""
    assert c.get("/api/suite-admin/addresses").json()["copy"] == "home"
    # a restart is left for the apps named; each copy picks its own up
    assert c.post("/api/suite-admin/restart", json={"apps": ["iopix"]}).json() == {"asked": ["iopix"]}
    rows = db.q("SELECT copy, action, requested_by FROM ios_copies")
    assert rows == [{"copy": "nas", "action": "restart", "requested_by": "alex"}]  # one row per copy, not per app
    assert c.post("/api/suite-admin/restart").json() == {"asked": ["iocalendar", "iopix", "iostart"]}


# ---- the log viewer
def stamp(seconds_ago=0.0):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - seconds_ago)) + ",000"


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    path = tmp_path / "iosuite.log"
    monkeypatch.setattr(config, "LOG_FILE", path)
    path.write_text(f"{stamp(30)} INFO [iocalendar] iocalendar.api: here, first\n{stamp(10)} WARNING [iostart] iostart.api: here, second\n")
    return path


def other_copy(monkeypatch, answer):
    """The other copy's answer to /api/suite-admin/logs?local=1, and what it was asked."""
    asked = []

    def as_viewer(request, app, path, params=None, **kw):
        asked.append((app, path, dict(params or {})))
        if isinstance(answer, Exception):
            raise answer
        return answer(params or {}) if callable(answer) else answer
    monkeypatch.setattr("iosuite_shared.links.as_viewer", as_viewer)
    return asked


def test_every_copy_s_lines_are_on_one_timeline(two_copies, log_file, monkeypatch):
    nas = {"copy": "whatever it calls itself", "file": "/opt/iosuite/data/iosuite.log", "size": 99, "cursor": "7:99", "more": False, "lines": [
        {"ts": time.time() - 20, "time": "x", "level": "ERROR", "app": "iopix", "logger": "iopix.scan", "text": "there, between"},
        {"ts": 0.0, "time": "", "level": "", "app": "-", "logger": "", "text": "the end of a record cut off"},
        {"ts": time.time() - 5, "time": "x", "level": "INFO", "app": "iopix", "logger": "iopix.scan", "text": "there, last"}]}
    asked = other_copy(monkeypatch, nas)
    got = admin.logs(None, level="any")
    assert [(r["copy"], r["text"]) for r in got["lines"]] == [
        ("home", "here, first"), ("nas", "there, between"), ("home", "here, second"), ("nas", "the end of a record cut off"), ("nas", "there, last")]
    assert got["here"] == "home" and not got["more"] and got["cursors"]["nas"] == "7:99" and got["cursors"]["home"].endswith(f":{log_file.stat().st_size}")
    assert [(c["copy"], c["apps"], c["reachable"]) for c in got["copies"]] == [("home", ["iocalendar", "iostart"], True), ("nas", ["iopix"], True)]
    assert got["apps"] == [{"app": "iocalendar", "name": "ioCalendar"}, {"app": "iopix", "name": "ioPix"}, {"app": "iostart", "name": "ioStart"}]
    assert asked == [("iopix", "/api/suite-admin/logs", {"level": "any", "limit": 300, "local": 1})]


def test_the_filters_and_the_cursors_go_to_every_copy(two_copies, log_file, monkeypatch):
    asked = other_copy(monkeypatch, {"file": "", "size": 0, "cursor": "7:120", "more": False, "lines": []})
    mine = logs.read()["cursor"]
    got = admin.logs(None, {"home": mine, "nas": "7:99"}, 50, app="iopix", level="error", contains="scan", requests=True, since=0, until=0)
    assert got["lines"] == [] and got["cursors"] == {"home": mine, "nas": "7:120"}
    assert asked[0][2] == {"app": "iopix", "level": "error", "contains": "scan", "requests": 1, "limit": 50, "local": 1, "after": "7:99"}


def test_a_copy_that_does_not_answer_is_said_and_the_rest_is_shown(two_copies, log_file, monkeypatch):
    other_copy(monkeypatch, OSError("no route to host"))
    got = admin.logs(None, {"nas": "7:99"})
    assert [r["text"] for r in got["lines"]] == ["here, first", "here, second"]
    nas = got["copies"][1]
    assert nas["copy"] == "nas" and nas["reachable"] is False and "did not answer" in nas["note"]
    assert got["cursors"]["nas"] == "7:99"  # where it was: followed again from there once it is back


def test_the_newest_lines_of_all_copies_are_kept(two_copies, log_file, monkeypatch):
    other_copy(monkeypatch, {"file": "", "size": 0, "cursor": "7:1", "more": False,
                             "lines": [{"ts": time.time() - 20, "time": "x", "level": "INFO", "app": "iopix", "logger": "iopix", "text": "there"}]})
    got = admin.logs(None, limit=2)
    assert [r["text"] for r in got["lines"]] == ["there", "here, second"] and got["more"]


def test_one_copy_asks_nobody(log_file, monkeypatch):
    monkeypatch.setattr(suite, "copy_name", lambda: "home")
    suite.register("iostart", "ioStart", copy="home")
    asked = other_copy(monkeypatch, {})
    got = admin.logs(None)
    assert len(got["lines"]) == 2 and [c["copy"] for c in got["copies"]] == ["home"] and asked == []


def test_the_log_endpoint(two_copies, log_file, monkeypatch):
    users.create("alex", "secret123", suite_admin=True)
    asked = other_copy(monkeypatch, {"file": "", "size": 0, "cursor": "7:1", "more": False, "lines": []})
    c = signed_in(make_app("iocalendar"), "alex")
    got = c.get("/api/suite-admin/logs").json()
    assert got["app"] == "iocalendar" and got["here"] == "home"  # the screen opens on the app it was opened from
    assert [r["text"] for r in got["lines"]] == ["here, first", "here, second"]  # signing in is the auth log's, which is not in this file
    got = c.get("/api/suite-admin/logs", params={"app": "iostart", "level": "warning", "after": json.dumps({"nas": "7:1"})}).json()
    assert [r["text"] for r in got["lines"]] == ["here, second"] and asked[-1][2]["after"] == "7:1" and asked[-1][2]["app"] == "iostart"
    assert c.get("/api/suite-admin/logs", params={"after": "not json"}).status_code == 200
    # what another copy asks: this copy's own lines, nobody else asked
    n = len(asked)
    got = c.get("/api/suite-admin/logs", params={"local": 1, "contains": "FIRST"}).json()
    assert got["copy"] == "home" and [r["text"] for r in got["lines"]] == ["here, first"] and "copies" not in got and len(asked) == n
    again = c.get("/api/suite-admin/logs", params={"local": 1, "after": got["cursor"]}).json()
    assert again["lines"] == []


# ---- the command
def run(*argv):
    said = []
    a = cli._parser().parse_args(list(argv))
    {"set": cli.set_cmd, "settings": cli.settings_cmd, "apps": cli.apps_cmd}[a.cmd](a, out=said.append)
    return "\n".join(said)


def test_the_command_sets_what_the_screen_sets():
    assert "TZ of the whole suite is Europe/Brussels" in run("set", "suite", "TZ", "Europe/Brussels")
    assert "EDITING of iopix is 0" in run("set", "iopix", "EDITING", "off")
    assert "systemctl restart iosuite" in run("set", "iopix", "THUMB_HEIGHT", "480")
    assert db.settings_of("") == {"TZ": "Europe/Brussels"} and db.settings_of("iopix") == {"EDITING": "0", "THUMB_HEIGHT": "480"}
    assert "is removed (the default applies)" in run("set", "iopix", "THUMB_HEIGHT") and "THUMB_HEIGHT" not in db.settings_of("iopix")
    for argv, says in ((("set", "iopix", "THUMB_HEIGHT", "tall"), "whole number"), (("set", "iopix", "NOPE", "1"), "No such setting: NOPE"),
                       (("set", "nosuchapp", "TZ", "UTC"), "No such app")):
        with pytest.raises(SystemExit, match=says):
            run(*argv)


def test_the_command_lists_the_settings():
    db.set_setting("TZ", "Europe/Brussels")
    db.set_setting("EDITING", "0", "iopix")
    all_of_it = run("settings")
    assert "suite:" in all_of_it and "Europe/Brussels" in all_of_it and "iopix:" in all_of_it and "iocalendar:" not in all_of_it
    assert "(default: 90)" in all_of_it and "apps with nothing set are left out" in all_of_it
    one = run("settings", "iocalendar")
    assert one.startswith("iocalendar:") and "HOLIDAYS_COUNTRY" in one and "suite:" not in one
    assert "COOKIE_DOMAIN" in run("settings", "suite") and "iopix:" not in run("settings", "suite")
    with pytest.raises(SystemExit, match="no such app"):
        run("settings", "nosuchapp")


def test_the_command_says_which_apps_run_where(two_copies, monkeypatch):
    monkeypatch.setattr("iosuite_shared.host.names", lambda given=None: ["iostart", "iocalendar"])
    monkeypatch.setattr(config, "APPS", ["iostart", "iocalendar"])
    said = run("apps")
    assert "this machine (home) runs: iostart, iocalendar" in said and "APPS is not set" not in said
    lines = {x.split()[0]: x for x in said.splitlines()[1:]}
    assert "here" in lines["iocalendar"] and "https://calendar.example.com  on home" in lines["iocalendar"]
    assert "here" not in lines["iopix"] and "on nas" in lines["iopix"] and "not running anywhere yet" in lines["iomoney"]


def test_the_command_s_words():
    p = cli._parser()
    assert p.parse_args(["serve", "--apps", "iopix"]).apps == "iopix" and p.parse_args(["--config", "/etc/iosuite", "check"]).config == "/etc/iosuite"
    assert isinstance(p.parse_args(["set", "suite", "TZ"]), argparse.Namespace) and p.parse_args(["set", "suite", "TZ"]).value == ""
    for words in (["apps"], ["settings"], ["init"], ["list"], ["admin", "alex"], ["sign-in-reset", "alex"], ["edge"], ["demo"],
                  ["provision", "--admin", "root"], ["stack", "--set", "suite.TZ=UTC", "--", "iosuite", "serve"]):
        assert p.parse_args(words).cmd == words[0]

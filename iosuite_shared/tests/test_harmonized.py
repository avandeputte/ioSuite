"""What every app gets the same way since 0.11.0: the public status, install() (400 for bad input, the headers, the body
cap), the MCP gate and helpers, the log set-up, the standard settings and the test helpers."""
import json

import iosuite_shared
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from iosuite_shared import db, testing, users
from iosuite_shared import mcp as shared_mcp
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater


class FakeUpdater:
    version = "1.2.3"

    def local_commit(self):
        return "abcdef0123"


def make_app(mcp_on=lambda: True, seen=None, **install):
    auth = Auth("iotest", app_label="ioTest", version="1.2.3", register=False)
    app = FastAPI()
    updater = FakeUpdater()
    gate = auth.mcp_gate(mcp_on, on_user=seen.append if seen is not None else None)
    app.middleware("http")(auth.middleware(open_paths=("/",), open_prefixes=("/mcp",), before=gate))
    app.include_router(auth.router())
    app.include_router(auth.status_router(updater, extra=lambda request: {"mine": users.is_admin(request.state.user)}))
    auth.install(app, **install)

    @app.get("/")
    def index():
        return {"page": True}

    @app.post("/api/echo", dependencies=[auth.access.public])
    async def echo(request: Request):
        return {"n": len(await request.body())}

    @app.get("/api/boom", dependencies=[auth.access.public])
    def boom():
        raise ValueError("a word where a number belongs")

    @app.get("/api/gone", dependencies=[auth.access.public])
    def gone():
        raise HTTPException(404, "No such thing")

    @app.post("/mcp", dependencies=[auth.access.public])
    def mcp():
        return {"mcp": True}
    return app, auth, updater


def test_status_is_public_and_the_same_shape_everywhere():
    app, auth, updater = make_app()
    c = TestClient(app, base_url="http://test.example.com")
    s = c.get("/api/status").json()
    # no accounts yet: the install is open, so a visitor counts as signed in and admin (the suite's rule), and sees the commit
    assert s == {"ok": True, "app": "iotest", "name": "ioTest", "version": "1.2.3", "usersExist": False, "requireLogin": False, "signedIn": True,
                 "isAdmin": True, "viaProxy": False, "user": None, "mine": True, "commit": "abcdef0"}
    c.post("/api/auth/setup", json={"name": "alex", "password": "secret123", "email": "a@b.c"})
    s = c.get("/api/status").json()
    assert s["user"] == {"id": 1, "name": "alex", "displayName": "alex", "email": "a@b.c", "role": "admin", "suiteAdmin": True, "passwordless": False}
    assert s["signedIn"] and s["isAdmin"] and s["mine"] and s["commit"] == "abcdef0" and s["usersExist"]
    assert "update" not in s  # updating is the suite's: Settings › Servers › Updates
    # sign-in required: the status still answers a visitor, with nothing about the install
    db.set_setting("require_login", "1", "iotest")
    v = TestClient(app, base_url="http://test.example.com")
    s = v.get("/api/status").json()
    assert s["requireLogin"] and s["usersExist"] and s["user"] is None and "commit" not in s and "update" not in s
    assert v.get("/api/echo").status_code == 401


def test_install_answers_bad_input_with_400_and_sets_the_headers():
    app, _, _ = make_app()
    c = TestClient(app)
    r = c.get("/api/boom")
    assert r.status_code == 400 and r.json() == {"detail": "Bad request: a word where a number belongs"}
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "same-origin"
    assert c.get("/").headers["cache-control"] == "no-cache"
    r = c.post("/api/echo", content=b"{", headers={"content-type": "application/json"})
    assert r.status_code == 200  # the route read the raw body itself; malformed JSON is a 400 only where a route parses it


def test_install_caps_the_body_by_length_and_as_it_arrives():
    app, _, _ = make_app(limit_for=lambda path, ctype: 64 if ctype == "application/json" else 1024)
    c = TestClient(app)
    assert c.post("/api/echo", content=b"x" * 64, headers={"content-type": "application/json"}).json() == {"n": 64}
    r = c.post("/api/echo", content=b"x" * 65, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["detail"] == "That request is too large"
    assert c.post("/api/echo", content=b"x" * 1000, headers={"content-type": "application/octet-stream"}).json() == {"n": 1000}
    assert c.post("/api/echo", content=b"x", headers={"content-length": "abc"}).status_code == 400

    def chunks():
        for _ in range(3):
            yield b"y" * 40
    r = c.post("/api/echo", content=chunks(), headers={"content-type": "application/json"})  # chunked: no Content-Length to check first
    assert r.status_code == 413


def test_mcp_gate_switch_sign_in_and_the_context():
    on = {"v": False}
    seen = []
    app, _, _ = make_app(mcp_on=lambda: on["v"], seen=seen)
    c = TestClient(app, base_url="http://test.example.com")
    r = c.post("/mcp", json={})
    assert r.status_code == 404 and "switched off (Settings › Apps)" in r.json()["detail"]
    on["v"] = True
    assert c.post("/mcp", json={}).status_code == 401  # an assistant always signs in, even before the first account exists
    c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
    assert c.post("/mcp", json={}).status_code == 200  # the session cookie is a sign-in too
    v = TestClient(app, base_url="http://test.example.com")
    r = v.post("/mcp", json={})
    assert r.status_code == 401 and "app password" in r.json()["detail"] and "Bearer" in r.headers["www-authenticate"]
    pw = c.post("/api/auth/app-passwords", json={"label": "Claude"}).json()["password"]
    assert v.post("/mcp", json={}, headers={"authorization": f"Bearer {pw}"}).status_code == 200
    assert seen[-1]["name"] == "alex"
    db.set_setting("require_login", "0", "iotest")
    assert v.post("/api/echo", json={}).status_code == 200  # the gate touches /mcp only


def test_mcp_helpers():
    from mcp.server.mcpserver.exceptions import ToolError
    assert shared_mcp.clamp("7", 1, 5) == 5 and shared_mcp.clamp(None, 1, 5) == 1 and shared_mcp.clamp(3, 1, 5) == 3
    # the switch is one row per app in the Shared ioSuite database, set under Settings › Apps
    switch = shared_mcp.Switch("iotest", "what it offers")
    assert shared_mcp.enabled_for("iotest") is False and switch.enabled() is False
    shared_mcp.set_for("iotest", True)
    assert switch.enabled() and switch.info() == {"mcpEnabled": True, "mcpAbout": "what it offers"}
    assert shared_mcp.switches()["iotest"] is True
    shared_mcp.set_for("iocalendar", False)
    assert shared_mcp.switches() == {"iotest": True, "iocalendar": False}  # one app's switch is not another's
    shared_mcp.set_for("iotest", None)  # no row of its own: the app follows the suite's switch
    assert "iotest" not in shared_mcp.switches() and switch.enabled() is False
    db.set_setting(shared_mcp.SETTING, "1", "")
    assert switch.enabled() is True
    db.set_setting(shared_mcp.SETTING, None, "")
    shared_mcp.set_for("iotest", False)
    assert not switch.enabled()
    with pytest.raises(ToolError):
        shared_mcp.who()
    users.create("alex", "secret123", "admin", "iotest", suite_admin=True)  # once accounts exist, roles count
    shared_mcp.current_user.set({"id": 2, "name": "bob", "role": "viewer"})
    assert shared_mcp.who()["name"] == "bob"
    with pytest.raises(ToolError):
        shared_mcp.need_admin()
    shared_mcp.current_user.set({"id": 1, "name": "alex", "role": "admin"})
    assert shared_mcp.need_admin()["name"] == "alex"
    shared_mcp.current_user.set(None)


def test_mcp_server_mounts_ahead_of_the_routes():
    server = shared_mcp.make_server("iotest", instructions="Testing.", app_tools=False)

    @server.tool(annotations=shared_mcp.READ_ONLY)
    def hello() -> str:
        return "hi"
    app = FastAPI()

    @app.get("/mcp")
    def shadow():
        return {"shadowed": True}
    shared_mcp.mount(app, server)
    assert app.router.routes[0].path == "/mcp" and len([r for r in app.router.routes if r.path == "/mcp"]) == 2


def test_check_access_declared_names_the_route_without_a_marker():
    app, auth, _ = make_app()

    @app.get("/api/open")
    def open_route():
        return {}
    with pytest.raises(AssertionError) as e:
        testing.check_access_declared(app, auth.access.declared)
    assert "/api/open" in str(e.value) and "/api/echo" not in str(e.value)


def test_check_conventions(tmp_path):
    root = tmp_path / "iocalendar"
    (root / "static").mkdir(parents=True)
    (root / "app.json").write_text('{"key": "iocalendar"}')
    (root / "static" / "app.js").write_text("fetch('api/events')\n")
    testing.check_conventions(root, "iocalendar", iosuite_shared.__version__, None)
    with pytest.raises(AssertionError):
        testing.check_conventions(root, "iocalendar", "0.0.1", None)
    (root / "config.env.example").write_text("PORT=8620\n")
    with pytest.raises(AssertionError):
        testing.check_conventions(root, "iocalendar", iosuite_shared.__version__, None)
    (root / "config.env.example").unlink()
    (root / "static" / "app.js").write_text("fetch('/api/events')\n")
    with pytest.raises(AssertionError):
        testing.check_conventions(root, "iocalendar", iosuite_shared.__version__, None)


def test_clean_shared_tables():
    users.create("alex", "secret123", "admin", "iotest", suite_admin=True)
    users.create("bob", "secret123", "viewer", "iotest")
    auth = Auth("iotest", register=False)
    auth._registered = True
    testing.clean_shared_tables(auth)
    assert not users.any_users() and not auth._registered
    assert users.create("carol", "secret123", "admin", "iotest")["id"] == 1


def test_updater_is_what_status_router_expects(tmp_path):
    u = Updater("1.0", tmp_path)
    for name in ("local_commit", "can_run", "in_docker"):
        assert callable(getattr(u, name))
    assert json.dumps(u.status())


def test_check_access_declared_sees_through_included_routers():
    """FastAPI 0.162 keeps an included router as one entry of app.routes: the check must still reach its routes, and
    must never pass because it found nothing to check."""
    from fastapi import APIRouter, FastAPI
    from iosuite_shared.fastapi import Auth
    auth = Auth("t", register=False)
    r = APIRouter()

    @r.get("/open")
    def open_route():
        return {}

    @r.get("/closed", dependencies=[auth.access.admin])
    def closed_route():
        return {}
    app = FastAPI()
    app.include_router(r, prefix="/api")
    assert {p for _m, p, _r in testing.api_routes(app)} >= {"/api/open", "/api/closed"}
    with pytest.raises(AssertionError, match="/api/open"):
        testing.check_access_declared(app, auth.access.declared)
    with pytest.raises(AssertionError, match="nothing was checked"):
        testing.check_access_declared(app, auth.access.declared, prefix="/nothing/")
    testing.check_access_declared(app, auth.access.declared, ignore=("/api/open",))


# ---- one command line: iosuite <app> <command> (iosuite_shared.appcli)
def test_every_app_answers_check_and_migrate_and_its_own_commands():
    """Each app had a cli.py that repeated migrate and check; they are the shared ones now, and an app's own
    commands come from its commands.py."""
    from iosuite_shared import appcli, catalog
    for key in catalog.APPS:
        names = set(appcli._parser(key)._subparsers._group_actions[0].choices)
        assert {"migrate", "check"} <= names, key
    assert "import" in set(appcli._parser("iotask")._subparsers._group_actions[0].choices)
    assert "sync-holidays" in set(appcli._parser("iocalendar")._subparsers._group_actions[0].choices)


def test_the_suite_command_hands_an_app_key_to_the_app(monkeypatch):
    from iosuite_shared import appcli, cli
    seen = []
    monkeypatch.setattr(appcli, "run", lambda key, argv: seen.append((key, argv)) or 0)
    assert cli.main(["iocalendar", "check"]) == 0 and seen == [("iocalendar", ["check"])]


def test_check_says_the_accounts_and_what_the_app_has(capsys):
    from iosuite_shared import appcli
    said = appcli._check(testing.StandIn("iotest", counts=lambda: {"notes": 3, "warning": "packets are small", "rev": None}))
    out = capsys.readouterr().out
    assert said == 0 and "0 account(s), 3 notes" in out and "note: packets are small" in out and "rev" not in out


def test_an_app_declares_what_it_has_in_its_tables_once():
    """`iosuite <app> check` and the app's diagnostics tool read the same numbers (<app>/db.py: counts)."""
    from iosuite_shared import app as declared, catalog
    for key in catalog.APPS:
        a = declared.of(key)
        if a.has("db"):
            assert callable(a.counts), f"{key}/db.py has no counts()"

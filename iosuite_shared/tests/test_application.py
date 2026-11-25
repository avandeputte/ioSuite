"""What every app has in the same words, kept once: its database (db.AppDatabase), the accounts as it sees them
(users.AppUsers), who a local MCP server acts as and what its diagnostics say (mcp.stdio_user, diagnostics,
account_list), and the app as a FastAPI application (application.create)."""
from types import SimpleNamespace

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from iosuite_shared import application, db, mcp as shared_mcp, testing, users
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

TABLES = ["CREATE TABLE IF NOT EXISTS zap_things (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL)",
          "CREATE TABLE IF NOT EXISTS zap_state (name VARCHAR(64) PRIMARY KEY, value MEDIUMTEXT)"]


def _config(name="iosuite_shared_app_test"):
    c = testing.fresh_database(name)
    return SimpleNamespace(DB_HOST=c["host"], DB_PORT=c["port"], DB_USER=c["user"], DB_PASSWORD=c["password"], DB_NAME=c["database"])


# ------------------------------------------------------------------ an app's own database

def test_an_app_s_database_makes_its_tables_keeps_its_own_notes_and_says_its_version():
    d = db.AppDatabase(_config(), "zap", TABLES, 3)
    seeded = []
    d.migrate(after=lambda cur: seeded.append(cur.execute("INSERT INTO zap_things (name) VALUES ('first')")))
    assert seeded == [1], "what an app cannot be without is written in the same transaction as its tables"
    assert d.schema_version() == 3
    assert d.one("SELECT name FROM zap_things")["name"] == "first"
    # what the app wrote down for itself (zap_state); a person's settings are the suite's one home for them
    assert d.get_state("synced") is None and d.get_state("synced", "never") == "never"
    d.set_state("synced", "yesterday")
    d.set_state("synced", "just now")
    assert d.get_state("synced") == "just now"
    d.set_state("synced", None)
    assert d.get_state("synced", "never") == "never"
    d.migrate()  # a second start changes nothing
    assert d.q("SELECT count(*) AS n FROM zap_things")[0]["n"] == 1


def test_the_tables_can_be_asked_for_at_start_and_the_database_is_read_from_the_config_each_time():
    config = _config()
    asked = []
    d = db.AppDatabase(config, "zap", lambda: asked.append(1) or TABLES, 1)
    assert asked == [], "nothing is asked before the app starts"
    d.migrate()
    assert asked == [1]
    other = _config("iosuite_shared_app_test2")
    config.DB_NAME = other.DB_NAME   # a test, or a copy set up again, names another database
    assert d.connect().db == b"iosuite_shared_app_test2"


def test_a_database_that_is_missing_is_made_and_reset_all_drops_only_the_app_s_tables():
    config = _config()
    with db.AppDatabase(config, "zap", TABLES, 1).tx() as con, con.cursor() as cur:
        cur.execute("DROP DATABASE `iosuite_shared_app_test`")
    d = db.AppDatabase(config, "zap", TABLES, 1)
    d.migrate()
    d.ex("CREATE TABLE other_app (id INT PRIMARY KEY)")
    d.reset_all()
    assert [list(r.values())[0] for r in d.q("SHOW TABLES")] == ["other_app"]


def test_marks_are_the_placeholders_of_a_list():
    assert db.marks(3) == "%s,%s,%s"
    assert db.marks(0) == "NULL", "IN (NULL) matches nothing, where IN () is an error"


# ------------------------------------------------------------------ the accounts as an app sees them

def test_an_app_s_accounts_come_with_the_role_they_hold_there_in_name_order():
    users.create("Zoe", "secret123", role="admin", app="iotask")
    users.create("adam", "secret123", role="viewer", app="iotask")
    u = users.AppUsers("iotask")
    u.init()
    assert [(x["name"], x["role"]) for x in u.all_users()] == [("adam", "viewer"), ("Zoe", "admin")]
    assert u.find("ZOE")["role"] == "admin" and u.get(u.find("adam")["id"])["name"] == "adam"
    assert u.find("nobody") is None
    assert users.AppUsers("iorecipe").find("adam")["role"] != "admin"


def test_an_app_that_is_not_for_everyone_writes_its_default_role_once():
    u = users.AppUsers("iomoney", default_role="none")
    u.init()
    assert db.get_setting("default_role", None, "iomoney") == "none"
    db.set_setting("default_role", "viewer", "iomoney")  # a suite admin opened it to everyone
    users.AppUsers("iomoney", default_role="none").init()
    assert db.get_setting("default_role", None, "iomoney") == "viewer", "a later start leaves the admin's choice alone"
    users.AppUsers("iotask").init()
    assert db.one("SELECT 1 AS x FROM ios_settings WHERE app = 'iotask' AND name = 'default_role'") is None


# ------------------------------------------------------------------ a local MCP server

ACCOUNTS = [{"id": 1, "name": "morgan", "email": "morgan@example.com", "role": "admin"},
            {"id": 2, "name": "riley", "email": "", "role": "editor"},
            {"id": 3, "name": "theo", "email": "", "role": "none"}]


def test_a_local_mcp_server_acts_as_the_named_account_or_the_only_admin():
    assert shared_mcp.stdio_user("iotask", "", ACCOUNTS, argv=[])["name"] == "morgan", "the only admin"
    assert shared_mcp.stdio_user("iotask", "Riley", ACCOUNTS, argv=[])["name"] == "riley", "MCP_USER"
    assert shared_mcp.stdio_user("iotask", "riley", ACCOUNTS, argv=["--user", "MORGAN@example.com"])["name"] == "morgan", "--user wins"


@pytest.mark.parametrize("named, argv, accounts, says", [
    ("ghost", [], ACCOUNTS, "no ioTask account named 'ghost'"),
    ("theo", [], ACCOUNTS, "has no access to ioTask"),
    ("", [], ACCOUNTS + [{"id": 4, "name": "ava", "role": "admin"}], "name the account: iosuite mcp iotask --user NAME"),
    ("", [], [], "name the account"),
])
def test_a_local_mcp_server_ends_with_why_when_it_cannot_tell_who_it_is(named, argv, accounts, says):
    with pytest.raises(SystemExit) as e:
        shared_mcp.stdio_user("iotask", named, accounts, argv=argv)
    assert says in str(e.value)


def test_before_any_account_exists_an_app_may_say_who_its_local_mcp_server_is():
    owner = {"id": 0, "name": "owner", "role": "admin"}
    assert shared_mcp.stdio_user("iopix", "", [], argv=[], open_install=owner) is owner
    assert shared_mcp.stdio_user("iopix", "", ACCOUNTS, argv=[], open_install=owner)["name"] == "morgan"


def _for_diagnostics(db_module, mcp_on=True, accounts=ACCOUNTS):
    config = SimpleNamespace(APP_DIR="/opt/iosuite", PUBLIC_URL="", DB_HOST="db", DB_PORT=3306, DB_NAME="things")
    updater = SimpleNamespace(version="4.1.0", local_commit=lambda: "0123456789abcdef", in_docker=lambda: False,
                              status=lambda: {"available": False})
    return testing.StandIn("iotest", config=config, updater=updater, mcp_enabled=lambda: mcp_on,
                           modules={"db": db_module, "users": SimpleNamespace(all_users=lambda: accounts)})


def test_diagnostics_say_the_same_in_every_app_and_a_database_that_is_down_is_an_error_line():
    good = SimpleNamespace(one=lambda sql: {"v": "11.4.2-MariaDB"}, schema_version=lambda: 7)
    out = shared_mcp.app_diagnostics(_for_diagnostics(good), counts=lambda: {"things": 12}, currency="EUR")
    assert out["version"] == "4.1.0" and out["commit"] == "0123456" and out["publicUrl"] is None and out["currency"] == "EUR"
    assert out["database"] == {"host": "db:3306", "name": "things", "server": "11.4.2-MariaDB", "schema": 7, "things": 12}
    assert out["mcp"] == {"enabled": True} and out["accounts"][1] == {"name": "riley", "role": "editor"}

    def down(sql):
        raise OSError("connection refused")
    out = shared_mcp.app_diagnostics(_for_diagnostics(SimpleNamespace(one=down), mcp_on=False, accounts=[]))
    assert out["database"] == {"error": "connection refused"} and out["accounts"] == []


def test_the_account_list_tool_names_each_account_with_its_role():
    assert shared_mcp.account_list(ACCOUNTS[:2]) == [
        {"name": "morgan", "displayName": None, "email": "morgan@example.com", "role": "admin"},
        {"name": "riley", "displayName": None, "email": None, "role": "editor"}]


# ------------------------------------------------------------------ the app as a FastAPI application

class Forbidden(Exception):
    pass


class Handle:
    def __init__(self, seen, name, how="cancel"):
        setattr(self, how, lambda: seen.append(f"{name} {how}"))


def _app(monkeypatch, seen, app="iotask", **more):
    auth = Auth(app)
    updater = Updater("1.2.3", user_agent=app)
    monkeypatch.setattr(updater, "start_daily", lambda: seen.append("daily check"))
    monkeypatch.setattr("iosuite_shared.demo.at_start", lambda a: seen.append(f"demo {a}"))
    r = APIRouter()

    @r.get("/api/things", dependencies=[auth.access.signed_in])
    def things():
        return {"ok": True}

    @r.get("/api/locked", dependencies=[auth.access.public])
    def locked():
        raise Forbidden("not yours")

    @r.get("/dav/x", dependencies=[auth.access.public])
    def dav():
        return {"dav": True}

    config = SimpleNamespace(DB_HOST="db", DB_PORT=3306, DB_NAME="tasks")
    stand_in = testing.StandIn(app, config=config, auth=auth, updater=updater, prepare=more.pop("prepare", ()))
    return application.create(stand_in, description="A test app.", routers=(r,), page=False,
                              forbidden=(Forbidden,), **more)


def test_an_app_starts_and_stops_in_the_order_every_app_had_it(monkeypatch):
    seen = []

    async def later():
        seen.append("start async")
        return Handle(seen, "server", "close")

    def nothing_to_hold():
        seen.append("start plain")

    app = _app(monkeypatch, seen,
               prepare=(lambda: seen.append("tables"), lambda: seen.append("accounts")),
               start=(later, nothing_to_hold),
               jobs=lambda: seen.append("jobs") or [Handle(seen, "job"), None],
               stop=(lambda: seen.append("stop"),))
    assert seen == [], "nothing happens until the host starts the app"
    with TestClient(app):
        assert seen == ["tables", "accounts", "demo iotask", "start async", "start plain", "daily check", "jobs"]
        del seen[:]
    assert seen == ["server close", "job cancel", "stop"]


def test_what_was_started_is_stopped_when_a_later_step_fails(monkeypatch):
    seen = []

    def jobs():
        raise RuntimeError("no runner")
    app = _app(monkeypatch, seen, start=(lambda: Handle(seen, "server", "close"),), jobs=jobs, stop=(lambda: seen.append("stop"),))
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass
    assert seen[-2:] == ["server close", "stop"]


def test_the_routes_every_app_answers_its_own_and_the_403_of_its_exceptions(monkeypatch):
    app = _app(monkeypatch, [], status=lambda request: {"timezone": "Europe/Brussels"})
    with TestClient(app, base_url="http://tasks.example.com") as c:
        s = c.get("/api/status").json()
        assert s["version"] == "1.2.3" and s["timezone"] == "Europe/Brussels"
        assert c.get("/api/things").status_code == 200, "no accounts yet: open"
        r = c.get("/api/locked")
        assert r.status_code == 403 and r.json() == {"detail": "not yours"}
        assert c.get("/api/docs").status_code == 200 and c.get("/api/openapi.json").json()["info"]["title"] == "ioTask"
        paths = {path for _methods, path, _route in testing.api_routes(app)}
        assert {"/api/auth/me", "/api/live", "/api/status"} <= paths and any(p.startswith("/api/related") for p in paths)


def test_what_the_manifest_lists_as_sync_is_open_to_a_client_that_signs_in_on_its_own(monkeypatch):
    app = _app(monkeypatch, [])           # ioTask's app.json: "/dav" and "/.well-known/"
    with TestClient(app, base_url="http://tasks.example.com") as c:
        assert c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"}).status_code == 200
    with TestClient(app, base_url="http://tasks.example.com") as visitor:
        assert visitor.get("/api/things").status_code == 401
        assert visitor.get("/dav/x").json() == {"dav": True}
    other = _app(monkeypatch, [], app="iorecipe")   # no sync paths of its own
    with TestClient(other, base_url="http://recipes.example.com") as visitor:
        assert visitor.get("/dav/x").status_code == 401
    opened = _app(monkeypatch, [], app="iorecipe", open_prefixes=("/dav",))
    with TestClient(opened, base_url="http://recipes.example.com") as visitor:
        assert visitor.get("/dav/x").json() == {"dav": True}


def test_an_app_without_the_linked_panel_has_no_related_routes(monkeypatch):
    app = _app(monkeypatch, [], app="iodns", related=False)
    paths = {path for _methods, path, _route in testing.api_routes(app)}
    assert "/api/status" in paths and not any(p.startswith("/api/related") for p in paths)

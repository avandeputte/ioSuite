from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import db, suite, users
from iosuite_shared.fastapi import Auth


def make_app(name, **kw):
    auth = Auth(name, app_label=kw.pop("label", name), **kw)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_paths=("/",)))
    app.include_router(auth.router())

    @app.get("/api/x", dependencies=[auth.access.public])
    def x():
        return {"ok": True}
    return app, auth


def test_register_keeps_one_row_and_clears_what_the_app_no_longer_says():
    suite.register("iopix", "ioPix", url="https://photo.example.com/", version="1.0", color="#3b4a8c")
    r = suite.get("iopix")
    assert r["url"] == "https://photo.example.com" and r["configuredUrl"] == "https://photo.example.com"
    assert r["icon"] == "https://photo.example.com/static/icons/mark.svg" and r["version"] == "1.0"
    suite.register("iopix", "ioPix", version="1.1")
    r = suite.get("iopix")
    assert r["url"] is None and r["version"] == "1.1" and r["color"] is None
    assert [a["app"] for a in suite.apps()] == ["iopix"]
    assert suite.forget("iopix") and suite.apps() == [] and not suite.forget("iopix")


def test_bad_url_is_refused():
    import pytest
    with pytest.raises(ValueError):
        suite.register("iopix", "ioPix", url="photo.example.com")


def test_rank_prefers_the_shared_domain_over_https(monkeypatch):
    __import__("iosuite_shared.db").db.set_setting("COOKIE_DOMAIN", "example.com")
    assert suite._rank("http://localhost:8600") == -1
    assert suite._rank("http://127.0.0.1:8600") == -1
    assert suite._rank("http://testserver") == -1
    assert suite._rank("http://192.168.1.89:8600") == 0
    assert suite._rank("http://[fd00::1]:8600") == 0
    assert suite._rank("http://nas:8600") == 1
    assert suite._rank("https://photo.example.com") == 3
    assert suite._rank("https://photo.example.com") > suite._rank("http://nas.lan:8600")


def test_middleware_registers_and_notes_the_best_address(monkeypatch):
    __import__("iosuite_shared.db").db.set_setting("COOKIE_DOMAIN", "example.com")
    suite.invalidate()
    app, _ = make_app("iocalendar", label="ioCalendar", version="0.4.0", color="#963522")
    TestClient(app, base_url="http://testserver").get("/api/x")
    r = suite.get("iocalendar")
    assert r["name"] == "ioCalendar" and r["version"] == "0.4.0" and r["url"] is None  # a test host is never kept
    TestClient(app, base_url="http://192.168.1.89:8620").get("/api/x")
    assert suite.get("iocalendar")["url"] == "http://192.168.1.89:8620"
    TestClient(app, base_url="http://calendar.lan:8620").get("/api/x")
    assert suite.get("iocalendar")["url"] == "http://calendar.lan:8620"
    # through a reverse proxy: believed once its address is listed (before that its visitors count as outside)
    c = TestClient(app, base_url="http://10.0.0.5:8620", client=("10.0.0.7", 40000))
    fwd = {"x-forwarded-proto": "https", "x-forwarded-host": "calendar.example.com"}
    assert c.get("/api/x", headers=fwd).status_code == 403
    assert suite.get("iocalendar")["url"] == "http://calendar.lan:8620"
    db.set_setting("auth_proxy_trusted", "10.0.0.7", "")
    db.settings_cache.clear()
    assert c.get("/api/x", headers=fwd).status_code == 200
    assert suite.get("iocalendar")["url"] == "https://calendar.example.com"
    assert suite.get("iocalendar")["icon"] == "https://calendar.example.com/static/icons/mark.svg"
    TestClient(app, base_url="http://192.168.1.89:8620").get("/api/x")  # a worse address does not replace it
    assert suite.get("iocalendar")["url"] == "https://calendar.example.com"


def test_configured_url_wins_and_register_false_stays_out():
    suite.invalidate()
    app, _ = make_app("iopix", label="ioPix", public_url="https://photo.example.com")
    TestClient(app, base_url="http://192.168.1.89:8600").get("/api/x")
    r = suite.get("iopix")
    assert r["url"] == "https://photo.example.com" and r["seenUrl"] == "http://192.168.1.89:8600"
    other, _ = make_app("tool", register=False)
    TestClient(other, base_url="http://192.168.1.89:9000").get("/api/x")
    assert suite.get("tool") is None


def test_bad_public_url_registers_without_it():
    suite.invalidate()
    app, _ = make_app("ionote", public_url="notes.example.com")
    TestClient(app, base_url="http://192.168.1.89:8610").get("/api/x")
    assert suite.get("ionote")["url"] == "http://192.168.1.89:8610"


def test_api_lists_for_signed_in_and_a_forgotten_app_goes():
    suite.invalidate()
    app, _ = make_app("iostart", label="ioStart")
    users.create("alex", "secret123", "admin", "iostart", suite_admin=True)
    users.create("bob", "secret123", "viewer", "iostart")
    suite.register("iopix", "ioPix", url="https://photo.example.com")
    c = TestClient(app, base_url="http://home.lan")
    assert c.get("/api/auth/suite").status_code == 401
    c.post("/api/auth/login", json={"name": "bob", "password": "secret123"})
    body = c.get("/api/auth/suite").json()
    assert body["app"] == "iostart" and {a["app"] for a in body["items"]} == {"iopix", "iostart"}
    assert suite.forget("iopix")  # Settings › Apps › The apps (test_admin: DELETE /api/suite-admin/apps/<app>)
    assert [a["app"] for a in c.get("/api/auth/suite").json()["items"]] == ["iostart"]


def test_an_app_with_its_own_middleware_registers_through_resolve():
    suite.invalidate()
    auth = Auth("iohealth", app_label="ioHealth", version="3.0")
    app = FastAPI()

    @app.middleware("http")
    async def mine(request, call_next):
        await auth.resolve(request)
        return await call_next(request)

    @app.get("/x")
    def x():
        return {"ok": True}
    TestClient(app, base_url="http://192.168.1.89:47800").get("/x")
    r = suite.get("iohealth")
    assert r["version"] == "3.0" and r["url"] == "http://192.168.1.89:47800"


def test_internal_url_is_recorded_and_never_the_link():
    suite.register("iostart", "ioStart", url="https://home.example.com", internal_url="http://192.168.1.151:8630/")
    r = suite.get("iostart")
    assert r["internalUrl"] == "http://192.168.1.151:8630" and r["url"] == "https://home.example.com"
    suite.register("iostart", "ioStart", internal_url="http://192.168.1.151:8630")
    r = suite.get("iostart")
    assert r["url"] is None and r["internalUrl"] == "http://192.168.1.151:8630"
    suite.register("iostart", "ioStart")
    assert suite.get("iostart")["internalUrl"] is None


def _machine(monkeypatch, **values):
    """The machine's settings for a test: HOST, PORT, SYNC_PORT, MCP_PORT, INTERNAL_URL, HTTPS_PORT..."""
    for k, v in values.items():
        monkeypatch.setattr(f"iosuite_shared.config.{k}", v)


def test_local_url(monkeypatch):
    _machine(monkeypatch, HOST="0.0.0.0", PORT=80, SYNC_PORT=8443, MCP_PORT=8444, INTERNAL_URL="", TLS_CERT_FILE="", TLS_KEY_FILE="")
    monkeypatch.setattr(suite, "_lan_ip", lambda: "192.168.1.151")
    monkeypatch.setattr(suite, "in_container", lambda: False)
    assert suite.local_url("iostart") == "http://192.168.1.151:80" and suite.local_url("iocalendar") == "http://192.168.1.151:80/calendar"
    assert suite.local_url("iocalendar", "sync") == "http://192.168.1.151:8443/calendar" and suite.local_url("iopix", "mcp") == "http://192.168.1.151:8444/pix"
    _machine(monkeypatch, PORT=9000, SYNC_PORT=0)
    assert suite.local_url("iostart") == "http://192.168.1.151:9000" and suite.local_url("iostart", "sync") is None  # a door that is not opened
    _machine(monkeypatch, HOST="127.0.0.1")
    assert suite.local_url("iostart") == "http://127.0.0.1:9000"  # behind a reverse proxy on the same host: for the copies beside it
    _machine(monkeypatch, HOST="localhost")
    assert suite.local_url("iostart") == "http://127.0.0.1:9000"
    _machine(monkeypatch, HOST="::1")
    assert suite.local_url("iostart") == "http://[::1]:9000"
    monkeypatch.setattr(suite, "in_container", lambda: True)
    assert suite.local_url("iostart") is None  # a container's loopback is its own
    monkeypatch.setattr(suite, "in_container", lambda: False)
    _machine(monkeypatch, HOST="10.0.0.7")
    assert suite.local_url("iostart") == "http://10.0.0.7:9000"
    _machine(monkeypatch, HOST="127.0.0.1, 10.0.0.7")
    assert suite.local_url("iostart") == "http://10.0.0.7:9000"  # of several, the one the network reaches
    _machine(monkeypatch, HOST="127.0.0.1 ::1")
    assert suite.local_url("iostart") == "http://127.0.0.1:9000"
    _machine(monkeypatch, HOST="::")
    monkeypatch.setattr(suite, "in_container", lambda: True)
    assert suite.local_url("iostart") is None  # a container's own address is no use
    _machine(monkeypatch, INTERNAL_URL="http://192.168.1.20")  # the machine says where the others reach it: the host counts, the ports are the doors'
    assert suite.local_url("iostart") == "http://192.168.1.20:9000" and suite.local_url("iotask") == "http://192.168.1.20:9000/tasks"
    _machine(monkeypatch, INTERNAL_URL="")
    monkeypatch.setattr(suite, "in_container", lambda: False)
    monkeypatch.setattr(suite, "_lan_ip", lambda: "fd00::5")
    # a copy that answers HTTPS itself is still called without it inside the network (its ports answer both)...
    from iosuite_shared import certs
    monkeypatch.setattr(certs, "SERVING", ("/suite.pem", None))
    _machine(monkeypatch, SYNC_PORT=8443)
    assert suite.local_url("iostart") == "http://[fd00::5]:9000" and suite.local_url("iotask", "sync") == "http://[fd00::5]:8443/tasks"
    # ...unless its file says to call it over HTTPS, by a name on the certificate
    _machine(monkeypatch, INTERNAL_URL="https://home.example.com")
    monkeypatch.setattr(certs, "PAGES_PORT", 443)
    assert suite.local_url("iostart") == "https://home.example.com:443" and suite.local_url("iotask", "sync") == "https://home.example.com:8443/tasks"
    monkeypatch.setattr(certs, "SERVING", None)
    assert suite.local_url("iostart") == "http://home.example.com:9000"


def test_two_copies_on_one_machine_have_names_of_their_own(monkeypatch):
    monkeypatch.setattr("socket.gethostname", lambda: "nas.lan")
    _machine(monkeypatch, PORT=80)
    assert suite.copy_name() == "nas"
    _machine(monkeypatch, PORT=8080)
    assert suite.copy_name() == "nas:8080"


def test_a_container_is_called_by_the_name_the_others_reach_it_at(monkeypatch):
    """A container's own name is a number, new each time it is made again."""
    monkeypatch.setattr("socket.gethostname", lambda: "3f2a9c1d7b21")
    monkeypatch.setattr(suite, "in_container", lambda: True)
    _machine(monkeypatch, HOST="0.0.0.0", PORT=80, INTERNAL_URL="http://iosuite")
    assert suite.copy_name() == "iosuite"
    _machine(monkeypatch, INTERNAL_URL="")
    assert suite.copy_name() == "3f2a9c1d7b21"  # it did not say: its own name
    monkeypatch.setattr(suite, "in_container", lambda: False)
    _machine(monkeypatch, INTERNAL_URL="http://192.168.1.20")
    assert suite.copy_name() == "3f2a9c1d7b21"  # a machine has a name of its own


def test_what_a_copy_no_longer_runs_leaves_the_list(monkeypatch):
    """APPS changed in a stack file: the apps taken out of it are no longer in the suite's list (a tile that leads
    nowhere, requests passed to a copy that does not run the app). What another copy runs stays."""
    _machine(monkeypatch, HOST="0.0.0.0", PORT=80, SYNC_PORT=8443, MCP_PORT=8444, INTERNAL_URL="http://iosuite", TLS_CERT_FILE="", TLS_KEY_FILE="")
    suite.invalidate()
    for app in ("iostart", "iocalendar", "iobackup"):
        suite.register(app, app, internal_url=suite.local_url(app))
    suite.register("iopix", "ioPix", internal_url="http://iopix:80/pix")       # another container's
    suite.register("iodns", "ioDNS", internal_url="http://iosuite:8080/dns")   # a second copy at the same address, on its own port
    suite.register("iohealth", "ioHealth")                                     # one that gave no address
    assert suite.left_behind(["iostart", "iocalendar"]) == ["iobackup"]
    assert suite.get("iobackup") is None and {a["app"] for a in suite.apps()} == {"iostart", "iocalendar", "iopix", "iodns", "iohealth"}
    assert suite.left_behind(["iostart", "iocalendar"]) == []
    monkeypatch.setattr(suite, "in_container", lambda: True)
    _machine(monkeypatch, INTERNAL_URL="")  # a container that does not say where it is: nothing to go by
    assert suite.left_behind([]) == [] and len(suite.apps()) == 5


def test_auth_registers_where_its_copy_is(monkeypatch):
    _machine(monkeypatch, HOST="0.0.0.0", PORT=80, SYNC_PORT=8443, MCP_PORT=8444, INTERNAL_URL="http://192.168.1.151", TLS_CERT_FILE="", TLS_KEY_FILE="")
    monkeypatch.setattr("socket.gethostname", lambda: "nas")
    suite.invalidate()
    app, _ = make_app("iostart", label="ioStart")
    TestClient(app, base_url="http://testserver").get("/api/x")
    r = suite.get("iostart")
    assert (r["internalUrl"], r["internalSyncUrl"], r["internalMcpUrl"], r["copy"]) == ("http://192.168.1.151:80", "http://192.168.1.151:8443", "http://192.168.1.151:8444", "nas")
    app, _ = make_app("iocalendar", label="ioCalendar", public_url="https://cal.example.com")
    TestClient(app, base_url="http://testserver").get("/api/x")
    r = suite.get("iocalendar")
    assert r["internalUrl"] == "http://192.168.1.151:80/calendar" and r["internalMcpUrl"] == "http://192.168.1.151:8444/calendar"
    assert r["url"] == "https://cal.example.com"
    assert set(suite.machines()) >= set() and any("192.168.1.151" in str(n) for n in suite.machines())  # a machine of the suite: its requests passed across are believed


def test_switcher_shows_only_the_apps_an_account_may_use():
    from iosuite_shared import db
    suite.invalidate()
    app, _ = make_app("iostart", label="ioStart")
    users.create("alex", "secret123", "admin", "iostart", suite_admin=True)
    bob = users.create("bob", "secret123", "viewer", "iostart")
    carol = users.create("carol", "secret123", "viewer", "iostart")
    suite.register("iohealth", "ioHealth", url="https://health.example.com")
    suite.register("iodns", "ioDNS", url="https://dns.example.com", admin_tool=True)
    db.set_setting("default_role", "none", "iohealth")  # ioHealth: only the accounts given a role there
    users.set_role(carol["id"] if isinstance(carol, dict) else carol, "iohealth", "viewer")
    users.set_role(carol["id"] if isinstance(carol, dict) else carol, "iodns", "editor")
    c = TestClient(app, base_url="http://home.lan")

    def seen(name):
        c.post("/api/auth/login", json={"name": name, "password": "secret123"})
        items = c.get("/api/auth/suite").json()["items"]
        return {a["app"]: a["adminTool"] for a in items}
    assert seen("bob") == {"iostart": False}                                       # no role in ioHealth; ioDNS is an admin tool
    assert seen("carol") == {"iostart": False, "iohealth": False}                  # an editor of ioDNS is not its admin
    assert seen("alex") == {"iostart": False, "iohealth": False, "iodns": True}    # a suite admin sees everything
    assert bob is not None
    # an app that registers again without the flag (an older library) is no admin tool any more only when it says so
    suite.register("iodns", "ioDNS", url="https://dns.example.com")
    assert suite.get("iodns")["adminTool"] is False


def test_before_the_first_account_the_switcher_lists_every_app():
    suite.invalidate()
    app, _ = make_app("iostart", label="ioStart")
    suite.register("iodns", "ioDNS", url="https://dns.example.com", admin_tool=True)
    c = TestClient(app, base_url="http://home.lan")
    assert {a["app"] for a in c.get("/api/auth/suite").json()["items"]} == {"iostart", "iodns"}


def test_one_order_everywhere_iostart_first_then_by_name():
    for key, name in (("iotask", "ioTask"), ("iostart", "ioStart"), ("iocalendar", "ioCalendar"), ("iodns", "ioDNS")):
        suite.register(key, name, url=f"https://{key}.example.com", admin_tool=key == "iodns")
    assert [a["app"] for a in suite.apps()] == ["iostart", "iocalendar", "iodns", "iotask"]

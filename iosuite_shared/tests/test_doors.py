"""The three doors of a copy (iosuite_shared.doors) and the host that opens them (iosuite_shared.host): which app a
request is for (its own name, its folder, the start page), which door serves which path, where a request that came in
by the wrong door is sent, and what is passed across to another copy of the suite."""
import asyncio
import json
import time

import pytest
from starlette.requests import Request

from iosuite_shared import config, doors, prefix, suite
from iosuite_shared.host import Entry, Host

OUTSIDE = "203.0.113.9"   # a visitor: nothing it says about itself is believed
HERE = "127.0.0.1"        # this machine: a reverse proxy, or another copy of the suite


def echo(name):
    """A stand-in for an app: answers with what the host handed it."""
    async def app(scope, receive, send):
        h = {k.decode(): v.decode() for k, v in scope["headers"]}
        body = json.dumps({"app": name, "path": scope["path"], "folder": scope.get(prefix.SCOPE_KEY), "door": scope.get(doors.SCOPE_DOOR),
                           "routed": scope.get(doors.SCOPE_ROUTED), "cookie": h.get("cookie"), "authorization": h.get("authorization")}).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})
    return app


def machine(monkeypatch, web=80, sync=8443, mcp=8444, **of_app):
    monkeypatch.setattr(config, "PORT", web)
    monkeypatch.setattr(config, "SYNC_PORT", sync)
    monkeypatch.setattr(config, "MCP_PORT", mcp)
    monkeypatch.setattr(config, "TLS_CERT_FILE", "")
    monkeypatch.setattr(config, "TLS_KEY_FILE", "")
    monkeypatch.setattr(config, "OF_APP", dict(of_app))


def a_host(*apps, hosts=None, remote=None, outer=("", 0, "")):
    """A copy running these apps, its table set by hand (never read from the database)."""
    from iosuite_shared import catalog
    h = Host([Entry(name=a, asgi=echo(a), state="up") for a in apps], ports={80: "web", 8443: "sync", 8444: "mcp"})
    h.table = doors.Table(hosts=dict(hosts or {}), folders={f: k for k, f in catalog.FOLDERS.items()}, remote=dict(remote or {}),
                          outer=outer, at=time.time() + 3600)
    return h


def ask(host, path, port=80, method="GET", name="home.example.com", headers=(), peer=OUTSIDE, query=""):
    """One request through the host: (status, headers, body as JSON or text)."""
    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": query.encode(), "scheme": "http",
             "headers": [(b"host", name.encode()), *[(k.encode(), v.encode()) for k, v in headers]],
             "server": ("10.0.0.5", port), "client": (peer, 50000)}
    got = {"status": 0, "headers": {}, "body": b""}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(m):
        if m["type"] == "http.response.start":
            got["status"] = m["status"]
            got["headers"] = {k.decode().lower(): v.decode() for k, v in m.get("headers") or []}
        else:
            got["body"] += m.get("body") or b""

    asyncio.run(host(scope, receive, send))
    try:
        body = json.loads(got["body"])
    except ValueError:
        body = got["body"].decode()
    return got["status"], got["headers"], body


def request(path="/", port=80, name="home.example.com", door="web", folder=""):
    scope = {"type": "http", "method": "GET", "path": path, "query_string": b"", "scheme": "http", "headers": [(b"host", name.encode())],
             "server": ("10.0.0.5", port), "client": (OUTSIDE, 50000), prefix.SCOPE_KEY: folder}
    if door:
        scope[doors.SCOPE_DOOR] = door
    return Request(scope)


# ---- which door serves which path
def test_under_covers_a_prefix_and_what_is_below_it_only():
    assert doors.under("/dav", ("/dav",)) and doors.under("/dav/x", ("/dav",)) and not doors.under("/davx", ("/dav",))
    assert doors.under("/ics/abc/", ("/ics/",)) and doors.under("/ics", ("/ics/",)) and not doors.under("/icsx", ("/ics/",))


def test_each_path_has_its_door():
    assert doors.home("iocalendar", "/mcp") == ("mcp",) and doors.home("iocalendar", "/mcp/x") == ("mcp",)
    assert doors.home("iocalendar", "/dav/alex/home/") == ("sync",)
    assert doors.home("iocalendar", "/.well-known/caldav") == ("sync",)
    assert doors.home("iocalendar", "/ics/secret/home.ics") == ("sync",)
    assert doors.home("iocontact", "/cal/secret/birthdays.ics") == ("sync",)
    assert doors.home("iohealth", "/v1/upload", "POST") == ("sync",)
    assert doors.home("iocalendar", "/api/events") == ("web", "sync")
    assert doors.home("iocalendar", "/api/events", "POST") == ("web", "sync")
    assert doors.home("iocalendar", "/") == ("web",) and doors.home("iocalendar", "/static/app.js") == ("web",)
    assert doors.home("iocalendar", "/mcpx") == ("web",)
    # a profile download is a person's browser, with the pages
    assert doors.home("iocalendar", "/profile/token/calendar.mobileconfig") == ("web",)


def test_nobody_signs_in_at_the_sync_door():
    assert doors.home("iocalendar", "/api/auth/login", "POST") == ("web",)
    assert doors.home("iocalendar", "/api/auth/account", "PUT") == ("web",)
    assert doors.home("iocalendar", "/api/auth/me") == ("web", "sync")  # an app asking who its password is
    assert not doors.allowed("sync", "iocalendar", "/api/auth/login", "POST") and doors.allowed("web", "iocalendar", "/api/auth/login", "POST")


def test_the_screen_to_say_yes_on_is_a_page_below_a_sync_path():
    assert doors.home("iostart", "/dav/ext/tree") == ("sync",)
    assert doors.home("iostart", "/dav/nextcloud/index.php/apps/bookmarks/public/rest/v2/bookmark") == ("sync",)
    assert doors.home("iostart", "/dav/nextcloud/index.php/login/v2/flow/abc") == ("web",)
    assert doors.home("iostart", "/dav/nextcloud/index.php/login/v2/grant", "POST") == ("web",)
    assert doors.home("iostart", "/dav/nextcloud/index.php/login/v2") == ("sync",)  # the client's own first call


def test_manifests_name_pages_below_their_sync_paths_only():
    from iosuite_shared import catalog
    for app, m in catalog.APPS.items():
        for p in m.get("pages") or ():
            assert doors.under(p, m.get("sync") or ()), (app, p)


# ---- which app
def test_an_app_is_reached_in_its_folder_and_the_start_page_at_the_root(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar")
    s, _, b = ask(h, "/calendar/api/events")
    assert s == 200 and b == {"app": "iocalendar", "path": "/api/events", "folder": "/calendar", "door": "web", "routed": True,
                              "cookie": None, "authorization": None}
    s, _, b = ask(h, "/")
    assert s == 200 and b["app"] == "iostart" and b["folder"] == "" and b["path"] == "/"
    s, _, b = ask(h, "/api/tiles")
    assert b["app"] == "iostart" and b["path"] == "/api/tiles"


def test_a_folder_without_its_slash_is_given_one(monkeypatch):
    machine(monkeypatch)
    s, hd, _ = ask(a_host("iostart", "iocalendar"), "/calendar", query="view=week")
    assert s == 308 and hd["location"] == "/calendar/?view=week"


def test_an_app_is_reached_at_its_own_name_on_every_door(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", hosts={"calendar.example.com": "iocalendar"})
    s, _, b = ask(h, "/api/events", name="calendar.example.com")
    assert s == 200 and b["app"] == "iocalendar" and b["folder"] == "" and b["path"] == "/api/events"
    s, _, b = ask(h, "/dav/alex/", port=8443, name="calendar.example.com:8443", method="PROPFIND")
    assert s == 200 and b["app"] == "iocalendar" and b["door"] == "sync" and b["path"] == "/dav/alex/"
    s, _, b = ask(h, "/mcp", port=8444, name="calendar.example.com:8444", method="POST")
    assert s == 200 and b["app"] == "iocalendar" and b["door"] == "mcp"
    # the folder still works at any other name, on the same port
    s, _, b = ask(h, "/calendar/api/events")
    assert s == 200 and b["app"] == "iocalendar" and b["folder"] == "/calendar"


def test_a_visitor_cannot_name_the_app_or_the_host_itself(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", "iomoney", hosts={"calendar.example.com": "iocalendar"})
    s, _, b = ask(h, "/api/x", headers=[("x-iosuite-app", "iomoney"), ("x-forwarded-host", "calendar.example.com")])
    assert b["app"] == "iostart"
    s, _, b = ask(h, "/api/x", headers=[("x-iosuite-app", "iomoney"), ("x-forwarded-prefix", "/money")], peer=HERE)
    assert b["app"] == "iomoney" and b["folder"] == "/money" and b["path"] == "/api/x"
    s, _, b = ask(h, "/api/x", headers=[("x-forwarded-host", "calendar.example.com")], peer=HERE)  # a reverse proxy on this machine
    assert b["app"] == "iocalendar"


def test_an_address_nobody_answers_at(monkeypatch):
    machine(monkeypatch)
    s, _, b = ask(a_host("iocalendar"), "/nothing/here")
    assert s == 404 and "No app" in b
    s, hd, _ = ask(a_host("iocalendar"), "/")  # no start page anywhere: the first app of this copy
    assert s == 307 and hd["location"] == "/calendar/"


def test_an_app_that_is_not_up_says_so(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar")
    h.by_name["iocalendar"].state, h.by_name["iocalendar"].error = "failed", "its database is away"
    s, hd, b = ask(h, "/calendar/api/events")
    assert s == 503 and hd["retry-after"] == "15" and b == {"detail": "ioCalendar is not available right now."}
    s, hd, b = ask(h, "/calendar/dav/alex/", port=8443, method="PROPFIND")
    assert s == 503 and b == {"detail": "ioCalendar is not available right now."}
    s, hd, b = ask(h, "/calendar/")
    assert s == 503 and hd["content-type"].startswith("text/html") and "ioCalendar is not available" in b
    assert ask(h, "/")[0] == 200  # the others are not held up


# ---- the doors
def test_the_sync_door_reads_no_cookie(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar")
    sent = [("cookie", "ios_session=abc"), ("authorization", "Basic YTpi")]
    s, _, b = ask(h, "/calendar/api/events", headers=sent)
    assert s == 200 and b["door"] == "web" and b["cookie"] == "ios_session=abc"
    s, _, b = ask(h, "/calendar/api/events", port=8443, headers=sent)
    assert s == 200 and b["door"] == "sync" and b["cookie"] is None and b["authorization"] == "Basic YTpi"
    s, _, b = ask(h, "/calendar/dav/alex/", port=8443, method="REPORT", headers=sent)
    assert s == 200 and b["cookie"] is None and b["path"] == "/dav/alex/"
    s, _, b = ask(h, "/calendar/mcp", port=8444, method="POST", headers=sent)
    assert s == 200 and b["door"] == "mcp" and b["cookie"] is None


def test_a_sync_path_asked_with_the_pages_is_sent_to_the_sync_door(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", hosts={"calendar.example.com": "iocalendar"})
    s, hd, _ = ask(h, "/calendar/dav/alex/home/", method="PROPFIND")  # whatever the method: 307 asks again as it was
    assert s == 307 and hd["location"] == "http://home.example.com:8443/calendar/dav/alex/home/"
    s, hd, _ = ask(h, "/ics/secret/home.ics", name="calendar.example.com", query="x=1")
    assert s == 307 and hd["location"] == "http://calendar.example.com:8443/ics/secret/home.ics?x=1"
    s, hd, _ = ask(h, "/dav/ext/tree", method="PUT")
    assert s == 307 and hd["location"] == "http://home.example.com:8443/dav/ext/tree"
    s, hd, _ = ask(h, "/calendar/mcp", method="POST")
    assert s == 307 and hd["location"] == "http://home.example.com:8444/calendar/mcp"


def test_a_phone_looking_its_account_up_is_sent_to_where_it_syncs(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", "iocontact")
    s, hd, _ = ask(h, "/.well-known/caldav", method="PROPFIND")
    assert s == 301 and hd["location"] == "http://home.example.com:8443/calendar/dav/"
    s, hd, _ = ask(h, "/.well-known/carddav")
    assert s == 301 and hd["location"] == "http://home.example.com:8443/contacts/dav/"
    s, _, b = ask(h, "/.well-known/caldav", port=8443, method="PROPFIND")  # at the sync door it is the app's to answer
    assert s == 200 and b["app"] == "iocalendar" and b["path"] == "/.well-known/caldav" and b["folder"] == "/calendar"


def test_a_page_asked_at_the_sync_door_is_sent_to_the_pages(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar")
    s, hd, _ = ask(h, "/calendar/", port=8443, name="home.example.com:8443")
    assert s == 307 and hd["location"] == "http://home.example.com/calendar/"
    s, hd, _ = ask(h, "/dav/nextcloud/index.php/login/v2/flow/abc", port=8443, name="home.example.com:8443")
    assert s == 307 and hd["location"] == "http://home.example.com/dav/nextcloud/index.php/login/v2/flow/abc"
    s, _, b = ask(h, "/dav/nextcloud/index.php/login/v2/flow/abc", headers=[("cookie", "ios_session=abc")])
    assert s == 200 and b["app"] == "iostart" and b["door"] == "web" and b["cookie"] == "ios_session=abc"
    # anything but a browser's GET is refused where it is: nobody signs in here
    s, _, b = ask(h, "/calendar/api/auth/login", port=8443, method="POST")
    assert s == 404 and b["door"] == "sync" and "devices and native apps" in b["detail"]
    s, _, b = ask(h, "/calendar/", port=8443, method="POST")
    assert s == 404


def test_the_mcp_door_serves_mcp_and_sends_nobody_on(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar")
    for path in ("/calendar/api/events", "/calendar/", "/calendar/dav/alex/"):
        s, hd, b = ask(h, path, port=8444)
        assert s == 404 and "location" not in hd and b["door"] == "mcp", path
    assert ask(h, "/mcp", port=8444, method="POST")[2]["app"] == "iostart"


def test_the_address_stored_for_a_door_is_where_its_requests_are_sent(monkeypatch):
    cal = {"SYNC_URLS": ["https://calsync.example.com", "https://sync.example.com/calendar"], "SYNC_URL_OWN": "https://calsync.example.com",
           "MCP_URLS": ["https://mcp.example.com/calendar"], "MCP_URL_OWN": "",
           "PUBLIC_URLS": ["https://calendar.example.com", "https://home.example.com/calendar"], "OWN_URL": "https://calendar.example.com"}
    machine(monkeypatch, iocalendar=cal)
    h = a_host("iostart", "iocalendar", hosts={"calendar.example.com": "iocalendar", "calsync.example.com": "iocalendar"})
    s, hd, _ = ask(h, "/calendar/dav/alex/", method="PROPFIND")  # came through the folder: the folder's address
    assert s == 307 and hd["location"] == "https://sync.example.com/calendar/dav/alex/"
    s, hd, _ = ask(h, "/dav/alex/", name="calendar.example.com", method="PROPFIND")  # came by its own name: its own
    assert s == 307 and hd["location"] == "https://calsync.example.com/dav/alex/"
    s, hd, _ = ask(h, "/calendar/mcp", method="POST")
    assert s == 307 and hd["location"] == "https://mcp.example.com/calendar/mcp"
    s, hd, _ = ask(h, "/", port=8443, name="calsync.example.com")  # the app opened from a sync client
    assert s == 307 and hd["location"] == "https://calendar.example.com/"
    s, hd, _ = ask(h, "/calendar/", port=8443, name="sync.example.com")
    assert s == 307 and hd["location"] == "https://home.example.com/calendar/"


def test_a_door_that_is_not_opened_has_nowhere_to_send_to(monkeypatch):
    machine(monkeypatch, sync=0, mcp=0)
    h = a_host("iostart", "iocalendar")
    s, hd, b = ask(h, "/calendar/dav/alex/", method="PROPFIND")
    assert s == 404 and "location" not in hd and "not opened on this server" in b["detail"]
    s, _, b = ask(h, "/calendar/mcp", method="POST")
    assert s == 404 and "MCP" in b["detail"]
    # but one with an address stored (something else serves it) is
    machine(monkeypatch, sync=0, mcp=0, iocalendar={"SYNC_URLS": ["https://sync.example.com/calendar"], "SYNC_URL_OWN": ""})
    s, hd, _ = ask(h, "/calendar/dav/alex/", method="PROPFIND")
    assert s == 307 and hd["location"] == "https://sync.example.com/calendar/dav/alex/"


def test_a_door_s_own_port_is_left_out_of_its_address(monkeypatch, tmp_path):
    machine(monkeypatch, web=8080, sync=80, mcp=443)
    assert doors._at_port("home.example.com", "web", "/calendar") == "http://home.example.com:8080/calendar"
    assert doors._at_port("home.example.com", "sync", "") == "http://home.example.com"
    assert doors._at_port("fd00::1", "sync", "") == "http://[fd00::1]"
    monkeypatch.setattr(config, "TLS_CERT_FILE", str(tmp_path / "c.pem"))
    monkeypatch.setattr(config, "TLS_KEY_FILE", str(tmp_path / "k.pem"))
    assert doors._at_port("home.example.com", "mcp", "/pix") == "https://home.example.com/pix"
    assert doors._at_port("home.example.com", "web", "") == "https://home.example.com:8080"


# ---- an app that runs in another copy
def test_a_request_for_another_copy_s_app_is_passed_to_that_copy_s_same_door(monkeypatch):
    machine(monkeypatch)
    there = {"web": "http://10.0.0.9", "sync": "http://10.0.0.9:8443", "mcp": None}
    h = a_host("iostart", "iocalendar", remote={"iopix": there})
    passed = []

    async def across(scope, receive, send, upstream, r):
        passed.append((upstream, r.app, r.folder, r.path))
        await doors.plain(send, 200, "passed")
    monkeypatch.setattr(doors, "across", across)
    assert ask(h, "/pix/api/photos")[0] == 200
    assert ask(h, "/pix/api/photos", port=8443)[0] == 200
    assert passed == [("http://10.0.0.9", "iopix", "/pix", "/api/photos"), ("http://10.0.0.9:8443", "iopix", "/pix", "/api/photos")]
    s, _, b = ask(h, "/pix/mcp", port=8444, method="POST")
    assert s == 502 and "no door for MCP" in b and len(passed) == 2
    # the doors are kept before anything is passed on
    s, hd, _ = ask(h, "/pix/mcp", method="POST")
    assert s == 307 and hd["location"] == "http://home.example.com:8444/pix/mcp" and len(passed) == 2


def test_a_request_that_was_passed_across_is_never_passed_on_again(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", remote={"iopix": {"web": "http://10.0.0.9"}})
    monkeypatch.setattr(doors, "across", None)  # would fail if it were called
    s, _, b = ask(h, "/api/photos", headers=[("x-iosuite-app", "iopix"), ("x-forwarded-prefix", "/pix")], peer=HERE)
    assert s == 404 and "No app" in b


def test_what_the_other_copy_is_told(monkeypatch):
    scope = {"type": "http", "method": "GET", "path": "/pix/api/photos", "scheme": "http", "client": (OUTSIDE, 50000),
             "headers": [(b"host", b"home.example.com"), (b"cookie", b"ios_session=abc"), (b"x-forwarded-for", b"1.2.3.4"),
                         (b"x-forwarded-proto", b"https"), (b"x-iosuite-app", b"iomoney"), (b"connection", b"keep-alive, x-mine"),
                         (b"x-mine", b"1"), (b"remote-user", b"admin"), (b"cf-connecting-ip", b"9.9.9.9"), (b"accept", b"text/html")]}
    got = dict(doors._across_headers(scope, "iopix", "/pix"))
    assert got["host"] == "home.example.com" and got["x-forwarded-host"] == "home.example.com"
    assert got["x-forwarded-for"] == OUTSIDE and got["x-forwarded-proto"] == "http"  # a visitor's own headers are not passed on as a proxy's
    assert got["x-forwarded-prefix"] == "/pix" and got["x-iosuite-app"] == "iopix"
    assert got["cookie"] == "ios_session=abc" and got["accept"] == "text/html"
    assert "x-mine" not in got and "connection" not in got and "remote-user" not in got and "cf-connecting-ip" not in got
    scope["client"] = (HERE, 50000)  # from a reverse proxy on this machine: what it says is passed on
    got = dict(doors._across_headers(scope, "iopix", "/pix"))
    assert got["x-forwarded-for"] == f"1.2.3.4, {HERE}" and got["x-forwarded-proto"] == "https"


# ---- the table
def test_the_table_knows_names_folders_and_where_other_copies_are(monkeypatch):
    machine(monkeypatch, iocalendar={"OWN_URL": "https://calendar.example.com", "SYNC_URL_OWN": "https://calsync.example.com", "MCP_URL_OWN": ""})
    suite.register("iocalendar", "ioCalendar", internal_url="http://10.0.0.5/calendar")
    suite.register("iopix", "ioPix", url="https://photos.example.com", sync_url="https://photosync.example.com",
                   internal_url="http://10.0.0.9/pix", internal_sync_url="http://10.0.0.9:8443/pix", copy="nas")
    suite.register("iomoney", "ioMoney", url="https://home.example.com/money", internal_url="http://10.0.0.9/money", copy="nas")
    t = doors.load_table(("iostart", "iocalendar"))
    assert t.hosts == {"photos.example.com": "iopix", "photosync.example.com": "iopix", "calendar.example.com": "iocalendar",
                       "calsync.example.com": "iocalendar"}  # an address in a folder is nobody's own name
    assert t.folders["calendar"] == "iocalendar" and t.folders["pix"] == "iopix" and t.folders["money"] == "iomoney"
    assert set(t.remote) == {"iopix", "iomoney"}
    assert t.remote["iopix"] == {"web": "http://10.0.0.9/pix", "sync": "http://10.0.0.9:8443/pix", "mcp": None}
    assert t.remote["iomoney"]["web"] == "http://10.0.0.9/money" and t.remote["iomoney"]["sync"] is None


def test_the_host_reads_the_table_itself_and_keeps_serving_when_it_cannot(monkeypatch):
    machine(monkeypatch)
    h = Host([Entry(name="iostart", asgi=echo("iostart"), state="up"), Entry(name="iocalendar", asgi=echo("iocalendar"), state="up")],
             ports={80: "web"})
    assert ask(h, "/calendar/api/x")[2]["app"] == "iocalendar" and h.table.at > 0
    h.forget_routes()
    monkeypatch.setattr(doors, "load_table", lambda local: (_ for _ in ()).throw(RuntimeError("the database is away")))
    assert ask(h, "/calendar/api/x")[2]["app"] == "iocalendar"


def test_a_port_the_host_does_not_know_is_the_pages(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart")
    assert h.door_of({"server": ("10.0.0.5", 9999)}) == "web" and h.door_of({}) == "web" and h.door_of({"server": ("x", 8443)}) == "sync"


# ---- the addresses an app shows people
def test_the_address_of_a_door_is_the_one_asked_with_that_door_s_port(monkeypatch):
    machine(monkeypatch, iocalendar={})
    r = request(folder="/calendar")
    assert doors.base("web", r, "iocalendar") == "http://home.example.com/calendar"
    assert doors.base("sync", r, "iocalendar") == "http://home.example.com:8443/calendar"
    assert doors.base("mcp", r, "iocalendar") == "http://home.example.com:8444/calendar"
    r = request(port=8443, name="home.example.com:8443", door="sync", folder="/calendar")
    assert doors.base("sync", r, "iocalendar") == "http://home.example.com:8443/calendar"
    assert doors.base("web", r, "iocalendar") == "http://home.example.com/calendar"


def test_the_address_stored_for_a_door_is_shown_in_the_style_of_the_request(monkeypatch):
    cal = {"SYNC_URLS": ["https://calsync.example.com", "https://sync.example.com/calendar"], "SYNC_URL_OWN": "https://calsync.example.com",
           "PUBLIC_URLS": ["https://calendar.example.com", "https://home.example.com/calendar"], "OWN_URL": "https://calendar.example.com"}
    machine(monkeypatch, iocalendar=cal)
    assert doors.base("sync", request(name="calendar.example.com"), "iocalendar") == "https://calsync.example.com"
    assert doors.base("sync", request(folder="/calendar"), "iocalendar") == "https://sync.example.com/calendar"
    assert doors.base("web", request(name="sync.example.com", door="sync", folder="/calendar"), "iocalendar") == "https://home.example.com/calendar"
    assert doors.base("mcp", request(folder="/calendar"), "iocalendar") == "http://home.example.com:8444/calendar"  # none stored


def test_an_app_asked_directly_has_one_address_for_everything(monkeypatch):
    machine(monkeypatch, iocalendar={})
    r = request(name="192.168.1.20:8620", port=8620, door="")
    assert doors.base("sync", r, "iocalendar") == "http://192.168.1.20:8620" == doors.base("web", r, "iocalendar") == doors.base("mcp", r, "iocalendar")


def test_a_door_that_is_not_opened_has_the_address_asked(monkeypatch):
    machine(monkeypatch, sync=0, iocalendar={})
    assert doors.base("sync", request(folder="/calendar"), "iocalendar") == "http://home.example.com/calendar"


def test_the_address_of_another_copy_s_app(monkeypatch):
    machine(monkeypatch, iocalendar={})
    suite.register("iopix", "ioPix", internal_url="http://10.0.0.9/pix", copy="nas")
    r = request(folder="/calendar")
    assert doors.base_of("sync", r, "iocalendar") == "http://home.example.com:8443/calendar"
    assert doors.base_of("sync", r, "iopix") == "http://10.0.0.9:8443/pix"
    assert doors.base_of("web", r, "iopix") == "http://10.0.0.9/pix"
    assert doors.base_of("sync", r, "iomoney") is None  # not running anywhere
    suite.register("iopix", "ioPix", sync_url="https://photosync.example.com", internal_url="http://10.0.0.9/pix", copy="nas")
    assert doors.base_of("sync", r, "iopix") == "https://photosync.example.com"


def test_an_app_s_own_redirect_keeps_its_folder():
    hosts = {"home.example.com"}
    assert doors.location("/api/x/", hosts, "/calendar") == "/calendar/api/x/"
    assert doors.location("http://home.example.com/api/x/?a=1", hosts, "/calendar") == "http://home.example.com/calendar/api/x/?a=1"
    assert doors.location("/calendar/api/x/", hosts, "/calendar") == "/calendar/api/x/"
    assert doors.location("https://elsewhere.example.com/x", hosts, "/calendar") == "https://elsewhere.example.com/x"
    assert doors.location("next", hosts, "/calendar") == "next"


def test_the_doors_of_a_copy(monkeypatch):
    machine(monkeypatch, mcp=0)
    assert doors.ports() == {80: "web", 8443: "sync"}
    assert [d["port"] for d in doors.state()] == [80, 8443, 0]


@pytest.mark.parametrize("path,query", [("/calendar/dav/a b/", ""), ("/calendar/dav/%2Fx", "a=1&b=2")])
def test_a_redirect_keeps_the_address_as_it_was_asked(monkeypatch, path, query):
    machine(monkeypatch)
    s, hd, _ = ask(a_host("iostart", "iocalendar"), path, query=query)
    assert s == 307 and hd["location"].startswith("http://home.example.com:8443/calendar/dav/") and " " not in hd["location"]
    assert hd["location"].endswith("?" + query if query else "/")


def test_the_copy_says_whether_it_is_serving(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar")
    s, _, b = ask(h, "/-/status")
    assert s == 200 and b == {"detail": "ok"}  # a visitor is told no more
    s, _, b = ask(h, "/-/status", port=8443, peer=HERE)
    assert s == 200 and b["door"] == "sync" and b["apps"] == [{"app": "iostart", "state": "up", "error": ""}, {"app": "iocalendar", "state": "up", "error": ""}]
    h.by_name["iocalendar"].state = "failed"  # tried again by itself: the copy is serving all the same
    assert ask(h, "/-/status")[0] == 200
    h.by_name["iocalendar"].state = "starting"
    s, _, b = ask(h, "/-/status")
    assert s == 503 and b == {"detail": "starting"}

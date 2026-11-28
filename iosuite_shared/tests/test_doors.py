"""The three doors of a copy (iosuite_shared.doors) and the host that opens them (iosuite_shared.host): which app a
request is for (its own name, its folder, the start page), which door serves which path, where a request that came in
by the wrong door is sent, and what is passed across to another copy of the suite."""
import asyncio
import json
import time

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


def machine(monkeypatch, web=80, sync=8443, mcp=8444, https=443, certificate=None, **of_app):
    """The machine's ports, and the names of the certificate this copy serves (None: it serves none)."""
    from iosuite_shared import certs
    monkeypatch.setattr(config, "PORT", web)
    monkeypatch.setattr(config, "SYNC_PORT", sync)
    monkeypatch.setattr(config, "MCP_PORT", mcp)
    monkeypatch.setattr(config, "HTTPS_PORT", https)
    monkeypatch.setattr(config, "TLS_CERT_FILE", "")
    monkeypatch.setattr(config, "TLS_KEY_FILE", "")
    monkeypatch.setattr(certs, "SERVING", ("/suite.pem", None) if certificate else None)
    monkeypatch.setattr(certs, "NAMES", tuple(certificate or ()))
    monkeypatch.setattr(certs, "PAGES_PORT", https if certificate else 0)
    monkeypatch.setattr(config, "OF_APP", dict(of_app))


def a_host(*apps, hosts=None, remote=None, outer=("", 0, "")):
    """A copy running these apps, its table set by hand (never read from the database)."""
    from iosuite_shared import catalog
    h = Host([Entry(name=a, asgi=echo(a), state="up") for a in apps], ports={80: "web", 8443: "sync", 8444: "mcp"})
    h.table = doors.Table(hosts=dict(hosts or {}), folders={f: k for k, f in catalog.FOLDERS.items()}, remote=dict(remote or {}),
                          outer=outer, at=time.time() + 3600)
    return h


def ask(host, path, port=80, method="GET", name="home.example.com", headers=(), peer=OUTSIDE, query="", scheme="http", password=True):
    """One request through the host: (status, headers, body as JSON or text). At the port for devices (8443) it sends
    a password unless password is False (the app behind checks it; the host only looks for one)."""
    if port == 8443 and password and not any(k.lower() == "authorization" for k, _ in headers):
        headers = (*headers, ("authorization", "Bearer iocalendar-0a1b2c3d-x"))
    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": query.encode(), "scheme": scheme,
             "headers": [(b"host", name.encode()), *[(k.encode(), v.encode()) for k, v in headers]],
             "server": ("10.0.0.5", port), "client": (peer, 50000)}
    got = {"status": 0, "headers": {}, "body": b""}
    asked = []

    async def receive():
        if asked:  # the request was read: nothing more comes while the visitor waits for the answer
            await asyncio.Event().wait()
        asked.append(1)
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
    # an app's API is the pages': a phone's calendar talks CalDAV, and no native app asks ioCalendar's API
    assert doors.home("iocalendar", "/api/events") == ("web",)
    assert doors.home("iocalendar", "/api/events", "POST") == ("web",)
    assert doors.home("iocalendar", "/") == ("web",) and doors.home("iocalendar", "/static/app.js") == ("web",)
    assert doors.home("iocalendar", "/mcpx") == ("web",)
    # a profile download is a person's browser, with the pages
    assert doors.home("iocalendar", "/profile/token/calendar.mobileconfig") == ("web",)


def test_of_an_app_s_api_the_sync_door_serves_the_calls_its_native_apps_make(monkeypatch):
    """The port for devices is the one opened to the internet: of /api/ it serves what an app's manifest names
    ("devices"), call by call, and nothing else of any app."""
    from iosuite_shared import catalog
    apps = {**catalog.APPS, "ionote": {**catalog.APPS["ionote"], "devices": ["GET /api/sync", "POST /api/sync/push", "GET,PUT /api/notes/*/image",
                                                                             "POST,DELETE /api/auth/device", "POST /api/*/password"]}}
    monkeypatch.setattr(catalog, "APPS", apps)
    assert doors.home("ionote", "/api/sync") == ("web", "sync") and doors.home("ionote", "/api/sync", "HEAD") == ("web", "sync")
    assert doors.home("ionote", "/api/sync", "POST") == ("web",)                 # another method of a call that is named
    assert doors.home("ionote", "/api/sync/push", "POST") == ("web", "sync") and doors.home("ionote", "/api/sync/push") == ("web",)
    assert doors.home("ionote", "/api/notes/ab-12/image", "PUT") == ("web", "sync")
    for path in ("/api/notes/ab-12", "/api/notes/ab-12/image/x", "/api/notes//image", "/api/notes/a/b/image", "/api/sync/", "/api/syncx", "/api"):
        assert doors.home("ionote", path) == ("web",), path                      # * is one part of a path, and a call is the whole path
    # what tells about the API, the scripts the pages load and the suite's settings are nobody's call
    for path in ("/api/docs", "/api/openapi.json", "/api/auth/ui.js", "/api/live.js", "/api/live", "/api/suite-admin", "/api/suite-admin/proxy",
                 "/api/auth/app-passwords", "/api/auth/accounts", "/api/push/sw.js", "/api/status"):
        assert doors.home("ionote", path) == ("web",), path
    # of an account, a native app's own sign-in only, whatever a list says
    assert doors.home("ionote", "/api/auth/device", "POST") == ("web", "sync")
    assert doors.home("ionote", "/api/auth/password", "POST") == ("web",) and doors.home("ionote", "/api/auth/login", "POST") == ("web",)
    # an app whose manifest names no call has none of its API at this port
    for app in ("iodocs", "iothings", "iodns", "iobackup", "iocalendar", "iocontact", "iotask"):
        assert not catalog.APPS[app].get("devices"), app
        for path, method in (("/api/status", "GET"), ("/api/auth/me", "GET"), ("/api/auth/device", "POST"), ("/api/suite-admin", "GET")):
            assert doors.home(app, path, method) == ("web",), (app, path)


def test_the_apps_native_apps_have_their_calls_at_the_sync_door():
    """As the manifests are: ioPix's, ioNote's and ioHealth's own apps, and the start page's (bookmarks, widgets)."""
    for app in ("iopix", "ionote", "iohealth", "iostart"):
        for method in ("POST", "DELETE"):
            assert doors.allowed("sync", app, doors.DEVICE_PATH, method), app
        assert not doors.allowed("sync", app, "/api/auth/login", "POST") and not doors.allowed("sync", app, "/api/docs")
        assert not doors.allowed("sync", app, "/api/suite-admin") and not doors.allowed("sync", app, "/api/auth/app-passwords", "POST")
    assert doors.allowed("sync", "iopix", "/api/photos") and doors.allowed("sync", "iopix", "/api/import/stage", "POST")
    for path, method in (("/api/folders/7/upload", "POST"), ("/api/settings", "GET"), ("/api/duplicates", "GET"), ("/api/trash/empty", "POST"),
                         ("/api/users", "GET"), ("/api/suite-admin/proxy", "GET"), ("/api/auth/accounts", "GET"), ("/api/log", "GET")):
        assert not doors.allowed("sync", "iopix", path, method), path  # an admin's, at home only
    assert doors.allowed("sync", "iopix", "/api/auth/me") and doors.allowed("sync", "iopix", "/api/status")
    assert not doors.allowed("sync", "iopix", "/api/settings", "POST") and not doors.allowed("sync", "iopix", "/api/scan", "POST")  # an admin's, with the pages
    assert doors.allowed("sync", "ionote", "/api/sync") and doors.allowed("sync", "ionote", "/api/notes/u1/attachments/3", "DELETE")
    assert not doors.allowed("sync", "ionote", "/api/notes/u1") and not doors.allowed("sync", "ionote", "/api/notes")
    assert doors.allowed("sync", "iohealth", "/v1/sessions", "POST") and not doors.allowed("sync", "iohealth", "/api/status")
    assert doors.allowed("sync", "iostart", "/dav/ext/tree") and not doors.allowed("sync", "iostart", "/dav/nextcloud/index.php/login/v2", "POST")
    for path in ("/api/status", "/api/trmnl/today", "/api/display", "/api/wall", "/api/search", "/api/auth/me"):
        assert not doors.allowed("sync", "iostart", path), path


def test_the_pages_take_an_app_password_from_outside_for_an_app_s_api_as_before():
    """What the port for devices serves is one thing; where the pages' port takes an app password or a token from a
    request from outside is another, and wider: a wall display, an e-ink screen or a script is given the address
    people know. Never to sign in by a session or change an account, and never for a page."""
    assert doors.password_from_outside("iocalendar", "/api/events") and doors.password_from_outside("iocalendar", "/api/events", "POST")
    assert doors.password_from_outside("iostart", "/api/trmnl/today") and doors.password_from_outside("iomoney", "/api/accounts")
    assert doors.password_from_outside("iocalendar", "/api/auth/me")
    assert not doors.password_from_outside("iocalendar", "/api/auth/login", "POST")
    assert not doors.password_from_outside("iocalendar", "/api/auth/app-passwords", "POST")
    assert doors.password_from_outside("iocalendar", doors.DEVICE_PATH, "POST") and doors.password_from_outside("iocalendar", doors.DEVICE_PATH, "DELETE")
    assert doors.password_from_outside("iopix", "/thumb/12") and not doors.password_from_outside("iopix", "/thumb/12", "POST")
    assert not doors.password_from_outside("iocalendar", "/") and not doors.password_from_outside("iocalendar", "/static/app.js")
    assert not doors.password_from_outside("iocalendar", "/thumb/12")


def test_pictures_a_native_app_shows_are_served_at_both_doors():
    """ioPix's thumbnails, previews and videos are outside /api/, and its Apple TV app, widgets and share sheet show
    them as its pages do: read at either door, changed at neither."""
    for path in ("/thumb/12", "/preview/12", "/face/3", "/facecrop/12/1/2/3/4.jpg", "/video/12.mp4", "/video/12/frame", "/orig/12"):
        assert doors.home("iopix", path) == ("web", "sync"), path
        assert doors.home("iopix", path, "HEAD") == ("web", "sync")
        assert doors.home("iopix", path, "POST") == ("web",), path
    assert doors.home("iopix", "/thumbs") == ("web",) and doors.home("iopix", "/") == ("web",)
    assert doors.home("iocalendar", "/thumb/12") == ("web",)  # another app's manifest says nothing of the kind


def test_a_picture_is_answered_at_the_sync_door_by_its_rules(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iopix")
    sent = [("cookie", "ios_session=abc"), ("authorization", "Basic YTpi")]
    s, hd, b = ask(h, "/pix/thumb/12", port=8443, query="fit=square", headers=sent)
    assert s == 200 and "location" not in hd and b["door"] == "sync" and b["cookie"] is None and b["authorization"] == "Basic YTpi"
    assert b["app"] == "iopix" and b["path"] == "/thumb/12" and b["folder"] == "/pix"
    s, _, b = ask(h, "/pix/thumb/12", headers=sent)  # with the pages it is the browser's, signed in by its cookie
    assert s == 200 and b["door"] == "web" and b["cookie"] == "ios_session=abc"
    s, hd, _ = ask(h, "/pix/", port=8443, name="home.example.com:8443")  # its pages are the pages': not here, and not told where
    assert s == 404 and "location" not in hd


def test_a_native_app_signs_its_person_in_at_the_sync_door_and_nothing_else_of_the_account_is_written_there():
    """The name and password typed in a native app get it an app password (iosuite_shared.routers), and signing out
    gives it back: the one path of /api/auth/ the door for devices takes a write at. A browser's sign-in, with its
    session, and every change to an account stay with the pages."""
    for method in ("POST", "DELETE"):
        assert doors.home("iopix", doors.DEVICE_PATH, method) == ("web", "sync")
        assert doors.allowed("sync", "iostart", doors.DEVICE_PATH, method)
    assert doors.home("iopix", doors.DEVICE_PATH + "/x", "POST") == ("web",) and doors.home("iopix", doors.DEVICE_PATH + "s", "POST") == ("web",)
    assert doors.home("iopix", "/api/auth/app-passwords", "POST") == ("web",) and doors.home("iopix", "/api/auth/password", "POST") == ("web",)
    assert doors.home("iocalendar", doors.DEVICE_PATH, "POST") == ("web",)  # an app no native app signs in to: its phones have a profile


def test_a_device_s_sign_in_reaches_the_app_at_the_sync_door(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iopix")
    s, _, b = ask(h, "/pix/api/auth/device", port=8443, method="POST")
    assert s == 200 and b["door"] == "sync" and b["app"] == "iopix" and b["path"] == "/api/auth/device"
    s, _, b = ask(h, "/api/auth/device", port=8443, method="POST")          # the start page, at the root
    assert s == 200 and b["door"] == "sync" and b["app"] == "iostart"
    s, _, b = ask(h, "/pix/api/auth/login", port=8443, method="POST")      # a browser's sign-in is not served here
    assert s == 404 and b["door"] == "sync"


def test_nobody_signs_in_by_a_session_at_the_sync_door():
    assert doors.home("iocalendar", "/api/auth/login", "POST") == ("web",)
    assert doors.home("iocalendar", "/api/auth/account", "PUT") == ("web",)
    assert doors.home("ionote", "/api/auth/me") == ("web", "sync")  # an app asking who its password is
    assert doors.home("ionote", "/api/auth/login", "POST") == ("web",) and doors.home("ionote", "/api/auth/logout", "POST") == ("web",)
    assert not doors.allowed("sync", "iocalendar", "/api/auth/login", "POST") and doors.allowed("web", "iocalendar", "/api/auth/login", "POST")


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
    h = a_host("iostart", "iocalendar", "ionote")
    sent = [("cookie", "ios_session=abc"), ("authorization", "Basic YTpi")]
    s, _, b = ask(h, "/calendar/api/events", headers=sent)
    assert s == 200 and b["door"] == "web" and b["cookie"] == "ios_session=abc"
    s, _, b = ask(h, "/notes/api/sync", port=8443, headers=sent)
    assert s == 200 and b["door"] == "sync" and b["cookie"] is None and b["authorization"] == "Basic YTpi"
    s, hd, b = ask(h, "/calendar/api/events", port=8443, headers=sent)  # not a call of a native app: not at this port
    assert s == 404 and "location" not in hd and b["door"] == "sync"
    s, _, b = ask(h, "/calendar/dav/alex/", port=8443, method="REPORT", headers=sent)
    assert s == 200 and b["cookie"] is None and b["path"] == "/dav/alex/"
    s, _, b = ask(h, "/calendar/mcp", port=8444, method="POST", headers=sent)
    assert s == 200 and b["door"] == "mcp" and b["cookie"] is None


def test_the_pages_port_answers_a_device_s_path_and_mcp_too(monkeypatch):
    """One port is enough for a whole server: a device's path or /mcp asked at the pages' port is answered there, by
    its own door's rules (no session: an app password or a token instead)."""
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", hosts={"calendar.example.com": "iocalendar"})
    sent = [("cookie", "iosuite_session=abc"), ("authorization", "Basic abc")]
    s, hd, b = ask(h, "/calendar/dav/alex/home/", method="PROPFIND", headers=sent)
    assert s == 200 and "location" not in hd and b["door"] == "sync" and b["cookie"] is None and b["authorization"] == "Basic abc"
    assert b["app"] == "iocalendar" and b["path"] == "/dav/alex/home/" and b["folder"] == "/calendar"
    s, _, b = ask(h, "/ics/secret/home.ics", name="calendar.example.com", query="x=1", headers=sent)
    assert s == 200 and b["door"] == "sync" and b["path"] == "/ics/secret/home.ics" and b["folder"] == ""
    s, _, b = ask(h, "/dav/ext/tree", method="PUT", headers=sent)
    assert s == 200 and b["app"] == "iostart" and b["door"] == "sync"
    s, _, b = ask(h, "/calendar/mcp", method="POST", headers=sent)
    assert s == 200 and b["door"] == "mcp" and b["cookie"] is None
    # the pages are still the pages there, and a page below a sync prefix (the screen a client opens) too
    s, _, b = ask(h, "/calendar/api/events", headers=sent)
    assert s == 200 and b["door"] == "web" and b["cookie"] == "iosuite_session=abc"


def test_a_phone_looking_its_account_up_reaches_the_app(monkeypatch):
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", "iocontact")
    s, _, b = ask(h, "/.well-known/caldav", method="PROPFIND")  # the pages' port answers it as the sync door does
    assert s == 200 and b["app"] == "iocalendar" and b["door"] == "sync" and b["path"] == "/.well-known/caldav"
    s, _, b = ask(h, "/.well-known/carddav")
    assert s == 200 and b["app"] == "iocontact" and b["door"] == "sync"
    # the port for devices does not serve it: a device set up by a profile is given its whole address
    s, _, b = ask(h, "/.well-known/caldav", port=8443, method="PROPFIND")
    assert s == 404


def test_the_sync_door_sends_nothing_on(monkeypatch):
    """The port for devices refuses what is not its own, the same way whatever was asked, and says nothing of where
    the pages are."""
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", "iodocs", "iomoney")
    refused = set()
    for path in ("/", "/calendar/", "/calendar/api/events", "/calendar/api/docs", "/calendar/api/openapi.json", "/api/docs", "/api/openapi.json",
                 "/api/auth/ui.js", "/api/live.js", "/api/push/sw.js", "/static/frame.js", "/static/base.css", "/api/status", "/api/wall",
                 "/api/trmnl/today", "/api/display", "/api/suite-admin", "/docs/", "/docs/api/status", "/docs/api/documents", "/money/", "/money/api/status",
                 "/money/api/rules", "/money/api/monarch", "/nothing/here"):
        s, hd, b = ask(h, path, port=8443, name="home.example.com:8443")
        assert s == 404 and "location" not in hd and b["door"] == "sync", path
        refused.add(b["detail"])
    said = refused.pop() if len(refused) == 1 else ""
    assert said and "ioMoney" not in said and "ioDocs" not in said  # one answer: it does not tell which apps are there
    s, hd, _ = ask(h, "/dav/nextcloud/index.php/login/v2/flow/abc", port=8443, name="home.example.com:8443")
    assert s == 404 and "location" not in hd
    # nobody signs in by a session here
    s, _, b = ask(h, "/calendar/api/auth/login", port=8443, method="POST")
    assert s == 404 and b["door"] == "sync"
    assert ask(h, "/dav/nextcloud/index.php/login/v2/grant", port=8443, method="POST")[0] == 404
    assert ask(h, "/calendar/", port=8443, method="POST")[0] == 404


def test_the_port_for_devices_answers_nothing_without_a_password_but_the_sign_in(monkeypatch):
    """The port open to the internet: whatever the address, served there or not, no password is a 401 with the
    challenge a sync client answers. The one call it takes without one is a device signing in."""
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", "iocontact", "iopix", "iohealth")
    for path, method in (("/dav/ext/tree", "GET"), ("/calendar/dav/alex/", "PROPFIND"), ("/pix/api/status", "GET"), ("/pix/thumb/7", "GET"),
                         ("/health/v1/health", "GET"), ("/contacts/cal/abc/family.ics", "GET"), ("/api/docs", "GET"), ("/nothing", "GET"),
                         ("/pix/api/auth/device", "DELETE"), ("/-/status", "GET")):
        s, hd, b = ask(h, path, port=8443, method=method, password=False)
        assert s == 401 and hd["www-authenticate"].startswith("Basic") and "location" not in hd, path
    for path in ("/api/auth/device", "/pix/api/auth/device", "/health/api/auth/device"):
        s, _, b = ask(h, path, port=8443, method="POST", password=False)
        assert s == 200 and b["door"] == "sync", path
    assert ask(h, "/calendar/api/auth/device", port=8443, method="POST", password=False)[0] == 404  # no native app of its own
    # what the port does not serve stays refused with a password too; the pages' port is as it was
    assert ask(h, "/api/docs", port=8443)[0] == 404
    assert ask(h, "/pix/api/status")[0] == 200


def test_secret_links_and_lookups_are_not_served_at_the_port_for_devices(monkeypatch):
    """The calendar links whose secret in the address is their only sign-in, and the lookups a profile never needs,
    are served at the pages' port only (the manifests' homeOnly). The birthday calendar a contacts profile adds is."""
    machine(monkeypatch)
    h = a_host("iostart", "iocalendar", "iocontact", "iotask")
    for path in ("/calendar/ics/abc/family.ics", "/.well-known/caldav", "/.well-known/carddav", "/calendar/.well-known/caldav", "/tasks/.well-known/caldav"):
        assert ask(h, path, port=8443)[0] == 404, path
    assert ask(h, "/calendar/ics/abc/family.ics")[0] == 200 and ask(h, "/.well-known/caldav")[0] == 200
    s, _, b = ask(h, "/contacts/cal/abc/family.ics", port=8443)
    assert s == 200 and b["app"] == "iocontact"


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
    start = {"PUBLIC_URLS": ["https://home.example.com"], "OWN_URL": "", "SYNC_URLS": ["https://sync.example.com"], "SYNC_URL_OWN": ""}
    machine(monkeypatch, iocalendar=cal, iostart=start)
    h = a_host("iostart", "iocalendar", hosts={"calendar.example.com": "iocalendar", "calsync.example.com": "iocalendar"})
    # a device's path at the pages' port is answered there all the same; the stored address is what the app hands out
    assert ask(h, "/calendar/dav/alex/", method="PROPFIND")[0] == 200
    assert ask(h, "/dav/alex/", port=8443, name="calsync.example.com", method="PROPFIND")[2]["app"] == "iocalendar"
    for path, name in (("/", "calsync.example.com"), ("/calendar/", "sync.example.com")):  # a page is not sent on from there
        s, hd, _ = ask(h, path, port=8443, name=name)
        assert s == 404 and "location" not in hd


def test_with_the_other_two_ports_off_the_pages_port_answers_everything(monkeypatch):
    machine(monkeypatch, sync=0, mcp=0)
    h = a_host("iostart", "iocalendar")
    s, hd, b = ask(h, "/calendar/dav/alex/", method="PROPFIND", headers=[("cookie", "iosuite_session=abc")])
    assert s == 200 and "location" not in hd and b["door"] == "sync" and b["cookie"] is None
    s, _, b = ask(h, "/calendar/mcp", method="POST")
    assert s == 200 and b["door"] == "mcp"
    assert doors.ports() == {80: "web"}


def test_a_door_s_own_port_is_left_out_of_its_address(monkeypatch, tmp_path):
    machine(monkeypatch, web=8080, sync=80, mcp=443)
    assert doors._at_port("home.example.com", "web", "/calendar") == "http://home.example.com:8080/calendar"
    assert doors._at_port("home.example.com", "sync", "") == "http://home.example.com"
    assert doors._at_port("fd00::1", "sync", "") == "http://[fd00::1]"
    # with a certificate: https for a name it holds for, the pages at their HTTPS port; any other name as before
    machine(monkeypatch, web=8080, sync=80, mcp=443, https=8081, certificate=["home.example.com", "*.apps.example.com"])
    assert doors.ports() == {8080: "web", 80: "sync", 443: "mcp", 8081: "web"} and doors.secure_ports() == [8081, 80, 443]
    assert doors._at_port("home.example.com", "mcp", "/pix") == "https://home.example.com/pix"
    assert doors._at_port("home.example.com", "web", "") == "https://home.example.com:8081"
    assert doors._at_port("calendar.apps.example.com", "sync", "") == "https://calendar.apps.example.com:80"
    assert doors._at_port("192.168.1.151", "sync", "/calendar") == "http://192.168.1.151/calendar"
    assert doors._at_port("192.168.1.151", "web", "") == "http://192.168.1.151:8080"
    machine(monkeypatch, certificate=["home.example.com"])
    assert doors._at_port("home.example.com", "web", "/calendar") == "https://home.example.com/calendar"
    assert doors.port_of("web") == 80 and doors.port_of("web", https=True) == 443
    machine(monkeypatch)
    assert doors.ports() == {80: "web", 8443: "sync", 8444: "mcp"} and doors.secure_ports() == []


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
    # that copy has no MCP port: its pages' port answers /mcp too, so that is where it goes, from either door here
    s, _, b = ask(h, "/pix/mcp", port=8444, method="POST")
    assert s == 200 and passed[-1] == ("http://10.0.0.9", "iopix", "/pix", "/mcp")
    s, _, b = ask(h, "/pix/mcp", method="POST")
    assert s == 200 and passed[-1] == ("http://10.0.0.9", "iopix", "/pix", "/mcp") and len(passed) == 4
    # a copy with no address at all for an app is said so plainly
    h.table.remote["iopix"] = {"web": None, "sync": None, "mcp": None}
    s, _, b = ask(h, "/pix/mcp", method="POST")
    assert s == 502 and "no door for MCP" in b


def test_a_request_passed_across_arrives_inside_the_app(monkeypatch):
    """Two copies joined for real: the first passes what is asked in ioPix's folder on, and the second hands it to
    ioPix with the path inside the app, in that folder, the visitor's cookie with it."""
    import httpx2
    machine(monkeypatch)
    second = a_host("iopix")
    seen = []

    async def other_copy(scope, receive, send):
        seen.append((scope["path"], scope["server"][0]))
        await second(scope, receive, send)
    wire = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=other_copy, client=(HERE, 50001)), trust_env=False)
    monkeypatch.setattr(doors, "client", lambda: wire)
    first = a_host("iostart", "iocalendar", remote={"iopix": {"web": "http://10.0.0.9", "sync": "http://10.0.0.9:8443", "mcp": None}})
    s, _, b = ask(first, "/pix/api/photos", headers=[("cookie", "ios_session=abc")], query="q=sea")
    assert s == 200 and b["app"] == "iopix" and b["path"] == "/api/photos" and b["folder"] == "/pix" and b["door"] == "web"
    assert b["cookie"] == "ios_session=abc"
    assert seen == [("/api/photos", "10.0.0.9")]
    s, _, b = ask(first, "/pix/api/photos", port=8443, headers=[("authorization", "Basic abc")])
    assert s == 200 and b["path"] == "/api/photos" and b["folder"] == "/pix" and b["door"] == "sync" and b["authorization"] == "Basic abc"
    assert len(seen) == 2
    # what the port for devices does not serve of ioPix is refused by the copy that was asked: nothing is passed on
    assert ask(first, "/pix/api/settings", port=8443, method="POST", headers=[("authorization", "Basic abc")])[0] == 404
    assert ask(first, "/pix/api/docs", port=8443)[0] == 404 and len(seen) == 2
    # at ioPix's own name there is no folder to tell the other copy about
    first.table.hosts["photos.example.com"] = "iopix"
    s, _, b = ask(first, "/api/photos", name="photos.example.com")
    assert s == 200 and b["app"] == "iopix" and b["path"] == "/api/photos" and not b["folder"]


def test_a_copy_that_started_a_moment_ago_is_believed(monkeypatch):
    """The list of the suite's machines is read every half minute. A copy that registered since says it is one
    (X-IoSuite-App): the list is read again before it is turned away, at most every few seconds."""
    from iosuite_shared import db, suite
    machine(monkeypatch)
    suite.invalidate()
    suite.register("iostart", "ioStart", internal_url="http://10.0.0.5")
    h = a_host("iostart", "iocalendar")
    said = [("x-iosuite-app", "iocalendar"), ("x-forwarded-prefix", "/calendar")]
    s, _, b = ask(h, "/api/events", headers=said, peer="10.0.0.9")
    assert s == 200 and b["app"] == "iostart"  # anybody can send that header: not believed
    now = int(time.time())  # another copy starts, in a process of its own: its row is there, this copy's list is as it was
    db.ex("INSERT INTO ios_apps (app, name, internal_url, created_at, updated_at, last_seen_at) VALUES ('iopix', 'ioPix', 'http://10.0.0.9/pix', %s, %s, %s)", (now, now, now))
    suite._machines["at"] = time.time() - 1
    assert ask(h, "/api/events", headers=said, peer="10.0.0.9")[2]["app"] == "iostart"  # the list was read a second ago
    suite._machines["at"] = time.time() - 5
    s, _, b = ask(h, "/api/events", headers=said, peer="10.0.0.9")
    assert s == 200 and b["app"] == "iocalendar" and b["folder"] == "/calendar" and b["path"] == "/api/events"
    assert ask(h, "/api/events", headers=said, peer="10.0.0.77")[2]["app"] == "iostart"  # and still nobody else


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
    # the other copy's doors, without the app's folder: a request is passed across with its path inside the app
    assert t.remote["iopix"] == {"web": "http://10.0.0.9", "sync": "http://10.0.0.9:8443", "mcp": None}
    assert t.remote["iomoney"]["web"] == "http://10.0.0.9" and t.remote["iomoney"]["sync"] is None


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


def test_an_app_is_in_the_suite_s_list_as_soon_as_it_is_up():
    """Another copy passes an app's requests here from the moment the app is up: the host writes its row at start,
    not at the first request somebody happens to make to this copy."""
    from fastapi import FastAPI
    called = []

    class Auth:
        def register(self):
            called.append("iocalendar")
    app = FastAPI()
    app.state.iosuite_auth = Auth()
    h = Host([Entry(name="iocalendar", asgi=app), Entry(name="iotask", asgi=FastAPI())], ports={80: "web"})  # iotask: nothing to register

    async def go():
        await h.start()
        assert [e.state for e in h.entries] == ["up", "up"] and called == ["iocalendar"]
        await h.stop()
    asyncio.run(go())


# ---- a copy that answers HTTPS itself (iosuite_shared.certs)
def secure_host(monkeypatch, *apps, **kw):
    """A copy that serves a certificate for home.example.com and every name under apps.example.com: the pages on
    443 as well as 80, devices and MCP on their ports."""
    machine(monkeypatch, certificate=["home.example.com", "*.apps.example.com"])
    h = a_host(*apps, **kw)
    h.ports = doors.ports()
    return h


def test_the_pages_asked_without_https_by_a_name_of_the_certificate_are_sent_on(monkeypatch):
    h = secure_host(monkeypatch, "iostart", "iocalendar")
    assert h.ports == {80: "web", 8443: "sync", 8444: "mcp", 443: "web"}
    s, hd, _ = ask(h, "/calendar/api/events", query="from=2026-11-01&q=a%20b")
    assert s == 301 and hd["location"] == "https://home.example.com/calendar/api/events?from=2026-11-01&q=a%20b"
    s, hd, _ = ask(h, "/calendar/api/events", method="POST")
    assert s == 308 and hd["location"] == "https://home.example.com/calendar/api/events"  # asked again as it was
    assert ask(h, "/", name="Calendar.Apps.Example.com:80")[1]["location"] == "https://calendar.apps.example.com/"
    # over HTTPS already: served, at either port of the pages
    s, _, b = ask(h, "/calendar/api/events", port=443, scheme="https")
    assert s == 200 and b["app"] == "iocalendar" and b["door"] == "web"
    # by a name the certificate does not hold for (the server's address, a name of the home network): as before
    assert ask(h, "/calendar/api/events", name="192.168.1.151")[0] == 200
    assert ask(h, "/calendar/api/events", name="nas.lan")[0] == 200
    # the suite's own servers and a reverse proxy on this machine: as before
    assert ask(h, "/calendar/api/events", peer=HERE)[0] == 200
    # through a proxy the suite was not told about: never sent round in circles
    for said in ("x-forwarded-proto", "x-forwarded-for", "cf-connecting-ip", "via", "forwarded"):
        assert ask(h, "/calendar/api/events", headers=[(said, "https")])[0] == 200
    # devices and MCP are never sent on: what was set up without HTTPS goes on working at the same port
    s, _, b = ask(h, "/calendar/dav/alex/", port=8443, method="PROPFIND")
    assert s == 200 and b["door"] == "sync"
    assert ask(h, "/calendar/mcp", port=8444, method="POST")[0] == 200
    # a copy whose HTTPS port for the pages is taken sends nobody there
    monkeypatch.setattr("iosuite_shared.certs.PAGES_PORT", 0)
    assert ask(h, "/calendar/api/events")[0] == 200
    # another port than 443 is named
    monkeypatch.setattr("iosuite_shared.certs.PAGES_PORT", 8081)
    assert ask(h, "/x")[1]["location"] == "https://home.example.com:8081/x"
    # and a copy without a certificate sends nobody anywhere
    machine(monkeypatch)
    assert ask(a_host("iostart", "iocalendar"), "/calendar/api/events")[0] == 200


def test_a_request_at_the_wrong_door_goes_to_https_when_the_certificate_holds_for_the_name(monkeypatch):
    h = secure_host(monkeypatch, "iostart", "iocalendar")
    # a CalDAV address asked with the pages over HTTPS is answered there, by the rules of the door for devices
    s, _, b = ask(h, "/calendar/dav/alex/", port=443, scheme="https", method="PROPFIND", headers=[("cookie", "s=1")])
    assert s == 200 and b["door"] == "sync" and b["cookie"] is None
    assert ask(h, "/calendar/", port=8443, scheme="https")[0] == 404  # a page is not this port's, and is not sent on


def test_the_authority_s_check_is_answered_at_any_door_by_any_copy(monkeypatch):
    from iosuite_shared import certs
    machine(monkeypatch)
    h = a_host("iocalendar")  # a copy without the start page, and without a certificate yet
    certs._publish("http-01", "home.example.com", "tok-1", "tok-1.thumbprint")
    s, hd, b = ask(h, "/.well-known/acme-challenge/tok-1")
    assert s == 200 and b == "tok-1.thumbprint" and hd["content-type"].startswith("text/plain")
    assert ask(h, "/.well-known/acme-challenge/tok-1", port=8443)[0] == 200
    s, _, b = ask(h, "/.well-known/acme-challenge/other")
    assert s == 404 and "No certificate is being asked for" in b
    h = secure_host(monkeypatch, "iostart")  # with a certificate: answered, not sent on to HTTPS (a renewal's check comes to port 80)
    assert ask(h, "/.well-known/acme-challenge/tok-1")[2] == "tok-1.thumbprint"
    certs._remove("http-01", "home.example.com", "tok-1")
    assert ask(h, "/.well-known/acme-challenge/tok-1")[0] == 404

"""The status dots (iostart/status.py) and each person's own layout (iostart/layout.py)."""
import pytest

from conftest import via_providers
from iostart import layout, status, widgets
from iosuite_shared import testing


@pytest.fixture(autouse=True)
def fresh():
    status.forget()
    yield
    status.forget()


def test_apps_status_from_each_apps_status(client, monkeypatch):
    answers = {"iopix": {"app": "ioPix", "version": "1.4.0"},
               "iohealth": {"app": "ioHealth", "version": "2.0"},
               "iocalendar": {"app": "ioCalendar", "version": "0.9"},
               "iotask": {"app": "ioTask", "version": "0.1"},
               "iomoney": {"app": "ioMoney", "version": "0.1"},
               "iodocs": {"app": "ioDocs", "version": "0.1"}}
    asked = []

    def fake(request, key, path, params=None, raw=False):
        asked.append(key)
        if key == "iocontact":
            raise widgets.Unavailable(403, "iocontact answered 401")  # up, but not open to this account
        if key == "ionote":
            raise widgets.Unavailable(502, "ionote is not reachable (URLError)")
        return answers[key]
    monkeypatch.setattr(widgets, "fetch", fake)
    d = client.get("/api/apps/status").json()["items"]
    assert d["iopix"] == {"ok": True, "version": "1.4.0", "why": None}
    assert d["iohealth"]["ok"] and d["iocalendar"]["ok"]
    assert d["iocontact"]["ok"] is True and d["ionote"] == {"ok": False, "version": None, "why": "ionote is not reachable (URLError)"}
    assert sorted(asked) == ["iocalendar", "iocontact", "iodocs", "iohealth", "iomoney", "ionote", "iopix", "iotask"]
    client.get("/api/apps/status")
    assert len(asked) == 8  # remembered for a minute
    client.cookies.clear()
    assert client.get("/api/apps/status").status_code == 401


def test_bookmarks_status_pings_each_link(client, monkeypatch):
    client.post("/api/bookmarks/groups", json={"name": "Home"})
    gid = client.get("/api/bookmarks").json()["groups"][0]["id"]
    for name, href in [("Router", "http://router.lan"), ("NAS", "https://nas.lan:5001")]:
        client.post(f"/api/bookmarks/groups/{gid}/links", json={"name": name, "href": href})
    links = {l["name"]: l["id"] for l in client.get("/api/bookmarks").json()["groups"][0]["links"]}
    pinged = []

    def fake(href):
        pinged.append(href)
        return {"ok": href.startswith("http://router"), "status": 200 if href.startswith("http://router") else None}
    monkeypatch.setattr(status, "_ping", fake)
    d = client.get("/api/bookmarks/status").json()["items"]
    assert d[str(links["Router"])] == {"ok": True, "status": 200} and d[str(links["NAS"])]["ok"] is False
    assert sorted(pinged) == ["http://router.lan", "https://nas.lan:5001"]
    client.get("/api/bookmarks/status")
    assert len(pinged) == 2  # remembered


def test_ping_without_a_server():
    import ipaddress
    assert status._ping("mailto:x@y") == {"ok": None, "status": None}
    assert status._allowed(ipaddress.ip_address("192.168.1.1")) and status._allowed(ipaddress.ip_address("10.0.0.7"))  # bookmarks are for the home network


def test_ping_never_reaches_this_server_or_metadata_and_never_follows_a_redirect():
    """A bookmark editor cannot make the server probe itself or a cloud metadata service, and a redirect is an
    answer (up), not a request to another address."""
    import http.server
    import threading
    for href in ("http://127.0.0.1:9/", "http://localhost/", "http://[::1]/", "http://169.254.169.254/latest/", "http://0.0.0.0/", "ftp://x/"):
        assert status._ping(href) == {"ok": None, "status": None}, href
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self):
            seen.append(self.path)
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/secret")
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        # the server is reached through its own address only when it is not loopback: pretend with the check off
        href = f"http://127.0.0.1:{srv.server_port}/x"
        import unittest.mock as um
        with um.patch.object(status, "_allowed", lambda ip: True):
            assert status._ping(href) == {"ok": True, "status": 302}
        assert seen == ["/x"]  # the redirect was not followed
    finally:
        srv.shutdown()


def test_my_layout(client):
    assert client.get("/api/me/layout").json() == layout.EMPTY
    assert client.get("/api/apps").json()["layout"] == layout.EMPTY
    r = client.put("/api/me/layout", json={"hidden": ["ionote", "week", "ionote"], "order": ["iocalendar", "iopix"], "cards": ["strip", "birthdays"], "strip": "onthisday"})
    assert r.status_code == 200 and r.json() == {**layout.EMPTY, "hidden": ["ionote", "week"], "order": ["iocalendar", "iopix"], "cards": ["strip", "birthdays"], "strip": "onthisday"}
    assert client.put("/api/me/layout", json={"cards": ["strip", "strip"]}).status_code == 400
    assert client.put("/api/me/layout", json={"cards": ["iopix"]}).status_code == 400
    assert client.get("/api/apps").json()["layout"]["order"] == ["iocalendar", "iopix"]
    assert client.put("/api/me/layout", json={"hidden": ["Not an app!"]}).status_code == 400
    assert client.put("/api/me/layout", json={"order": ["iopix", "iopix"]}).status_code == 400
    assert client.put("/api/me/layout", json={"strip": "all"}).status_code == 400
    assert client.put("/api/me/layout", json={"search": "altavista"}).status_code == 400
    assert client.put("/api/me/layout", json={"search": "google"}).json()["search"] == "google"
    assert client.put("/api/me/layout", json={"stripMove": "spin"}).status_code == 400
    assert client.put("/api/me/layout", json={"stripEvery": 7}).status_code == 400
    r = client.put("/api/me/layout", json={"stripMove": "page", "stripEvery": 300}).json()
    assert (r["stripMove"], r["stripEvery"]) == ("page", 300)
    assert client.put("/api/me/layout", json={"wallBg": "aquarium"}).status_code == 400
    assert client.put("/api/me/layout", json={"wallEvery": 7}).status_code == 400
    assert client.put("/api/me/layout", json={"wallEvery": True}).status_code == 400
    r = client.put("/api/me/layout", json={"wallBg": "sky", "wallEvery": 300}).json()
    assert (r["wallBg"], r["wallEvery"]) == ("sky", 300)
    for bad in ("album:", "album:x", "album:0", "everything", 3):
        assert client.put("/api/me/layout", json={"wallPhotos": bad}).status_code == 400, bad
    assert client.put("/api/me/layout", json={"wallPhotos": "album:12"}).json()["wallPhotos"] == "album:12"
    assert client.put("/api/me/layout", json={"wallPhotos": "favorites"}).json()["wallPhotos"] == "favorites"
    assert client.put("/api/me/layout", json={"style": "mosaic"}).status_code == 400
    assert client.put("/api/me/layout", json={"style": "today"}).json()["style"] == "today"
    assert client.put("/api/me/layout", json={"style": "cards"}).json()["style"] == "cards"
    assert client.put("/api/me/layout", json=[]).status_code == 400
    # a size for each app, what the Today card holds, the top row, the look, the bookmarks
    for bad in ({"sizes": {"iopix": "huge"}}, {"sizes": {"Not an app!": "card"}}, {"sizes": ["iopix"]}, {"todayOff": ["weather"]}, {"todayDays": 9}, {"todayDays": True},
                {"units": "kelvin"}, {"weatherOff": ["rain"]}, {"accent": "#ff0000"}, {"text": "tiny"}, {"bookmarks": "cloud"}):
        assert client.put("/api/me/layout", json=bad).status_code == 400, bad
    r = client.put("/api/me/layout", json={"sizes": {"iohealth": "tile", "iomoney": "card"}, "todayOff": ["bills", "photos", "bills"], "todayDays": 0, "hidden": ["greeting", "weather", "search"],
                                           "units": "imperial", "accent": "teal", "text": "large", "bookmarks": "icons"}).json()
    assert r == {**layout.EMPTY, "sizes": {"iohealth": "tile", "iomoney": "card"}, "todayOff": ["bills", "photos"], "todayDays": 0, "hidden": ["greeting", "weather", "search"],
                 "units": "imperial", "accent": "teal", "text": "large", "bookmarks": "icons"}
    assert client.put("/api/me/layout", json={"todayDays": 2}).json()["todayDays"] == 2
    assert client.put("/api/me/layout", json={"weatherOff": ["pollen", "sun", "pollen"]}).json()["weatherOff"] == ["pollen", "sun"]
    assert client.put("/api/me/layout", json={}).json() == layout.EMPTY
    # another account has its own
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"})
    client.put("/api/me/layout", json={"hidden": ["iohealth"]})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/me/layout").json()["hidden"] == []


DEV, DEV2 = "kitchen0tablet1", "phone000abc"


def test_a_setup_per_device(client):
    """A device keeps a setup of its own; the others stay on the account's, and removing it goes back to that."""
    client.put("/api/me/layout", json={"hidden": ["ionote"], "style": "cards"})
    got = client.get("/api/apps").json()
    assert got["layoutOf"] == {"scope": "account", "device": None, "devices": [], "family": False}
    assert client.get(f"/api/apps?device={DEV}").json()["layoutOf"]["scope"] == "account"  # nothing of its own yet
    r = client.put(f"/api/me/layout?device={DEV}&name=%20Kitchen%20%20tablet%20", json={"style": "today", "text": "large"})
    assert r.status_code == 200 and (r.json()["style"], r.json()["text"], r.json()["hidden"]) == ("today", "large", [])
    got = client.get(f"/api/apps?device={DEV}").json()
    assert got["layout"]["style"] == "today"
    assert got["layoutOf"] == {"scope": "device", "device": {"id": DEV, "name": "Kitchen tablet"}, "devices": [{"id": DEV, "name": "Kitchen tablet"}], "family": False}
    assert client.get(f"/api/me/layout?device={DEV}").json()["style"] == "today"
    # the account's is untouched, and is what another device and no device get
    for q in ("", f"?device={DEV2}", "?device=not%20an%20id"):
        got = client.get(f"/api/apps{q}").json()
        assert (got["layout"]["style"], got["layout"]["hidden"], got["layoutOf"]["scope"]) == ("cards", ["ionote"], "account"), q
    assert client.get("/api/me/layout/where").json()["layoutOf"]["devices"] == [{"id": DEV, "name": "Kitchen tablet"}]
    # an empty setup is still the device's own (the page as it comes, there only)
    assert client.put(f"/api/me/layout?device={DEV2}&name=Phone", json={}).json() == layout.EMPTY
    assert client.get(f"/api/apps?device={DEV2}").json()["layoutOf"]["scope"] == "device"
    assert client.put("/api/me/layout?device=short", json={}).status_code == 400
    assert client.put(f"/api/me/layout?device={DEV}", json={"style": "mosaic"}).status_code == 400
    assert client.delete(f"/api/me/layout/devices/{DEV}").json() == {"devices": [{"id": DEV2, "name": "Phone"}]}
    assert client.get(f"/api/apps?device={DEV}").json()["layout"]["hidden"] == ["ionote"]
    # no more than a dozen
    for i in range(layout.DEVICES_MOST - 1):
        assert client.put(f"/api/me/layout?device=device{i:04d}", json={}).status_code == 200
    assert client.put("/api/me/layout?device=onetoomany00", json={}).status_code == 400
    assert client.put(f"/api/me/layout?device={DEV2}&name=My%20phone", json={"accent": "green"}).json()["accent"] == "green"  # one it has already
    # another person's devices are their own
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    got = client.get(f"/api/apps?device={DEV2}").json()
    assert got["layout"] == layout.EMPTY and got["layoutOf"] == {"scope": "none", "device": None, "devices": [], "family": False}


def test_the_family_starting_point(client):
    """An admin's setup for whoever has none of their own, and a setup given to one person."""
    kid = testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"}).json()["id"]
    client.put("/api/me/layout", json={"hidden": ["iohealth"]})  # the admin's own
    assert client.get("/api/layout/family").json()["layout"] is None
    assert client.put("/api/layout/family", json={"style": "mosaic"}).status_code == 400
    r = client.put("/api/layout/family", json={"style": "today", "hidden": ["iomoney"], "accent": "amber"})
    assert r.status_code == 200 and r.json()["layout"] == {**layout.EMPTY, "style": "today", "hidden": ["iomoney"], "accent": "amber"}
    got = client.get("/api/layout/family").json()
    assert got["layout"]["style"] == "today"
    assert {p["name"]: (p["own"], p["devices"]) for p in got["people"]} == {"alex": (True, 0), "kid": (False, 0)}
    # the admin keeps their own; the page says a starting point exists
    got = client.get("/api/apps").json()
    assert got["layout"]["hidden"] == ["iohealth"] and got["layoutOf"]["scope"] == "account" and got["layoutOf"]["family"] is True
    # giving one person a setup replaces what they and their devices had
    assert client.put("/api/layout/people/987654", json={}).status_code == 404
    assert client.put(f"/api/layout/people/{kid}", json={"accent": "nope"}).status_code == 400
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    got = client.get("/api/apps").json()
    assert (got["layout"]["style"], got["layout"]["hidden"], got["layoutOf"]["scope"]) == ("today", ["iomoney"], "family")
    assert client.put("/api/layout/family", json={}).status_code == 403 and client.get("/api/layout/family").status_code == 403
    assert client.put(f"/api/layout/people/{kid}", json={}).status_code == 403
    client.put(f"/api/me/layout?device={DEV}&name=Tablet", json={"style": "cards"})
    assert client.put("/api/me/layout", json={"hidden": ["ionote"]}).json()["style"] is None  # their own now, not the family's
    assert client.put("/api/me/layout", json={}).json()["style"] == "today"  # back to the default: the family's
    client.put("/api/me/layout", json={"hidden": ["ionote"]})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert client.put(f"/api/layout/people/{kid}", json={"bookmarks": "folded", "text": "large"}).json() == {"ok": True}
    assert {p["name"]: (p["own"], p["devices"]) for p in client.get("/api/layout/family").json()["people"]} == {"alex": (True, 0), "kid": (True, 0)}
    assert client.put("/api/layout/family", json={}).json() == {"layout": None}  # taken away again
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    got = client.get(f"/api/apps?device={DEV}").json()
    assert got["layout"] == {**layout.EMPTY, "bookmarks": "folded", "text": "large"} and got["layoutOf"] == {"scope": "account", "device": None, "devices": [], "family": False}


def test_what_is_kept_is_read_leniently(client):
    """A value that is no longer known (an older version's, a typo in the table) is left out, the rest stands."""
    from iostart import db
    me = client.get("/api/status").json()["user"]["id"]
    db.set_state(f"user:{me}:layout", '{"hidden": ["ionote", 7, "Not an app!"], "style": "mosaic", "sizes": {"iopix": "tile", "x y": "card", "iotask": "huge"}, "accent": "teal", "todayDays": 12}')
    assert client.get("/api/me/layout").json() == {**layout.EMPTY, "hidden": ["ionote"], "sizes": {"iopix": "tile"}, "accent": "teal"}
    db.set_state(f"user:{me}:layout", "not json")
    assert client.get("/api/me/layout").json() == layout.EMPTY


def test_contacts_search_for_the_search_box(client, monkeypatch):
    asked = []
    table = {("iocontact", "/api/contacts"): {"total": 1, "items": [{"id": 3, "fn": "Ada Lovelace", "hasPhoto": True, "org": "Analytical Engines"}]}}
    monkeypatch.setattr(widgets, "fetch", via_providers(table, asked, cookie=False))
    d = client.get("/api/widgets/iocontact?q=ada").json()
    assert d == {"items": [{"kind": "contact", "id": "3", "title": "Ada Lovelace", "text": "Analytical Engines", "when": None, "allDay": False,
                            "done": False, "image": "", "href": "#/c/3", "round": True, "icon": "person"}], "more": False}
    assert asked == [("iocontact", "/api/contacts", {"q": "ada", "limit": 5})]


def test_ping_trusts_a_self_signed_certificate(monkeypatch):
    """A router on a home address with its own certificate answered: it is up, not "Not reachable"."""
    import ssl
    import urllib.error

    class Opener:
        def __init__(self, err):
            self.err = err

        def open(self, req, timeout=None):
            raise self.err
    monkeypatch.setattr(status, "_opener", Opener(urllib.error.URLError(ssl.SSLCertVerificationError(1, "self-signed certificate"))))
    assert status._ping("https://192.168.1.1") == {"ok": True, "status": None}
    monkeypatch.setattr(status, "_opener", Opener(ssl.SSLCertVerificationError(1, "self-signed certificate")))
    assert status._ping("https://192.168.1.1") == {"ok": True, "status": None}
    monkeypatch.setattr(status, "_opener", Opener(urllib.error.URLError(ConnectionRefusedError(111, "refused"))))
    assert status._ping("https://192.168.1.1") == {"ok": False, "status": None}


def test_events_tasks_recipes_and_notes_for_the_search_box(client, monkeypatch):
    """The search box asks ioCalendar, ioTask and ioRecipe with the viewer's sign-in: the coming events only, the open
    tasks only, a recipe with its small picture."""
    asked = []

    def answer(key, path, params, raw):
        if path == "/api/calendars":
            return {"items": [{"id": 1, "color": "#c00"}]}
        if path == "/api/events":
            return {"items": [{"id": 7, "calendarId": 1, "title": "Dentist 2020", "allDay": False, "recurring": False, "location": None,
                               "next": {"start": "2020-03-01T09:00:00+00:00", "end": "2020-03-01T10:00:00+00:00"}},
                              {"id": 9, "calendarId": 1, "title": "Dentist far", "allDay": True, "recurring": False, "location": "Town",
                               "next": {"start": "2999-05-02", "end": "2999-05-03"}},
                              {"id": 8, "calendarId": 1, "title": "Dentist soon", "allDay": False, "recurring": True, "location": None,
                               "next": {"start": "2999-01-01T09:00:00+00:00", "end": "2999-01-01T10:00:00+00:00", "recurrenceId": "29990101T090000Z"}},
                              {"id": 6, "calendarId": 2, "title": "Dentist 2021", "allDay": True, "recurring": False, "location": None,
                               "next": {"start": "2021-03-01", "end": "2021-03-02"}}]}
        if path == "/api/lists":
            return {"items": [{"id": 4, "color": "#146b5e"}]}
        if path == "/api/tasks":
            if params["status"] == "done":
                return {"items": [{"id": 2, "title": "Dentist 2019", "done": True, "listId": 4}]}
            return {"items": [{"id": 1, "title": "Call the dentist", "due": "2026-11-20", "dueAllDay": True, "done": False, "listId": 4}]}
        if path == "/api/recipes":
            return {"items": [{"id": 3, "title": "Tarte Tatin", "photo": "/api/recipes/3/photos/12", "totalMinutes": 75, "tags": ["dessert", "apple", "french", "oven"], "favourite": True},
                              {"id": 5, "title": "Tartiflette", "photo": None, "totalMinutes": None, "tags": [], "favourite": False}]}
        if path == "/api/notes":
            return {"total": 9, "notes": [{"id": "ab-1", "title": "", "body": "# Dentist\n\nDr. Molar, 02 555 01 23", "pinned": True, "updatedAt": 1.5},
                                          {"id": "ab-2", "title": "Insurance", "body": "- dentist: 80 %", "pinned": False, "updatedAt": 1.0},
                                          {"id": "ab-3", "title": "", "body": "", "ocrText": "", "hasImage": True, "pinned": False, "updatedAt": 0.5}]}
        if path == "/api/items":
            return {"items": [{"id": 2, "name": "Dentist chair", "photo": "api/items/2/files/9", "location": {"id": 1, "name": "Attic", "path": "House / Attic"}}]}
        if path == "/api/items/2/files/9":
            assert raw and params == {"size": "small"}
            return b"jpg", "image/jpeg"
        if path == "/api/recipes/3/photos/12":
            assert raw and params == {"size": "small"}
            return b"jpeg", "image/jpeg"
        raise AssertionError(path)
    paths = ["/api/calendars", "/api/events", "/api/lists", "/api/tasks", "/api/recipes", "/api/notes", "/api/items", "/api/items/2/files/9",
             "/api/recipes/3/photos/12"]
    table = {(k, p): (lambda p_, k=k, p=p: answer(k, p, p_, p.count("/") > 3)) for k in ("iocalendar", "iotask", "iorecipe", "ionote", "iothings") for p in paths}
    monkeypatch.setattr(widgets, "fetch", via_providers(table, asked, cookie=False))
    d = client.get("/api/widgets/iocalendar?q=dentist&tz=Europe/Brussels").json()
    # the coming ones soonest first, then the ones that are over (done: the box leaves them out), the latest first
    assert [(x["id"], x["done"]) for x in d["items"]] == [("8", False), ("9", False), ("6", True), ("7", True)] and d["more"] is False
    assert d["items"][0] == {"kind": "event", "id": "8", "title": "Dentist soon", "text": "", "when": "2999-01-01T09:00:00+00:00", "allDay": False,
                             "done": False, "image": None, "href": "#/event/8?rid=29990101T090000Z", "color": "#c00", "icon": "event", "recurring": True}
    assert ("iocalendar", "/api/events", {"q": "dentist", "limit": 200}) in asked
    d = client.get("/api/widgets/iotask?q=dentist").json()
    assert [(x["title"], x["when"], x["allDay"], x["done"], x.get("color")) for x in d["items"]] == [
        ("Call the dentist", "2026-11-20", True, False, "#146b5e"), ("Dentist 2019", None, False, True, "#146b5e")] and d["more"] is False
    d = client.get("/api/widgets/iorecipe?q=tart").json()
    assert [(x["title"], x["text"], x["image"], x.get("favourite")) for x in d["items"]] == [("Tarte Tatin", "75 min", "12", True), ("Tartiflette", "", None, None)]
    assert ("iorecipe", "/api/recipes", {"q": "tart", "limit": 6}) in asked
    r = client.get("/api/widgets/iorecipe/image/recipe/3?p=12")
    assert r.status_code == 200 and r.content == b"jpeg" and r.headers["content-type"] == "image/jpeg"
    assert client.get("/api/widgets/iorecipe").status_code == 404  # no tile of its own
    d = client.get("/api/widgets/ionote?q=dentist").json()
    assert [(x["id"], x["title"], x["text"], x.get("pinned"), x["image"]) for x in d["items"]] == [
        ("ab-1", "Dentist", "Dr. Molar, 02 555 01 23", True, None), ("ab-2", "Insurance", "dentist: 80 %", None, None), ("ab-3", "Picture", "", None, "")]
    assert d["more"] is True
    assert ("ionote", "/api/notes", {"q": "dentist", "limit": 5}) in asked
    assert client.get("/api/widgets/ionote").status_code == 404
    d = client.get("/api/widgets/iothings?q=dentist").json()
    assert [(x["title"], x["text"], x["image"], x["href"]) for x in d["items"]] == [("Dentist chair", "House / Attic", "9", "#/item/2")]
    assert client.get("/api/widgets/iothings/image/item/2?p=9").content == b"jpg"
    assert client.get("/api/widgets/iothings").status_code == 404

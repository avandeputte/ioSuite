"""A page the person lays out block by block (iostart/layout.py): the grid and its sections, a rule for when a thing
shows, the badges, more pages than one, a setup copied from elsewhere or pasted in as text."""
import json

from iosuite_shared import testing

from iostart import db, layout

DEV = "tablet0001"
GRID = {"cols": 4, "sections": [
    {"id": "sec1", "title": None, "blocks": [
        {"id": "b001", "kind": "today", "w": 2},
        {"id": "b002", "kind": "app", "app": "iomoney", "h": 2, "when": {"content": True}},
        {"id": "b003", "kind": "apps", "apps": ["iopix", "ionote"], "look": "list"}]},
    {"id": "sec2", "title": "  The   house ", "when": {"screen": ["wide", "tablet"]}, "blocks": [
        {"id": "b004", "kind": "home", "title": "Downstairs", "entities": ["light.kitchen", "binary_sensor.front_door"], "w": 3},
        {"id": "b005", "kind": "home", "title": "Garden", "entities": ["switch.pump"]},
        {"id": "b006", "kind": "bookmarks", "group": 12, "look": "icons"},
        {"id": "b007", "kind": "week", "who": 3},
        {"id": "b008", "kind": "news", "folder": "Tech"},
        {"id": "b009", "kind": "strip", "strip": "onthisday", "w": 4}]}]}


def put(client, body, q=""):
    return client.put(f"/api/me/layout{q}", json=body)


def test_a_grid_of_blocks(client):
    r = put(client, {"style": "grid", "grid": GRID})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["style"] == "grid" and got["grid"]["cols"] == 4
    one, two = got["grid"]["sections"]
    assert one == {"id": "sec1", "title": None, "blocks": [
        {"id": "b001", "kind": "today", "w": 2},
        {"id": "b002", "kind": "app", "h": 2, "when": {"content": True}, "app": "iomoney"},
        {"id": "b003", "kind": "apps", "apps": ["iopix", "ionote"], "look": "list"}]}
    assert two["title"] == "The house" and two["when"] == {"screen": ["tablet", "wide"]}
    assert two["blocks"][0] == {"id": "b004", "kind": "home", "w": 3, "title": "Downstairs", "entities": ["light.kitchen", "binary_sensor.front_door"]}
    assert two["blocks"][2] == {"id": "b006", "kind": "bookmarks", "look": "icons", "group": "12"}  # the same card twice is the point: two Home cards above
    assert two["blocks"][3] == {"id": "b007", "kind": "week", "who": 3} and two["blocks"][4]["folder"] == "Tech"
    assert client.get("/api/apps").json()["layout"]["grid"] == got["grid"]
    # a width of one is what a block has anyway; a height of one is a choice (no taller than a row), nothing is as tall as what it shows
    g = put(client, {"grid": {"sections": [{"id": "sec1", "blocks": [{"id": "b001", "kind": "birthdays", "w": 1, "h": 1}, {"id": "b002", "kind": "week", "h": None}]}]}}).json()["grid"]
    assert g == {"cols": None, "sections": [{"id": "sec1", "title": None, "blocks": [{"id": "b001", "kind": "birthdays", "h": 1}, {"id": "b002", "kind": "week"}]}]}
    assert put(client, {"grid": {}}).json()["grid"] is None


def test_what_a_grid_refuses(client):
    def sec(*blocks, **more):
        return {"grid": {"sections": [{"id": "sec1", "blocks": list(blocks), **more}]}}
    for bad in ({"grid": []}, {"grid": {"cols": 7, "sections": []}}, {"grid": {"sections": [{"blocks": []}]}}, {"grid": {"sections": ["x"]}},
                sec({"id": "b001", "kind": "clock"}), sec({"id": "b001", "kind": "app"}), sec({"id": "b001", "kind": "app", "app": "Not an app!"}),
                sec({"id": "B1", "kind": "today"}), sec({"id": "b001", "kind": "today"}, {"id": "b001", "kind": "week"}), sec({"id": "sec1", "kind": "today"}),
                sec({"id": "b001", "kind": "today", "w": 5}), sec({"id": "b001", "kind": "today", "h": 0.5}), sec({"id": "b001", "kind": "today", "app": "iopix"}),
                sec({"id": "b001", "kind": "home", "entities": ["kitchen light"]}), sec({"id": "b001", "kind": "week", "who": "ava"}),
                sec({"id": "b001", "kind": "apps", "look": "icons"}), sec({"id": "b001", "kind": "bookmarks", "group": "a b"}),
                sec({"id": "b001", "kind": "strip", "strip": "off"}), sec({"id": "b001", "kind": "today", "when": {"screen": ["watch"]}})):
        assert put(client, bad).status_code == 400, bad
    many = [{"id": f"b{i:03d}", "kind": "today"} for i in range(layout.BLOCKS_MOST + 1)]
    assert put(client, sec(*many)).status_code == 400
    assert put(client, {"grid": {"sections": [{"id": f"s{i:03d}", "blocks": []} for i in range(layout.SECTIONS_MOST + 1)]}}).status_code == 400
    assert put(client, {"colour": "green"}).status_code == 400  # a key a setup does not have: said, not dropped in silence


def test_when_a_thing_shows(client):
    w = {"screen": ["phone"], "from": "06:00", "to": "09:30", "days": [5, 1, 1, 2, 3, 4], "content": True, "ha": {"id": "binary_sensor.front_door", "state": " open ", "not": 1}}
    got = put(client, {"whens": {"iomoney": w, "strip": {"screen": ["wide", "phone", "tablet"]}, "weather": {"days": [0, 1, 2, 3, 4, 5, 6]}, "week": {"ha": {"id": "person.alex"}}}}).json()["whens"]
    assert got == {"iomoney": {"screen": ["phone"], "from": "06:00", "to": "09:30", "days": [1, 2, 3, 4, 5], "content": True,
                               "ha": {"id": "binary_sensor.front_door", "state": "open", "not": True}},
                   "week": {"ha": {"id": "person.alex", "state": "on"}}}  # every screen, every day: no rule at all
    for bad in ({"whens": []}, {"whens": {"Not an app!": {}}}, {"whens": {"iopix": "phone"}}, {"whens": {"iopix": {"screen": "phone"}}}, {"whens": {"iopix": {"from": "06:00"}}},
                {"whens": {"iopix": {"from": "6:00", "to": "09:00"}}}, {"whens": {"iopix": {"from": "06:00", "to": "06:00"}}}, {"whens": {"iopix": {"days": [7]}}},
                {"whens": {"iopix": {"days": [True]}}}, {"whens": {"iopix": {"ha": {"id": "the door"}}}}, {"whens": {"iopix": {"weather": "rain"}}}):
        assert put(client, bad).status_code == 400, bad
    assert put(client, {"whens": {"iopix": {"from": "22:00", "to": "06:00"}}}).json()["whens"] == {"iopix": {"from": "22:00", "to": "06:00"}}  # through the night


def test_badges(client):
    r = put(client, {"badges": [{"id": "bg01", "app": "iocalendar"}, {"id": "bg02", "entity": "sensor.outside_temperature", "when": {"screen": ["phone"]}}, {"id": "bg03", "app": "iotask", "when": {"content": True}}]})
    assert r.status_code == 200 and r.json()["badges"] == [{"id": "bg01", "app": "iocalendar"}, {"id": "bg02", "entity": "sensor.outside_temperature", "when": {"screen": ["phone"]}},
                                                          {"id": "bg03", "app": "iotask", "when": {"content": True}}]
    for bad in ({"badges": {}}, {"badges": [{"id": "bg01"}]}, {"badges": [{"id": "bg01", "app": "iopix", "entity": "light.x"}]}, {"badges": [{"app": "iopix"}]},
                {"badges": [{"id": "bg01", "app": "iopix"}, {"id": "bg01", "app": "iotask"}]}, {"badges": [{"id": "bg01", "entity": "the door"}]},
                {"badges": [{"id": f"bg{i:02d}", "app": "iopix"} for i in range(layout.BADGES_MOST + 1)]}):
        assert put(client, bad).status_code == 400, bad


def test_more_pages_than_one(client):
    kitchen = {"id": "kitchen", "name": " Kitchen  tablet ", "style": "grid", "grid": GRID, "hidden": ["search"], "when": {"screen": ["tablet", "wide"]}}
    money = {"id": "money", "name": "Money", "style": "today", "todayOff": ["health"], "badges": [{"id": "bg01", "app": "iomoney"}], "order": ["iomoney", "iodocs"]}
    r = put(client, {"name": "Home", "style": "cards", "accent": "teal", "pages": [kitchen, money]})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["name"] == "Home" and got["accent"] == "teal" and [p["id"] for p in got["pages"]] == ["kitchen", "money"]
    k, m = got["pages"]
    assert k["name"] == "Kitchen tablet" and k["when"] == {"screen": ["tablet", "wide"]} and k["hidden"] == ["search"] and k["grid"]["cols"] == 4
    assert set(k) == {"id", "name", "when", *layout.PAGE}  # what a page holds by itself, and nothing of the person's (the colour, the units)
    assert m["style"] == "today" and m["todayOff"] == ["health"] and m["order"] == ["iomoney", "iodocs"] and m["badges"] == [{"id": "bg01", "app": "iomoney"}] and "when" not in m
    for bad in ({"pages": {}}, {"pages": ["x"]}, {"pages": [{"name": "No id"}]}, {"pages": [{"id": "pg01"}, {"id": "pg01"}]}, {"pages": [{"id": "pg01", "accent": "teal"}]},
                {"pages": [{"id": "pg01", "style": "mosaic"}]}, {"pages": [{"id": f"pg{i:02d}"} for i in range(layout.PAGES_MOST)]}, {"name": 7}):
        assert put(client, bad).status_code == 400, bad
    assert put(client, {"pages": [{"id": "pg01"}]}).json()["pages"][0]["name"] == "Page"
    # a device has pages of its own as it has everything else
    put(client, {"pages": [money]}, f"?device={DEV}&name=Tablet")
    assert [p["id"] for p in client.get(f"/api/apps?device={DEV}").json()["layout"]["pages"]] == ["money"]
    assert [p["id"] for p in client.get("/api/apps").json()["layout"]["pages"]] == ["pg01"]


def test_what_was_kept_is_read_leniently(client):
    """A block of a kind no longer known, a rule with a part no longer known: left out, the rest stands."""
    me = client.get("/api/status").json()["user"]["id"]
    kept = {"style": "grid", "grid": {"cols": 9, "sections": [{"id": "sec1", "title": 3, "blocks": [
        {"id": "b001", "kind": "clock"}, {"id": "b002", "kind": "app", "app": "iotask", "w": 9, "when": {"moon": "full", "screen": ["phone", "watch"], "content": 1}},
        {"id": "b002", "kind": "today"}, {"id": "b003", "kind": "home", "entities": ["light.a", "nope", 4], "title": "A"}, "x"]}, "x", {"id": "sec1", "blocks": []}]},
        "badges": [{"id": "bg01", "app": "iopix"}, {"id": "bg01", "app": "iotask"}, 5], "whens": {"iopix": {"screen": "phone"}, "strip": {"content": True}, "?": {}},
        "pages": [{"id": "pg01", "name": "A", "style": "mosaic", "colour": 1}, "x", {"id": "pg01"}], "name": ["x"]}
    db.set_state(f"user:{me}:layout", json.dumps(kept))
    got = client.get("/api/me/layout").json()
    assert got["grid"] == {"cols": None, "sections": [{"id": "sec1", "title": None, "blocks": [
        {"id": "b002", "kind": "app", "when": {"content": True}, "app": "iotask"}, {"id": "b003", "kind": "home", "title": "A", "entities": ["light.a"]}]}]}
    assert got["badges"] == [{"id": "bg01", "app": "iopix"}] and got["whens"] == {"strip": {"content": True}} and got["name"] is None
    assert [(p["id"], p["name"], p["style"]) for p in got["pages"]] == [("pg01", "A", None)]


def test_a_setup_copied_from_elsewhere(client):
    kid = testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"}).json()["id"]
    assert client.get("/api/me/layout/sources").json() == {"account": False, "devices": [], "family": False, "people": []}
    for nothing in ("account", "family", f"device:{DEV}", f"person:{kid}", "person:x", "elsewhere", ""):
        assert client.get("/api/me/layout/copy", params={"source": nothing}).status_code == 404, nothing
    put(client, {"style": "today", "accent": "amber"})
    put(client, {"style": "grid", "grid": GRID}, f"?device={DEV}&name=Tablet")
    client.put("/api/layout/family", json={"bookmarks": "folded"})
    me = client.get("/api/status").json()["user"]["id"]
    assert client.get("/api/me/layout/sources").json() == {"account": True, "devices": [{"id": DEV, "name": "Tablet"}], "family": True, "people": []}
    assert client.get("/api/me/layout/copy", params={"source": "account"}).json()["layout"]["accent"] == "amber"
    assert client.get("/api/me/layout/copy", params={"source": f"device:{DEV}"}).json()["layout"]["grid"]["cols"] == 4
    assert client.get("/api/me/layout/copy", params={"source": "family"}).json()["layout"]["bookmarks"] == "folded"
    assert client.get("/api/me/layout/copy", params={"source": f"person:{me}"}).status_code == 404  # your own is "account"
    # someone else: their account's setup, when it has one; never a device's of theirs
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/me/layout/sources").json() == {"account": False, "devices": [], "family": True, "people": [{"id": me, "name": "alex"}]}
    assert client.get("/api/me/layout/copy", params={"source": f"person:{me}"}).json()["layout"]["style"] == "today"
    assert client.get("/api/me/layout/copy", params={"source": f"device:{DEV}"}).status_code == 404
    assert client.get("/api/me/layout").json()["style"] is None  # looking copies nothing


def test_a_setup_as_text(client):
    r = client.post("/api/layout/check", json={"style": "grid", "grid": GRID, "hidden": ["ionote", "ionote"]})
    assert r.status_code == 200 and r.json()["layout"]["hidden"] == ["ionote"] and set(r.json()["layout"]) == set(layout.EMPTY)
    assert client.get("/api/me/layout").json() == layout.EMPTY  # checked, not saved
    r = client.post("/api/layout/check", json={"grid": {"sections": [{"id": "sec1", "blocks": [{"id": "b001", "kind": "clock"}]}]}})
    assert r.status_code == 400 and "kind" in r.json()["detail"]
    assert client.post("/api/layout/check", json=[]).status_code == 400
    assert client.put("/api/me/layout", json=client.post("/api/layout/check", json={"style": "grid", "grid": GRID}).json()["layout"]).json()["grid"]["cols"] == 4


def test_headlines_of_one_folder(client, monkeypatch):
    from iostart import news
    feed = (b'<rss version="2.0"><channel><title>T</title><link>https://t.example/</link>'
            b'<item><title>One</title><link>https://t.example/1</link><guid>1</guid></item><item><title>Two</title><link>https://t.example/2</link><guid>2</guid></item></channel></rss>')
    monkeypatch.setattr(news, "fetch_url", lambda url, etag=None, modified=None: (200, feed, url, {"etag": None, "modified": None}))
    f = client.post("/api/news/feeds", json={"url": "https://t.example/feed.xml", "folder": "Tech"}).json()["feed"]
    client.patch(f"/api/news/feeds/{f['id']}", json={"onStart": False})
    assert client.get("/api/news/card").json() == {"items": [], "unread": 0, "feeds": 1}
    c = client.get("/api/news/card", params={"folder": "Tech", "n": 1}).json()
    assert len(c["items"]) == 1 and c["unread"] == 2 and c["feeds"] == 1  # the folder's, on the usual card or not
    assert client.get("/api/news/card", params={"folder": "Sport"}).json() == {"items": [], "unread": 0, "feeds": 0}

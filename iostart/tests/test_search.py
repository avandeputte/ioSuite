"""One search across the apps (app/search.py, GET /api/search): every app asked at once as the viewer, the answers
ranked together, a slow app named as late, a hidden or forbidden app left out."""
import threading

from iosuite_shared import suite

from iostart import apps, search, widgets


def _register(*keys):
    for key in keys:
        suite.register(key, "io" + key[2:].capitalize(), url=f"https://{key[2:]}.example.com", version="1.0",
                       description=key[2:].capitalize(), color="#123456")
    apps.forget_registry()


def _answers(monkeypatch, table: dict, asked: list):
    def fake(request, key, path, params=None, raw=False, body=None, timeout=None):
        assert path == "/api/suite/search" and body is None
        asked.append((key, params["q"], request.cookies.get("iothing_session") is not None))
        got = table.get(key)
        if isinstance(got, Exception):
            raise got
        return got(params) if callable(got) else got
    monkeypatch.setattr(widgets, "fetch", fake)


def item(kind, i, title, text="", when=None, done=False):
    return {"kind": kind, "id": str(i), "title": title, "text": text, "when": when, "done": done, "href": f"#/{kind}/{i}"}


def test_ranked_together_across_apps(client, monkeypatch):
    _register("iocontact", "ionote", "iotask", "iorecipe")
    asked = []
    _answers(monkeypatch, {
        "ionote": {"items": [item("note", 1, "Insurance", "Ann's number"), item("note", 2, "Ann birthday ideas")], "more": True},
        "iocontact": {"items": [item("contact", 3, "Ann"), item("contact", 4, "Annabel Lee")], "more": False},
        "iotask": {"items": [item("task", 5, "Call Ann", done=True), item("task", 6, "Call Ann back")], "more": False},
        "iorecipe": {"items": [], "more": False},
    }, asked)
    d = client.get("/api/search?q=ann").json()
    assert [(x["app"], x["title"]) for x in d["items"]] == [
        ("iocontact", "Ann"), ("iocontact", "Annabel Lee"), ("ionote", "Ann birthday ideas"),
        ("iotask", "Call Ann back"), ("ionote", "Insurance")]  # the finished task is left out
    assert d["apps"] == {"iocontact": {"more": False}, "ionote": {"more": True}, "iotask": {"more": False}, "iorecipe": {"more": False}}
    assert d["late"] == []
    assert sorted(k for k, *_ in asked) == ["iocontact", "ionote", "iorecipe", "iotask"]
    assert all(signed for *_, signed in asked)  # asked as the viewer, with their own session


def test_only_the_apps_asked_for_and_never_one_the_viewer_may_not_use(client, monkeypatch):
    _register("iocontact", "ionote")
    asked = []
    _answers(monkeypatch, {"iocontact": {"items": [item("contact", 3, "Ann")]}, "ionote": {"items": [item("note", 1, "Ann")]}}, asked)
    d = client.get("/api/search?q=ann&apps=ionote,iobackup,nothere").json()
    assert [x["app"] for x in d["items"]] == ["ionote"] and [k for k, *_ in asked] == ["ionote"]
    monkeypatch.setattr(apps, "may_see", lambda user, entry: entry["app"] != "ionote")
    asked.clear()
    d = client.get("/api/search?q=ann").json()
    assert [x["app"] for x in d["items"]] == ["iocontact"] and [k for k, *_ in asked] == ["iocontact"]


def test_an_app_that_refuses_or_is_down_leaves_the_others(client, monkeypatch):
    _register("iocontact", "ionote", "iotask")
    _answers(monkeypatch, {"iocontact": widgets.Unavailable(403, "ioContact does not let this account in"),
                           "ionote": widgets.Unavailable(502, "ioNote is not reachable"),
                           "iotask": {"items": [item("task", 6, "Call Ann")]}}, [])
    d = client.get("/api/search?q=ann").json()
    assert [x["title"] for x in d["items"]] == ["Call Ann"]
    assert d["apps"]["iocontact"]["status"] == 403 and d["apps"]["ionote"]["status"] == 502


def test_a_slow_app_is_late_and_asked_again_on_its_own(client, monkeypatch):
    _register("iocontact", "ionote")
    gate = threading.Event()

    def slow(params):
        gate.wait(5)
        return {"items": [item("note", 1, "Ann")]}
    _answers(monkeypatch, {"iocontact": {"items": [item("contact", 3, "Ann")]}, "ionote": slow}, [])
    monkeypatch.setattr(search, "DEADLINE", 0.2)
    d = client.get("/api/search?q=ann").json()
    assert [x["app"] for x in d["items"]] == ["iocontact"] and d["late"] == ["ionote"]
    gate.set()
    d = client.get("/api/search?q=ann&apps=ionote&wait=1").json()
    assert [x["app"] for x in d["items"]] == ["ionote"] and d["late"] == []


def test_nothing_asked_for_nothing_typed(client, monkeypatch):
    asked = []
    _answers(monkeypatch, {}, asked)
    assert client.get("/api/search?q=%20").json() == {"items": [], "apps": {}, "late": []}
    assert asked == []


def test_score():
    import datetime as dt
    today = dt.date(2026, 11, 23)
    s = lambda title, text="", pos=0, key="iocontact", when=None: search.score("ann", {"title": title, "text": text, "when": when}, key, pos, today)  # noqa: E731
    assert s("Ann") > s("Annabel") > s("Mary Ann") > s("Joanne") > s("Note", "about ann") > s("Note")
    assert s("Ånn") == s("Ann")  # accents folded
    assert s("Ann", pos=1) < s("Ann")  # the app's own order counts
    assert s("Call Ann", key="iotask", when="2026-11-24") > s("Call Ann", key="iotask", when="2027-01-01")
    sm = lambda title: search.score("ann sm", {"title": title}, "iocontact", 0, today)  # noqa: E731
    assert sm("Ann Smith") == sm("Smithers, Ann") > sm("Annsmall")  # every word starts a word of the title

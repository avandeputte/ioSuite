"""The record of who added and changed an item (iosuite_shared.stamp): what a request says about itself, the words the
record is shown in, the history's length, a move, and what is shown of the address to whom."""
import json
from types import SimpleNamespace

from iosuite_shared import db, doors, stamp, users

SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"


def request(path="/api/x", door=doors.WEB, ua=SAFARI, ip="192.168.1.20", cloudflare=False, headers=None, inside=False):
    scope = {doors.SCOPE_DOOR: door}
    if inside:
        scope["iosuite.inside"] = True
    from iosuite_shared.sessions import classify
    return SimpleNamespace(url=SimpleNamespace(path=path), scope=scope, headers={k.lower(): v for k, v in (headers or {}).items()},
                           state=SimpleNamespace(origin={"ip": ip, "cloudflare": cloudflare, "client": classify(ua), "user_agent": ua}))


ALEX = {"id": 1, "name": "alex", "displayName": "Alex"}


def test_what_a_request_says():
    s = stamp.of_request(request(), ALEX, False)
    assert (s.client, s.where, s.name, s.ip) == ("web", "Safari on iPhone", "Alex", "192.168.1.20")
    pw = dict(ALEX, app_password={"id": 3, "label": "iPhone calendar"})
    s = stamp.of_request(request("/dav/calendars/alex/family/x.ics", doors.SYNC, ua="iOS/18.0 (22A3354) dataaccessd/1.0"), pw, True)
    assert (s.client, s.where, s.outside) == ("dav", "iPhone calendar", True)
    s = stamp.of_request(request("/mcp", doors.MCP, ua="claude-code/2.0"), dict(ALEX, app_password={"id": 4, "label": "Claude"}), True)
    assert (s.client, s.where) == ("mcp", "Claude")
    s = stamp.of_request(request("/api/bookmarks", doors.SYNC, ua="iostart/12 CFNetwork/1568 Darwin/24.0.0"), ALEX, True)
    assert (s.client, s.where) == ("app", "ioStart app")
    s = stamp.of_request(request("/api/events", doors.SYNC, ua="curl/8.5"), dict(ALEX, app_password={"id": 5, "label": "backup script"}), False)
    assert (s.client, s.where) == ("api", "backup script")


def test_on_behalf_is_believed_from_inside_only():
    said = json.dumps({"app": "iostart", "client": "web", "where": "Safari on Mac", "ip": "203.0.113.4", "outside": True})
    h = {stamp.HEADER: said}
    s = stamp.of_request(request(headers=h, inside=True), ALEX, False)
    assert (s.via, s.client, s.where, s.ip, s.outside) == ("iostart", "web", "Safari on Mac", "203.0.113.4", True)
    s = stamp.of_request(request(headers=h, ip="198.51.100.7"), ALEX, True)  # from outside: a visitor's word, not believed
    assert s.via == "" and s.ip == "198.51.100.7"
    s = stamp.of_request(request(headers={stamp.HEADER: json.dumps({"app": "nosuchapp"})}), ALEX, False)
    assert s.via == ""


def test_in_words():
    assert stamp.how("web", "Safari on Mac") == "the web page (Safari on Mac)"
    assert stamp.how("dav", "iPhone", app="iocontact") == "CardDAV (iPhone)"
    assert stamp.how("mcp", "Claude", "iostart") == "MCP (Claude) through the start page"
    assert stamp.how("sync", "Monarch Money") == "Monarch Money"
    assert stamp.how("import", "a bank file") == "an import (a bank file)"
    assert stamp.how("api", "backup script") == "the app password “backup script”"


def test_record_history_move_and_who_sees_the_address():
    users.init()
    a = users.create("alex", "secret123", "admin", "iocalendar")
    b = users.create("sam", "secret123", "member", "iocalendar")
    with stamp.job("", "web", users.get(a["id"])):
        stamp.CURRENT.set(stamp.Stamp(a["id"], "alex", "web", "Safari on Mac", "192.168.1.20"))
        stamp.touch("iocalendar", "event", 7, "added")
        for n in range(stamp.KEEP + 5):
            stamp.touch("iocalendar", "event", 7, "changed", "time")
    assert db.one("SELECT COUNT(*) AS n FROM ios_item_changes WHERE item = '7'")["n"] == stamp.KEEP  # the last KEEP only
    rec = stamp.record("iocalendar", "event", 7, users.get(a["id"]))
    assert rec["added"]["by"] == "alex" and rec["changed"]["how"] == "the web page (Safari on Mac)"
    assert rec["history"][0]["from"] == "192.168.1.20"  # their own change: the address
    assert stamp.record("iocalendar", "event", 7, users.get(b["id"]))["history"][0]["from"] == "at home"  # someone else's
    stamp.move("iocalendar", "event", 7, 8)
    assert stamp.record("iocalendar", "event", 8)["added"]["by"] == "alex"
    assert stamp.line("iocalendar", "event", 8)["addedWith"] == "the web page (Safari on Mac)"
    with stamp.job("Monarch Money", "sync"):
        stamp.touch("iomoney", "transaction", 5, "added")
    assert stamp.line("iomoney", "transaction", 5)["addedWith"] == "Monarch Money"
    stamp.touch("iocalendar", "event", 8, "deleted")
    assert stamp.line("iocalendar", "event", 8) is None
    stamp.forget("iocalendar", "event", [8])
    assert not db.q("SELECT id FROM ios_item_changes WHERE item = '8'")


def test_a_record_that_cannot_be_written_never_fails_the_change(monkeypatch):
    monkeypatch.setattr(db, "tx", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    stamp.touch("iocalendar", "event", 1, "added")  # no exception

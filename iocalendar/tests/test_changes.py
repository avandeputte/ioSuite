"""Who added an event and who changed it, with what and from where (iosuite_shared.stamp): the pages, CalDAV, MCP,
another app on the person's behalf; and only to people who may see the event."""
import json

from iosuite_shared import mcp as shared_mcp
from iosuite_shared import stamp, testing

from test_api import mk
from test_caldav import ICS
from test_mcp import call

SAFARI = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"


def changes(client, eid, **kw):
    return client.get(f"/api/changes/event/{eid}", **kw)


def test_web_then_caldav_then_mcp(client, family_id):
    e = mk(client, family_id, title="Dentist", start="2026-11-10T10:00")
    client.headers["User-Agent"] = SAFARI
    try:
        assert client.patch(f"/api/events/{e['id']}", json={"title": "Dentist (Sam)", "location": "Main St"}).status_code == 200
    finally:
        client.headers.pop("User-Agent")
    rec = changes(client, e["id"]).json()
    assert rec["added"]["by"] == "alex"
    assert rec["changed"]["client"] == "web" and rec["changed"]["how"] == "the web page (Safari on Mac)"
    assert rec["history"][0]["action"] == "changed" and rec["history"][0]["what"] == "title, place"
    assert rec["history"][-1]["action"] == "added"

    # a phone's calendar, with its own app password
    pw = client.post("/api/auth/app-passwords", json={"label": "iPhone calendar"}).json()["password"]
    href = client.get(f"/api/events/{e['id']}").json().get("href") or ""
    uid = client.get(f"/api/events/{e['id']}/ics").text.split("UID:")[1].split("\r\n")[0] if not href else None
    ics = ICS.format(uid=uid or "x", start="20261110T150000", end="20261110T160000", title="Dentist (Sam)", extra="")
    client.cookies.clear()  # a phone has nothing but its app password
    r = client.request("PUT", f"/dav/calendars/alex/family/{href or 'phone.ics'}", content=ics, auth=("alex", pw))
    assert r.status_code in (201, 204), r.text
    assert client.post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200
    phone = next(x for x in client.get("/api/events", params={"q": "Dentist"}).json()["items"])
    rec = changes(client, phone["id"]).json()
    assert rec["changed"]["client"] == "dav" and rec["changed"]["how"] == "CalDAV (iPhone calendar)"
    assert "time" in rec["history"][0]["what"]

    # Claude, through MCP
    shared_mcp.set_for("iocalendar", True)
    secret = client.post("/api/auth/app-passwords", json={"label": "Claude"}).json()["password"]
    client.cookies.clear()
    made = call(client, {"Authorization": f"Bearer {secret}"}, "create_event", title="Swim", start="2026-11-12T16:00", calendar="Family")
    assert client.post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200
    rec = changes(client, made["id"]).json()
    assert rec["added"]["client"] == "mcp" and rec["added"]["how"] == "MCP (Claude)"


def test_on_behalf_of_the_person_from_inside_only(client, family_id):
    behalf = json.dumps({"app": "iostart", "client": "web", "where": "Safari on iPhone", "ip": "203.0.113.9", "outside": True})
    r = client.post(f"/api/events?calendar={family_id}", json={"title": "Quick add", "start": "2026-11-11T09:00"},
                    headers={stamp.HEADER: behalf})
    assert r.status_code == 201, r.text
    rec = changes(client, r.json()["id"]).json()
    assert rec["added"]["how"] == "the web page (Safari on iPhone) through the start page"
    assert rec["history"][0]["from"] == "203.0.113.9"  # the one who made the change sees the address


def test_only_people_who_see_the_event_see_its_record(client, family_id):
    assert testing.add_account(client, {"name": "kid", "password": "kidpass99", "role": "member"}).status_code == 200
    fam = mk(client, family_id, title="Family thing", start="2026-11-10T10:00")
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "kid", "password": "kidpass99"}).status_code == 200
    mine = next(c for c in client.get("/api/calendars").json()["items"] if not c["shared"])
    own = mk(client, mine["id"], title="Secret", start="2026-11-10T11:00")
    assert changes(client, own["id"]).json()["added"]["by"] == "kid"
    seen = changes(client, fam["id"]).json()
    assert seen["added"]["by"] == "alex" and seen["history"][0]["from"] in ("", "at home", "away from home")  # not alex's address
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200
    assert changes(client, own["id"]).status_code == 404  # an admin does not see kid's private event, nor its record
    assert changes(client, 999999).status_code == 404


def test_deleted_and_moved(client, family_id):
    cals = client.get("/api/calendars").json()["items"]
    personal = next(c for c in cals if not c["shared"] and c["kind"] == "events")
    e = mk(client, family_id, title="Move me", start="2026-11-10T10:00")
    r = client.patch(f"/api/events/{e['id']}", json={"calendarId": personal["id"]})
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    rec = changes(client, new_id).json()
    assert rec["added"]["by"] == "alex"  # the record followed the event to its new id
    assert any(h["what"] == "calendar" for h in rec["history"])
    assert client.delete(f"/api/events/{new_id}").status_code == 200
    assert changes(client, new_id).status_code == 404

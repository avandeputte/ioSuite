"""The provider of a bill (a recurring transaction): the account number with the power company, the water board, the
internet provider, with their phone, website and a note. Seen wherever the bill is (the Recurring page, the bills
ioCalendar shows, the MCP list, the estate PDF), and by nobody who does not see the account it is paid from."""
import datetime as dt

from iosuite_shared import users

from conftest import sign_in
from test_api import add


def test_kept_changed_and_removed(client):
    today = dt.date.today().isoformat()
    r = client.post("/api/recurring", json={"name": "City Power", "amount": 80, "day": today, "approximate": True,
                                            "provider": {"accountNumber": " 1234-5678 ", "phone": "1-800-555-0100",
                                                         "website": "citypower.example", "note": "Meter 99"}})
    assert r.status_code == 201, r.text
    x = r.json()
    assert x["provider"] == {"accountNumber": "1234-5678", "phone": "1-800-555-0100",
                             "website": "https://citypower.example", "note": "Meter 99"}
    # the fields given change, the others stay; empty removes one
    x = client.patch(f"/api/recurring/{x['id']}", json={"provider": {"phone": "", "note": "Meter 100"}}).json()
    assert x["provider"] == {"accountNumber": "1234-5678", "website": "https://citypower.example", "note": "Meter 100"}
    x = client.patch(f"/api/recurring/{x['id']}", json={"amount": 85}).json()  # other changes leave it alone
    assert x["provider"]["accountNumber"] == "1234-5678"
    assert client.patch(f"/api/recurring/{x['id']}", json={"provider": "x"}).status_code == 400
    assert client.patch(f"/api/recurring/{x['id']}", json={"provider": {"accountNumber": "9" * 129}}).status_code == 400
    bills = client.get("/api/bills", params={"start": today, "end": today}).json()["items"]
    assert bills[0]["provider"]["accountNumber"] == "1234-5678"
    x = client.patch(f"/api/recurring/{x['id']}", json={"provider": {"accountNumber": "", "website": "", "note": None}}).json()
    assert x["provider"] is None
    plain = client.post("/api/recurring", json={"name": "Gym", "amount": 30, "day": today}).json()
    assert plain["provider"] is None


def test_never_seen_by_those_who_do_not_see_its_account(client, as_user):
    today = dt.date.today().isoformat()
    as_user("jo", "admin")
    jo = users.find("jo")["id"]
    sign_in(client, "alex")
    mine = add(client, name="Alex alone", household=False)
    joint = add(client, name="Joint")
    for name, acct, number in (("Alex's phone", mine["id"], "PRIVATE-1"), ("Water board", joint["id"], "W-77"),
                               ("Internet", None, "NET-5")):
        assert client.post("/api/recurring", json={"name": name, "accountId": acct, "amount": 50, "day": today,
                                                   "provider": {"accountNumber": number}}).status_code == 201
    sign_in(client, "jo")  # an admin here, not shown Alex's private account
    seen = {x["name"]: x["provider"]["accountNumber"] for x in client.get("/api/recurring").json()["items"]}
    assert seen == {"Water board": "W-77", "Internet": "NET-5"}
    bills = client.get("/api/bills", params={"start": today, "end": today}).json()["items"]
    assert "PRIVATE-1" not in str(bills) and "W-77" in str(bills)
    # the estate PDF: Alex's own lists all three; Jo's, or one Jo makes for Alex, never the private one
    sign_in(client, "alex")
    alex = users.find("alex")["id"]
    secs = {s["title"]: s for s in client.get(f"/api/auth/estate/{alex}").json()["sections"]}
    rows = secs["Bills and providers"]["table"]["rows"]
    assert sorted(r[1] for r in rows) == ["NET-5", "PRIVATE-1", "W-77"]
    assert ["Alex's phone", "PRIVATE-1", "", "", "Alex alone", ""] in rows
    sign_in(client, "jo")
    for whom in (jo, alex):
        r = client.get(f"/api/auth/estate/{whom}")
        if r.status_code != 200:  # not every role may make someone else's
            continue
        assert "PRIVATE-1" not in str(r.json())

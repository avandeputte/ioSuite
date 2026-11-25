"""Medicines, allergies and the emergency card: each person's own; doses ticked taken or skipped; the reminder at each
dose's time, once, with a Taken button; the card from this app, ioContact and ioDocs (asked as the viewer)."""
import datetime as dt
import json

import pytest
from iosuite_shared import links, push, testing

from iohealth import db, emergency, meds, webapi

TZ = "Europe/Brussels"


@pytest.fixture
def sent(monkeypatch):
    out = []

    def post(endpoint, body, headers):
        out.append(endpoint)
        return 201
    monkeypatch.setattr(push, "_post", post)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    return out


@pytest.fixture
def messages(monkeypatch):
    """What notify() would send, as the messages themselves."""
    out = []
    monkeypatch.setattr(push, "_send", lambda rows, message, ttl, urgency: out.append(message) or 1)
    return out


def _device(uid):
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    push.add_device(uid, {"endpoint": "https://fcm.googleapis.com/fcm/send/m",
                          "keys": {"p256dh": push.b64u(push._raw_public(k.public_key())), "auth": push.b64u(b"0123456789abcdef")}}, "iohealth")


def _today():
    return dt.datetime.now(webapi.zone_of(0)).date()


def test_medicines_are_kept_checked_and_changed(client, admin):
    r = client.post("/api/medicines", json={"name": "Lisinopril", "dose": "10 mg", "reason": "Blood pressure", "times": ["20:00", "8:00", "08:00"]})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["times"] == ["08:00", "20:00"] and m["days"] == list(range(7)) and m["remind"] and m["onCard"] and not m["asNeeded"]
    for bad in ({"dose": "1"}, {"name": "x", "times": ["25:00"]}, {"name": "x", "days": [7]}, {"name": "x" * 129},
                {"name": "x", "startOn": "2026-05-02", "endOn": "2026-05-01"}, {"name": "x", "startOn": "soon"}):
        assert client.post("/api/medicines", json=bad).status_code == 400, bad
    assert client.post("/api/medicines", json=["x"]).status_code == 400
    r = client.patch(f"/api/medicines/{m['id']}", json={"days": [0, 2, 4], "remind": False})
    assert r.json()["days"] == [0, 2, 4] and not r.json()["remind"] and r.json()["dose"] == "10 mg", "the rest stays"
    assert client.patch(f"/api/medicines/{m['id']}", json={"endOn": "2000-01-01", "startOn": "2001-01-01"}).status_code == 400
    assert client.patch(f"/api/medicines/{m['id']}", json={"endOn": "2000-01-01"}).status_code == 200
    got = client.get("/api/medicines", params={"tz": TZ}).json()
    assert [x["name"] for x in got["medicines"]] == ["Lisinopril"] and got["day"]["doses"] == [], "ended: nothing due"
    assert client.delete(f"/api/medicines/{m['id']}").status_code == 200
    assert client.get("/api/medicines").json()["medicines"] == []
    assert client.patch(f"/api/medicines/{m['id']}", json={"name": "x"}).status_code == 404


def test_doses_are_ticked_skipped_and_unticked(client, admin):
    a = client.post("/api/medicines", json={"name": "Metformin", "dose": "500 mg", "note": "with food", "times": ["08:00", "20:00"]}).json()
    b = client.post("/api/medicines", json={"name": "Vitamin D", "times": ["08:00"], "days": [(_today().weekday() + 1) % 7]}).json()
    c = client.post("/api/medicines", json={"name": "Ibuprofen", "dose": "400 mg"}).json()  # when needed
    day = client.get("/api/medicines", params={"tz": TZ}).json()["day"]
    assert [(d["name"], d["slot"]) for d in day["doses"]] == [("Metformin", "08:00"), ("Metformin", "20:00")], "Vitamin D: not today"
    assert [x["name"] for x in day["asNeeded"]] == ["Ibuprofen"] and day["asNeeded"][0]["taken"] == []
    today = day["date"]
    r = client.post(f"/api/medicines/{a['id']}/doses", json={"day": today, "slot": "08:00"})
    assert r.status_code == 200 and r.json()["taken"]
    client.post(f"/api/medicines/{a['id']}/doses", json={"day": today, "slot": "20:00", "taken": False, "skipped": True})
    doses = client.get("/api/medicines", params={"tz": TZ}).json()["day"]["doses"]
    assert doses[0]["taken"] and not doses[0]["skipped"] and doses[1]["skipped"] and not doses[1]["taken"]
    client.post(f"/api/medicines/{a['id']}/doses", json={"day": today, "slot": "08:00", "taken": False})
    assert client.get("/api/medicines", params={"tz": TZ}).json()["day"]["doses"][0]["taken"] is None, "unticked"
    assert client.post(f"/api/medicines/{a['id']}/doses", json={}).status_code == 400, "set times: say which dose"
    assert client.post(f"/api/medicines/{a['id']}/doses", json={"day": "2001-01-01", "slot": "08:00"}).status_code == 400
    assert client.post(f"/api/medicines/{c['id']}/doses", json={}).status_code == 200
    assert len(client.get("/api/medicines", params={"tz": TZ}).json()["day"]["asNeeded"][0]["taken"]) == 1
    assert b["id"]
    # the reminder's button: the 08:00 doses not ticked yet
    assert client.post("/api/medicines/taken", json={"day": today, "slot": "08:00"}).json() == {"ticked": 1}
    assert client.post("/api/medicines/taken", json={"day": today, "slot": "08:00"}).json() == {"ticked": 0}
    assert client.post("/api/medicines/taken", json={"day": today}).status_code == 400
    h = client.get("/api/medicines/history", params={"days": 3, "tz": TZ}).json()
    assert len(h["days"]) == 3 and h["days"][-1]["date"] == today
    assert h["days"][-1]["medicines"] == [{"medicine": a["id"], "due": 2, "taken": 1, "skipped": 1}]


def test_stopped_medicines_are_not_due_and_another_account_sees_none(client, admin):
    m = client.post("/api/medicines", json={"name": "Amoxicillin", "times": ["09:00"]}).json()
    a = client.post("/api/allergies", json={"name": "Penicillin", "severity": "severe", "reaction": "Hives"}).json()
    client.patch(f"/api/medicines/{m['id']}", json={"stoppedOn": _today().isoformat()})
    assert client.get("/api/medicines").json()["day"]["doses"] == []
    assert testing.add_account(client, {"name": "bo", "password": "secretpw2", "role": "member"}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "bo", "password": "secretpw2"}).status_code == 200
    got = client.get("/api/medicines").json()
    assert got["medicines"] == [] and got["allergies"] == []
    assert client.patch(f"/api/medicines/{m['id']}", json={"name": "x"}).status_code == 404
    assert client.post(f"/api/medicines/{m['id']}/doses", json={"slot": "09:00"}).status_code == 404
    assert client.delete(f"/api/allergies/{a['id']}").status_code == 404
    assert client.get("/api/emergency").json()["allergies"] == []


def test_allergies(client, admin):
    client.post("/api/allergies", json={"name": "Pollen", "severity": "mild"})
    p = client.post("/api/allergies", json={"name": "Peanuts", "severity": "Severe", "reaction": "Anaphylaxis", "note": "EpiPen in bag"}).json()
    client.post("/api/allergies", json={"name": "Latex"})
    assert [x["name"] for x in client.get("/api/allergies").json()["items"]] == ["Peanuts", "Pollen", "Latex"], "severe first"
    assert client.post("/api/allergies", json={"name": "x", "severity": "deadly"}).status_code == 400
    assert client.post("/api/allergies", json={"severity": "mild"}).status_code == 400
    assert client.patch(f"/api/allergies/{p['id']}", json={"severity": "moderate"}).json()["reaction"] == "Anaphylaxis"
    assert client.delete(f"/api/allergies/{p['id']}").status_code == 200
    assert [x["name"] for x in client.get("/api/allergies").json()["items"]] == ["Pollen", "Latex"]


def test_the_reminder_comes_at_the_dose_time_once_with_a_taken_button(client, admin, messages, monkeypatch):
    monkeypatch.setattr(push, "link", lambda app, path="": "https://health.example.com/" + path.lstrip("/"))
    uid = admin["id"]
    client.get("/api/medicines", params={"tz": TZ})  # the zone the person is in
    loc = webapi.zone_of(uid)
    assert str(loc) == TZ
    client.post("/api/medicines", json={"name": "Metformin", "dose": "500 mg", "note": "with food", "times": ["08:00"]})
    client.post("/api/medicines", json={"name": "Lisinopril", "dose": "10 mg", "times": ["08:00", "20:00"]})
    client.post("/api/medicines", json={"name": "Quiet one", "times": ["08:00"], "remind": False})
    day = dt.datetime.now(loc).date()
    at = lambda h, m=0: dt.datetime(day.year, day.month, day.day, h, m, tzinfo=loc)  # noqa: E731
    assert meds.remind(uid, at(7, 59)) == 0, "no device yet"
    _device(uid)
    assert meds.remind(uid, at(7, 59)) == 0 and not messages, "not yet"
    assert meds.remind(uid, at(8, 1)) == 1
    msg = messages[-1]
    assert msg["title"] == "Time for Lisinopril and Metformin" and "Quiet one" not in msg["body"]
    assert msg["kind"] == "health_meds" and msg["url"].endswith("#/medicines")
    assert msg["actions"][0]["title"] == "Taken" and msg["actions"][0]["post"].endswith("/api/medicines/taken")
    assert msg["actions"][0]["body"] == {"day": day.isoformat(), "slot": "08:00"}
    assert meds.remind(uid, at(8, 30)) == 0, "once"
    # the evening dose, ticked before its time: no reminder
    lis = next(m for m in meds.medicines(uid) if m["name"] == "Lisinopril")
    meds.mark(uid, lis["id"], day, "20:00")
    assert meds.remind(uid, at(20, 5)) == 0
    # a server that was off at the time: not hours later
    client.post("/api/medicines", json={"name": "Late", "times": ["12:00"]})
    assert meds.remind(uid, at(15, 0)) == 0
    assert meds.remind(uid, at(12, 10)) == 1 and messages[-1]["title"] == "Time for Late"
    # turned off in Settings › Account › Notifications
    push.set_prefs(uid, kinds={"health_meds": False})
    assert meds.reminders(at(12, 15)) == 0


def test_the_kind_is_offered_and_a_device_gets_the_buttons(client, admin, sent):
    assert "health_meds" in push.KIND and push.KIND["health_meds"]["app"] == "iohealth"
    _device(admin["id"])
    acts = [{"action": "taken", "title": "Taken", "post": "https://health.example.com/api/medicines/taken", "body": {"slot": "08:00"}},
            {"action": "x", "title": "No address", "post": "javascript:alert(1)"}]
    assert push._actions(acts) == acts[:1], "only an http(s) address"
    assert push.notify(admin["id"], "health_meds", "Time for pills", actions=acts) == 1 and len(sent) == 1


def _contact(cid, name, phone, org=None):
    return {"id": cid, "fn": name, "org": org, "title": None, "phones": [{"label": "work", "value": phone, "pref": 1}]}


def test_the_emergency_card(client, admin, monkeypatch):
    client.post("/api/allergies", json={"name": "Penicillin", "severity": "severe", "reaction": "Hives"})
    client.post("/api/medicines", json={"name": "Lisinopril", "dose": "10 mg", "times": ["08:00"]})
    client.post("/api/medicines", json={"name": "Secret one", "times": ["08:00"], "onCard": False})
    db.ex("INSERT INTO hlt_characteristics (name, value, user_id) VALUES ('dateOfBirth', '1984-03-12', %s)", (admin["id"],))
    contacts = {11: _contact(11, "Dr. Helen Park", "+1 541 555 0160", "Juniper Family Medicine"), 12: _contact(12, "Riley Calloway", "+1 541 555 0102")}
    docs = {21: {"id": 21, "title": "Morgan’s health insurance card", "kind": "membership", "kindLabel": "Membership or card",
                 "issuer": "Willamette Care Health Plan", "number": "WCH900217", "fields": [{"name": "Group", "value": "GRP-55120"}]},
            22: {"id": 22, "title": "Car insurance", "kind": "insurance", "issuer": "Cascade Auto", "fields": []},
            23: {"id": 23, "title": "Passport", "kind": "passport", "fields": []}}
    asked = []

    def ask(self, request, path, params=None, body=None, method=None):
        asked.append((self.provider, path, params))
        if path == "/api/contacts":
            return {"items": [contacts[11]]}
        if path == "/api/documents":
            return {"items": list(docs.values())}
        kind, i = path.rsplit("/", 2)[-2:]
        pool = contacts if kind == "contacts" else docs
        if int(i) not in pool:
            raise links.Unavailable(404, "Not found")
        return pool[int(i)]
    monkeypatch.setattr(links.App, "ask", ask)
    monkeypatch.setattr(links.App, "enabled", lambda self: True)
    monkeypatch.setattr(links.App, "url", lambda self: f"https://{self.provider}.example.com/")

    assert client.put("/api/emergency", json={"bloodType": "Z+"}).status_code == 400
    assert client.put("/api/emergency", json={"doctors": [1, 2, 3, 4, 5]}).status_code == 400, "what fits on a card"
    r = client.put("/api/emergency", json={"bloodType": "o+", "organDonor": "yes", "conditions": "Type 2 diabetes",
                                           "doctors": [11], "contacts": [{"id": 12}, 99], "documents": [21]})
    assert r.status_code == 200 and r.json()["bloodType"] == "O+" and r.json()["contacts"] == [12, 99]
    assert client.put("/api/emergency", json={"notes": "Glasses"}).json()["conditions"] == "Type 2 diabetes", "the rest stays"
    c = client.get("/api/emergency", params={"tz": TZ}).json()
    assert c["person"] == {"name": "alex", "born": "1984-03-12"} and c["bloodType"] == "O+" and c["organDonor"] == "yes"
    assert [a["name"] for a in c["allergies"]] == ["Penicillin"] and [m["name"] for m in c["medicines"]] == ["Lisinopril"]
    assert c["doctors"] == [{"id": 11, "name": "Dr. Helen Park", "org": "Juniper Family Medicine", "title": "", "phone": "+1 541 555 0160", "found": True}]
    assert c["contacts"][0]["name"] == "Riley Calloway" and c["contacts"][1] == {"id": 99, "found": False}, "no longer seen: marked"
    assert c["contacts"][0]["relation"] == "", "no card of their own in ioContact: nothing is said"
    # with their own card there ("This is me"), what each person to call is to them: stated first, then what the family implies
    from iosuite_shared import users as shared_users
    contacts[5] = {**_contact(5, "Morgan Calloway", "+1 541 555 0101"), "relations": [{"type": "spouse", "relatedId": 12, "typeLabel": "Wife"},
                                                                                 {"type": "emergency", "relatedId": 13, "typeLabel": "Emergency contact"}],
                   "impliedRelations": [{"type": "parent", "relatedId": 12, "typeLabel": "Mother"}, {"type": "aunt_uncle", "relatedId": 13, "typeLabel": "Uncle"}]}
    contacts[13] = _contact(13, "Sam Calloway", "+1 541 555 0170")
    shared_users.set_value(admin["id"], "iocontact", "me_contact_id", 5)
    client.put("/api/emergency", json={"contacts": [12, 13, 99]})
    c = client.get("/api/emergency", params={"tz": TZ}).json()
    assert [x.get("relation") for x in c["contacts"]] == ["Wife", "Uncle", None]
    assert "relation" not in c["doctors"][0]
    assert c["documents"][0]["number"] == "WCH900217" and c["documents"][0]["fields"] == [{"name": "Group", "value": "GRP-55120"}]
    assert ("iodocs", "/api/documents/21", None) in asked, "asked as the viewer, one by one"
    found = client.get("/api/emergency/documents").json()["items"]
    assert [d["id"] for d in found][:2] == [21, 22] and found[0]["suggested"] and not found[2]["suggested"], "health insurance first"
    assert asked[-1][2] == {"person": str(admin["id"]), "limit": 100}, "theirs"
    assert client.get("/api/emergency/contacts", params={"q": "park"}).json()["items"][0]["phone"] == "+1 541 555 0160"

    def down(self, request, path, params=None, body=None, method=None):
        raise links.Unavailable(502, "ioContact did not answer a moment ago")
    monkeypatch.setattr(links.App, "ask", down)
    c = client.get("/api/emergency").json()
    assert c["problems"] and c["doctors"] == [{"id": 11, "found": None}], "not answering is not the same as gone"
    assert client.get("/api/emergency/contacts", params={"q": "x"}).status_code == 502


def test_the_blood_type_the_phone_sends():
    assert [emergency.blood_of(v) for v in ("A+", "aPositive", "HKBloodTypeABNegative", "o-", "notSet", None)] == ["A+", "A+", "AB-", "O-", "", ""]


def test_the_card_without_the_other_apps(client, admin):
    c = client.get("/api/emergency").json()
    assert c["doctors"] == [] and c["documents"] == [] and c["problems"] == [] and c["bloodType"] == ""
    assert json.loads(json.dumps(c["apps"]))["iocontact"]["on"] in (True, False)


def test_deleting_someone_removes_their_medicines(client, admin):
    from iosuite_shared import users
    assert testing.add_account(client, {"name": "sam", "password": "secretpw2", "role": "member"}).status_code == 200
    sam = users.find("sam")["id"]
    mid = meds.add(sam, {"name": "Aspirin", "times": ["08:00"]})["id"]
    meds.mark(sam, mid, _today(), "08:00")
    db.ex("INSERT INTO hlt_allergies (name, user_id) VALUES ('Cats', %s)", (sam,))
    emergency.save(sam, {"bloodType": "A+"})
    got = {i["what"]: i["count"] for i in client.get(f"/api/suite-admin/person-data/{sam}").json()["items"]}
    assert got["medicine"] == 1 and got["allergy"] == 1
    assert client.delete(f"/api/suite-admin/users/{sam}").status_code == 200
    for t in ("hlt_medicines", "hlt_medicine_doses", "hlt_allergies", "hlt_emergency"):
        assert db.one(f"SELECT count(*) FROM {t} WHERE user_id = %s", (sam,))[0] == 0, t

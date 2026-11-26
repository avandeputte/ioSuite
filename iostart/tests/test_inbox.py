"""The suite's inbox by email (iostart/inbox): taking messages apart, what kind each is, whose it is, who sees it,
filing it as its sender (by itself only when the mail server vouched for them), and the mailbox's settings. The mail
server and the other apps are stood in for."""
import json
import time
from email.message import EmailMessage

import pytest

from iosuite_shared import credentials, testing, users

from iostart import db, inbox
from iostart.inbox import mail

ALEX = "alex@family.example"
GOOD = "mx.example.net; dkim=pass header.d=family.example header.s=x; spf=pass smtp.mailfrom=family.example; dmarc=pass (p=none) header.from=family.example"


def message(sender=ALEX, subject="Hello", text="Hi", html=None, files=(), to="inbox@family.example", auth=GOOD, mid=None, date=None):
    m = EmailMessage()
    m["From"] = f"Someone <{sender}>"
    m["To"] = to
    m["Subject"] = subject
    m["Date"] = date or "Mon, 23 Nov 2026 10:00:00 +0000"
    m["Message-ID"] = mid or f"<{time.time_ns()}@family.example>"
    if auth:
        m["Authentication-Results"] = auth
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    for name, mime, data in files:
        main, sub = mime.split("/")
        m.add_attachment(data, maintype=main, subtype=sub, filename=name)
    return m.as_bytes()


PDF = b"%PDF-1.4\n%fake\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
ICS = (b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:dentist-1@example\r\nSUMMARY:Dentist\r\n"
       b"DTSTART:20261201T150000Z\r\nDTEND:20261201T160000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


@pytest.fixture()
def apps(monkeypatch):
    """The other apps, stood in for: {(app, method, path): reply or callable(params, body, data)}; calls: every
    (app, method, path, params, body, data, cookie) asked."""
    table, calls = {}, []

    def fake(req, app, path, params=None, body=None, method=None, data=None, content_type=None, **kw):
        m = method or ("POST" if body is not None or data is not None else "GET")
        calls.append((app, m, path, dict(params or {}), body, data, content_type, req.cookies.get("iothing_session")))
        r = table.get((app, m, path))
        if r is None:
            raise AssertionError(f"not stood in for: {app} {m} {path}")
        return r(params or {}, body, data) if callable(r) else r
    monkeypatch.setattr(inbox.links, "as_viewer", fake)
    monkeypatch.setattr(inbox.links, "available", lambda app: True)
    return table, calls


def alex_email():
    uid = users.find("alex")["id"]
    users.update(uid, email=ALEX)
    return uid


# ------------------------------------------------------------------ reading a message

def test_what_a_message_is():
    # a receipt whose amount is in its HTML only, the grand total over the subtotal
    m = mail.parse(message(subject="Your receipt from Corner Bakery", text="",
                           html="<p>Subtotal $80.00</p><p>Tax $4.12</p><table><tr><td>Grand Total</td><td>$84.12</td></tr></table><script>x()</script>"))
    assert "Grand Total" in m["text"] and "<" not in m["text"] and "x()" not in m["text"]
    kind, tag, g = inbox.classify(m)
    assert kind == "receipt" and tag is None and g["amount"] == 84.12 and g["day"] == "2026-11-23"
    # a PDF with no money words: a document; an invitation; a plain note
    assert inbox.classify(mail.parse(message(subject="Passport scan", files=[("scan.pdf", "application/pdf", PDF)])))[0] == "document"
    inv = mail.parse(message(subject="Invitation: Dentist", files=[("invite.ics", "text/calendar", ICS)]))
    assert inv["invite"] and inbox.classify(inv)[0] == "invite"
    assert inbox.classify(mail.parse(message(subject="Lunch?", text="Lunch tomorrow?")))[0] == "other"
    # the +word of the address says where it goes, whatever it looks like
    k, tag, _ = inbox.classify(mail.parse(message(subject="Lunch?", to="inbox+docs@family.example", files=[("a.pdf", "application/pdf", PDF)])),
                               "inbox@family.example")
    assert (k, tag) == ("document", "docs")
    assert inbox.classify(mail.parse(message(subject="Receipt", text="Total $5.00", to="inbox+hold@family.example")))[0] == "other"


def test_amounts_and_forwarded_receipts():
    assert inbox.money("1,234.56") == 1234.56 and inbox.money("1.234,56") == 1234.56 and inbox.money("84,12") == 84.12
    assert inbox.amount_of("Subtotal: $10.00\nShipping $2.00\nOrder total: $12.00\nTotal paid $12.00") == 12.0
    assert inbox.amount_of("Sub-total 9.00\nTotal 9.99") == 9.99
    assert inbox.amount_of("nothing to pay") is None
    fwd = ("Here it is\n\n---------- Forwarded message ---------\nFrom: Corner Bakery <orders@cornerbakery.example>\n"
           "Date: Mon, Nov 23, 2026\nSubject: Your receipt\n\nTotal: $84.12\n")
    m = mail.parse(message(subject="Fwd: Your receipt", text=fwd))
    assert m["forwarded"] == {"name": "Corner Bakery", "from": "orders@cornerbakery.example"}
    kind, _, g = inbox.classify(m)
    assert kind == "receipt" and g["merchant"] == "Corner Bakery" and g["title"] == "Your receipt"
    assert inbox.merchant_of({"from": "receipts@shop.acme.example", "name": ""}) == "Acme"


def test_only_the_mailbox_servers_word_on_the_sender_counts():
    assert mail.parse(message())["trusted"]
    assert not mail.parse(message(auth=None))["trusted"]
    assert not mail.parse(message(auth="mx.example.net; dmarc=fail header.from=family.example"))["trusted"]
    assert not mail.parse(message(auth="mx.example.net; dkim=pass header.d=other.example"))["trusted"]
    assert mail.parse(message(auth="mx.example.net; dkim=pass header.d=family.example; dmarc=none"))["trusted"]
    # a sender who writes their own "pass" line below the server's gets nowhere
    m = EmailMessage()
    m["Authentication-Results"] = "mx.example.net; dmarc=fail header.from=family.example"
    m["Authentication-Results"] = GOOD
    m["From"] = ALEX
    m.set_content("x")
    assert not mail.parse(m.as_bytes())["trusted"]


# ------------------------------------------------------------------ whose it is, who sees it

def test_whose_mail_it_is_and_who_sees_it(client):
    uid = alex_email()
    mine = inbox.keep(mail.parse(message(subject="Mine")))
    nobody = inbox.keep(mail.parse(message(sender="stranger@else.example", subject="Who?")))
    assert inbox.keep(mail.parse(message(mid="<same@x>"))) and inbox.keep(mail.parse(message(mid="<same@x>"))) is None  # once
    got = client.get("/api/inbox").json()
    assert {i["subject"] for i in got["items"]} >= {"Mine", "Who?"} and got["unclaimed"] == 1
    assert client.get(f"/api/inbox/{nobody}").json()["person"] is None
    # riley (a member, no suite admin) sees neither alex's nor the stranger's
    testing.add_account(client, {"name": "riley", "password": "secret123", "role": "member", "email": "riley@family.example"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "riley", "password": "secret123"})
    assert client.get("/api/inbox").json()["items"] == []
    assert client.get(f"/api/inbox/{mine}").status_code == 404 and client.get(f"/api/inbox/{nobody}").status_code == 404
    assert client.post(f"/api/inbox/{nobody}/give", json={"person": "riley"}).status_code == 403
    assert client.get("/api/inbox/mailbox").status_code == 403
    # another address of riley's makes mail from it riley's
    assert client.put("/api/inbox/me", json={"addresses": "Riley@Work.example, " + ALEX}).status_code == 400  # alex's
    assert client.put("/api/inbox/me", json={"addresses": "Riley@Work.example"}).json()["addresses"] == ["riley@work.example"]
    hers = inbox.keep(mail.parse(message(sender="riley@work.example", subject="From work")))
    assert [i["id"] for i in client.get("/api/inbox").json()["items"]] == [hers]
    # the suite admin gives the stranger's to riley
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert client.post(f"/api/inbox/{nobody}/give", json={"person": "riley"}).json()["person"] != uid
    assert client.get(f"/api/inbox/{nobody}").status_code == 404
    assert inbox.person_data(uid, False) == 2 and inbox.person_data(uid, True) == 2
    assert client.get(f"/api/inbox/{mine}").status_code == 404


def test_the_addresses_on_a_persons_own_card_in_iocontact_are_theirs(client, apps):
    table, calls = apps
    uid = alex_email()
    inbox._cards.clear()
    table[("iocontact", "GET", "/api/contacts/7")] = {"id": 7, "fn": "Alex Example", "emails": [{"value": "Alex@Other.example"}, {"value": ALEX}]}
    early = inbox.keep(mail.parse(message(sender="alex@other.example", subject="Before the card")))
    assert client.get(f"/api/inbox/{early}").json()["person"] is None, "no card of their own yet"
    users.set_value(uid, "iocontact", "me_contact_id", 7)
    later = inbox.keep(mail.parse(message(sender="alex@other.example", subject="From my other address")))
    assert client.get(f"/api/inbox/{later}").json()["person"] == uid
    assert calls[-1][:3] == ("iocontact", "GET", "/api/contacts/7") and calls[-1][-1], "read as the person, with a sign-in of theirs"
    n = len(calls)
    assert inbox.claim() == 1 and client.get(f"/api/inbox/{early}").json()["person"] == uid, "what waited as nobody's is theirs too"
    assert len(calls) == n, "the card is not read again for every message"
    assert client.get("/api/inbox/me").json()["card"] == ["alex@other.example", ALEX.lower()]
    assert inbox.keep(mail.parse(message(sender="stranger@else.example", subject="Still nobody's"))) and client.get("/api/inbox").json()["unclaimed"] == 1
    users.set_value(uid, "iocontact", "me_contact_id", None)
    inbox._cards.clear()


def test_files_are_served_safely(client):
    alex_email()
    iid = inbox.keep(mail.parse(message(subject="Scan", files=[("scan.pdf", "application/pdf", PDF), ("x.png", "image/png", b"\x89PNG\r\n\x1a\nxx")])))
    it = client.get(f"/api/inbox/{iid}").json()
    assert [f["name"] for f in it["files"]] == ["scan.pdf", "x.png"]
    r = client.get(it["files"][1]["url"])
    assert r.status_code == 200 and "sandbox" in r.headers["content-security-policy"]
    assert client.get(it["files"][0]["url"] + "?download=true").headers["content-type"] == "application/octet-stream"


# ------------------------------------------------------------------ filing

def test_a_vouched_receipt_lands_on_its_transaction_by_itself(client, apps):
    table, calls = apps
    alex_email()
    table[("iomoney", "GET", "/api/transactions")] = {"items": [{"id": 7, "day": "2026-11-22", "amount": -84.12, "merchant": "CORNER BAKERY #12"},
                                                                {"id": 8, "day": "2026-11-21", "amount": -84.12, "merchant": "Gas station"}]}
    table[("iomoney", "POST", "/api/transactions/7/receipts")] = {"id": 1}
    table[("iomoney", "GET", "/api/transactions/7")] = {"id": 7, "day": "2026-11-22", "amount": -84.12, "merchant": "Corner Bakery"}
    iid = inbox.keep(mail.parse(message(subject="Your receipt from Corner Bakery", text="Total: $84.12",
                                        files=[("receipt.pdf", "application/pdf", PDF)])))
    inbox.by_itself(iid)
    r = db.one("SELECT * FROM prt_inbox WHERE id = %s", (iid,))
    assert r["status"] == "filed", r["note"]
    filed = json.loads(r["filed"])
    assert filed["app"] == "iomoney" and filed["id"] == 7 and filed["auto"] is True
    ask = calls[0]
    assert ask[3]["amount"] == "84.12" and ask[3]["flow"] == "out" and ask[3]["start"] == "2026-11-16" and ask[3]["end"] == "2026-11-27"
    post = next(c for c in calls if c[1] == "POST")
    assert post[5] == PDF and post[6] == "application/pdf" and post[7]  # the file, as alex
    # the sign-in made for it is gone again
    assert email_sessions() == 0


def email_sessions():
    from iosuite_shared import db as shared
    return shared.one("SELECT count(*) AS n FROM ios_sessions WHERE via = 'email'")["n"]


def test_what_is_not_vouched_or_not_clear_waits(client, apps):
    table, calls = apps
    alex_email()
    a = inbox.keep(mail.parse(message(subject="Receipt", text="Total $5.00", auth=None)))
    inbox.by_itself(a)
    r = db.one("SELECT * FROM prt_inbox WHERE id = %s", (a,))
    assert r["status"] == "waiting" and "vouch" in r["note"] and calls == []
    # two transactions of the amount, neither named like the shop: pick one by hand
    table[("iomoney", "GET", "/api/transactions")] = {"items": [{"id": 7, "merchant": "A"}, {"id": 8, "merchant": "B"}]}
    b = inbox.keep(mail.parse(message(subject="Receipt", text="Total $5.00")))
    inbox.by_itself(b)
    r = db.one("SELECT * FROM prt_inbox WHERE id = %s", (b,))
    assert r["status"] == "waiting" and "pick" in r["note"] and r["retry_at"] is None
    table[("iomoney", "POST", "/api/transactions/8/receipts")] = {"id": 3}
    table[("iomoney", "GET", "/api/transactions/8")] = {"id": 8, "merchant": "B"}
    got = client.post(f"/api/inbox/{b}/file", json={"to": "money", "transaction": 8}).json()
    assert got["status"] == "filed" and got["filed"]["auto"] is False
    post = [c for c in calls if c[1] == "POST"][-1]
    assert post[5][:5] == b"%PDF-" and post[3]["name"].endswith(".pdf")  # no file came with it: the mail itself as a PDF
    # someone who turned "file by itself" off gets everything to tap
    client.put("/api/inbox/me", json={"auto": False})
    c = inbox.keep(mail.parse(message(subject="Receipt", text="Total $5.00")))
    n = len(calls)
    inbox.by_itself(c)
    assert len(calls) == n and db.one("SELECT status FROM prt_inbox WHERE id = %s", (c,))["status"] == "waiting"


def test_a_receipt_before_its_transaction_is_tried_again(client, apps):
    table, calls = apps
    alex_email()
    table[("iomoney", "GET", "/api/transactions")] = {"items": []}
    iid = inbox.keep(mail.parse(message(subject="Order confirmation", text="Order total: $19.99")))
    inbox.by_itself(iid)
    r = db.one("SELECT * FROM prt_inbox WHERE id = %s", (iid,))
    assert r["status"] == "waiting" and r["retry_at"] and "bank" in r["note"]
    table[("iomoney", "GET", "/api/transactions")] = {"items": [{"id": 4, "merchant": "Shop"}]}
    table[("iomoney", "POST", "/api/transactions/4/receipts")] = {"id": 1}
    table[("iomoney", "GET", "/api/transactions/4")] = {"id": 4}
    assert inbox.retry_due() == 0  # not yet due
    db.ex("UPDATE prt_inbox SET retry_at = 1 WHERE id = %s", (iid,))
    inbox.tick()
    assert db.one("SELECT status FROM prt_inbox WHERE id = %s", (iid,))["status"] == "filed"


def test_papers_go_to_iodocs_privately_and_invitations_to_the_calendar(client, apps):
    table, calls = apps
    uid = alex_email()
    table[("iodocs", "POST", "/api/documents")] = {"id": 12, "title": "Passport scan"}
    table[("iodocs", "POST", "/api/documents/12/files")] = {"file": {"id": 1}}
    d = inbox.keep(mail.parse(message(subject="Fwd: Passport scan", files=[("passport.pdf", "application/pdf", PDF)])))
    inbox.by_itself(d)
    made = next(c for c in calls if c[2] == "/api/documents")
    assert made[4]["visibility"] == "private" and made[4]["title"] == "Passport scan"
    up = next(c for c in calls if c[2] == "/api/documents/12/files")
    assert up[3] == {"ext": "pdf"} and up[5] == PDF and "name" not in up[3]  # ioDocs names the file itself
    assert json.loads(db.one("SELECT filed FROM prt_inbox WHERE id = %s", (d,))["filed"])["href"]
    table[("iocalendar", "GET", "/api/calendars")] = {"items": [{"id": 1, "name": "Family", "writable": True, "mine": False},
                                                                 {"id": 2, "name": "Alex", "writable": True, "mine": True},
                                                                 {"id": 3, "name": "Holidays", "writable": False, "mine": False}]}
    table[("iocalendar", "POST", "/api/calendars/2/import")] = {"created": 1, "updated": 0, "errors": []}
    table[("iocalendar", "POST", "/api/calendars/1/import")] = {"created": 0, "updated": 1, "errors": []}
    e = inbox.keep(mail.parse(message(subject="Invitation: Dentist", files=[("invite.ics", "text/calendar", ICS)])))
    inbox.by_itself(e)
    imp = next(c for c in calls if c[2] == "/api/calendars/2/import")
    assert b"Dentist" in imp[5] and imp[6] == "text/calendar"
    assert "Dentist in Alex" in json.loads(db.one("SELECT filed FROM prt_inbox WHERE id = %s", (e,))["filed"])["label"]
    # a calendar of one's choice, for the next ones
    inbox.set_own(uid, {"calendar": 1})
    f = inbox.keep(mail.parse(message(subject="Updated invitation: Dentist", files=[("invite.ics", "text/calendar", ICS)])))
    inbox.by_itself(f)
    assert any(c[2] == "/api/calendars/1/import" for c in calls)
    assert client.get("/api/inbox/calendars").json()["items"] == [{"id": 1, "name": "Family", "mine": False, "color": None},
                                                                  {"id": 2, "name": "Alex", "mine": True, "color": None}]


def test_let_go_bring_back_and_remove(client):
    alex_email()
    iid = inbox.keep(mail.parse(message(subject="Lunch?")))
    assert client.post(f"/api/inbox/{iid}/let-go").json()["status"] == "gone"
    assert client.get("/api/inbox").json()["waiting"] == 0
    assert [i["id"] for i in client.get("/api/inbox?show=done").json()["items"]] == [iid]
    assert client.post(f"/api/inbox/{iid}/back").json()["status"] == "waiting"
    assert client.post(f"/api/inbox/{iid}/file", json={"to": "nowhere"}).status_code == 400
    assert client.delete(f"/api/inbox/{iid}").status_code == 200 and client.get(f"/api/inbox/{iid}").status_code == 404
    db.ex("UPDATE prt_inbox SET status = 'gone', done_at = 1")
    inbox.purge()


# ------------------------------------------------------------------ the mailbox

def test_the_mailbox_settings_and_reading_it(client, apps, monkeypatch):
    alex_email()
    assert client.get("/api/inbox").json()["mailbox"]["ready"] is False
    assert client.put("/api/inbox/mailbox", json={"host": "imap.example.net/x"}).status_code == 400
    got = client.put("/api/inbox/mailbox", json={"host": "imap.example.net", "user": "inbox@family.example", "password": "pw-1"}).json()
    assert got["ready"] and got["passwordSet"] and "pw-1" not in json.dumps(got) and got["port"] == 993
    assert credentials.get("iostart", "mail_password") == "pw-1"
    assert any(k["name"] == "mail_password" for k in credentials.listing("iostart"))  # Settings › Suite › Keys lists it
    seen, raws = [], [("1", message(subject="Lunch?")), ("2", None), ("3", message(subject="Lunch?", mid="<l@x>"))]

    class Box:
        def __init__(self, host, port, user, password, folder):
            assert (host, port, user, password, folder) == ("imap.example.net", 993, "inbox@family.example", "pw-1", "INBOX")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def unread(self, limit):
            yield from raws

        def seen(self, uid):
            seen.append(uid)
    monkeypatch.setattr(mail, "Mailbox", Box)
    assert client.post("/api/inbox/mailbox/check").json() == {"read": 3, "kept": 2}
    assert seen == ["1", "2", "3"]
    items = client.get("/api/inbox").json()["items"]
    assert len(items) == 3 and any("too large" in i["subject"] for i in items)
    assert client.get("/api/inbox/mailbox").json()["state"]["error"] is None

    class Broken(Box):
        def __enter__(self):
            raise mail.MailError("The mail server did not take this user name and password")
    monkeypatch.setattr(mail, "Mailbox", Broken)
    r = client.post("/api/inbox/mailbox/check")
    assert r.status_code == 400 and "user name" in r.json()["detail"]
    assert "user name" in client.get("/api/inbox/mailbox").json()["state"]["error"]
    # the password can be taken away; then the job leaves the mailbox alone
    client.put("/api/inbox/mailbox", json={"password": None})
    assert not inbox.ready() and client.post("/api/inbox/mailbox/check").status_code == 400

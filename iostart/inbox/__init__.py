"""The suite's inbox by email: one mailbox the suite reads, so that mail sent or forwarded to it lands where it belongs.

    a receipt     on the matching ioMoney transaction (the same amount, a few days around the mail), as its receipt
    a PDF, a scan in ioDocs, as a new document only the sender sees (they share it from there)
    an invitation in ioCalendar (its .ics), in the sender's own calendar
    the rest      waits on the Inbox page (#/inbox) to be filed by hand, or let go

Whose mail it is: the sender's address, matched against the accounts' email addresses, the other addresses each
person adds on the Inbox page (Your addresses), and the addresses on each person's own card in ioContact (the one
their account is tied to, "This is me" there; read as that person, card_addresses). Mail from an address nobody has waits for a suite admin, who gives it
to someone or lets it go. Nobody else sees a person's mail, admins included.

Filing happens as that person: the suite asks the other app with a sign-in of theirs made for the moment (a session
of a few minutes, ended right after), so the app decides as it always does (the ioMoney accounts they see, the
calendars they may write). The item's history in that app says it came by email, through the start page.

Filing by itself (without a tap) only when the mail server vouched for the sender (mail.vouched: DMARC or DKIM passed
for the sender's domain), because anybody can write any From line; and only for a person who leaves "File by itself"
on. Everything else waits for a tap. A receipt whose transaction has not come from the bank yet is tried again every
hour for RETRY_DAYS days. Sending to the mailbox's +money, +docs, +calendar address (inbox+docs@…) says where it goes;
+inbox keeps it in the Inbox.

The mailbox (Inbox › Mailbox, suite admins): host, port, user name and folder in the start page's settings; the
password with the suite's keys and tokens (iostart mail_password, Settings › Suite › Keys). The job reads it every
EVERY seconds. Filed and let-go mail stays listed (with its files) for KEEP_DAYS days, then goes.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import logging
import re
import time
import urllib.error

from iosuite_shared import admin as suite_admin, catalog, credentials, db as shared_db, links, push, sessions, stamp, users
from iosuite_shared.errors import Invalid

from iostart import config, db
from iostart.inbox import mail

log = logging.getLogger("iostart.inbox")

EVERY = 5 * 60          # between two looks at the mailbox
TICK = 60               # between the job's looks at whether one is due
BATCH = 25              # messages read in one look
KEEP_DAYS = 30          # filed and let-go mail stays this long
RETRY_DAYS = 10         # a receipt waits this long for its transaction to come from the bank
RETRY_S = 3600          # ... asked again this often
AROUND = (-7, 4)        # days around the mail's day a transaction may be on
SESSION_S = 300         # the sign-in made to file as somebody lasts at most this long
KINDS = ("receipt", "document", "invite", "other")
TAGS = {"money": "receipt", "receipt": "receipt", "receipts": "receipt", "iomoney": "receipt",
        "docs": "document", "doc": "document", "document": "document", "documents": "document", "papers": "document", "iodocs": "document",
        "calendar": "invite", "cal": "invite", "event": "invite", "events": "invite", "invite": "invite", "iocalendar": "invite",
        "inbox": "other", "hold": "other"}
APP_OF = {"receipt": "iomoney", "document": "iodocs", "invite": "iocalendar"}
STATE = "inbox_state"  # what the last look at the mailbox found (prt_state)
CONTACTS = "iocontact"
CARD_S = 10 * 60        # a person's own card in ioContact is read again after this long
PASSWORD = "mail_password"  # with the start page's keys and tokens (iostart/keys.py)

SCHEMA = [
    # one message. key: what makes it the same message (its Message-ID, else its bytes); person_id: whose it is (NULL:
    # from an address nobody has, for a suite admin to give to someone); trusted: the mail server vouched for the
    # sender; kind: receipt, document, invite or other; tag: the +word of the address it went to; guess: what was read
    # off it (amount, day, merchant); status: waiting, filed or gone (let go); filed: where it went ({app, kind, id,
    # label, href, auto}); note: why it waits; retry_at: when a receipt is matched again
    """CREATE TABLE IF NOT EXISTS prt_inbox (
        id INT AUTO_INCREMENT PRIMARY KEY,
        msg_key CHAR(64) NOT NULL,
        received_at BIGINT NOT NULL,
        sent_at BIGINT NULL,
        from_addr VARCHAR(320) NOT NULL,
        from_name VARCHAR(200) NOT NULL DEFAULT '',
        subject VARCHAR(500) NOT NULL DEFAULT '',
        body MEDIUMTEXT NOT NULL,
        invite MEDIUMTEXT NULL,
        person_id INT NULL,
        trusted TINYINT(1) NOT NULL DEFAULT 0,
        kind VARCHAR(16) NOT NULL DEFAULT 'other',
        tag VARCHAR(32) NULL,
        guess TEXT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'waiting',
        filed TEXT NULL,
        note VARCHAR(300) NULL,
        retry_at BIGINT NULL,
        done_at BIGINT NULL,
        UNIQUE KEY idx_prt_inbox_key (msg_key),
        KEY idx_prt_inbox_person (person_id, status),
        KEY idx_prt_inbox_status (status, done_at)
    )""",
    # an attachment of one (a PDF, a picture, a calendar file), kept until the message goes
    """CREATE TABLE IF NOT EXISTS prt_inbox_files (
        id INT AUTO_INCREMENT PRIMARY KEY,
        item_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        mime VARCHAR(100) NOT NULL,
        size INT NOT NULL,
        data LONGBLOB NOT NULL,
        KEY idx_prt_inbox_files_item (item_id),
        FOREIGN KEY (item_id) REFERENCES prt_inbox(id) ON DELETE CASCADE
    )""",
]


class NotFiled(Exception):
    """Filing did not happen: the words say why (for the person, and kept as the item's note)."""

    def __init__(self, why: str, retry: bool = False):
        super().__init__(why)
        self.retry = retry


# ------------------------------------------------------------------ the mailbox's settings

def mailbox() -> dict:
    """{host, port, user, folder, on}: the mailbox the suite reads (the password is with the keys and tokens)."""
    return {"host": config.live("MAIL_HOST"), "port": config.live_int("MAIL_PORT", 993), "user": config.live("MAIL_USER"),
            "folder": config.live("MAIL_FOLDER", "INBOX"), "on": config.live_flag("MAIL_ON", True)}


def state() -> dict:
    try:
        return json.loads(db.get_state(STATE) or "{}")
    except ValueError:
        return {}


def _set_state(**kw) -> None:
    s = state()
    s.update(kw)
    db.set_state(STATE, json.dumps(s))


def ready() -> bool:
    m = mailbox()
    return bool(m["on"] and m["host"] and m["user"] and credentials.get(config.APP, PASSWORD))


def mailbox_public() -> dict:
    m = mailbox()
    return {**m, "passwordSet": credentials.is_set(config.APP, PASSWORD), "ready": ready(), "state": state(),
            "address": m["user"] if "@" in m["user"] else ""}


def set_mailbox(b: dict, by: str) -> dict:
    """{host?, port?, user?, folder?, on?, password? ('' keeps it; null clears it)}."""
    m = mailbox()
    for k in ("host", "user", "folder"):
        if k in b:
            v = str(b[k] or "").strip()
            if k == "host" and v and not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", v):
                raise Invalid("The mail server: a host name, like imap.gmail.com")
            m[k] = v[:320] or ("INBOX" if k == "folder" else "")
    if "port" in b:
        try:
            port = int(b["port"] or 993)
        except (TypeError, ValueError):
            raise Invalid("The port: a number, 993 for IMAP over TLS") from None
        if not 1 <= port <= 65535:
            raise Invalid("The port: a number, 993 for IMAP over TLS")
        m["port"] = port
    if "on" in b:
        m["on"] = bool(b["on"])
    for k in ("host", "port", "user", "folder", "on"):  # app.json's MAIL_*: kept with the suite's settings, shown on All settings
        suite_admin.set_setting(config.APP, "MAIL_" + k.upper(), m[k])
    if b.get("password"):
        credentials.put(config.APP, PASSWORD, str(b["password"]), by=by)
    elif "password" in b and b["password"] is None:
        credentials.put(config.APP, PASSWORD, "", by=by)
    return mailbox_public()


# ------------------------------------------------------------------ a person's own settings

def own(uid: int) -> dict:
    """{addresses: the other addresses they send from, auto: file what is clear by itself, calendar: the calendar
    invitations go to (None: their own first one)}."""
    v = users.get_value(uid, config.APP, "inbox", None) or {}
    return {"addresses": [a for a in v.get("addresses") or [] if isinstance(a, str)], "auto": bool(v.get("auto", True)),
            "calendar": v.get("calendar") if isinstance(v.get("calendar"), int) else None}


def set_own(uid: int, b: dict) -> dict:
    v = own(uid)
    if "addresses" in b:
        got = b["addresses"] if isinstance(b["addresses"], list) else re.split(r"[\s,;]+", str(b["addresses"] or ""))
        out = []
        for a in got:
            a = str(a or "").strip().lower()
            if not a:
                continue
            if not re.fullmatch(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}", a):
                raise Invalid(f"Not an email address: {a[:80]}")
            taken = _owner_of(a)
            if taken and taken != uid:
                raise Invalid(f"{a} is somebody else's address already")
            if a not in out:
                out.append(a)
        v["addresses"] = out[:20]
    if "auto" in b:
        v["auto"] = bool(b["auto"])
    if "calendar" in b:
        try:
            v["calendar"] = int(b["calendar"]) if b["calendar"] not in (None, "") else None
        except (TypeError, ValueError):
            raise Invalid("Which calendar: its id") from None
    users.set_value(uid, config.APP, "inbox", v)
    return own(uid)


def addresses() -> dict:
    """{address: account id} of every person: their account's email, and the other addresses they added."""
    out = {}
    for u in users.list_users():
        if u.get("email"):
            out.setdefault(u["email"].strip().lower(), u["id"])
    for u in users.list_users():
        for a in own(u["id"])["addresses"]:
            out.setdefault(a, u["id"])
    return out


_cards: dict = {}  # account id: (card id, read at, [addresses])


def card_addresses(uid: int) -> list:
    """The addresses on the person's own card in ioContact (the card their account is tied to), read as that person
    and kept for CARD_S seconds; [] without such a card or without ioContact. When ioContact does not answer, the ones
    read last."""
    try:
        cid = int(users.get_value(uid, CONTACTS, "me_contact_id") or 0)
    except (TypeError, ValueError):
        cid = 0
    if not cid or not links.available(CONTACTS):
        return []
    had = _cards.get(uid)
    if had and had[0] == cid and time.time() - had[1] < CARD_S:
        return had[2]
    try:
        with as_person(uid) as req:
            c = _ask(req, CONTACTS, f"/api/contacts/{cid}")
    except NotFiled:
        return had[2] if had and had[0] == cid else []
    out = []
    for e in c.get("emails") or []:
        a = str((e or {}).get("value") or "").strip().lower()
        if "@" in a and a not in out:
            out.append(a)
    _cards[uid] = (cid, time.time(), out)
    return out


def _owner_of(addr: str) -> int | None:
    """Whose address this is: an account's own or one they added first, then one on a person's own card in ioContact."""
    a = (addr or "").strip().lower()
    if not a:
        return None
    uid = addresses().get(a)
    if uid is not None:
        return uid
    for u in users.list_users():
        if not u.get("service") and a in card_addresses(u["id"]):
            return u["id"]
    return None


def claim() -> int:
    """Mail that waits as nobody's and is from an address somebody has by now (added since, or on their card): theirs."""
    n = 0
    for r in db.q("SELECT id, from_addr FROM prt_inbox WHERE status = 'waiting' AND person_id IS NULL LIMIT 50"):
        uid = _owner_of(r["from_addr"])
        if uid is not None:
            db.ex("UPDATE prt_inbox SET person_id = %s, note = NULL WHERE id = %s AND person_id IS NULL", (uid, r["id"]))
            by_itself(r["id"])
            n += 1
    return n


# ------------------------------------------------------------------ what a message is

_AMOUNT = r"(?:[$€£]|USD|EUR|GBP|CAD)?\s?(\d{1,3}(?:[,.\s]\d{3})*[.,]\d{2}|\d+[.,]\d{2})\s?(?:[$€£]|USD|EUR|GBP|CAD)?"
_TOTALS = re.compile(r"(?im)\b(grand total|order total|total charged|amount charged|amount paid|total paid|you paid|charged|"
                     r"payment amount|amount due|total due|total amount|balance paid|total)\b[^\n\d]{0,40}?" + _AMOUNT)
_RECEIPTISH = re.compile(r"(?i)\b(receipt|invoice|order\s+(?:confirmation|confirmed|#|no\.?|number)|your\s+order|purchase|"
                         r"payment\s+(?:received|confirmation|receipt)|you\s+paid|thanks\s+for\s+your\s+(?:order|purchase|payment)|"
                         r"bill|reçu|factura|rechnung|facture)\b")
_BEST = ("grand total", "order total", "total charged", "amount charged", "amount paid", "total paid", "you paid", "charged",
         "payment amount", "total amount", "balance paid", "amount due", "total due", "total")


def money(s: str) -> float | None:
    """'1,234.56', '1.234,56', '84.12' → the amount."""
    s = re.sub(r"\s", "", s or "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{2}", s) or re.fullmatch(r"\d+,\d{2}", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return round(v, 2) if 0 < v < 1_000_000 else None


def amount_of(text: str) -> float | None:
    """The amount a receipt is for: the line that says it best (grand total over subtotal), the last of its kind."""
    found = []
    for m in _TOTALS.finditer(text or ""):
        word = re.sub(r"\s+", " ", m.group(1).lower())
        if word == "total" and re.search(r"(?i)sub\s?-?$", (text[max(0, m.start() - 4):m.start()])):
            continue  # a subtotal
        v = money(m.group(2))
        if v is not None:
            found.append((_BEST.index(word) if word in _BEST else len(_BEST), m.start(), v))
    if not found:
        return None
    best = min(f[0] for f in found)
    return [f for f in found if f[0] == best][-1][2]


def _tag(to: list, own_addr: str) -> str | None:
    """The +word of the address the message went to (inbox+docs@…: docs), when it is the mailbox's address or the
    mailbox's address is not known."""
    base = (own_addr or "").lower()
    for a in to:
        m = re.fullmatch(r"([^@+]+)\+([a-z0-9-]{1,32})@(.+)", a)
        if m and (not base or f"{m.group(1)}@{m.group(3)}" == base):
            return m.group(2)
    return None


def merchant_of(m: dict) -> str:
    """Who the receipt is from: the original sender of a forwarded message, else the sender (their name, else their
    domain's first part)."""
    f = m.get("forwarded") or {}
    name, addr = (f.get("name"), f.get("from")) if f else (m.get("name"), m.get("from"))
    if name and "@" not in name:
        return name[:120]
    dom = (addr or "").rsplit("@", 1)[-1].split(".")
    dom = [d for d in dom if d not in ("mail", "email", "e", "info", "news", "notifications", "receipts", "orders", "shop", "store")]
    return (dom[-2] if len(dom) >= 2 else (dom[0] if dom else "")).capitalize()[:120]


def classify(m: dict, mailbox_addr: str = "") -> tuple[str, str | None, dict]:
    """(kind, tag, guess) of a parsed message (mail.parse)."""
    tag = _tag(m.get("to") or [], mailbox_addr)
    files = m.get("files") or []
    papers = [f for f in files if f["mime"] != "text/calendar"]
    words = f"{m.get('subject') or ''}\n{m.get('text') or ''}"
    amount = amount_of(words)
    day = dt.datetime.fromtimestamp(m.get("sent") or m.get("at") or time.time()).date().isoformat()
    guess = {"amount": amount, "day": day, "merchant": merchant_of(m), "title": clean_subject(m.get("subject") or "")}
    if m.get("invite") and re.search(r"(?im)^METHOD:\s*CANCEL", m["invite"]):
        guess["cancel"] = True
    if tag in TAGS:
        return TAGS[tag], tag, guess
    if m.get("invite") and not guess.get("cancel"):
        return "invite", tag, guess
    if amount is not None and _RECEIPTISH.search(words[:4000]):
        return "receipt", tag, guess
    if papers:
        return "document", tag, guess
    return "other", tag, guess


def clean_subject(s: str) -> str:
    s = str(s or "").strip()
    while True:
        t = re.sub(r"(?i)^\s*(fwd?|fw|re|tr|wg|aw)\s*:\s*", "", s)
        if t == s:
            break
        s = t
    return s.strip()[:200]


# ------------------------------------------------------------------ keeping a message

def keep(m: dict, mailbox_addr: str = "") -> int | None:
    """Keep a parsed message (mail.parse) as an Inbox item. Its id, or None when it was kept already."""
    if db.one("SELECT id FROM prt_inbox WHERE msg_key = %s", (m["key"],)):
        return None
    kind, tag, guess = classify(m, mailbox_addr)
    person = _owner_of(m["from"])
    note = None
    if person is None:
        note = "From an address nobody in the family has: give it to someone, or let it go"
    with db.tx():
        db.ex("INSERT INTO prt_inbox (msg_key, received_at, sent_at, from_addr, from_name, subject, body, invite, person_id, trusted, kind, tag, guess, note) "
              "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
              (m["key"], int(m.get("at") or time.time()), int(m["sent"]) if m.get("sent") else None, m["from"] or "(no sender)",
               m.get("name") or "", (m.get("subject") or "")[:500], m.get("text") or "", m.get("invite"), person,
               1 if m.get("trusted") else 0, kind, (tag or "")[:32] or None, json.dumps(guess), note))
        iid = db.one("SELECT LAST_INSERT_ID() AS id")["id"]
        for f in m.get("files") or []:
            db.ex("INSERT INTO prt_inbox_files (item_id, name, mime, size, data) VALUES (%s, %s, %s, %s, %s)",
                  (iid, f["name"][:255], f["mime"], len(f["data"]), f["data"]))
    return iid


def keep_too_large(uid: str, mailbox_addr: str = "") -> None:
    key = f"too-large-{mailbox_addr}-{uid}"
    keep({"key": hashlib.sha256(key.encode()).hexdigest(), "from": "", "name": "", "subject": "(a message too large to read)",
          "text": f"A message larger than {mail.MAX_MESSAGE >> 20} MB was left in the mailbox, marked read.", "to": [],
          "files": [], "invite": None, "trusted": False, "at": time.time(), "sent": None}, mailbox_addr)


# ------------------------------------------------------------------ who sees what

def _row(iid: int) -> dict:
    r = db.one("SELECT * FROM prt_inbox WHERE id = %s", (int(iid),))
    if not r:
        raise LookupError("No such message")
    return r


def may_see(u: dict, r: dict) -> bool:
    if r["person_id"] is not None:
        return r["person_id"] == u["id"]
    return users.is_suite_admin(u)


def item(u: dict, iid: int) -> dict:
    r = _row(iid)
    if not may_see(u, r):
        raise LookupError("No such message")
    return r


def _files(iid: int) -> list:
    return db.q("SELECT id, name, mime, size FROM prt_inbox_files WHERE item_id = %s ORDER BY id", (iid,))


def public(r: dict, full: bool = False) -> dict:
    try:
        guess = json.loads(r.get("guess") or "{}")
    except ValueError:
        guess = {}
    try:
        filed = json.loads(r["filed"]) if r.get("filed") else None
    except ValueError:
        filed = None
    out = {"id": r["id"], "from": r["from_addr"], "name": r["from_name"], "subject": r["subject"] or "(no subject)",
           "received": r["received_at"], "sent": r["sent_at"], "kind": r["kind"], "tag": r["tag"], "trusted": bool(r["trusted"]),
           "status": r["status"], "filed": filed, "note": r["note"], "guess": guess, "person": r["person_id"],
           "snippet": re.sub(r"\s+", " ", (r.get("body") or ""))[:160]}
    if full:
        out["text"] = r.get("body") or ""
        out["files"] = [{"id": f["id"], "name": f["name"], "mime": f["mime"], "size": f["size"],
                         "url": f"api/inbox/{r['id']}/files/{f['id']}"} for f in _files(r["id"])]
        out["invite"] = bool(r.get("invite"))
        if out["person"] is not None:
            p = users.get(out["person"])
            out["personName"] = (p or {}).get("displayName") or ""
    return out


def listing(u: dict, show: str = "waiting", limit: int = 200) -> dict:
    """{items, waiting, unclaimed}: the person's own messages (a suite admin: also those nobody's yet), the newest first.
    show: waiting, or done (filed and let go)."""
    admin = users.is_suite_admin(u)
    who = "(person_id = %s" + (" OR person_id IS NULL)" if admin else ")")
    status = "status = 'waiting'" if show != "done" else "status IN ('filed', 'gone')"
    rows = db.q(f"SELECT * FROM prt_inbox WHERE {who} AND {status} ORDER BY received_at DESC, id DESC LIMIT %s", (u["id"], max(1, min(int(limit), 500))))
    return {"items": [public(r) for r in rows], **counts(u)}


def counts(u: dict) -> dict:
    admin = users.is_suite_admin(u)
    mine = db.one("SELECT count(*) AS n FROM prt_inbox WHERE person_id = %s AND status = 'waiting'", (u["id"],))["n"]
    nobody = db.one("SELECT count(*) AS n FROM prt_inbox WHERE person_id IS NULL AND status = 'waiting'")["n"] if admin else 0
    return {"waiting": int(mine) + int(nobody), "unclaimed": int(nobody)}


def file_content(u: dict, iid: int, fid: int) -> tuple[bytes, str, str]:
    item(u, iid)
    r = db.one("SELECT name, mime, data FROM prt_inbox_files WHERE id = %s AND item_id = %s", (int(fid), int(iid)))
    if not r:
        raise LookupError("No such file")
    return bytes(r["data"]), r["mime"], r["name"]


def give(u: dict, iid: int, person) -> dict:
    """A suite admin gives a message from an unknown address to someone (it is theirs from then on, to file)."""
    r = item(u, iid)
    if r["person_id"] is not None:
        raise Invalid("This message is somebody's already")
    p = users.get(int(person)) if str(person or "").isdigit() else users.find(str(person or ""))
    if not p or p.get("service"):
        raise Invalid("No such person")
    db.ex("UPDATE prt_inbox SET person_id = %s, note = NULL WHERE id = %s", (p["id"], r["id"]))
    return public(_row(r["id"]))


def let_go(u: dict, iid: int) -> dict:
    r = item(u, iid)
    db.ex("UPDATE prt_inbox SET status = 'gone', done_at = %s, retry_at = NULL WHERE id = %s", (int(time.time()), r["id"]))
    return public(_row(r["id"]))


def bring_back(u: dict, iid: int) -> dict:
    """Back to waiting (a message let go by mistake, or filed and to be filed elsewhere as well)."""
    r = item(u, iid)
    db.ex("UPDATE prt_inbox SET status = 'waiting', done_at = NULL WHERE id = %s", (r["id"],))
    return public(_row(r["id"]))


def remove(u: dict, iid: int) -> None:
    r = item(u, iid)
    db.ex("DELETE FROM prt_inbox WHERE id = %s", (r["id"],))


# ------------------------------------------------------------------ filing, as the person

class _AsPerson:
    """What links.as_viewer reads of a request: the sign-in to pass on (made for the moment), and no host of its own."""

    def __init__(self, token: str):
        self.cookies = {sessions.COOKIE: token}
        self.headers = {}


@contextlib.contextmanager
def as_person(uid: int):
    """A sign-in of this person's for SESSION_S seconds at most, ended when the block ends; the record of what it
    changes says it came by email, through the start page."""
    from iosuite_shared import host
    p = users.get(uid)
    if not p:
        raise NotFiled("That account is gone")
    token = sessions.create(uid, config.APP, "email", {"client": "email", "user_agent": "ioSuite inbox"})
    shared_db.ex("UPDATE ios_sessions SET expires_at = %s WHERE token_hash = %s", (int(time.time()) + SESSION_S, sessions._hash(token)))
    app_token = host.CURRENT.set(config.APP)
    try:
        with stamp.job("by email", client="import", user=p):
            yield _AsPerson(token)
    finally:
        host.CURRENT.reset(app_token)
        sessions.end(token)


def _ask(req, app: str, path: str, params: dict = None, body: dict = None, data: bytes = None, content_type: str = None, method: str = None):
    name = catalog.name_of(app)
    if not links.available(app):
        raise NotFiled(f"{name} is not part of the suite")
    try:
        return links.as_viewer(req, app, path, params, body, method=method, timeout=30, user_agent="ioSuite inbox",
                               data=data, content_type=content_type)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail")
        except (ValueError, AttributeError):
            detail = None
        if e.code in (401, 403):
            raise NotFiled(detail if isinstance(detail, str) else f"{name} does not let this account in") from None
        raise NotFiled(detail if isinstance(detail, str) else f"{name} answered {e.code}") from None
    except links.Unreachable:
        raise NotFiled(f"{name} is not reachable right now", retry=True) from None


def _href(kind: str, iid) -> str | None:
    h = (catalog.ITEMS.get(kind) or {}).get("href")
    return h.replace("{id}", str(iid)) if h else None


def _papers(iid: int) -> list:
    return db.q("SELECT id, name, mime, data FROM prt_inbox_files WHERE item_id = %s AND mime != 'text/calendar' ORDER BY id", (iid,))


def as_pdf(r: dict) -> bytes:
    """The message itself as a PDF (a receipt that came as the mail's text, with no file attached)."""
    from fpdf import FPDF
    pdf = FPDF(format="letter", unit="mm")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, 18)
    pdf.set_creator("ioSuite")
    pdf.add_page()

    def t(s):
        s = str(s or "").translate({0x2019: "'", 0x2018: "'", 0x201c: '"', 0x201d: '"', 0x2013: "-", 0x2014: "-", 0x2026: "...", 0x20ac: "EUR "})
        return s.encode("latin-1", "replace").decode("latin-1")
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 6.5, t(r["subject"] or "(no subject)"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    when = dt.datetime.fromtimestamp(r["sent_at"] or r["received_at"]).strftime("%Y-%m-%d %H:%M")
    pdf.multi_cell(0, 5, t(f"From {r['from_name'] or ''} <{r['from_addr']}> · {when}".replace("·", "-")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, t((r.get("body") or "")[:60000]), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def matches(req, r: dict) -> list:
    """The person's ioMoney transactions the receipt could be for: money out of its amount, a few days around it."""
    g = json.loads(r.get("guess") or "{}")
    if not g.get("amount"):
        return []
    day = dt.date.fromisoformat(g.get("day") or dt.date.today().isoformat())
    got = _ask(req, "iomoney", "/api/transactions", {"amount": f"{g['amount']:.2f}", "flow": "out", "limit": 20,
                                                    "start": (day + dt.timedelta(days=AROUND[0])).isoformat(),
                                                    "end": (day + dt.timedelta(days=AROUND[1])).isoformat()})
    return [{"id": t.get("id"), "day": t.get("day") or t.get("date"), "amount": t.get("amount"), "merchant": t.get("merchant") or t.get("payee") or "",
             "account": t.get("account") if isinstance(t.get("account"), str) else (t.get("account") or {}).get("name") if isinstance(t.get("account"), dict) else t.get("accountName"),
             "receipts": len(t.get("receipts") or [])}
            for t in (got or {}).get("items", [])]


_PLAIN = {"the", "inc", "llc", "ltd", "co", "corp", "store", "shop", "online", "com", "www", "pos", "purchase", "payment", "card", "debit"}


def _pick(cands: list, merchant: str, subject: str = "") -> dict | None:
    """The one transaction it is: the only one, else the only one whose payee is named in the merchant or the
    subject ("CORNER BAKERY #12" for a mail "Your receipt from Corner Bakery")."""
    if len(cands) == 1:
        return cands[0]
    said = " " + re.sub(r"[^a-z0-9]+", " ", f"{merchant or ''} {subject or ''}".lower()) + " "
    named = []
    for c in cands:
        words = [w for w in re.findall(r"[a-z]{3,}", str(c.get("merchant") or "").lower()) if w not in _PLAIN]
        if words and f" {words[0]} " in said:
            named.append(c)
    return named[0] if len(named) == 1 else None


def to_money(req, r: dict, tid=None) -> dict:
    g = json.loads(r.get("guess") or "{}")
    if tid is None:
        cands = matches(req, r)
        if not g.get("amount"):
            raise NotFiled("No amount found on this receipt: pick the transaction")
        if not cands:
            raise NotFiled(f"No transaction of {g['amount']:.2f} around {g.get('day')} yet (it may still come from the bank)", retry=True)
        hit = _pick(cands, g.get("merchant"), r["subject"])
        if hit is None:
            raise NotFiled(f"{len(cands)} transactions of {g['amount']:.2f} around then: pick the one")
        tid = hit["id"]
    papers = _papers(r["id"])
    p = next((f for f in papers if f["mime"] == "application/pdf"), None) or next((f for f in papers if f["mime"].startswith("image/")), None)
    if p is not None:
        data, mime, name = bytes(p["data"]), p["mime"], p["name"]
    else:
        data, mime, name = as_pdf(r), "application/pdf", (clean_subject(r["subject"]) or "receipt")[:80] + ".pdf"
    _ask(req, "iomoney", f"/api/transactions/{int(tid)}/receipts", {"name": name}, data=data, content_type=mime)
    t = _ask(req, "iomoney", f"/api/transactions/{int(tid)}")
    label = " · ".join(str(x) for x in (t.get("merchant") or g.get("merchant") or "", t.get("day") or "", t.get("amount") if t.get("amount") is not None else "") if x != "")
    return {"app": "iomoney", "kind": "transaction", "id": int(tid), "label": label or "a transaction", "href": _href("transaction", tid)}


def to_docs(req, r: dict, title: str = None) -> dict:
    papers = _papers(r["id"])
    if not papers:
        raise NotFiled("Nothing attached to keep in ioDocs")
    g = json.loads(r.get("guess") or "{}")
    when = dt.datetime.fromtimestamp(r["sent_at"] or r["received_at"]).date().isoformat()
    d = _ask(req, "iodocs", "/api/documents", body={"title": (title or g.get("title") or clean_subject(r["subject"]) or "From the inbox")[:200],
                                                   "visibility": "private", "notes": f"By email from {r['from_name'] or r['from_addr']}, {when}."})
    for f in papers:
        ext = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp",
               "image/heic": "heic", "image/heif": "heif"}.get(f["mime"], "")
        _ask(req, "iodocs", f"/api/documents/{d['id']}/files", {"ext": ext} if ext else None, data=bytes(f["data"]), content_type=f["mime"])
    return {"app": "iodocs", "kind": "document", "id": d["id"], "label": d.get("title") or "a document", "href": _href("document", d["id"])}


def calendars(req) -> list:
    """The calendars the person may add to: [{id, name, mine, color}]."""
    got = _ask(req, "iocalendar", "/api/calendars")
    return [{"id": c["id"], "name": c["name"], "mine": bool(c.get("mine")), "color": c.get("color")}
            for c in (got or {}).get("items", []) if c.get("writable") and (c.get("kind") or "events") == "events"]


def to_calendar(req, r: dict, cid=None, uid: int = None) -> dict:
    ics = r.get("invite")
    if not ics:
        f = db.one("SELECT data FROM prt_inbox_files WHERE item_id = %s AND mime = 'text/calendar' ORDER BY id LIMIT 1", (r["id"],))
        ics = bytes(f["data"]).decode("utf-8", "replace") if f else None
    if not ics:
        raise NotFiled("No invitation in this message")
    cals = calendars(req)
    if not cals:
        raise NotFiled("No calendar this account may add to")
    want = cid if cid is not None else (own(uid)["calendar"] if uid else None)
    cal = next((c for c in cals if want is not None and c["id"] == int(want)), None)
    if cal is None:
        if cid is not None:
            raise NotFiled("That calendar is not one this account may add to")
        cal = next((c for c in cals if c["mine"]), cals[0])
    got = _ask(req, "iocalendar", f"/api/calendars/{cal['id']}/import", {"replace": "true"}, data=ics.encode(), content_type="text/calendar")
    if not (got or {}).get("created") and not (got or {}).get("updated"):
        raise NotFiled("; ".join((got or {}).get("errors") or []) or "ioCalendar found no event in the invitation")
    m = re.search(r"(?im)^SUMMARY[^:]*:(.*)$", ics)
    return {"app": "iocalendar", "kind": "calendar", "id": cal["id"], "label": f"{(m.group(1).strip() if m else 'the event')[:80]} in {cal['name']}",
            "href": None}


def file_it(req, r: dict, to: str, auto: bool = False, **kw) -> dict:
    """File the message where `to` says (money, docs, calendar), asked as the person req signs in. The item as it is now."""
    where = {"money": "receipt", "docs": "document", "calendar": "invite"}.get(to, to)
    if where == "receipt":
        filed = to_money(req, r, kw.get("transaction"))
    elif where == "document":
        filed = to_docs(req, r, kw.get("title"))
    elif where == "invite":
        filed = to_calendar(req, r, kw.get("calendar"), r["person_id"])
    else:
        raise Invalid("Where to: money, docs or calendar")
    filed["auto"] = auto
    filed["url"] = push.link(filed["app"], filed["href"] or "")
    db.ex("UPDATE prt_inbox SET status = 'filed', filed = %s, note = NULL, retry_at = NULL, done_at = %s WHERE id = %s",
          (json.dumps(filed), int(time.time()), r["id"]))
    return public(_row(r["id"]))


def file_by_hand(request, u: dict, iid: int, b: dict) -> dict:
    """The person files one from the Inbox page: as themselves (their own sign-in passed on)."""
    r = item(u, iid)
    if r["person_id"] is None:
        raise Invalid("Give it to someone first: it is from an address nobody has")
    if r["person_id"] != u["id"]:
        raise LookupError("No such message")
    try:
        return file_it(request, r, str(b.get("to") or ""), transaction=b.get("transaction"), calendar=b.get("calendar"), title=b.get("title"))
    except NotFiled as e:
        raise Invalid(str(e)) from None


# ------------------------------------------------------------------ the job

def by_itself(iid: int) -> None:
    """File a message without a tap, when everything says where (see the top); otherwise leave it waiting, with why."""
    r = _row(iid)
    if r["status"] != "waiting" or r["person_id"] is None:
        return
    g = json.loads(r.get("guess") or "{}")
    why = None
    if r["kind"] == "other":
        why = "Kept for you to file" if r["tag"] in ("inbox", "hold") else None
    elif not r["trusted"]:
        why = "Not filed by itself: the mail server could not vouch for the sender"
    elif not own(r["person_id"])["auto"]:
        why = None
    elif r["kind"] == "invite" and g.get("cancel"):
        why = "A cancellation: take the event off the calendar yourself"
    else:
        try:
            with as_person(r["person_id"]) as req:
                done = file_it(req, r, r["kind"], auto=True)
            _tell(r, f"Filed: {done['subject']}", f"{_where(done['filed'])}")
            return
        except NotFiled as e:
            retry = e.retry and time.time() - r["received_at"] < RETRY_DAYS * 86400
            db.ex("UPDATE prt_inbox SET note = %s, retry_at = %s WHERE id = %s",
                  (str(e)[:300], int(time.time()) + RETRY_S if retry else None, r["id"]))
            if not retry and not r["retry_at"]:
                _tell(r, f"In your inbox: {r['subject'] or '(no subject)'}", str(e))
            return
        except Exception as e:  # noqa: BLE001 - kept for a tap; the log says what broke
            log.warning("inbox: filing %s: %s", r["id"], e)
            why = "Could not file it by itself: file it by hand"
    db.ex("UPDATE prt_inbox SET note = %s WHERE id = %s", (why, r["id"]))
    if r["retry_at"] is None:
        _tell(r, f"In your inbox: {r['subject'] or '(no subject)'}", why or "Mail you sent to the suite waits for you to file it")


def _where(filed: dict) -> str:
    return {"iomoney": "On the transaction ", "iodocs": "In ioDocs: ", "iocalendar": "Added "}.get(filed.get("app"), "") + (filed.get("label") or "")


def _tell(r: dict, title: str, body: str) -> None:
    try:
        push.notify(r["person_id"], "inbox", title, body, url=push.link(config.APP, "#/inbox"), once=f"inbox-{r['id']}-{r['status']}-{bool(r['retry_at'])}")
    except Exception as e:  # noqa: BLE001 - the Inbox page shows it either way
        log.debug("inbox: notification: %s", e)


def check(limit: int = BATCH) -> dict:
    """Read the mailbox now: keep what is new, file what can be filed by itself. {read, kept} (MailError when the
    mailbox could not be read: the state says so too)."""
    m = mailbox()
    pw = credentials.get(config.APP, PASSWORD)
    if not (m["host"] and m["user"] and pw):
        raise mail.MailError("The mailbox is not set up: Inbox › Mailbox")
    kept, read = [], 0
    try:
        with mail.Mailbox(m["host"], m["port"], m["user"], pw, m["folder"]) as box:
            for uid, raw in box.unread(limit):
                read += 1
                if raw is None:
                    keep_too_large(uid, m["user"])
                else:
                    try:
                        iid = keep(mail.parse(raw), m["user"])
                    except Exception as e:  # noqa: BLE001 - one odd message must not stop the rest; it stays unread
                        log.warning("inbox: could not read message %s: %s", uid, e)
                        continue
                    if iid:
                        kept.append(iid)
                box.seen(uid)
    except mail.MailError as e:
        _set_state(checkedAt=int(time.time()), error=str(e))
        raise
    except (OSError, EOFError) as e:
        _set_state(checkedAt=int(time.time()), error=f"The connection broke ({e})")
        raise mail.MailError(f"The connection broke ({e})") from None
    _set_state(checkedAt=int(time.time()), error=None, read=read)
    for iid in kept:
        by_itself(iid)
    return {"read": read, "kept": len(kept)}


def retry_due() -> int:
    n = 0
    for r in db.q("SELECT id FROM prt_inbox WHERE status = 'waiting' AND retry_at IS NOT NULL AND retry_at <= %s LIMIT 50", (int(time.time()),)):
        by_itself(r["id"])
        n += 1
    return n


def purge() -> None:
    db.ex("DELETE FROM prt_inbox WHERE status IN ('filed', 'gone') AND done_at < %s", (int(time.time()) - KEEP_DAYS * 86400,))


def tick() -> None:
    purge()
    if ready() and time.time() - (state().get("checkedAt") or 0) >= EVERY:
        try:
            check()
        except mail.MailError as e:
            log.info("inbox: %s", e)
    claim()
    retry_due()


def job():
    """The look at the mailbox, as one of the copy's jobs (INBOX_LOOP=0 leaves it off: the tests call tick())."""
    from iosuite_shared import chores
    if not config.INBOX_LOOP:
        return None
    return chores.start(tick, every_s=TICK, first_s=TICK, name="inbox", app=config.APP, quiet=True,
                        title="Read the suite's mailbox and file what came in")


def person_data(uid: int, remove_: bool) -> int:
    n = db.one("SELECT count(*) AS n FROM prt_inbox WHERE person_id = %s", (uid,))["n"]
    if remove_:
        db.ex("DELETE FROM prt_inbox WHERE person_id = %s", (uid,))
    return int(n)

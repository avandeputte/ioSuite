"""The emergency card: what someone helping you needs to know, on one wallet-size card to print, cut out and fold.

Front: your name, date of birth, blood type, allergies (severe ones first), conditions and organ donation. Back: the
medicines you take (those marked "on the card"), your doctors and the people to call, and your health insurance.

What is kept here (hlt_emergency, one row per person, their own like everything in ioHealth): blood type, conditions,
organ donor, a note, and which doctors and people to call (ioContact contact ids) and which insurance papers (ioDocs
document ids) go on the card. The rest is read when the card is shown: the allergies and medicines from this app
(meds.py), the date of birth from what the phone sent (hlt_characteristics), and the contacts and documents from
ioContact and ioDocs, asked as the viewer (iosuite_shared.links.App), so the card only ever shows what the person may
see there. A contact or a paper they no longer see is left off the card and marked in the editor. Nothing to set up:
both apps are found in the suite's list; without one of them, that part of the card is just not offered.
"""
import datetime as dt
import json
import logging
import re

from fastapi import APIRouter, Request
from iosuite_shared import links
from iosuite_shared.access import json_body
from iosuite_shared.errors import Invalid

from iohealth import access, db, meds, webapi
from iohealth.auth import me, uid as uid_of

log = logging.getLogger("iohealth.emergency")
router = APIRouter()

CONTACTS, DOCS = "iocontact", "iodocs"
TIMEOUT = 5
MAX_PICKS = 4             # doctors, people to call, insurance papers: each, what fits on a card
BLOOD_TYPES = ("", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
DONOR = ("", "yes", "no")
# what a health insurance paper looks like in ioDocs, to offer it first in the picker
HEALTH_WORDS = re.compile(r"health|medic|dental|vision|\bcare\b|hospital|kranken|mutuelle|mutualit|ziekenfonds|zorg|\bnhs\b|\behic\b", re.I)
HEALTH_KINDS = ("insurance", "membership", "medical")

_contacts = links.App(CONTACTS, asker="ioHealth", timeout=TIMEOUT, no_role="No role in ioContact", own_word=False)
_docs = links.App(DOCS, asker="ioHealth", timeout=TIMEOUT, no_role="No role in ioDocs", own_word=False)


# ------------------------------------------------------------------ what is kept

def _ids(v, what: str) -> list:
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        raise Invalid(f"{what} is a list")
    out = []
    for x in v:
        try:
            i = int(x.get("id") if isinstance(x, dict) else x)
        except (TypeError, ValueError, AttributeError):
            raise Invalid(f"{what}: ids are numbers") from None
        if i > 0 and i not in out:
            out.append(i)
    if len(out) > MAX_PICKS:
        raise Invalid(f"At most {MAX_PICKS} {what.lower()} fit on the card")
    return out


def blood_of(v) -> str:
    """A blood type as the phone sends it ("A+", "aPositive", "HKBloodTypeABNegative") as the card writes it; '' else."""
    t = re.sub(r"^(HK)?BloodType", "", str(v or "").strip(), flags=re.I).lower()
    t = t.replace("positive", "+").replace("negative", "-").replace(" ", "").upper()
    return t if t in BLOOD_TYPES else ""


def kept(uid: int) -> dict:
    r = db.qd("SELECT blood_type, organ_donor, conditions, notes, doctors, contacts, documents FROM hlt_emergency WHERE user_id = %s", (uid,))
    r = r[0] if r else {}

    def ids(k):
        try:
            v = json.loads(r.get(k) or "[]")
        except (TypeError, ValueError):
            return []
        return [int(x) for x in v if isinstance(x, int)] if isinstance(v, list) else []
    return {"bloodType": r.get("blood_type") or "", "organDonor": r.get("organ_donor") or "", "conditions": r.get("conditions") or "",
            "notes": r.get("notes") or "", "doctors": ids("doctors"), "contacts": ids("contacts"), "documents": ids("documents")}


def save(uid: int, b: dict) -> dict:
    now = kept(uid)
    blood = str(b.get("bloodType", now["bloodType"]) or "").strip().upper()
    if blood not in BLOOD_TYPES:
        raise Invalid("Blood type is one of A+, A-, B+, B-, AB+, AB-, O+ or O-")
    donor = str(b.get("organDonor", now["organDonor"]) or "").strip().lower()
    if donor not in DONOR:
        raise Invalid("Organ donor is yes, no or not said")
    texts = {}
    for k, n in (("conditions", 600), ("notes", 600)):
        v = str(b.get(k, now[k]) or "").strip()
        if len(v) > n:
            raise Invalid(f"{k.capitalize()}: at most {n} characters")
        texts[k] = v
    picks = {k: _ids(b[k], k.capitalize()) if k in b else now[k] for k in ("doctors", "contacts", "documents")}
    db.ex("INSERT INTO hlt_emergency (user_id, blood_type, organ_donor, conditions, notes, doctors, contacts, documents) "
          "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE blood_type = VALUES(blood_type), "
          "organ_donor = VALUES(organ_donor), conditions = VALUES(conditions), notes = VALUES(notes), doctors = VALUES(doctors), "
          "contacts = VALUES(contacts), documents = VALUES(documents)",
          (uid, blood, donor, texts["conditions"], texts["notes"], json.dumps(picks["doctors"]), json.dumps(picks["contacts"]),
           json.dumps(picks["documents"])))
    return kept(uid)


# ------------------------------------------------------------------ from the other apps

def _phone(c: dict) -> str:
    phones = sorted(c.get("phones") or [], key=lambda p: (not p.get("pref"), p.get("position") or 0))
    return (phones[0].get("value") or "") if phones else (c.get("phone") or "")


def _contact(c: dict) -> dict:
    name = (c.get("fn") or "").strip() or (c.get("org") or "").strip()
    return {"id": c.get("id"), "name": name, "org": c.get("org") if (c.get("org") or "") != name else "",
            "title": c.get("title") or "", "phone": _phone(c)}


def _document(d: dict) -> dict:
    fields = [{"name": str(f.get("name") or ""), "value": str(f.get("value") or "")} for f in d.get("fields") or []
              if isinstance(f, dict) and f.get("value")]
    return {"id": d.get("id"), "title": d.get("title") or "", "kind": d.get("kind") or "", "kindLabel": d.get("kindLabel") or "",
            "issuer": d.get("issuer") or "", "number": d.get("number") or "", "expiresOn": d.get("expiresOn"),
            "fields": fields[:3]}


def _each(request, app: links.App, path: str, ids: list, shape) -> tuple:
    """([items, each {found: bool}], problem or None): the items the viewer still sees in the other app; one they no
    longer see is {id, found: false}."""
    if not ids:
        return [], None
    if not app.enabled():
        return [{"id": i, "found": False} for i in ids], f"{app.name} is not part of the suite"
    out, problem = [], None
    for i in ids:
        try:
            out.append({**shape(app.ask(request, path.format(i))), "found": True})
        except links.Unavailable as e:
            if e.status in (403, 404):
                out.append({"id": i, "found": False})
                if e.status == 403:
                    problem = str(e)
            else:
                return [{"id": i, "found": None} for i in ids], str(e)
    return out, problem


def card(request: Request) -> dict:
    """Everything on the card, and what is kept to make it."""
    u = me(request)
    uid, loc = int(u["id"]), webapi.location(request)
    k = kept(uid)
    today = dt.datetime.now(loc).date()
    chars = {n: v for n, v in db.q("SELECT name, value FROM hlt_characteristics WHERE user_id = %s AND name IN ('dateOfBirth', 'bloodType')", (uid,))}
    born = str(chars.get("dateOfBirth") or "")[:10] or None
    phone_blood = blood_of(chars.get("bloodType"))
    meds_now = [m for m in meds.medicines(uid) if m["onCard"] and meds.active_on(m, today)]
    doctors, p1 = _each(request, _contacts, "/api/contacts/{}", k["doctors"], _contact)
    people, p2 = _each(request, _contacts, "/api/contacts/{}", k["contacts"], _contact)
    papers, p3 = _each(request, _docs, "/api/documents/{}", k["documents"], _document)
    problems = [{"app": a, "message": p} for a, p in ((CONTACTS, p1 or p2), (DOCS, p3)) if p]
    return {"person": {"name": u.get("displayName") or u.get("name"), "born": born},
            "bloodType": k["bloodType"] or phone_blood,
            "organDonor": k["organDonor"], "conditions": k["conditions"], "notes": k["notes"],
            "allergies": meds.allergies(uid),
            "medicines": [{"id": m["id"], "name": m["name"], "dose": m["dose"], "times": m["times"], "days": m["days"], "asNeeded": m["asNeeded"],
                           "reason": m["reason"]} for m in meds_now],
            "doctors": doctors, "contacts": people, "documents": papers, "kept": k, "problems": problems,
            "apps": {CONTACTS: {"on": _contacts.enabled(), "url": _contacts.url()}, DOCS: {"on": _docs.enabled(), "url": _docs.url()}},
            "printed": today.isoformat()}


def find_contacts(request: Request, q: str) -> list:
    got = _contacts.ask(request, "/api/contacts", {"q": q, "limit": 20})
    return [_contact(c) for c in got.get("items", [])]


def find_documents(request: Request, q: str) -> list:
    """The papers the viewer sees in ioDocs that are theirs (or, with words, any they see), health insurance first."""
    uid = uid_of(request)
    params = {"q": q, "limit": 40} if q else {"person": str(uid), "limit": 100}
    try:
        got = _docs.ask(request, "/api/documents", params)
    except links.Unavailable as e:
        if e.status != 404 or q:
            raise
        got = {"items": []}  # not in ioDocs' family: nothing of theirs there
    items = [_document(d) for d in got.get("items", [])]
    for d in items:
        d["suggested"] = d["kind"] in HEALTH_KINDS and bool(HEALTH_WORDS.search(f"{d['title']} {d['issuer']}"))
    items.sort(key=lambda d: (not d["suggested"], d["kind"] not in HEALTH_KINDS, d["title"].lower()))
    return items


# ------------------------------------------------------------------ routes

def _unavailable(e: links.Unavailable):
    from fastapi import HTTPException
    raise HTTPException(e.status if e.status in (403, 404) else 502, str(e))


@router.get("/api/emergency", dependencies=[access.signed_in])
def get_card(request: Request):
    """Your emergency card: {person: {name, born}, bloodType, organDonor, conditions, notes, allergies, medicines,
    doctors, contacts, documents (each {found: false} when you no longer see it), kept (what is saved), problems,
    apps}. tz."""
    return card(request)


@router.put("/api/emergency", dependencies=[access.signed_in])
async def put_card(request: Request):
    """{bloodType?, organDonor? ('yes', 'no' or ''), conditions?, notes?, doctors?: [ioContact ids], contacts?:
    [ioContact ids], documents?: [ioDocs ids]}: the fields given; the others stay. The saved fields."""
    return save(uid_of(request), await json_body(request))


@router.get("/api/emergency/contacts", dependencies=[access.signed_in])
def get_contacts(request: Request, q: str = ""):
    """Contacts you see in ioContact whose name or details have these words, to pick a doctor or someone to call."""
    try:
        return {"items": find_contacts(request, q.strip()[:100])}
    except links.Unavailable as e:
        _unavailable(e)


@router.get("/api/emergency/documents", dependencies=[access.signed_in])
def get_documents(request: Request, q: str = ""):
    """Papers you see in ioDocs: yours (q: any with these words), health insurance first ({suggested: true})."""
    try:
        return {"items": find_documents(request, q.strip()[:100])}
    except links.Unavailable as e:
        _unavailable(e)

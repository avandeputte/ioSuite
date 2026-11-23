"""ioContact's part of a person's estate planning PDF (iosuite_shared.estate): their own card (the one linked to their
account, "This is me") and their closest family with how to reach each one: spouse or partner, parents, siblings and
children, the ones the card names and the ones its family implies (her sibling's parent is her parent), and the
emergency contacts it names. Every address book counts: it is a suite admin or the person asking."""
from iosuite_shared import users as shared_users

from iocontact import config, db, model
from iocontact import relations as rel

# the relations that go in, in this order, under these headings
CLOSE = (("Spouse or partner", ("spouse", "partner")),
         ("Parents", ("parent", "step_parent")),
         ("Siblings", ("sibling", "half_sibling", "step_sibling")),
         ("Children", ("child", "step_child")),
         ("Emergency contacts", ("emergency",)))
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def _date(b: dict | None) -> str:
    if not b:
        return ""
    y, m, d = b.get("year"), b.get("month"), b.get("day")
    if m and d:
        return f"{MONTHS[m - 1]} {d}{f', {y}' if y else ''}"
    if m:
        return f"{MONTHS[m - 1]} {y or ''}".strip()
    return str(y or "")


def _address(a: dict) -> str:
    city = " ".join(x for x in (a.get("city"), a.get("region"), a.get("postcode")) if x)
    return ", ".join(x for x in (a.get("pobox"), a.get("ext"), a.get("street"), city, a.get("country")) if x)


def _lab(x: dict, kind: str) -> str:
    return f"{kind} ({x['label']})" if x.get("label") else kind


def _rows(c: dict, everything: bool) -> list:
    rows = [[_lab(p, "Phone"), p["value"]] for p in c["phones"]]
    rows += [[_lab(e, "Email"), e["value"]] for e in c["emails"]]
    rows += [[_lab(a, "Address"), _address(a)] for a in c["addresses"]]
    rows.append(["Birthday", _date(c["birthday"])])
    if everything:
        rows += [[d["label"] or "Date", _date(d)] for d in c["dates"]]
        if c["maiden"]:
            rows.append(["Maiden name", c["maiden"]])
        rows += [[_lab(u, "Web"), u["value"]] for u in c["urls"]]
    work = ", ".join(x for x in (c["title"], c["org"]) if x)
    if work:
        rows.append(["Work", work])
    return rows


def data(user_id: int) -> list:
    me_id = shared_users.get_value(user_id, config.APP, "me_contact_id")
    me = model.full(int(me_id)) if me_id else None
    if not me:
        return [{"title": "Contact details and family", "order": 10,
                 "intro": "No ioContact card is linked to this person. A suite admin links it under Settings › People › Family "
                          "(or the person marks their own card “This is me” in ioContact); their relatives come from that card."}]
    stated = [r for r in me["relations"] if r["relatedId"] or r["relatedName"]]
    books = [r["id"] for r in db.q("SELECT id FROM con_address_books")]
    implied = [r for r in model.implied_relations(me["id"], books)
               if not any(s["relatedId"] == r["relatedId"] for s in stated)]
    people = model.load(list(dict.fromkeys(r["relatedId"] for r in stated + implied if r["relatedId"])))
    by_id = {p["id"]: p for p in people}
    items = [{"title": me["fn"] or "Their card", "subtitle": "Their own card", "rows": _rows(me, True), "notes": me["notes"] or ""}]
    for heading, types in CLOSE:
        for r in stated + implied:
            if r["type"] not in types:
                continue
            p = by_id.get(r["relatedId"])
            label = r.get("typeLabel") or rel.label(r["type"], r.get("relatedGender"))
            sub = label
            if r.get("implied"):
                sub += f" (through {r['viaFn']})"
            if p:
                items.append({"title": p["fn"] or "?", "subtitle": sub, "rows": _rows(p, False)})
            else:
                items.append({"title": r["relatedName"] or r.get("relatedFn") or "?", "subtitle": sub,
                              "rows": [["Contact", "Not in ioContact: no details"]]})
    return [{"title": "Contact details and family", "order": 10,
             "intro": "Their own card in ioContact and their closest family: spouse or partner, parents, siblings and children, "
                      "with how to reach each one.", "items": items}]

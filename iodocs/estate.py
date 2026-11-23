"""ioDocs's part of a person's estate planning PDF (iosuite_shared.estate): the papers that are theirs (they are one
of its people, whatever its visibility: a suite admin or the person asking) and the household's (nobody's in
particular, shared with the family: the house insurance, the deed), with their scans. Archived ones (an old passport)
stay out. Wills and legal papers come first, then insurance, property and the rest."""
import datetime as dt
import json

from iosuite_shared import family as suite_family

from iodocs import db, files, model

ORDER = ("legal", "insurance", "property", "tax", "vehicle", "marriage", "birth", "passport", "passport_card", "id_card",
         "residence", "visa", "driver_license", "membership", "education", "medical", "other")


def _ids(user_id: int) -> tuple[list[int], set[int]]:
    """(their documents, the household's)."""
    theirs = [r["doc_id"] for r in db.q("SELECT p.doc_id FROM doc_people p JOIN doc_documents d ON d.id = p.doc_id "
                                        "WHERE p.user_id = %s AND d.archived = 0", (user_id,))]
    house = {r["id"] for r in db.q("SELECT d.id FROM doc_documents d WHERE d.archived = 0 AND d.visibility = 'family' "
                                   "AND NOT EXISTS (SELECT 1 FROM doc_people p WHERE p.doc_id = d.id)")}
    return theirs, house


def _day(v) -> str:
    return v.strftime("%B %-d, %Y") if isinstance(v, (dt.date, dt.datetime)) else ""


def data(user_id: int) -> list:
    theirs, house = _ids(user_id)
    ids = list(dict.fromkeys(theirs + sorted(house)))
    if not ids:
        return []
    docs = db.q(f"SELECT * FROM doc_documents WHERE id IN ({db.marks(len(ids))})", ids)
    rank = {k: i for i, k in enumerate(ORDER)}
    docs.sort(key=lambda d: (rank.get(d["kind"], 99), d["id"] in house, (d["title"] or "").lower()))
    people = model.people_of([d["id"] for d in docs])
    names = {m["id"]: m["displayName"] for m in suite_family.everyone()}
    items = []
    for d in docs:
        try:
            own = model.own_fields(json.loads(d["fields"] or "[]"))
        except (ValueError, model.Invalid):
            own = []
        with_ = [names.get(u, f"#{u}") for u in people.get(d["id"], []) if u != user_id]
        rows = [["Kind", model.kind_label(d["kind"])], ["Number", d["number"]], ["Issued by", d["issuer"]],
                ["Country", d["country"]], ["Issued", _day(d["issued_on"])], ["Expires", _day(d["expires_on"])],
                ["Also for", ", ".join(with_)]]
        rows += [[f["name"], f["value"]] for f in own]
        items.append({"title": d["title"], "subtitle": "The household’s" if d["id"] in house else "Theirs",
                      "rows": [[k, str(v)] for k, v in rows if v not in (None, "")], "notes": d["notes"] or "",
                      "files": [{"ref": f"{d['id']}-{f['id']}", "name": f["name"], "mime": f["mime"]} for f in files.listed(d["id"])]})
    return [{"title": "Documents", "order": 20,
             "intro": "Their papers in ioDocs and the household’s, with the details printed on them. The scans follow at the end.",
             "items": items}]


def file(user_id: int, ref: str) -> tuple[bytes, str, str]:
    """A scan of one of the documents data() lists. LookupError for anything else."""
    try:
        doc_id, fid = (int(x) for x in ref.split("-", 1))
    except ValueError:
        raise LookupError(ref)
    theirs, house = _ids(user_id)
    if doc_id not in theirs and doc_id not in house:
        raise LookupError(ref)
    try:
        return files.content(doc_id, fid)
    except model.NotFound:
        raise LookupError(ref)

"""The family: one list of the people in it for the whole suite, kept in the Shared ioSuite database and managed by suite
admins in Settings › People › Family. ioCalendar tags events with them, ioTask gives them tasks, and every app shows
a member the same way: the same colour, the same initials and the same face.

Everyone with an account people use is in the family unless a suite admin took them out (an "admin" account or a
guest is not a person of the family). A member may have a colour picked for them; without one, they get the next
colour of PALETTE by their place in the list (by display name), so two members never look alike. A member is linked
to their card in ioContact (the account's "me" contact, the one ioContact itself calls "This is me") and to their
person in ioPix's People (the account's person in photos, as on the People pane); their face is that person's face
in ioPix, else their ioContact card's photo.

Kept per account in ios_user_data (app '', name 'family'): {"out": true} for one taken out, {"color": "#rrggbb"}
for a picked colour. The two links are the values ioPix and ioContact keep for the account already.
"""
import re
import time

from iosuite_shared import db, users
from iosuite_shared.errors import Invalid

KEY = "family"
SUITE = ""                # ios_user_data.app for what belongs to the whole suite
PHOTO_APP, CONTACT_APP = "iopix", "iocontact"
PHOTO_KEY, CONTACT_KEY = "person", "me_contact_id"
PALETTE = ["#1e8e3e", "#e0426a", "#1a73e8", "#e8710a", "#8e44d6", "#0b8a9e", "#b5452f", "#4b53c7", "#e8a100", "#5f6b7a"]
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
TTL = 30  # seconds an app keeps the list before it reads it again (a change in another app shows within this)

_cache: dict = {"at": 0.0, "list": None, "all": None}


def initials(name: str) -> str:
    """The first letter of the first and of the last word ("Emma Smith": ES; "Emma": E), as every app shows them."""
    p = (name or "?").split()
    return ((p[0][0] if p else "?") + (p[-1][0] if len(p) > 1 else "")).upper()


def _values() -> dict:
    """{user_id: {name: value}} of the family values and the two links, in one query."""
    out: dict = {}
    for r in db.q("SELECT user_id, app, name, value FROM ios_user_data WHERE (app = %s AND name = %s) OR (app = %s AND name = %s) OR (app = %s AND name = %s)",
                  (SUITE, KEY, PHOTO_APP, PHOTO_KEY, CONTACT_APP, CONTACT_KEY)):
        out.setdefault(r["user_id"], {})[(r["app"], r["name"])] = db.json_load(r["value"])
    return out


def everyone() -> list[dict]:
    """Every account people use, in the family or not, by display name: {id, name, displayName, inFamily, initials,
    color, colorPicked, photoPerson, contactId, hasFace}. The colour of one out of the family is the one it would have."""
    now = time.monotonic()
    if _cache["all"] is not None and now - _cache["at"] <= TTL:
        return _cache["all"]
    vals = _values()
    out = []
    for u in users.list_users():
        v = vals.get(u["id"], {})
        f = v.get((SUITE, KEY)) if isinstance(v.get((SUITE, KEY)), dict) else {}
        pp, cid = v.get((PHOTO_APP, PHOTO_KEY)), v.get((CONTACT_APP, CONTACT_KEY))
        out.append({"id": u["id"], "name": u["name"], "displayName": u["displayName"], "inFamily": not f.get("out"),
                    "initials": initials(u["displayName"]), "color": f.get("color") or None, "colorPicked": bool(f.get("color")),
                    "photoPerson": int(pp) if pp else None, "contactId": int(cid) if cid else None, "hasFace": bool(pp or cid)})
    out.sort(key=lambda m: (m["displayName"].lower(), m["id"]))
    # the members without a picked colour take the palette's colours in turn, skipping the ones picked for others
    taken = {m["color"].lower() for m in out if m["inFamily"] and m["color"]}
    free = [c for c in PALETTE if c.lower() not in taken] or PALETTE
    i = 0
    for m in out:
        if not m["color"]:
            m["color"] = free[i % len(free)]
            if m["inFamily"]:
                i += 1
    _cache.update(at=now, all=out, list=[m for m in out if m["inFamily"]])
    return out


def members() -> list[dict]:
    """The family, by display name (see everyone())."""
    everyone()
    return _cache["list"]


def ids() -> set[int]:
    return {m["id"] for m in members()}


def in_family(uid: int) -> bool:
    return int(uid) in ids()


def forget() -> None:
    _cache.update(at=0.0, list=None, all=None)


def get(uid: int) -> dict | None:
    return next((m for m in everyone() if m["id"] == int(uid)), None)


def update(uid: int, body: dict) -> dict:
    """Change one account's place in the family: inFamily (bool), color ("#rrggbb"; None or "" goes back to the
    palette's), contactId (an ioContact card id; None unlinks), photoPerson (a person in ioPix's People; None unlinks).
    LookupError for no such account, ValueError for a bad value."""
    u = users.get(int(uid))
    if not u or u.get("service"):
        raise LookupError("No such user")
    cur = users.get_value(u["id"], SUITE, KEY, {}) or {}
    cur = cur if isinstance(cur, dict) else {}
    if "inFamily" in body:
        if body["inFamily"]:
            cur.pop("out", None)
        else:
            cur["out"] = True
    if "color" in body:
        c = (body.get("color") or "").strip()
        if c and not COLOR_RE.match(c):
            raise ValueError("A colour is #rrggbb")
        if c:
            cur["color"] = c.lower()
        else:
            cur.pop("color", None)
    users.set_value(u["id"], SUITE, KEY, cur or None)
    for field, app, key in (("contactId", CONTACT_APP, CONTACT_KEY), ("photoPerson", PHOTO_APP, PHOTO_KEY)):
        if field in body:
            v = body.get(field)
            if v in (None, "", 0):
                users.set_value(u["id"], app, key, None)
            else:
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    raise ValueError(f"{field} is a number")
                users.set_value(u["id"], app, key, v)
    forget()
    return get(u["id"])


def public(m: dict) -> dict:
    """What an app serves for a member."""
    return {k: m[k] for k in ("id", "name", "displayName", "initials", "color", "hasFace")}


# ---- faces, read from the other apps as the reader (iosuite_shared.links)
def face(reader: str, uid: int) -> tuple[bytes, str]:
    """The member's face: their person's in ioPix, else their ioContact card's photo. LookupError when there is none."""
    from iosuite_shared import links
    import urllib.error
    m = get(uid)
    if not m:
        raise LookupError("No such member")
    tries = []
    if m["photoPerson"]:
        tries.append((PHOTO_APP, f"/face/{m['photoPerson']}"))
    if m["contactId"]:
        tries.append((CONTACT_APP, f"/api/contacts/{m['contactId']}/photo"))
    for app, path in tries:
        if not links.available(app):
            continue
        try:
            with links.get(reader, app, path, accept="image/*") as r:
                return r.read(), r.headers.get("Content-Type") or "image/jpeg"
        except (RuntimeError, urllib.error.URLError, OSError):
            continue
    raise LookupError("No face")


def contacts(reader: str, q: str = "") -> dict:
    """Cards in ioContact to link a member to: {available, items: [{id, fn, iopixPersonId}], error?}."""
    from iosuite_shared import links
    from urllib.parse import quote
    if not links.available(CONTACT_APP):
        return {"available": False, "items": []}
    try:
        r = links.json(reader, CONTACT_APP, f"/api/contacts?limit=30&q={quote(q or '')}")
    except Exception as e:  # noqa: BLE001  ioContact is away
        return {"available": True, "items": [], "error": f"ioContact did not answer: {e}"}
    items = r.get("items") if isinstance(r, dict) else []
    return {"available": True, "items": [{"id": c["id"], "fn": c.get("fn") or "", "iopixPersonId": c.get("iopixPersonId")}
                                         for c in items or [] if isinstance(c, dict) and c.get("id")]}


def contact(reader: str, cid: int) -> dict | None:
    """One card's name in ioContact ({id, fn}), or None."""
    from iosuite_shared import links
    if not links.available(CONTACT_APP):
        return None
    try:
        c = links.json(reader, CONTACT_APP, f"/api/contacts/{int(cid)}", timeout=4)
        return {"id": int(cid), "fn": c.get("fn") or ""} if isinstance(c, dict) else None
    except Exception:  # noqa: BLE001
        return None


class Tags:
    """Family members as tags on an app's items (ioCalendar's events, ioTask's tasks): the family as this app sees it
    (the suite's list, less the accounts with no role in the app), and a member tag kept in the item itself as an
    iCalendar CATEGORIES value with the member's display name, so the apps that sync show it, and a category typed
    there with a member's name (or account name, in any case) tags the item here too. An item's other categories stay
    as they are. `users` is the app's own accounts module (all_users, ROLES); each app keeps one Tags, with its own
    short-lived copy of the list (`ttl` seconds)."""

    def __init__(self, users, ttl: float = 30):
        self._users, self.ttl = users, ttl
        self._cache: dict = {"at": 0.0, "list": None}

    def in_family(self, uid: int) -> bool:
        return in_family(uid)

    def family(self) -> list[dict]:
        """[{id, name, displayName, initials, color, hasFace}] of the suite's family members who may use this app, by display name."""
        now = time.monotonic()
        if self._cache["list"] is None or now - self._cache["at"] > self.ttl:
            if self.ttl <= 0:
                forget()
            here = {u["id"] for u in self._users.all_users() if u.get("role") in self._users.ROLES}
            self._cache.update(at=now, list=[public(m) for m in members() if m["id"] in here])
        return self._cache["list"]

    def forget(self) -> None:
        self._cache.update(at=0.0, list=None)
        forget()

    @staticmethod
    def _keys(m: dict) -> set[str]:
        return {m["displayName"].strip().lower(), m["name"].strip().lower()}

    def of(self, categories: list[str] | None, fam: list[dict] | None = None) -> list[dict]:
        """The members an item is tagged with, from its categories (in the order of the family list)."""
        if not categories:
            return []
        have = {str(c).strip().lower() for c in categories}
        return [m for m in (fam if fam is not None else self.family()) if self._keys(m) & have]

    def ids_of(self, categories: list[str] | None, fam: list[dict] | None = None) -> list[int]:
        return [m["id"] for m in self.of(categories, fam)]

    def find(self, ref, fam: list[dict] | None = None) -> dict:
        """A member by id, account name or display name. ValueError when there is no such member."""
        fam = fam if fam is not None else self.family()
        s = str(ref.get("id") if isinstance(ref, dict) else ref).strip()
        for m in fam:
            if s.isdigit() and m["id"] == int(s):
                return m
        for m in fam:
            if s.lower() in self._keys(m):
                return m
        raise Invalid(f"No family member '{ref}'. The family: " + ", ".join(m["displayName"] for m in fam))

    def resolve(self, refs, fam: list[dict] | None = None) -> list[dict]:
        """Member refs (ids or names, or one comma-separated string) as members, each once."""
        if refs is None:
            return []
        if isinstance(refs, (str, int)):
            refs = [x for x in str(refs).split(",") if x.strip()]
        out = []
        for r in refs:
            m = self.find(r, fam)
            if m not in out:
                out.append(m)
        return out

    def fold(self, data: dict, current_categories: list[str] | None = None) -> dict:
        """JSON fields with `members` (ids or names) turned into categories: the member tags replace the old member tags,
        and the categories that are not a member's name stay (those given in data, else the item's current ones)."""
        if "members" not in data:
            return data
        fam = self.family()
        want = self.resolve(data.get("members") or [], fam)
        base = data["categories"] if "categories" in data else (current_categories or [])
        member_keys = set().union(*(self._keys(m) for m in fam)) if fam else set()
        cats = [c for c in (base or []) if str(c).strip().lower() not in member_keys]
        out = {k: v for k, v in data.items() if k != "members"}
        out["categories"] = cats + [m["displayName"] for m in want]
        return out

    def public(self, ms: list[dict]) -> list[dict]:
        return [public(m) for m in ms]

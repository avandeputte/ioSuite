"""What ioPix hangs on the suite's sign-in (iosuite_shared.app: hooks.setup): the digiKam person an account is linked
to, which is the face badge on the sign-in screen. It is kept as the "person" value of the account's iopix data.
"""
from iosuite_shared import users as shared
from iosuite_shared.errors import Invalid

APP = "iopix"


def setup(auth) -> None:
    auth.decorate = decorate
    auth.on_update = on_update


def decorate(u):
    """The user dict ioPix serves: the shared fields plus the linked person tag."""
    if u is None:
        return None
    u = dict(u)
    u["person"] = shared.get_value(u["id"], APP, "person")
    return u


def person_tag(tag_id) -> bool:
    """Is this a person tag in the index (a tag under People with digiKam's person property)?"""
    if not tag_id:
        return True
    from iopix.runtime import db
    con = db()
    try:
        r = con.execute("SELECT person FROM tags WHERE id = ?", (int(tag_id),)).fetchone()
        return bool(r and r[0])
    finally:
        con.close()


def set_person(user_id: int, tag_id):
    """Link the account to a digiKam person tag (None unlinks). The caller checks the tag is a person."""
    shared.set_value(user_id, APP, "person", int(tag_id) if tag_id else None)
    shared.invalidate()


def on_update(user_id: int, body: dict):
    """A change to an account may carry {person}: the account's face badge (Settings › People › People sets it through
    the suite admin routes; an account's own PATCH /api/auth/me passes only its name and email)."""
    if "person" in body:
        if not person_tag(body["person"]):
            raise Invalid("That tag is not a person")
        set_person(user_id, body["person"])

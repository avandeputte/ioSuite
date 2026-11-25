"""What ioContact hangs on its sign-in (iosuite_shared.app calls setup once, as the app's Auth is made): the dict the
app works with for an account, made of the shared one."""
from iosuite_shared import users as shared

from iocontact.config import APP


def row_of(u):
    """The dict the app works with, from a shared account (with its role here): the shared fields as they are (what the
    shared routes serve: displayName, passwordless, suiteAdmin, ...) plus the row names ioContact's own code uses and
    the account's "me" contact. Tolerant of partial dicts (the sign-in picker's entries carry no role or email)."""
    if u is None:
        return None
    out = dict(u)
    me_id = shared.get_value(u["id"], APP, "me_contact_id")
    out.update(display_name=u["displayName"] if u.get("displayName") and u["displayName"] != u["name"] else None,
               email=u.get("email") or None, role=u.get("role", "viewer"), passwordless=bool(u.get("passwordless")),
               me_contact_id=me_id, meContactId=me_id, suite_admin=bool(u.get("suiteAdmin")), suiteAdmin=bool(u.get("suiteAdmin")))
    return out


def setup(auth) -> None:
    auth.decorate = row_of

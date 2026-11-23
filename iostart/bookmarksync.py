"""What the bookmark sync of the browser extension and the iPhone app (iostart/bookmarkext.py) and the files in and
out (iostart/bookmarkfiles.py) share: who is asking, and the tree as the items of a file.

A sync client signs in with HTTP Basic: the account's name and an app password (Settings › Account, or the one the
sign-in flow for apps makes, iostart/appsignin.py), kept in the Shared ioSuite database like every app password. A
client gets the account's tree (their own bookmarks and the shared ones, iostart/bookmarks.py); changing it takes a
member, editor or admin, and the shared bookmarks only change for an admin of the start page, as in the Bookmarks page.
"""
from fastapi import HTTPException, Request
from iosuite_shared import users

from iostart import bookmarks
from iostart.auth import auth

REALM = 'Basic realm="ioStart bookmarks", charset="UTF-8"'


def user(request: Request, write: bool = False) -> dict:
    """The account asking, or 401 (with the Basic challenge that makes a client send its password) / 403."""
    u = auth.current_user(request)
    if not u:
        raise HTTPException(401, "Sign in with your ioStart name and an app password.", headers={"WWW-Authenticate": REALM})
    if write and not users.is_member(u):
        raise HTTPException(403, "This account can read the bookmarks, not change them.")
    bookmarks.as_user(u)
    return u


# ------------------------------------------------------------------ the tree as a file's items

def items(t: bookmarks.Tree | None = None, pid=None) -> list[dict]:
    t = t or bookmarks.Tree()
    return [{"type": "folder", "id": r["id"], "title": r["name"], "children": items(t, r["id"])} if r["folder"] else
            {"type": "bookmark", "id": r["id"], "title": r["name"], "url": r["url"], "tags": bookmarks.tags_of(r)} for r in t.children(pid)]

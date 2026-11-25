"""The app's own writable state: favorites, app-side albums, what it wrote down for itself (STATE), users, the
pending-edit and tag-manager queues, and (through analysis.py and consistency.py,
which share the database) the analysis results.

Everything lives in the viewer's own database (appdb.py: MariaDB or MySQL, since v1.113 nothing
else), never in digiKam's database. Photos are referenced by digiKam image id; the file hash is
stored alongside so entries could be re-matched if digiKam ever renumbers its images.
"""
import contextvars
import logging
import threading
import time

from iopix.data import appdb
from iopix.digikam.dkdb import in_chunks

rev = 0  # bumped on every write so cached query results can be invalidated
lock = threading.Lock()
_kept = (-1, {})  # (stamp it was read at, {key: value}); the app's own notes, read on every poll and every POST
log = logging.getLogger("iopix.data.state")

# What the app writes down for itself (pix_state): not settings, which are the suite's one home for them (declared
# in iopix/app.json, in the Shared ioSuite database, read as they are now with config.live). {key: (default, what)}
STATE = {
    "digikam_closed_until": ("0", "epoch seconds until which the admin vouched that digiKam is closed (dbsync writes without checking)"),
    "face_vectors_built": ("sface", "the face vector model the stored vectors were made with (a change rebuilds them)"),
    "near_dups_gen": ("", "the generation the near-duplicate groups were computed for; empty: compute again"),
    "recent_tags": ("[]", "the last tags used in the Edit panel, newest first (at most 12)"),
}
_unknown_keys = set()  # logged once each


def _known(key: str):
    if key not in STATE and key not in _unknown_keys:
        _unknown_keys.add(key)
        log.warning("%r is not in state.STATE (add it there with its default)", key)


def connect():
    """The viewer database (see appdb.py); rows answer to names and indexes."""
    return appdb.connect(timeout=10)


def init():
    """Open the viewer database and create or migrate every table (appdb.init: never raises; the viewer starts
    without a database and says so)."""
    appdb.init()


def write(fn):
    """Run fn(con) inside the one writer lock and commit; returns what fn returned and moves `rev` on (polls notice the change)."""
    global rev
    with lock, appdb.write_lock:  # one writer in the process, the jobs included: a request never waits out SQLite's busy timeout
        con = connect()
        try:
            out = fn(con)
            con.commit()
        finally:
            con.close()
        rev += 1
        return out


# who is asking, set per request by the server (an account of the Shared ioSuite database, or None for visitors, MCP and jobs): private
# albums are seen only by their owner, so every album read below goes through _visible()
viewer = contextvars.ContextVar("album_viewer", default=None)


def _uid(user=...):
    u = viewer.get() if user is ... else user
    return int(u["id"]) if u and u.get("id") is not None else None


def _visible(user=..., alias: str = "") -> tuple:
    """SQL condition (and its parameters) for the albums this user may see: shared ones, and their own private ones."""
    a, uid = (alias + ".") if alias else "", _uid(user)
    if uid is None:
        return f"{a}shared = 1", []
    return f"({a}shared = 1 OR {a}owner_id = ?)", [uid]


def summary(user=...) -> dict:
    """Favorites, the viewer's albums (with size and cover), people groups and saved searches the user may see, in one call for the UI."""
    vis, vp = _visible(user, "a")
    owner = _favorites_of(user)
    con = connect()
    try:
        return {
            "favorites": [] if owner is None else [r[0] for r in con.execute("SELECT photo_id FROM pix_favorite_photos WHERE user_id = ? ORDER BY added_at DESC, photo_id", (owner,))],
            "albums": [dict(r) for r in con.execute(
                "SELECT a.id, a.name, a.created_at AS created, a.owner_id, a.shared, count(i.photo_id) AS n, "
                "(SELECT photo_id FROM pix_album_photos WHERE album_id = a.id ORDER BY added_at, photo_id LIMIT 1) AS cover "
                f"FROM pix_albums a LEFT JOIN pix_album_photos i ON i.album_id = a.id WHERE {vis} "
                "GROUP BY a.id, a.name, a.created_at, a.owner_id, a.shared ORDER BY a.created_at DESC", vp)],
            # smart albums: a saved filter query string, listed with the albums and evaluated live
            "searches": [dict(r) for r in con.execute("SELECT id, name, query, created_at AS created FROM pix_saved_searches ORDER BY created_at DESC")],
        }
    finally:
        con.close()


# ---- favorites: every account keeps its own. While there are no accounts there is one list (user 0). That list goes
# to one account, the first admin who uses the app once accounts exist; every other account starts with none.
_taken = False  # the one list is known to be empty (taken, or never there): not looked at again until it is added to


def _favorites_of(user=...):
    """Whose favorites this user sees and changes: their account's; with no accounts, the one list (0); None for a
    visitor who is not signed in while accounts exist (no favorites)."""
    u = viewer.get() if user is ... else user
    uid = _uid(u)
    if uid is not None:
        if not _taken:
            take_favorites(u)
        return uid
    from iopix import users  # lazy: users -> auth -> ... -> state
    return None if users.any_users() else 0


def take_favorites(user):
    """The one list everyone shared becomes this account's own, when it is an admin's and the list is still there:
    the favorites of before stay with one account, not with all of them. Nobody else gets a copy."""
    global _taken
    from iopix import users
    if not user or user.get("id") is None or not users.is_admin(user):
        return
    uid = int(user["id"])

    def go(c):
        n = c.execute("SELECT count(*) FROM pix_favorite_photos WHERE user_id = 0").fetchone()[0]
        if n:
            c.execute("INSERT OR IGNORE INTO pix_favorite_photos (user_id, photo_id, hash, added_at) "
                      "SELECT ?, photo_id, hash, added_at FROM pix_favorite_photos WHERE user_id = 0", (uid,))
            c.execute("DELETE FROM pix_favorite_photos WHERE user_id = 0")
        return n
    n = write(go)
    _taken = True
    if n:
        log.info("favorites are kept per account from now on: the %d there were are now those of %s", n, user.get("name") or uid)


def set_favorites(items: list, on: bool, user=...):
    """items: [(photo_id, hash)], for this user (the one asking, by default). False for a visitor, who has none."""
    global _taken
    owner = _favorites_of(user)
    if owner is None:
        return False
    if owner == 0:
        _taken = False  # the one list again (no accounts): the first admin there will be takes it
    now = int(time.time())
    if on:
        write(lambda c: c.executemany("INSERT OR IGNORE INTO pix_favorite_photos (user_id, photo_id, hash, added_at) VALUES (?,?,?,?)", [(owner, i, h, now) for i, h in items]))
    else:
        write(lambda c: c.executemany("DELETE FROM pix_favorite_photos WHERE user_id = ? AND photo_id = ?", [(owner, i) for i, _ in items]))
    return True


# ---- People groups (the People page's sections; digiKam is not touched)

def people_groups() -> list:
    """[{id, name, members: [tag ids in order]}] in the order chosen."""
    con = connect()
    try:
        groups = [{"id": r[0], "name": r[1], "members": []} for r in con.execute("SELECT id, name FROM pix_people_groups ORDER BY position, id")]
        by = {g["id"]: g for g in groups}
        for gid, tid in con.execute("SELECT group_id, tag_id FROM pix_people_group_members ORDER BY group_id, position, tag_id"):
            if gid in by:
                by[gid]["members"].append(tid)
        return groups
    finally:
        con.close()


def create_people_group(name: str) -> int:
    """A new people group at the end of the order; returns its id."""
    def go(c):
        pos = (c.execute("SELECT max(position) FROM pix_people_groups").fetchone()[0] or 0) + 1
        return c.execute("INSERT INTO pix_people_groups (name, position, created_at) VALUES (?,?,?)", (name, pos, int(time.time()))).lastrowid
    return write(go)


def update_people_group(group_id: int, name: str = None, members: list = None) -> bool:
    """Rename a group and/or set its members (tag ids, in order; replaces the list). False if there is no such group."""
    def go(c):
        if not c.execute("SELECT 1 FROM pix_people_groups WHERE id = ?", (group_id,)).fetchone():
            return False
        if name is not None:
            c.execute("UPDATE pix_people_groups SET name = ? WHERE id = ?", (name, group_id))
        if members is not None:
            c.execute("DELETE FROM pix_people_group_members WHERE group_id = ?", (group_id,))
            seen = list(dict.fromkeys(int(t) for t in members))
            c.executemany("INSERT INTO pix_people_group_members (group_id, tag_id, position) VALUES (?,?,?)", [(group_id, t, k) for k, t in enumerate(seen)])
        return True
    return write(go)


def delete_people_group(group_id: int):
    """Remove a people group and its memberships (the people themselves are digiKam tags and stay)."""
    def go(c):
        c.execute("DELETE FROM pix_people_group_members WHERE group_id = ?", (group_id,))
        c.execute("DELETE FROM pix_people_groups WHERE id = ?", (group_id,))
    write(go)


def order_people_groups(ids: list):
    """Store this order of group ids as their positions (the UI's drag order)."""
    write(lambda c: c.executemany("UPDATE pix_people_groups SET position = ? WHERE id = ?", [(k, int(i)) for k, i in enumerate(ids)]))


def create_album(name: str, owner_id: int = None, shared: bool = True) -> int:
    """A new viewer album; returns its id. owner_id None: nobody's, visible to all; shared False: the owner's alone."""
    return write(lambda c: c.execute("INSERT INTO pix_albums (name, created_at, owner_id, shared) VALUES (?,?,?,?)",
                                      (name, int(time.time()), owner_id, 1 if shared else 0)).lastrowid)


def album(album_id: int) -> dict:
    """{id, name, owner_id, shared}, or None; no visibility check (callers decide what the user may do)."""
    con = connect()
    try:
        r = con.execute("SELECT id, name, owner_id, shared FROM pix_albums WHERE id = ?", (int(album_id),)).fetchone()
        return {"id": r[0], "name": r[1], "owner_id": r[2], "shared": bool(r[3])} if r else None
    finally:
        con.close()


def set_album_sharing(album_id: int, shared: bool, owner_id: int = None):
    """Shared: everyone sees it. Private: only owner_id does (the user who made it private)."""
    write(lambda c: c.execute("UPDATE pix_albums SET shared = ?, owner_id = COALESCE(?, owner_id) WHERE id = ?",
                               (1 if shared else 0, owner_id, int(album_id))))


def rename_album(album_id: int, name: str):
    """Set the album's name (the caller has checked the user may)."""
    write(lambda c: c.execute("UPDATE pix_albums SET name = ? WHERE id = ?", (name, album_id)))


def delete_album(album_id: int):
    """Remove a viewer album and its memberships; the photos are untouched."""
    def run(c):
        c.execute("DELETE FROM pix_album_photos WHERE album_id = ?", (album_id,))
        c.execute("DELETE FROM pix_albums WHERE id = ?", (album_id,))
    write(run)


def create_search(name: str, query: str) -> int:
    """Save a filter query string under a name; returns its id."""
    return write(lambda c: c.execute("INSERT INTO pix_saved_searches (name, query, created_at) VALUES (?,?,?)", (name, query, int(time.time()))).lastrowid)


def rename_search(search_id: int, name: str):
    """Set a saved search's name."""
    write(lambda c: c.execute("UPDATE pix_saved_searches SET name = ? WHERE id = ?", (name, search_id)))


def delete_search(search_id: int):
    """Remove a saved search."""
    write(lambda c: c.execute("DELETE FROM pix_saved_searches WHERE id = ?", (search_id,)))


def set_album_items(album_id: int, items: list, on: bool):
    """Add (on) or remove the photos to an album. items: [(photo id, digiKam hash)]; the hash lets a renumbered photo be found again (index.remap)."""
    now = int(time.time())
    if on:
        write(lambda c: c.executemany("INSERT OR IGNORE INTO pix_album_photos VALUES (?,?,?,?)",
                                       [(album_id, i, h, now) for i, h in items]))
    else:
        write(lambda c: c.executemany("DELETE FROM pix_album_photos WHERE album_id = ? AND photo_id = ?",
                                       [(album_id, i) for i, _ in items]))


def _state_stamp() -> tuple:
    """Changes on every write: rev for this process, and for writes by another one (the stdio MCP server
    shares this database) a few-second clock, since the server offers no cheap change marker."""
    return rev, int(time.time() / 5)


def get_state(key: str, default: str = None) -> str:
    """What the app wrote down for itself. These are tiny and read on every status poll and every POST, so the whole
    table is cached and re-read only after a write. No default: STATE's own."""
    global _kept
    _known(key)
    if default is None:
        default = STATE[key][0] if key in STATE else ""
    stamp, values = _kept
    now = _state_stamp()  # taken before the query: a write racing with it makes the next call reload
    if stamp != now:
        con = connect()
        try:
            values = dict(con.execute("SELECT name, value FROM pix_state").fetchall())
        except Exception:
            return default
        finally:
            con.close()
        _kept = (now, values)
    return values.get(key, default)




def set_state(key: str, value: str):
    """Write one of them down (a known key, as a string); the UI and the index pick it up on their next poll."""
    _known(key)
    write(lambda c: c.execute("INSERT OR REPLACE INTO pix_state (name, value) VALUES (?,?)", (key, value)))


# ---- the viewer's own photo sets as id lists: favorites and album contents live in this database (SQLite or MySQL),
# while the index is a separate SQLite file, so query.py inlines them as `id IN (...)` instead of joining
def favorite_ids(user=...) -> list:
    """The ids of this user's favorite photos (the one asking, by default)."""
    owner = _favorites_of(user)
    if owner is None:
        return []
    con = connect()
    try:
        return [r[0] for r in con.execute("SELECT photo_id FROM pix_favorite_photos WHERE user_id = ?", (owner,))]
    finally:
        con.close()


def album_item_ids(album_ids: list) -> list:
    """The photos in these albums, counting only the albums the current user may see."""
    if not album_ids:
        return []
    vis, vp = _visible(alias="a")
    con = connect()
    try:
        return [r[0] for r in in_chunks(con, "SELECT i.photo_id FROM pix_album_photos i JOIN pix_albums a ON a.id = i.album_id "
                                             f"WHERE i.album_id IN ({{ids}}) AND {vis}", map(int, album_ids), params_after=tuple(vp))]
    finally:
        con.close()


def albums_of(photo_id: int) -> list:
    """Ids of the viewer albums holding this photo that the current user may see."""
    vis, vp = _visible(alias="a")
    con = connect()
    try:
        return [r[0] for r in con.execute(
            f"SELECT i.album_id FROM pix_album_photos i JOIN pix_albums a ON a.id = i.album_id WHERE i.photo_id = ? AND {vis}", [photo_id] + vp)]
    finally:
        con.close()


def is_favorite(photo_id: int, user=...) -> bool:
    """Whether the photo is one of this user's favorites."""
    owner = _favorites_of(user)
    if owner is None:
        return False
    con = connect()
    try:
        return con.execute("SELECT 1 FROM pix_favorite_photos WHERE user_id = ? AND photo_id = ?", (owner, photo_id)).fetchone() is not None
    finally:
        con.close()


def album_id_by_name(name_or_id) -> int:
    """The id of the viewer album with this name (any letter case) or id, among those the current user may see; None if none."""
    vis, vp = _visible()
    con = connect()
    try:
        r = con.execute(f"SELECT id FROM pix_albums WHERE (lower(name) = lower(?) OR id = ?) AND {vis}", [str(name_or_id), str(name_or_id)] + vp).fetchone()
        return r[0] if r else None
    finally:
        con.close()

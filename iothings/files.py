"""What comes with a thing: its photos, the manual, the receipt, the warranty card, anything else.

The bytes are kept in the database (thg_file_parts, in parts), so the suite's database backup (ioBackup) holds them
too and nothing lives beside the app; the keeping itself is the suite's (iosuite_shared.attachments, the same in
every app that keeps files in its database). A picture also gets a small JPEG for the cards (thumb); the first
photo of a thing is the one the cards show (thg_items.photo). A file is served as it came, with its own type, except
for the kinds a page could run (HTML, SVG, XML...), which are sent as a download.
A file gets a name of its own here, made of its number with the extension of its type (iothings-000123.jpg); the
name it was uploaded under is never kept, and a file is not renamed.
"""
from PIL import Image

from iosuite_shared import attachments, stamp
from iosuite_shared.errors import Invalid

from iothings import config, db
from iothings.model import NotFound, need_write, may_add, Forbidden

KINDS = ("photo", "manual", "receipt", "warranty", "other")
PART_BYTES = attachments.PART_BYTES
MAX_FILES = 200           # of one thing
THUMB_SIDE = 520
MAX_PIXELS = attachments.MAX_PIXELS
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

# the suite's way of keeping files in the app's database (iosuite_shared.attachments); a video and a voice memo of
# a thing are shown in the browser as they are too
files = attachments.Store(db, "thg_files", "item_id", parts="thg_file_parts", prefix="iothings-",
                          max_files=MAX_FILES, thumb_side=THUMB_SIDE,
                          inline=attachments.INLINE | {"video/mp4", "audio/mpeg"},
                          full="A thing holds at most {n} files")
assigned = files.assigned
inline = files.inline


def _public(r: dict) -> dict:
    return {"id": r["id"], "kind": r["kind"], "name": r["name"], "mime": r["mime"], "size": int(r["size"]),
            "thumb": bool(r.get("has_thumb")), "url": f"api/items/{r['item_id']}/files/{r['id']}",
            "added": r["created_at"].isoformat() if r.get("created_at") else None}


def listed(item_id: int) -> list[dict]:
    rows = db.q("SELECT id, item_id, kind, name, mime, size, thumb IS NOT NULL AS has_thumb, created_at FROM thg_files "
                "WHERE item_id = %s ORDER BY FIELD(kind, 'photo', 'manual', 'receipt', 'warranty', 'other'), position, id", (item_id,))
    return [_public(r) for r in rows]


def _cover(item_id: int) -> None:
    """The picture the cards show: the first photo (one with a small picture)."""
    p = db.one("SELECT id FROM thg_files WHERE item_id = %s AND kind = 'photo' AND thumb IS NOT NULL ORDER BY position, id LIMIT 1", (item_id,))
    db.ex("UPDATE thg_items SET photo = %s, updated_at = updated_at WHERE id = %s", (p["id"] if p else 0, item_id))


def may_attach(u: dict, it: dict) -> None:
    """Files: the ones who may change the thing, and any member (a receipt, a photo of the label)."""
    if not may_add(u):
        raise Forbidden("A viewer only looks: a member or more adds files")


@stamp.records("iothings", "item", "file added", item=lambda u, it, *a, **k: it["id"])
def add(u: dict, it: dict, raw: bytes, hint: str | None, mime: str | None, kind: str | None) -> dict:
    """Keep a file with the thing; kind left out: a photo for a picture, a manual for a PDF, other otherwise."""
    may_attach(u, it)
    mime, ext = files.look(raw, hint, mime, config.MAX_FILE_BYTES)
    # made in the helper: a picture that crashes Pillow costs only its small picture. A file somebody adds as a
    # photo is tried as one whatever its type says, so that it is told below when it is not a picture at all.
    small = files.small(raw, "image/jpeg" if mime.startswith("image/") or kind == "photo" else mime)
    if kind not in KINDS:
        kind = "photo" if small else "manual" if mime == "application/pdf" else "other"
    if kind == "photo" and not small:
        raise Invalid("That is not a picture this server can read (JPEG, PNG, WebP or GIF): add it as another kind of file")
    with db.tx():
        fid = files.store(it["id"], raw, mime=mime, ext=ext, thumb=small, user=u, extra={"kind": kind})
        _cover(it["id"])
    return one(it["id"], fid)


def one(item_id: int, fid) -> dict:
    r = db.one("SELECT id, item_id, kind, name, mime, size, thumb IS NOT NULL AS has_thumb, created_at FROM thg_files "
               "WHERE id = %s AND item_id = %s", (int(fid), int(item_id)))
    if not r:
        raise NotFound("This thing has no such file")
    return _public(r)


def content(item_id: int, fid, small: bool = False) -> tuple[bytes, str, str]:
    """(bytes, type, name) of the file, or of its small picture."""
    if small:
        r = db.one("SELECT thumb, name FROM thg_files WHERE id = %s AND item_id = %s", (int(fid), int(item_id)))
        if not r or r["thumb"] is None:
            raise NotFound("This file has no small picture")
        return bytes(r["thumb"]), "image/jpeg", r["name"]
    f = one(item_id, fid)
    return files.bytes_of(f["id"]), f["mime"], f["name"]


@stamp.records("iothings", "item", "file changed", item=lambda u, it, *a, **k: it["id"])
def change(u: dict, it: dict, fid, data: dict) -> dict:
    """{kind?, first?: true to make it the first of its kind (a photo: the one the cards show)}"""
    may_attach(u, it)
    f = one(it["id"], fid)
    sets = {}
    if "kind" in data:
        k = str(data.get("kind") or "")
        if k not in KINDS:
            raise Invalid(f"kind: one of {', '.join(KINDS)}")
        if k == "photo" and not f["thumb"]:
            raise Invalid("Only a picture can be a photo")
        sets["kind"] = k
    if data.get("first"):
        sets["position"] = files.before_all(it["id"])
    with db.tx():
        if sets:
            db.ex(f"UPDATE thg_files SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), f["id"]])
        _cover(it["id"])
    return one(it["id"], fid)


@stamp.records("iothings", "item", "file removed", item=lambda u, it, *a, **k: it["id"])
def remove(u: dict, it: dict, fid) -> None:
    """Members remove what they added; editors and the one who added the thing remove any of its files."""
    f = db.one("SELECT id, created_by FROM thg_files WHERE id = %s AND item_id = %s", (int(fid), it["id"]))
    if not f:
        raise NotFound("This thing has no such file")
    if f["created_by"] != u.get("id"):
        need_write(u, it)
    with db.tx():
        db.ex("DELETE FROM thg_files WHERE id = %s", (f["id"],))
        _cover(it["id"])

"""A document's scans and files: the front and back of a license, the photo page of a passport, a policy's PDF.

The bytes are kept in the database (doc_file_parts, in parts), so the suite's database backup (ioBackup) holds them
too and nothing lives beside the app; the keeping itself is the suite's (iosuite_shared.attachments, the same in
every app that keeps files in its database). A picture (and a PDF's first page) also gets a small JPEG for the
cards (thumb); the first file with one is the document's cover. Each file can be read (iodocs/ocr.py): its text goes
into the search, and the facts made of it fill in the document (iodocs/model.py apply_found). A file is served as it
came, with its own type, except for the kinds a page could run (HTML, SVG, XML...), which are sent as a download.
A file gets a name of its own here, made of its number with the extension of its type (iodocs-000123.pdf); the
name it was uploaded under is never kept, and a file is not renamed.
"""
import datetime as dt
import json
import logging

from PIL import Image

from iosuite_shared import attachments, helper, stamp
from iosuite_shared.errors import Invalid

from iodocs import config, db, ocr
from iodocs.model import NotFound, need_write, rewords

log = logging.getLogger("iodocs.files")
MAX_FILES = 100           # of one document
THUMB_SIDE = 640
READ_TIMEOUT = 600  # seconds one file may take to read (each run of tesseract may take ocr.TIMEOUT; a scan gets several)
Image.MAX_IMAGE_PIXELS = attachments.MAX_PIXELS

# the suite's way of keeping files in the app's database (iosuite_shared.attachments)
files = attachments.Store(db, "doc_files", "doc_id", parts="doc_file_parts", prefix="iodocs-",
                          max_files=MAX_FILES, thumb_side=THUMB_SIDE, full="A document holds at most {n} files")
assigned = files.assigned
inline = files.inline


def _public(r: dict) -> dict:
    try:
        found = json.loads(r["found"]) if r.get("found") else None
    except ValueError:
        found = None
    return {"id": r["id"], "name": r["name"], "mime": r["mime"], "size": int(r["size"]), "thumb": bool(r.get("has_thumb")),
            "url": f"api/documents/{r['doc_id']}/files/{r['id']}", "added": r["created_at"].isoformat() if r.get("created_at") else None,
            "read": r["read_at"].isoformat() if r.get("read_at") else None, "found": found,
            "hasText": bool(r.get("has_text"))}


_COLS = "id, doc_id, name, mime, size, thumb IS NOT NULL AS has_thumb, created_at, read_at, found, (text IS NOT NULL AND text <> '') AS has_text"


def listed(doc_id: int) -> list[dict]:
    return [_public(r) for r in db.q(f"SELECT {_COLS} FROM doc_files WHERE doc_id = %s ORDER BY position, id", (doc_id,))]


def _cover(doc_id: int) -> None:
    p = db.one("SELECT id FROM doc_files WHERE doc_id = %s AND thumb IS NOT NULL ORDER BY position, id LIMIT 1", (doc_id,))
    db.ex("UPDATE doc_documents SET cover = %s, updated_at = updated_at WHERE id = %s", (p["id"] if p else 0, doc_id))


@stamp.records("iodocs", "document", "file added", item=lambda u, d, *a, **k: d["id"])
def add(u: dict, d: dict, raw: bytes, hint: str | None, mime: str | None) -> dict:
    need_write(u, d)
    mime, ext = files.look(raw, hint, mime, config.MAX_FILE_BYTES)
    small = files.small(raw, mime, pages=ocr.pdf_pages)   # a scan that crashes Pillow or Poppler is kept without one
    with db.tx():
        fid = files.store(d["id"], raw, mime=mime, ext=ext, thumb=small, user=u)
        _cover(d["id"])
    return one(d["id"], fid)


def one(doc_id: int, fid) -> dict:
    r = db.one(f"SELECT {_COLS} FROM doc_files WHERE id = %s AND doc_id = %s", (int(fid), int(doc_id)))
    if not r:
        raise NotFound("This document has no such file")
    return _public(r)


def content(doc_id: int, fid, small: bool = False) -> tuple[bytes, str, str]:
    """(bytes, type, name) of the file, or of its small picture."""
    if small:
        r = db.one("SELECT thumb, name FROM doc_files WHERE id = %s AND doc_id = %s", (int(fid), int(doc_id)))
        if not r or r["thumb"] is None:
            raise NotFound("This file has no small picture")
        return bytes(r["thumb"]), "image/jpeg", r["name"]
    f = one(doc_id, fid)
    return files.bytes_of(f["id"]), f["mime"], f["name"]


def text_of(doc_id: int, fid) -> str:
    r = db.one("SELECT text FROM doc_files WHERE id = %s AND doc_id = %s", (int(fid), int(doc_id)))
    if not r:
        raise NotFound("This document has no such file")
    return r["text"] or ""


def _json(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else str(v)


def read(u: dict, d: dict, fid, apply: bool = True) -> dict:
    """Read the file (OCR, the passport's zone, the license's barcode), keep its text and facts, and (apply) fill in
    the document where it says nothing yet. {file, found, source, filled, differs, available}"""
    need_write(u, d)
    can = ocr.available()
    raw, mime, _ = content(d["id"], fid)
    if not (mime.startswith("image/") or mime == "application/pdf"):
        raise Invalid("Only pictures and PDFs can be read")
    if not can["ocr"] and mime != "application/pdf" and not can["barcodes"]:
        raise Invalid("Reading scans needs Tesseract on the server (apt install tesseract-ocr)")
    got = helper.call(ocr.read, raw, mime, timeout=READ_TIMEOUT)  # Tesseract, zxing-cpp and Pillow, in the helper
    found = {k: (_json(v) if isinstance(v, (dt.date, dt.datetime)) else v) for k, v in got["found"].items()}
    if got["source"]:
        found["source"] = got["source"]
    db.ex("UPDATE doc_files SET text = %s, found = %s, read_at = CURRENT_TIMESTAMP WHERE id = %s AND doc_id = %s",
          (got["text"], json.dumps(found, ensure_ascii=False, default=_json) if found else None, int(fid), d["id"]))
    rewords(d["id"])
    out = {"found": found, "source": got["source"], "filled": [], "differs": [], "unread": [], "available": can}
    if apply and found:
        from iodocs import model
        out.update(model.apply_found(u, model.get(d["id"]), {**got["found"], "source": got["source"]}))
    out["file"] = one(d["id"], fid)
    return out


@stamp.records("iodocs", "document", "file changed", item=lambda u, d, *a, **k: d["id"])
def change(u: dict, d: dict, fid, data: dict) -> dict:
    """{first?: true to put it first (with a picture: the cover)}"""
    need_write(u, d)
    f = one(d["id"], fid)
    sets = {}
    if data.get("first"):
        sets["position"] = files.before_all(d["id"])
    with db.tx():
        if sets:
            db.ex(f"UPDATE doc_files SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), f["id"]])
        _cover(d["id"])
    return one(d["id"], fid)


@stamp.records("iodocs", "document", "file removed", item=lambda u, d, *a, **k: d["id"])
def remove(u: dict, d: dict, fid) -> None:
    need_write(u, d)
    f = one(d["id"], fid)
    with db.tx():
        db.ex("DELETE FROM doc_files WHERE id = %s", (f["id"],))
        _cover(d["id"])
    rewords(d["id"])

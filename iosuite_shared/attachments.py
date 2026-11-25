"""Files an app keeps in its own database, once for the suite.

ioDocs keeps a document's scans and its policy PDFs, ioThings what comes with a thing (its photos, the manual, the
receipt), ioMoney a transaction's receipts. All three keep the bytes in parts of PART_BYTES in a table of their own,
so the suite's database backup (ioBackup) holds them too and nothing lives beside the app; all three read the type
off the first bytes rather than trusting what the upload says, give a file a name made of its number
(iodocs-000123.pdf) instead of the one it was uploaded under, make the small picture in the suite's helper process
so a scan that crashes Pillow costs only its thumbnail, and serve a file as it came unless it is a kind a page
could run.

A Store does that much. What is the app's own stays in the app: who may add a file, what else its row carries (a
kind, the text read off it), the line in the item's history and which picture the cards show.

    files = attachments.Store(db, "doc_files", "doc_id", parts="doc_file_parts", prefix="iodocs-",
                              max_files=100, thumb_side=640)

    mime, ext = files.look(raw, hint, given_mime, config.MAX_FILE_BYTES)
    fid = files.store(d["id"], raw, mime=mime, ext=ext, user=u, extra={"kind": kind})
    raw = files.bytes_of(fid)

ioNote's attachments are its own: they are keyed by the id a device chose, keep the name they were sent under and
live in one row with the note's own rev, so they share the text pulled out of a file (`text_of`) and nothing else.
"""
import hashlib
import io
import logging

from iosuite_shared import helper, stored
from iosuite_shared.errors import Invalid

log = logging.getLogger("iosuite_shared.attachments")
PART_BYTES = stored.PART_BYTES
MAX_PIXELS = 80_000_000      # a picture larger than this is kept, without a small one
THUMB_TIMEOUT = 120          # seconds the helper may take over one small picture
MAX_TEXT = 2 << 20           # the text pulled out of one file (a long PDF's)
MAX_PDF_PAGES = 500
# shown in the browser as they are; anything else is a download, so that a page of somebody's (HTML, SVG, XML)
# can never run as this site
INLINE = frozenset({"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic",
                    "image/avif", "text/plain"})
TEXT_TYPES = ("text/plain", "text/markdown", "text/csv", "application/json", "text/x-python", "application/xml",
              "text/xml")
TEXT_EXT = (".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log", ".xml", ".yaml", ".yml", ".py", ".js",
            ".sh", ".swift")


class Store:
    """The files of one kind of item, in one table of the app's database.

    `table` holds a row per file with `owner` (the item's id), name, mime and size, and `parts` its bytes under
    `part_key`. `prefix`: the name a file gets here (iodocs-000123.pdf); empty to keep the name it was sent under
    (ioMoney's receipts). `thumb_side`: the small JPEG a picture gets, 0 for none. `ordered`: the table has a
    `position`, so a file can be put first. `inline`: the types a browser is handed as they are. `full`: what the
    person is told when the item holds as many files as it may, with {n} for how many.
    """

    def __init__(self, db, table: str, owner: str, *, parts: str, part_key: str = "file_id", prefix: str = "",
                 max_files: int = 100, thumb_side: int = 0, ordered: bool = True, sha: bool = True,
                 inline=INLINE, full: str = "That holds at most {n} files"):
        self.db, self.table, self.owner, self.parts, self.part_key = db, table, owner, parts, part_key
        self.prefix, self.max_files, self.thumb_side = prefix, max_files, thumb_side
        self.ordered, self.sha, self._inline, self.full = ordered, sha, frozenset(inline), full

    # ---- what a file is

    def look(self, raw: bytes, hint: str | None, mime: str | None, max_bytes: int) -> tuple[str, str]:
        """(type, extension) of an upload. Invalid when it is empty or larger than the app allows."""
        if not raw:
            raise Invalid("The file is empty")
        if len(raw) > max_bytes:
            raise Invalid(f"Files up to {max_bytes // (1024 * 1024)} MB")
        found = stored.mime_of(hint or "", mime, raw)
        return found, stored.extension(hint, found)

    def assigned(self, fid: int, ext: str) -> str:
        """The name a file gets here, made of its number: the name it was uploaded under is never kept."""
        return stored.assigned(self.prefix, fid, ext)

    def inline(self, mime: str) -> bool:
        """True when the browser is handed this type as it is, False when it is a download."""
        return mime in self._inline

    def small(self, raw: bytes, mime: str, pages=None) -> bytes | None:
        """A small JPEG of a picture (turned upright), or of the first page of a PDF where `pages` can draw one
        (ioDocs hands in Poppler). None for anything else, for a picture of more than MAX_PIXELS, and for one this
        server cannot read. Made in the suite's helper process: what crashes Pillow costs only the small picture."""
        if not self.thumb_side:
            return None
        if mime.startswith("image/"):
            return helper.call_or(None, stored.picture, raw, self.thumb_side, MAX_PIXELS, timeout=THUMB_TIMEOUT)
        if mime == "application/pdf" and pages is not None:
            return helper.call_or(None, _pdf_thumb, raw, self.thumb_side, pages, timeout=THUMB_TIMEOUT)
        return None

    # ---- keeping one

    def room(self, owner_id: int) -> int:
        """The position a new file takes. Invalid when the item holds as many files as it may."""
        got = self.db.one(f"SELECT COUNT(*) AS n, COALESCE(MAX(position), -1) AS last FROM {self.table} "
                          f"WHERE {self.owner} = %s", (owner_id,)) if self.ordered else \
            self.db.one(f"SELECT COUNT(*) AS n, -1 AS last FROM {self.table} WHERE {self.owner} = %s", (owner_id,))
        if got["n"] >= self.max_files:
            raise Invalid(self.full.format(n=self.max_files))
        return int(got["last"]) + 1

    def store(self, owner_id: int, raw: bytes, *, mime: str, ext: str = "", name: str = "", thumb: bytes = None,
              user: dict | None = None, extra: dict | None = None) -> int:
        """Write the file's row and its bytes, and return its number. Inside the caller's transaction, so that a
        file and what the app writes beside it (the cover, the item's stamp) land together."""
        cols = {self.owner: owner_id, "name": name, "mime": mime, "size": len(raw), **(extra or {})}
        if self.sha:
            cols["sha256"] = hashlib.sha256(raw).hexdigest()
        if self.thumb_side:
            cols["thumb"] = thumb
        if self.ordered:
            cols["position"] = self.room(owner_id)
        else:
            self.room(owner_id)
        if user is not None:
            cols["created_by"] = user.get("id")
        fid = self.db.ex(f"INSERT INTO {self.table} ({', '.join(cols)}) "
                         f"VALUES ({', '.join(['%s'] * len(cols))})", list(cols.values()))
        if self.prefix:
            self.db.ex(f"UPDATE {self.table} SET name = %s WHERE id = %s", (self.assigned(fid, ext), fid))
        self.keep(fid, raw)
        return fid

    def keep(self, fid: int, raw: bytes) -> None:
        """The file's bytes, in parts."""
        for n, part in stored.parts(raw):
            self.db.ex(f"INSERT INTO {self.parts} ({self.part_key}, n, data) VALUES (%s, %s, %s)", (fid, n, part))

    # ---- reading one back

    def bytes_of(self, fid: int) -> bytes:
        """The file again, from its parts."""
        return stored.join(self.db.q(f"SELECT data FROM {self.parts} WHERE {self.part_key} = %s ORDER BY n",
                                     (int(fid),)))

    def before_all(self, owner_id: int) -> int:
        """The position that puts a file first among the item's (a picture there: the one the cards show)."""
        low = self.db.one(f"SELECT COALESCE(MIN(position), 0) AS p FROM {self.table} WHERE {self.owner} = %s",
                          (owner_id,))["p"]
        return int(low) - 1


def _pdf_thumb(raw: bytes, side: int, pages) -> bytes | None:
    """A small JPEG of a PDF's first page, drawn by whatever the app hands in (Poppler). In the helper."""
    from PIL import Image, UnidentifiedImageError
    try:
        drawn = pages(raw, pages=1, dpi=72)
        return stored.small_jpeg(drawn[0], side) if drawn else None
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


# ---- the text in a file, for the search (ioDocs reads a scan; this is what a file says by itself)

def pdf_text(raw: bytes, max_text: int = MAX_TEXT, max_pages: int = MAX_PDF_PAGES) -> str:
    """The text a PDF carries itself (pypdf), "" for one that is only scans, damaged or locked."""
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(raw))
        out, size = [], 0
        for i, page in enumerate(r.pages):
            if i >= max_pages or size > max_text:
                break
            t = page.extract_text() or ""
            out.append(t)
            size += len(t)
        return "\n".join(out).strip()[:max_text]
    except Exception as e:  # noqa: BLE001 - a damaged or encrypted PDF is kept, without its text
        log.info("no text from a PDF: %s", e)
        return ""


def text_of(raw: bytes, mime: str, name: str = "", max_text: int = MAX_TEXT) -> str:
    """The text a file says by itself: a PDF's own words, a text file's text, "" for anything else (a picture is
    read instead: iosuite_shared.ocr)."""
    if mime == "application/pdf":
        return pdf_text(raw, max_text)
    if mime.startswith("text/") or mime in TEXT_TYPES or str(name).lower().endswith(TEXT_EXT):
        return raw[:max_text].decode("utf-8", "replace").replace("\x00", "")
    return ""

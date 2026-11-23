"""Files an app keeps in its database (ioDocs' scans, what comes with a thing in ioThings, ioMoney's receipts): what
those apps do the same way.

The bytes are kept in parts of PART_BYTES in a table of the app's own, so the suite's database backup (ioBackup)
holds them too and nothing lives beside the app. A file gets a name of its own, made of its number with the
extension of its type (iodocs-000123.pdf): the name it was uploaded under is never kept. The tables, who may add and
what else a file carries (a kind, the text read off it) are each app's.
"""
import io
import mimetypes
import re

PART_BYTES = 4 * 1024 * 1024


def parts(raw: bytes):
    """(n, the part's bytes) for each part of a file, in order: one row each."""
    for i in range(0, len(raw), PART_BYTES):
        yield i // PART_BYTES, raw[i:i + PART_BYTES]


def join(rows: list, column: str = "data") -> bytes:
    """A file again, from its parts' rows in order."""
    return b"".join(bytes(r[column]) for r in rows)


def extension(hint: str | None, mime: str) -> str:
    """The extension the file keeps, so it still opens: the one it came with when it fits its type, else its type's."""
    m = re.search(r"\.([A-Za-z0-9]{1,8})$", str(hint or "").strip())
    came = "." + m.group(1).lower() if m else ""
    if came and mimetypes.guess_type("x" + came)[0] == mime:
        return came
    known = mimetypes.guess_extension(mime) if mime != "application/octet-stream" else None
    return known or came


def assigned(prefix: str, fid: int, ext: str) -> str:
    """The name a file gets, made of its number: the name it was uploaded under is never kept."""
    return f"{prefix}{int(fid):06d}{ext}"


def mime_of(hint: str, given: str | None, raw: bytes) -> str:
    """The file's type: a PDF by its first bytes, else what the upload says when that is a type at all, else what its
    name suggests."""
    if raw[:4] == b"%PDF":
        return "application/pdf"
    g = (given or "").split(";")[0].strip().lower()
    if g and g != "application/octet-stream" and re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", g):
        return g
    return mimetypes.guess_type(hint)[0] or "application/octet-stream"


def small_jpeg(im, side: int) -> bytes:
    """A small JPEG of an opened picture (Pillow), at most `side` pixels a side, what was see-through on white."""
    from PIL import Image
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        back = Image.new("RGB", im.size, (255, 255, 255))
        back.paste(im, mask=im.split()[-1])
        im = back
    else:
        im = im.convert("RGB")
    im.thumbnail((side, side), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=80, optimize=True)
    return out.getvalue()


def picture(raw: bytes, side: int, max_pixels: int) -> bytes | None:
    """A small JPEG of a picture's bytes (turned upright); None when they are not a picture this server reads, or one
    of more than `max_pixels`. Work for the helper (iosuite_shared.helper): it decodes what somebody uploaded."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        im = Image.open(io.BytesIO(raw))
        if im.width * im.height > max_pixels:
            return None
        return small_jpeg(ImageOps.exif_transpose(im), side)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None

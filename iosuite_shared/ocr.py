"""Reading the text in a picture, once for the suite.

ioDocs reads a scan of a passport or a policy, ioRecipe a photo of a cookbook page, ioNote a picture pasted into a
note. Each had its own way of finding the reader, its own setting for the languages and its own picture tidy-up
before reading; this is the one, with two settings for the whole suite (Settings › Apps › All settings):

    OCR_PROGRAM     tesseract by default, another path, or off to never read a picture
    OCR_LANGUAGES   eng+nld+fra; empty: every language installed, English first

    from iosuite_shared import ocr
    if ocr.available():
        text = ocr.read(raw)                       # Invalid when it is not a picture or nothing can be read
    text = ocr.run(image, psm=6)                   # one run on a picture already prepared (ioDocs does its own)

The picture never leaves the server. The reading runs in the suite's helper process (iosuite_shared.helper), so a
reader that needs a lot of memory gives it back afterwards and a crash in it cannot take the copy down.
"""
import io
import logging
import shutil
import subprocess

from iosuite_shared.errors import Invalid

log = logging.getLogger("iosuite_shared.ocr")
TIMEOUT = 90      # seconds for one picture
MAX_SIDE = 2600   # the longest side handed to the reader: enough for a page, quick enough
MIN_SIDE = 1400   # small print reads better enlarged
OFF = ("off", "0", "no", "none", "")
_langs: list | None = None


def _setting(name: str, default: str = "") -> str:
    from iosuite_shared import db
    try:
        return (db.get_setting(name, default) or "").strip()
    except Exception:  # noqa: BLE001 - the database away: the default
        return default


def program() -> str | None:
    """The reader on this server, or None when it is not installed or the suite turned it off."""
    named = _setting("OCR_PROGRAM", "tesseract") or "tesseract"
    if named.lower() in OFF:
        return None
    return shutil.which(named)


def languages() -> list:
    """The languages the reader has here (eng, nld, fra...), [] when it is not installed."""
    global _langs
    if _langs is None:
        exe = program()
        if not exe:
            return []
        try:
            out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=15).stdout
            _langs = sorted(x.strip() for x in out.splitlines()[1:] if x.strip() and x.strip() not in ("osd", "equ"))
        except (OSError, subprocess.SubprocessError):
            _langs = []
    return _langs


def forget() -> None:
    """Read the languages again (the setting changed, a language package was installed)."""
    global _langs
    _langs = None


def available() -> bool:
    return bool(program() and languages())


def wanted(langs: str | None = None) -> str:
    """The languages to read in, as the reader takes them: what is asked for and installed, else what is installed
    (English first, six at most: each one costs time)."""
    have = languages()
    asked = [x.strip() for x in (langs if langs is not None else _setting("OCR_LANGUAGES")).replace(",", "+").split("+")]
    keep = [x for x in asked if x in have]
    if keep:
        return "+".join(keep)
    rest = sorted(have, key=lambda x: (x != "eng", x))[:6]
    return "+".join(rest) or "eng"


def status() -> dict:
    """What this server can read with (an app's diagnostics, GET /api/status)."""
    return {"program": program(), "languages": languages(), "reads": wanted() if available() else ""}


def prepared(im, max_side: int = MAX_SIDE, min_side: int = MIN_SIDE):
    """A picture as the reader likes it: upright, grey, not too large, not too small, with its contrast stretched."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(im).convert("L")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    elif max(im.size) < min_side:
        f = min_side / max(im.size)
        im = im.resize((round(im.width * f), round(im.height * f)), Image.LANCZOS)
    return ImageOps.autocontrast(im)


def run(im, psm: int = 3, langs: str | None = None, tessdata: str | None = None, timeout: int = TIMEOUT,
        extra: list | None = None) -> str:
    """One run of the reader on a picture (a PIL image or PNG bytes), as it comes: "" when it could not read it.
    `psm`: how the page is laid out (Tesseract's --psm). `tessdata`: a folder with a model of its own, whose name
    `langs` then gives as it is (ioDocs reads the machine-readable zone of a passport with one trained on its font).
    `extra`: more arguments for the reader."""
    exe = program()
    if not exe:
        return ""
    if not isinstance(im, (bytes, bytearray)):
        buf = io.BytesIO()
        im.save(buf, "PNG")
        im = buf.getvalue()
    cmd = [exe, "stdin", "stdout"]
    if tessdata:
        cmd += ["--tessdata-dir", tessdata, "-l", langs or "eng"]
    else:
        cmd += ["-l", wanted(langs)]
    cmd += ["--psm", str(psm), *(extra or [])]
    try:
        r = subprocess.run(cmd, input=bytes(im), capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("the reader did not finish: %s", e)
        return ""
    if r.returncode != 0:
        log.warning("the reader said: %s", r.stderr.decode("utf-8", "replace")[-300:])
    return r.stdout.decode("utf-8", "replace")


def read(raw: bytes, psm: int = 3, langs: str | None = None, timeout: int = TIMEOUT) -> str:
    """The text in a picture. Invalid when it is not a picture, when nothing can be read, or without a reader."""
    from PIL import Image, UnidentifiedImageError
    if not available():
        raise Invalid("This server cannot read text in pictures: no OCR program is installed on it")
    try:
        im = prepared(Image.open(io.BytesIO(raw)))
    except (UnidentifiedImageError, OSError) as e:
        raise Invalid("That is not a picture this server can read") from e
    text = run(im, psm=psm, langs=langs, timeout=timeout).replace("\x0c", "").strip()
    if not text:
        raise Invalid("No text could be read in that picture")
    return text


# ---- the other reader: a model, for pictures without a scan's clean print (ioNote's)
def rapid_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("rapidocr") is not None


_engine = None


def rapid_read(data: bytes) -> str:
    """The text in a picture, read by RapidOCR: a model (a few hundred MB once loaded) rather than Tesseract, which
    reads a photo or a screenshot better than printed-page software does. Called in the suite's helper process
    (iosuite_shared.helper.call), where the model leaves memory again when there is nothing to read."""
    global _engine
    import numpy as np
    from PIL import Image
    if _engine is None:
        from rapidocr import RapidOCR
        _engine = RapidOCR()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((2400, 2400))
    res = _engine(np.array(img))
    return "\n".join(t for t in (res.txts or []) if t and t.strip())

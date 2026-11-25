"""Reading the text in a picture, once for the suite (iosuite_shared.ocr): which reader the suite uses, the
languages it reads in, the tidy-up before a reading and the arguments it is run with. The readers themselves are
not installed in the tests, so the run is a stand-in that records what it was asked."""
import io
import subprocess

import pytest
from PIL import Image

from iosuite_shared import db, ocr
from iosuite_shared.errors import Invalid


@pytest.fixture(autouse=True)
def forget_languages():
    ocr.forget()
    yield
    ocr.forget()


def reader(monkeypatch, langs=("eng", "nld", "fra", "deu", "spa", "ita", "por", "osd"), exe="/usr/bin/tesseract"):
    """A reader that is installed, with these languages. Returns the list its runs land in."""
    runs = []

    def which(name):
        return exe if name in ("tesseract", exe) else None

    def run(cmd, **kw):
        runs.append((cmd, kw))
        if "--list-langs" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="List of available languages:\n" + "\n".join(langs) + "\n")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"Hello from the page\n\x0c", stderr=b"")

    monkeypatch.setattr(ocr.shutil, "which", which)
    monkeypatch.setattr(ocr.subprocess, "run", run)
    return runs


def picture(size=(1800, 1200), color=128) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (color, color, color)).save(buf, "PNG")
    return buf.getvalue()


def test_the_suite_says_which_reader_and_whether_it_is_there(monkeypatch):
    reader(monkeypatch)
    assert ocr.program() == "/usr/bin/tesseract" and ocr.available()
    db.set_setting("OCR_PROGRAM", "off")           # never read a picture
    ocr.forget()
    assert ocr.program() is None and not ocr.available()
    db.set_setting("OCR_PROGRAM", "/opt/bin/other")
    ocr.forget()
    assert ocr.program() is None                   # named, but not installed here


def test_no_reader_installed(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    assert ocr.program() is None and ocr.languages() == [] and not ocr.available()
    assert ocr.run(Image.new("L", (10, 10))) == ""  # nothing to run: no reading, no error
    with pytest.raises(Invalid):
        ocr.read(picture())


def test_the_languages_are_the_installed_ones_and_osd_is_not_one(monkeypatch):
    reader(monkeypatch, langs=("eng", "nld", "osd", "equ"))
    assert ocr.languages() == ["eng", "nld"]


def test_the_languages_asked_for_are_the_installed_ones_of_them(monkeypatch):
    reader(monkeypatch)
    db.set_setting("OCR_LANGUAGES", "nld+fra+klingon")
    assert ocr.wanted() == "nld+fra"               # one that is not installed is left out
    assert ocr.wanted("deu, ita") == "deu+ita"     # a comma is a plus
    db.set_setting("OCR_LANGUAGES", "klingon")
    assert ocr.wanted() == "eng+deu+fra+ita+nld+por"   # none of them installed: what is, English first, six at most


def test_the_status_says_what_this_server_reads_with(monkeypatch):
    reader(monkeypatch, langs=("eng", "nld"))
    db.set_setting("OCR_LANGUAGES", "nld")
    assert ocr.status() == {"program": "/usr/bin/tesseract", "languages": ["eng", "nld"], "reads": "nld"}


def test_a_picture_is_made_ready_before_it_is_read():
    big = ocr.prepared(Image.new("RGB", (6000, 3000)))
    assert big.mode == "L" and max(big.size) == ocr.MAX_SIDE
    small = ocr.prepared(Image.new("RGB", (400, 200)))
    assert max(small.size) == ocr.MIN_SIDE         # small print reads better enlarged
    assert ocr.prepared(Image.new("RGB", (1800, 1200))).size == (1800, 1200)


def test_a_reading_passes_the_layout_and_the_languages(monkeypatch):
    runs = reader(monkeypatch, langs=("eng", "nld"))
    assert ocr.run(Image.new("L", (50, 50)), psm=6).startswith("Hello")
    cmd = runs[-1][0]
    assert cmd[:3] == ["/usr/bin/tesseract", "stdin", "stdout"]
    assert cmd[cmd.index("--psm") + 1] == "6" and cmd[cmd.index("-l") + 1] == "eng+nld"
    assert "--tessdata-dir" not in cmd


def test_a_model_of_its_own_is_passed_as_it_is(monkeypatch):
    runs = reader(monkeypatch)
    ocr.run(Image.new("L", (50, 50)), langs="mrz", tessdata="/opt/iosuite/iodocs/tessdata",
            extra=["-c", "tessedit_char_whitelist=AB<"])
    cmd = runs[-1][0]
    assert cmd[cmd.index("--tessdata-dir") + 1] == "/opt/iosuite/iodocs/tessdata"
    assert cmd[cmd.index("-l") + 1] == "mrz"       # not filtered against what Tesseract lists
    assert cmd[-2:] == ["-c", "tessedit_char_whitelist=AB<"]


def test_a_reader_that_does_not_finish_reads_nothing(monkeypatch):
    reader(monkeypatch)

    def boom(cmd, **kw):
        if "--list-langs" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="List:\neng\n")
        raise subprocess.TimeoutExpired(cmd, 90)

    monkeypatch.setattr(ocr.subprocess, "run", boom)
    assert ocr.run(Image.new("L", (50, 50))) == ""


def test_what_is_read_and_what_cannot_be(monkeypatch):
    reader(monkeypatch)
    assert ocr.read(picture()) == "Hello from the page"   # the page break and the spaces around it are gone
    with pytest.raises(Invalid):
        ocr.read(b"this is not a picture")

    monkeypatch.setattr(ocr, "run", lambda *a, **kw: "  \x0c ")
    with pytest.raises(Invalid):
        ocr.read(picture())                                # nothing could be read


def test_the_other_reader_is_only_offered_when_it_is_installed(monkeypatch):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert ocr.rapid_available() is False          # ioNote's model: reading a picture is simply not offered
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    assert ocr.rapid_available() is True

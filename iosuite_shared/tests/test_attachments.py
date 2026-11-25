"""Files an app keeps in its own database (iosuite_shared.attachments): what an upload is, the name it gets, the
limit, the bytes in parts and the text a file says by itself. The Store is driven here against a table of a test's
own; what each app does beside it (who may add a file, its kind, the picture its cards show) is each app's tests."""
import io

import pytest
from PIL import Image

from iosuite_shared import attachments, db
from iosuite_shared.errors import Invalid

MAX = 10 << 20


@pytest.fixture
def files():
    """A Store over a table made for this test: files of a 'box', with a position and a small picture."""
    db.ex("CREATE TABLE tst_files (id INT AUTO_INCREMENT PRIMARY KEY, box_id INT NOT NULL, name VARCHAR(255) NOT NULL, "
          "mime VARCHAR(128) NOT NULL, size BIGINT NOT NULL, sha256 CHAR(64), thumb LONGBLOB, position INT NOT NULL "
          "DEFAULT 0, created_by INT, kind VARCHAR(32)) ENGINE=InnoDB")
    db.ex("CREATE TABLE tst_file_parts (file_id INT NOT NULL, n INT NOT NULL, data LONGBLOB NOT NULL, "
          "PRIMARY KEY (file_id, n)) ENGINE=InnoDB")
    yield attachments.Store(db, "tst_files", "box_id", parts="tst_file_parts", prefix="iotest-", max_files=3,
                            thumb_side=120, full="A box holds at most {n} files")


def png(size=(300, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def test_what_an_upload_is(files):
    assert files.look(png(), "snap.PNG", "image/png", MAX) == ("image/png", ".png")
    assert files.look(b"%PDF-1.7\nhello", "policy.pdf", "application/octet-stream", MAX) == ("application/pdf", ".pdf")
    # the first bytes win over what the upload says it is
    assert files.look(b"%PDF-1.7\nhello", "sneaky.html", "text/html", MAX)[0] == "application/pdf"


def test_an_upload_that_is_empty_or_too_large(files):
    with pytest.raises(Invalid):
        files.look(b"", "a.png", "image/png", MAX)
    with pytest.raises(Invalid) as e:
        files.look(b"x" * 2048, "a.bin", None, 1024)
    assert "MB" in str(e.value)


def test_a_file_gets_a_name_made_of_its_number(files):
    fid = files.store(1, png(), mime="image/png", ext=".png")
    assert db.one("SELECT name FROM tst_files WHERE id = %s", (fid,))["name"] == f"iotest-{fid:06d}.png"


def test_a_receipt_may_keep_the_name_it_was_sent_under(files):
    kept = attachments.Store(db, "tst_files", "box_id", parts="tst_file_parts", max_files=3, ordered=False, sha=False)
    fid = kept.store(1, b"%PDF-1.7\n", mime="application/pdf", name="Till slip.pdf")
    r = db.one("SELECT name, sha256, position FROM tst_files WHERE id = %s", (fid,))
    assert r["name"] == "Till slip.pdf" and r["sha256"] is None and r["position"] == 0


def test_the_row_says_the_size_the_sum_and_who_added_it(files):
    raw = png()
    fid = files.store(7, raw, mime="image/png", ext=".png", user={"id": 42}, extra={"kind": "photo"})
    r = db.one("SELECT box_id, size, sha256, created_by, kind, position FROM tst_files WHERE id = %s", (fid,))
    assert r["box_id"] == 7 and r["size"] == len(raw) and r["created_by"] == 42 and r["kind"] == "photo"
    assert len(r["sha256"]) == 64 and r["position"] == 0


def test_the_bytes_come_back_from_their_parts(files, monkeypatch):
    monkeypatch.setattr(attachments.stored, "PART_BYTES", 1024)
    raw = bytes(range(256)) * 20          # five parts and a bit
    fid = files.store(1, raw, mime="application/octet-stream")
    assert db.one("SELECT COUNT(*) AS n FROM tst_file_parts WHERE file_id = %s", (fid,))["n"] == 5
    assert files.bytes_of(fid) == raw


def test_each_file_takes_the_next_place_and_one_can_be_put_first(files):
    a = files.store(1, b"a", mime="text/plain", ext=".txt")
    b = files.store(1, b"b", mime="text/plain", ext=".txt")
    assert db.one("SELECT position FROM tst_files WHERE id = %s", (b,))["position"] == 1
    assert files.before_all(1) == -1
    db.ex("UPDATE tst_files SET position = %s WHERE id = %s", (files.before_all(1), b))
    first = db.q("SELECT id FROM tst_files WHERE box_id = 1 ORDER BY position, id")[0]
    assert first["id"] == b and a != b


def test_an_item_holds_as_many_files_as_the_app_allows(files):
    for _ in range(3):
        files.store(1, b"x", mime="text/plain", ext=".txt")
    with pytest.raises(Invalid) as e:
        files.store(1, b"x", mime="text/plain", ext=".txt")
    assert str(e.value) == "A box holds at most 3 files"
    files.store(2, b"x", mime="text/plain", ext=".txt")   # another box has its own room


def test_a_picture_gets_a_small_one_and_other_files_do_not(files):
    small = files.small(png((900, 600)), "image/png")
    assert small and max(Image.open(io.BytesIO(small)).size) == 120
    assert files.small(b"%PDF-1.7\n", "application/pdf") is None      # no way to draw a page handed in
    assert files.small(b"not a picture", "image/png") is None
    assert files.small(png(), "application/zip") is None


def test_a_pdf_page_is_drawn_by_what_the_app_hands_in(files):
    drawn = []

    def pages(raw, pages, dpi):
        drawn.append((pages, dpi))
        return [Image.new("RGB", (800, 1000), (255, 255, 255))]

    small = files.small(b"%PDF-1.7\n", "application/pdf", pages=pages)
    assert drawn == [(1, 72)] and small and max(Image.open(io.BytesIO(small)).size) == 120


def test_no_small_picture_where_the_app_asked_for_none():
    plain = attachments.Store(db, "tst_files", "box_id", parts="tst_file_parts")
    assert plain.small(png(), "image/png") is None


def test_which_types_the_browser_is_handed_as_they_are(files):
    assert files.inline("application/pdf") and files.inline("image/jpeg")
    assert not files.inline("text/html") and not files.inline("image/svg+xml")
    mine = attachments.Store(db, "tst_files", "box_id", parts="tst_file_parts",
                             inline=attachments.INLINE | {"video/mp4"})
    assert mine.inline("video/mp4") and not files.inline("video/mp4")


def test_the_text_a_file_says_by_itself():
    assert attachments.text_of(b"hello there", "text/plain", "a.txt") == "hello there"
    assert attachments.text_of(b'{"a": 1}', "application/json", "a.json") == '{"a": 1}'
    assert attachments.text_of(b"print(1)", "application/octet-stream", "a.py") == "print(1)"
    assert attachments.text_of(b"\x89PNG", "image/png", "a.png") == ""      # a picture is read instead
    assert attachments.text_of(b"a" * 50, "text/plain", "a.txt", max_text=10) == "a" * 10


def test_a_pdf_that_is_damaged_is_kept_without_its_text():
    assert attachments.pdf_text(b"%PDF-1.7\nnot really a PDF") == ""

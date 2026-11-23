"""Files an app keeps in its database (iosuite_shared.stored): the parts, the name a file gets, its type, its small
picture."""
import io

from PIL import Image

from iosuite_shared import stored


def test_a_file_goes_into_parts_and_comes_back():
    raw = bytes(range(256)) * ((stored.PART_BYTES * 2) // 256 + 10)
    got = list(stored.parts(raw))
    assert [n for n, _p in got] == [0, 1, 2] and all(len(p) <= stored.PART_BYTES for _n, p in got)
    assert stored.join([{"data": p} for _n, p in got]) == raw
    assert list(stored.parts(b"")) == [] and stored.join([]) == b""


def test_the_name_is_the_file_s_number_with_its_type_s_extension():
    assert stored.assigned("iodocs-", 123, ".pdf") == "iodocs-000123.pdf"
    assert stored.extension("Holiday Scan.JPG", "image/jpeg") == ".jpg"   # the one it came with, when it fits its type
    assert stored.extension("passport.exe", "application/pdf") == ".pdf"  # else its type's
    assert stored.extension(None, "application/pdf") == ".pdf"
    assert stored.extension("notes.xyz", "application/octet-stream") == ".xyz"  # an unknown type keeps what it came with


def test_the_type_is_told_by_the_bytes_then_the_upload_then_the_name():
    assert stored.mime_of("x.txt", "text/plain", b"%PDF-1.7 ...") == "application/pdf"
    assert stored.mime_of("x.bin", "image/png; charset=binary", b"\x89PNG") == "image/png"
    assert stored.mime_of("manual.pdf", "application/octet-stream", b"....") == "application/pdf"
    assert stored.mime_of("x", "<script>", b"....") == "application/octet-stream"


def test_a_small_picture_is_a_jpeg_on_white_within_its_side():
    buf = io.BytesIO()
    Image.new("RGBA", (1200, 900), (255, 0, 0, 0)).save(buf, "PNG")  # see-through
    small = Image.open(io.BytesIO(stored.picture(buf.getvalue(), 520, 80_000_000)))
    assert small.format == "JPEG" and small.size == (520, 390) and small.getpixel((10, 10))[0] > 240 and small.getpixel((10, 10))[2] > 240
    assert stored.picture(b"not a picture", 520, 80_000_000) is None
    assert stored.picture(buf.getvalue(), 520, 1000) is None  # more pixels than this app reads

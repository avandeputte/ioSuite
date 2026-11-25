"""ioDocs' own commands from a shell, beside the migrate and check every app has (iosuite_shared.appcli):

    iosuite iodocs read FILE      what this server reads off a scan or a photo of a document
"""
import json
import mimetypes
from pathlib import Path


def add(sub) -> None:
    p = sub.add_parser("read", help="what this server reads off a scan or a photo of a document")
    p.add_argument("file")
    p.set_defaults(run=_read)


def _read(a) -> None:
    from iodocs import ocr
    raw = Path(a.file).read_bytes()
    mime = "application/pdf" if raw[:4] == b"%PDF" else mimetypes.guess_type(a.file)[0] or "image/jpeg"
    got = ocr.read(raw, mime)
    print(json.dumps({"reads": ocr.available(), "source": got["source"], "found": got["found"]}, indent=2, default=str))
    print("--- text ---")
    print(got["text"])

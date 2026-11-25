"""What ioPix's route modules share beside the suite's own readers and answers (iosuite_shared.http: jresp,
json_body): a form-encoded filter list, one photo's row, and the thumbnail and preview file responses with their
cache headers. Nothing here knows about digiKam; the index connection comes from iopix.runtime."""
import os
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from iopix import thumbs
from iopix.runtime import THUMB_COLS, db

IMG_CACHE = {"Cache-Control": "private, max-age=86400"}
# the most photo ids one request acts on: more than any one folder or year holds, so a selection is never cut
# short in practice, and small enough that the id list stays a few hundred KB and its chunked queries a moment
MAX_IDS = 20000


async def form_items(request: Request) -> list:
    """(key, value) pairs of a form-encoded body: the same filters the URL carries,
    for selections too long for a URL."""
    return parse_qsl((await request.body()).decode("utf-8", "replace"), keep_blank_values=True)


def photo_row(photo_id: int, cols: str = THUMB_COLS) -> dict:
    con = db()
    try:
        row = con.execute(f"SELECT {cols} FROM photos WHERE id = ?", (photo_id,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404)
    return dict(row)


def cached_image(kind: str, photo_id: int, dl: bool = False) -> FileResponse:
    row = photo_row(photo_id)
    try:
        path = thumbs.make(kind, row)
    except FileNotFoundError:
        raise HTTPException(404, "Original file is not available")
    except OSError as e:
        raise HTTPException(503, f"The file could not be read right now ({type(e).__name__})")
    if dl:  # a download of the resized JPEG, named after the photo (sharing a smaller file)
        return FileResponse(path, media_type="image/jpeg", filename=os.path.splitext(row["name"])[0] + "-preview.jpg",
                            content_disposition_type="attachment", headers=IMG_CACHE)
    return FileResponse(path, media_type="image/jpeg", headers=IMG_CACHE)

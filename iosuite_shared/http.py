"""Reading a request and writing an answer, the same way in every app of the suite.

    from iosuite_shared.http import attachment, jresp, json_body, user_name

    body = await json_body(request)                 # a JSON object, or 400 with what is wrong
    return jresp(request, data)                     # JSON with an ETag, gzipped when large
    return Response(zip_bytes, headers=attachment("export.zip"))
    notes.save(uid, body, user_name(request))       # who made the change, for the history

ioNote and ioPix each had their own copy of jresp, and ioPix of json_body; the differences were the wording of a
message and nothing else.
"""
import gzip
import hashlib
from urllib.parse import quote

import orjson
from fastapi import HTTPException, Request
from fastapi.responses import Response


def json_body(request: Request):
    """The request's body as a JSON object. Anything else (a list, a string, bad JSON) is the client's mistake and
    answers 400 rather than an AttributeError further down. Awaited: `body = await json_body(request)`."""
    async def read():
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request body is not JSON")
        if not isinstance(body, dict):
            raise HTTPException(400, "A JSON object is expected")
        return body
    return read()


def jresp(request: Request, data) -> Response:
    """JSON, gzipped when large, with an ETag: a client that sends it back (If-None-Match) gets 304 and no body while
    the answer is unchanged (what the pages reload again and again)."""
    body = orjson.dumps(data)
    etag = 'W/"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'
    headers = {"Cache-Control": "private, no-cache", "ETag": etag, "Vary": "Accept-Encoding, Cookie"}
    if etag in [t.strip() for t in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=headers)
    if len(body) > 2048 and "gzip" in request.headers.get("accept-encoding", ""):
        body = gzip.compress(body, compresslevel=3)
        headers["Content-Encoding"] = "gzip"
    return Response(body, media_type="application/json", headers=headers)


def attachment(name: str) -> dict:
    """The header that makes a browser save the answer under this name. A header is Latin-1 only, so a name with other
    characters goes twice (RFC 6266): an ASCII stand-in, and the real name as filename*=UTF-8''..."""
    plain = "".join(c if c.isascii() and c not in '"\\' and c.isprintable() else "_" for c in name)
    return {"Content-Disposition": f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name, safe='')}"}


def user_name(request: Request) -> str:
    """Who is asking, for a change history: the account's name, or "visitor"."""
    u = getattr(request.state, "user", None)
    return u["name"] if u else "visitor"

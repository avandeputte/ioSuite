"""One app of the suite asking another that runs in the same copy: the request is handed to it in this process,
without going out over the network.

The apps read from each other over HTTP (iosuite_shared.links), because an app may run on a server of its own. When
it runs in this very copy, that request went out to the machine's own address and came back in through the web
server: a TCP connection, a request parsed again, an answer parsed again. Here it is handed straight to the other
app's ASGI application instead, with exactly the headers the request would have carried, so the other app signs the
caller in, decides what they may see, and answers as it always does. Nothing is skipped but the network.

    if inside.runs("iocontact"):
        r = inside.ask("iocontact", "/api/contacts?q=ann", headers={"Authorization": "Basic …"})

iosuite_shared.host attaches itself as a copy starts (attach()), so this works only where a copy of the program runs
the other app: an app started on its own (`uvicorn iocalendar.main:app`) has no host, nothing is attached, and every
call goes over the network as before. Which is also what happens for an app that runs in another copy of the suite.
"""
from __future__ import annotations

import asyncio
import email.message
import io
import logging
import urllib.error
from urllib.parse import quote

from iosuite_shared import catalog, config, doors, prefix

log = logging.getLogger("iosuite_shared.inside")

PEER = "127.0.0.1"          # the other app sees the request as one from this machine, as over loopback it did
LIMIT = 64 << 20            # the most of an answer that is read
_LOOP: asyncio.AbstractEventLoop | None = None
_HOST = None                # the copy's host (iosuite_shared.host.Host), while one runs


def attach(loop, host) -> None:
    """The copy says which apps it runs and in which event loop (iosuite_shared.host, as it starts)."""
    global _LOOP, _HOST
    _LOOP, _HOST = loop, host


def detach() -> None:
    global _LOOP, _HOST
    _LOOP, _HOST = None, None


def asgi(app: str):
    """The app's ASGI application when this copy runs it and it is up; None otherwise."""
    if _HOST is None or _LOOP is None or _LOOP.is_closed():
        return None
    e = _HOST.by_name.get(app)
    return e.asgi if e is not None and e.state == "up" and e.asgi is not None else None


def runs(app: str) -> bool:
    """Whether this app can be asked inside this copy."""
    return asgi(app) is not None


class Answer:
    """What the other app answered, the way urllib would hand it over: a context manager with read(), status and
    headers. A 1xx/4xx/5xx never arrives here (ask() raises urllib's HTTPError, as a request over HTTP would)."""

    def __init__(self, url: str, status: int, headers: email.message.Message, body: bytes):
        self.url, self.status, self.code, self.headers, self._body = url, status, status, headers, io.BytesIO(body)

    def read(self, amt: int = None) -> bytes:
        return self._body.read() if amt is None else self._body.read(amt)

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.status

    def info(self) -> email.message.Message:
        return self.headers

    def close(self) -> None:
        self._body.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _headers_of(headers: dict, door: str) -> list:
    """The headers as the other app gets them: the ones the caller named and nothing else, so nothing a visitor said
    about themselves (a proxy's user header, X-Forwarded-For) is believed because this machine is trusted."""
    out = []
    for k, v in (headers or {}).items():
        name = str(k).lower()
        if name in doors.HOP or name in doors.SET_HERE or name.startswith("x-forwarded") or v is None:
            continue
        if door != doors.WEB and name == "cookie":  # no session at the doors for devices and MCP
            continue
        out.append((name.encode("latin-1"), str(v).encode("latin-1")))
    return out


def _scope(app: str, path: str, query: str, method: str, headers: dict, door: str, host: str) -> dict:
    folder = prefix.clean(catalog.FOLDERS.get(app) or "")
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1", "method": method.upper(),
            "scheme": "http", "path": path, "raw_path": quote(path, safe="/:@!$&'()*+,;=-._~").encode("latin-1"),
            "query_string": query.encode("latin-1"), "root_path": "", "client": (PEER, 0),
            "server": (host, config.PORT or 80), "headers": [(b"host", host.encode("latin-1")), *_headers_of(headers, door)],
            prefix.SCOPE_KEY: folder, doors.SCOPE_ROUTED: True, doors.SCOPE_DOOR: door, "iosuite.inside": True}


async def request(app: str, path: str, headers: dict = None, body: bytes = None, method: str = None, door: str = doors.WEB,
                  host: str = PEER, limit: int = LIMIT) -> Answer:
    """Ask the app that runs in this copy, from the event loop it runs in. LookupError when it does not run here;
    urllib's HTTPError for an answer that is not a 2xx, so a caller tells them apart as it does over HTTP."""
    from iosuite_shared.host import CURRENT
    inner = asgi(app)
    if inner is None:
        raise LookupError(f"{app} does not run in this copy")
    at, _, query = path.partition("?")
    scope = _scope(app, at, query, method or ("POST" if body else "GET"), headers or {}, door, host)
    sent = [{"type": "http.request", "body": body or b"", "more_body": False}]

    async def receive():
        return sent.pop(0) if sent else {"type": "http.disconnect"}

    status, out, got, over = 0, email.message.Message(), bytearray(), False

    async def send(message) -> None:
        nonlocal status, over
        if message["type"] == "http.response.start":
            status = message["status"]
            for k, v in message.get("headers") or []:
                out[k.decode("latin-1")] = v.decode("latin-1")
        elif message["type"] == "http.response.body":
            if len(got) + len(message.get("body") or b"") > limit:
                over = True
                raise OSError(f"{app} answered with more than {limit} bytes")
            got.extend(message.get("body") or b"")

    token = CURRENT.set(app)  # what the other app logs is its own, as when the host hands it a request
    try:
        await inner(scope, receive, send)
    except Exception as x:  # noqa: BLE001 - as the web server would: the app's own 500, not this caller's traceback
        if over:
            raise
        log.exception("%s failed on %s (asked inside this copy by %s)", app, path, CURRENT.get() or "another app")
        raise urllib.error.HTTPError(f"inside://{app}{path}", 500, f"{app} failed: {type(x).__name__}", out, io.BytesIO(b"")) from x
    finally:
        CURRENT.reset(token)
    url = f"inside://{app}{path}"
    if not 200 <= status < 300:
        raise urllib.error.HTTPError(url, status or 500, out.get("x-reason") or "", out, io.BytesIO(bytes(got)))
    return Answer(url, status, out, bytes(got))


def ask(app: str, path: str, headers: dict = None, body: bytes = None, method: str = None, door: str = doors.WEB,
        host: str = PEER, timeout: float = 15, limit: int = LIMIT) -> Answer:
    """request(), from a thread (where the apps call each other): it runs in the copy's event loop and the answer
    comes back here. LookupError when the app does not run in this copy, or when this is the event loop itself (a
    caller there would hold up the very loop the answer has to come from: it asks over the network instead)."""
    if _LOOP is None or asgi(app) is None:
        raise LookupError(f"{app} does not run in this copy")
    try:
        if asyncio.get_running_loop() is _LOOP:
            raise LookupError("asked from the event loop itself: over the network, so as not to hold it up")
    except RuntimeError:
        pass  # a thread, as it should be
    waiting = asyncio.run_coroutine_threadsafe(
        request(app, path, headers, body, method, door, host, limit), _LOOP)
    try:
        return waiting.result(timeout)
    except (asyncio.TimeoutError, TimeoutError):
        waiting.cancel()
        raise TimeoutError(f"{app} did not answer within {timeout} seconds") from None
    except asyncio.CancelledError:  # the copy is stopping
        raise LookupError(f"{app} stopped answering inside this copy") from None

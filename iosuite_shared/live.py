"""One live-refresh connection per browser, carrying every app's changes.

A page used to learn of a change only by asking again, and only about its own app. Now each page holds one stream
(`GET /api/live`, server-sent events) and gets the changes of every app of the suite on it, so a task ticked off in
ioTask refreshes the start page's Today card, a photo added in ioPix refreshes the strip, and an event moved in
ioCalendar refreshes the calendar in another tab.

An app says what changed, where the change is made:

    live.changed("iocalendar", "events", user_id=None)        # everyone who may see that calendar
    live.changed("ionote", "notes", user_id=7)                # only that person's pages

Most changes need no such line: a request that changed something through an app's API, or from a device that syncs
(CalDAV, CardDAV), is noticed where every request passes (of_request). The apps say it themselves for what arrives
another way: a tool called over MCP (iosuite_shared.mcp), an upload from the phone (ioHealth), the browser extension's
bookmarks (ioStart), and what a job brought in (Monarch Money, a subscribed calendar, new photos on the disk).

The lines go into the Shared ioSuite database (`ios_changes`, a few minutes deep), and each copy of the program has
one reader that picks up the new lines and hands them to the browsers connected to it. So a change in a copy on one
server reaches a page served by a copy on another, and a copy with no page open asks for nothing. Nothing calls
another copy for this.

What a browser is told is only "app X's Y changed" and when: never what changed, so a line is safe for any signed-in
page. Lines addressed to one person (`user_id`) are given only to that person's own pages.
"""
import asyncio
import json
import logging
import os
import secrets
import socket
import time

from iosuite_shared import db

log = logging.getLogger("iosuite_shared.live")

READ_S = 1.0        # how often a copy looks for new lines
BEAT_S = 25.0       # a comment down each stream, so a proxy does not close it
KEEP_S = 300        # how deep the table is kept
QUEUE = 100         # lines held for one browser before the oldest are dropped
RETRY_MS = 3000     # how soon a browser should come back after the stream ends

# This process, as its lines are stamped: its own pages are told in the process, so the reader skips what it wrote.
ORIGIN = f"{socket.gethostname()[:24]}-{os.getpid()}-{secrets.token_hex(3)}"[:40]


def changed(app: str, what: str, user_id: int = None, body: dict = None) -> None:
    """Say that something of `app` changed, for every page of the suite to hear. `what` is a short name the pages
    know ("events", "tasks", "notes", "photos"); `user_id` keeps the line to that person's own pages.

    The pages held by this copy are told at once, in this process, so a change shows in a one-copy install as soon as
    it is made. The line is written to the database for the other copies' pages, off the request's own thread, so a
    change never waits for it. Never raises: a change is still a change when nobody is listening."""
    line = {"id": 0, "at": int(time.time() * 1000), "app": app[:32], "what": what[:48], "user_id": user_id,
            "body": json.dumps(body)[:500] if body else None}
    reader.hand_out(line)
    _write_soon(line)


def _write_soon(line: dict) -> None:
    """The line into the table, in a thread when a request is being answered (the loop must not wait on the
    database), otherwise here and now."""
    def write():
        try:
            db.ex("INSERT INTO ios_changes (at, app, what, user_id, body, origin) VALUES (%s, %s, %s, %s, %s, %s)",
                  (line["at"], line["app"], line["what"], line["user_id"], line["body"], ORIGIN))
        except Exception:  # noqa: BLE001 - the stream is a convenience, never what a change depends on
            log.debug("a change could not be written for the live stream", exc_info=True)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        write()
        return
    loop.run_in_executor(None, write)


# The paths a change on says nothing to a page: signing in, the suite's own screens, the stream itself.
QUIET = ("auth", "suite-admin", "live", "status", "log", "docs", "related", "feeds")
READS = ("GET", "HEAD", "OPTIONS")
# What a device that syncs sends when it changes something (CalDAV, CardDAV). Its reads are requests with a body
# too (PROPFIND, REPORT), so only these count; a POST outside the API says itself when it changed something.
SYNC_WRITES = ("PUT", "DELETE", "PATCH", "PROPPATCH", "MKCOL", "MKCALENDAR", "MOVE", "COPY")


def of_request(app: str, method: str, path: str, api_prefix: str = "/api/") -> None:
    """Called for every request that was answered well (Auth.install's middleware). One that changed something
    through the app's API makes its pages hear "<the first part of the path> changed", which is all a page needs to
    know to ask again; one that changed something from a device that syncs (a calendar or a contact saved on a
    phone) makes them hear "sync". This is why an app needs no code of its own for the live stream; `changed` is for
    what no such request does (an upload, a tool called over MCP, a job)."""
    if method in READS:
        return
    if not path.startswith(api_prefix):
        if method in SYNC_WRITES:
            changed(app, "sync")
        return
    what = path[len(api_prefix):].strip("/").split("/")[0].split("?")[0]
    if not what or what in QUIET:
        return
    changed(app, what)


def forget_old(older_than_s: float = KEEP_S) -> int:
    """Drop the lines a page that reconnects no longer needs (the copy's job runner does this)."""
    return db.ex("DELETE FROM ios_changes WHERE at < %s", (int((time.time() - older_than_s) * 1000),))


class Reader:
    """The copy's one reader of the table, and the browsers connected to this copy. It starts with the first stream
    and stops with the last, so a copy nobody is looking at asks the database for nothing."""

    def __init__(self):
        self.listeners: set = set()
        self._task: asyncio.Task | None = None
        self._loop = None
        self._last = 0

    def join(self, user_id: int) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=QUEUE)
        q.user_id = user_id
        q.loop = asyncio.get_running_loop()   # a change made in another thread is handed over on this one
        self.listeners.add(q)
        self._ensure()
        return q

    def leave(self, q: asyncio.Queue) -> None:
        self.listeners.discard(q)

    def _ensure(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._task is not None and self._loop is loop and not self._task.done():
            return
        self._loop = loop
        self._last = _newest()
        self._task = loop.create_task(self._read(), name="live")

    async def _read(self) -> None:
        while self.listeners:
            try:
                for line in await asyncio.to_thread(self._new):
                    self.hand_out(line)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the database being away never ends the streams
                log.debug("the live reader's round failed (it goes on)", exc_info=True)
            await asyncio.sleep(READ_S)
        self._task = None

    def _new(self) -> list:
        rows = db.q("SELECT id, at, app, what, user_id, body FROM ios_changes WHERE id > %s AND origin <> %s "
                    "ORDER BY id", (self._last, ORIGIN))
        if rows:
            self._last = rows[-1]["id"]
        rows = [r for r in rows if r["at"] > (time.time() - KEEP_S) * 1000]
        return rows

    def hand_out(self, line: dict) -> None:
        """The line to the pages this copy holds. A change can be made anywhere — a request, a job's thread, another
        copy's line — so each stream is handed its line on the loop it is waiting on."""
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        for q in list(self.listeners):
            if line["user_id"] and getattr(q, "user_id", None) != line["user_id"]:
                continue  # a line for one person goes only to that person's pages
            loop = getattr(q, "loop", None)
            if loop is not None and loop is not here:
                try:
                    loop.call_soon_threadsafe(_put, q, line)
                except RuntimeError:  # that loop has closed: the page is gone with it
                    self.listeners.discard(q)
            else:
                _put(q, line)


def _put(q: asyncio.Queue, line: dict) -> None:
    """One line into one page's queue. A page that cannot keep up loses its oldest line, never the newest."""
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        q.put_nowait(line)
    except asyncio.QueueFull:  # pragma: no cover - the drop above makes room
        pass


reader = Reader()


def _newest() -> int:
    """The line a stream starts after: what is there now, so a page is told of changes from its connection on."""
    try:
        r = db.one("SELECT MAX(id) AS id FROM ios_changes")
        return int((r or {}).get("id") or 0)
    except Exception:  # noqa: BLE001
        return 0


# ---- the stream itself
def router(auth):
    """GET /api/live: the one stream a page holds (signed in, on the pages door). Each line is
    {app, what, at} (and `body` when the app sent one), as a server-sent event named "change"."""
    from fastapi import APIRouter, Request
    from fastapi.responses import StreamingResponse

    from iosuite_shared import pages

    r = APIRouter()

    @r.get("/api/live.js", dependencies=[auth.access.public])
    def live_js(request: Request):
        """The page's side of it (static/live.js): onChange(what, fn), the one connection shared by the whole page:
        import { onChange } from './api/live.js'."""
        return pages.send(request, pages.SHARED / "live.js", "text/javascript")

    @r.get("/api/live", dependencies=[auth.access.signed_in])
    async def live(request: Request):
        user = getattr(request.state, "user", None) or {}
        q = reader.join(user.get("id") or 0)

        async def lines():
            yield f"retry: {RETRY_MS}\n\n".encode()
            try:
                while True:
                    try:
                        line = await asyncio.wait_for(q.get(), timeout=BEAT_S)
                    except (TimeoutError, asyncio.TimeoutError):
                        yield b": still here\n\n"       # the heartbeat a proxy needs
                        continue
                    if await request.is_disconnected():
                        return
                    out = {"app": line["app"], "what": line["what"], "at": line["at"]}
                    if line.get("body"):
                        try:
                            out["body"] = json.loads(line["body"])
                        except ValueError:
                            pass
                    yield f"event: change\ndata: {json.dumps(out)}\n\n".encode()
            finally:
                reader.leave(q)

        return StreamingResponse(lines(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no",
                                          "Connection": "keep-alive"})

    return r

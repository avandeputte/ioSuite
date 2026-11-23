"""The host: one copy of the program running the apps it is told to.

    iosuite serve                          the apps the machine's file names (APPS; empty: every app that is installed)
    iosuite serve --apps iopix             a copy of its own for ioPix
    python -m iocalendar                   the same thing for one app

Each app stays what it was, a FastAPI application with its own database and its own start-up and background jobs.
The host loads only the apps it is told to (an app that is not named is not imported, so its packages need not be
there), opens the copy's three doors (iosuite_shared.doors: the pages, what devices sync with, MCP; one port each) and
hands each request to the app it is for: the one whose own name was asked (calendar.example.com), else the one whose
folder the path starts with (/calendar/), else the start page. An app that cannot start (its database is away, a
package is missing) answers "not available" and is tried again every half minute; the others are not held up by it.

Several copies make one suite: every app writes where it is into the Shared ioSuite database (iosuite_shared.suite),
and sign-in, the start page's tiles, search and the links between apps go through that list. A request for an app
that runs in another copy is passed across to it, so every copy answers for the whole suite at its own address.

What the apps of one copy share: the process (they restart together, and an update is the copy's), the listen
address, the ports and the TLS files (the machine's file), the thread pool their blocking work runs on (sized by how
many they are), and one log, each line marked with the app it came from (iosuite_shared.logs).
"""
from __future__ import annotations

import asyncio
import contextvars
import importlib
import importlib.util
import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from iosuite_shared import catalog, certs, config, doors, inside, prefix

log = logging.getLogger("iosuite_shared.host")

RETRY_S = 30.0          # an app that could not start is tried again this often
THREADS_PER_APP = 16    # the thread pool: at least anyio's own 40, more with many apps
SHUTDOWN_GRACE = 3      # a stop waits this long for open requests (event streams stay open as long as a page shows)
STATUS_PATH = "/-/status"  # the copy's own answer, whichever apps it runs (no app has a path that begins /-/)
UNREAD_EVERY_S = 15.0   # started while the Shared ioSuite database was away: looked for this often, then started again

# the app a piece of work belongs to: set for each request and each app's start-up, so its log lines go to its file
CURRENT: contextvars.ContextVar[str] = contextvars.ContextVar("iosuite_app", default="")

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class Entry:
    """One app of this copy."""
    name: str
    asgi: Any = None                 # its FastAPI application, once imported
    state: str = "starting"          # starting | up | failed | stopped
    error: str = ""
    serve: dict[str, Any] = field(default_factory=dict)  # what it asks of the web server (config.SERVE)
    ready: asyncio.Event | None = None
    task: asyncio.Task[None] | None = None


def installed() -> list[str]:
    """Every app whose package is in the program folder, in the suite's order (the heavy ones last)."""
    return [k for k in catalog.install_order() if importlib.util.find_spec(k) is not None]


def names(given: list[str] | None = None) -> list[str]:
    """The apps this copy runs: the ones given, else the machine's APPS, else every app installed; in the suite's order."""
    asked = given or config.APPS or installed()
    unknown = [a for a in asked if a not in catalog.APPS]
    if unknown:
        raise SystemExit(f"no such app: {', '.join(unknown)} (the suite's apps: {', '.join(catalog.APPS)})")
    return [k for k in catalog.install_order() if k in asked]


def load(name: str) -> Entry:
    """Import one app. Never raises: an app that cannot be imported is an entry that says why."""
    e = Entry(name=name)
    token = CURRENT.set(name)
    try:
        cfg = importlib.import_module(f"{name}.config")
        e.serve = dict(getattr(cfg, "SERVE", {}) or {})
        e.asgi = importlib.import_module(f"{name}.main").app
    except BaseException as x:  # noqa: BLE001  SystemExit too: an app's config may refuse a setting
        if isinstance(x, KeyboardInterrupt):
            raise
        e.state, e.error = "failed", f"{type(x).__name__}: {x}"[:300]
        log.exception("%s could not be loaded", name)
    finally:
        CURRENT.reset(token)
    return e


class Host:
    """The ASGI application of a copy: each request to the app it is for, by the door it came in."""

    def __init__(self, entries: list[Entry], ports: dict[int, str] | None = None):
        self.entries = entries
        self.by_name = {e.name: e for e in entries}
        self.local = tuple(e.name for e in entries)
        self.ports = dict(ports if ports is not None else doors.ports())  # port -> door
        self._chores: list = []
        self.table = doors.Table()
        self._reading = asyncio.Lock()
        self._stop: asyncio.Event | None = None

    def door_of(self, scope: Scope) -> str:
        server = scope.get("server")
        return self.ports.get(server[1] if server else 0) or doors.WEB  # a socket it was handed (one app, behind something else): the pages

    async def routes(self) -> doors.Table:
        """The table of names and folders, read again every few seconds. While one request reads it, the others go
        on with what was read before (only the very first read is waited for): a slow database holds nobody up."""
        t = self.table
        if time.time() - t.at >= doors.REFRESH_S:
            if self._reading.locked() and t.at:
                return t
            async with self._reading:
                if time.time() - self.table.at >= doors.REFRESH_S:
                    try:
                        self.table = await asyncio.to_thread(doors.load_table, self.local)
                    except Exception as x:  # noqa: BLE001  the database is away: the folders this copy knows by itself
                        if not t.at:
                            log.warning("the list of apps could not be read (%s): serving this copy's own by their folders", x)
                        self.table = doors.Table(folders={f: k for k, f in catalog.FOLDERS.items()}, hosts=dict(t.hosts), remote=dict(t.remote),
                                                 outer=t.outer, at=time.time())
        return self.table

    def forget_routes(self) -> None:
        """Read the table again on the next request (tests; a setting just changed here)."""
        self.table.at = 0.0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        door = self.door_of(scope)
        if scope["type"] == "http" and scope.get("path") == STATUS_PATH:
            await self._status(scope, send)
            return
        if scope["type"] == "http" and (scope.get("path") or "").startswith(certs.CHALLENGE_PATH):
            await self._proof(scope, send)  # a certificate authority checking that the suite answers at this name
            return
        table = await self.routes()
        from iosuite_shared import proxyauth
        peer = (scope.get("client") or ("",))[0]
        try:
            trusted = proxyauth.Forwarded.allows(peer)
            if not trusted and any(k.lower() == doors.APP_HEADER.encode() for k, _ in scope.get("headers") or []):
                # it says it is a copy passing a request across, and is not on the list of the suite's machines: one
                # that started after the list was read. Read again (at most every few seconds) before saying no.
                trusted = await asyncio.to_thread(proxyauth.Forwarded.allows, peer, True)
        except Exception:  # noqa: BLE001
            trusted = False
        if not trusted and door == doors.WEB and scope["type"] == "http" and scope.get("scheme") == "http" and certs.PAGES_PORT:
            # the pages asked without HTTPS, by one of the certificate's names: sent on to HTTPS. The suite's own
            # servers, a reverse proxy, and whoever asks by another name (the server's address) are served as before.
            where = _to_https(scope)
            if where:
                await doors.redirect(send, 301 if scope.get("method") in ("GET", "HEAD") else 308, where)
                return
        r = doors.route(scope, door, table, trusted, self.local)
        if scope["type"] != "http":
            if scope["type"] == "websocket":  # no app of the suite uses one
                if (await receive())["type"] == "websocket.connect":
                    await send({"type": "websocket.close", "code": 1008})
            return
        if r.redirect:
            await doors.redirect(send, r.status, r.redirect)
            return
        e = self.by_name.get(r.app)
        if not r.app or (e is None and (r.passed or r.app not in table.remote)):
            await doors.plain(send, 404, "No app of the suite answers at this address.\n")
            return
        method = scope.get("method", "GET")
        door = doors.served_as(door, r.app, r.path, method)  # the pages' port answers a device's path or /mcp too, by that door's rules
        if not doors.allowed(door, r.app, r.path, method):
            status, where = doors.elsewhere(door, scope, r.app, r.path, r.folder)
            if status:  # it came in by the wrong door: the right one's address
                await doors.redirect(send, status, where)
                return
            status, text = doors.refusal(door, r.app, r.path)
            await doors.json_answer(send, status, text, door=door)
            return
        if e is None:  # it runs in another copy of the suite
            # that copy's door, or its pages' port, which answers every door's paths as well (doors.served_as)
            upstream = table.remote[r.app].get(door) or table.remote[r.app].get(doors.WEB)
            if not upstream:
                await doors.plain(send, 502, f"{catalog.name_of(r.app)} runs on another server of the suite, which has no door for {doors.NAMES[door]}.\n")
                return
            await doors.across(scope, receive, send, upstream, r)
            return
        if e.state != "up":
            await _unavailable(scope, receive, send, e, r.path)
            return
        inner = dict(scope)
        inner["path"] = r.path
        inner["raw_path"] = r.raw_path or r.path.encode("utf-8")
        inner[prefix.SCOPE_KEY] = r.folder
        inner[doors.SCOPE_ROUTED] = True
        inner[doors.SCOPE_DOOR] = door
        if door != doors.WEB:  # no session here: an app password, a token or the secret in the address is what counts
            inner["headers"] = [(k, v) for k, v in scope.get("headers") or [] if k.lower() != b"cookie"]
        token = CURRENT.set(e.name)
        try:
            await e.asgi(inner, receive, doors.with_folder(send, scope, r.folder))
        finally:
            CURRENT.reset(token)

    async def _proof(self, scope: Scope, send: Send) -> None:
        """/.well-known/acme-challenge/<token>: the proof a certificate authority looks for (iosuite_shared.certs),
        answered by whichever copy is asked: it is in the Shared ioSuite database for the minutes it is needed."""
        try:
            value = await asyncio.to_thread(certs.proof, scope.get("path") or "")
        except Exception:  # noqa: BLE001 - the database is away
            value = None
        if value:
            await doors.plain(send, 200, value)
        else:
            await doors.plain(send, 404, "No certificate is being asked for with this token.\n")

    async def _status(self, scope: Scope, send: Send) -> None:
        """/-/status: whether this copy is serving (a container's health check, a load balancer's): 200 once every
        app has had its start, 503 before. Which app is in which state is told to this machine only."""
        started = all(e.state != "starting" for e in self.entries)
        more = {}
        if (scope.get("client") or ("",))[0] in ("127.0.0.1", "::1"):
            more = {"apps": self.status(), "door": self.door_of(scope)}
        await doors.json_answer(send, 200 if started else 503, "ok" if started else "starting", **more)

    # ---- start-up and shutdown: each app's own, in a task of its own
    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await self.start()
                except Exception as x:  # noqa: BLE001
                    await send({"type": "lifespan.startup.failed", "message": str(x)})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.stop()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def start(self) -> None:
        import anyio.to_thread
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = max(limiter.total_tokens, THREADS_PER_APP * len(self.entries))
        self._stop = asyncio.Event()
        began = time.monotonic()
        for e in self.entries:  # one after another: each makes its tables and may load its demo data
            e.ready = asyncio.Event()
            if e.asgi is None:
                continue
            e.task = asyncio.create_task(self._run(e), name=f"app:{e.name}")
            await e.ready.wait()
        from iosuite_shared import suite
        try:  # what this copy ran before and no longer does leaves the suite's list of apps
            gone = await asyncio.to_thread(suite.left_behind, [e.name for e in self.entries])
            if gone:
                self.forget_routes()
                log.info("no longer run here, taken off the suite's list of apps: %s", ", ".join(gone))
        except Exception as x:  # noqa: BLE001 - the list is a convenience, never a reason not to start
            log.warning("could not look for apps this copy no longer runs: %s", x)
        up = [e.name for e in self.entries if e.state == "up"]
        down = [f"{e.name} ({e.error})" for e in self.entries if e.state != "up"]
        log.info("%d app(s) up in %.1f s: %s%s", len(up), time.monotonic() - began, ", ".join(up) or "none",
                 f"; not available: {'; '.join(down)}" if down else "")
        if config.UNREAD:
            threading.Thread(target=_restart_when_readable, name="settings-unread", daemon=True).start()
        from iosuite_shared import chores, serve
        certs.attach(serve.reload, _restart)
        inside.attach(asyncio.get_running_loop(), self)  # the apps of this copy ask each other in this process
        self._chores.append(chores.start(certs.tick, every_s=certs.EVERY_S, name="certificate", first_s=20,
                                         title="Keep the suite's certificate up to date"))
        self._chores.append(chores.start(_housekeeping, every_s=300, name="housekeeping", first_s=120,
                                         title="Clear what the suite's own tables no longer need"))

    async def _run(self, e: Entry) -> None:
        """The app's lifespan, entered and left in this one task (its task groups require that); tried again while it fails."""
        CURRENT.set(e.name)
        assert self._stop is not None and e.ready is not None
        while not self._stop.is_set():
            try:
                async with e.asgi.router.lifespan_context(e.asgi):
                    e.state, e.error = "up", ""
                    await asyncio.to_thread(_register, e)
                    e.ready.set()
                    await self._stop.wait()
                e.state = "stopped"
                return
            except asyncio.CancelledError:
                raise
            except BaseException as x:  # noqa: BLE001  its start-up failed, or its shutdown did
                if self._stop.is_set():
                    log.warning("%s did not stop cleanly: %s", e.name, x)
                    return
                e.state, e.error = "failed", f"{type(x).__name__}: {x}"[:300]
                log.exception("%s could not start (tried again in %d s)", e.name, RETRY_S)
                e.ready.set()
            try:
                await asyncio.wait_for(self._stop.wait(), RETRY_S)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        if self._stop is None:
            return
        self._stop.set()
        inside.detach()
        for chore in self._chores:
            chore.cancel()
        self._chores.clear()
        tasks = [e.task for e in reversed(self.entries) if e.task is not None]
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=SHUTDOWN_GRACE + 5)
            for t in pending:
                t.cancel()
        await doors.close()

    def status(self) -> list[dict[str, Any]]:
        return [{"app": e.name, "state": e.state, "error": e.error} for e in self.entries]


def _housekeeping() -> str:
    """What the suite's own tables no longer need: the live stream's lines a reconnecting page is past, and the rows
    of jobs no copy has registered for a week (an app that was removed, a job that was renamed)."""
    from iosuite_shared import jobs as jobs_mod, live
    lines, old = live.forget_old(), jobs_mod.forget_old()
    said = ([f"{lines} change lines"] if lines else []) + ([f"{old} job rows"] if old else [])
    return ", ".join(said)


def _register(e: Entry) -> None:
    """The app's row in the suite's list of apps, written as soon as it is up: the other copies of the suite pass its
    requests here from then on, not from the first request somebody happens to make to this copy. Never stops an
    app from starting (its own middleware tries again on a request)."""
    auth = getattr(getattr(e.asgi, "state", None), "iosuite_auth", None)
    if auth is None:
        return
    try:
        auth.register()
    except Exception as x:  # noqa: BLE001
        log.warning("%s could not be registered in the suite's list of apps: %s", e.name, x)


async def _unavailable(scope: Scope, receive: Receive, send: Send, e: Entry | None, path: str | None = None) -> None:
    """503 for an app of this copy that is not up (path: the request's inside the app): a page for a person, a line
    of JSON for what a program asked."""
    if scope["type"] != "http":
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1013})
        return
    name = catalog.name_of(e.name) if e else "This address"
    text = f"{name} is not available right now"
    if e and e.state == "starting":
        text = f"{name} is starting"
    path = path or scope.get("path") or "/"
    if path.startswith("/api/") or path.startswith("/mcp") or (e and doors.under(path, doors.sync_paths(e.name))):
        import json
        body, ctype = json.dumps({"detail": text + "."}).encode(), b"application/json"
    else:
        body = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<meta http-equiv=refresh content=10><title>{text}</title>"
                f"<body style='font:16px system-ui;margin:15vh auto;max-width:28em;padding:0 1em;color:#333'>"
                f"<h1 style='font-size:1.3em'>{text}</h1><p>The server is running, but this app could not start. "
                f"It is tried again every half minute; this page looks again by itself. The server log says why.</p>").encode()
        ctype = b"text/html; charset=utf-8"
    await send({"type": "http.response.start", "status": 503,
                "headers": [(b"content-type", ctype), (b"content-length", str(len(body)).encode()), (b"retry-after", b"15"),
                            (b"cache-control", b"no-store")]})
    await send({"type": "http.response.body", "body": body})


THROUGH_A_PROXY = (b"x-forwarded-for", b"x-forwarded-proto", b"x-forwarded-host", b"forwarded", b"via", b"x-real-ip", b"cf-connecting-ip")


def _to_https(scope: Scope) -> str:
    """Where a request for the pages that came without HTTPS goes when it asked one of the certificate's names: the
    same address over HTTPS. "" for any other name (the server's address, a name of the home network), served as it
    came, and for a request that came through a proxy: one the suite was not told about would be sent round in
    circles, since it asks without HTTPS whatever the visitor did."""
    headers = scope.get("headers") or []
    if any(k.lower() in THROUGH_A_PROXY for k, _ in headers):
        return ""
    host = next((v.decode("latin-1").strip() for k, v in headers if k.lower() == b"host"), "")
    name = (host[1:].split("]")[0] if host.startswith("[") else host.split(":")[0]).lower()
    if not certs.named(name):
        return ""
    raw = scope.get("raw_path") or (scope.get("path") or "/").encode("utf-8")
    query = scope.get("query_string") or b""
    port = "" if certs.PAGES_PORT == 443 else f":{certs.PAGES_PORT}"
    return f"https://{name}{port}{raw.decode('latin-1')}" + (f"?{query.decode('latin-1')}" if query else "")


def _restart() -> None:
    """End the copy shortly: the service manager starts it again (as after an update)."""
    import os
    threading.Timer(1.5, lambda: os._exit(0)).start()  # what asked for it (the panel's button) still gets its answer


def _restart_when_readable() -> None:
    """Apps that started while the Shared ioSuite database was away run on the default settings (config.UNREAD). Once
    the database answers, the copy ends and the service manager starts it again, with the settings as they are stored."""
    import os
    from iosuite_shared import db
    while True:
        time.sleep(UNREAD_EVERY_S)
        try:
            db.init()
            db.q("SELECT 1")
        except Exception:  # noqa: BLE001  still away
            continue
        log.warning("the Shared ioSuite database answers again: starting again to read the settings of %s", ", ".join(sorted(config.UNREAD)))
        os._exit(0)


def wait_for_database(seconds: float = 60.0) -> bool:
    """Before the apps are loaded: give the Shared ioSuite database a moment to come up (a stack whose database
    container starts beside this one). False when it still does not answer: the apps then start on the defaults."""
    from iosuite_shared import db
    end = time.monotonic() + seconds
    said = False
    while True:
        try:
            db.init()
            return True
        except Exception as x:  # noqa: BLE001
            if time.monotonic() >= end:
                return False
            if not said:
                print(f"waiting for the Shared ioSuite database at {config.DB_HOST}:{config.DB_PORT} ({str(x)[:100]})", file=sys.stderr)
                said = True
            time.sleep(1.5)


RUNNING: Host | None = None  # the host of this process, once built


def together(app: str) -> list[str]:
    """The other apps that run in the same copy as this one (they restart with it), by name."""
    if RUNNING is None:
        return []
    return [catalog.name_of(e.name) for e in RUNNING.entries if e.name != app]


def build(given: list[str] | None = None) -> Host:
    """The host for these apps (see names()), each loaded."""
    global RUNNING
    RUNNING = Host([load(n) for n in names(given)])
    return RUNNING


def run(given: list[str] | None = None, wait_s: float = 60.0) -> None:
    """Serve the apps until stopped: `iosuite serve`, and `python -m <app>`."""
    from iosuite_shared import logs, serve
    which = names(given)
    if not which:
        raise SystemExit("no app to run: none is installed in the program folder")
    logs.setup()
    wait_for_database(wait_s)
    certs.start()  # with a certificate (the suite's own, or the machine's files) this copy's doors speak HTTPS
    host = build(which)
    opened = doors.ports()
    if not opened:
        raise SystemExit("no door to open: PORT, SYNC_PORT and MCP_PORT are all off in the machine's file")
    settings: dict[str, Any] = {"timeout_graceful_shutdown": SHUTDOWN_GRACE}
    for e in host.entries:  # what an app asks of the web server: the largest of each wins (ioHealth's long keep-alive)
        for k, v in e.serve.items():
            settings[k] = max(settings[k], v) if k in settings else v
    log.info("%s: %s", ", ".join(which), "; ".join(f"{doors.NAMES[d]} on port {p}" for p, d in opened.items()))
    cert, key = certs.SERVING or (None, None)
    serve.run(host, config.HOST, list(opened), secure=doors.secure_ports(), proxy_headers=False, ssl_certfile=cert, ssl_keyfile=key,
              log_config=None, **settings)

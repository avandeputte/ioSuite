"""The three doors of a copy of the program, and which app a request is for.

A copy listens on three ports (the machine's file: PORT, SYNC_PORT, MCP_PORT; iosuite_shared.host opens them), so a
firewall or a reverse proxy can treat each kind of traffic on its own:

    web   (80)     the pages people open and what the pages ask for: signed in by the session cookie, a passkey, or
                   the sign-in of a reverse proxy. An app password or a token in Authorization is taken here only from
                   inside the network (the apps calling each other); from outside it is ignored.
    sync  (8443)   what phones, native apps and devices talk to: CalDAV and CardDAV (/dav, /.well-known/), calendar
                   subscriptions (/ics/, /cal/), the bookmark sync, ioHealth's uploads
                   (/v1/) and each app's API (/api/) for native apps, widgets and e-ink screens. Signed in by an app
                   password, a token or the secret in the address only: cookies and a proxy's sign-in are not read
                   here, nobody signs in or makes an account here, and no page is served.
    mcp   (8444)   MCP clients: /mcp and nothing else.

What an app serves at the sync door is its manifest's "sync" list of path prefixes, plus /api/. A request that comes
in by the wrong door is sent to the right one (a redirect): a sync or MCP path asked with the pages goes to its own
door, and a page asked at the sync door goes to the pages (a sync client that opens the app in a browser, or the
screen where the person says yes to it: the manifest's "pages", below a sync prefix yet a page). So a phone, a native
app or a browser extension is given one address, the sync door's, and people one, the pages'.

On every door the app is chosen the same way, so both of these work at once and on the same port:

    https://calendar.example.com/…           the app's own name: the hostname of the PUBLIC_URL (or SYNC_URL, MCP_URL)
                                             stored for it
    https://home.example.com/calendar/…      its folder (its manifest's "folder") at any other name; the start page
                                             answers at the root

An app of this copy gets the request directly. One that runs in another copy of the suite (ioPix on a server of its
own) is passed across to that copy's same door, at the address it recorded inside the network (iosuite_shared.suite),
with the headers a reverse proxy sets and X-IoSuite-App naming the app, which the other copy believes from a machine
of the suite; a request that was passed across once is never passed on again.

The app is told the folder it was reached in (iosuite_shared.prefix) and writes its links in that style: a request
that came by the app's own name gets links there, one that came through the folder gets links in the folder.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from iosuite_shared import catalog, config, prefix

log = logging.getLogger("iosuite_shared.doors")

WEB, SYNC, MCP = "web", "sync", "mcp"
NAMES = {WEB: "the pages", SYNC: "devices and native apps", MCP: "MCP"}
SCOPE_DOOR = "iosuite.door"        # which door a request came in by (absent: the app was asked directly, as in its tests)
SCOPE_ROUTED = "iosuite.routed"    # the host settled the app and its folder: the app's own middleware takes them as they are
APP_HEADER = "x-iosuite-app"       # set by a copy passing a request across to the copy that runs the app
DOOR_APP = "iostart"               # the app at the root of an address
MCP_PATH = "/mcp"
WELL_KNOWN = {"/.well-known/caldav": "iocalendar", "/.well-known/carddav": "iocontact"}
REFRESH_S = 5.0
# what belongs to one connection, never passed on (RFC 9110 §7.6.1)
HOP = frozenset(("connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "proxy-connection", "te", "trailer",
                 "transfer-encoding", "upgrade"))
SET_HERE = frozenset(("host", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host", "x-forwarded-prefix", "x-real-ip",
                      "forwarded", "expect", APP_HEADER, "x-iosuite-outside"))  # expect: this server says "100 Continue" itself


def ports() -> dict:
    """{port: door} of the doors this copy opens (a door whose port is 0 is not opened)."""
    return {p: d for d, p in ((WEB, config.PORT), (SYNC, config.SYNC_PORT), (MCP, config.MCP_PORT)) if p}


def port_of(door: str) -> int:
    return {WEB: config.PORT, SYNC: config.SYNC_PORT, MCP: config.MCP_PORT}[door]


def under(path: str, prefixes) -> bool:
    """Whether a path is one of these prefixes or below it ("/dav" covers /dav and /dav/x, never /davx)."""
    for p in prefixes:
        if p.endswith("/"):
            if path.startswith(p) or path == p[:-1]:
                return True
        elif path == p or path.startswith(p + "/"):
            return True
    return False


def sync_paths(app: str) -> tuple:
    """The path prefixes an app serves at the sync door, beside /api/ (its manifest's "sync")."""
    return tuple((catalog.APPS.get(app) or {}).get("sync") or ())


def page_paths(app: str) -> tuple:
    """The paths below a sync prefix that are pages all the same (its manifest's "pages"): the screen a sync client
    opens in a browser for the person to say yes on, which needs their sign-in."""
    return tuple((catalog.APPS.get(app) or {}).get("pages") or ())


def home(app: str, path: str, method: str = "GET") -> tuple:
    """The doors that serve a path of an app, the first being where one that came in elsewhere is sent: MCP for
    /mcp; the sync door for the app's sync paths; both the pages' and the sync door for /api/ (but for signing in
    and changing an account, which is the pages' alone); the pages' door for everything else."""
    if path == MCP_PATH or path.startswith(MCP_PATH + "/"):
        return (MCP,)
    if under(path, sync_paths(app)) and not under(path, page_paths(app)):
        return (SYNC,)
    if path.startswith("/api/") and not (path.startswith("/api/auth/") and method not in ("GET", "HEAD", "OPTIONS")):
        return (WEB, SYNC)
    return (WEB,)


def allowed(door: str, app: str, path: str, method: str = "GET") -> bool:
    """Whether this door serves this path of this app (see the module's text)."""
    return door in home(app, path, method)


def of(request) -> str:
    """The door a request came in by: web, sync or mcp; "" when the app was asked directly (its own tests)."""
    return request.scope.get(SCOPE_DOOR) or ""


# ---- the address of a door, for what an app shows people (the CalDAV address to type into a phone, the MCP address)
def _asked(request) -> tuple:
    """(hostname, scheme) the request named: X-Forwarded-Host and -Proto as the app's middleware settled them."""
    h = request.headers
    host = (h.get("x-forwarded-host") or h.get("host") or request.url.netloc or "").split(",")[0].strip()
    name = host[1:].split("]")[0] if host.startswith("[") else host.split(":")[0]
    return name, (request.url.scheme or "http")


def _named(request, mine: dict, door: str) -> str:
    """Of the addresses stored for an app at a door (its own, its folder at the suite's), the one in the style of this
    request: the one whose name it asked, else its own when it came by the app's own name and the suite's when it
    came through the folder. "" when none is stored."""
    key = "PUBLIC" if door == WEB else door.upper()
    urls = [u for u in mine.get(f"{key}_URLS") or () if u]
    if len(urls) < 2:
        return urls[0] if urls else ""
    name = _asked(request)[0].lower()
    for u in urls:
        if (urlsplit(u).hostname or "").lower() == name:
            return u
    own = mine.get("OWN_URL" if door == WEB else f"{key}_URL_OWN")
    by_folder = bool(prefix.of(request))
    return next((u for u in urls if (u != own) == by_folder), urls[0])


def _at_port(name: str, door: str, path: str) -> str:
    """http(s)://name[:the door's port]path: https only when this server holds the certificate itself (what serves
    HTTPS in front of it has an address of its own for each door: PUBLIC_URL, SYNC_URL, MCP_URL)."""
    scheme = "https" if config.TLS_CERT_FILE and config.TLS_KEY_FILE else "http"
    port = port_of(door)
    shown = "" if port == (443 if scheme == "https" else 80) else f":{port}"
    if ":" in name:
        name = f"[{name}]"
    return f"{scheme}://{name or 'localhost'}{shown}{path}"


def base(door: str, request, app: str) -> str:
    """The address of this app at a door, without a trailing slash: where a phone finds CalDAV
    (base(SYNC, …) + "/dav/"), where an MCP client connects (base(MCP, …) + "/mcp"), where its pages are (base(WEB, …)).

    The address stored for the app at that door (PUBLIC_URL, SYNC_URL, MCP_URL: its own, else its folder at the
    suite's), in the style the request came in on; failing that, the address this request asked: as it is when it
    came in by that door, else with that door's port."""
    mine = config.OF_APP.get(app) or {}
    here = of(request)
    if not here:  # the app asked directly (no host in front, as in its tests): one address for everything
        return prefix.base_url(request, _named(request, mine, WEB))
    named = _named(request, mine, door)
    if named:
        return named.rstrip("/")
    if here == door or not port_of(door):  # asked at that door already: the address it was asked at
        return prefix.base_url(request)
    return _at_port(_asked(request)[0], door, prefix.of(request))


def base_of(door: str, request, app: str) -> str | None:
    """The address of any app of the suite at a door, seen from this request (the Apple profile for several apps): one
    of this copy's as base() says; another copy's from the list of apps: the address stored for it at that door (its
    own, else its folder at the suite's), failing that its usual address with that door's port. None when it has no
    address to give a device (none at all, or only the server's own loopback)."""
    if app in config.OF_APP:
        return base(door, request, app)
    from iosuite_shared import suite
    a = suite.get(app)
    if not a:
        return None
    folder = catalog.FOLDERS.get(app) or ""
    whole = config.suite_setting("PUBLIC_URL" if door == WEB else f"{door.upper()}_URL").rstrip("/")
    own = a.get({WEB: "configuredUrl", SYNC: "syncUrl", MCP: "mcpUrl"}[door])
    named = pick(request, [own, f"{whole}/{folder}".rstrip("/") if whole else ""])
    if named:
        return named.rstrip("/")
    for usual in (a.get("url"), a.get("internalUrl")):
        u = urlsplit(usual or "")
        if u.scheme not in ("http", "https") or u.hostname in (None, "127.0.0.1", "::1", "localhost"):
            continue
        port = port_of(door)
        if door == WEB or not port or not of(request):  # asked without the host in front: one address for everything
            return usual.rstrip("/")
        scheme = "https" if config.TLS_CERT_FILE and config.TLS_KEY_FILE else "http"
        shown = "" if port == (443 if scheme == "https" else 80) else f":{port}"
        name = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
        return f"{scheme}://{name}{shown}{u.path.rstrip('/')}"
    return None


def sync_base(request, app: str) -> str:
    return base(SYNC, request, app)


def mcp_base(request, app: str) -> str:
    return base(MCP, request, app)


def pick(request, urls) -> str:
    """Of an app's public addresses (its own, its folder at the suite's), the one this request came in by: the links
    of an answer stay in the style of the question. The first when the request came by neither (the LAN address)."""
    urls = [u for u in urls if u]
    if len(urls) > 1:
        name, _ = _asked(request)
        for u in urls:
            if (urlsplit(u).hostname or "").lower() == name.lower():
                return u
    return urls[0] if urls else ""


# ---- which app
@dataclass
class Table:
    """What routing needs to know, read from the Shared ioSuite database every few seconds."""
    hosts: dict = field(default_factory=dict)      # hostname -> app: the apps' own names, at any door
    folders: dict = field(default_factory=dict)    # folder -> app
    remote: dict = field(default_factory=dict)     # app -> {web, sync, mcp: where another copy takes it}
    outer: tuple = ("", 0, "")                     # (host, port, folder) of the suite's address when it has a folder itself
    at: float = 0.0


@dataclass
class Route:
    app: str = ""
    folder: str = ""          # what the app is reached in: "/calendar", "" at its own name
    path: str = "/"
    raw_path: bytes = b""
    redirect: str = ""        # send the client here instead (status in `status`)
    status: int = 0
    passed: bool = False      # it came from another copy of the suite: never passed on again


def _hostname(url: str) -> str:
    try:
        return (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return ""


def load_table(local: tuple = ()) -> Table:
    """The table as the Shared ioSuite database has it now. `local`: the apps of this copy (never passed across)."""
    from iosuite_shared import suite
    t = Table(at=time.time())
    for k, f in catalog.FOLDERS.items():
        t.folders[f] = k
    rows = suite.apps()
    for a in rows:
        k = a["app"]
        f = suite.folder_of(k)
        if f and f not in t.folders:
            t.folders[f] = k
        if k != DOOR_APP:  # the start page is the root of every name that is nobody's own
            for u in (a.get("configuredUrl"), a.get("syncUrl"), a.get("mcpUrl")):
                h = _hostname(u) if u and not prefix.clean(urlsplit(u).path) else ""
                if h:
                    t.hosts.setdefault(h, k)
        if k not in local:
            # the copy's door, not the app's folder at it: a request is passed across with its path inside the app
            where = {WEB: _origin(suite.upstream_of(a)), SYNC: _origin(suite.upstream_of(a, "internalSyncUrl")),
                     MCP: _origin(suite.upstream_of(a, "internalMcpUrl"))}
            if any(where.values()):
                t.remote[k] = where
    for k in local:  # this copy's own, as their settings say (they may not have registered yet)
        mine = config.OF_APP.get(k) or {}
        if k != DOOR_APP:
            for u in (mine.get("OWN_URL"), mine.get("SYNC_URL_OWN"), mine.get("MCP_URL_OWN")):
                h = _hostname(u) if u and not prefix.clean(urlsplit(u).path) else ""
                if h:
                    t.hosts[h] = k
    t.outer = prefix.of_url(config.suite_setting("PUBLIC_URL"))
    return t


def _origin(url) -> str | None:
    """scheme://host:port of an address (None for none)."""
    if not url:
        return None
    u = urlsplit(url)
    return f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else None


def _headers(scope: dict) -> dict:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}


def route(scope: dict, door: str, table: Table, trusted: bool, local: tuple) -> Route:
    """Which app this request is for, the folder it is reached in and its path inside the app."""
    h = _headers(scope)
    path = scope.get("path") or "/"
    raw = scope.get("raw_path") or b""
    query = (scope.get("query_string") or b"").decode("latin-1")
    if trusted and h.get(APP_HEADER):  # another copy settled it
        return Route(app=h[APP_HEADER].strip().lower(), folder=prefix.clean((h.get("x-forwarded-prefix") or "").split(",")[0]),
                     path=path, raw_path=raw, passed=True)
    name, asked = prefix._host(h if trusted else {"host": h.get("host", "")})
    app = table.hosts.get(name)
    if app:  # its own name: the app at the root (or in the folder a proxy in front says it took off)
        return Route(app=app, folder=prefix.clean((h.get("x-forwarded-prefix") or "").split(",")[0]) if trusted else "", path=path, raw_path=raw)
    outer = ""
    if trusted:
        outer = prefix.clean((h.get("x-forwarded-prefix") or "").split(",")[0])
    if not outer and table.outer[2] and name == table.outer[0] and asked in (None, table.outer[1]):
        outer = table.outer[2]
    if outer:
        if path == outer:
            return Route(redirect=outer + "/" + ("?" + query if query else ""), status=308)
        if path.startswith(outer + "/"):
            path = path[len(outer):]
            enc = outer.encode("latin-1")
            raw = raw[len(enc):] if raw.startswith(enc + b"/") else b""
    if path in WELL_KNOWN:  # a phone asking this name for its calendar or contacts account
        return Route(app=WELL_KNOWN[path], folder=f"{outer}/{catalog.FOLDERS.get(WELL_KNOWN[path], '')}".rstrip("/"), path=path, raw_path=raw)
    first, slash, _rest = path[1:].partition("/")
    app = table.folders.get(first) if first else None
    if app is None:
        if DOOR_APP in local or DOOR_APP in table.remote:
            return Route(app=DOOR_APP, folder=outer, path=path, raw_path=raw)
        if path == "/" and local:  # no start page anywhere: the first app of this copy
            f = catalog.FOLDERS.get(local[0])
            return Route(redirect=f"{outer}/{f}/", status=307) if f else Route(app=local[0], folder=outer, path=path, raw_path=raw)
        return Route()
    if not slash:  # /calendar: the page's relative addresses need /calendar/
        return Route(redirect=f"{outer}/{first}/" + ("?" + query if query else ""), status=308)
    cut = len(first) + 1
    enc = raw[cut:] if raw.startswith(f"/{first}/".encode("latin-1")) else b""
    return Route(app=app, folder=f"{outer}/{first}", path=path[cut:], raw_path=enc)


# ---- answers of the host itself
async def plain(send, status: int, text: str, headers=()) -> None:
    body = text.encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode()),
                            (b"cache-control", b"no-store"), *headers]})
    await send({"type": "http.response.body", "body": body})


async def json_answer(send, status: int, detail: str, **more) -> None:
    import json
    body = json.dumps({"detail": detail, **more}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]})
    await send({"type": "http.response.body", "body": body})


async def redirect(send, status: int, where: str) -> None:
    await plain(send, status, "", [(b"location", where.encode("latin-1"))])


def location(value: str, hosts: set, folder: str) -> str:
    """An app's redirect to a place on this address that lost its folder: Starlette's own trailing-slash redirect
    builds it from the request, where the folder is not the root path (iosuite_shared.prefix). The folder goes back
    in front; a redirect elsewhere, relative to the page, or already in the folder stays as it is."""
    p = urlsplit(value)
    if p.scheme or p.netloc:
        if p.netloc.lower() not in hosts:
            return value
    elif not value.startswith("/"):
        return value
    if p.path == folder or p.path.startswith(folder + "/"):
        return value
    return urlunsplit((p.scheme, p.netloc, folder + (p.path or "/"), p.query, p.fragment))


def with_folder(send, scope: dict, folder: str):
    """`send` for an app served in a folder: a redirect of its own that lost the folder gets it back."""
    if not folder:
        return send
    h = _headers(scope)
    hosts = {h.get(n, "").split(",")[0].strip().lower() for n in ("host", "x-forwarded-host")} - {""}

    async def fixed(message):
        if message.get("type") == "http.response.start" and 300 <= message.get("status", 0) < 400:
            message = dict(message)
            message["headers"] = [(k, location(v.decode("latin-1"), hosts, folder).encode("latin-1") if k.lower() == b"location" else v)
                                  for k, v in message.get("headers") or []]
        await send(message)
    return fixed


# ---- passing a request across to the copy that runs the app
_client = None


def client():
    global _client
    if _client is None:
        import httpx2
        # no pool limit to queue behind and no read timeout to cut a live stream; a dead copy is noticed on connect.
        # trust_env off: the copies are on this network, never behind the machine's HTTP proxy
        _client = httpx2.AsyncClient(timeout=httpx2.Timeout(10, read=None, write=None, pool=None), follow_redirects=False, trust_env=False,
                                     limits=httpx2.Limits(max_connections=None, max_keepalive_connections=32))
        for name in ("accept", "accept-encoding", "user-agent"):  # the visitor's own or none: nothing asked for in their name
            _client.headers.pop(name, None)
    return _client


async def close() -> None:
    global _client
    c, _client = _client, None
    if c is not None:
        await c.aclose()


def _across_headers(scope: dict, app: str, folder: str) -> list:
    """The request's headers as the other copy gets them: the way a reverse proxy tells where a request came from, and
    the app it is for. What a proxy names the signed-in person with, and the visitor's address as Cloudflare gives
    it, are taken off unless the request came from a proxy the suite trusts: the other copy sees this machine as the
    sender, and must not take a visitor's own header for the proxy's word."""
    from iosuite_shared import proxyauth
    proxy = proxyauth.Proxy(app)
    got = [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in scope.get("headers") or []]
    named = {k: v for k, v in got}
    peer = (scope.get("client") or ("",))[0]
    from_proxy = proxy.from_trusted(peer)
    drop = set(HOP) | SET_HERE
    for name in (named.get("connection") or "").split(","):  # what the sender tied to its own connection
        drop.add(name.strip().lower())
    if "transfer-encoding" in named:  # sent in pieces: a length beside it is not the body's (and h11 would refuse it)
        drop.add("content-length")
    if not from_proxy:
        drop.update(x.lower() for x in (*proxyauth.GENERIC_HEADERS, proxyauth.CF_HEADER, *proxy.headers(), "cf-connecting-ip"))
    out = [(k, v) for k, v in got if k not in drop]
    host = named.get("host") or ""
    trusted = proxyauth.Forwarded.allows(peer)
    out.append(("host", host))
    out.append(("x-forwarded-host", ((named.get("x-forwarded-host") if trusted else "") or host).split(",")[0].strip()))
    proto = (named.get("x-forwarded-proto") or "").split(",")[0].strip().lower() if trusted else ""
    out.append(("x-forwarded-proto", proto if proto in ("http", "https") else "https" if scope.get("scheme") in ("https", "wss") else "http"))
    out.append(("x-forwarded-for", ", ".join(x for x in (named.get("x-forwarded-for") if trusted else "", peer) if x)))
    out.append(("x-forwarded-prefix", folder))
    out.append((APP_HEADER, app))
    if proxy.external(named, peer):
        out.append((proxyauth.OUTSIDE_HEADER, "1"))
    return out


async def across(scope: dict, receive, send, upstream: str, r: Route) -> None:
    """Pass the request on to the copy at `upstream` as it came: any method (CalDAV's PROPFIND and REPORT), the body
    as it arrives (an upload is never held here), the answer as it is produced (a video's ranges, a live stream, MCP)."""
    import httpx2
    name = catalog.name_of(r.app)
    query = (scope.get("query_string") or b"").decode("latin-1")
    raw = r.raw_path.decode("latin-1") if r.raw_path else quote(r.path, safe="/:@!$&'()*+,;=-._~")
    url = upstream + raw + (f"?{query}" if query else "")
    try:  # the proxy settings come from the Shared ioSuite database (cached): read off the event loop
        headers = await asyncio.to_thread(_across_headers, scope, r.app, r.folder)
    except Exception as e:  # noqa: BLE001 - the database is away: this request, plainly, not a traceback
        log.warning("could not read the proxy settings (%s)", e)
        return await plain(send, 503, "The Shared ioSuite database does not answer: try again in a moment.\n")
    gone = asyncio.Event()  # the client went away
    sent = {k.decode("latin-1").lower(): v for k, v in scope.get("headers") or []}
    has_body = "transfer-encoding" in sent or sent.get("content-length", b"0").strip() not in (b"", b"0")
    done_reading = asyncio.Event()

    async def body():
        while True:
            m = await receive()
            if m["type"] == "http.disconnect":
                gone.set()
                raise ConnectionError("the client went away while sending")
            if m.get("body"):
                yield m["body"]
            if not m.get("more_body"):
                done_reading.set()
                return

    if not has_body:
        done_reading.set()
    try:
        req = client().build_request(scope["method"], url, headers=headers, content=body() if has_body else None)
        resp = await client().send(req, stream=True)
    except httpx2.InvalidURL:  # a path longer than any app takes
        return await plain(send, 414, "That address is too long.\n")
    except (httpx2.ConnectError, httpx2.ConnectTimeout) as e:
        log.info("%s is not answering at %s (%s)", name, url.split("/", 3)[2], e)
        return await plain(send, 502, f"{name} is not answering. It may be starting or updating: try again in a moment.\n")
    except (httpx2.HTTPError, ConnectionError, OSError) as e:
        if gone.is_set():
            return
        log.warning("passing %s %s on failed: %s", scope["method"], scope.get("path"), e)
        return await plain(send, 502, f"{name} could not be reached.\n")

    async def watch():  # a live stream ends when the client leaves, not when the app has something to say
        await done_reading.wait()
        while True:
            m = await receive()
            if m["type"] == "http.disconnect":
                gone.set()
                return

    watcher = asyncio.ensure_future(watch())
    try:
        # date and server: this server writes its own
        out = [(k.lower(), v) for k, v in resp.headers.raw if k.decode("latin-1").lower() not in HOP and k.lower() not in (b"date", b"server")]
        await send({"type": "http.response.start", "status": resp.status_code, "headers": out})
        chunks = resp.aiter_raw().__aiter__()
        while True:
            nxt = asyncio.ensure_future(chunks.__anext__())
            await asyncio.wait({nxt, watcher}, return_when=asyncio.FIRST_COMPLETED)
            if not nxt.done():  # the client left first
                nxt.cancel()
                try:
                    await nxt
                except (asyncio.CancelledError, StopAsyncIteration, httpx2.HTTPError, OSError):
                    pass
                return
            try:
                chunk = nxt.result()
            except StopAsyncIteration:
                break
            if chunk:
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
    except (httpx2.HTTPError, OSError) as e:  # the other copy went away mid-answer: the connection is cut, as it would be without us
        if not gone.is_set():
            log.info("%s stopped answering mid-way on %s: %s", name, scope.get("path"), e)
        return  # one line, no traceback: the answer is left unfinished, so the server closes the connection
    finally:
        watcher.cancel()
        await resp.aclose()


def address_of(door: str, scope: dict, app: str, folder: str) -> str:
    """Where this app's door is, from a request the host is answering itself (no Request yet): the stored address,
    else the name asked with the door's port, in the folder the request came through."""
    mine = config.OF_APP.get(app) or {}
    key = "PUBLIC" if door == WEB else door.upper()
    urls = [u for u in mine.get(f"{key}_URLS") or () if u]
    h = _headers(scope)
    host = (h.get("host") or "").split(",")[0].strip()
    name = host[1:].split("]")[0] if host.startswith("[") else host.split(":")[0]
    named = next((u for u in urls if _hostname(u) == name.lower()), None)
    if named is None and urls:
        own = mine.get("OWN_URL" if door == WEB else f"{key}_URL_OWN")
        named = next((u for u in urls if (u != own) == bool(folder)), urls[0])
    if named:
        return named.rstrip("/")
    return _at_port(name, door, folder)


def elsewhere(door: str, scope: dict, app: str, path: str, folder: str) -> tuple:
    """(status, address) to send a request to that came in by a door which does not serve its path, or (0, "") when
    it is refused where it is. From the pages' door, a sync or MCP path goes to its own door whatever the method
    (307: the request is made again as it was). From the sync door, a page a person's browser asked for goes to the
    pages' door. A phone looking an account up (/.well-known/caldav) is sent to where it syncs."""
    method = scope.get("method", "GET")
    to = home(app, path, method)[0]
    if to == door or (not port_of(to) and not (config.OF_APP.get(app) or {}).get(f"{'PUBLIC' if to == WEB else to.upper()}_URLS")):
        return 0, ""
    if door == MCP or (door == SYNC and method not in ("GET", "HEAD")):
        return 0, ""
    where = address_of(to, scope, app, folder)
    if path in WELL_KNOWN:
        return 301, where + "/dav/"
    query = scope.get("query_string") or b""
    return 307, where + quote(path, safe="/%:@!$&'()*+,;=~-._") + ("?" + query.decode("latin-1") if query else "")


def refusal(door: str, app: str, path: str) -> tuple:
    """(status, what to say) for a path this door does not serve and that is not sent on."""
    name = catalog.name_of(app)
    if door == WEB:
        other = MCP if (path == MCP_PATH or path.startswith(MCP_PATH + "/")) else SYNC
        return 404, f"{name} serves this at its door for {NAMES[other]} (port {port_of(other) or 'not opened on this server'}), not with the pages."
    return 404, f"This port is {name}'s door for {NAMES[door]}: this address is not served here."


def state() -> list[dict[str, Any]]:
    """The doors of this copy, for status pages."""
    return [{"door": d, "port": port_of(d), "for": NAMES[d]} for d in (WEB, SYNC, MCP)]

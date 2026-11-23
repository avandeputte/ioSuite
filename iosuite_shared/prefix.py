"""An app served in a folder of an address instead of at its root: https://home.example.com/calendar/ beside
https://home.example.com/notes/, the whole suite on one address and one port.

The app's own routes do not change (/api/…, /dav/…, /static/…): the folder is taken off the path before they see it,
and what the app writes into its answers (the links of CalDAV and CardDAV, redirects, the addresses it shows) starts
with it. The page itself asks for everything with relative addresses (api/events, static/app.js), so it works in any
folder as it is.

Which folder a request came through: the host that runs the app says (iosuite_shared.doors: it chose the app by its
own name, or by its folder, and tells it which). An app asked directly, with no host in front (its own tests, or
`uvicorn iocalendar.main:app` behind something else), finds it itself, in this order:

  1. `X-Forwarded-Prefix: /calendar` from this machine or a listed reverse proxy (proxyauth.forwarders()), the header
     a copy of the suite sends when it passes a request across and Traefik's StripPrefix adds;
  2. the path of one of its public addresses (https://home.example.com/calendar), when the request names that host
     (and, if it names a port, that port).

`of(request)` is that folder ("/calendar", or "" at the root). It is not the ASGI root_path: Starlette's mounts
(/static, /mcp) would look for the folder on the path the routes see. Only FastAPI's docs page and OpenAPI document
get it as root_path, which is how they find their own addresses.
"""
import re
from urllib.parse import urlsplit

SCOPE_KEY = "iosuite.prefix"
_SEGMENTS = re.compile(r"(/[A-Za-z0-9._~-]+)+")


def clean(value) -> str:
    """"/calendar" from "calendar/", " /calendar " …; "" for nothing, the root, or anything that is not plain path
    segments (it goes into links and a Location header)."""
    value = (value or "").strip()
    p = "/" + value.strip("/")
    return p if p != "/" and len(p) <= 128 and "//" not in value and "/." not in p and _SEGMENTS.fullmatch(p) else ""


def of_url(url) -> tuple:
    """(host, port, folder) of an address: ("home.example.com", 443, "/calendar"); ("", 0, "") when it has no folder."""
    try:
        u = urlsplit((url or "").strip())
        folder = clean(u.path)
        if not (folder and u.hostname and u.scheme in ("http", "https")):
            return ("", 0, "")
        return (u.hostname.lower(), u.port or (443 if u.scheme == "https" else 80), folder)
    except ValueError:
        return ("", 0, "")


def _host(headers: dict) -> tuple:
    """(host, port or None) the request names: X-Forwarded-Host, else Host."""
    h = (headers.get("x-forwarded-host") or headers.get("host") or "").split(",")[0].strip().lower()
    name, port = h, ""
    if h.startswith("["):
        name, _, rest = h[1:].partition("]")
        port = rest.lstrip(":")
    elif h.count(":") == 1:
        name, port = h.split(":")
    return name, (int(port) if port.isdigit() else None)


def resolve(headers: dict, trusted: bool, public_url: str = "") -> str:
    """The folder this request came through (see the module's text). `headers`: lower-case names; `trusted`: the
    connection is from this machine or a listed reverse proxy; `public_url`: the app's PUBLIC_URL."""
    if trusted:
        named = clean((headers.get("x-forwarded-prefix") or "").split(",")[0])
        if named:
            return named
    host, port, folder = of_url(public_url)
    if not folder:
        return ""
    name, asked = _host(headers)
    # the same name on another port is the app's own (http://server.lan:8620 beside http://server.lan/calendar); a
    # proxy that passes the name on without its port (nginx's $host) still counts
    return folder if name == host and asked in (None, port) else ""


def apply(scope: dict, folder: str, rooted: tuple = ()) -> str | None:
    """Note the folder on the ASGI scope and take it off the path when the proxy left it there. Returns the address
    to send the browser to instead, for the folder asked for without its slash (/calendar): the page's relative
    addresses need /calendar/. `rooted`: the paths that get the folder as their ASGI root_path (FastAPI's docs)."""
    scope[SCOPE_KEY] = folder
    if not folder:
        return None
    path = scope.get("path") or "/"
    if path == folder:
        q = scope.get("query_string") or b""
        return folder + "/" + ("?" + q.decode("latin-1") if q else "")
    if path.startswith(folder + "/"):
        scope["path"] = path[len(folder):]
        raw = scope.get("raw_path")
        enc = folder.encode("latin-1")
        if raw and raw.startswith(enc + b"/"):
            scope["raw_path"] = raw[len(enc):]
    if scope["path"] in rooted:
        scope["root_path"] = folder
    return None


def of(request) -> str:
    """The folder the app is served in for this request: "/calendar", or "" at the root."""
    return request.scope.get(SCOPE_KEY) or ""


def base_url(request, public_url: str = "") -> str:
    """The address links are made with, without a trailing slash: PUBLIC_URL, else what the proxy (or the client)
    says, kept to a scheme and a host[:port] (a forged header only changes the links in that client's own answer,
    but it stays an address), and the folder the app is served in."""
    if public_url:
        return public_url.rstrip("/")
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").split(",")[0].strip().lower()
    proto = proto if proto in ("http", "https") else "http"
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc or "").split(",")[0].strip()
    if not re.fullmatch(r"[A-Za-z0-9.\-]+(:\d{1,5})?|\[[0-9A-Fa-f:.]+\](:\d{1,5})?", host):
        host = request.url.netloc if re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", request.url.netloc or "") else "localhost"
    return f"{proto}://{host}{of(request)}"

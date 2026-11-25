"""The page every app serves at its root, its manifest and its static folder (ioStart and ioPix add their own), and
how the suite sends its scripts and style sheets: compressed for a browser that takes that, answered 304 when the
browser's copy is still the file, and kept for good where the address says which file it is.

    static/app.js?v=3f9c01ab7e    the page names its script and style sheets with a mark of what is in them (stamp()),
                                  so the browser, and Cloudflare, keep them without asking again, and an update, which
                                  changes the mark, is fetched at once
    static/js/*.js, api/auth/*.js imported by name, without a mark: asked for each time (no-cache), 304 when unchanged,
                                  so an update never pairs one module with another kept from the version before
"""
import functools
import gzip
import hashlib
from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

SHARED = Path(__file__).with_name("static")
PUBLIC = SHARED / "public"  # served in every app's /static, after the app's own files
STAMPED = ("static/app.js", "static/app.css", "static/js/theme.js", "api/auth/base.css")
TEXT = (".js", ".css", ".html", ".svg", ".json", ".webmanifest", ".txt")  # what is worth compressing
SMALL = 1024  # under this, compressing saves nothing
FOR_GOOD = "public, max-age=31536000, immutable"


@functools.lru_cache(maxsize=1024)
def _read(path: str, mtime_ns: int, size: int) -> tuple:
    """(the file, its mark, the file compressed or None), read once for as long as the file stays as it is."""
    raw = Path(path).read_bytes()
    packed = gzip.compress(raw, compresslevel=6, mtime=0) if len(raw) >= SMALL and path.endswith(TEXT) else None
    return raw, hashlib.sha256(raw).hexdigest()[:10], packed


def _file(file: Path) -> tuple:
    st = file.stat()
    return _read(str(file), st.st_mtime_ns, st.st_size)


def mark(file: Path) -> str:
    """Ten characters that change when the file does: the ?v= on its address."""
    return _file(file)[1]


def stamp(html: str, static_dir: Path) -> str:
    """The page with a mark on its script and style sheets ("static/app.js" becomes "static/app.js?v=<mark>")."""
    for f in STAMPED:
        file = SHARED / f.rsplit("/", 1)[1] if f.startswith("api/auth/") else Path(static_dir) / f.split("/", 1)[1]
        if file.is_file():
            html = html.replace(f'"{f}"', f'"{f}?v={mark(file)}"')
    return html


def _keeping(asked: str | None, file: Path) -> str:
    """For good when the address carries this file's mark; else asked for again each time."""
    return FOR_GOOD if asked and asked == mark(file) else "no-cache"


def _takes_gzip(headers) -> bool:
    return "gzip" in (headers.get("accept-encoding") or "").lower()


def _asked_v(scope) -> str | None:
    for part in scope.get("query_string", b"").decode("latin-1").split("&"):
        if part.startswith("v="):
            return part[2:]
    return None


def send(request, file: Path, media_type: str) -> Response:
    """One of the suite's own files (a script, a style sheet) at a route: 304 when the browser's copy is still it,
    compressed when the browser takes that, kept for good when asked for by its mark."""
    raw, tag, packed = _file(file)
    etag = f'"{tag}"'
    headers = {"ETag": etag, "Cache-Control": _keeping(request.query_params.get("v"), file), "Vary": "Accept-Encoding"}
    if etag in [t.strip(" W/") for t in (request.headers.get("if-none-match") or "").split(",")]:
        return Response(status_code=304, headers=headers)
    if packed and _takes_gzip(request.headers):
        return Response(packed, media_type=media_type, headers={**headers, "ETag": "W/" + etag, "Content-Encoding": "gzip"})
    return Response(raw, media_type=media_type, headers=headers)


class Static(StaticFiles):
    """/static: as StaticFiles answers (304 when unchanged, ranges), with the text files compressed for a browser
    that takes that, and Cache-Control said for each: for good when asked for by its mark, else no-cache. Beside the
    app's own files it has what the suite keeps once for every app (static/public here: static/vendor/leaflet, the
    maps of ioPix and ioHealth), so an app serves it from wherever it runs."""

    def __init__(self, *, directory, **kw):
        super().__init__(directory=directory, **kw)
        self.all_directories = [*self.all_directories, PUBLIC]   # the app's own first

    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        full, _ = self.lookup_path(path)
        if r.status_code not in (200, 304) or not full or not Path(full).is_file():
            return r
        file = Path(full)
        r.headers["Cache-Control"] = _keeping(_asked_v(scope), file)
        if not full.endswith(TEXT):
            return r
        r.headers["Vary"] = "Accept-Encoding"
        asked = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers", [])}
        packed = _file(file)[2]
        if r.status_code != 200 or scope.get("method") != "GET" or "range" in asked or not packed or not _takes_gzip(asked):
            return r
        keep = {k: r.headers[k] for k in ("last-modified", "cache-control", "vary") if k in r.headers}
        return Response(packed, media_type=r.media_type, headers={**keep, "ETag": "W/" + r.headers["etag"], "Content-Encoding": "gzip"})


def mount(app, static_dir: Path, service_worker: bool = False, dependencies=()) -> None:
    """GET / (index.html with a mark on its script and style sheets: stamp()), the manifest, /sw.js at the root when
    the app has one (its scope is then the whole app), and /static. `dependencies`: the access marker these routes
    declare, like every other route of the app (iosuite_shared.access: the page is public)."""
    static_dir = Path(static_dir)
    marked = list(dependencies)

    @app.get("/", include_in_schema=False, dependencies=marked)
    def index():
        return HTMLResponse(stamp((static_dir / "index.html").read_text(encoding="utf-8"), static_dir), headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest", include_in_schema=False, dependencies=marked)
    def manifest():
        return FileResponse(static_dir / "manifest.webmanifest", media_type="application/manifest+json")

    if service_worker:
        @app.get("/sw.js", include_in_schema=False, dependencies=marked)
        def sw():
            return FileResponse(static_dir / "sw.js", media_type="text/javascript")

    app.mount("/static", Static(directory=static_dir), name="static")

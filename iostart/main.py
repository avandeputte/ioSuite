"""ioStart: the application (what is its own: its tables and jobs, what a device may ask without an account, its
routes and its two pages; the rest is every app's: iosuite_shared.application).

Who may call a route is declared on the route (iostart/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from fastapi.responses import FileResponse, HTMLResponse
from iosuite_shared import application, mcp as shared_mcp, pages, users

from iostart import __version__, api, appsignin, bookmarks, config, db, keys, mcp, news, timers
from iostart.bookmarks import api as bookmarksapi, ext as bookmarkext
from iostart.homeassistant import api as haapi
from iostart.news import api as newsapi
from iostart.trmnl import api as trmnlapi, push as trmnlpush
from iostart.auth import auth, updater

# a TRMNL e-ink device set to this server (iostart/trmnl/server.py) has no account: it signs its requests with its own key
TRMNL_DEVICE = {("GET", "/api/setup"), ("GET", "/api/display"), ("GET", "/api/current_screen"), ("POST", "/api/log")}


def _device_asks(request) -> bool:
    return (request.method, request.url.path) in TRMNL_DEVICE or (request.method == "GET" and request.url.path.startswith("/api/trmnl/image/"))


# Settings › Apps › MCP: this app's switch in the Shared ioSuite database, the suite's one unless it says otherwise
mcp_switch = shared_mcp.Switch(config.APP,
                               "The suite's one MCP server: an AI assistant connected here with an ioStart app password uses every "
                               "app's tools as you (each app's own MCP server has to be on), and suite admins can update every app at once.")
mcp_enabled = mcp_switch.enabled


def _jobs() -> list:
    """The copy's jobs (Settings › Servers › Jobs): the "timer done" notifications (iostart/timers.py), the feeds
    people follow (iostart/news/__init__.py), the screens pushed to TRMNL's cloud (iostart/trmnl/push.py)."""
    return [j for j in (timers.job(), news.job(), trmnlpush.job()) if j]


def _limit_for(path: str, ctype: str) -> int:
    return config.MAX_IMPORT_BYTES if "/import" in path or path.endswith("/api/news/opml") or path.startswith("/dav/") else config.MAX_JSON_BYTES


app = application.create(
    auth, updater, __version__, config,
    description="The start page of ioSuite: one place with every io app, and the accounts they share.",
    prepare=(db.migrate, users.init,
             bookmarks.claim_unowned,  # bookmarks nobody owns become the first admin's
             keys.declare),            # the Home Assistant token and AccuWeather key live with the suite's keys and tokens
    jobs=_jobs,
    mcp=mcp, mcp_enabled=mcp_enabled,
    before=auth.mcp_gate(mcp_enabled, on_user=mcp.current_user.set, on_request=mcp.remember_sign_in),
    # what a visitor may still fetch when sign-in is required, beside what app.json lists as sync (/dav/: the
    # extension's sync answers 401 with a Basic challenge itself, and the sign-in flow for apps starts before anyone
    # is signed in): the Bookmarks page; a wall display asks for its pairing code before it has a sign-in (approving
    # one takes a signed-in person: its route says so)
    open_paths=("/bookmarks", "/bookmarks.webmanifest"), open_prefixes=("/api/wall/pair",),
    middleware={"is_open": _device_asks},
    limit_for=_limit_for, related=False,
    routers=(api.router,           # the apps and the layout, the weather, the search, the tiles, the timers, the wall display
             haapi.router,         # /api/ha: the Home Assistant card
             bookmarksapi.router,  # /api/bookmarks, /api/groups, /api/links: the bookmarks
             trmnlapi.router,      # /api/trmnl, and what a TRMNL device asks (/api/setup, /api/display...)
             newsapi.router,       # /api/news: the feed reader (the Feeds page) and the headlines card
             appsignin.router,     # /dav/nextcloud/index.php/login/v2: how the extension and the iPhone app sign in
             bookmarkext.router),  # /dav/ext: the ioStart Bookmarks browser extension (static/extension/)
    page=False)  # two pages (the start page and Bookmarks), served below


def _page(swap: dict[str, str] | None = None) -> HTMLResponse:
    """The page, with a mark on its script and style sheets (pages.stamp): after an update the browser (and
    Cloudflare, which caches .js and .css at the edge) fetches the new ones instead of serving what it kept."""
    html = pages.stamp((config.STATIC_DIR / "index.html").read_text(encoding="utf-8"), config.STATIC_DIR)
    for a, b in (swap or {}).items():
        html = html.replace(a, b)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
def index():
    return _page()


@app.get("/bookmarks", include_in_schema=False)
def bookmarks_app():
    """The Bookmarks page as an app of its own: the same page, opening on the bookmarks, with its own name, icon and
    manifest, so "Add to Home Screen" (iPhone, iPad) or "Install" (desktop, Android) makes a Bookmarks icon that opens
    straight on them, without the browser around it."""
    return _page({
        "<title>ioStart</title>": "<title>Bookmarks</title>",
        '<meta name="apple-mobile-web-app-capable" content="yes">':
            '<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="apple-mobile-web-app-title" content="Bookmarks">',
        'href="static/icons/apple-touch-icon.png"': 'href="static/icons/bookmarks-180.png"',
        'href="static/icons/mark.svg" type="image/svg+xml"': 'href="static/icons/bookmarks.svg" type="image/svg+xml"',
        'href="manifest.webmanifest"': 'href="bookmarks.webmanifest"',
    })


def _manifest(name: str):
    return FileResponse(config.STATIC_DIR / name, media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return _manifest("manifest.webmanifest")


@app.get("/bookmarks.webmanifest", include_in_schema=False)
def bookmarks_manifest():
    return _manifest("bookmarks.webmanifest")


app.mount("/static", pages.Static(directory=config.STATIC_DIR), name="static")

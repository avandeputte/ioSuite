"""ioPix: a web front end for a digiKam library.

Who may call a route is declared on the route (iopix/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite. The library (digiKam's database and the photo files) is only read here; the few endpoints that change it
(sidecars, image files, digiKam's database on request) declare access.editor_write or access.admin_write on their route
and go through the modules that own those writes."""
import logging
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi import HTTPException
from iosuite_shared import chores, demo as suite_demo, mcp as shared_mcp, pages
from iosuite_shared.fastapi import public_user
from iosuite_shared.updates import setup_log

from iopix.ai import analysis, models as dlmodels
from iopix.faces import facedetect, facemgr
from iopix import access, config, events, jobs as bgjobs, mcp, suiteitems, thumbs, users
from iopix.auth import auth, updater
from iopix.photos import consistency, edits, history, lossless, scanner, tagmanager
from iopix.data import index as photo_index, state as appstate, appdb
from iopix.digikam import dkdb
from iopix.geo import maps, places
from iopix.ai.semantic import enabled as semantic_enabled, semantic
from fastapi import FastAPI
from iopix.routes import auth as auth_routes, backup, browse, images, albums, editing, geo, tools, review, organize, faces, settings
from iopix.runtime import state, kick, look, refresh, auto, resolve, prewarmer, models_arrived, APP_NAME_DEFAULT, app_name, app_stamp, public_version
from iopix import __version__ as APP_VERSION

setup_log()  # the copy's one log, each line marked with its app (iosuite_shared.logs); the app runs without the file
__all__ = ["app", "state", "kick", "refresh", "auto", "resolve", "prewarmer"]  # tests and app.mcp reach these through app.main

@asynccontextmanager
async def lifespan(_app):
    appstate.init()
    if not appdb.ready():  # no viewer database (a fresh install, or its server is down): the set-up page only
        logging.getLogger("iopix.main").error("starting without a viewer database (%s): only the page that says so answers until it does", appdb.error)
        async with shared_mcp.running(mcp.server):
            yield
        return
    users.init()
    maps.declare_keys()  # the Google keys live with the suite's keys and tokens
    edits.init()
    tagmanager.init()
    analysis.init()
    consistency.init()
    analysis.on_progress = kick.set  # fold new analysis results into the index as they arrive
    if tagmanager.pending_jobs():  # finish sidecar updates left over from a previous run
        tagmanager.start_worker()
    facemgr.resume_queue()  # and the face sidecar rewrites a restart interrupted
    bgjobs.attach()  # the analysis queue is one of the copy's jobs from here on (Settings › Servers › Jobs)
    refresh(initial=True)  # also starts the library when there is no digiKam database
    suite_demo.at_start(config.APP)  # the demo photos while the suite's demo switch is on (iosuite_demo); the watcher indexes them
    # the copy's jobs (Settings › Servers › Jobs): the previews and the cut-down thumbnails kept under their caps, the
    # look at whether the index is up to date (and at once when kicked), the file scanner (Settings › Library › File
    # scanner: passes only while it is on)
    looks = [chores.start(thumbs.prune_caches, every_s=thumbs.PRUNE_EVERY_S, first_s=20, name="cache prune", app=config.APP,
                          title="Keep the previews and the small thumbnails under their size"),
             chores.start(look, every_s=config.REINDEX_POLL, first_s=config.REINDEX_POLL, name="index", app=config.APP, quiet=True,
                          title="Bring the photo index up to date with the library"),
             scanner.start(events.after_write)]
    kick.job = looks[1]
    if dkdb.no_digikam() and scanner.enabled():
        scanner.run_soon()  # no digiKam to have found what was added while iopix was stopped: a pass right after start-up
    updater.start_daily()  # the daily "is there a newer version" check, when the setting allows it
    if config.AUTO_MODELS:  # containers and fresh installs: fetch missing models, then start the jobs that need them
        dlmodels.auto_download(config.AUTO_MODELS, on_done=models_arrived)
    async with shared_mcp.running(mcp.server):  # the MCP endpoint (/mcp) lives in this process
        yield
    kick.job = None
    bgjobs.detach()
    for j in looks:
        if j is not None:
            j.cancel()


app = FastAPI(title="ioPix", version=APP_VERSION, lifespan=lifespan, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
              description="A web front end for a digiKam photo library, for the family. Also an MCP endpoint (/mcp) for AI assistants.")

@app.exception_handler(photo_index.Unavailable)
async def _no_index(_request: Request, exc: photo_index.Unavailable) -> JSONResponse:
    """The photo index is not there to answer from (it is still being built, or its folder is not ioPix's to read):
    said in words, with what the log says, rather than as the sqlite error of whichever route asked first."""
    logging.getLogger("iopix.main").warning("the photo index could not be read: %s", exc)
    return JSONResponse({"detail": str(exc), "indexing": True}, status_code=503)


MAX_JSON_BYTES = 4 << 20   # a JSON request larger than this is refused
MAX_UPLOAD_BYTES = 2 << 30  # a multipart upload (photos, a library, a model): what the upload routes accept at most

# what a visitor may still fetch when sign-in is required: the app shell and its files (the map library among them),
# the API docs, a share link, and the MCP endpoint (its gate below)
OPEN_PATHS = ("/", "/sw.js", "/manifest.webmanifest", "/share", "/api/docs", "/api/openapi.json")
OPEN_PREFIXES = ("/static/", "/mcp")


def _open_to_visitors(request: Request) -> bool:
    """What a visitor gets while sign-in is required: the avatars on the sign-in screen. Only the faces accounts are
    linked to, and like the account tiles themselves (/api/auth/accounts) only on the network the server is on."""
    path = request.url.path
    if path.startswith("/face/") and not auth.outside(request):
        tail = path[6:].split("/")[0]
        return tail.isdigit() and int(tail) in users.linked_persons()
    return False


# Settings › Apps › MCP: this app's switch in the Shared ioSuite database, the suite's one unless it says otherwise
mcp_switch = shared_mcp.Switch(config.APP,
                               "Lets an AI assistant search, look at and organize your photos, as you.")
mcp_enabled = mcp_switch.enabled


def _mcp_user(user):
    """The account an MCP request acts as: its tools see that account's favorites and private albums."""
    mcp.current_user.set(user)
    appstate.viewer.set(user)


_mcp_gate = auth.mcp_gate(mcp_enabled, on_user=_mcp_user)


def _before(request: Request):
    """Once the user is known: who the change history and private albums see, and the MCP endpoint's gate (the switch;
    an app password or session; every tool acts as that account, as in every app of the suite)."""
    user = request.state.user
    history.user.set(user["name"] if user else ("MCP" if request.url.path.startswith("/mcp") else "visitor"))
    appstate.viewer.set(user)  # private albums: seen only by their owner
    return _mcp_gate(request)


# who is asking (the shared session cookie, the proxy's identity, Basic, a bearer app password), whether sign-in is
# required at all, and the cross-site check on writes: iosuite_shared's middleware. What each route needs beyond
# that (an editor, an admin, an account) is declared on the route (iopix/access.py).
app.middleware("http")(auth.middleware(open_paths=OPEN_PATHS, open_prefixes=OPEN_PREFIXES, is_open=_open_to_visitors, before=_before))


async def _without_database(request: Request, call_next):
    """The viewer's own database does not answer (appdb.ready() is false): the app shell and the status answer, the
    page says what is wrong and offers Retry (served here directly: the sign-in middleware and the routes' own checks
    would need the database), and everything else says what is missing. The viewer restarts once it answers."""
    path, method = request.url.path, request.method
    if path == "/api/status":
        return JSONResponse({"ok": False, "app": config.APP, "name": APP_NAME_DEFAULT, "version": APP_VERSION, "appName": APP_NAME_DEFAULT,
                             "needsDatabase": True, "databaseError": appdb.error, "databaseConfigured": appdb.configured(), "index": "", "stamp": ""})
    if path.startswith("/api/database"):
        if method not in ("GET", "HEAD", "OPTIONS") and auth.cross_site(request):  # the sign-in middleware's own rule
            return JSONResponse({"detail": "Requests from another site are refused"}, status_code=403)
        if path == "/api/database" and method == "GET":
            return JSONResponse({"configured": appdb.configured(), "locked": True, "error": appdb.error, "type": "mysql"})
        if path == "/api/database/retry" and method == "POST":
            try:
                return JSONResponse(await settings.api_database_retry())
            except HTTPException as e:
                return JSONResponse({"detail": e.detail}, status_code=e.status_code)
        return JSONResponse({"detail": "Not found"}, status_code=404)
    if path in OPEN_PATHS or path.startswith("/static/"):  # the shell and its files, not the sign-in API
        return await call_next(request)
    return JSONResponse({"detail": f"{APP_NAME_DEFAULT}'s database does not answer ({appdb.error})", "needsDatabase": True}, status_code=503)


@app.middleware("http")
async def _database_gate(request: Request, call_next):
    """Registered last, so it runs first: while the viewer has no database of its own, nothing below it runs."""
    if not appdb.ready():
        return await _without_database(request, call_next)
    return await call_next(request)


UPLOAD_PATHS = ("/api/import", "/api/import/stage", "/share")  # and /api/folders/<id>/upload: where photos are sent
MAX_TRACK_BYTES = 64 << 20  # a GPS track to match photos with (/api/gpx/preview)


def _limit_for(path: str, ctype: str) -> int:
    """What BodyCap lets through: JSON and forms a few MiB, and a multipart upload up to MAX_UPLOAD_BYTES on the
    routes that take uploads (which refuse larger files themselves too). Never by the content type alone: a request
    that only calls itself multipart would be read whole by a route that expects JSON, the sign-in among them."""
    if ctype.startswith("multipart/"):
        if path in UPLOAD_PATHS or (path.startswith("/api/folders/") and path.endswith("/upload")):
            return MAX_UPLOAD_BYTES
        if path == "/api/gpx/preview":
            return MAX_TRACK_BYTES
    return MAX_JSON_BYTES


# 400 for bad input, the headers, no-store on the API, the body cap: the same in every app of the suite
auth.install(app, limit_for=_limit_for)


def _status_extra(request: Request) -> dict:
    """ioPix's own fields of GET /api/status, beside the suite's: the index version the page compares to reload, the
    front end's stamp, the jobs, what the viewer may do. On the sign-in screen (sign-in required, nobody signed in):
    only what it needs, nothing about the library or the server."""
    user = request.state.user
    out = {"index": public_version(), "stamp": app_stamp(), "appName": app_name(), "digikamCheck": config.DIGIKAM_CHECK}
    if user is None and users.require_login():
        return {**out, "editing": False, "dbWrite": False, "pendingEdits": 0}
    admin, signed, writer = users.is_admin(user), users.is_signed_in(user), users.can_write(user)
    dk = photo_index.status()
    out.update({
        "error": state["error"] if admin or not state["error"] else "The library could not be read; an admin can see why in Settings › Library.", "rev": appstate.rev,
        "thumbs": {"running": prewarmer.running, "done": prewarmer.done, "total": prewarmer.total, "since": prewarmer.started, "last": prewarmer.last,
                   "current": list(prewarmer.current.values())[:3] if signed else []},  # file paths: not for anonymous clients
        "semantic": {"enabled": semantic_enabled(), "running": semantic.running, "done": semantic.done,
                     "total": semantic.total, "indexed": 0 if semantic.ids is None else int(len(semantic.ids))},
        "places": places.available(), "editing": edits.available() and writer, "pendingEdits": edits.pending_count(),
        "dbWrite": config.DB_WRITE and writer, "writeFiles": edits.writes_files(),
        "user": {**public_user(user), "person": user.get("person")} if user else None,  # the suite's shape, plus the linked person
        "digikam": dk if admin else {k: v for k, v in dk.items() if k != "error"}, "faceDetect": facedetect.available(),
        "lossless": lossless.capabilities() if config.DB_WRITE and edits.available() else None,
        "tagJobs": {**tagmanager.progress, "pending": tagmanager.pending_jobs()},
        "analysis": analysis.progress,
        "jobs": bgjobs.status() if admin else {k: v for k, v in bgjobs.status().items() if k not in ("held", "memory")}})  # the server's memory: for admins
    return out


app.include_router(auth.suite_router(suiteitems.PROVIDER))  # /api/suite: search, items, tile, as every app answers them (app.json)
app.include_router(browse.router)
app.include_router(images.router)
app.include_router(albums.router)
app.include_router(editing.router)
app.include_router(settings.router)
app.include_router(tools.router)
app.include_router(auth.status_router(updater, extra=_status_extra))  # /api/status: public, the same shape in every app
app.include_router(auth_routes.router)
app.include_router(auth.admin_router())  # /api/suite-admin (+ ui.js, the Settings › People, Apps, Servers and Keys panel): the whole suite (suite admins)
app.include_router(auth.live_router())  # /api/live: the one live-refresh stream a page holds, with every app's changes on it
app.include_router(geo.router)
app.include_router(backup.router)
app.include_router(review.router)
app.include_router(organize.router)
app.include_router(faces.router)

shared_mcp.mount(app, mcp.server)  # MCP over streamable HTTP at /mcp, ahead of everything else


@app.get("/", include_in_schema=False, dependencies=[access.public])
def index():
    """The page, with the version stamped on the script and stylesheet: after an update the browser (and Cloudflare,
    which caches .js and .css at the edge) fetches the new ones instead of serving what it kept."""
    html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for f in ("static/app.js", "static/app.css"):
        html = html.replace(f'"{f}"', f'"{f}?v={APP_VERSION}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False, dependencies=[access.public])
def service_worker():
    """At the root, so the service worker's scope is the whole app."""
    return FileResponse(config.STATIC_DIR / "sw.js", media_type="text/javascript")


app.mount("/static", pages.Static(directory=config.STATIC_DIR), name="static")  # modules marked no-cache

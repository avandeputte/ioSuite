"""ioPix: a web front end for a digiKam library.

Who may call a route is declared on the route (iopix/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite, and the application itself is the one every app builds (iosuite_shared.application.create, from app.json).
The library (digiKam's database and the photo files) is only read here; the few endpoints that change it (sidecars,
image files, digiKam's database on request) declare access.editor_write or access.admin_write on their route and go
through the modules that own those writes."""
import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from iosuite_shared import application, chores
from iosuite_shared.fastapi import public_user

from iopix.ai import analysis, models as dlmodels
from iopix.faces import facedetect, facemgr
from iopix import auth, config, events, jobs as bgjobs, suite_app, thumbs, users
from iopix.photos import consistency, edits, history, lossless, scanner, tagmanager
from iopix.data import index as photo_index, state as appstate, appdb
from iopix.digikam import dkdb
from iopix.geo import maps, places
from iopix.ai.semantic import enabled as semantic_enabled, semantic
from iopix.routes import auth as auth_routes, backup, browse, images, albums, editing, geo, tools, review, organize, faces, settings
from iopix.runtime import state, kick, look, refresh, auto, resolve, prewarmer, models_arrived, APP_NAME_DEFAULT, app_name, app_stamp, public_version
from iopix import __version__ as APP_VERSION

__all__ = ["app", "state", "kick", "refresh", "auto", "resolve", "prewarmer"]  # tests and iopix.mcp reach these through iopix.main
log = logging.getLogger("iopix.main")


# ---- what ioPix does before anything else: its own tables, then the library (nothing at all without its database)
def _prepare():
    """The app's tables and the suite's accounts, and what the library needs; without ioPix's own database only the
    page that says so answers (_database_gate below)."""
    appstate.init()
    if not appdb.ready():
        log.error("starting without a viewer database (%s): only the page that says so answers until it does", appdb.error)
        return
    users.init()
    maps.declare_keys()  # the Google keys live with the suite's keys and tokens
    edits.init()
    tagmanager.init()
    analysis.init()
    consistency.init()
    analysis.on_progress = kick.set  # fold new analysis results into the index as they arrive


def _start():
    """Once the tables are there: the work a previous run left unfinished, and the library."""
    if not appdb.ready():
        return
    if tagmanager.pending_jobs():  # finish sidecar updates left over from a previous run
        tagmanager.start_worker()
    facemgr.resume_queue()  # and the face sidecar rewrites a restart interrupted
    bgjobs.attach()  # the analysis queue is one of the copy's jobs from here on (Settings › Servers › Jobs)
    refresh(initial=True)  # also starts the library when there is no digiKam database
    if config.AUTO_MODELS:  # containers and fresh installs: fetch missing models, then start the jobs that need them
        dlmodels.auto_download(config.AUTO_MODELS, on_done=models_arrived)


def _jobs():
    """The copy's jobs (Settings › Servers › Jobs): the previews and the cut-down thumbnails kept under their caps,
    the look at whether the index is up to date (and at once when kicked), the file scanner (Settings › Library ›
    File scanner: passes only while it is on)."""
    if not appdb.ready():
        return []
    looks = [chores.start(thumbs.prune_caches, every_s=thumbs.PRUNE_EVERY_S, first_s=20, name="cache prune", app=config.APP,
                          title="Keep the previews and the small thumbnails under their size"),
             chores.start(look, every_s=config.REINDEX_POLL, first_s=config.REINDEX_POLL, name="index", app=config.APP, quiet=True,
                          title="Bring the photo index up to date with the library"),
             scanner.start(events.after_write)]
    kick.job = looks[1]
    if dkdb.no_digikam() and scanner.enabled():
        scanner.run_soon()  # no digiKam to have found what was added while ioPix was stopped: a pass right after start-up
    return looks


def _stop():
    kick.job = None
    bgjobs.detach()


# ---- who gets in
# what a visitor may still fetch when sign-in is required, beside the page and its files: the share link and the
# service worker (the API docs and the shell are every app's)
OPEN_PATHS = ("/sw.js", "/share")


def _open_to_visitors(request: Request) -> bool:
    """What a visitor gets while sign-in is required: the avatars on the sign-in screen. Only the faces accounts are
    linked to, and like the account tiles themselves (/api/auth/accounts) only on the network the server is on."""
    path = request.url.path
    if path.startswith("/face/") and not auth.outside(request):
        tail = path[6:].split("/")[0]
        return tail.isdigit() and int(tail) in users.linked_persons()
    return False


def _before(request: Request):
    """Once the user is known: who the change history and private albums see, and the MCP endpoint's gate (the switch;
    an app password or session; every tool acts as that account, as in every app of the suite)."""
    user = request.state.user
    history.user.set(user["name"] if user else ("MCP" if request.url.path.startswith("/mcp") else "visitor"))
    appstate.viewer.set(user)  # private albums: seen only by their owner
    return _mcp_gate(request)


# ---- GET /api/status
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


def _mcp_user(user):
    """The account an MCP request acts as: its tools see that account's favourites and private albums, and the change
    log names them (iopix/mcp: the stdio server goes through the same)."""
    from iopix import mcp
    mcp.set_user(user)


_mcp_gate = auth.mcp_gate(suite_app.mcp_enabled, on_user=_mcp_user)

app = application.create(
    suite_app,
    description="A web front end for a digiKam photo library, for the family. Also an MCP endpoint (/mcp) for AI assistants.",
    prepare=(_prepare,), start=(_start,), jobs=_jobs, stop=(_stop,), before=_before, open_paths=OPEN_PATHS, middleware={"is_open": _open_to_visitors},
    related=False, status=_status_extra, service_worker=True,
    routers=(auth_routes.router, browse.router, images.router, albums.router, editing.router, settings.router,
             tools.router, geo.router, backup.router, review.router, organize.router, faces.router))


@app.exception_handler(photo_index.Unavailable)
async def _no_index(_request: Request, exc: photo_index.Unavailable) -> JSONResponse:
    """The photo index is not there to answer from (it is still being built, or its folder is not ioPix's to read):
    said in words, with what the log says, rather than as the sqlite error of whichever route asked first."""
    log.warning("the photo index could not be read: %s", exc)
    return JSONResponse({"detail": str(exc), "indexing": True}, status_code=503)


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
    if path in application.OPEN_PATHS + OPEN_PATHS or path.startswith("/static/"):  # the shell and its files, not the sign-in API
        return await call_next(request)
    return JSONResponse({"detail": f"{APP_NAME_DEFAULT}'s database does not answer ({appdb.error})", "needsDatabase": True}, status_code=503)


@app.middleware("http")
async def _database_gate(request: Request, call_next):
    """Registered after everything else, so it runs first: while the viewer has no database of its own, nothing below
    it runs."""
    if not appdb.ready():
        return await _without_database(request, call_next)
    return await call_next(request)

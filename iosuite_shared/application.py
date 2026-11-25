"""An app of the suite as a FastAPI application: what every app's main.py did in the same words, once.

    from iotask import api, caldav, model, notify, suite_app

    app = application.create(suite_app,
                             description="…",
                             jobs=lambda: [chores.start(notify.run, every_s=60, name="notifications", app=suite_app.key)],
                             not_found=(model.NotFound,), forbidden=(model.Forbidden,),
                             status=_status_extra, routers=(api.router, caldav.router))

`suite_app` is the app as declared (iosuite_shared.app.App): its sign-in, its accounts, its settings, and from its
manifest (app.json) who gets in, how large a body may be and what its MCP switch says. What an app's main.py keeps
is what is its own: the description, its jobs, its extra status fields, its routes. The rest is here, in the order
every app had it:

- at start: the app's tables and the suite's accounts (`App.prepare`, off the event loop), the demo data while the
  demo switch is on, what the app starts beside its jobs (`start`), the daily update check, its jobs, a line in the
  log, and the MCP endpoint's session manager for as long as the app runs; at the end the jobs are taken off the runner;
- the middleware that works out who is asking (iosuite_shared.fastapi.Auth.middleware), with the MCP endpoint's
  gate as its `before`, or the app's own;
- 400 for bad input, the headers, no-store on the API and the body cap (Auth.install);
- the routes every app answers (/api/auth, /api/suite-admin, /api/live, /api/related, /api/suite, /api/status), then
  the app's own, the MCP endpoint and the page with its files.
"""
import inspect
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from iosuite_shared import catalog, demo, mcp as shared_mcp, pages
from iosuite_shared.updates import setup_log

# what a visitor may still fetch when sign-in is required: the app shell and its files, and the API docs
OPEN_PATHS = ("/", "/manifest.webmanifest", "/api/docs", "/api/openapi.json")
OPEN_PREFIXES = ("/static/",)


AUTO = object()  # an argument left for create() to find in the app's package


def create(suite_app, *, description: str, prepare=None, start=(), jobs=None, stop=(), where=None,
           mcp=AUTO, on_mcp_user=None, before=None, open_paths=(), open_prefixes=(), middleware=None,
           limit_for=None, not_found=(), forbidden=(), status=None, suite=AUTO, related: bool = True,
           routers=(), page: bool = True, service_worker: bool = False) -> FastAPI:
    """The app `suite_app` declares (iosuite_shared.app.App), as the FastAPI application the host runs.

    `prepare`: functions run one after another before anything else, each in a thread; left out, the app's tables
    and the suite's accounts (App.prepare; an app with more to do gives `(*suite_app.prepare, more)`). `start`:
    functions called after them on the event loop, awaited when they are coroutines; what one returns is closed or
    cancelled when the app stops. `jobs`: a function that registers the app's jobs (iosuite_shared.chores.start) and
    returns their handles. `stop`: functions called when the app stops, after its jobs left the runner. `where`: a
    function that says where the app's data is, for the log line (the app's own database unless given).

    `mcp`: the app's MCP module (its `server`, and the account a request to /mcp acts as: its `set_user` where it
    has one, which the stdio server uses too, else `current_user`, unless `on_mcp_user` is given): <app>/mcp where the package has one, unless given (None: no MCP endpoint). Its
    switch is the app's (App.mcp_switch), and GET /api/status says `mcp` to whoever is signed in. `before`: the app's
    own hook for the middleware instead of the MCP gate alone. `open_paths`, `open_prefixes`: what a visitor may
    fetch when sign-in is required, beside the page and its files and what the app's manifest lists as `sync`
    (app.json: CalDAV and CardDAV, the calendar links, the phone's uploads, which check their own sign-in).
    `middleware`: more arguments for Auth.middleware.

    `limit_for`: the body cap's function, where the manifest's `bodies` cannot say it (App.limit_for otherwise).
    `not_found`: as Auth.install takes it. `forbidden`: the app's exception classes that mean 403. `status`: the
    app's own fields of GET /api/status. `suite`: what it answers at /api/suite (search, items, tile):
    <app>/suiteitems.py's PROVIDER where the package has one, unless given. `related`: whether it has the Linked
    panel. `routers`: its routes, in the order they are looked through. `page`: False for an app that serves its
    page and files itself (the start page, which is two pages); `service_worker`: whether the page has one at /sw.js."""
    auth, updater, config = suite_app.auth, suite_app.updater, suite_app.config
    version = updater.version
    if mcp is AUTO:
        mcp = suite_app.module("mcp") if suite_app.has("mcp") else None
    if suite is AUTO:
        suite = suite_app.module("suiteitems").PROVIDER if suite_app.has("suiteitems") else None
    if prepare is None:
        prepare = suite_app.prepare
    mcp_enabled = suite_app.mcp_enabled if mcp is not None else None
    extra = status

    def status(request) -> dict:
        """The app's own fields of GET /api/status, and whether its MCP endpoint is on (to an account)."""
        out = dict(extra(request)) if extra else {}
        if mcp is not None:
            out.setdefault("mcp", mcp_enabled() if request.state.user else None)
        return out

    setup_log()  # the copy's one log, each line marked with its app (iosuite_shared.logs); the app runs without the file
    app_key, label = auth.app, catalog.name_of(auth.app)
    log = logging.getLogger(app_key)
    server = getattr(mcp, "server", None)

    @asynccontextmanager
    async def lifespan(_app):
        for fn in prepare:
            await run_in_threadpool(fn)
        await run_in_threadpool(demo.at_start, app_key)  # the demo data while the suite's demo switch is on
        held = []
        try:
            for fn in start:
                got = fn()
                if inspect.isawaitable(got):
                    got = await got
                if hasattr(got, "cancel") or hasattr(got, "close"):
                    held.append(got)
            updater.start_daily()  # the daily "is there a newer version" check, while the setting allows it
            held.extend(jobs() if jobs else ())
            log.info("%s %s started, %s", label, version,
                     where() if where else f"database {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
            if server is not None:
                async with shared_mcp.running(server):  # the MCP endpoint (/mcp) lives in this process
                    yield
            else:
                yield
        finally:
            for h in held:
                if h is not None:   # a job the app registers only when it is wanted
                    (getattr(h, "cancel", None) or h.close)()
            for fn in stop:
                fn()

    app = FastAPI(title=label, version=version, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json", description=description)

    # who is asking, whether sign-in is required at all, the cross-site check on writes, and the MCP endpoint's gate
    # (the switch; an app password or a session; every tool acts as that account)
    if before is None and server is not None:
        before = auth.mcp_gate(mcp_enabled, on_user=on_mcp_user or getattr(mcp, "set_user", None) or mcp.current_user.set)
    app.middleware("http")(auth.middleware(
        open_paths=OPEN_PATHS + tuple(open_paths),
        # what the app serves to phones and devices (its manifest's "sync") signs in on its own, as /mcp does
        open_prefixes=(OPEN_PREFIXES + tuple((catalog.APPS.get(app_key) or {}).get("sync") or ())
                       + (("/mcp",) if server is not None else ()) + tuple(open_prefixes)),
        before=before, **(middleware or {})))

    # 400 for bad input, the headers, no-store on the API, the body cap: the same in every app of the suite
    auth.install(app, limit_for=limit_for or suite_app.limit_for, not_found=tuple(not_found))

    async def _forbidden(_request, e):
        return JSONResponse({"detail": str(e)}, status_code=403)
    for cls in forbidden:
        app.add_exception_handler(cls, _forbidden)

    app.include_router(auth.router())            # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords
    app.include_router(auth.admin_router())      # /api/suite-admin (+ ui.js): Settings › People, Apps, Servers and Keys, for suite admins
    app.include_router(auth.live_router())       # /api/live: the one live-refresh stream a page holds, with every app's changes on it
    if related:
        app.include_router(auth.related_router())  # /api/related (+ ui.js, the "Linked" panel): items linked across the apps
    if suite is not None:
        app.include_router(auth.suite_router(suite))  # /api/suite: search, items, tile, as every app answers them (app.json)
    app.include_router(auth.settings_router())   # /api/app-settings: the settings it declares (app.json), for its admins
    app.include_router(auth.status_router(updater, extra=status))  # /api/status: public, the same shape in every app
    for r in routers:
        app.include_router(r)
    if server is not None:
        shared_mcp.mount(app, server)  # MCP over streamable HTTP at /mcp, ahead of everything else
    if page:
        pages.mount(app, config.STATIC_DIR, service_worker=service_worker, dependencies=[auth.access.public],
                    declared=suite_app.manifest)  # /, the manifest and /static; the page is the shell every app shares (app.json's `page`)
    return app

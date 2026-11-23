"""ioTask: the application (what is its own: its tables and jobs, its body limits, its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iotask/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores, mcp as shared_mcp

from iotask import __version__, api, caldav, config, db, ical, mcp, model, notify, suiteitems, users
from iotask.auth import auth, updater

# Settings › Apps › MCP: this app's switch in the Shared ioSuite database, the suite's one unless it says otherwise
mcp_switch = shared_mcp.Switch(config.APP,
                               "Lets an AI assistant read the lists, add tasks and tick them off, as you.")
mcp_enabled = mcp_switch.enabled


def _jobs() -> list:
    return [chores.start(model.purge_deleted, name="purge of old deletion markers", app=config.APP),  # once a day: KEEP_DELETED_DAYS
            chores.start(notify.run, every_s=60, first_s=20, name="notifications", app=config.APP)]  # tasks falling due, the morning summary


def _limit_for(path: str, ctype: str) -> int:
    if "/import" in path:  # an .ics file to import
        return config.MAX_IMPORT_BYTES
    if path.startswith("/dav"):  # CalDAV checks its own PUTs (max-resource-size)
        return config.MAX_TASK_BYTES
    return config.MAX_JSON_BYTES


def _status_extra(request) -> dict:
    """ioTask's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"timezone": ical.default_tz(), "mcp": mcp_enabled() if u else None}


app = application.create(
    auth, updater, __version__, config,
    description="Task lists for the family. Also served over CalDAV at /dav/ (to-dos, for Apple Reminders and "
                "other reminders apps) and to AI assistants over MCP (/mcp). JSON by default; ask for "
                "text/calendar with Accept or ?format=ics.",
    prepare=(db.migrate, users.init), jobs=_jobs,
    mcp=mcp, mcp_enabled=mcp_enabled,
    # what a visitor may still fetch when sign-in is required, beside what app.json lists as sync (CalDAV, with its
    # own sign-in): the profile links (their own secret)
    open_prefixes=("/profile/",),
    limit_for=_limit_for, not_found=(model.NotFound,),
    status=_status_extra, suite=suiteitems.PROVIDER,
    routers=(auth.profile_router(api.sync_url),  # /profile/<token>/<file> and the profile for all the apps that sync
             api.router, caldav.router))

"""ioTask: the application (what is its own: its jobs and its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iotask/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores

from iotask import api, auth, caldav, config, ical, model, notify, suite_app


def _jobs() -> list:
    return [chores.start(model.purge_deleted, name="purge of old deletion markers", app=config.APP),  # once a day: KEEP_DELETED_DAYS
            chores.start(notify.run, every_s=60, first_s=20, name="notifications", app=config.APP)]  # tasks falling due, the morning summary


def _status_extra(request) -> dict:
    """ioTask's own fields of GET /api/status, beside the suite's."""
    return {"timezone": ical.default_tz()}


app = application.create(
    suite_app,
    description="Task lists for the family. Also served over CalDAV at /dav/ (to-dos, for Apple Reminders and "
                "other reminders apps) and to AI assistants over MCP (/mcp). JSON by default; ask for "
                "text/calendar with Accept or ?format=ics.",
    jobs=_jobs,
    # what a visitor may still fetch when sign-in is required, beside what app.json lists as sync (CalDAV, with its
    # own sign-in): the profile links (their own secret)
    open_prefixes=("/profile/",),
    not_found=(model.NotFound,), status=_status_extra,
    routers=(auth.profile_router(api.sync_url),  # /profile/<token>/<file> and the profile for all the apps that sync
             api.router, caldav.router))

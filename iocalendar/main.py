"""ioCalendar: the application (what is its own: its tables and jobs, its body limits, its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iocalendar/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores, mcp as shared_mcp

from iocalendar import __version__, api, bills, caldav, config, contacts, db, holiday, ical, mcp, model, notify, papers, places, subscribe, suiteitems, tasks, users
from iocalendar.auth import auth, updater

# Settings › Apps › MCP: this app's switch in the Shared ioSuite database, the suite's one unless it says otherwise
mcp_switch = shared_mcp.Switch(config.APP,
                               "Lets an AI assistant read the agenda, find free time and add or change events, as you.")
mcp_enabled = mcp_switch.enabled


def _jobs() -> list:
    return [contacts.start_sync(),   # the Birthdays calendar from ioContact, every few hours
            holiday.start_sync(),    # the Holidays calendar, every day
            chores.start(model.purge_deleted, name="purge of old deletion markers", app=config.APP),  # once a day: KEEP_DELETED_DAYS
            chores.start(notify.tick, every_s=60, first_s=20, name="notifications", app=config.APP),  # the events' reminders
            chores.start(subscribe.tick, every_s=300, first_s=30, name="outside calendars", app=config.APP)]  # each fetched again when its time comes


def _limit_for(path: str, ctype: str) -> int:
    if "/import" in path or path.startswith("/dav"):  # an .ics file to import; CalDAV checks its own PUTs (max-resource-size)
        return config.MAX_IMPORT_BYTES
    return config.MAX_JSON_BYTES


def _status_extra(request) -> dict:
    """ioCalendar's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"timezone": ical.default_tz(), "iocontact": contacts.enabled() if u else None, "iotask": tasks.enabled() if u else None,
            "iomoney": bills.enabled() if u else None, "iodocs": papers.enabled() if u else None, "mcp": mcp_enabled() if u else None,
            "places": places.enabled() if u else None}


app = application.create(
    auth, updater, __version__, config,
    description="Calendars for the family. Also served over CalDAV at /dav/ (iCalendar), as subscription links "
                "(/ics/<private token>/<calendar>.ics) and to AI assistants over MCP (/mcp). JSON by default; ask "
                "for text/calendar or application/calendar+json (jCal) with Accept or ?format=ics|jcal.",
    prepare=(db.migrate, users.init), jobs=_jobs,
    mcp=mcp, mcp_enabled=mcp_enabled,
    # what a visitor may still fetch when sign-in is required, beside what app.json lists as sync (the subscription
    # links with their own secret, CalDAV with its own sign-in): the profile links
    open_prefixes=("/profile/",),
    limit_for=_limit_for, not_found=(model.NotFound,),
    status=_status_extra, suite=suiteitems.PROVIDER,
    routers=(auth.profile_router(api.sync_url),  # /profile/<token>/<file> and the profile for all the apps that sync
             api.router,
             auth.feeds_router(api.feed_links),  # /api/feeds: your subscription links (Shared ioSuite database, shown once)
             caldav.router))

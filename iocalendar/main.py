"""ioCalendar: the application (what is its own: its tables and jobs, its body limits, its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iocalendar/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores

from iocalendar import api, auth, bills, caldav, config, contacts, holiday, ical, model, notify, papers, places, subscribe, suite_app, tasks


def _jobs() -> list:
    return [contacts.start_sync(),   # the Birthdays calendar from ioContact, every few hours
            holiday.start_sync(),    # the Holidays calendar, every day
            chores.start(model.purge_deleted, name="purge of old deletion markers", app=config.APP),  # once a day: KEEP_DELETED_DAYS
            chores.start(notify.tick, every_s=60, first_s=20, name="notifications", app=config.APP),  # the events' reminders
            chores.start(subscribe.tick, every_s=300, first_s=30, name="outside calendars", app=config.APP)]  # each fetched again when its time comes


def _status_extra(request) -> dict:
    """ioCalendar's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"timezone": ical.default_tz(), "iocontact": contacts.enabled() if u else None, "iotask": tasks.enabled() if u else None,
            "iomoney": bills.enabled() if u else None, "iodocs": papers.enabled() if u else None,
            "places": places.enabled() if u else None}


app = application.create(
    suite_app,
    description="Calendars for the family. Also served over CalDAV at /dav/ (iCalendar), as subscription links "
                "(/ics/<private token>/<calendar>.ics) and to AI assistants over MCP (/mcp). JSON by default; ask "
                "for text/calendar or application/calendar+json (jCal) with Accept or ?format=ics|jcal.",
    jobs=_jobs,
    # what a visitor may still fetch when sign-in is required, beside what app.json lists as sync (the subscription
    # links with their own secret, CalDAV with its own sign-in): the profile links
    open_prefixes=("/profile/",),
    not_found=(model.NotFound,),
    status=_status_extra,
    routers=(auth.profile_router(api.sync_url),  # /profile/<token>/<file> and the profile for all the apps that sync
             api.router,
             auth.feeds_router(api.feed_links),  # /api/feeds: your subscription links (Shared ioSuite database, shown once)
             caldav.router))

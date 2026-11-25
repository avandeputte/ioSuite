"""ioContact: the application (what is its own: its tables and jobs, the LDAP directory, who reads, its body
limits, its routes; the rest is every app's: iosuite_shared.application).

Who may call a route is declared on the route (iocontact/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
import logging

from iosuite_shared import application, chores

from iocontact import api, auth, carddav, config, enrich, iopix, ldapd, mcp, model, notify, quality, suite_app, users

log = logging.getLogger("iocontact")


async def _ldap():
    """The LDAP directory (read-only), where a port is set for it; closed when the app stops."""
    if not config.LDAP_PORT:
        return None
    try:
        return await ldapd.serve(config.LDAP_HOST, config.LDAP_PORT)
    except OSError as e:
        log.warning("LDAP directory not started on port %s: %s", config.LDAP_PORT, e)
        return None


def _jobs() -> list:
    return [chores.start(quality.housekeeping, name="purge of old deletion markers and merges", app=config.APP),  # once a day: KEEP_DELETED_DAYS, 30 days of undo
            chores.start(notify.run, every_s=60, first_s=20, name="notifications", app=config.APP)]  # the morning's birthdays


# the MCP endpoint's gate (the switch; an app password or session; every tool acts as that account). An app password
# with a scope, such as an Apple profile's CardDAV/LDAP-only one, is kept to its paths by the same middleware.
_mcp_gate = auth.mcp_gate(suite_app.mcp_enabled, on_user=mcp.set_user)  # whose the call is: iocontact/mcp


def _before(request):
    """Once the account is known: the model is told who reads (relations into somebody's private book are theirs
    alone, model.full_many), then the MCP endpoint's gate."""
    model.viewer.set(request.state.user)
    return _mcp_gate(request)


def _status_extra(request) -> dict:
    """ioContact's own fields of GET /api/status, beside the suite's (its `user` also names the account's own contact)."""
    u = request.state.user
    return {"user": users.public(u), "iopix": bool(iopix.settings()["url"]) if u else None,
            "suggestions": enrich.pending_count(api.book_ids(u)) if u else None}


app = application.create(
    suite_app,
    description="Contacts for the family. Also served over CardDAV at /dav/ (vCard 3.0 and 4.0), LDAP "
                "(read-only), as a birthday calendar (iCalendar) and to AI assistants over MCP (/mcp). JSON by "
                "default; ask for text/vcard or application/vcard+json (jCard) with Accept or ?format=vcard|vcard4|jcard.",
    start=(_ldap,), jobs=_jobs,
     before=_before,
    # what a visitor may still fetch when sign-in is required, beside what app.json lists as sync (the birthday
    # calendar links with their own secret, CardDAV with its own sign-in): the profile links
    open_prefixes=("/profile/",),
    status=_status_extra, 
    routers=(auth.profile_router(api.sync_url),  # /profile/<token>/<file> and the profile for all the apps that sync
             api.router,                         # the contacts; also an account's own fields (its "me" contact, the face on its tile)
             auth.feeds_router(api.feed_links),  # /api/feeds: your birthday calendar links (Shared ioSuite database, shown once)
             carddav.router))

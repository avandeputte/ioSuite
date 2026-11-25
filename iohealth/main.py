"""ioHealth: the iPhone app's upload API and the fitness web app, over the suite's shared accounts (what is its
own: its tables and jobs, the phone's endpoints, its routes; the rest is every app's: iosuite_shared.application).

Who may call a route is declared on the route (iohealth/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, or a bearer app
password), whether sign-in is required at all (it always is here: health data is private), and refuses cross-site
writes.
"""
from iosuite_shared import application, chores, users as shared

from iohealth import config, db, emergency, meds, notify, suite_app, upload, usual, webapi
from iohealth.config import APP


def _jobs() -> list:
    return [chores.start(notify.weekly, every_s=60, first_s=20, name="weekly summary", app=config.APP),  # Monday morning: last week next to the one before
            chores.start(notify.usual_morning, every_s=60, first_s=40, name="outside your usual", app=config.APP),
            chores.start(meds.reminders, every_s=60, first_s=30, name="medicine reminders", app=config.APP)]  # at each dose's time  # at each person's morning time


def _where() -> str:
    c = db.params()
    return "writing to %s:%s/%s (%s)" % (c["host"], c["port"], c["database"], "accounts exist" if shared.any_users() else
                                         "no accounts yet: create the first one from the sign-in screen, inside your network")


def _status_extra(request) -> dict:
    """ioHealth's own fields of GET /api/status, beside the suite's: the schema and the map tiles for everyone, and for an
    account its last sync."""
    out = {"schemaVersion": db.schema_version(), "tiles": {"url": config.MAP_TILE_URL, "attribution": config.MAP_TILE_ATTRIBUTION}}
    u = request.state.user
    if u:
        out.update(webapi.last_sync(int(u["id"])))
    return out


upload.on_sync.append(webapi.sync_finished)
upload.on_user_sync.append(notify.after_sync_quietly)  # "goal reached" and "outside your usual" notifications

app = application.create(
    suite_app,
    description="Apple Health data from the iPhone in your own MariaDB: the phone uploads to /v1/, the web app reads /api/. "
                "Every figure is the signed-in account's own.",
    prepare=(db.wait_for_server, shared.init, db.migrate),
    start=(webapi.start_backfill,),  # the hourly rollup of the types that have none yet, after the demo data
    jobs=_jobs, where=_where,
    # (the phone's endpoints under /v1/, app.json's sync, check the app password themselves)
    status=_status_extra, related=False,
    routers=(upload.router, webapi.router,
             usual.router,  # /api/usual: what is outside the account's usual
             meds.router, emergency.router))  # medicines and allergies, the emergency card

__all__ = ["app", "APP"]

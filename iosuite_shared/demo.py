"""The demo switch: the suite's demo data (a made-up family of four, the Calloways, with something in every app) is
the iosuite_demo package of the program folder; this module says when an app adds its share.

  * The switch is one suite-wide setting in the Shared ioSuite database (ios_settings 'demo'), set by `iosuite demo`
    (an installed server) or `iosuite stack --demo` (a Docker stack, before it starts: what the compose file builder's
    "Fill it with demo data" box writes).
  * At start, after its tables are made, every app calls `at_start(APP)`: while the switch is on and the app has not
    been seeded yet (ios_settings 'demo_seeded' for the app), it runs its seed (the family's accounts are made when
    missing).
  * Turning the switch off (`iosuite demo --off`) stops further seeding; it removes nothing.
"""
import logging

log = logging.getLogger("iosuite_shared.demo")

SWITCH = "demo"          # ios_settings, app '': "1" while the demo is wanted
SEEDED = "demo_seeded"   # ios_settings, app <app>: when its seed ran (epoch seconds)
DEMO_PASSWORD = "calloway"
FAMILY_KEYS = ("morgan", "riley", "ava", "theo")  # the demo's account names (iosuite_demo.FAMILY)


# ---- the switch
def wanted() -> bool:
    from iosuite_shared import db
    return db.get_setting(SWITCH, "", "") == "1"


def switch(on: bool) -> None:
    from iosuite_shared import db
    db.set_setting(SWITCH, "1" if on else None, "")


def seeded(app: str) -> bool:
    from iosuite_shared import db
    return bool(db.settings_of(app).get(SEEDED))


def at_start(app: str) -> None:
    """At an app's start, after its tables: seed it when the demo switch is on and it has not been seeded. Never stops
    the app from starting: a seed that fails is logged."""
    try:
        from iosuite_shared import users
        if not (users.init() and wanted()) or seeded(app):
            return
        import iosuite_demo
        iosuite_demo.seed(app)
    except Exception:  # noqa: BLE001
        log.exception("the demo data for %s could not be added", app)


# ---- the command: iosuite demo
def add_parser(sub):
    p = sub.add_parser("demo", help="fill the suite with demo data: a made-up family of four, something in every app")
    p.add_argument("--off", action="store_true", help="stop adding demo data to apps that start (removes nothing)")
    return p


def main(a, log=print) -> int:
    from iosuite_shared import users
    if not users.init():
        from iosuite_shared import db
        raise SystemExit(f"error: the Shared ioSuite database cannot be reached: {db.error}")
    if a.off:
        switch(False)
        log("ok: no more demo data is added (what was added stays)")
        return 0
    switch(True)
    log(f"  the Calloway family: {', '.join(FAMILY_KEYS)} (password: {DEMO_PASSWORD}), made by the first app that adds its demo data")
    log("ok: every app adds its share of the demo data at its next start (restart the suite: systemctl restart 'iosuite*')")
    return 0

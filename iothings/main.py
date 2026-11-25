"""ioThings: the application (its tables and jobs, its body limits, its routes; the rest is every app's:
iosuite_shared.application).

Who may call a route is declared on the route (iothings/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores

from iothings import api, config, model, notify, suite_app


def _jobs() -> list:
    return [chores.start(notify.run, every_s=60, first_s=20, name="notifications", app=config.APP)]  # the morning's upkeep and warranties


app = application.create(
    suite_app,
    description="Everything you own: where each thing is, what it cost, its warranty, manuals and "
                "receipts, and its upkeep (as repeating tasks in ioTask). Imports a Homebox export. Also "
                "served to AI assistants over MCP (/mcp).",
    jobs=_jobs,
    not_found=(model.NotFound,), forbidden=(model.Forbidden,),
    routers=(api.router,))

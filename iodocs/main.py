"""ioDocs: the application (what is its own: its tables and jobs, its body limits, its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iodocs/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores

from iodocs import api, config, model, notify, suite_app


def _jobs() -> list:
    return [chores.start(notify.run, every_s=60, first_s=20, name="notifications", app=config.APP)]  # the morning's papers about to expire


app = application.create(
    suite_app,
    description="The family's important papers: passports, ID cards, driver's licenses, insurance "
                "policies, certificates, each with its scans, whose it is and when it expires, with a "
                "reminder before it does. Scans are read on the server (OCR, a passport's machine-readable "
                "zone, a license's barcode) to fill the details in. Also served to AI assistants over MCP (/mcp).",
    jobs=_jobs,
    not_found=(model.NotFound,), forbidden=(model.Forbidden,),
    routers=(api.router,))

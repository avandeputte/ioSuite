"""ioDNS: the application (what is its own: its tables and jobs, its routes; the rest is every app's:
iosuite_shared.application).

Who may call a route is declared on the route (iodns/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from iosuite_shared import application

from iodns import api, config, ddns, model, suite_app, sync
from iodns.providers import ProviderError


def _jobs() -> list:
    if not config.env_flag("BACKGROUND", True):
        return []
    return [sync.start_checks(config.CHECK_MINUTES),  # every server compared with the master list now and then
            ddns.start()]                             # the public address, every few minutes


app = application.create(
    suite_app,
    description="One master list of local DNS records, per view (Internal, External, Tailscale…), kept in sync on "
                "AdGuard Home, Pi-hole, UniFi and Cloudflare, with dynamic DNS and Tailscale device addresses.",
    jobs=_jobs,
    not_found=(model.NotFound,),
    related=False, routers=(api.router,))


@app.exception_handler(ProviderError)
async def provider_error(request: Request, e: ProviderError):
    """A DNS server that answered with an error or could not be reached: 502, with what it said."""
    return JSONResponse({"detail": str(e)}, status_code=502)

"""ioThings: the application (its tables and jobs, its body limits, its routes; the rest is every app's:
iosuite_shared.application).

Who may call a route is declared on the route (iothings/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores, mcp as shared_mcp

from iothings import __version__, api, config, db, mcp, model, notify, suiteitems, users
from iothings.auth import auth, updater

# Settings › Apps › MCP: this app's switch in the Shared ioSuite database, the suite's one unless it says otherwise
mcp_switch = shared_mcp.Switch(config.APP,
                               "Lets an AI assistant look things up, add them and log their upkeep, as you.")
mcp_enabled = mcp_switch.enabled


def _jobs() -> list:
    return [chores.start(notify.run, every_s=60, first_s=20, name="notifications", app=config.APP)]  # the morning's upkeep and warranties


def _limit_for(path: str, ctype: str) -> int:
    if path == "/api/import/homebox":
        return config.MAX_IMPORT_BYTES
    return config.MAX_FILE_BYTES if path.endswith("/files") else config.MAX_JSON_BYTES


def _status_extra(request) -> dict:
    """ioThings's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"mcp": mcp_enabled() if u else None}


app = application.create(
    auth, updater, __version__, config,
    description="Everything you own: where each thing is, what it cost, its warranty, manuals and "
                "receipts, and its upkeep (as repeating tasks in ioTask). Imports a Homebox export. Also "
                "served to AI assistants over MCP (/mcp).",
    prepare=(db.migrate, users.init), jobs=_jobs,
    mcp=mcp, mcp_enabled=mcp_enabled,
    limit_for=_limit_for, not_found=(model.NotFound,), forbidden=(model.Forbidden,),
    status=_status_extra, suite=suiteitems.PROVIDER, routers=(api.router,))

"""ioRecipe: the application (what is its own: its tables and jobs, its body limits, its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iorecipe/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, mcp as shared_mcp

from iorecipe import __version__, ai, api, config, db, mcp, model, suiteitems, users
from iorecipe.auth import auth, updater

# Settings › Apps › MCP: this app's switch in the Shared ioSuite database, the suite's one unless it says otherwise
mcp_switch = shared_mcp.Switch(config.APP,
                               "Lets an AI assistant look recipes up, add them and import them from the web, as you.")
mcp_enabled = mcp_switch.enabled


def _limit_for(path: str, ctype: str) -> int:
    if path == "/api/import/file":
        return config.MAX_IMPORT_BYTES
    return config.MAX_PHOTO_BYTES if path.endswith(("/photos", "/import/photo")) else config.MAX_JSON_BYTES


def _status_extra(request) -> dict:
    """ioRecipe's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"mcp": mcp_enabled() if u else None}


app = application.create(
    auth, updater, __version__, config,
    description="The family's recipes: ingredients, steps, a photo, and import from a web page. Also served "
                "to AI assistants over MCP (/mcp).",
    prepare=(db.migrate, users.init),
    start=(ai.start,),  # the AI model on its way, where it is wanted and not there yet
    mcp=mcp, mcp_enabled=mcp_enabled,
    limit_for=_limit_for, not_found=(model.NotFound,), forbidden=(model.Forbidden,),
    status=_status_extra, suite=suiteitems.PROVIDER, routers=(api.router,))

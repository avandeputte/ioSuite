"""ioNote: the web app, the API the Mac and iPhone apps use, and the MCP endpoint, on one port (8610).

Who may call a route is declared on the route (ionote/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite. What is ioNote's own: whose notes a request works on (notes are private to each account, but for the Family
space's, which everyone with a role reads and editors change).
"""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from iosuite_shared import application, chores, mcp as shared_mcp, users

from ionote import __version__, config, db, mcp, suitedb, suiteitems
from ionote import notes as notes_mod
from ionote.auth import auth, updater
from ionote.routes import notes as notes_routes, settings

log = logging.getLogger("ionote")

# Settings › Apps › MCP: this app's switch in the Shared ioSuite database, the suite's one unless it says otherwise
mcp_switch = shared_mcp.Switch(config.APP,
                               "Lets an AI assistant search, read and write your notes, as you.")
mcp_enabled = mcp_switch.enabled


def _open() -> None:
    try:
        db.init()
    except Exception as e:
        db.error = str(e)[:300]
        log.error("the database could not be opened: %s", e)
        raise


def _jobs() -> list:
    return [chores.start(notes_mod.housekeeping, every_s=6 * 3600, name="purge of the trash and of what deletions left behind", app=config.APP)]


def _where() -> str:
    c, sd = db.settings(), suitedb.public()
    return "on MariaDB/MySQL %s:%s/%s (%s); Shared ioSuite database (accounts, suite settings): %s@%s:%s/%s" % (
        c["host"], c["port"], c["database"],
        "accounts exist" if users.any_users() else "no accounts yet: open to everyone until one is made",
        sd["user"], sd["host"], sd["port"], sd["database"])


def _owner_of(request: Request) -> int:
    """Whose notes this request sees: the signed-in account's; before any account exists, the open install's (0);
    a visitor once accounts exist sees none."""
    u = request.state.user
    if u:
        return int(u["id"])
    return 0 if not users.any_users() else notes_mod.NOBODY


def _family_of(user) -> int:
    """What this account may do with the Family space's notes: editors and admins change them, everyone else with a
    role reads them; a visitor sees none, and an install without accounts has no family."""
    if not user:
        return notes_mod.NO_FAMILY
    if users.can_write(user):
        return notes_mod.FAMILY_WRITE
    return notes_mod.FAMILY_READ if users.is_signed_in(user) else notes_mod.NO_FAMILY


def _mcp_user(u: dict) -> None:
    """The MCP endpoint, once its gate let the request through: every tool acts as this account, on its own notes and
    the family's."""
    mcp.current_user.set(u)
    notes_mod.current_owner.set(int(u["id"]))
    notes_mod.current_family.set(_family_of(u))


_mcp_gate = auth.mcp_gate(mcp_enabled, on_user=_mcp_user)


def _before(request: Request):
    """Once the user is known: whose notes the request works on, and the MCP endpoint's gate (the switch; an app
    password or session, as in every app of the suite)."""
    refused = _mcp_gate(request)
    if refused is not None:
        return refused
    if not request.url.path.startswith("/mcp"):
        notes_mod.current_owner.set(_owner_of(request))
        notes_mod.current_family.set(_family_of(request.state.user))
    return None


def _limit_for(path: str, ctype: str) -> int:
    if "/api/import" in path:
        return config.MAX_IMPORT_BYTES
    if "/attachments" in path:
        return config.MAX_IMAGE_BYTES
    if ctype.startswith("image/") or ctype in ("multipart/form-data", "application/octet-stream", "application/zip"):
        return config.MAX_IMAGE_BYTES
    return config.MAX_JSON_BYTES


def _status_extra(request: Request) -> dict:
    """ioNote's own fields of GET /api/status, beside the suite's: the name an admin gave the app and,
    signed in, the account's change counter (the page polls it to learn of changes made elsewhere)."""
    out = {"appName": db.get_setting("app_name", "") or "ionote"}
    if users.is_signed_in(request.state.user):
        out["rev"] = notes_mod.owner_rev()
    return out


app = application.create(
    auth, updater, __version__, config,
    description="Notes for the family: each account's own, and the Family space's. The API the Mac and iPhone apps use, and an MCP "
                "endpoint (/mcp) for AI assistants.",
    prepare=(_open, users.init), jobs=_jobs, where=_where,
    mcp=mcp, mcp_enabled=mcp_enabled, before=_before,  # whose notes a request works on, and the MCP endpoint's gate
    open_paths=("/sw.js",),
    # the body cap is counted as the body arrives, so nothing large is ever held in memory; another account's note
    # answers the same 404 as none at all
    limit_for=_limit_for, not_found=(notes_mod.NotFound,),
    status=_status_extra, suite=suiteitems.PROVIDER,
    routers=(notes_routes.router, settings.router),
    service_worker=True)  # /, the manifest, /sw.js and /static


@app.exception_handler(notes_mod.Stale)
async def _stale(_request: Request, e: notes_mod.Stale):
    """An edit older than the server's copy, or of a family note by someone who only reads those: 409 with the
    server's copy, which the device takes."""
    return JSONResponse({"detail": e.detail, "current": e.current}, status_code=409)

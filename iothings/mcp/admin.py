"""The server itself, for admins: health."""
from iosuite_shared import mcp as shared_mcp

from iothings import __version__, config, db, users
from iothings.auth import updater
from iothings.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server version, things,
    places, files and their size), the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    from iothings.main import mcp_enabled
    return shared_mcp.diagnostics(config, __version__, updater, db, mcp_enabled, users.all_users(), counts=lambda: {
        "items": db.one("SELECT count(*) AS n FROM thg_items")["n"],
        "locations": db.one("SELECT count(*) AS n FROM thg_locations")["n"],
        "files": db.one("SELECT count(*) AS n FROM thg_files")["n"],
        "fileBytes": int(db.one("SELECT COALESCE(SUM(size), 0) AS n FROM thg_files")["n"])})


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles here (viewer, member, editor, admin)."""
    need_admin()
    return shared_mcp.account_list(users.all_users())

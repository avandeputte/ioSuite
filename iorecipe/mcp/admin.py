"""The server itself, for admins: health."""
from iosuite_shared import mcp as shared_mcp

from iorecipe import __version__, config, db, users
from iorecipe.auth import updater
from iorecipe.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server
    version, recipes, photos, cookbooks), the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    from iorecipe.main import mcp_enabled
    return shared_mcp.diagnostics(config, __version__, updater, db, mcp_enabled, users.all_users(), counts=lambda: {
        "recipes": db.one("SELECT count(*) AS n FROM rcp_recipes")["n"],
        "photos": db.one("SELECT count(*) AS n FROM rcp_photos")["n"],
        "cookbooks": db.one("SELECT count(*) AS n FROM rcp_books")["n"],
        "photoBytes": int(db.one("SELECT COALESCE(SUM(LENGTH(picture) + LENGTH(thumb)), 0) AS n FROM rcp_photos")["n"])})


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles here (viewer, member, editor, admin)."""
    need_admin()
    return shared_mcp.account_list(users.all_users())

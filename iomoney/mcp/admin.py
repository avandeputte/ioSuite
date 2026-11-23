"""The server itself, for admins: health."""
from iosuite_shared import mcp as shared_mcp

from iomoney import __version__, config, db, monarch, users
from iomoney.auth import updater
from iomoney.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server version, accounts,
    transactions, holdings, quotes), the Monarch sync, the MCP switch, the last update check and update, and the
    accounts with a role here."""
    need_admin()
    from iomoney.main import mcp_enabled
    out = shared_mcp.diagnostics(config, __version__, updater, db, mcp_enabled, users.all_users(), counts=lambda: {
        t: db.one(f"SELECT count(*) AS n FROM mny_{t}")["n"] for t in ("accounts", "transactions", "holdings", "quotes", "recurring")})
    if "error" not in out["database"]:
        out["monarch"] = monarch.status()
    return out

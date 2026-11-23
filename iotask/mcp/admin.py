"""The server itself, for admins: health."""
from iosuite_shared import mcp as shared_mcp

from iotask import __version__, config, db, ical, users
from iotask.auth import updater
from iotask.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the time zone, the database (server
    version, tables, rows), the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    from iotask.main import mcp_enabled
    return shared_mcp.diagnostics(config, __version__, updater, db, mcp_enabled, users.all_users(), counts=lambda: {
        "lists": db.one("SELECT count(*) AS n FROM tsk_lists")["n"],
        "tasks": db.one("SELECT count(*) AS n FROM tsk_tasks WHERE deleted = 0")["n"],
        "open": db.one("SELECT count(*) AS n FROM tsk_tasks WHERE deleted = 0 AND done = 0")["n"],
        "tombstones": db.one("SELECT count(*) AS n FROM tsk_tasks WHERE deleted = 1")["n"]}, timezone=ical.default_tz())


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles here (viewer, member, editor, admin)."""
    need_admin()
    return shared_mcp.account_list(users.all_users())

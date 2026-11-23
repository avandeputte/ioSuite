"""The server itself, for admins: health, accounts."""

from mcp.server.mcpserver.exceptions import ToolError

from iosuite_shared import mcp as shared_mcp

from iocontact import __version__, config, db, iopix, users
from iocontact.auth import auth, updater
from iocontact.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server version, tables,
    rows), the LDAP directory, ioPix, the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    from iocontact.main import mcp_enabled
    out = shared_mcp.diagnostics(config, __version__, updater, db, mcp_enabled, users.all_users(), counts=lambda: {
        "contacts": db.one("SELECT count(*) AS n FROM con_contacts WHERE deleted = 0")["n"],
        "tombstones": db.one("SELECT count(*) AS n FROM con_contacts WHERE deleted = 1")["n"],
        "relations": db.one("SELECT count(*) AS n FROM con_contact_relations")["n"],
        "addressBooks": db.one("SELECT count(*) AS n FROM con_address_books")["n"]},
        ldap={"port": config.LDAP_PORT, "base": config.LDAP_BASE} if config.LDAP_PORT else "off", proxySignIn=auth.proxy.mode())
    ip = iopix.public_settings()
    out["iopix"] = {"url": ip.get("url") or None, "connected": ip["enabled"]}
    return out


@server.tool(annotations=READ_ONLY)
def test_iopix() -> dict:
    """Admins: whether ioPix (found in the suite by itself) answers, and how many people it has."""
    need_admin()
    if not iopix.settings()["url"]:
        raise ToolError("ioPix is not part of the suite (it connects by itself once it runs on the same Shared ioSuite database)")
    return iopix.test()


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles (viewer, member, editor, admin)."""
    need_admin()
    return [{"name": u["name"], "displayName": u.get("display_name"), "email": u.get("email"), "role": u["role"]} for u in users.all_users()]

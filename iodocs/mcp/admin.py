"""The server itself, for admins: health."""
from iosuite_shared import mcp as shared_mcp

from iodocs import __version__, config, db, users
from iodocs.auth import updater
from iodocs.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server version, documents,
    files and their size), what the server can read off a scan, the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    from iodocs.main import mcp_enabled
    out = shared_mcp.diagnostics(config, __version__, updater, db, mcp_enabled, users.all_users(), counts=lambda: {
        "documents": db.one("SELECT count(*) AS n FROM doc_documents")["n"],
        "files": db.one("SELECT count(*) AS n FROM doc_files")["n"],
        "fileBytes": int(db.one("SELECT COALESCE(SUM(size), 0) AS n FROM doc_files")["n"])})
    from iodocs import ocr
    out["reads"] = ocr.available()
    return out


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles here (viewer, member, editor, admin)."""
    need_admin()
    return shared_mcp.account_list(users.all_users())

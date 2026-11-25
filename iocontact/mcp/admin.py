"""The server itself, for admins: health, accounts."""

from mcp.server.mcpserver.exceptions import ToolError

from iocontact import iopix
from iocontact.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def test_iopix() -> dict:
    """Admins: whether ioPix (found in the suite by itself) answers, and how many people it has."""
    need_admin()
    if not iopix.settings()["url"]:
        raise ToolError("ioPix is not part of the suite (it connects by itself once it runs on the same Shared ioSuite database)")
    return iopix.test()



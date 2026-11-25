"""The operator's tools, for admins: ioNote's log (its health is the suite's diagnostics tool, iosuite_shared.mcp)."""
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from ionote import config
from iosuite_shared.updates import tail
from ionote.mcp.base import READ_ONLY, need_admin, server

LOG_LINES_MAX = 2000


@server.tool(annotations=READ_ONLY)
def server_log(lines: int = 200, contains: str = "", level: Literal["any", "warning", "error", "auth"] = "any") -> dict:
    """The last lines of ioNote in the server's log. `contains` keeps only lines with that text;
    `level` keeps only WARNING+ or ERROR+ lines, or the sign-ins (auth)."""
    need_admin()
    if not config.LOG_FILE:
        raise ToolError("this server keeps no log file (LOG_FILE=off in its config.env)")
    try:
        return tail(config.APP, min(int(lines), LOG_LINES_MAX), contains, level)
    except OSError as e:
        raise ToolError(f"cannot read the log: {e}")

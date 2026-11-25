"""The MCP server: lets an AI assistant (Claude, for example) look up the things you own and keep their upkeep.

Served at /mcp by the web app (main.py) over streamable HTTP, and with `iosuite mcp iothings` over stdio. Every call acts as
one ioThings account and may do what that account may do in the web app; the server tools need an admin.

  base.py     the MCPServer instance, who is asking, and the shared helpers (finding a thing by name)
  items.py    the tools: overview, things, places, labels, upkeep and the maintenance log
"""
from iothings.mcp.base import server, current_user
from iothings.mcp import items  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "current_user", "items"]

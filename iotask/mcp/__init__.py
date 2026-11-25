"""The MCP server: lets an AI assistant (Claude, for example) read and keep the family's task lists.

Served at /mcp by the web app (main.py) over streamable HTTP, and with `iosuite mcp iotask` over stdio. Every call acts as
one ioTask account, so it sees that account's lists (the shared ones and its own private ones) and may change what the
account may change in the web app; the server tools need an admin.

  base.py   the MCPServer instance, who is asking, and the shared helpers (finding a list or a task by name)
  read.py   the read-only tools: overview, lists, tasks (today, overdue, by list, by member), search, one task
  write.py  the tools that change tasks and lists: add, change, tick off, delete, move, new list, import
"""
from iotask.mcp.base import server, current_user
from iotask.mcp import read, write  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "current_user", "read", "write"]

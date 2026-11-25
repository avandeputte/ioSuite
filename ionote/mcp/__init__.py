"""MCP server for ionote, in the same shape as iopix's.

Lets an MCP client such as Claude search the notes, read any note (and look at its picture), list folders and
tags, and, as a member, write: create, edit, file, tag, pin and delete notes, manage folders and tag
colours, plus the operator's tools (diagnostics, the server log, the change log, proxy sign-in).
It is served at /mcp by the web app (main.py) and can also run on its own with `iosuite mcp ionote` (stdio),
on the same database.

  base.py   the MCPServer instance, the admin-token gate and the helpers the tool modules share
  read.py   the read-only tools, on the signed-in account's own notes
  write.py  the tools that change notes, folders and tags (members)
  files.py  the operator's diagnostics (admins)
  prompts.py  ready-made requests (summarise a note, a weekly review, tidy up)
"""
from ionote.mcp.base import server, current_user
from ionote.mcp import read, write, files, prompts  # noqa: F401  importing them registers the tools and prompts on `server`

__all__ = ["server", "current_user", "read", "write", "files", "prompts", "set_user"]


def set_user(user) -> None:
    """Whose this call is: the account, and the notes it works on (its own). The web app's gate and the stdio server
    (`iosuite mcp ionote`) both go through here."""
    from ionote import notes
    current_user.set(user)
    notes.current_owner.set(int(user["id"]) if user else 0)
    notes.current_family.set(notes.family_for(user))

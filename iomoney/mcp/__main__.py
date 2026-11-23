"""`python -m iomoney.mcp [--user NAME]`: the MCP server over stdio, for clients that start a local process.
It acts as the account named by --user or MCP_USER (or the only admin, when there is just one):
iosuite_shared.mcp.stdio_user."""
from iosuite_shared import mcp as shared_mcp

from iomoney import config, db, users
from iomoney.mcp import current_user, server

db.migrate()
users.init()
current_user.set(shared_mcp.stdio_user(config.APP, config.MCP_USER, users.all_users()))
server.run()

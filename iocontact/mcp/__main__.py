"""`python -m iocontact.mcp [--user NAME]`: the MCP server over stdio, for clients that start a local process.
It acts as the account named by --user or MCP_USER (or the only admin, when there is just one):
iosuite_shared.mcp.stdio_user."""
from iosuite_shared import mcp as shared_mcp

from iocontact import config, db, model, users
from iocontact.mcp import current_user, server

db.migrate()
me = shared_mcp.stdio_user(config.APP, config.MCP_USER, users.all_users())
current_user.set(me)
model.viewer.set(me)  # relations into somebody else's private book stay hidden, as over HTTP
server.run()

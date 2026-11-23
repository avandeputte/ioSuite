"""`python -m ionote.mcp [--user NAME]`: the MCP server over stdio, for clients that start a local process, on the same
database as the web app. It acts as the account named by --user or MCP_USER (or the only admin, when there is just
one: iosuite_shared.mcp.stdio_user), on that account's own notes, as the HTTP endpoint does for a client signed in
with an app password."""
from iosuite_shared import mcp as shared_mcp, users

from ionote import config, db, notes
from ionote.mcp import current_user, server

if __name__ == "__main__":
    db.init()
    users.init()
    u = shared_mcp.stdio_user(config.APP, config.MCP_USER, users.list_users(config.APP))
    current_user.set(u)
    notes.current_owner.set(int(u["id"]))
    server.run()

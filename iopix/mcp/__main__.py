"""`python -m iopix.mcp [--user NAME]`: the MCP server over stdio, for clients that spawn a local process. It acts as
the account named by --user or MCP_USER (or the only admin, when there is just one: iosuite_shared.mcp.stdio_user), as
the HTTP endpoint does for a client signed in with an app password."""
from iosuite_shared import mcp as shared_mcp

from iopix import config, users
from iopix.data import state as appstate
from iopix.mcp import current_user, server
from iopix.photos import history

users.init()
# no accounts yet: the open install, as in the web app
me = shared_mcp.stdio_user(config.APP, config.MCP_USER, users.list_users(), open_install={"id": 0, "name": "owner", "role": "admin"})
current_user.set(me)
appstate.viewer.set(me)  # private albums and favourites: theirs, as over HTTP
history.user.set(me["name"])  # the change log names them, not "system"
server.run()

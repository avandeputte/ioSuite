"""Accounts, roles, sessions and app passwords: the suite's accounts (iosuite_shared), seen from ioTask.

Roles as in the rest of the suite: viewer (reads the shared lists), member (also keeps their own private lists),
editor (changes the shared lists too), admin (also settings and users); an account holds a role per app, a suite admin is admin everywhere. Web
sessions are the suite's cookie (shared by the apps on the domain). Reminders apps (CalDAV), the REST API and MCP use
HTTP Basic or a bearer app password (one per device, revocable, shown once).
"""
from iosuite_shared.users import AppUsers

from iotask.auth import APP

# get and find with the role held here, the accounts by name, and what the app does at start (iosuite_shared.users.AppUsers)
_users = AppUsers(APP)
ROLES, get, find, all_users, init = _users.ROLES, _users.get, _users.find, _users.all_users, _users.init

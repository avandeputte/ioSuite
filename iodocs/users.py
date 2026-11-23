"""Accounts, roles, sessions and app passwords: the suite's accounts (iosuite_shared), seen from ioDocs.

Roles as in the rest of the suite: viewer (looks at the documents they may see), member (adds documents and changes
the ones they added or that are theirs), editor (changes every document they may see, and sees the family's except
the private ones), admin (also the server and users); an account holds a role per app, a suite admin is admin
everywhere. Nobody has a role here until one is given (the default role is none): which documents each one then sees
is iodocs/model.py's. The REST API and MCP use HTTP Basic or a bearer app password (one per program, revocable, shown once).
"""
from iosuite_shared.users import AppUsers

from iodocs.auth import APP

# get and find with the role held here, the accounts by name, and what the app does at start (iosuite_shared.users.AppUsers)
# The default role is none, until a suite admin says otherwise (Settings › Apps › The apps): passports and policies
# are not for everyone with an account, so each person is given a role here by name.
_users = AppUsers(APP, default_role="none")
ROLES, get, find, all_users, init = _users.ROLES, _users.get, _users.find, _users.all_users, _users.init

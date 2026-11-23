"""Accounts, roles, sessions and app passwords: the suite's accounts (iosuite_shared), seen from ioMoney.

Roles as in the rest of the suite, read for money: viewer (sees the household's accounts, net worth and portfolio),
member (also keeps private accounts, holdings and things of their own), editor (changes the household's: categories,
values of the house and cars, holdings, transactions), admin (also the Monarch Money sync, settings and users); an
account with no role here sees nothing, so the finances stay with the people given a role. A suite admin is admin
everywhere. Web sessions are the suite's cookie (shared by the apps on the domain). The REST API and MCP use HTTP Basic
or a bearer app password (one per program, revocable, shown once).
"""
from iosuite_shared.users import AppUsers

from iomoney.auth import APP

# get and find with the role held here, the accounts by name, and what the app does at start (iosuite_shared.users.AppUsers)
# The default role is none, until a suite admin says otherwise (Settings › Apps › The apps): money is not for everyone
# in the family, so each person is given a role here by name.
_users = AppUsers(APP, default_role="none")
ROLES, get, find, all_users, init = _users.ROLES, _users.get, _users.find, _users.all_users, _users.init

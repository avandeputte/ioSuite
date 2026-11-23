"""Who may call a route, declared on the route itself: `dependencies=[access.signed_in]` (or editor, admin, public). The
markers come from iosuite-shared (app/auth.py). Every /api route carries one, and a test fails when one is missing.

- public: the sign-in endpoints and the status (iosuite-shared's routers)
- signed_in: an account: the page, the apps, the widgets, the bookmarks, Home Assistant's states
- member: a member or more keeping something of their own: the feeds they follow, what they read and starred
- editor: changing the bookmarks, switching what Home Assistant lets the page control
- admin: the home page, the weather, Home Assistant and the server settings, accounts
"""
from iostart.auth import auth

public = auth.access.public
signed_in = auth.access.signed_in
member = auth.access.member
editor = auth.access.editor
admin = auth.access.admin
declared = auth.access.declared

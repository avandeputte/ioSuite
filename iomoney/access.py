"""Who may call a route, declared on the route itself: `dependencies=[access.signed_in]` (or admin, public). The
markers come from iosuite_shared (iomoney/auth.py). Every /api route carries one, and a test fails when one is missing.

- public: the sign-in endpoints and the status
- signed_in: an account: everything else (what it may see and change is the money account's business: iomoney/model.py; nothing without a role in ioMoney)
- admin: users and the server
"""
from iomoney.auth import auth

public = auth.access.public
signed_in = auth.access.signed_in
admin = auth.access.admin
declared = auth.access.declared

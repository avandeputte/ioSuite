"""Sign-in: login, logout, the signed-in account's own settings and password, first-run setup: iosuite_shared's
routes, shared with the other ioSuite apps."""

from ionote.auth import auth

router = auth.router()

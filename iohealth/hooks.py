"""What ioHealth hangs on its sign-in (iosuite_shared.app calls setup once, as the app's Auth is made), and the two
helpers its routes use: every health figure belongs to someone."""
from fastapi import HTTPException, Request


def me(request: Request) -> dict:
    """The signed-in account, or 401: every health figure belongs to someone."""
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "Sign in to use ioHealth")
    return u


def uid(request: Request) -> int:
    return int(me(request)["id"])


def setup(auth) -> None:
    """Nothing beyond the manifest's (app.json: writeRole member, every account's data being its own)."""

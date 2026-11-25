"""What ioCalendar hangs on its sign-in (iosuite_shared.app calls setup once, as the app's Auth is made)."""


def _account_changed(user_id, body) -> None:
    """After someone changed their display name (Settings › Account) or an admin changed an account: the family list
    shows names, so it is read again."""
    from iocalendar import members
    members.forget()


def setup(auth) -> None:
    auth.on_update = _account_changed

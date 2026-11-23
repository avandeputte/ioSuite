"""Time zones, as every app that keeps dates reads them: the server's own, whether a name is one, and a moment in UTC.

    zones.server()            # "Europe/Brussels": TZ, else what /etc/localtime links to, else /etc/timezone; UTC when none
    zones.valid("Mars/Base")  # False
    zones.zone(name)          # the ZoneInfo, the server's when the name is not a zone
    zones.to_utc(d, name)     # a date, a floating or a zoned datetime as an aware UTC datetime
"""
import datetime as dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = dt.timezone.utc


def valid(name: str | None) -> bool:
    if not name:
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False


def _named():
    """What this server says its zone is, the most deliberate first."""
    tz = os.environ.get("TZ", "").strip().lstrip(":")
    if tz:
        yield tz
    try:
        p = str(Path("/etc/localtime").resolve())
        if "zoneinfo/" in p:
            yield p.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    try:
        yield Path("/etc/timezone").read_text().strip()
    except OSError:
        pass


def server() -> str:
    """The server's time zone: floating times (no zone) and new times without one are read in it. UTC when the server
    names none that is a zone."""
    return next((name for name in _named() if valid(name)), "UTC")


def zone(name: str | None) -> dt.tzinfo:
    return ZoneInfo(name) if valid(name) else ZoneInfo(server())


def to_utc(d, tzname: str | None = None) -> dt.datetime:
    """A date, floating or zoned datetime as an aware UTC datetime (a date: its midnight UTC; floating: in tzname or
    the server's zone)."""
    if isinstance(d, dt.datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=zone(tzname))
        return d.astimezone(UTC)
    return dt.datetime(d.year, d.month, d.day, tzinfo=UTC)

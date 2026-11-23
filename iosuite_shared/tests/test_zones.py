"""Time zones as every app that keeps dates reads them (iosuite_shared.zones): the server's own, whether a name is
one, a moment in UTC."""
import datetime as dt

from iosuite_shared import zones


def test_the_server_s_zone_is_the_first_it_names_that_is_one(monkeypatch):
    monkeypatch.setattr(zones, "_named", lambda: iter(["Mars/Base", "Europe/Brussels", "America/New_York"]))
    assert zones.server() == "Europe/Brussels"
    monkeypatch.setattr(zones, "_named", lambda: iter([]))
    assert zones.server() == "UTC"


def test_tz_in_the_environment_comes_first(monkeypatch):
    monkeypatch.setenv("TZ", ":Asia/Tokyo")
    assert zones.server() == "Asia/Tokyo"
    monkeypatch.setenv("TZ", "Not/AZone")
    assert zones.valid(zones.server())  # what the machine says next, or UTC


def test_names_and_moments(monkeypatch):
    assert zones.valid("Europe/Brussels") and not zones.valid("Mars/Base") and not zones.valid("") and not zones.valid(None)
    monkeypatch.setenv("TZ", "America/New_York")
    assert str(zones.zone("Europe/Brussels")) == "Europe/Brussels" and str(zones.zone("nope")) == "America/New_York"
    noon = dt.datetime(2026, 7, 1, 12, 0)
    assert zones.to_utc(noon, "Europe/Brussels") == dt.datetime(2026, 7, 1, 10, 0, tzinfo=zones.UTC)   # floating: in the zone named
    assert zones.to_utc(noon) == dt.datetime(2026, 7, 1, 16, 0, tzinfo=zones.UTC)                      # else the server's
    assert zones.to_utc(noon.replace(tzinfo=zones.UTC), "Europe/Brussels").hour == 12                  # zoned: as it is
    assert zones.to_utc(dt.date(2026, 7, 1)) == dt.datetime(2026, 7, 1, tzinfo=zones.UTC)              # a date: its midnight UTC

"""The iCalendar code ioCalendar and ioTask share (iosuite_shared.ical): the text in, the moments, one object per
UID, the repeat rule, the stamps and the whole feed out. Each app's own tests cover what it does with its own kind of
component."""
import datetime as dt

import pytest

from iosuite_shared import ical
from iosuite_shared.errors import Invalid

PRODID = "-//iothing//ioTest 1.0//EN"
EVENT = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VTIMEZONE\r
TZID:Europe/Brussels\r
BEGIN:STANDARD\r
DTSTART:19701025T030000\r
TZOFFSETFROM:+0200\r
TZOFFSETTO:+0100\r
TZNAME:CET\r
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10\r
END:STANDARD\r
BEGIN:DAYLIGHT\r
DTSTART:19700329T020000\r
TZOFFSETFROM:+0100\r
TZOFFSETTO:+0200\r
TZNAME:CEST\r
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3\r
END:DAYLIGHT\r
END:VTIMEZONE\r
BEGIN:VEVENT\r
UID:one@example.com\r
DTSTART;TZID=Europe/Brussels:20261103T100000\r
SUMMARY:Dentist\r
END:VEVENT\r
BEGIN:VTODO\r
UID:two@example.com\r
DUE;VALUE=DATE:20261105\r
SUMMARY:Pay the bill\r
END:VTODO\r
END:VCALENDAR\r
"""


@pytest.fixture
def fresh_db():
    """Overrides conftest's autouse database fixture: nothing here needs MariaDB."""
    yield


def test_the_prodid_is_the_app_and_the_suites_version():
    import iosuite_shared
    assert ical.prodid("iocalendar") == f"-//iothing//ioCalendar {iosuite_shared.__version__}//EN"


def test_parse_takes_a_bom_several_calendars_and_nothing_else():
    cal = ical.parse("﻿" + EVENT)
    assert ical.kinds_of(cal) == {"VEVENT", "VTODO"}
    assert [str(c.get("SUMMARY")) for c in ical.components_of(cal, "VEVENT")] == ["Dentist"]
    both = ical.parse(EVENT + EVENT.replace("one@", "three@").replace("two@", "four@"))
    assert len(ical.components_of(both, "VEVENT")) == 2  # several VCALENDARs in one file: one calendar with all of it
    for bad in ("", "hello", "<html>no calendar here</html>"):
        with pytest.raises(Invalid):
            ical.parse(bad)


def test_split_by_uid_keeps_the_zones_each_object_uses():
    objs = ical.split_by_uid(ical.parse(EVENT), "VEVENT", lambda: "made-up", PRODID)
    assert len(objs) == 1 and str(objs[0].get("PRODID")) == PRODID
    assert ical.kinds_of(objs[0]) == {"VEVENT"}  # the VTODO beside it is another app's
    assert [c.name for c in objs[0].subcomponents] == ["VTIMEZONE", "VEVENT"]  # the zone its DTSTART names, with it
    no_uid = ical.parse(EVENT.replace("UID:one@example.com\r\n", ""))
    made = ical.split_by_uid(no_uid, "VEVENT", lambda: "made-up", PRODID)[0]
    assert str(ical.components_of(made, "VEVENT")[0]["UID"]) == "made-up"


def test_the_master_is_the_one_without_a_recurrence_id():
    cal = ical.parse(EVENT.replace("SUMMARY:Dentist", "RECURRENCE-ID;TZID=Europe/Brussels:20261110T100000\r\nSUMMARY:Moved"))
    comps = ical.components_of(cal, "VEVENT")
    assert ical.master_of(comps) is comps[0]      # a lone changed occurrence: that one
    assert ical.master_of([]) is None


def test_moments_and_what_the_columns_keep():
    assert ical.iso(dt.date(2026, 11, 3)) == "2026-11-03" and ical.iso(None) is None
    assert ical.iso(dt.datetime(2026, 11, 3, 10, tzinfo=ical.UTC)) == "2026-11-03T10:00:00+00:00"
    assert ical.naive_utc(None) is None
    assert ical.naive_utc(dt.datetime(2026, 11, 3, 10, tzinfo=ical.zone("Europe/Brussels"))) == dt.datetime(2026, 11, 3, 9)
    assert ical.tz_name(dt.datetime(2026, 11, 3, 10, tzinfo=ical.zone("Europe/Brussels"))) == "Europe/Brussels"
    assert ical.tz_name(dt.date(2026, 11, 3)) is None and ical.tz_name(dt.datetime(2026, 11, 3, 10)) is None
    assert ical.parse_when("2026-11-03") == dt.date(2026, 11, 3)
    assert ical.parse_when("2026-11-03T10:00", "Europe/Brussels").utcoffset() == dt.timedelta(hours=1)
    assert ical.parse_when("2026-11-03T10:00", all_day=True) == dt.date(2026, 11, 3)
    for bad in ("", "soon", "2026-13-40"):
        with pytest.raises(Invalid):
            ical.parse_when(bad)


def test_a_repeat_rule_from_a_line_or_its_parts_and_a_task_repeats_daily_at_most():
    assert ical.rrule(None) is None and ical.rrule("") is None
    assert ical.rrule("RRULE:FREQ=WEEKLY;BYDAY=MO").to_ical().decode() == "FREQ=WEEKLY;BYDAY=MO"
    assert ical.rrule({"freq": "DAILY", "byday": ["MO", "TU"]})["FREQ"] == ["DAILY"]
    with pytest.raises(Invalid):
        ical.rrule("BYDAY=MO")          # no FREQ
    assert ical.rrule("FREQ=HOURLY")["FREQ"] == ["HOURLY"]
    with pytest.raises(Invalid):
        ical.rrule("FREQ=HOURLY", daily_at_most=True)


def test_until_takes_the_kind_of_the_moment_it_is_anchored_to():
    r = ical.fit_until(ical.rrule("FREQ=WEEKLY;UNTIL=20261231T235959Z"), dt.date(2026, 11, 3))
    assert r["UNTIL"] == [dt.date(2026, 12, 31)]   # a whole-day series: a date
    zoned = dt.datetime(2026, 11, 3, 10, tzinfo=ical.zone("Europe/Brussels"))
    r = ical.fit_until(ical.rrule("FREQ=WEEKLY;UNTIL=20261231"), zoned)
    assert r["UNTIL"][0] == dt.datetime(2026, 12, 31, 22, 59, 59, tzinfo=ical.UTC)  # a zoned start: UTC
    assert ical.fit_until(ical.rrule("FREQ=WEEKLY"), None)["FREQ"] == ["WEEKLY"]


def test_setting_a_property_removes_it_when_the_value_is_empty():
    ev = ical.components_of(ical.parse(EVENT), "VEVENT")[0]
    ical.set_prop(ev, "SUMMARY", "Doctor")
    assert str(ev["SUMMARY"]) == "Doctor"
    ical.set_prop(ev, "SUMMARY", "")
    assert "SUMMARY" not in ev
    ical.set_prop(ev, "ATTENDEE", "mailto:a@b.c", {"CN": "Ann"})
    assert ev["ATTENDEE"].params["CN"] == "Ann"


def test_the_stamps_say_when_and_how_many_times():
    ev = ical.components_of(ical.parse(EVENT), "VEVENT")[0]
    ical.stamp(ev)
    assert "DTSTAMP" in ev and "CREATED" in ev and int(ev["SEQUENCE"]) == 0  # a new object: no bump yet
    created = ev["CREATED"].dt
    ical.stamp(ev)
    assert int(ev["SEQUENCE"]) == 1 and ev["CREATED"].dt == created
    ical.stamp(ev, bump=False)
    assert int(ev["SEQUENCE"]) == 1


def test_only_a_safe_link_is_kept():
    assert ical.safe_url("https://example.com/x") == "https://example.com/x"
    assert ical.safe_url("mailto:a@b.c") == "mailto:a@b.c"
    for bad in (None, "", "javascript:alert(1)", "file:///etc/passwd", "data:text/html,x"):
        assert ical.safe_url(bad) is None


def test_a_feed_holds_each_zone_once_and_only_the_kinds_asked_for():
    out = ical.feed([EVENT, EVENT.replace("one@", "three@").replace("two@", "four@")], "Family", PRODID,
                    kinds=("VEVENT",), description="ours", color="#146b5e", tzname="Europe/Brussels", refresh_hours=2)
    assert out.count("BEGIN:VTIMEZONE") == 1 and out.count("BEGIN:VEVENT") == 2 and "BEGIN:VTODO" not in out
    assert "X-WR-CALNAME:Family" in out and "X-WR-CALDESC:ours" in out and "X-APPLE-CALENDAR-COLOR:#146b5e" in out
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT2H" in out and "METHOD:PUBLISH" in out
    plain = ical.feed([EVENT], "Tasks", PRODID, kinds=("VTODO",))
    assert "BEGIN:VTODO" in plain and "BEGIN:VEVENT" not in plain and "METHOD:PUBLISH" not in plain


def test_a_zone_on_its_own_for_caldav():
    out = ical.vtimezone(PRODID, "Europe/Brussels")
    assert "BEGIN:VTIMEZONE" in out and "TZID:Europe/Brussels" in out and "BEGIN:VEVENT" not in out
    assert ical.vtimezone(PRODID, None) is None


def test_the_file_out_and_its_etag():
    cal = ical.finish(ical.new_calendar(PRODID), PRODID)
    out = ical.text(cal)
    assert out.startswith("BEGIN:VCALENDAR") and PRODID in out
    assert ical.etag_of(out) == ical.etag_of(out) and len(ical.etag_of(out)) == 24
    assert ical.etag_of(out) != ical.etag_of(out + " ")

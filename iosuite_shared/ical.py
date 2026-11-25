"""iCalendar (RFC 5545), the parts ioCalendar and ioTask both need.

An event and a to-do are different things, but reading and writing the file around them is the same work: the text
in, the zones, the moments, one object per UID, the repeat rule, the stamps, and the whole feed out. Both apps had
their own copy of it; this is the one.

    from iosuite_shared import ical as shared_ical

    PRODID = shared_ical.prodid("iotask")               # -//iothing//ioTask 4.2.2//EN
    cal = shared_ical.parse(text)                       # one VCALENDAR, Invalid when the text is not iCalendar
    for obj in shared_ical.split_by_uid(cal, "VTODO", new_uid):   # an import, one object per UID
        ...
    shared_ical.set_prop(todo, "SUMMARY", title)        # replace a property, remove it when the value is empty
    shared_ical.stamp(todo)                             # DTSTAMP, LAST-MODIFIED, CREATED, SEQUENCE
    print(shared_ical.text(shared_ical.finish(cal, PRODID)))

What stays in each app is what knows about its own kind of component: the columns it indexes, how it reads a due
date or a start and end, what its web app may edit, recurrence over events, completing a repeating task.
"""
import datetime as dt
import hashlib
import re
import uuid as uuidlib

from icalendar import Calendar, Event, vRecur

from iosuite_shared import zones
from iosuite_shared.errors import Invalid

UTC = dt.timezone.utc
default_tz, valid_tz, zone, to_utc = zones.server, zones.valid, zones.zone, zones.to_utc
TZ_PROPS = ("DTSTART", "DTEND", "DUE", "RECURRENCE-ID", "EXDATE", "RDATE")  # properties that may carry a TZID
FEED_KINDS = ("VEVENT", "VTODO", "VJOURNAL")


# ---- the header
def prodid(app: str) -> str:
    """What the app writes as PRODID: its name and the suite's version."""
    from iosuite_shared import __version__, catalog
    return f"-//iothing//{catalog.name_of(app)} {__version__}//EN"


def new_calendar(prodid: str) -> Calendar:
    c = Calendar()
    c.add("PRODID", prodid)
    c.add("VERSION", "2.0")
    return c


def finish(cal: Calendar, prodid: str) -> Calendar:
    """VTIMEZONE definitions for every zone the components use (calendar and reminders apps want them), and the header."""
    if "PRODID" not in cal:
        cal.add("PRODID", prodid)
    if "VERSION" not in cal:
        cal.add("VERSION", "2.0")
    try:
        cal.add_missing_timezones()
    except Exception:  # noqa: BLE001 - a zone the library cannot describe: apps fall back on its name
        pass
    return cal


def text(cal: Calendar) -> str:
    return cal.to_ical().decode("utf-8")


def etag_of(ics: str) -> str:
    return hashlib.sha1(ics.encode("utf-8")).hexdigest()[:24]


def uuid() -> str:
    return str(uuidlib.uuid4())


# ---- moments
def tz_name(d) -> str | None:
    """The IANA name of a datetime's zone (None for floating times and dates; 'UTC' for UTC)."""
    if not isinstance(d, dt.datetime) or d.tzinfo is None:
        return None
    k = getattr(d.tzinfo, "key", None) or getattr(d.tzinfo, "zone", None)
    if k:
        return k
    if d.utcoffset() == dt.timedelta(0):
        return "UTC"
    try:
        from icalendar.timezone import tzid_from_dt
        return tzid_from_dt(d)
    except Exception:  # noqa: BLE001
        return None


def naive_utc(d, tzname: str | None = None) -> dt.datetime | None:
    """For the DATETIME columns."""
    return None if d is None else to_utc(d, tzname).replace(tzinfo=None)


def iso(d) -> str | None:
    """A date as YYYY-MM-DD, a datetime as ISO 8601 with its offset (floating: without one)."""
    if d is None:
        return None
    if isinstance(d, dt.datetime):
        return d.isoformat(timespec="seconds")
    return d.isoformat()


def parse_when(s: str, tzname: str | None = None, all_day: bool = False):
    """'2026-11-03' (a date) or '2026-11-03T10:00[:00][Z|+01:00]' (a datetime: without an offset it is wall time in
    tzname). Invalid when it is neither."""
    s = (s or "").strip()
    if not s:
        raise Invalid("A date or time is missing")
    try:
        if all_day or re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return dt.date.fromisoformat(s[:10])
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise Invalid(f"Not an ISO date or date-time: {s}")
    if d.tzinfo is None:
        d = d.replace(tzinfo=zone(tzname))
    return d.replace(microsecond=0)


def vtimezone(prodid: str, name: str | None) -> str | None:
    """A VTIMEZONE for a zone on its own (CalDAV's calendar-timezone)."""
    if not name:
        return None
    cal = new_calendar(prodid)
    ev = Event()
    ev.add("DTSTART", dt.datetime(2026, 1, 1, tzinfo=zone(name)))
    cal.add_component(ev)
    try:
        cal.add_missing_timezones()
    except Exception:  # noqa: BLE001
        return None
    cal.subcomponents[:] = [c for c in cal.subcomponents if c.name == "VTIMEZONE"]
    return text(cal) if cal.subcomponents else None


# ---- the text in
def parse(text: str | bytes) -> Calendar:
    """One VCALENDAR; Invalid when the text is not iCalendar. Several VCALENDARs in one file (some exports) become
    one calendar with all their components."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = text.lstrip("﻿")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise Invalid("Not an iCalendar object (no BEGIN:VCALENDAR)")
    try:
        cals = Calendar.from_ical(text, multiple=True)
    except Exception as e:  # noqa: BLE001 - the library raises several kinds
        raise Invalid(f"Not valid iCalendar: {e}") from e
    if not cals:
        raise Invalid("No VCALENDAR in the text")
    out = cals[0]
    for c in cals[1:]:
        for sub in c.subcomponents:
            out.add_component(sub)
    return out


def components_of(cal: Calendar, name: str) -> list:
    return [c for c in cal.subcomponents if c.name == name]


def kinds_of(cal: Calendar) -> set:
    """The components in an object besides time zones (a CalDAV collection takes one kind)."""
    return {s.name for s in cal.subcomponents if s.name != "VTIMEZONE"}


def master_of(comps: list):
    """The component without a RECURRENCE-ID (the series, or the one object); for a lone changed occurrence, that one."""
    for c in comps:
        if "RECURRENCE-ID" not in c:
            return c
    return comps[0] if comps else None


def split_by_uid(cal: Calendar, kind: str, new_uid, prodid: str) -> list:
    """A calendar with many components of one kind (an import, a feed) as one calendar object per UID, each with the
    VTIMEZONEs it uses."""
    tzs = {str(c.get("TZID")): c for c in cal.subcomponents if c.name == "VTIMEZONE"}
    groups: dict = {}
    for comp in components_of(cal, kind):
        uid = str(comp.get("UID") or "").strip() or new_uid()
        if "UID" not in comp:
            comp.add("UID", uid)
        groups.setdefault(uid, []).append(comp)
    out = []
    for comps in groups.values():
        c = new_calendar(prodid)
        used = set()
        for comp in comps:
            for k in TZ_PROPS:
                vals = comp.get(k)
                for v in (vals if isinstance(vals, list) else [vals]):
                    if v is not None and getattr(v, "params", None) and v.params.get("TZID"):
                        used.add(str(v.params["TZID"]))
        for name in sorted(used):
            if name in tzs:
                c.add_component(tzs[name])
        for comp in sorted(comps, key=lambda x: "RECURRENCE-ID" in x):  # the series first, then its changed occurrences
            c.add_component(comp)
        out.append(c)
    return out


def feed(objects: list, name: str, prodid: str, kinds=FEED_KINDS, description: str = "", color: str | None = None,
         tzname: str | None = None, refresh_hours: int | None = None) -> str:
    """Many calendar objects (parsed, or as text) as one VCALENDAR (a subscription or an export), each VTIMEZONE
    once. The objects are read only: their components go into the new calendar as they are."""
    out = new_calendar(prodid)
    if refresh_hours:
        out.add("CALSCALE", "GREGORIAN")
        out.add("METHOD", "PUBLISH")
    out.add("X-WR-CALNAME", name)
    if description:
        out.add("X-WR-CALDESC", description)
    if tzname:
        out.add("X-WR-TIMEZONE", tzname)
    if color:
        out.add("X-APPLE-CALENDAR-COLOR", color)
    if refresh_hours:
        out.add("REFRESH-INTERVAL", dt.timedelta(hours=refresh_hours), parameters={"VALUE": "DURATION"})
        out.add("X-PUBLISHED-TTL", dt.timedelta(hours=refresh_hours))
    tzs: dict = {}
    items = []
    for o in objects:
        cal = o if isinstance(o, Calendar) else parse(o)
        for sub in cal.subcomponents:
            if sub.name == "VTIMEZONE":
                tzs.setdefault(str(sub.get("TZID")), sub)
            elif sub.name in kinds:
                items.append(sub)
    for z in tzs.values():
        out.add_component(z)
    for i in items:
        out.add_component(i)
    return out.to_ical().decode("utf-8")


# ---- writing a component
def set_prop(comp, name: str, value, params: dict | None = None) -> None:
    """Replace a property, or remove it when the value is empty."""
    if name in comp:
        del comp[name]
    if value not in (None, "", []):
        comp.add(name, value, parameters=params)


def stamp(comp, bump: bool = True) -> None:
    """DTSTAMP and LAST-MODIFIED now, CREATED the first time, and SEQUENCE one further on a change."""
    now = dt.datetime.now(UTC).replace(microsecond=0)
    set_prop(comp, "DTSTAMP", now)
    set_prop(comp, "LAST-MODIFIED", now)
    if "CREATED" not in comp:
        comp.add("CREATED", now)
    if bump:
        set_prop(comp, "SEQUENCE", int(str(comp.get("SEQUENCE") or 0) or 0) + (1 if "SEQUENCE" in comp else 0))


def safe_url(u) -> str | None:
    """A link on an item: http(s) or mailto only (never javascript: or the like), else none."""
    u = (u or "").strip()[:2000]
    return u if re.match(r"^(https?://|mailto:)", u, re.I) else None


def rrule(value, daily_at_most: bool = False):
    """A repeat rule from a RRULE line ('FREQ=WEEKLY;BYDAY=MO') or a dict of its parts; None removes it. Invalid when
    it is not a rule. `daily_at_most`: a rule that repeats within the day is refused (a task's)."""
    if not value:
        return None
    if isinstance(value, dict):
        value = ";".join(f"{k.upper()}={','.join(map(str, v)) if isinstance(v, list) else v}" for k, v in value.items())
    value = str(value).strip()
    if value.upper().startswith("RRULE:"):
        value = value[6:]
    try:
        r = vRecur.from_ical(value)
    except Exception as e:  # noqa: BLE001
        raise Invalid(f"Not a repeat rule (RRULE): {value}") from e
    if not r.get("FREQ"):
        raise Invalid("A repeat rule needs FREQ (DAILY, WEEKLY, MONTHLY or YEARLY)")
    if daily_at_most and str(r["FREQ"][0]).upper() in ("SECONDLY", "MINUTELY", "HOURLY"):
        raise Invalid("A task repeats daily at most")
    return r


def fit_until(r: vRecur, anchor) -> vRecur:
    """UNTIL has to be of the anchor's kind (RFC 5545): a date for a date, UTC for a zoned time."""
    u = r.get("UNTIL")
    if not u or anchor is None:
        return r
    u = u[0] if isinstance(u, list) else u
    if not isinstance(anchor, dt.datetime):
        r["UNTIL"] = [u.date() if isinstance(u, dt.datetime) else u]
    else:
        if not isinstance(u, dt.datetime):
            u = dt.datetime.combine(u, dt.time(23, 59, 59), anchor.tzinfo)
        r["UNTIL"] = [to_utc(u) if anchor.tzinfo else u.replace(tzinfo=None)]
    return r

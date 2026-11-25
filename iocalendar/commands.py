"""ioCalendar's own commands from a shell, beside the migrate and check every app has (iosuite_shared.appcli):

    iosuite iocalendar import 3 holidays.ics      events from an .ics file into a calendar
    iosuite iocalendar sync-birthdays             bring the Birthdays calendar up to date from ioContact
    iosuite iocalendar sync-holidays              bring the Holidays calendars up to date
"""
from pathlib import Path


def add(sub) -> None:
    p = sub.add_parser("import", help="events from an .ics file into a calendar")
    p.add_argument("calendar", type=int, help="the calendar's id")
    p.add_argument("file")
    p.set_defaults(run=_import)
    sub.add_parser("sync-birthdays", help="bring the Birthdays calendar up to date from ioContact").set_defaults(run=_birthdays)
    sub.add_parser("sync-holidays", help="bring the Holidays calendars up to date (Settings › Holidays and birthdays)").set_defaults(run=_holidays)


def _import(a) -> None:
    from iocalendar import model
    print(model.import_text(a.calendar, Path(a.file).read_text(encoding="utf-8", errors="replace")))


def _birthdays(_a) -> None:
    from iocalendar import contacts
    print(contacts.sync_birthdays())


def _holidays(_a) -> None:
    from iocalendar import holiday
    print(holiday.sync())

"""The server itself, for admins: the Birthdays calendar from ioContact and the Holidays calendars."""
from typing import Optional

from mcp.server.mcpserver.exceptions import ToolError

from iocalendar import contacts, holiday
from iocalendar.mcp.base import READ_ONLY, UPDATES, WRITES, need_admin, server


@server.tool(annotations=UPDATES)
def sync_birthdays() -> dict:
    """Admins: bring the Birthdays calendar up to date from ioContact now (it also happens every few hours)."""
    need_admin()
    if not contacts.enabled():
        raise ToolError("ioContact is not part of the suite (it connects by itself once it runs on the same Shared ioSuite database)")
    return contacts.sync_birthdays()


@server.tool(annotations=WRITES)
def set_holidays(country: str, region: Optional[str] = None, language: Optional[str] = None, remove: bool = False) -> dict:
    """Admins: add a shared Holidays calendar for a country, or change the region or language of one already there
    (each country has its own calendar; others stay). country: a two-letter code (US, BE, NL, GB...); region: a state or
    province code of that country (US: NY, CA...; BE: none); language: of the holiday names (e.g. nl, fr), else the
    country's own; remove: true takes that country's calendar away. Use holiday_regions to see the choices."""
    need_admin()
    try:
        if remove:
            holiday.remove_country(country)
        else:
            holiday.set_country(country, region, language)
    except ValueError as e:
        raise ToolError(str(e))
    sync = holiday.sync()
    return {"countries": [{k: x[k] for k in ("country", "countryName", "region", "language")} for x in holiday.public_settings()["items"]],
            "sync": sync}


@server.tool(annotations=READ_ONLY)
def holiday_regions(country: str) -> dict:
    """The regions (states, provinces...) of a country and the languages its holiday names come in."""
    try:
        return holiday.country_info(country)
    except ValueError as e:
        raise ToolError(str(e))



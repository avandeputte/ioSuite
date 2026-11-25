"""Settings: ioCalendar's own are kept in the Shared ioSuite database and read once, as it starts (Settings › Apps ›
All settings changes them; app.json lists them). The settings every app of the suite shares come from
iosuite_shared.config.standard; the machine's file says only where that database is and where the server listens."""
from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
live, live_flag, live_int = _own["live"], _own["live_flag"], _own["live_int"]
env = _own["env"]

# the time zone new events and all-day feeds default to is the suite's TZ (the server's own when empty)

# public holidays (Settings › Holidays and birthdays wins once an admin has chosen): a two-letter country code or several,
# comma-separated (off: none), and optionally the first one's region (a state or province code) and the language of its
# names; no country: the time zone's
HOLIDAYS_COUNTRY = env("HOLIDAYS_COUNTRY").strip()
HOLIDAYS_REGION = env("HOLIDAYS_REGION").strip().upper()
HOLIDAYS_LANGUAGE = env("HOLIDAYS_LANGUAGE").strip()

# ioContact is found in the suite's list of apps and signed in to by itself (iocalendar/contacts.py): nothing to set

# MCP_USER (iosuite_shared.config.standard): the account `iosuite mcp iocalendar` (stdio) acts as

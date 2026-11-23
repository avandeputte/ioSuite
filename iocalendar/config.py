"""Settings: ioCalendar's own are kept in the Shared ioSuite database and read once, as it starts (Settings › Global settings ›
Settings changes them; app.json lists them). The settings every app of the suite shares come from
iosuite_shared.config.standard; the machine's file says only where that database is and where the server listens."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iocalendar"
APP_DIR = Path(__file__).resolve().parent
_s = shared.settings(APP)  # what is stored for this app in the Shared ioSuite database, read once, now
env, env_flag, env_int = _s.get, _s.flag, _s.int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR, _s))

# the app's own database: beside the Shared ioSuite database, under the same login (DB_NAME names another than iocalendar)
_db = shared.own_db(APP, _s)
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

# the time zone new events and all-day feeds default to is the suite's TZ (the server's own when empty)

# public holidays (Settings › Holidays and birthdays wins once an admin has chosen): a two-letter country code or several,
# comma-separated (off: none), and optionally the first one's region (a state or province code) and the language of its
# names; no country: the time zone's
HOLIDAYS_COUNTRY = env("HOLIDAYS_COUNTRY").strip()
HOLIDAYS_REGION = env("HOLIDAYS_REGION").strip().upper()
HOLIDAYS_LANGUAGE = env("HOLIDAYS_LANGUAGE").strip()

# ioContact is found in the suite's list of apps and signed in to by itself (app/contacts.py): nothing to set

MAX_EVENT_BYTES = 2 * 1024 * 1024     # one calendar object (CalDAV PUT, REST)
MAX_IMPORT_BYTES = 32 * 1024 * 1024   # an .ics file to import
MAX_JSON_BYTES = 4 * 1024 * 1024      # any other request body

# MCP_USER (iosuite_shared.config.standard): the account `python -m iocalendar.mcp` (stdio) acts as

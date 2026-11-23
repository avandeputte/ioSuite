"""Settings: ioStart's own are kept in the Shared ioSuite database and read once, as it starts (Settings › Global settings ›
Settings changes them; app.json lists them). The settings every app of the suite shares come from
iosuite_shared.config.standard; the machine's file says only where that database is and where the server listens."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iostart"
APP_DIR = Path(__file__).resolve().parent
_s = shared.settings(APP)  # what is stored for this app in the Shared ioSuite database, read once, now
env, env_flag, env_int = _s.get, _s.flag, _s.int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR, _s))
ROOT = APP_DIR

# the app's own database: beside the Shared ioSuite database, under the same login (DB_NAME names another than iostart)
_db = shared.own_db(APP, _s)
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

# where the apps are: each registers itself in the suite's list in the Shared ioSuite database (see apps.py)

# the weather and Home Assistant are set in Settings (the key and the token with the suite's keys and tokens)
HA_FEED = env_flag("HA_FEED", True)   # HA_FEED=0: no websocket to Home Assistant, the page polls instead
SITE_ICONS = env_flag("SITE_ICONS", True)   # SITE_ICONS=0: the server does not fetch the bookmarked sites' icons
TIMERS_LOOP = env_flag("TIMERS_LOOP", True)   # TIMERS_LOOP=0: no thread that sends "timer done" notifications (timers.py; the tests call tick())
NEWS_LOOP = env_flag("NEWS_LOOP", True)   # NEWS_LOOP=0: the server does not fetch the feeds people follow by itself (news.py; the tests call tick())
TRMNL_PUSH = env_flag("TRMNL_PUSH", True)   # TRMNL_PUSH=0: the start page does not push anyone's TRMNL screens (trmnlpush.py)

MAX_IMPORT_BYTES = 16 * 1024 * 1024   # a bookmarks file to import
MAX_JSON_BYTES = 4 * 1024 * 1024      # any other request body

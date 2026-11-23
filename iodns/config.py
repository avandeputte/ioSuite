"""Settings: kept in the Shared ioSuite database and read once, as the app starts (Settings › Global settings › Settings
changes them; app.json lists the app's own). Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iodns"
APP_DIR = Path(__file__).resolve().parent
_s = shared.settings(APP)  # what is stored for this app in the Shared ioSuite database, read once, now
env, env_flag, env_int = _s.get, _s.flag, _s.int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR, _s))

# the app's own database: beside the Shared ioSuite database, under the same login (DB_NAME names another than iodns)
_db = shared.own_db(APP, _s)
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

TZ = env("TZ")

# how often the servers are compared with the master list on their own (minutes; 0: only when someone looks)
CHECK_MINUTES = env_int("CHECK_MINUTES", 30)

MAX_JSON_BYTES = 4 * 1024 * 1024   # any request body (an import of a few thousand entries fits)


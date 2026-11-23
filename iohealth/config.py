"""Settings: ioHealth's own are kept in the Shared ioSuite database and read once, as it starts (Settings › Global
settings › Settings changes them; app.json lists them). The names every app of the suite shares come from
iosuite_shared.config.standard; the machine's file says only where that database is and where the server listens.

The health data lives in a database of its own (iohealth, unless DB_NAME names another), beside the Shared ioSuite
database on the same server and under the same login.
"""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iohealth"
APP_DIR = Path(__file__).resolve().parent
_s = shared.settings(APP)  # what is stored for this app in the Shared ioSuite database, read once, now
env, env_flag, env_int = _s.get, _s.flag, _s.int

# DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE, ADMIN_USER,
# ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR, _s))

# the health data: {host, port, database, user, password}
_db = shared.own_db(APP, _s)
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

MAP_TILE_URL = env("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
MAP_TILE_ATTRIBUTION = env("MAP_TILE_ATTRIBUTION", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors')

# Fallback time zone for days and weeks when a request carries no tz parameter.
TZ = env("TZ", "UTC")

# the most a JSON request may carry; the phone's uploads (/v1/) have their own cap, app.upload.MAX_BODY
MAX_JSON_BYTES = 4 << 20

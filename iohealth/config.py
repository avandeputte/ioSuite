"""Settings: ioHealth's own are kept in the Shared ioSuite database and read once, as it starts (Settings › Global
settings › Settings changes them; app.json lists them). The names every app of the suite shares come from
iosuite_shared.config.standard; the machine's file says only where that database is and where the server listens.

The health data lives in a database of its own (iohealth, unless DB_NAME names another), beside the Shared ioSuite
database on the same server and under the same login.
"""
from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
env = _own["env"]

MAP_TILE_URL = env("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
MAP_TILE_ATTRIBUTION = env("MAP_TILE_ATTRIBUTION", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors')

# Fallback time zone for days and weeks when a request carries no tz parameter.
TZ = env("TZ", "UTC")

# the most a JSON request may carry; the phone's uploads (/v1/) have their own cap, app.upload.MAX_BODY

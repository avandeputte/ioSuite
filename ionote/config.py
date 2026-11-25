"""Paths and tunables: kept in the Shared ioSuite database and read once, as the app starts (Settings › Apps › All settings
changes them; app.json lists the app's own). The settings every app of the suite shares come from iosuite_shared.config.standard.

Everything ioNote keeps lives in its MariaDB/MySQL database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).
The notes' images are stored in the database too (BLOBs), so one database backup holds everything. DATA_DIR only
keeps the log and the update result.
"""
from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
env_int = _own["env_int"]

# the largest image a note may carry; MariaDB's max_allowed_packet (16 MB by default) must be larger
MAX_IMAGE_MB = env_int("MAX_IMAGE_MB", 15)
THUMB_SIZE = env_int("THUMB_SIZE", 480)
THUMB_QUALITY = env_int("THUMB_QUALITY", 80)

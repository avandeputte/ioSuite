"""Paths and tunables: kept in the Shared ioSuite database and read once, as the app starts (Settings › Global settings › Settings
changes them; app.json lists the app's own). The settings every app of the suite shares come from iosuite_shared.config.standard.

Everything ioNote keeps lives in its MariaDB/MySQL database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).
The notes' images are stored in the database too (BLOBs), so one database backup holds everything. DATA_DIR only
keeps the log and the update result.
"""
from pathlib import Path

from iosuite_shared import config as shared

APP = "ionote"
APP_DIR = Path(__file__).resolve().parent
_s = shared.settings(APP)  # what is stored for this app in the Shared ioSuite database, read once, now
env, env_flag, env_int = _s.get, _s.flag, _s.int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR, _s))

# MCP_USER (iosuite_shared.config.standard): the account `python -m ionote.mcp` (stdio) acts as

# the app's own database: beside the Shared ioSuite database, under the same login (DB_NAME names another than ionote)
_db = shared.own_db(APP, _s)
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

# the largest image a note may carry; MariaDB's max_allowed_packet (16 MB by default) must be larger
MAX_IMAGE_MB = env_int("MAX_IMAGE_MB", 15)
THUMB_SIZE = env_int("THUMB_SIZE", 480)
THUMB_QUALITY = env_int("THUMB_QUALITY", 80)
MAX_JSON_BYTES = 8 << 20                  # a JSON request larger than this is refused before it is read (pictures go as their own body)
MAX_IMAGE_BYTES = (MAX_IMAGE_MB + 1) << 20
MAX_IMPORT_BYTES = 4 << 30                # an export with every picture; spooled to disk as it arrives, never held in memory


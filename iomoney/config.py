"""Settings: kept in the Shared ioSuite database and read once, as the app starts (Settings › Global settings › Settings
changes them; app.json lists the app's own). Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard.

The Monarch Money sign-in and any other key are not settings: they are kept in the Shared ioSuite database with the
suite's other keys and tokens (Settings › Global settings › Keys and tokens; app/monarch.py declares them)."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iomoney"
APP_DIR = Path(__file__).resolve().parent
_s = shared.settings(APP)  # what is stored for this app in the Shared ioSuite database, read once, now
env, env_flag, env_int = _s.get, _s.flag, _s.int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR, _s))

# the app's own database: beside the Shared ioSuite database, under the same login (DB_NAME names another than iomoney)
_db = shared.own_db(APP, _s)
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

MAX_JSON_BYTES = 2 * 1024 * 1024      # a request body
MAX_IMPORT_BYTES = 20 * 1024 * 1024   # a CSV file of transactions or holdings
MAX_RECEIPT_BYTES = 20 * 1024 * 1024  # one receipt (a picture or a PDF) as uploaded

# the background work (app/chores.py): SYNC=0 stops it (Monarch, quotes and notifications then only run when asked)
SYNC = env_flag("SYNC", True)

# MCP_USER (iosuite_shared.config.standard): the account `python -m iomoney.mcp` (stdio) acts as

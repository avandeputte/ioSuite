"""Settings: kept in the Shared ioSuite database and read once, as the app starts (Settings › Global settings › Settings
changes them; app.json lists the app's own). Everything stored
lives in MariaDB, the scans of the documents too (so a backup of the database is a backup of everything). The
settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iodocs"
APP_DIR = Path(__file__).resolve().parent
_s = shared.settings(APP)  # what is stored for this app in the Shared ioSuite database, read once, now
env, env_flag, env_int = _s.get, _s.flag, _s.int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR, _s))

# the app's own database: beside the Shared ioSuite database, under the same login (DB_NAME names another than iodocs)
_db = shared.own_db(APP, _s)
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

MAX_FILE_BYTES = env_int("MAX_FILE_MB", 100) * 1024 * 1024  # one file (a scan, a photo, a policy's PDF) as uploaded
TESSERACT = env("TESSERACT", "tesseract")  # the OCR program that reads the scans (app/ocr.py); "off": never read them
OCR_LANGS = env("OCR_LANGS", "eng")        # Tesseract's languages, eng+fra+deu say (each needs its tesseract-ocr-<lang> package)
MAX_JSON_BYTES = 2 * 1024 * 1024      # any other request body

# MCP_USER (iosuite_shared.config.standard): the account `python -m iodocs.mcp` (stdio) acts as

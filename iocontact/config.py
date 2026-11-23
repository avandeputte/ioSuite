"""Settings: kept in the Shared ioSuite database and read once, as the app starts (Settings › Suite › Apps
changes them; app.json lists the app's own). Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared, serve

APP = "iocontact"
APP_DIR = Path(__file__).resolve().parent
_s = shared.settings(APP)  # what is stored for this app in the Shared ioSuite database, read once, now
env, env_flag, env_int = _s.get, _s.flag, _s.int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR, _s))

# the app's own database: beside the Shared ioSuite database, under the same login (DB_NAME names another than iocontact). The Shared ioSuite database
# (IOSUITE_DB_*: accounts, sessions, app passwords, roles, suite-wide settings) is read by iosuite_shared itself, on the
# contacts' server unless told otherwise.
_db = shared.own_db(APP, _s)
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

# LDAP directory (read-only): port 0 turns it off; it listens where the web app does unless told otherwise
LDAP_PORT = env_int("LDAP_PORT", 3890)
LDAP_HOST = [h.strip("[]") for h in serve.hosts(env("LDAP_HOST", HOST))]  # noqa: F821 - HOST: the machine's, from standard()
LDAP_BASE = env("LDAP_BASE", "dc=iocontact")

# ioPix is found in the suite's list of apps and signed in to by itself (app/iopix.py): nothing to set

MAX_IMPORT_BYTES = 64 * 1024 * 1024   # a vCard, CSV or JSON file to import
MAX_JSON_BYTES = 16 * 1024 * 1024     # any other request body: a contact (JSON or vCard, a photo inline) or a CardDAV request

# MCP_USER (iosuite_shared.config.standard): the account `python -m iocontact.mcp` (stdio) acts as

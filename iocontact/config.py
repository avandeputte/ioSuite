"""Settings: kept in the Shared ioSuite database, the suite's one home for them (Settings › Apps › All settings and
the app's own Settings page change them; app.json lists the app's own). The ones that say where the app answers and
where it keeps what it keeps are read once, as it starts (`env`); every other is read as it is now (`live`), so a
change takes hold without a restart. Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from iosuite_shared import config as shared, serve

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
live, live_flag, live_int = _own["live"], _own["live_flag"], _own["live_int"]
env, env_int, HOST = _own["env"], _own["env_int"], _own["HOST"]

# LDAP directory (read-only): port 0 turns it off; it listens where the web app does unless told otherwise
LDAP_PORT = env_int("LDAP_PORT", 3890)
LDAP_HOST = [h.strip("[]") for h in serve.hosts(env("LDAP_HOST", HOST))]  # HOST: the machine's, from standard()
LDAP_BASE = env("LDAP_BASE", "dc=iocontact")

# ioPix is found in the suite's list of apps and signed in to by itself (iocontact/iopix.py): nothing to set

# MCP_USER (iosuite_shared.config.standard): the account `iosuite mcp iocontact` (stdio) acts as

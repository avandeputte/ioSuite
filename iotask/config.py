"""Settings: kept in the Shared ioSuite database, the suite's one home for them (Settings › Apps › All settings and
the app's own Settings page change them; app.json lists the app's own). The ones that say where the app answers and
where it keeps what it keeps are read once, as it starts (`env`); every other is read as it is now (`live`), so a
change takes hold without a restart. Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
live, live_flag, live_int = _own["live"], _own["live_flag"], _own["live_int"]


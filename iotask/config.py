"""Settings: kept in the Shared ioSuite database and read once, as the app starts (Settings › Apps › All settings
changes them; app.json lists the app's own). Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)


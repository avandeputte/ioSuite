"""Settings: kept in the Shared ioSuite database and read once, as the app starts (Settings › Apps › All settings
changes them; app.json lists the app's own). What ioBackup keeps
(servers, destinations, jobs, the history of runs) lives in MariaDB; the passwords and Google keys with the suite's
keys and tokens. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
env, DATA_DIR = _own["env"], _own["DATA_DIR"]

TZ = env("TZ")

# the folder a new local destination suggests (the Docker image mounts a volume there)
BACKUP_DIR = env("BACKUP_DIR", "/var/backups/iobackup")
# where a backup is put together before it is stored (room for two compressed backups), and where a backup read from
# Google Drive is kept while it is restored
WORK_DIR = Path(env("WORK_DIR", str(DATA_DIR / "work"))).expanduser()
CACHE_DIR = Path(env("CACHE_DIR", str(DATA_DIR / "cache"))).expanduser()

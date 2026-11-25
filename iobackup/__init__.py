"""ioBackup: backups of the suite's MariaDB servers (and any other MariaDB or Galera server), on demand or on a
schedule, to a local folder or Google Drive, with retention and a restore of exactly what you pick."""
from iosuite_shared import __version__, app as _app

__all__ = ["__version__"]
__getattr__ = _app.declare(__name__)  # auth, access, users, updater...: made from app.json when first asked for (iosuite_shared.app)

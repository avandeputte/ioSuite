"""ioContact: self-hosted contacts for ioSuite."""
from iosuite_shared import __version__, app as _app

__all__ = ["__version__"]
__getattr__ = _app.declare(__name__)  # auth, access, users, updater...: made from app.json when first asked for (iosuite_shared.app)

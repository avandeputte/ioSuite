"""ioPix: a web front end for a digiKam photo library, one of the apps `iosuite serve` runs."""
from iosuite_shared import __version__, app as _app

__all__ = ["__version__"]
__getattr__ = _app.declare(__name__)  # auth, users, updater...: made from app.json when first asked for (iosuite_shared.app)

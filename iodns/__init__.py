"""ioDNS: one master list of local DNS records for ioSuite, pushed to every DNS server of the house."""
from iosuite_shared import __version__, app as _app

__all__ = ["__version__"]
__getattr__ = _app.declare(__name__)  # auth, access, users, updater...: made from app.json when first asked for (iosuite_shared.app)

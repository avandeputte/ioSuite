"""ioMoney: the household's finances for ioSuite: accounts and transactions from Monarch Money, a portfolio
with its quotes, and what the house and the cars are worth."""
from iosuite_shared import __version__, app as _app

__all__ = ["__version__"]
__getattr__ = _app.declare(__name__)  # auth, access, users, updater...: made from app.json when first asked for (iosuite_shared.app)

"""The conventions every app of the suite follows, checked over every app at once (iosuite_shared.testing:
check_conventions) rather than by thirteen copies of the same test, one per app."""
import pytest

import iosuite_shared
from iosuite_shared import catalog, testing


@pytest.fixture
def fresh_db():
    """Overrides conftest's autouse database fixture: these are file checks, not a database."""
    yield


@pytest.mark.parametrize("key", sorted(catalog.APPS))
def test_every_app_follows_the_conventions(key):
    """The suite's version as the app's, a manifest that names it, no settings file of its own, and a page that asks
    for everything with relative addresses (the app is served in a folder of one address as well as at its own)."""
    testing.check_conventions(catalog.ROOT / key, key, iosuite_shared.__version__)


def test_the_apps_are_the_folders_beside_the_shared_library():
    assert len(catalog.APPS) >= 13 and "iocalendar" in catalog.APPS and "iosuite_shared" not in catalog.APPS

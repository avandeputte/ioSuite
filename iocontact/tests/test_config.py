"""What this app's own settings and routes must look like: an access marker on every API route, and the paths it
keeps things in. The conventions every app shares are checked over all of them at once
(iosuite_shared/tests/test_conventions.py)."""
import os

from iosuite_shared import testing

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_api_route_declares_who_may_call_it(app):
    from iocontact import access
    testing.check_access_declared(app, access.declared)


def test_standard_paths():
    from pathlib import Path
    from iocontact import config
    root = Path(ROOT)
    assert config.APP_DIR == root and config.STATIC_DIR == root / "static" and config.DATA_DIR.name == "iocontact"
    assert config.LOG_FILE is None  # LOG_FILE=off in the tests' stored settings


def test_served_in_a_folder_of_an_address(client):
    testing.check_folder(client)  # https://home.example.com/suite-app/, the whole suite on one address

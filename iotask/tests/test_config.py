"""What this app's own settings and routes must look like: an access marker on every API route, and the paths it
keeps things in. The conventions every app shares are checked over all of them at once
(iosuite_shared/tests/test_conventions.py)."""
from pathlib import Path

from iosuite_shared import testing

from iotask import access, config

ROOT = Path(__file__).resolve().parent.parent



def test_every_api_route_declares_who_may_call_it(app):
    testing.check_access_declared(app, access.declared)


def test_standard_paths():
    assert config.APP_DIR == ROOT and config.STATIC_DIR == ROOT / "static" and config.DATA_DIR.name == "iotask"
    assert config.LOG_FILE is None  # LOG_FILE=off in the tests' stored settings


def test_served_in_a_folder_of_an_address(client):
    testing.check_folder(client)  # https://home.example.com/suite-app/, the whole suite on one address

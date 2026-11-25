"""What ioPix's own settings and routes must look like: an access marker on every API route (test_access.py also
checks each route's level against access_table.json) and the paths it keeps things in. The conventions every app
shares are checked over all of them at once (iosuite_shared/tests/test_conventions.py)."""
from pathlib import Path

from iosuite_shared import testing

from iopix import access, config

ROOT = Path(__file__).resolve().parent.parent



def test_every_api_route_declares_who_may_call_it():
    from iopix.main import app
    testing.check_access_declared(app, access.declared)


def test_the_port_for_devices_serves_calls_the_app_has_and_no_admin_s():
    from iopix.main import app
    testing.check_device_calls(app, "iopix", access.declared)


def test_standard_paths():
    assert config.APP_DIR == ROOT and config.STATIC_DIR == ROOT / "static"
    assert config.INDEX_DB == config.DATA_DIR / "index.db"
    assert config.LOG_FILE == (config.DATA_DIR / "iosuite.log").resolve()  # the tests keep the copy's log in their scratch data folder


def test_served_in_a_folder_of_an_address(client):
    testing.check_folder(client)  # https://home.example.com/suite-app/, the whole suite on one address

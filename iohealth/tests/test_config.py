"""The conventions every app of the suite follows (iosuite_shared.testing): the port, one version, config.env, and an
access marker on every API route (and on the phone's /v1/ routes)."""
from pathlib import Path

from iosuite_shared import testing

from iohealth import access, config

ROOT = Path(__file__).resolve().parent.parent



def test_every_api_route_declares_who_may_call_it(app):
    testing.check_access_declared(app, access.declared)
    testing.check_access_declared(app, access.declared, prefix="/v1/")


def test_the_port_for_devices_serves_calls_the_app_has_and_no_admin_s(app):
    testing.check_device_calls(app, "iohealth", access.declared)


def test_standard_paths():
    assert config.APP_DIR == ROOT and config.STATIC_DIR == ROOT / "static" and config.DATA_DIR.name == "iohealth"
    assert config.LOG_FILE is None  # LOG_FILE=off in the tests' stored settings


def test_served_in_a_folder_of_an_address(client):
    testing.check_folder(client)  # https://home.example.com/suite-app/, the whole suite on one address

"""The conventions every app of the suite follows (iosuite_shared.testing): the port, one version, config.env, and an
access marker on every API route."""
import os

from iosuite_shared import testing

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_suite_conventions():
    from iocontact import __version__, config
    testing.check_conventions(ROOT, "iocontact", __version__, config)


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

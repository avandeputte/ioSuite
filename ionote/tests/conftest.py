"""Test set-up: a scratch DATA_DIR, and a test MariaDB of their own (iosuite_shared.testing: a Docker container, or
the server named by IOSUITE_TEST_DB=host:port:user:password) with two scratch databases, ionote_test for the notes and
ionote_test_auth for the shared accounts, never a live one. Every test begins with empty tables. Without a test server
the suite is skipped."""
import os

import pytest

# the shared accounts (iosuite-shared): a fresh database on the test MariaDB (a Docker container, or
# IOSUITE_TEST_DB=host:port:user:password), never the suite's live `iosuite`
from iosuite_shared import testing as _authtest  # noqa: E402

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOSUITE_TEST_DB=host:port:user:password)", allow_module_level=True)
_authtest.app_env("ionote", "ionote_test")
_tmp = os.environ["DATA_DIR"]


from ionote import db, notes  # noqa: E402
from iosuite_shared import proxyauth  # noqa: E402

TABLES = ["nts_notes", "nts_note_images", "nts_attachments", "nts_templates", "nts_folders", "nts_tag_colors", "nts_change_log", "nts_change_counter", "nts_settings"]


@pytest.fixture(scope="session")
def app():
    from ionote.main import app as a
    return a


@pytest.fixture(autouse=True)
def clean():
    db.init()
    with db.connect() as con:
        for t in TABLES:
            con.execute(f"DELETE FROM {t}")
        con.commit()
    from ionote.auth import auth
    _authtest.clean_shared_tables(auth)  # accounts, sessions, app passwords, settings, the list of apps; the first account is #1 again
    proxyauth.forget_identities()
    notes._tags_seen.clear()
    notes._seeded.clear()
    yield


@pytest.fixture(scope="session")
def _client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:  # once: the MCP session manager starts only once per process
        yield c


@pytest.fixture
def client(_client):
    _client.cookies.clear()
    return _client


@pytest.fixture
def admin(client):
    """A signed-in admin (the client carries the session cookie)."""
    r = client.post("/api/auth/setup", json={"name": "alex", "password": "secretpw1"})
    assert r.status_code == 200, r.text
    return r.json()["user"]

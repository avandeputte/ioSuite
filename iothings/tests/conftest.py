"""Tests run against a test MariaDB of their own (iosuite_shared.testing: a Docker container, or the server named by
IOSUITE_TEST_DB=host:port:user:password): two scratch databases, home_test and home_test_auth, dropped and
recreated per session, never a live one. Without a test server the suite is skipped. The app starts once per session;
every test begins with empty tables and a fresh admin, alex."""
import pytest

from iosuite_shared import testing as _authtest, users as shared_users

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOSUITE_TEST_DB=host:port:user:password)", allow_module_level=True)
_authtest.app_env("iothings", "home_test")

from fastapi.testclient import TestClient  # noqa: E402

from iothings import db  # noqa: E402


@pytest.fixture(scope="session")
def app():
    from iothings.main import app as a
    return a


@pytest.fixture(scope="session")
def _client(app):
    with TestClient(app) as c:  # once: the MCP session manager starts once per process
        yield c


@pytest.fixture()
def client(_client):
    db.reset_all()
    db.migrate()
    from iothings import auth
    _authtest.clean_shared_tables(auth)
    from iosuite_shared import apppasswords
    apppasswords.forget()
    shared_users.invalidate()
    _client.cookies.clear()
    r = _client.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
    assert r.status_code == 200, r.text
    return _client


@pytest.fixture()
def as_user(client):
    """as_user(name, role): an account with that role here, signed in on the shared client (alex is signed out)."""
    def go(name, role):
        r = _authtest.add_account(client, {"name": name, "password": "secret123", "role": role})
        assert r.status_code in (200, 201), r.text
        client.cookies.clear()
        assert client.post("/api/auth/login", json={"name": name, "password": "secret123"}).status_code == 200
        return client
    return go


def sign_in(client, name):
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": name, "password": "secret123"}).status_code == 200

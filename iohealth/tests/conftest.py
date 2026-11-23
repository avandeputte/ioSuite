"""Tests run against a test MariaDB of their own (iosuite_shared.testing: a Docker container, or the server named by
IOSUITE_TEST_DB=host:port:user:password): two scratch databases, health_test and health_test_auth, dropped and
recreated per session, never a live one. Without a test server the suite is skipped. The app starts once per session;
every test begins with empty tables."""
import re
import threading

import pytest

from iosuite_shared import testing as _authtest

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOSUITE_TEST_DB=host:port:user:password)", allow_module_level=True)
_srv = _authtest.app_env("iohealth", "health_test", TZ="Europe/Brussels")


from iohealth import db  # noqa: E402

HEALTH_TABLES = tuple(re.search(r"hlt_\w+", s).group(0) for s in db.SCHEMA)


@pytest.fixture(scope="session")
def app():
    from iohealth.main import app as a
    return a


@pytest.fixture(scope="session")
def _client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(_client):
    from iohealth import webapi
    from iohealth.auth import auth
    # what the last test's finished sync started may still be at work (the hourly rollup of a type seen for the first
    # time, its notifications): their writes would deadlock with the deletes below
    for t in threading.enumerate():
        if t.name in ("after-sync", "hourly-rollup"):
            t.join(10)
    with db.pool.auto() as con, con.cursor() as cur:
        for t in HEALTH_TABLES:
            cur.execute(f"DELETE FROM {t}")
    _authtest.clean_shared_tables(auth)
    webapi.cache.clear()
    webapi.effort_cache.clear()
    webapi._all_types["at"] = 0.0
    webapi._kinds.clear()
    webapi._zones.clear()
    webapi.ready.types = set()
    yield


@pytest.fixture(autouse=True)
def started_by_a_sync(app, monkeypatch):
    """A finished sync starts the notifications ("goal reached", "outside your usual") in a thread of its own, at the
    time it then is. A test that uploads and next asks for a notification itself, at a time it chose, raced that thread
    for the one notification of the day, and lost now and then once the server's clock was past the morning time. So
    no test has that thread: each asks itself. What a sync would have started is handed to the test that checks it."""
    from iohealth import upload
    wired = list(upload.on_user_sync)
    monkeypatch.setattr(upload, "on_user_sync", [])
    return wired


@pytest.fixture
def client(_client):
    _client.cookies.clear()
    return _client


@pytest.fixture
def admin(client):
    """A signed-in suite admin, alex (the client carries the session cookie)."""
    r = client.post("/api/auth/setup", json={"name": "alex", "password": "secretpw1"})
    assert r.status_code == 200, r.text
    return r.json()["user"]

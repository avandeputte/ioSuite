"""The app has no Settings › Server of its own any more: the version, the log, updating and the MCP switch are the
suite's (Settings › Apps and Settings › Servers), so the app's status carries no update of its own and /api/server is
gone with that panel."""
from iohealth import __version__
from iosuite_shared import testing


def test_status_has_the_version_and_no_update_of_its_own(client, admin):
    s = client.get("/api/status").json()
    assert s["version"] == __version__ and s["commit"] and "update" not in s


def test_the_server_page_is_gone(client, admin):
    assert client.get("/api/server").status_code == 404
    assert client.get("/api/server/ui.js").status_code == 404
    assert client.post("/api/server", json={"action": "restart"}).status_code in (404, 405)
    assert client.get("/api/log").status_code in (200, 404)  # the server log, when the test writes one
    assert client.post("/api/auth/logout_all").status_code in (404, 405)  # Sign out is the only sign out


def test_the_server_log_is_for_admins_only(client, admin):
    testing.add_account(client, {"name": "bo", "password": "secretpw2", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "bo", "password": "secretpw2"})
    assert client.get("/api/log").status_code in (403, 404)  # 404: the route is not registered without a log file (LOG_FILE= in the tests)

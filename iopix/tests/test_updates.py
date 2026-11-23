"""Settings › Server through iosuite_shared's server_router (/api/server): the installed commit is known and the server
log answers. Updating is the suite's (Settings › Global settings › Updates): the app has no update action of its own.
The updater itself is tested in iosuite-shared."""
from iopix.auth import updater


def test_status_and_no_update_of_its_own(client, monkeypatch):
    monkeypatch.setattr(updater, "local_commit", lambda: "abcdef1234567890")
    s = client.get("/api/server").json()
    assert s["installed"] == "abcdef1" and "canRun" in s and "docker" in s and "mcpEnabled" in s
    assert "check" not in s and "autoCheck" not in s
    assert "update" not in client.get("/api/status").json()
    for action in ("check", "update"):
        assert client.post("/api/server", json={"action": action}).status_code == 400


def test_the_log_is_the_copy_s_read_by_suite_admins(client):
    """The server log is the copy's one log (Settings › Global settings › Logs), every line marked with its app."""
    import logging
    logging.getLogger("iopix.sync").warning("probe-warning for the log test")
    assert client.get("/api/log").status_code == 404  # no log of the app's own any more
    r = client.get("/api/suite-admin/logs", params={"app": "iopix", "level": "warning", "contains": "probe-warning"})
    assert r.status_code == 200
    j = r.json()
    assert j["app"] == "iopix" and j["copies"][0]["reachable"]
    assert j["lines"] and all("probe-warning" in x["text"] and x["app"] == "iopix" and x["level"] == "WARNING" for x in j["lines"])
    assert client.get("/api/suite-admin/logs", params={"app": "iocalendar", "contains": "probe-warning"}).json()["lines"] == []

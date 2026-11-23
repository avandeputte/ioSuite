"""The app has no Settings › Server of its own: the version, the log and updating are the suite's (Settings › Servers).
/api/server is gone with that panel, and the app's status carries no update action. The updater itself is tested in
iosuite_shared."""


def test_no_server_page_and_no_update_of_its_own(client):
    assert client.get("/api/server").status_code == 404
    assert client.get("/api/server/ui.js").status_code == 404
    assert "update" not in client.get("/api/status").json()


def test_the_log_is_the_copy_s_read_by_suite_admins(client):
    """The server log is the copy's one log (Settings › Servers › Logs), every line marked with its app."""
    import logging
    logging.getLogger("iopix.sync").warning("probe-warning for the log test")
    assert client.get("/api/log").status_code == 404  # no log of the app's own any more
    r = client.get("/api/suite-admin/logs", params={"app": "iopix", "level": "warning", "contains": "probe-warning"})
    assert r.status_code == 200
    j = r.json()
    assert j["app"] == "iopix" and j["copies"][0]["reachable"]
    assert j["lines"] and all("probe-warning" in x["text"] and x["app"] == "iopix" and x["level"] == "WARNING" for x in j["lines"])
    assert client.get("/api/suite-admin/logs", params={"app": "iocalendar", "contains": "probe-warning"}).json()["lines"] == []

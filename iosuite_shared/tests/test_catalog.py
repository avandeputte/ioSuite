"""The apps' manifests (<app>/app.json) and what is made from them, without a database."""
import json
from pathlib import Path

import pytest

from iosuite_shared import catalog, doors, push, related, suite

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fresh_db():
    """Overrides conftest's autouse database fixture: nothing here needs MariaDB."""
    yield


def test_every_app_folder_has_a_manifest():
    folders = sorted(p.parent.name for p in ROOT.glob("io*/app.json"))
    assert sorted(catalog.APPS) == folders and len(folders) == 13
    for k in catalog.APPS:
        assert (ROOT / k / "__init__.py").is_file() and (ROOT / k / "main.py").is_file(), f"{k} is not a package beside the library"
        assert json.loads((ROOT / k / "app.json").read_text())["key"] == k
        assert not (ROOT / k / "config.env.example").exists() and not (ROOT / k / "setup.sh").exists(), f"{k} has no set-up of its own"


def test_the_lists_read_the_manifests():
    assert suite.FOLDERS["iocalendar"] == "calendar" and "iostart" not in suite.FOLDERS
    assert catalog.install_order()[-1] == "iopix" and set(catalog.install_order()) == set(catalog.APPS)
    assert related.KINDS["note"] == {"app": "ionote", "label": "Note", "plural": "Notes", "href": "#/note/{id}", "id": "uuid"}
    assert {k["kind"] for k in push.KINDS} >= {"events", "tasks", "birthdays", "backups", "updates"}
    assert push.KIND["backups"]["admin"] and push.KIND["backups"]["app"] == "iobackup"
    assert all("port" not in m for m in catalog.APPS.values()), "an app has no port of its own: the copy's three doors"


def test_what_each_app_serves_to_devices():
    assert doors.sync_paths("iocalendar") == ("/dav", "/.well-known/", "/ics/")
    assert doors.sync_paths("iocontact") == ("/dav", "/.well-known/", "/cal/") and doors.sync_paths("iotask") == ("/dav", "/.well-known/")
    assert doors.sync_paths("iohealth") == ("/v1/",) and doors.sync_paths("iostart") == ("/dav/ext",) and doors.sync_paths("iomoney") == ()
    assert not any(doors.page_paths(k) for k in catalog.APPS)  # no page below a sync path: nothing is sent on to the pages
    assert doors.home_only_paths("iocalendar") == ("/.well-known/", "/ics/") and doors.home_only_paths("iocontact") == ("/.well-known/",)
    # of /api/, the calls the native apps make: the apps that have one, and no other
    assert {k for k, m in catalog.APPS.items() if m.get("devices")} == {"iopix", "ionote", "iohealth", "iostart"}
    assert catalog.APPS["iohealth"]["devices"] == ["POST,DELETE /api/auth/device"]
    # the start page: its sign-in, and the feed reader of its iPhone app (with the feeds' site icons)
    assert all(c in ("POST,DELETE /api/auth/device", "GET /api/bookmarks/site-icon") or c.split(" ")[1].startswith("/api/news") for c in catalog.APPS["iostart"]["devices"])
    assert doors.device_call("iostart", "/api/news/items/7") and doors.device_call("iostart", "/api/news/read", "POST")
    assert not doors.device_call("iostart", "/api/news/opml") and not doors.device_call("iostart", "/api/me/layout")


def test_validate_refuses_a_home_only_path_outside_the_sync_paths():
    a = {"key": "ioone", "name": "ioOne", "description": "One", "color": "#123456", "order": 1, "folder": "one", "sync": ["/dav"], "homeOnly": ["/ics/"]}
    with pytest.raises(ValueError, match="homeOnly"):
        catalog.validate([a])


def test_validate_refuses_clashes():
    a = {"key": "ioone", "name": "ioOne", "description": "One", "color": "#123456", "order": 1, "folder": "one"}
    b = dict(a, key="iotwo", name="ioTwo", folder="two")
    with pytest.raises(ValueError, match="folder one"):
        catalog.validate([a, dict(b, folder="one")])
    with pytest.raises(ValueError, match="folder 'x'"):
        catalog.validate([dict(a, folder="x")])
    with pytest.raises(ValueError, match="kind event"):
        catalog.validate([dict(a, items=[{"kind": "event", "label": "E", "plural": "Es", "href": "#/e/{id}"}]),
                          dict(b, items=[{"kind": "event", "label": "E", "plural": "Es", "href": "#/e/{id}"}])])
    with pytest.raises(ValueError, match="color"):
        catalog.validate([dict(a, color="red")])
    with pytest.raises(ValueError, match="sync"):
        catalog.validate([dict(a, sync=["/api/x"])])
    with pytest.raises(ValueError, match="sync"):
        catalog.validate([dict(a, sync=["dav"])])
    with pytest.raises(ValueError, match="pages"):
        catalog.validate([dict(a, sync=["/dav"], pages=["/elsewhere/"])])
    for bad in (["/api/thumb/"], ["thumb"], ["/dav/files/"], ["/static/x/"]):
        with pytest.raises(ValueError, match="media"):
            catalog.validate([dict(a, sync=["/dav"], media=bad)])
    assert catalog.validate([dict(a, sync=["/dav"], media=["/thumb/"])])
    # the calls of its API the port for devices serves: methods and a path under /api/, * for one part of it
    for bad in (["/api/sync"], ["GET api/sync"], ["GET /sync"], ["FETCH /api/sync"], ["GET /api/"], ["GET /api/notes/**"], ["GET  /api/sync"],
                ["GET /api/notes/{id}"], ["get /api/sync"], [{"GET": "/api/sync"}], ["GET /api/sync?x=1"], ["GET,/api/sync"]):
        with pytest.raises(ValueError, match="devices"):
            catalog.validate([dict(a, devices=bad)])
    # of an account, a native app's own sign-in and its person's settings: nothing that changes an account
    for bad in (["POST /api/auth/login"], ["POST /api/auth/password"], ["GET,POST /api/auth/app-passwords"], ["DELETE /api/auth/me"],
                ["GET /api/auth/device"], ["POST /api/auth/*"], ["GET /api/auth/accounts"]):
        with pytest.raises(ValueError, match="nothing that changes an account"):
            catalog.validate([dict(a, devices=bad)])
    assert catalog.validate([dict(a, devices=["GET /api/sync", "GET,PUT,DELETE /api/notes/*/attachments/*", "POST,DELETE /api/auth/device",
                                              "GET /api/auth/me", "POST /api/auth/settings"])])
    assert [m["key"] for m in catalog.validate([dict(b, order=0), a])] == ["iotwo", "ioone"]

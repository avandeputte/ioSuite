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
    assert doors.sync_paths("iohealth") == ("/v1/",) and doors.sync_paths("iostart") == ("/dav/",) and doors.sync_paths("iomoney") == ()
    assert doors.page_paths("iostart") and all(p.startswith("/dav/") for p in doors.page_paths("iostart"))


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
    assert [m["key"] for m in catalog.validate([dict(b, order=0), a])] == ["iotwo", "ioone"]

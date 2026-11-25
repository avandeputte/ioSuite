"""Every route declares who may call it (iopix/access.py): the API, the image and video routes, the share target and the
page itself. The declared levels match the table in access_table.json: a new route without a marker, or a route whose
level changed by accident, fails here. Change the table on purpose when a route's audience changes."""
import json

import pytest
from pathlib import Path

from iosuite_shared import testing

from iopix import access

TABLE = json.loads((Path(__file__).parent / "access_table.json").read_text())


def _api_routes():
    """Every route of the app, whatever its address: its own, the ones every app of the suite answers, and the page."""
    from iopix.main import app
    seen = set()
    for methods, path, r in testing.api_routes(app):
        key = (path, tuple(sorted(methods)))
        if key not in seen:
            seen.add(key)
            yield r


def test_every_api_route_declares_its_access():
    missing = [f"{sorted(r.methods)} {r.path}" for r in _api_routes() if access.declared(r) is None]
    assert not missing, "routes without exactly one access marker (dependencies=[access.<level>]):\n" + "\n".join(missing)


# the panel every app of the suite serves (Settings › People, Apps, Servers and Keys, the Linked panel, the live
# stream, /api/suite): the shared tests check those, and the table below is ioPix's own routes
SUITE = ("/api/suite-admin", "/api/live", "/api/related", "/api/suite")


def test_declared_access_matches_the_table():
    seen = {}
    for r in _api_routes():
        if r.path.startswith(SUITE):
            continue
        role, write = access.declared(r)
        for m in r.methods - {"HEAD", "OPTIONS"}:
            seen[f"{m} {r.path}"] = role + ("+write" if write else "")
    assert seen == TABLE, {k: (seen.get(k), TABLE.get(k)) for k in set(seen) | set(TABLE) if seen.get(k) != TABLE.get(k)}


def test_markers_refuse_the_right_people(client):
    """A visitor is refused on an editor route and an admin route once accounts exist (before that, the library is
    open to whoever reaches it, as before)."""
    from iopix import users
    if not users.any_users():
        pytest.skip("no accounts in this library: everyone may edit")
    r = client.post("/api/photos/trash", json={"ids": []})
    assert r.status_code in (401, 403) and "editor" in r.json()["detail"].lower()
    r = client.get("/api/suite-admin/overview")
    assert r.status_code in (401, 403)

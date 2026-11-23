"""The fixes from the November 2026 external code review: the set-up endpoints are locked while a configured
database does not answer, a stored password goes to the stored server only, a nested reader never rolls back
the writer above it, the merge keeps folder paths and inserts new tags parents first, GPX checks are
case-insensitive, and a batch delete refuses two roots' files that would land on the same backup path."""
import asyncio
import json

import pytest
from starlette.requests import Request

from iopix.data import appdb
from iopix.digikam import dkdb, merge
from iopix.geo import gpx


def _request(path: str, method: str = "GET", body: dict = None, peer: str = "127.0.0.1", headers: dict = None):
    raw = json.dumps(body or {}).encode()
    extra = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": method, "path": path, "query_string": b"", "headers": [(b"host", b"viewer.local"), (b"content-type", b"application/json")] + extra,
             "scheme": "http", "server": ("viewer.local", 80), "client": (peer, 1234)}

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}
    return Request(scope, receive)


def _call(path, method="GET", body=None, **who):
    from iopix import main

    async def nxt(_r):
        raise AssertionError("the request must not reach the app")
    resp = asyncio.run(main._without_database(_request(path, method, body, **who), nxt))
    return resp.status_code, json.loads(resp.body)


def test_only_retry_is_served_while_the_database_is_down(monkeypatch):
    """The viewer's database is the suite's login on the suite's server (the machine's file), and it did not answer at
    start: nobody can sign in, so only the error and Retry are served. Nothing here names a server or takes one: the
    endpoints that tested and switched databases are gone."""
    monkeypatch.setattr(appdb, "configured", lambda: True)
    monkeypatch.setattr(appdb, "ready", lambda: False)
    monkeypatch.setattr(appdb, "error", "connection refused")
    for who in ({}, {"peer": "8.8.8.8"}, {"peer": "192.168.1.20"}):
        code, d = _call("/api/database", **who)
        assert code == 200 and d == {"configured": True, "locked": True, "error": "connection refused", "type": "mysql"}
        for p in ("/api/database/test", "/api/database/switch"):
            assert _call(p, "POST", {"host": "evil.example", "password": ""}, **who)[0] == 404, p
    monkeypatch.setattr(appdb, "retry", lambda: False)
    code, d = _call("/api/database/retry", "POST")
    assert code == 400 and "Still unavailable" in d["detail"]
    code, d = _call("/api/database/retry", "POST", headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert code == 403
    code, d = _call("/api/status")
    assert code == 200 and d["needsDatabase"] and d["databaseConfigured"]
    code, d = _call("/api/photos")
    assert code == 503 and d["needsDatabase"]


def test_the_stored_password_goes_to_the_stored_server_only(monkeypatch):
    """digiKam's connection test: an empty password field means the stored one only for the stored server."""
    seen = {}

    def fake_connect(**kw):
        seen.update(kw)
        raise OSError("not today")
    import pymysql
    monkeypatch.setattr(pymysql, "connect", fake_connect)
    monkeypatch.setattr(dkdb, "settings", lambda: {"type": "mysql", "sqlite_dir": "", "host": "dk.local", "port": 3306, "database": "digikam", "user": "digikam", "password": "dk-secret"})
    with pytest.raises(OSError):
        dkdb.test_connection({"host": "other.example", "password": ""})
    assert seen["host"] == "other.example" and seen["password"] == ""
    with pytest.raises(OSError):
        dkdb.test_connection({"password": ""})
    assert seen["host"] == "dk.local" and seen["password"] == "dk-secret"


def test_a_nested_reader_does_not_roll_back_the_writer_above_it():
    """Each block is lent a connection of its own out of the pool: a reader opened inside a writer's block (a setting
    looked up, a row read) never shares the writer's, so its close() ends nothing of the writer's."""
    from iopix.data import state
    state.init()
    with appdb.writer() as con:
        con.execute("INSERT OR REPLACE INTO pix_settings (name, value) VALUES (?, ?)", ("zz_nested_probe", "kept"))
        with appdb.reader() as inner:
            assert inner.raw.raw is not con.raw.raw, "the nested reader has its own connection"
            inner.execute("SELECT 1").fetchone()
        own = appdb.connect()  # what a writer opened inside a library transaction (Sync off) gets: a connection of its own
        try:
            assert own.raw.raw is not con.raw.raw
            own.execute("INSERT OR REPLACE INTO pix_settings (name, value) VALUES (?, ?)", ("zz_nested_probe2", "own"))
            own.commit()
        finally:
            own.close()
        assert con.execute("SELECT value FROM pix_settings WHERE name = ?", ("zz_nested_probe",)).fetchone()[0] == "kept", "the outer write survived the nested blocks"
    with appdb.reader() as con:
        assert isinstance(con.raw, appdb._Lent), "after the blocks, a connection out of the pool again"
        assert con.execute("SELECT value FROM pix_settings WHERE name = ?", ("zz_nested_probe",)).fetchone()[0] == "kept"
    with appdb.writer() as con:
        con.execute("DELETE FROM pix_settings WHERE name LIKE 'zz_nested_probe%'")


def test_new_tags_merge_parents_first_whatever_their_ids():
    cols = ["id", "pid", "name", "icon", "iconkde"]
    rows = [(100, 101, "A", None, None), (101, 0, "B", None, None), (102, 100, "C", None, None), (99, 7, "old parent", None, None)]
    order = [r[0] for r in merge._parents_first(rows, cols)]
    assert order.index(101) < order.index(100) < order.index(102) and order[0] == 99
    loop = [(1, 2, "x", None, None), (2, 1, "y", None, None)]  # never hangs on a cycle
    assert len(merge._parents_first(loop, cols)) == 2


def test_merge_writes_the_folder_path_back_to_digikam():
    """A folder renamed or moved with sync off: digiKam's Albums row gets the new relativePath, not only the caption."""
    import inspect
    src = inspect.getsource(merge._Merge.folders)
    assert "UPDATE Albums SET relativePath = ?, date = ?, caption = ?, collection = ?" in src


def test_gpx_doctype_check_is_case_insensitive_and_waypoints_need_no_namespace():
    with pytest.raises(ValueError):
        gpx.parse(b'<?xml version="1.0"?><!doctype gpx [<!entity x "y">]><gpx></gpx>')
    with pytest.raises(ValueError):
        gpx.parse('<?xml version="1.0" encoding="utf-16"?><gpx/>'.encode("utf-16"))
    pts = gpx.parse(b'<gpx version="1.0"><wpt lat="51.5" lon="-0.1"><time>2024-07-14T10:30:00Z</time></wpt>'
                    b'<trk><trkseg><trkpt lat="51.6" lon="-0.2"><time>2024-07-14T10:31:00Z</time></trkpt></trkseg></trk></gpx>')
    assert [p[1] for p in pts] == [51.5, 51.6], "the waypoint without a namespace counts too"


def test_two_roots_can_hold_the_same_relative_path(tmp_path, monkeypatch):
    """Why deletion.delete checks the backup path before copying: two album roots can hold the same relative path, and
    one deleted-photos folder would hold one copy for both."""
    from iopix.photos import deletion
    monkeypatch.setattr(deletion, "_roots", lambda: [tmp_path / "root1", tmp_path / "root2"])
    a, b = str(tmp_path / "root1" / "2024" / "IMG_0001.JPG"), str(tmp_path / "root2" / "2024" / "IMG_0001.JPG")
    assert deletion._rel(a) == deletion._rel(b) and deletion._root_of(a) != deletion._root_of(b)

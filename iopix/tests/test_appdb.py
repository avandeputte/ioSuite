"""The viewer database (MariaDB-only since v1.113): the schema lands in an empty database, the dump is the backup
form, and the viewer waits for a database that does not answer."""

from iosuite_shared import users as shared_users
import pytest

import mariadb
from iopix.data import state, appdb
from iopix import users


@pytest.fixture
def other_db():
    """A second, empty database on the test server, dropped afterwards."""
    cfg = mariadb.fresh_database("iopix_test_other")
    yield cfg
    import pymysql
    c = mariadb.server()
    con = pymysql.connect(host=c["host"], port=c["port"], user=c["user"], password=c["password"], autocommit=True)
    con.cursor().execute("DROP DATABASE IF EXISTS `iopix_test_other`")
    con.close()


def _seed():
    alex = users.create("alex", "correct horse", "admin")
    state.set_setting("zz_probe", "value with ? and %s and `key`")
    assert state.set_favorites([(1, "h1"), (2, "h2")], True, user=alex), "favorites are an account's own"
    aid = state.create_album("Trip"); state.set_album_items(aid, [(1, "h1")], True)
    with appdb.writer() as con:
        con.execute("INSERT OR REPLACE INTO pix_ai_quality VALUES (?,?,?,?,?)", (1, 0.5, 0.4, 0, 0))
        con.execute("INSERT OR REPLACE INTO pix_ai_scans VALUES (?,?,?,?)", (1, "quality", "2026-10-15T00:00:00.000", None))
        con.execute("INSERT OR REPLACE INTO pix_ai_descriptions VALUES (?,?)", (1, "a dog on a beach"))
    return aid


def test_a_fresh_empty_database_gets_every_table(other_db):
    """A new install starts on an empty database: the first start creates the tables."""
    con = appdb.connect(cfg=other_db)
    try:
        assert appdb.columns(con, "pix_ai_quality") == []
        appdb.ensure_schema(con)
        assert set(appdb.TABLES) <= appdb.table_names(con)
        assert appdb.add_missing_columns(con) == [], "a second open adds nothing"
    finally:
        con.close()


def test_private_albums_and_accounts_on_the_server(client, fresh):
    """The modules' queries on MariaDB (GROUP BY under ONLY_FULL_GROUP_BY, COLLATE NOCASE dropped, the `key` column)."""
    with appdb.writer() as con:  # leftovers from the tests before
        for t in ("pix_favorite_photos", "pix_album_photos", "pix_albums"):
            con.execute(f"DELETE FROM {t}")
    users.create("alex", "correct horse", "admin"); users.create("vi", "", "viewer")
    state._settings = (-1, {})
    state.set_setting("zz_probe", "héllo ? %s"); state._settings = (-1, {})
    assert state.get_setting("zz_probe") == "héllo ? %s"
    me = users.get(next(u["id"] for u in users.list_users() if u["name"] == "alex"))
    assert me["role"] == "admin" and shared_users.authenticate("alex", "correct horse", "iopix") and not shared_users.authenticate("alex", "wrong", "iopix")
    assert shared_users.authenticate("vi", "", "iopix"), "a passwordless viewer signs in with one click"
    u = users.create("new", "password-1", "editor", "New@Example.com")
    assert u["email"] == "new@example.com" and users.get(u["id"])["name"] == "new"
    aid = state.create_album("Trip"); state.set_album_items(aid, [(1, "h1")], True)
    priv = state.create_album("Secret", me["id"], shared=False); state.set_album_items(priv, [(1, "h1")], True)
    assert "Secret" not in {a["name"] for a in state.summary(None)["albums"]}
    assert {a["name"] for a in state.summary(me)["albums"]} >= {"Trip", "Secret"}
    assert state.album_item_ids([priv]) == [] and state.album(priv)["shared"] is False
    tok = state.viewer.set(me)
    try:
        assert state.album_item_ids([priv]) == [1] and sorted(state.albums_of(1)) == sorted([aid, priv])
    finally:
        state.viewer.reset(tok)


def test_a_column_added_to_the_schema_reaches_an_existing_table(client):
    c = appdb.connect()
    try:
        c.execute("ALTER TABLE pix_albums DROP COLUMN shared")
        c.commit()
        appdb.ensure_schema(c)
        assert "shared" in appdb.columns(c, "pix_albums")
    finally:
        c.close()


def test_dump_is_the_backup_form(client, fresh, tmp_path):
    if not appdb.dump_tool():
        pytest.skip("no mysqldump/mariadb-dump on this machine")
    _seed()
    out = tmp_path / "iopix.sql"
    appdb.dump(out)
    text = out.read_text(errors="replace")
    assert "CREATE TABLE `pix_favorite_photos`" in text and "'zz_probe'" in text


def test_without_a_configuration_the_viewer_waits(monkeypatch):
    monkeypatch.setattr(appdb, "_cfg", None)
    monkeypatch.setattr(appdb.config, "own_db", lambda: {"host": "", "port": 3306, "database": "", "user": "", "password": ""})
    monkeypatch.setattr(appdb, "error", None)
    assert not appdb.configured()
    appdb.init()  # never raises
    assert appdb.error and not appdb.ready() and appdb.describe() == "no database configured"
    with pytest.raises(RuntimeError):
        appdb.connect()


def test_an_unreachable_server_is_recorded_not_fatal(monkeypatch):
    monkeypatch.setattr(appdb, "settings", lambda: {"type": "mysql", "host": "127.0.0.1", "port": 1, "database": "x", "user": "u", "password": ""})
    monkeypatch.setattr(appdb, "error", None)
    appdb.init()
    assert appdb.error and appdb.configured() and not appdb.ready() and "unavailable" in appdb.describe()


def test_every_declared_column_is_in_the_create_statement():
    for name, (cols, ddl) in appdb.TABLES.items():
        assert list(appdb.declared_columns(ddl)) == cols, name
    assert "undo" not in appdb.TABLES["pix_photo_history"][0] and " undo " not in appdb.TABLES["pix_photo_history"][1]

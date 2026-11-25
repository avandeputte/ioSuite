"""tools/settings_to_shared.py: what an install kept in prt_settings before 4.2.7 is where the program reads it now.
The settings are in the suite's one home under their new names; a person's layout, the bookmarks' counters and the
rest of what the start page wrote down for itself are in prt_state."""
import importlib.util
import json
from pathlib import Path

import pytest

from iosuite_shared import db as shared
from iostart import config, db, layout

OLD = {"accuweather_location": "348181", "accuweather_location_name": "Chicago, IL", "weather_units": "imperial",
       "photo_strip": "0", "ha_url": "http://ha.local:8123", "ha_name": "Home", "ha_entities": json.dumps([{"id": "light.kitchen"}]),
       "layout:default": json.dumps({"hidden": ["iomoney"]}), "user:7:layout": json.dumps({"hidden": ["iodns"]}),
       "user:7:layout:ab12": json.dumps({"name": "Kitchen tablet", "layout": {"layout": "cards"}}),
       "user:7:trmnl": json.dumps({"on": True}), "bookmarks_rev": "412", "bookmarks_highest_id": "97",
       "accuweather_location_geo": json.dumps({"lat": 41.9, "lon": -87.6}), "rates": json.dumps({"at": 1, "USD": 1}),
       "inbox_state": json.dumps({"checkedAt": 5}),
       "inbox_mailbox": json.dumps({"host": "imap.example.com", "port": 993, "user": "inbox@example.com", "folder": "Suite", "on": True})}


@pytest.fixture()
def tool():
    spec = importlib.util.spec_from_file_location("settings_to_shared", Path(__file__).resolve().parents[2] / "tools" / "settings_to_shared.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def before(client):
    """The table as 4.2.6 left it."""
    db.ex("CREATE TABLE IF NOT EXISTS prt_settings (name VARCHAR(64) PRIMARY KEY, value MEDIUMTEXT)")
    db.ex("DELETE FROM prt_settings")
    db.many("INSERT INTO prt_settings (name, value) VALUES (%s, %s)", list(OLD.items()))
    yield client
    db.ex("DROP TABLE prt_settings")


def _live(name):
    shared.settings_cache.clear()
    return config.live(name)


def test_everything_kept_before_is_read_now(before, tool, capsys):
    assert tool.main(["--app", "iostart"]) == 0
    said = capsys.readouterr().out
    assert "Run it again with --write" in said and _live("WEATHER_LOCATION") == "" and db.get_state("user:7:layout") is None, "without --write nothing is written"

    assert tool.main(["--write", "--app", "iostart"]) == 0
    said = capsys.readouterr().out
    assert "Start the suite again" in said and " 0 left alone" in said, said
    # the settings, under their new names
    assert _live("WEATHER_LOCATION") == "348181" and _live("WEATHER_LOCATION_NAME") == "Chicago, IL"
    assert _live("WEATHER_UNITS") == "imperial" and _live("PHOTO_STRIP") == "0"
    assert _live("HA_URL") == "http://ha.local:8123" and json.loads(_live("HA_ENTITIES")) == [{"id": "light.kitchen"}]
    assert _live("MAIL_HOST") == "imap.example.com" and _live("MAIL_FOLDER") == "Suite" and _live("MAIL_ON") == "1"
    # what the start page wrote down for itself: the layouts, the counters, the rest, under the names it reads
    assert layout.family()["hidden"] == ["iomoney"] and layout.get(7)["hidden"] == ["iodns"], "as the page reads them"
    assert json.loads(db.get_state("user:7:layout")) == {"hidden": ["iodns"]}
    assert json.loads(db.get_state("user:7:layout:ab12"))["name"] == "Kitchen tablet"
    assert db.get_state("bookmarks_rev") == "412" and db.get_state("bookmarks_highest_id") == "97"
    assert json.loads(db.get_state("weather_location_geo"))["lat"] == 41.9 and db.get_state("accuweather_location_geo") is None
    assert json.loads(db.get_state("user:7:trmnl")) == {"on": True} and json.loads(db.get_state("inbox_state")) == {"checkedAt": 5}
    for setting in ("accuweather_location", "ha_url", "inbox_mailbox", "weather_units"):
        assert db.get_state(setting) is None, f"{setting} is a setting: not in prt_state as well"

    assert tool.main(["--write", "--app", "iostart"]) == 0
    assert "\n0 carried over" in capsys.readouterr().out, "a second run finds everything the same"


def test_what_was_written_since_is_kept_but_a_counter_never_goes_back(before, tool, capsys):
    """The new version ran for a while first: a place chosen again and a layout saved again stay, a counter that
    started again from nothing takes the larger number (a new bookmark must not get an id that is in use)."""
    shared.set_setting("WEATHER_LOCATION", "999", "iostart")
    db.set_state("user:7:layout", json.dumps({"hidden": []}))
    db.set_state("bookmarks_highest_id", "3")
    db.set_state("bookmarks_rev", "500")
    assert tool.main(["--write", "--app", "iostart"]) == 0
    said = capsys.readouterr().out
    assert "2 left alone" in said and "--overwrite takes the old value" in said, said
    assert _live("WEATHER_LOCATION") == "999" and json.loads(db.get_state("user:7:layout")) == {"hidden": []}
    assert db.get_state("bookmarks_highest_id") == "97" and db.get_state("bookmarks_rev") == "500"
    assert tool.main(["--write", "--overwrite", "--app", "iostart"]) == 0
    assert _live("WEATHER_LOCATION") == "348181" and json.loads(db.get_state("user:7:layout")) == {"hidden": ["iodns"]}
    assert db.get_state("bookmarks_rev") == "500", "never the smaller number, whatever is asked"


def test_a_run_that_could_not_read_says_so(before, tool, capsys, monkeypatch):
    """Not '0 carried over' and a clean exit: the first version of this stopped on every app and looked done."""
    def broken(app):
        raise RuntimeError("the database went away")
    monkeypatch.setattr(tool, "tables", broken)
    assert tool.main(["--write", "--app", "iostart"]) == 1
    err = capsys.readouterr().err
    assert "the database went away" in err and "NOT DONE for iostart" in err


def test_an_app_without_the_old_table_has_nothing_to_carry(client, tool, capsys):
    assert tool.main(["--write", "--app", "iostart"]) == 0
    assert "no prt_settings table" in capsys.readouterr().out

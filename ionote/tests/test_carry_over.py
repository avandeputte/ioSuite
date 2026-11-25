"""tools/settings_to_shared.py for ioNote: the app's name is a setting in the suite's one home, and what it wrote down
for itself (which standard templates each account was given) is in nts_state, so nobody is given them again."""
import importlib.util
from pathlib import Path

from iosuite_shared import db as shared
from ionote import config, db


def test_what_nts_settings_held_is_read_now(client, capsys):
    spec = importlib.util.spec_from_file_location("settings_to_shared", Path(__file__).resolve().parents[2] / "tools" / "settings_to_shared.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    with db.tx() as con:
        con.execute("CREATE TABLE IF NOT EXISTS nts_settings (name VARCHAR(191) PRIMARY KEY, value MEDIUMTEXT, updated_at DATETIME(3))")
        con.execute("DELETE FROM nts_settings")
        for k, v in (("app_name", "Family notes"), ("standard_templates:7", "3"), ("write_lock", "")):
            con.execute("INSERT INTO nts_settings (name, value) VALUES (%s, %s)", (k, v))
    try:
        assert tool.main(["--write", "--app", "ionote"]) == 0
        assert "2 carried over" in capsys.readouterr().out
        shared.settings_cache.clear()
        assert config.live("APP_NAME") == "Family notes" and db.get_state("standard_templates:7") == "3"
        assert db.get_state("app_name") is None
    finally:
        with db.tx() as con:
            con.execute("DROP TABLE nts_settings")

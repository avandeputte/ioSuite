"""tools/settings_to_shared.py for ioMoney: its settings are in the suite's one home, and what it wrote down for
itself is in mny_state: the day the household started looking at its transactions (the one from before stands, or
everything since would no longer ask for a look), a gap someone accepted on an account."""
import importlib.util
from pathlib import Path

from iosuite_shared import db as shared
from iomoney import balancecheck, config, db, review


def test_what_mny_settings_held_is_read_now(client, capsys):
    spec = importlib.util.spec_from_file_location("settings_to_shared", Path(__file__).resolve().parents[2] / "tools" / "settings_to_shared.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    db.ex("CREATE TABLE IF NOT EXISTS mny_settings (name VARCHAR(64) PRIMARY KEY, value MEDIUMTEXT)")
    db.ex("DELETE FROM mny_settings")
    db.many("INSERT INTO mny_settings (name, value) VALUES (%s, %s)",
            [("currency", "EUR"), ("monarch_auto", "0"), (review.SINCE, "1700000000"), (f"{balancecheck.OK}3", "12.50"),
             (f"{balancecheck.OK}4", "100"), ("monarch_ids", '["a", "b"]')])
    db.set_state(review.SINCE, "1790000000")      # the page was opened on the new version: it began again today
    db.set_state(f"{balancecheck.OK}4", "250")    # and a larger gap was accepted since: that is a person's newer word
    try:
        assert tool.main(["--write", "--app", "iomoney"]) == 0
        said = capsys.readouterr().out
        assert "5 carried over, 0 already the same, 1 left alone" in said, said
        shared.settings_cache.clear()
        assert config.live("CURRENCY") == "EUR" and config.live_flag("MONARCH_AUTO", True) is False
        assert review.since() == 1700000000
        assert db.get_state(f"{balancecheck.OK}3") == "12.50" and db.get_state(f"{balancecheck.OK}4") == "250"
        assert db.get_state("monarch_ids") == '["a", "b"]' and db.get_state("currency") is None
    finally:
        db.ex("DROP TABLE mny_settings")
        shared.set_setting("CURRENCY", None, "iomoney")
        shared.set_setting("MONARCH_AUTO", None, "iomoney")

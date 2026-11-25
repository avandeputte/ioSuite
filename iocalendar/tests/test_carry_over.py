"""tools/settings_to_shared.py for ioCalendar: its two settings are in the suite's one home, and what it wrote down
for itself (how far each calendar's deletion markers were purged, which a sync client's token is held against) is
in cal_state."""
import importlib.util
from pathlib import Path

from iosuite_shared import db as shared
from iocalendar import config, db, model


def test_what_cal_settings_held_is_read_now(client, capsys):
    spec = importlib.util.spec_from_file_location("settings_to_shared", Path(__file__).resolve().parents[2] / "tools" / "settings_to_shared.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    db.ex("CREATE TABLE IF NOT EXISTS cal_settings (name VARCHAR(64) PRIMARY KEY, value MEDIUMTEXT)")
    db.ex("DELETE FROM cal_settings")
    db.many("INSERT INTO cal_settings (name, value) VALUES (%s, %s)",
            [("holidays_countries", '[{"country": "BE"}]'), ("iocontact_birthdays", "1"), (f"{model.PURGED}4", "310"), (f"{model.PURGED}5", "12")])
    db.set_state(f"{model.PURGED}5", "40")  # purged again since, further on
    try:
        assert tool.main(["--write", "--app", "iocalendar"]) == 0
        assert "3 carried over, 1 already the same, 0 left alone" in capsys.readouterr().out
        shared.settings_cache.clear()
        assert config.live("HOLIDAYS") == '[{"country": "BE"}]' and config.live_flag("CONTACT_BIRTHDAYS") is True
        assert model.purged_before(4) == 310 and model.purged_before(5) == 40
    finally:
        db.ex("DROP TABLE cal_settings")

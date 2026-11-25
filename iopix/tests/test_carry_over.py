"""tools/settings_to_shared.py for ioPix: its settings are in the suite's one home under their new names, the digiKam
password is with the suite's keys and tokens, and what it wrote down for itself is in pix_state."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from iosuite_shared import credentials, db as shared
from iopix import config
from iopix.data import appdb, state
from iopix.digikam import dkdb


def test_what_pix_settings_held_is_read_now(client, capsys):
    spec = importlib.util.spec_from_file_location("settings_to_shared", Path(__file__).resolve().parents[2] / "tools" / "settings_to_shared.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    old = {"app_name": "Family photos", "map_provider": "osm", "scan_interval": "45", "db_backup": "0", "db_password": "s3cret",
           "recent_tags": '["Holidays"]', "near_dups_gen": "17", "face_vectors_built": "sface", "something_older": "x"}

    def make(con):
        con.execute("CREATE TABLE IF NOT EXISTS pix_settings (name VARCHAR(191) PRIMARY KEY, value MEDIUMTEXT)")
        con.execute("DELETE FROM pix_settings")
        for k, v in old.items():
            con.execute("INSERT INTO pix_settings (name, value) VALUES (?,?)", (k, v))
    state.write(make)
    before = {k: shared.get_setting(k, "", "iopix") for k in ("APP_NAME", "MAP_PROVIDER", "SCAN_INTERVAL", "DIGIKAM_DB_BACKUP")}
    kept = {k: state.get_state(k) for k in ("recent_tags", "near_dups_gen")}
    try:
        for k in before:
            shared.set_setting(k, None, "iopix")
        state.write(lambda c: c.execute("DELETE FROM pix_state WHERE name IN ('recent_tags', 'near_dups_gen')"))
        assert tool.main(["--write", "--app", "iopix"]) == 0
        said = capsys.readouterr().out
        assert "something_older is not kept any more" in said and "s3cret" not in said, said
        shared.settings_cache.clear()
        credentials.forget()
        assert config.live("APP_NAME") == "Family photos" and config.live("MAP_PROVIDER") == "osm" and config.live_int("SCAN_INTERVAL", 0) == 45
        assert config.live("DIGIKAM_DB_BACKUP") == "0" and credentials.get("iopix", dkdb.PASSWORD) == "s3cret"
        con = appdb.connect()
        try:
            now = dict(con.execute("SELECT name, value FROM pix_state").fetchall())
        finally:
            con.close()
        assert now["recent_tags"] == '["Holidays"]' and now["near_dups_gen"] == "17" and "something_older" not in now and "app_name" not in now
        # and run the way a person runs it, as a process of its own: it finds its way to ioPix's database by itself
        r = subprocess.run([sys.executable, str(Path(tool.__file__)), "--app", "iopix"], capture_output=True, text=True, env=dict(os.environ), timeout=120)
        assert r.returncode == 0 and "something_older is not kept any more" in r.stdout and "\n0 to carry over" in r.stdout, r.stdout + r.stderr
    finally:
        for k, v in before.items():
            shared.set_setting(k, v or None, "iopix")
        credentials.put("iopix", dkdb.PASSWORD, "", by="test")
        for k, v in kept.items():
            state.set_state(k, v)
        state.write(lambda c: c.execute("DROP TABLE pix_settings"))
        shared.settings_cache.clear()

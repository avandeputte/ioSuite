"""Carry an install's app settings over to the suite's one home for them.

Until 4.2 each app kept the settings a person changed on its own Settings page in a table of its own
(cal_settings, prt_settings, pix_settings...), beside the ones its app.json declared, which were already in the
Shared ioSuite database. There is now one home: every setting is declared in the app's app.json and kept in the
Shared ioSuite database (ios_settings), read as it is now, and each app's own table holds only what the app writes
down for itself (<prefix>_state).

A fresh install needs nothing. On an install that already ran, this reads the old rows and writes them to the one
home under their new names. It is not part of the program: nothing in the suite runs it, and running it twice does
no harm (it writes the same values again). Values a person has since set in the one home are left alone unless
--overwrite is given.

    cd /opt/iosuite
    .venv/bin/python tools/settings_to_shared.py            # say what would be carried over
    .venv/bin/python tools/settings_to_shared.py --write     # do it

The old tables are not dropped: the new version simply stops using them, so an admin can look before dropping
them (DROP TABLE cal_settings, and so on for each app whose lines this printed).
"""
import argparse
import sys

# the old key in the app's own table, and the name it has in the one home. Where a name is None the value was never
# a setting (what the app wrote down for itself): it stays in the app's own table, which is now <prefix>_state.
MOVED = {
    "iocalendar": {"holidays_countries": "HOLIDAYS", "iocontact_birthdays": "CONTACT_BIRTHDAYS"},
    "iodns": {"ddns_detect": "DDNS_DETECT", "ddns_minutes": "DDNS_MINUTES"},
    "iomoney": {"currency": "CURRENCY", "monarch_auto": "MONARCH_AUTO"},
    "ionote": {"app_name": "APP_NAME"},
    "iothings": {"currency": "CURRENCY"},
    "iostart": {"photo_strip": "PHOTO_STRIP", "weather_units": "WEATHER_UNITS",
                "accuweather_location": "WEATHER_LOCATION", "accuweather_location_name": "WEATHER_LOCATION_NAME",
                "ha_url": "HA_URL", "ha_name": "HA_NAME", "ha_entities": "HA_ENTITIES",
                "ha_builtin_alerts": "HA_BUILTIN_ALERTS"},
    "iopix": {"app_name": "APP_NAME", "write_files": "WRITE_FILES", "sidecar_compat": "SIDECAR_COMPAT",
              "digikam_sync": "DIGIKAM_SYNC", "file_scanner": "FILE_SCANNER", "scan_interval": "SCAN_INTERVAL",
              "bg_threads": "BG_THREADS", "search_model": "SEARCH_MODEL", "face_detector": "FACE_DETECTOR",
              "object_model": "OBJECT_MODEL", "caption_model": "CAPTION_MODEL", "face_vectors": "FACE_VECTORS",
              "speech_model": "SPEECH_MODEL", "near_dups_level": "NEAR_DUPS_LEVEL",
              "import_layout": "IMPORT_LAYOUT", "map_provider": "MAP_PROVIDER", "album_roots": "ALBUM_ROOTS",
              "templates": "EDIT_TEMPLATES",
              "db_type": "DIGIKAM_DB_TYPE", "db_sqlite_dir": "DIGIKAM_DB_DIR", "db_host": "DIGIKAM_DB_HOST",
              "db_port": "DIGIKAM_DB_PORT", "db_database": "DIGIKAM_DB_NAME", "db_user": "DIGIKAM_DB_USER",
              "db_backup": "DIGIKAM_DB_BACKUP"},
}
# the digiKam password was a setting too; it belongs with the suite's keys and tokens now (written, never read back)
SECRET = {"iopix": {"db_password": "digikam_db_password"}}
TABLE = {"iocalendar": "cal_settings", "iodns": "dns_settings", "iomoney": "mny_settings", "ionote": "nts_settings",
         "iothings": "thg_settings", "iostart": "prt_settings", "iopix": "pix_settings"}


def old_rows(app: str) -> dict:
    """{key: value} of the app's old settings table, {} when it is not there any more."""
    from iosuite_shared.app import of
    want = TABLE[app]
    if app == "iopix":   # its own database, which may be MySQL or the one the suite uses
        of(app).config   # read its settings, so appdb knows where to look
        from iopix.data import appdb
        con = appdb.connect(timeout=10)
        try:
            return dict(con.execute(f"SELECT name, value FROM {want}").fetchall())
        finally:
            con.close()
    db = of(app).module("db")
    db.init()
    return {r["name"]: r["value"] for r in db.q(f"SELECT name, value FROM {want}")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="carry the values over (without it, only say what would be)")
    ap.add_argument("--overwrite", action="store_true", help="also replace a value already set in the one home")
    ap.add_argument("--app", action="append", help="one app only (may be given several times)")
    a = ap.parse_args(argv)

    from iosuite_shared import config, credentials, db
    config.load_file()
    db.init()
    apps = a.app or sorted(MOVED)
    moved = kept = 0
    for app in apps:
        if app not in MOVED:
            print(f"{app}: nothing was ever kept apart for it", file=sys.stderr)
            continue
        try:
            rows = old_rows(app)
        except Exception as e:  # noqa: BLE001 - the app was never installed, or its table is already gone
            print(f"{app}: nothing to read ({type(e).__name__}: {str(e)[:80]})")
            continue
        here = db.settings_of(app)
        for old, new in MOVED[app].items():
            v = (rows.get(old) or "").strip()
            if not v:
                continue
            if here.get(new) and not a.overwrite:
                print(f"{app}: {new} is already set here ({here[new][:40]}); {old} was {v[:40]}")
                kept += 1
                continue
            print(f"{app}: {old} -> {new} = {v[:60]}")
            moved += 1
            if a.write:
                db.set_setting(new, v, app)
        for old, name in (SECRET.get(app) or {}).items():
            if (rows.get(old) or "").strip():
                print(f"{app}: {old} -> the suite's keys and tokens ({name})")
                moved += 1
                if a.write:
                    credentials.put(app, name, rows[old], by="settings_to_shared")
    print(f"\n{moved} to carry over, {kept} left alone." if not a.write else f"\n{moved} carried over, {kept} left alone.")
    if moved and not a.write:
        print("Run it again with --write to do it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

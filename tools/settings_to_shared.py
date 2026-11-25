"""Carry an install's app settings over to the suite's one home for them.

Until 4.2 each app kept the settings a person changed on its own Settings page in a table of its own
(cal_settings, prt_settings, pix_settings...), beside the ones its app.json declared, which were already in the
Shared ioSuite database. There is now one home: every setting is declared in the app's app.json and kept in the
Shared ioSuite database (ios_settings), read as it is now, and each app's own table holds only what the app writes
down for itself (<prefix>_state).

A fresh install needs nothing. On an install that already ran, this reads the old rows and puts each where the
program reads it now: a setting in the one home under its new name, and everything else (a person's layout of the
start page, where a sync got to, the highest bookmark id ever given) in the app's <prefix>_state under the name it
had. It is not part of the program: nothing in the suite runs it, and running it twice does no harm (the second run
finds everything the same). A value that is already there and differs is left alone unless --overwrite is given,
except a counter or a high-water mark (LARGER), where the larger one stands, and the day something began (FIRST),
where the one from before stands.

    cd /opt/iosuite
    .venv/bin/python tools/settings_to_shared.py            # say what would be carried over
    .venv/bin/python tools/settings_to_shared.py --write     # do it, then start the suite again

The old tables are not dropped: the new version simply stops using them, so an admin can look before dropping
them (DROP TABLE cal_settings, and so on for each app whose lines this printed).
"""
import argparse
import json
import sys

# the old key in the app's own table, and the name it has in the one home. A row that is not named here was never a
# setting: it is what the app wrote down for itself, and goes to the app's <prefix>_state (see carry).
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
# one old row that held several settings as JSON: each of its fields is a setting of its own now
SPLIT = {"iostart": {"inbox_mailbox": {"host": "MAIL_HOST", "port": "MAIL_PORT", "user": "MAIL_USER",
                                       "folder": "MAIL_FOLDER", "on": "MAIL_ON"}}}
# the digiKam password was a setting too; it belongs with the suite's keys and tokens now (written, never read back)
SECRET = {"iopix": {"db_password": "digikam_db_password"}}
# every app that had a table of its own, by the prefix of its tables: <prefix>_settings then, <prefix>_state now
PREFIX = {"iocalendar": "cal", "iocontact": "con", "iodns": "dns", "iodocs": "doc", "iomoney": "mny", "ionote": "nts",
          "iopix": "pix", "iorecipe": "rcp", "iostart": "prt", "iothings": "thg", "iotask": "tsk"}
# what an app wrote down for itself keeps its name, but for these
STATE_NAME = {"iostart": {"accuweather_location_geo": "weather_location_geo"}}
# what only ever goes up (a counter, a high-water mark), by the start of its name: where the app has written one again
# since, the larger stands, so a counter that began again from nothing never hands out a number that is in use
LARGER = {"iostart": ("bookmarks_rev", "bookmarks_highest_id"), "iocalendar": ("purged_token:",),
          "iocontact": ("purged_token:",), "iotask": ("purged_token:",), "ionote": ("standard_templates:",)}
# what says when something began: the one from before stands, whatever was written since
FIRST = {"iomoney": ("review_since",)}
# rows that are not carried: a lock row the app makes again
NOT_CARRIED = {"ionote": {"write_lock"}}


class Failed(Exception):
    """An app's tables could not be read or written: said, and the run ends with an error."""


def _missing(e: Exception) -> bool:
    """The table is not there (MariaDB's 1146, SQLite's "no such table")."""
    return (getattr(e, "args", None) or [None])[0] == 1146 or "no such table" in str(e).lower() or "doesn't exist" in str(e)


def tables(app: str):
    """(rows(table) -> {name: value}, write(name, value) into the app's state, the state names it knows or None)."""
    from iosuite_shared.app import of
    if app == "iopix":   # its own database layer, and a fixed list of what it writes down
        of(app).config   # read its settings, so appdb knows where to look
        from iopix.data import appdb, state

        def rows(table: str) -> dict:
            con = appdb.connect(timeout=10)
            try:
                return {r[0]: r[1] for r in con.execute(f"SELECT name, value FROM {table}").fetchall()}
            finally:
                con.close()
        return rows, state.set_state, set(state.STATE)
    db = of(app).module("db")
    if app == "ionote":  # its own connections too
        def rows(table: str) -> dict:
            with db.connect() as con:
                return {r[0]: r[1] for r in con.execute(f"SELECT name, value FROM {table}").fetchall()}
        return rows, db.set_state, None
    return (lambda table: {r["name"]: r["value"] for r in db.q(f"SELECT name, value FROM {table}")}), db.set_state, None


def _short(v: str) -> str:
    v = " ".join(str(v).split())
    return v if len(v) <= 60 else v[:57] + "..."


def _number(v) -> int | None:
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def carry(app: str, write: bool, overwrite: bool, say=print) -> tuple:
    """One app. Returns (carried, the same already, left alone)."""
    from iosuite_shared import credentials, db as shared
    p = PREFIX[app]
    rows, put_state, known = tables(app)
    try:
        old = rows(f"{p}_settings")
    except Exception as e:  # noqa: BLE001
        if _missing(e):
            say(f"{app}: no {p}_settings table (never installed here, or already dropped)")
            return 0, 0, 0
        raise Failed(f"{app}: {p}_settings could not be read ({type(e).__name__}: {e})") from e
    try:
        state = rows(f"{p}_state")
    except Exception as e:  # noqa: BLE001
        if _missing(e):
            raise Failed(f"{app}: there is no {p}_state table yet: start the app once on this version, then run this again") from e
        raise Failed(f"{app}: {p}_state could not be read ({type(e).__name__}: {e})") from e
    moved, split, secret = MOVED.get(app) or {}, SPLIT.get(app) or {}, SECRET.get(app) or {}
    here = shared.settings_of(app)
    carried = same = left = 0

    # the settings: to the one home, under their new names
    pairs = [(o, n, (old.get(o) or "").strip()) for o, n in moved.items()]
    for o, fields in split.items():
        try:
            blob = json.loads(old.get(o) or "{}")
        except ValueError:
            blob = {}
        for field, n in fields.items():
            v = blob.get(field) if isinstance(blob, dict) else None
            pairs.append((f"{o}.{field}", n, "" if v is None else ("1" if v else "0") if isinstance(v, bool) else str(v).strip()))
    for o, n, v in pairs:
        if not v:
            continue
        cur = (here.get(n) or "").strip()
        if cur == v:
            same += 1
        elif cur and not overwrite:
            say(f"{app}: {n} is already set ({_short(cur)}); left alone, {o} was {_short(v)}")
            left += 1
        else:
            say(f"{app}: {o} -> setting {n} = {_short(v)}")
            carried += 1
            if write:
                shared.set_setting(n, v, app)
    for o, name in secret.items():
        if (old.get(o) or "").strip():
            if credentials.get(app, name) == old[o]:
                same += 1
                continue
            say(f"{app}: {o} -> the suite's keys and tokens ({name})")
            carried += 1
            if write:
                credentials.put(app, name, old[o], by="settings_to_shared")

    # everything else is what the app wrote down for itself: to <prefix>_state
    renamed, skip = STATE_NAME.get(app) or {}, NOT_CARRIED.get(app) or set()
    for o in sorted(old):
        v = old[o]
        if o in moved or o in split or o in secret or o in skip or v is None or str(v) == "":
            continue
        n = renamed.get(o, o)
        if known is not None and n not in known:
            say(f"{app}: {o} is not kept any more; not carried")
            continue
        cur = state.get(n)
        if cur is not None and str(cur) == str(v):
            same += 1
            continue
        if cur is not None and str(cur) != "":
            a, b = _number(v), _number(cur)
            if n.startswith(LARGER.get(app) or ("\0",)) and a is not None and b is not None:
                if a <= b:
                    same += 1
                    continue
                say(f"{app}: {n} = {a} (it is {b} here: the larger stands)")
            elif n.startswith(FIRST.get(app) or ("\0",)):
                say(f"{app}: {n} = {_short(v)} (it is {_short(cur)} here: the one from before stands)")
            elif not overwrite:
                say(f"{app}: {n} was written again since ({_short(cur)}); left alone, it was {_short(v)}")
                left += 1
                continue
            else:
                say(f"{app}: {n} = {_short(v)} (replacing {_short(cur)})")
        else:
            say(f"{app}: {n} = {_short(v)}" if n == o else f"{app}: {o} -> {n} = {_short(v)}")
        carried += 1
        if write:
            put_state(n, str(v))
    return carried, same, left


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="carry the values over (without it, only say what would be)")
    ap.add_argument("--overwrite", action="store_true", help="also replace a value that is already there and differs")
    ap.add_argument("--app", action="append", help="one app only (may be given several times)")
    a = ap.parse_args(argv)

    from iosuite_shared import config, db
    config.load_file()
    db.init()
    carried = same = left = 0
    failed = []
    for app in a.app or sorted(PREFIX):
        if app not in PREFIX:
            print(f"{app}: it never had a table of its own for this", file=sys.stderr)
            continue
        try:
            c, s, k = carry(app, a.write, a.overwrite)
        except Failed as e:
            print(str(e), file=sys.stderr)
            failed.append(app)
            continue
        except Exception as e:  # noqa: BLE001 - said in full: a run that carried nothing must never look like one that had nothing to do
            print(f"{app}: stopped ({type(e).__name__}: {e})", file=sys.stderr)
            failed.append(app)
            continue
        carried, same, left = carried + c, same + s, left + k
    print(f"\n{carried} {'carried over' if a.write else 'to carry over'}, {same} already the same, {left} left alone.")
    if failed:
        print(f"NOT DONE for {', '.join(failed)}: see the lines above.", file=sys.stderr)
        return 1
    if carried and not a.write:
        print("Run it again with --write to do it.")
    elif carried:
        print("Start the suite again now, so every app reads what was carried over.")
    if left:
        print("What was left alone is kept as it is now; --overwrite takes the old value instead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

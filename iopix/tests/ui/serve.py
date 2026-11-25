"""The browser tests' server: ioPix alone under uvicorn, with stored settings of its own.

The API tests and this server share the session's Shared ioSuite database (so an account made in a test is one the
server knows), but not the library, the data folder or ioPix's own database: what would be stored for ioPix is
overlaid, for this process only, with the values in IOPIX_UI_SETTINGS (JSON): where iopix.config reads them as it
starts, and where one is asked for as it is now (config.live, e.g. the folder with digiKam's database, which the API
tests store for their own library).

    python iopix/tests/ui/serve.py PORT
"""
import json
import os
import sys

from iosuite_shared import config, db

_read, _get, _own = config._stored, db.get_setting, json.loads(os.environ["IOPIX_UI_SETTINGS"])


def _stored(app: str) -> tuple:
    mine, suite = _read(app)
    return ({**mine, **_own} if app == "iopix" else mine), suite


def _get_setting(key: str, default: str = "", app: str = "") -> str:
    return _own[key] if app == "iopix" and key in _own else _get(key, default, app)


config._stored, db.get_setting = _stored, _get_setting

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("iopix.main:app", host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")

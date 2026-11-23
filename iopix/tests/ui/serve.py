"""The browser tests' server: ioPix alone under uvicorn, with stored settings of its own.

The API tests and this server share the session's Shared ioSuite database (so an account made in a test is one the
server knows), but not the library, the data folder or ioPix's own database: what would be stored for ioPix is
overlaid, for this process only, with the values in IOPIX_UI_SETTINGS (JSON) before iopix.config reads them.

    python iopix/tests/ui/serve.py PORT
"""
import json
import os
import sys

from iosuite_shared import config

_read, _own = config._stored, json.loads(os.environ["IOPIX_UI_SETTINGS"])


def _stored(app: str) -> tuple:
    mine, suite = _read(app)
    return ({**mine, **_own} if app == "iopix" else mine), suite


config._stored = _stored

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("iopix.main:app", host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")

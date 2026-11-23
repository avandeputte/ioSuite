"""One log per copy of the program, every line marked with the app it came from.

    2026-11-23 09:14:02,118 INFO [iocalendar] uvicorn.access: 192.168.1.20:51234 - "GET /api/events HTTP/1.1" 200
    2026-11-23 09:14:03,402 WARNING [-] iosuite_shared.host: iopix could not start (tried again in 30 s)

The file is the machine's LOG_FILE (<DATA_DIR>/iosuite.log by default; LOG_FILE=off: none, the lines still go to
stderr, which is the service's journal). One rule keeps it small: at MAX_BYTES it is put aside and a new one begun,
and KEEP old ones stay (about 100 MB at most). Uvicorn's request and error lines are in it too.

Which app a line is from: the logger's name says (iocalendar.model, iosuite_shared.iocalendar), else the app whose
request or start-up this is (iosuite_shared.host.CURRENT); "-" for what is nobody's in particular (the web server
starting, the host itself, a library on a thread of its own).

`read()` is what the suite's log viewer shows (Settings › Servers › Logs: iosuite_shared.admin asks every copy of the
suite and merges their lines by time): the lines of this copy, filtered by app, level, time and text, with a cursor
to ask for what came after. `tail()` is the same for the apps' MCP tools: one app's last lines as text.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import threading
import time
from pathlib import Path

from iosuite_shared import config

FORMAT = "%(asctime)s %(levelname)s [%(app)s] %(name)s: %(message)s"
MAX_BYTES = 20 << 20   # the file is put aside at this size
KEEP = 4               # and this many old ones are kept
READ_BYTES = 8_000_000  # how far back one read of a file goes
NOBODY = "-"
LEVELS = ("any", "info", "warning", "error", "auth")
PAGE_REQUEST = "uvicorn.access"
AUTH_LOGGER = "iosuite_shared.auth"
LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)[,.](\d{3}) ([A-Z]+) \[([A-Za-z0-9_-]+)\] (\S+?): (.*)$")
# addresses whose path holds a secret (subscription links /ics/<secret>/ and /cal/<secret>/, iosuite_shared.feeds; the
# Apple profile downloads /profile/<secret>/): the request log, which suite admins read, shows "-"
SECRET_PATHS = re.compile(r"/(ics|cal|profile)/[^/?\s]+")
_lock = threading.Lock()
_handler = None


class SecretPaths:
    """A logging filter for uvicorn's request lines: the secret in those paths becomes "-"."""

    def filter(self, record) -> bool:
        a = record.args
        if isinstance(a, tuple) and any(isinstance(x, str) and SECRET_PATHS.search(x) for x in a):
            record.args = tuple(SECRET_PATHS.sub(r"/\1/-", x) if isinstance(x, str) else x for x in a)
        return True


def app_of(record) -> str:
    """The app a log record belongs to (see the module's text)."""
    from iosuite_shared import catalog
    name = record.name
    first = name.split(".", 1)[0]
    if first == "iosuite_shared":
        first = name.split(".", 2)[1] if name.count(".") else ""
    if first in catalog.APPS:
        return first
    from iosuite_shared import host
    return host.CURRENT.get() or NOBODY


class Mark:
    """A logging filter on the handlers: every record gets its app (record.app), which the format prints."""

    def filter(self, record) -> bool:
        if not hasattr(record, "app"):
            record.app = app_of(record)
        return True


def copy_name() -> str:
    """What this copy is called in the viewer when the suite has several (iosuite_shared.suite.copy_name)."""
    from iosuite_shared import suite
    return suite.copy_name()


def setup(level: int | None = None) -> bool:
    """Logging for the copy: INFO to stderr (the service's journal) and to the one log file, every line marked with
    its app. Idempotent: a second call (each app asks as it is loaded; the tests start apps more than once) adds
    nothing. False when there is no file (LOG_FILE=off, or it could not be opened: the copy runs without it)."""
    global _handler
    root = logging.getLogger()
    with _lock:
        mark = Mark()
        if not root.handlers:  # nothing set up yet (a test runner has its own): stderr, which is the service's journal
            err = logging.StreamHandler()
            err.setFormatter(logging.Formatter(FORMAT))
            err.addFilter(mark)
            root.addHandler(err)
        if level:
            root.setLevel(level)
        if root.level > logging.INFO or root.level == logging.NOTSET:
            root.setLevel(logging.INFO)
        access = logging.getLogger("uvicorn.access")
        if not any(isinstance(f, SecretPaths) for f in access.filters):
            access.addFilter(SecretPaths())
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):  # theirs go where everything goes, once
            lg = logging.getLogger(name)
            lg.handlers.clear()
            lg.propagate = True
        path = config.LOG_FILE
        if not path:
            return False
        if _handler is not None and _handler.baseFilename == str(Path(path).resolve()) and _handler in root.handlers:
            return True
        if os.environ.get("IOSUITE_LOG_CHILD"):  # a process an app started (a job worker): its stderr is the copy's; one writer per file
            return False
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            h = logging.handlers.RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=KEEP, encoding="utf-8")
        except OSError as e:
            logging.getLogger("iosuite_shared.logs").warning("no log file at %s: %s", path, e)
            return False
        h.setFormatter(logging.Formatter(FORMAT))
        h.addFilter(mark)
        if _handler is not None and _handler in root.handlers:
            root.removeHandler(_handler)
        root.addHandler(h)
        _handler = h
        return True


# ---- reading it back
def _files(path: Path) -> list:
    """The log's files, oldest first: iosuite.log.4 … iosuite.log.1, iosuite.log."""
    out = [Path(f"{path}.{i}") for i in range(KEEP, 0, -1)]
    return [p for p in out if p.exists()] + ([path] if path.exists() else [])


def _epoch(stamp: str, ms: str) -> float:
    try:
        return time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S")) + int(ms) / 1000
    except (ValueError, OverflowError):
        return 0.0


def parse(text: str) -> list:
    """The records of a piece of the log: [{ts, time, level, app, logger, text}]. A line that does not begin like one
    (a traceback, a message of several lines) belongs to the record before it."""
    out = []
    for line in text.splitlines():
        m = LINE.match(line)
        if m:
            out.append({"ts": _epoch(m[1], m[2]), "time": f"{m[1]}.{m[2]}", "level": m[3], "app": m[4], "logger": m[5], "text": m[6]})
        elif out:
            out[-1]["text"] += "\n" + line
        elif line.strip():  # the piece began in the middle of a record
            out.append({"ts": 0.0, "time": "", "level": "", "app": NOBODY, "logger": "", "text": line})
    return out


def _keep(r: dict, app: str, level: str, contains: str, requests: bool, since: float, until: float) -> bool:
    if app and r["app"] != app:
        return False
    if not requests and r["logger"] == PAGE_REQUEST:
        return False
    if since and r["ts"] and r["ts"] < since:
        return False
    if until and r["ts"] and r["ts"] > until:
        return False
    if level == "auth":
        if r["logger"] != AUTH_LOGGER:
            return False
    elif level == "error":
        if r["level"] not in ("ERROR", "CRITICAL") and "Traceback" not in r["text"]:
            return False
    elif level == "warning":
        if r["level"] not in ("WARNING", "ERROR", "CRITICAL") and "Traceback" not in r["text"]:
            return False
    elif level == "info":
        if r["level"] == "DEBUG":
            return False
    if contains and contains not in r["text"].lower() and contains not in r["logger"].lower():
        return False
    return True


def _read_from(p: Path, start: int) -> tuple:
    """(text, size, inode) of a file from `start` (a negative start: that far back from the end, from the first whole line)."""
    with open(p, "rb") as f:
        st = os.fstat(f.fileno())
        size = st.st_size
        back = start < 0
        if back:
            start = max(0, size + start)
        f.seek(min(start, size))
        data = f.read()
    text = data.decode("utf-8", "replace")
    if back and start > 0:
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text, size, st.st_ino


def read(app: str = "", level: str = "any", contains: str = "", requests: bool = False, since: float = 0, until: float = 0,
         limit: int = 300, after: str = "") -> dict:
    """This copy's log lines, oldest first:
        {copy, file, size, lines: [{ts, time, level, app, logger, text}], cursor, more}
    The last `limit` lines that pass the filters (app: one app's, "-" for nobody's; level: any, info, warning, error,
    auth (sign-ins only); contains: text, any case; requests: page requests too; since/until: seconds since 1970).
    `after`: the cursor of an earlier answer: only what was written since (following the log live). `more`: older
    lines that pass were left out."""
    path = config.LOG_FILE
    limit = max(1, min(int(limit or 300), 5000))
    level = level if level in LEVELS else "any"
    contains = (contains or "").strip().lower()[:200]
    out = {"copy": copy_name(), "file": str(path) if path else "", "size": 0, "lines": [], "cursor": "", "more": False}
    if not path:
        out["note"] = "this server keeps no log file (LOG_FILE=off)"
        return out
    path = Path(path)
    files = _files(path)
    if not files:
        out["note"] = "no log file yet"
        return out
    records = []
    inode = offset = 0
    if after:  # what came since: the rest of the file the cursor was in (put aside meanwhile, perhaps), then the newer ones
        try:
            inode, offset = (int(x) for x in after.split(":", 1))
        except ValueError:
            inode = offset = 0
        seen = False
        for p in files:
            try:
                ino = p.stat().st_ino
                if ino == inode:
                    text, _end, _ = _read_from(p, offset)
                    seen = True
                elif seen:
                    text, _end, _ = _read_from(p, 0)
                else:
                    continue
            except OSError:
                continue
            records += parse(text)
        if not seen:  # the file of the cursor is gone (cleaned up): the current one's end
            text, _end, _ = _read_from(files[-1], -READ_BYTES)
            records = parse(text)
    else:
        need_older = bool(since or until or app or contains or level != "any")
        for p in reversed(files):  # the newest first; older files only while there is room and a filter might find more
            try:
                text, _end, _ = _read_from(p, -READ_BYTES)
            except OSError:
                continue
            got = [r for r in parse(text) if _keep(r, app, level, contains, requests, since, until)]
            records = got + records
            if len(records) >= limit or not need_older:
                break
            if since and got and got[0]["ts"] and got[0]["ts"] <= since:
                break
    if after:
        records = [r for r in records if _keep(r, app, level, contains, requests, since, until)]
    try:
        st = path.stat()
        out["size"], out["cursor"] = st.st_size, f"{st.st_ino}:{st.st_size}"
    except OSError:
        pass
    out["more"] = len(records) > limit
    out["lines"] = records[-limit:]
    return out


def tail(app: str = "", lines: int = 300, contains: str = "", level: str = "any", requests: bool = True) -> dict:
    """One app's last lines as text, for the apps' MCP tools: {file, size_bytes, returned, lines}."""
    got = read(app=app, level=level, contains=contains, requests=requests, limit=lines)
    text = [f"{r['time']} {r['level']} {r['logger']}: {r['text']}" for r in got["lines"]]
    out = {"file": got["file"], "size_bytes": got["size"], "returned": len(text), "lines": text}
    if got.get("note"):
        out["note"] = got["note"]
    return out

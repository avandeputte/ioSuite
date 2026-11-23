"""The copy's one log (iosuite_shared.logs): every line marked with its app, one file with one size rule, and reading
it back for the viewer (filters, the cursor that follows it live, the file being put aside meanwhile)."""
import logging
import os
import time

import pytest

from iosuite_shared import config, host, logs


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    """A log file of the test's own; the handlers it brought are taken off again."""
    path = tmp_path / "iosuite.log"
    monkeypatch.setattr(config, "LOG_FILE", path)
    monkeypatch.delenv("IOSUITE_LOG_CHILD", raising=False)
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield path
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)
    logs._handler = None


def write(path, *lines):
    with open(path, "a", encoding="utf-8") as f:
        f.write("".join(x + "\n" for x in lines))


def stamp(seconds_ago=0.0, ms="000"):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - seconds_ago)) + "," + ms


def test_every_line_says_which_app_it_is_from(log_file):
    assert logs.setup() is True
    logging.getLogger("iocalendar.model").info("an event was saved")
    logging.getLogger("iosuite_shared.iomoney").warning("a link changed")
    logging.getLogger("iosuite_shared.host").info("3 app(s) up")
    token = host.CURRENT.set("iopix")
    try:
        logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/api/photos", "1.1", 200)
        logging.getLogger("PIL.Image").warning("a library, during an ioPix request")
    finally:
        host.CURRENT.reset(token)
    got = logs.read(requests=True)["lines"]
    assert [(r["app"], r["logger"], r["level"]) for r in got] == [
        ("iocalendar", "iocalendar.model", "INFO"), ("iomoney", "iosuite_shared.iomoney", "WARNING"),
        ("-", "iosuite_shared.host", "INFO"), ("iopix", "uvicorn.access", "INFO"), ("iopix", "PIL.Image", "WARNING")]
    assert got[0]["text"] == "an event was saved" and got[0]["ts"] > time.time() - 60 and got[3]["text"].endswith('"GET /api/photos HTTP/1.1" 200')


def test_setting_up_twice_adds_nothing(log_file):
    assert logs.setup() and logs.setup() and logs.setup()
    files = [h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(files) == 1 and files[0].maxBytes == logs.MAX_BYTES and files[0].backupCount == logs.KEEP
    logging.getLogger("iotask.api").info("once")
    assert log_file.read_text().count("once") == 1
    assert not logging.getLogger("uvicorn.access").handlers and logging.getLogger("uvicorn.access").propagate


def test_no_file_when_the_machine_says_off_or_it_cannot_be_written(log_file, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOG_FILE", None)
    assert logs.setup() is False
    assert logs.read()["note"] == "this server keeps no log file (LOG_FILE=off)" and logs.read()["lines"] == []
    blocked = tmp_path / "a-file"
    blocked.write_text("x")
    monkeypatch.setattr(config, "LOG_FILE", blocked / "iosuite.log")
    assert logs.setup() is False  # the copy runs without it


def test_a_process_an_app_started_leaves_the_file_to_the_copy(log_file, monkeypatch):
    monkeypatch.setenv("IOSUITE_LOG_CHILD", "1")
    assert logs.setup() is False and not log_file.exists()


def test_the_secret_in_a_subscription_address_is_not_logged(log_file):
    logs.setup()
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/calendar/ics/s3cr3t/home.ics?x=1", "1.1", 200)
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/profile/t0ken/calendar.mobileconfig", "1.1", 200)
    text = log_file.read_text()
    assert "s3cr3t" not in text and "t0ken" not in text and "/calendar/ics/-/home.ics?x=1" in text and "/profile/-/calendar.mobileconfig" in text


def test_a_traceback_belongs_to_the_line_before_it(log_file):
    write(log_file, f"{stamp()} ERROR [iomoney] iomoney.sync: the sync failed", "Traceback (most recent call last):", '  File "x.py", line 1',
          "ValueError: no", f"{stamp()} INFO [iomoney] iomoney.sync: next")
    got = logs.read()["lines"]
    assert len(got) == 2 and got[0]["text"].endswith("ValueError: no") and got[0]["text"].count("\n") == 3 and got[1]["text"] == "next"


def test_reading_filters_by_app_level_text_and_time(log_file):
    write(log_file,
          f"{stamp(7200)} INFO [iocalendar] iocalendar.api: two hours ago",
          f"{stamp(60)} INFO [iocalendar] iocalendar.api: saved an Event",
          f"{stamp(50)} WARNING [iomoney] iomoney.sync: Monarch was slow",
          f"{stamp(40)} ERROR [iomoney] iomoney.sync: Monarch did not answer",
          f"{stamp(30)} INFO [iocalendar] uvicorn.access: 1.2.3.4:5 - \"GET /api/events HTTP/1.1\" 200",
          f"{stamp(20)} INFO [-] iosuite_shared.auth: alex signed in",
          f"{stamp(10)} DEBUG [iopix] iopix.scan: looking at a file",
          f"{stamp(5)} INFO [iopix] iopix.scan: done",
          "Traceback (most recent call last):")
    texts = lambda **kw: [r["text"].split("\n")[0] for r in logs.read(**kw)["lines"]]  # noqa: E731
    assert len(texts()) == 7 and len(texts(requests=True)) == 8
    assert texts(app="iomoney") == ["Monarch was slow", "Monarch did not answer"]
    assert texts(app="-") == ["alex signed in"]
    assert texts(level="warning") == ["Monarch was slow", "Monarch did not answer", "done"]  # a traceback counts, whatever the level
    assert texts(level="error") == ["Monarch did not answer", "done"]
    assert texts(level="auth") == ["alex signed in"]
    assert "looking at a file" not in texts(level="info") and "looking at a file" in texts(level="any")
    assert texts(contains="MONARCH") == ["Monarch was slow", "Monarch did not answer"]
    assert texts(contains="iopix.scan") == ["looking at a file", "done"]  # the logger's name too
    assert texts(since=time.time() - 3600)[0] == "saved an Event" and texts(until=time.time() - 3600) == ["two hours ago"]
    assert texts(level="nonsense") == texts()
    got = logs.read(limit=3)
    assert len(got["lines"]) == 3 and got["more"] and got["lines"][-1]["text"].startswith("done")
    assert not logs.read(limit=50)["more"]


def test_the_cursor_gives_only_what_came_since(log_file):
    write(log_file, f"{stamp()} INFO [iotask] iotask.api: one")
    first = logs.read()
    assert [r["text"] for r in first["lines"]] == ["one"] and first["cursor"] == f"{os.stat(log_file).st_ino}:{os.stat(log_file).st_size}"
    assert logs.read(after=first["cursor"])["lines"] == []
    write(log_file, f"{stamp()} INFO [iotask] iotask.api: two", f"{stamp()} INFO [ionote] ionote.api: three")
    second = logs.read(after=first["cursor"])
    assert [r["text"] for r in second["lines"]] == ["two", "three"]
    assert [r["text"] for r in logs.read(after=first["cursor"], app="ionote")["lines"]] == ["three"]
    assert logs.read(after=second["cursor"])["lines"] == []


def test_following_goes_on_when_the_file_is_put_aside(log_file):
    write(log_file, f"{stamp()} INFO [iotask] iotask.api: one")
    cursor = logs.read()["cursor"]
    write(log_file, f"{stamp()} INFO [iotask] iotask.api: two, in the old file")
    os.rename(log_file, f"{log_file}.1")  # what the handler does at MAX_BYTES
    write(log_file, f"{stamp()} INFO [iotask] iotask.api: three, in the new file")
    got = logs.read(after=cursor)
    assert [r["text"] for r in got["lines"]] == ["two, in the old file", "three, in the new file"]
    assert logs.read(after=got["cursor"])["lines"] == []
    # a cursor into a file that is gone, or one that says nothing: the current file's end
    assert [r["text"] for r in logs.read(after="12345:0")["lines"]] == ["three, in the new file"]
    assert [r["text"] for r in logs.read(after="nonsense")["lines"]] == ["three, in the new file"]


def test_a_filter_looks_in_the_older_files_too(log_file):
    write(f"{log_file}.2", f"{stamp(300)} ERROR [iodns] iodns.zone: oldest")
    write(f"{log_file}.1", f"{stamp(200)} ERROR [iodns] iodns.zone: older", f"{stamp(190)} INFO [iotask] iotask.api: x")
    write(log_file, f"{stamp(10)} INFO [iotask] iotask.api: newest")
    assert [r["text"] for r in logs.read()["lines"]] == ["newest"]  # no filter: the current file is enough
    assert [r["text"] for r in logs.read(app="iodns")["lines"]] == ["oldest", "older"]
    assert [r["text"] for r in logs.read(level="error", limit=1)["lines"]] == ["older"]


def test_no_file_yet(log_file):
    assert logs.read()["note"] == "no log file yet" and logs.read()["cursor"] == ""


def test_an_app_s_last_lines_as_text(log_file):
    write(log_file, f"{stamp(2)} INFO [iotask] iotask.api: one", f"{stamp(1)} WARNING [ionote] ionote.api: two",
          f"{stamp()} INFO [iotask] uvicorn.access: 1.2.3.4:5 - \"GET /api/tasks HTTP/1.1\" 200")
    got = logs.tail("iotask")
    assert got["returned"] == 2 and got["file"] == str(log_file) and got["size_bytes"] == os.stat(log_file).st_size
    assert got["lines"][0].endswith("INFO iotask.api: one") and "GET /api/tasks" in got["lines"][1]
    assert logs.tail("iotask", requests=False)["returned"] == 1 and logs.tail("ionote", level="warning")["returned"] == 1

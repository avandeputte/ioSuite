"""The helper process: work goes there and comes back; a crash, a timeout or too much memory there costs the call,
never the copy; with the helper off the work runs here. Also its heavy lane (helper.Heavy), the process that stays
between calls and talks both ways while one runs (ioPix's analysis jobs; iopix/tests/test_jobproc.py has those)."""
import logging
import os
import threading
import time

import pytest

from iosuite_shared import helper
from iosuite_shared.tests import heavywork, helperwork

pytestmark = pytest.mark.skipif(os.name != "posix", reason="the helper runs on Linux and macOS")


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("HELPER", "on")
    monkeypatch.delenv("HELPER_MEMORY_MB", raising=False)
    yield
    helper.shutdown()


def test_runs_in_another_process(on):
    assert helper.enabled()
    assert helper.call(helperwork.add, 2, 3, times=4) == 20
    there = helper.call(helperwork.pid)
    assert there != os.getpid()
    assert helper.call(helperwork.pid) == there  # the same helper serves the next call
    assert helper.status()["calls"] >= 3


def test_its_errors_come_back_as_they_are(on):
    with pytest.raises(helperwork.Picky, match="not this one"):
        helper.call(helperwork.fail)
    assert helper.call(helperwork.add, 1, 1) == 2  # and the helper is still there


def test_a_crash_costs_the_call_not_the_copy(on):
    first = helper.call(helperwork.pid)
    with pytest.raises(helper.HelperLost, match="crashed"):
        helper.call(helperwork.crash)
    assert helper.call(helperwork.pid) != first  # a new helper
    assert helper.status()["lastLost"]["work"].endswith("crash")


def test_too_long(on):
    with pytest.raises(helper.HelperLost, match="longer than 1 seconds"):
        helper.call(helperwork.sleep, 30, timeout=1)
    assert helper.call(helperwork.sleep, 0) == "woke"


@pytest.mark.skipif(not os.path.exists("/proc/self/statm"), reason="memory is read from /proc")
def test_too_much_memory(on, monkeypatch):
    monkeypatch.setenv("HELPER_MEMORY_MB", "100")
    with pytest.raises(helper.HelperLost, match="more memory"):
        helper.call(helperwork.hog, 300, timeout=60)


def test_log_lines_and_messages_reach_the_copy(on, caplog):
    heard = []
    with caplog.at_level(logging.INFO):
        assert helper.call(helperwork.talk, 3, on_message=heard.append) == 3
    assert heard == [0, 1, 2]
    assert any(r.name == "iodocs.ocr" and "reading 3 pages" in r.getMessage() for r in caplog.records)


def test_only_module_level_functions(on):
    with pytest.raises(TypeError):
        helper.call(lambda: 1)


def test_off_runs_here(monkeypatch):
    monkeypatch.setenv("HELPER", "off")
    assert not helper.enabled()
    assert helper.call(helperwork.pid) == os.getpid()
    heard = []
    assert helper.call(helperwork.talk, 2, on_message=heard.append) == 2
    assert heard == [0, 1]


def test_idle_helpers_end(on, monkeypatch):
    helper.call(helperwork.pid)
    monkeypatch.setattr(helper, "IDLE_S", 0.0)
    helper.shutdown()
    assert helper.status()["running"] == 0


def test_call_or_gives_the_default_when_the_helper_is_lost(on):
    assert helper.call_or("none", helperwork.crash) == "none"
    assert helper.call_or("none", helperwork.add, 1, 2) == 3
    with pytest.raises(helperwork.Picky):  # an error of the function's own is not swallowed
        helper.call_or("none", helperwork.fail)


def test_lost_is_said_to_the_person_not_as_a_server_error(on):
    from iosuite_shared.errors import Invalid
    with pytest.raises(Invalid, match="could not be finished"):
        helper.call(helperwork.crash)


# ---- the heavy lane

NO_LIMITS = {"limit": None, "used": None, "free": None, "reserve": None, "ceiling": None}


@pytest.fixture
def lane():
    """A lane of its own for the test, with no memory limits applied, and its process ended afterwards."""
    one = helper.Heavy("iosuite_shared.tests.heavywork", lambda: dict(NO_LIMITS), name="test", what="the test's work")
    yield one
    one.release()


def test_the_heavy_lane_keeps_its_process_between_calls(lane):
    heard = []
    setup, there, arg = lane.call(heavywork.what, ("x",), setup={"n": 1}, on_message=heard.append)
    assert there != os.getpid() and arg == "x"
    assert setup == {"n": 1}            # it reached the helper's before_call, with the call
    assert heard == [("after", {"n": 1})]  # and after_call had the last word before the answer
    assert lane.call(heavywork.what, ("y",))[1] == there  # the same process serves the next call
    lane.release()
    assert lane.call(heavywork.what, ("z",))[1] != there  # and a new one once it has been let go


def test_a_note_reaches_the_call_while_it_runs(lane):
    out = {}
    t = threading.Thread(target=lambda: out.update(notes=lane.call(heavywork.until_told)))
    t.start()
    end = time.time() + 15
    while time.time() < end and not lane.running:
        time.sleep(0.02)
    lane.note("stop")
    t.join(20)
    assert out["notes"] == ["stop"]


def test_what_the_function_raised_is_raised_here_unless_the_lane_says_otherwise(lane):
    with pytest.raises(ValueError, match="no good"):
        lane.call(heavywork.boom)
    with pytest.raises(helper.HelperError, match="no good"):
        lane.call(heavywork.boom, failed_as=lambda text, _tb: helper.HelperError(text))


def test_a_process_over_its_ceiling_is_stopped_and_named(lane, monkeypatch):
    lane.budget = lambda: {**NO_LIMITS, "limit": 16_000 * helper.MB, "used": 0, "free": 16_000 * helper.MB, "ceiling": 150 * helper.MB}
    monkeypatch.setattr(helper, "CHECK_EVERY", 0.1)
    with pytest.raises(helper.HelperLost, match="more memory than the test's work may use"):
        lane.call(helperwork.hog, (400,))

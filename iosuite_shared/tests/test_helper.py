"""The helper process: work goes there and comes back; a crash, a timeout or too much memory there costs the call,
never the copy; with the helper off the work runs here."""
import logging
import os

import pytest

from iosuite_shared import helper
from iosuite_shared.tests import helperwork

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

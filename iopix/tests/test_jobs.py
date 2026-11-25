"""The background job queue: one job at a time, fixed order, resubmission
replaces a queued job, and the core budget stays within bounds."""
import os
import threading
import time

import pytest

from helpers import wait_for as _wait
from iopix import jobs
from iopix.tests.helpers import pixsetting


@pytest.fixture(autouse=True)
def idle_worker():
    """These tests time the one worker thread, so it starts idle: jobs queued by earlier tests (a library's scans, in
    the full suite on a real library) are dropped, and one still running is waited out."""
    with jobs._lock:
        jobs._queue.clear()
    assert _wait(lambda: jobs.status()["running"] is None, timeout=120), f"a job from an earlier test still runs: {jobs.status()['running']}"


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError):
        jobs.submit("not-a-job", lambda: None)


def test_jobs_run_one_at_a_time_in_order():
    log, active, overlap = [], [0], [False]
    gate = threading.Event()

    def job(name, hold=0.05):
        def run():
            active[0] += 1
            if active[0] > 1:
                overlap[0] = True
            gate.wait(2)
            time.sleep(hold)
            log.append(name)
            active[0] -= 1
        return run

    # submit in reverse priority while the worker is held on the first job
    jobs.submit("captions", job("captions"))
    _wait(lambda: jobs.status()["running"] == "captions")
    jobs.submit("vision", job("vision"))
    jobs.submit("thumbs", job("thumbs"))
    jobs.submit("pixels", job("pixels"))
    assert jobs.status()["queued"] == ["thumbs", "pixels", "vision"]
    gate.set()
    assert _wait(lambda: len(log) == 4)
    assert log == ["captions", "thumbs", "pixels", "vision"]
    assert overlap[0] is False


def test_resubmitting_a_queued_key_replaces_it():
    gate = threading.Event()
    seen = []
    jobs.submit("captions", lambda: gate.wait(2))
    _wait(lambda: jobs.status()["running"] == "captions")
    jobs.submit("vision", lambda: seen.append("first"))
    jobs.submit("vision", lambda: seen.append("second"))
    assert jobs.status()["queued"].count("vision") == 1
    gate.set()
    assert _wait(lambda: jobs.status()["running"] is None and not jobs.status()["queued"])
    assert seen == ["second"]


def test_a_failing_job_does_not_stop_the_worker():
    done = []
    jobs.submit("pixels", lambda: 1 / 0)
    jobs.submit("vision", lambda: done.append(1))
    assert _wait(lambda: done == [1])


def test_while_the_app_runs_the_queue_is_one_of_the_copy_s_jobs(client, monkeypatch):
    """The app's start attached the queue: a pass is made by the copy's job runner (Settings › Servers › Jobs says
    what it ran), not by a thread of the queue's own; once the app has stopped (detach) the queue's thread makes the
    passes again."""
    from iosuite_shared import db as shared_db
    monkeypatch.setattr(jobs, "GRACE", 0.1)
    assert jobs._job is not None and jobs._job.every_s == 0 and not jobs._job.heavy
    done, threads = [], []

    def work(name):
        return lambda: (done.append(name), threads.append(threading.current_thread().name))

    def row():
        return shared_db.one("SELECT * FROM ios_jobs WHERE app = %s AND name = 'analysis'", (jobs.config.APP,)) or {}

    jobs.submit("pixels", work("pixels"))
    jobs.submit("thumbs", work("thumbs"))
    assert _wait(lambda: len(done) == 2 and jobs.status()["running"] is None)
    assert done == ["thumbs", "pixels"] and "jobs" not in threads, (done, threads)
    assert _wait(lambda: row().get("state") == "ok" and row().get("message") == "thumbs, pixels"), row()
    assert row()["every_s"] == 0 and not row()["heavy"] and row()["next_at"] is None
    jobs.detach()
    try:
        jobs.submit("vision", work("vision"))
        assert _wait(lambda: done[-1] == "vision" and jobs.status()["running"] is None)
        assert threads[-1] == "jobs"
    finally:
        client.portal.call(jobs.attach)  # as the app's start does, on the copy's loop
    jobs.submit("captions", work("captions"))
    assert _wait(lambda: done[-1] == "captions" and jobs.status()["running"] is None)
    assert threads[-1] != "jobs"


def test_thread_budget_is_bounded(monkeypatch):
    n = os.cpu_count() or 4
    assert 1 <= jobs.threads() <= max(1, n - 1)
    pixsetting("BG_THREADS", "999")
    assert jobs.threads() == max(1, n - 1)
    pixsetting("BG_THREADS", "0")
    assert jobs.threads() == max(1, min(jobs.config.BG_THREADS, n - 1))


def test_a_burst_of_submissions_is_picked_in_order(monkeypatch):
    """Startup submits several jobs within a second; the worker must not grab the first one
    that arrives (embeddings) ahead of thumbnails."""
    monkeypatch.setattr(jobs, "GRACE", 0.5)
    order = []
    jobs.submit("embeddings", lambda: order.append("embeddings"))
    time.sleep(0.1)
    jobs.submit("thumbs", lambda: order.append("thumbs"))
    jobs.submit("pixels", lambda: order.append("pixels"))
    assert _wait(lambda: len(order) == 3, timeout=5)
    assert order == ["thumbs", "pixels", "embeddings"]


def test_scan_job_start_rule_and_reset(monkeypatch):
    """The shared scan scaffolding (iopix/ai/scanjob.py): a start whose to-do is already inside the running job's is
    ignored, one with something new cancels the run, and a reset cancels it and empties the job's tables."""
    from iopix.ai.scanjob import ScanJob
    from iopix.data import appdb
    monkeypatch.setattr(jobs.config, "ANALYSIS", True)  # the tests run with analysis off; start() refuses otherwise
    monkeypatch.setattr(jobs, "GRACE", 0.2)
    # with analysis on, a rebuild by an earlier test's threads would queue the real scans (thumbs first by ORDER) on
    # the whole library ahead of this one: only this test's job reaches the worker
    submit = jobs.submit
    monkeypatch.setattr(jobs, "submit", lambda key, fn: submit(key, fn) if key == "captions" else None)
    gate = threading.Event()
    runs, done = [], []

    def work(gen, todo):
        runs.append(gen)
        gate.wait(2)
        if not job.progress.cancelled(gen):
            done.append([p["id"] for p in todo])

    job = ScanJob("captions", lambda con, photos: [p for p in photos if p["id"] not in done_ids], work)
    done_ids = set()
    photos = [{"id": 1}, {"id": 2}]
    job.start(photos)
    assert _wait(lambda: job.progress["running"] and job.progress["total"] == 2)
    job.start(photos)  # nothing new: no second run, the first one keeps its generation
    job.start([photos[0]])
    assert len(runs) == 1 and not job.progress.cancelled(runs[0])
    job.start(photos + [{"id": 3}])  # something new: the running job is cancelled and a new run takes over
    assert job.progress.cancelled(runs[0])
    gate.set()
    assert _wait(lambda: len(runs) == 2 and jobs.status()["running"] is None)
    assert done == [[1, 2, 3]]
    gate.clear()
    job.start(photos + [{"id": 4}])
    assert _wait(lambda: len(runs) == 3)
    job.reset()  # cancels the run (its results are not recorded) and leaves nothing in pix_ai_scans for the job
    assert job.progress.cancelled(runs[2]) and not job.progress["running"]
    gate.set()
    assert _wait(lambda: jobs.status()["running"] is None)
    assert done == [[1, 2, 3]]
    with appdb.reader() as con:
        assert con.execute("SELECT count(*) FROM pix_ai_scans WHERE job = 'captions'").fetchone()[0] == 0
    jobs._progress.pop("captions", None)  # the test's own Progress leaves the status registry as it found it

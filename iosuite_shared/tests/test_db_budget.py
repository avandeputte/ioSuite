"""The copy's one allowance of database connections (iosuite_shared.db.Budget): however many pools the apps keep and
however many threads ask at once, no more than the limit is open; a request waits for one, an idle one elsewhere is
closed to make room, and a thread that holds one already is never made to wait for its second."""
import gc
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import db
from iosuite_shared.fastapi import Auth


class Con:
    """A connection as the pool sees one."""
    made = 0

    def __init__(self):
        Con.made += 1
        self.open, self._sock = True, None

    def get_autocommit(self):
        return True

    def ping(self, reconnect=False):
        pass

    def begin(self):
        pass

    commit = rollback = begin

    def close(self):
        self.open = False


@pytest.fixture
def budget(monkeypatch):
    b = db.Budget(limit=2)
    monkeypatch.setattr(db, "budget", b)
    Con.made = 0
    return b


def test_a_copy_never_opens_more_than_its_limit(budget):
    pool = db.Pool(Con, size=8)
    most, now, lock, done = [0], [0], threading.Lock(), []

    def work():
        with pool.auto():
            with lock:
                now[0] += 1
                most[0] = max(most[0], now[0])
            time.sleep(0.05)
            with lock:
                now[0] -= 1
        done.append(1)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(done) == 8 and most[0] == 2
    s = budget.status()
    assert s["open"] == 2 and s["waited"] >= 1 and s["refused"] == 0
    assert Con.made == 2, "the waiting threads took the ones that came back; none was opened beyond the limit"


def test_an_idle_connection_elsewhere_is_closed_to_make_room(budget):
    a, b = db.Pool(Con), db.Pool(Con)
    with a.auto() as one:
        pass

    def second():
        with a.auto():
            time.sleep(0.05)

    t = threading.Thread(target=second)
    with a.auto():
        t.start()
        time.sleep(0.02)
    t.join(5)
    assert budget.status()["open"] == 2 and a.idle() == 2  # the copy is at its limit, all of it kept by one app
    with b.auto() as other:
        assert other is not one
    s = budget.status()
    assert s["open"] == 2 and s["shed"] == 1 and a.idle() == 1 and b.idle() == 1
    assert not one.open, "the one kept unused the longest was the one closed"


def test_a_thread_that_holds_one_is_never_made_to_wait_for_its_second(budget):
    budget._limit = 1
    app_pool, shared = db.Pool(Con), db.Pool(Con)
    began = time.monotonic()
    with app_pool.tx():        # an app's transaction …
        with shared.auto():    # … that reads a setting from the Shared ioSuite database
            assert budget.status()["open"] == 2
    assert time.monotonic() - began < 1 and budget.status()["over"] == 1


def test_all_in_use_for_too_long_is_busy_and_answered_503(budget, monkeypatch):
    budget._limit = 1
    monkeypatch.setattr(db.Budget, "WAIT_S", 0.3)
    pool, other = db.Pool(Con), db.Pool(Con)
    held, go = threading.Event(), threading.Event()

    def holder():
        with pool.auto():
            held.set()
            go.wait(10)

    t = threading.Thread(target=holder)
    t.start()
    held.wait(5)
    try:
        with pytest.raises(db.Busy):
            other.borrow()
        assert budget.status()["refused"] == 1
        auth = Auth("iocontact", register=False)
        app = FastAPI()
        auth.install(app)

        @app.get("/api/x", dependencies=[auth.access.public])
        def x():
            with other.auto():
                return {}

        r = TestClient(app).get("/api/x")
        assert r.status_code == 503 and r.headers["retry-after"] == "2" and "busy" in r.json()["detail"]
    finally:
        go.set()
        t.join(5)
    with other.auto():  # and a moment later it works
        pass


def test_a_connection_that_was_dropped_gives_its_room_back(budget):
    pool = db.Pool(Con)
    con = pool.borrow()
    assert budget.status()["open"] == 1
    del con            # never given back (a caller that forgot to close)
    gc.collect()
    assert budget.status()["open"] == 0


def test_what_was_kept_unused_is_closed_by_the_housekeeping(budget):
    pool = db.Pool(Con)
    with pool.auto() as con:
        pass
    assert pool.trim() == 0 and pool.idle() == 1  # used a moment ago: kept
    assert pool.trim(older_than_s=0) == 1 and pool.idle() == 0 and not con.open and budget.status()["open"] == 0


def test_the_limit_is_the_machines(monkeypatch):
    monkeypatch.setenv("DB_CONNECTIONS", "25")
    from iosuite_shared import config
    config._read()
    try:
        assert db.Budget().limit == 25
    finally:
        monkeypatch.delenv("DB_CONNECTIONS")
        config._read()
    assert db.Budget().limit == 60

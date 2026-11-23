"""The copy's one job runner (iosuite_shared.jobs): every app's chores, syncs and reminders in one loop, each run
written down so that Settings › Servers › Jobs can show it, Run now across copies, and heavy jobs waiting for each
other instead of piling up."""
import asyncio
import time

from iosuite_shared import chores, db, jobs


async def _until(test, timeout=4.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if test():
            return True
        await asyncio.sleep(step)
    return False


def test_a_job_runs_on_its_own_clock_and_its_row_says_how_it_went():
    async def go():
        ran = []
        job = chores.start(lambda: ran.append(1) or "3 reminders sent", every_s=0.2, first_s=0, app="iotest",
                           name="notifications", title="The morning's reminders")
        try:
            assert await _until(lambda: len(ran) >= 2), "the job did not run twice"
            assert await _until(lambda: (db.one("SELECT * FROM ios_jobs WHERE app = 'iotest'") or {}).get("state") == "ok")
            r = db.one("SELECT * FROM ios_jobs WHERE app = 'iotest' AND name = 'notifications'")
            assert r["title"] == "The morning's reminders" and r["every_s"] == 0 and r["copy"]
            assert r["message"] == "3 reminders sent" and r["runs"] >= 2 and r["failures"] == 0 and r["took_ms"] is not None
            one = [i for i in jobs.rows() if i["app"] == "iotest"][0]
            assert one["title"] == "The morning's reminders" and one["state"] == "ok" and one["message"] == "3 reminders sent"
        finally:
            job.cancel()


    asyncio.run(go())

def test_a_job_that_fails_is_counted_and_tried_again():
    async def go():
        tries = []

        def boom():
            tries.append(1)
            raise ValueError("the server said no")

        job = chores.start(boom, every_s=0.1, first_s=0, app="iotest", name="sync")
        try:
            assert await _until(lambda: len(tries) >= 2), "a failed job was not tried again"
            assert await _until(lambda: (db.one("SELECT * FROM ios_jobs WHERE name = 'sync'") or {}).get("state") == "failed")
            r = db.one("SELECT * FROM ios_jobs WHERE app = 'iotest' AND name = 'sync'")
            assert r["message"] == "ValueError: the server said no" and r["failures"] >= 2
            assert jobs.summary()["failed"] == 1
        finally:
            job.cancel()


    asyncio.run(go())

def test_run_now_reaches_the_copy_that_owns_the_job():
    async def go():
        """A suite admin presses Run now; the flag on the row is what the owning copy picks up, so the screen works the
        same whether the job's app shares this copy or sits on another server."""
        ran = []
        job = chores.start(lambda: ran.append(time.time()), every_s=3600, first_s=3600, app="iotest", name="holidays")
        try:
            assert await _until(lambda: db.one("SELECT * FROM ios_jobs WHERE name = 'holidays'") is not None)
            assert ran == [], "a job an hour away should not have run yet"
            assert jobs.run_now("iotest", "holidays", by="alex") is True
            assert await _until(lambda: len(ran) == 1), "Run now did not reach the job"
            assert jobs.run_now("iotest", "nothing like it") is False
            await asyncio.sleep(jobs.TICK_S * 2)
            assert len(ran) == 1, "one press is one run"
        finally:
            job.cancel()


    asyncio.run(go())

def test_heavy_jobs_wait_for_each_other_but_the_light_ones_do_not():
    async def go():
        """Two heavy jobs in one copy never run at the same moment: a scan, an index and a backup take their turn."""
        together, now = [], []

        def heavy():
            now.append(1)
            together.append(len(now))
            time.sleep(0.3)
            now.pop()

        a = chores.start(heavy, every_s=3600, first_s=0, app="iotest", name="scan", heavy=True)
        b = chores.start(heavy, every_s=3600, first_s=0, app="iotest2", name="index", heavy=True)
        try:
            assert await _until(lambda: len(together) >= 2, timeout=6)
            assert max(together) == 1, f"two heavy jobs ran at once: {together}"
        finally:
            a.cancel()
            b.cancel()


    asyncio.run(go())

def test_a_job_is_not_started_again_while_its_last_run_is_still_going():
    async def go():
        inside = []

        def slow():
            inside.append(1)
            time.sleep(0.6)
            inside.pop()

        job = chores.start(slow, every_s=0.05, first_s=0, app="iotest", name="long one")
        try:
            await asyncio.sleep(0.4)
            assert len(inside) == 1, "the job piled up on itself"
        finally:
            job.cancel()


    asyncio.run(go())

def test_a_cancelled_job_stops_but_its_row_stays():
    async def go():
        ran = []
        job = chores.start(lambda: ran.append(1), every_s=0.1, first_s=0, app="iotest", name="purge")
        assert await _until(lambda: ran != [])
        job.cancel()
        was = len(ran)
        await asyncio.sleep(jobs.TICK_S + 0.3)
        assert len(ran) == was, "a cancelled job went on running"
        assert db.one("SELECT * FROM ios_jobs WHERE name = 'purge'"), "the row is what the screen reads: it stays"
    asyncio.run(go())



def test_rows_of_jobs_nothing_registers_any_more_are_forgotten():
    db.ex("INSERT INTO ios_jobs (app, name, copy, title, every_s, seen_at) VALUES (%s, %s, %s, %s, %s, %s)",
          ("iogone", "old", "server", "A job of an app that is gone", 60, int(time.time() - 30 * 86400)))
    db.ex("INSERT INTO ios_jobs (app, name, copy, title, every_s, seen_at) VALUES (%s, %s, %s, %s, %s, %s)",
          ("iotest", "fresh", "server", "A job that still registers", 60, int(time.time())))
    jobs.forget_old()
    left = {r["name"] for r in db.q("SELECT name FROM ios_jobs")}
    assert left == {"fresh"}

"""One job runner per copy: every app's chores, syncs and reminders in one place, on one screen.

Each app says what it wants run and how often, in its lifespan (iosuite_shared.chores.start, which is this module's
front door, so an app's code reads the same as before):

    chores.start(notify.run, every_s=60, first_s=20, name="notifications", app=config.APP)
    chores.start(scan.all, every_s=3600, name="file scan", app=config.APP, heavy=True)
    look = chores.start(timers.tick, every_s=2, name="timers", app=config.APP, quiet=True)

One loop in the copy runs them all, instead of a timer of its own per job, and writes every run into the Shared ioSuite
database (`ios_jobs`: one row per job, with the copy that runs it, when it last ran, how long it took and what it
said). Settings › Servers › Jobs shows those rows from every copy of the suite, with **Run now** per job, so the
screen is the same whether the apps share a copy or sit on different servers: a Run now is a flag on the row, and the
copy that owns the job picks it up within a few seconds. Nothing calls another copy over the network for this.

A job that is a look every few seconds or every minute (is a timer done, is a feed due, is a backup scheduled for
this minute) is `quiet=True`: its row is written once a minute, and at once when a look failed or said something,
not at every look, so the screen has it without the database being written to all day. `job.soon()` has a job run
now instead of at its next turn (somebody asked for a scan; an edit wants the index brought up to date).

Two jobs of the same name in the same app are one job. A run that is still going when the next one falls due is not
started again, and `heavy=True` jobs wait for each other, so a scan, an index and a backup never pile up in one copy
at the same moment. A run that raises is logged, counted and shown on the screen; the next run still happens.
"""
import asyncio
import logging
import time

from starlette.concurrency import run_in_threadpool

from iosuite_shared import db

log = logging.getLogger("iosuite_shared.jobs")

TICK_S = 2.0        # how often the loop looks for a job that is due or asked for
HEAVY_AT_ONCE = 1   # heavy jobs that may run together in one copy
ALIVE_S = 120       # a row not touched for this long: that copy is not running the job now
KEEP_S = 7 * 86400  # a row of a job nothing registers any more is forgotten after a week
QUIET_S = 60        # how often the row of a quiet job is written while its looks find nothing to say


def copy_name() -> str:
    """The name of this copy, the same one the Logs and Updates screens use (iosuite_shared.suite.copy_name): the
    machine's name, with the port of its pages beside it when two copies share a machine."""
    from iosuite_shared import suite
    return suite.copy_name()


class Job:
    """One registered job: what to run, how often, and the row it keeps."""

    def __init__(self, app: str, name: str, fn, every_s: float, first_s: float, heavy: bool, title: str, quiet: bool = False):
        self.app, self.name, self.fn = app, name, fn
        self.every_s, self.heavy, self.title, self.quiet = float(every_s), bool(heavy), title or name, bool(quiet)
        self.next_at = time.time() + float(first_s)
        self.running = False
        self.cancelled = False
        self.again = False     # soon() was called while it ran: one more run right after
        self.wrote_at = 0.0    # when a quiet job's row was last written, and the runs since
        self.unwritten = 0

    def soon(self) -> None:
        """Run now rather than at the next turn; from any thread. Asked while it runs, it runs once more right after,
        so what was changed during the run is seen."""
        if self.cancelled:
            return
        self.again = self.running
        self.next_at = 0.0
        _runner.wake()

    def cancel(self) -> None:
        """Stop running it (the app is shutting down). The row stays, so the screen still says when it last ran."""
        self.cancelled = True
        _runner.forget(self)

    def __repr__(self) -> str:
        return f"<Job {self.app}/{self.name}>"


class Runner:
    """The copy's one loop. Started by the first job that registers; stops when the loop's task is cancelled."""

    def __init__(self):
        self.jobs: dict[tuple, Job] = {}
        self._task: asyncio.Task | None = None
        self._loop = None
        self._heavy: asyncio.Semaphore | None = None
        self._wake: asyncio.Event | None = None

    def add(self, job: Job) -> Job:
        old = self.jobs.get((job.app, job.name))
        if old is not None:
            old.cancelled = True
        self.jobs[(job.app, job.name)] = job
        _declare(job)
        self._ensure()
        if self._wake is not None:
            self._wake.set()   # a job that starts at once does not wait for the round the loop is sleeping through
        return job

    def forget(self, job: Job) -> None:
        if self.jobs.get((job.app, job.name)) is job:
            self.jobs.pop((job.app, job.name), None)

    def wake(self) -> None:
        """Have the loop look now (a job asked to run soon), from whichever thread."""
        loop, wake = self._loop, self._wake
        if loop is None or wake is None:
            return
        try:
            loop.call_soon_threadsafe(wake.set)
        except RuntimeError:  # the loop has closed: nothing runs any more
            pass

    def _ensure(self) -> None:
        """One loop per copy, made by the first job that registers. The loop it belongs to is remembered too: a
        process that starts a second event loop (each of the suite's tests does) gets a runner on that loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # no loop (a script, or a call outside one): nothing runs until a loop is there
            return
        if self._task is not None and self._loop is loop and not self._task.done():
            return
        self._loop, self._heavy, self._wake = loop, asyncio.Semaphore(HEAVY_AT_ONCE), asyncio.Event()
        self._task = loop.create_task(self._round(), name="jobs")

    async def _round(self) -> None:
        """Wake when the next job is due, and look at the rows for a Run now every TICK_S at most: a job that runs
        every few seconds is on time, and the database is asked twice a minute however many jobs the copy has."""
        polled = 0.0
        while True:
            try:
                polled = await self._tick(polled)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the runner never takes the copy down
                log.exception("the job runner's round failed (it goes on)")
                polled = time.time()
            try:  # until the next job is due, or until a run that was going has finished
                await asyncio.wait_for(self._wake.wait(), timeout=self._sleep_for())
            except (TimeoutError, asyncio.TimeoutError):
                pass
            self._wake.clear()

    def _sleep_for(self) -> float:
        waiting = [j.next_at for j in self.jobs.values() if not (j.running or j.cancelled)]
        return max(0.02, min(TICK_S, min(waiting) - time.time())) if waiting else TICK_S

    async def _tick(self, polled: float) -> float:
        now = time.time()
        asked = _asked(list(self.jobs)) if now - polled >= TICK_S else {}
        if asked or now - polled >= TICK_S:
            polled = now
        for key, job in list(self.jobs.items()):
            if job.running or job.cancelled:
                continue
            by = asked.get(key)
            if by is None and job.next_at > now:
                continue
            job.running = True
            asyncio.get_running_loop().create_task(self._run(job, by), name=f"job:{job.app}/{job.name}")
        return polled

    async def _run(self, job: Job, by: str | None) -> None:
        """One run, in a thread (the jobs are blocking), while the row says it is running."""
        try:
            if job.heavy:
                async with self._heavy:
                    await self._once(job, by)
            else:
                await self._once(job, by)
        finally:
            job.running = False
            job.next_at = 0.0 if job.again else time.time() + job.every_s
            job.again = False
            if self._wake is not None:
                self._wake.set()

    async def _once(self, job: Job, by: str | None) -> None:
        started = time.time()
        if not job.quiet or by is not None:
            _began(job, by)
        try:
            out = await run_in_threadpool(job.fn)
            said = _said(out)
            job.unwritten += 1
            if not job.quiet or said or by is not None or started - job.wrote_at >= QUIET_S:
                _ended(job, started, "ok", said)
        except asyncio.CancelledError:
            _ended(job, started, "", "")
            raise
        except Exception as x:  # noqa: BLE001 - a job that fails is a line on the screen, not a stopped app
            log.exception("the job %s of %s failed (it is tried again at its next turn)", job.name, job.app)
            job.unwritten += 1
            _ended(job, started, "failed", f"{type(x).__name__}: {x}")


_runner = Runner()


def register(fn, every_s: float = 86400, name: str = None, first_s: float = 5, app: str = "", heavy: bool = False,
             title: str = "", quiet: bool = False) -> Job:
    """Have `fn` run `first_s` seconds from now and then every `every_s` seconds, as this copy's job runner's turn
    comes. `app` is the app it belongs to (""; the copy itself, for the suite's own jobs), `heavy` makes it wait for
    the copy's other heavy jobs, `quiet` is for a look every few seconds (its row is written once a minute). Returns
    a handle with .cancel(), to call in the app's shutdown, and .soon(), to have it run now."""
    name = (name or getattr(fn, "__name__", "job"))[:64]
    return _runner.add(Job(app or "", name, fn, every_s, first_s, heavy, title or name, quiet))


def run_now(app: str, name: str, by: str = "") -> bool:
    """Ask for a job's next run to be now. The copy that runs it picks the flag up within a few seconds, wherever it
    is; False when no such job is registered anywhere."""
    if not db.one("SELECT app FROM ios_jobs WHERE app = %s AND name = %s", (app, name)):
        return False
    db.ex("UPDATE ios_jobs SET run_now = 1, requested_by = %s WHERE app = %s AND name = %s",
          (by[:64] or None, app, name))
    return True


def rows() -> list:
    """Every job the suite knows of, newest run first within an app: what the screen shows."""
    out = []
    for r in db.q("SELECT * FROM ios_jobs ORDER BY app, name"):
        out.append({
            "app": r["app"], "name": r["name"], "title": r["title"] or r["name"], "copy": r["copy"],
            "every": int(r["every_s"] or 0), "heavy": bool(r["heavy"]),
            "state": "running" if r["state"] == "running" and _fresh(r) else ("" if r["state"] == "running" else r["state"] or ""),
            "startedAt": r["started_at"], "finishedAt": r["finished_at"], "tookMs": r["took_ms"],
            "message": r["message"] or "", "runs": int(r["runs"] or 0), "failures": int(r["failures"] or 0),
            "pending": bool(r["run_now"]), "nextAt": r["next_at"], "serving": _fresh(r, ALIVE_S),
        })
    return out


def summary() -> dict:
    """The screen's answer: every job, and the counts the section's heading says."""
    items = rows()
    return {"items": items, "failed": sum(1 for i in items if i["state"] == "failed"),
            "running": sum(1 for i in items if i["state"] == "running"), "copies": sorted({i["copy"] for i in items if i["copy"]})}


def forget_old(older_than_s: float = KEEP_S) -> int:
    """Drop the rows of jobs no copy has registered for a week (an app that was removed, a job that was renamed)."""
    return db.ex("DELETE FROM ios_jobs WHERE seen_at < %s", (int(time.time() - older_than_s),))


# ---- the rows
def _said(out) -> str:
    """What a job's return value says on the screen: a short line, or nothing."""
    if out is None or out is True or out is False:
        return ""
    if isinstance(out, (int, float)):
        return "" if not out else str(out)
    return str(out)[:300]


def _fresh(row, within_s: float = ALIVE_S) -> bool:
    return bool(row.get("seen_at")) and row["seen_at"] > time.time() - within_s


def _declare(job: Job) -> None:
    """The row for a job this copy has just taken on, with what it is and who runs it."""
    _write("INSERT INTO ios_jobs (app, name, copy, title, every_s, heavy, seen_at, next_at) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
           "ON DUPLICATE KEY UPDATE copy = VALUES(copy), title = VALUES(title), every_s = VALUES(every_s), "
           "heavy = VALUES(heavy), seen_at = VALUES(seen_at), next_at = VALUES(next_at), "
           "state = IF(state = 'running', '', state)",
           (job.app, job.name, copy_name(), job.title[:120], int(job.every_s), 1 if job.heavy else 0,
            int(time.time()), int(job.next_at)))


def _asked(keys: list) -> dict:
    """{(app, name): who asked} for the jobs of this copy somebody pressed Run now on, the flag taken off the row so
    that one press is one run."""
    if not keys:
        return {}
    try:
        where = " OR ".join(["(app = %s AND name = %s)"] * len(keys))
        args = tuple(x for k in keys for x in k)
        got = db.q(f"SELECT app, name, requested_by FROM ios_jobs WHERE run_now = 1 AND ({where})", args)
        if not got:
            return {}
        db.ex(f"UPDATE ios_jobs SET run_now = 0 WHERE run_now = 1 AND ({where})", args)
        return {(r["app"], r["name"]): (r["requested_by"] or "") for r in got}
    except Exception:  # noqa: BLE001 - the database is away: the jobs still run on their own clock
        return {}


def _began(job: Job, by: str | None) -> None:
    _write("UPDATE ios_jobs SET state = 'running', started_at = %s, seen_at = %s, copy = %s, "
           "requested_by = %s WHERE app = %s AND name = %s",
           (int(time.time()), int(time.time()), copy_name(), by or None, job.app, job.name))


def _ended(job: Job, started: float, state: str, message: str) -> None:
    now = time.time()
    runs, job.unwritten, job.wrote_at = max(job.unwritten, 1), 0, now   # a quiet job's looks since its row was last written
    # when it began, and where, are written here too: a quiet job's row is not written as it begins
    _write("UPDATE ios_jobs SET state = %s, started_at = %s, finished_at = %s, took_ms = %s, message = %s, seen_at = %s, "
           "copy = %s, runs = runs + %s, failures = failures + %s, next_at = %s WHERE app = %s AND name = %s",
           (state, int(started), int(now), int((now - started) * 1000), message[:300] or None, int(now), copy_name(), runs,
            1 if state == "failed" else 0, int(now + job.every_s), job.app, job.name))


def _write(sql: str, args: tuple) -> None:
    """The rows are what the screen reads, never what a job depends on: a database that is away never stops a run."""
    try:
        db.ex(sql, args)
    except Exception:  # noqa: BLE001
        log.debug("the job row could not be written", exc_info=True)

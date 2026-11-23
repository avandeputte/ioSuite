"""Runs (backups and restores), the queue that carries them out one at a time, and the scheduler that starts jobs on
their schedule. Every run and its log are kept in bkp_runs.

Everything runs one at a time, in order: two dumps of the same server at once would only compete for its disks, and
a restore must never overlap a backup of the database it is writing. The runs and the scheduler are two of the copy's
jobs (iosuite_shared.jobs, Settings › Servers › Jobs): the runs as a heavy one, so a backup does not start while
another heavy job of the copy is at work (ioPix scanning its folders); the stored setting BACKGROUND=0 leaves both
out.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import queue
import threading
import time
import traceback

from iobackup import config, db, engine, model, schedule
from iobackup.destinations import open_destination, prune

log = logging.getLogger("iobackup")

KEEP_RUNS = 500          # the history keeps this many runs
MAX_LOG_LINES = 5000     # lines kept per run; after that only errors and the outcome

_queue: queue.Queue = queue.Queue()
_cancel: dict[int, threading.Event] = {}
_lines: dict[int, int] = {}
_unsaved: dict[int, dict] = {}  # how a run ended, while ioBackup's own database could not take it (saved at the next chance)
_started = False
_jobs: dict = {"runs": None, "schedule": None}   # the copy's two jobs while the app runs (start())


def _now() -> _dt.datetime:
    return _dt.datetime.now().replace(microsecond=0)


def iso(t) -> str | None:
    """A stored local time as ISO 8601 with the server's offset."""
    return t.astimezone().isoformat(timespec="seconds") if t else None


def _public(r: dict, with_log: bool = False) -> dict:
    lines = (r.get("log") or "").splitlines()
    out = {"id": r["id"], "kind": r["kind"], "title": r["title"], "jobId": r["job_id"], "trigger": r["trigger_kind"],
           "user": r["user_name"], "status": r["status"], "queued": iso(r["queued_at"]), "started": iso(r["started_at"]),
           "finished": iso(r["finished_at"]), "result": json.loads(r["result"]) if r.get("result") else None,
           "last": lines[-1] if lines else ""}
    if with_log:
        out["log"] = lines
    return out


def runs(limit: int = 100, job_id: int | None = None) -> list[dict]:
    limit = max(1, min(int(limit or 100), KEEP_RUNS))
    cols = "id, kind, title, job_id, trigger_kind, user_name, status, queued_at, started_at, finished_at, result, " \
           "SUBSTRING_INDEX(TRIM(TRAILING '\\n' FROM log), '\\n', -1) AS log"
    if job_id:
        rows = db.q(f"SELECT {cols} FROM bkp_runs WHERE job_id = %s ORDER BY id DESC LIMIT %s", (job_id, limit))
    else:
        rows = db.q(f"SELECT {cols} FROM bkp_runs ORDER BY id DESC LIMIT %s", (limit,))
    return [_public(r) for r in rows]


def run(rid: int) -> dict:
    r = db.one("SELECT * FROM bkp_runs WHERE id = %s", (rid,))
    if not r:
        raise model.NotFound("No such run")
    return _public(r, with_log=True)


def last_runs() -> dict[int, dict]:
    """Each job's newest finished run."""
    rows = db.q("SELECT r.id, r.job_id, r.status, r.finished_at, r.result FROM bkp_runs r JOIN "
                "(SELECT job_id, MAX(id) AS id FROM bkp_runs WHERE job_id IS NOT NULL AND status NOT IN ('queued', 'running') "
                "GROUP BY job_id) m ON m.id = r.id")
    return {r["job_id"]: {"id": r["id"], "status": r["status"], "finished": iso(r["finished_at"]),
                          "result": json.loads(r["result"]) if r["result"] else None} for r in rows}


def pending_jobs() -> set[int]:
    return {r["job_id"] for r in db.q("SELECT DISTINCT job_id FROM bkp_runs WHERE status IN ('queued', 'running') AND job_id IS NOT NULL")}


def busy() -> bool:
    return bool(db.one("SELECT 1 AS x FROM bkp_runs WHERE status IN ('queued', 'running') LIMIT 1"))


def _update(rid: int, **fields) -> None:
    if "result" in fields:
        fields["result"] = json.dumps(fields["result"]) if fields["result"] is not None else None
    cols = {"started": "started_at", "finished": "finished_at"}
    sets = ", ".join(f"{cols.get(k, k)} = %s" for k in fields)
    db.ex(f"UPDATE bkp_runs SET {sets} WHERE id = %s", (*fields.values(), rid))


def _logger(rid: int):
    def emit(msg: str) -> None:
        n = _lines.get(rid, 0) + 1
        _lines[rid] = n
        log.info("[run %s] %s", rid, msg)
        if n > MAX_LOG_LINES and not any(w in msg for w in ("FAILED", "error", "Finished", "Cancelled")):
            if n == MAX_LOG_LINES + 1:
                msg = "… (the rest of the log is not kept; errors and the outcome still are)"
            else:
                return
        line = "%s %s\n" % (_dt.datetime.now().strftime("%H:%M:%S"), msg)
        try:
            db.ex("UPDATE bkp_runs SET log = CONCAT(log, %s) WHERE id = %s", (line, rid))
        except Exception:  # noqa: BLE001 - ioBackup's own database away: the backup goes on, the line is in the service log
            log.warning("[run %s] the log line could not be saved", rid)
    return emit


def _finish(rid: int, tries: int = 6, wait: float = 2.0, **fields) -> None:
    """Save how a run ended. ioBackup's own database may be the server that just went away (it is often one of the
    servers backed up): try a few times, and if it is still away keep the outcome to save at the next chance, so the
    run never stays "running" and its job never stays blocked."""
    for i in range(tries):
        try:
            _update(rid, **fields)
            _unsaved.pop(rid, None)
            return
        except Exception:  # noqa: BLE001
            if i + 1 < tries:
                time.sleep(wait * (2 ** i))
    log.warning("run %s: its outcome (%s) could not be saved yet; it will be when the database answers", rid, fields.get("status"))
    _unsaved[rid] = fields


def save_unsaved() -> None:
    """Save the outcomes kept by _finish (the worker and the scheduler call it)."""
    for rid, fields in list(_unsaved.items()):
        try:
            _update(rid, **fields)
            _unsaved.pop(rid, None)
        except Exception:  # noqa: BLE001 - still away
            return


def enqueue(kind: str, title: str, payload: dict, job_id: int | None = None, trigger: str = "manual", by: str | None = None) -> int:
    rid = db.ex("INSERT INTO bkp_runs (kind, title, job_id, trigger_kind, user_name, status, queued_at, payload, log) "
                "VALUES (%s, %s, %s, %s, %s, 'queued', %s, %s, '')", (kind, title[:255], job_id, trigger, by, _now(), json.dumps(payload)))
    old = db.one("SELECT id FROM bkp_runs ORDER BY id DESC LIMIT 1 OFFSET %s", (KEEP_RUNS,))
    if old:
        db.ex("DELETE FROM bkp_runs WHERE id <= %s AND status NOT IN ('queued', 'running')", (old["id"],))
    _cancel[rid] = threading.Event()
    _queue.put(rid)
    if _jobs["runs"] is not None:
        _jobs["runs"].soon()   # carried out now, not at the job's next look
    return rid


def cancel(rid: int) -> bool:
    r = run(rid)
    ev = _cancel.get(rid)
    if r["status"] not in ("queued", "running") or ev is None:
        return False
    ev.set()
    if r["status"] == "queued":
        _update(rid, status="cancelled", finished=_now())
    return True


# ---------------------------------------------------------------- what a run does

def _do_backup(p: dict, emit, ev) -> dict:
    job = model.job(p["job_id"])
    server, dest = model.server(job["serverId"]), model.destination(job["destinationId"])
    label = engine.slug(job["name"])
    emit("Backing up %s to %s" % (server["name"], dest["name"]))
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    tar, manifest = engine.run_backup(
        server, job["databases"], include_users=job["includeUsers"], workdir=str(config.WORK_DIR), label=label,
        lock_all=job["lockAll"], desync=job["desync"], compress_level=int(job["compressLevel"] or 6),
        log=emit, cancel=ev, source_name=server["name"], files=job["files"])
    try:
        size = os.path.getsize(tar)
        d = open_destination(dest)
        emit("Stored as %s" % d.store(tar, emit, ev))
    finally:
        if os.path.exists(tar):
            os.unlink(tar)
    removed = []
    if job["keep"]:
        try:
            removed = prune(d, label, job["keep"], emit)
            if not removed:
                emit("Retention: %d or fewer backups kept, nothing to remove" % job["keep"])
        except Exception as e:  # a failed clean-up does not make a good backup a failed one
            emit("warning: the retention clean-up failed: %s" % e)
    return {"file": os.path.basename(tar), "size": size, "destinationId": dest["id"],
            "databases": [x["name"] for x in manifest["databases"]], "pruned": removed}


def _do_restore(p: dict, emit, ev) -> dict:
    dest, server = model.destination(p["destination_id"]), model.server(p["server_id"])
    d = open_destination(dest)
    path = d.fetch(p["file"], emit) if dest["type"] == "gdrive" else d.fetch(p["file"])
    emit("Restoring %s onto %s" % (p["file"], server["name"]))
    with engine.Archive(path) as a:
        errors = engine.run_restore(server, a, p["plan"], log=emit, cancel=ev)
    if errors:
        raise engine.EngineError("%d error(s) during the restore; see the log" % len(errors))
    return {"file": p["file"], "serverId": server["id"]}


def _dur(s: float) -> str:
    s = int(s)
    return "%dm %02ds" % (s // 60, s % 60) if s >= 60 else "%ds" % s


def execute(rid: int) -> None:
    """Carry out one queued run (the worker calls it; the tests call it directly)."""
    r = db.one("SELECT status, kind, payload FROM bkp_runs WHERE id = %s", (rid,))
    if not r or r["status"] != "queued":
        return
    ev = _cancel.setdefault(rid, threading.Event())
    emit = _logger(rid)
    _update(rid, status="running", started=_now())
    t0 = time.time()
    try:
        fn = _do_backup if r["kind"] == "backup" else _do_restore
        result = fn(json.loads(r["payload"]), emit, ev)
        emit("Finished in %s" % _dur(time.time() - t0))
        _finish(rid, status="ok", finished=_now(), result=result)
    except Exception as e:
        if isinstance(e, engine.Cancelled) or ev.is_set():
            emit("Cancelled")
            _finish(rid, status="cancelled", finished=_now())
        else:
            emit("FAILED: %s" % e)
            if not isinstance(e, (engine.EngineError, model.NotFound)):
                log.error("run %s crashed:\n%s", rid, traceback.format_exc())
            _finish(rid, status="failed", finished=_now())
            _tell_failed(rid, r["kind"], e)
    finally:
        _cancel.pop(rid, None)
        _lines.pop(rid, None)


def _tell_failed(rid: int, kind: str, e: Exception) -> None:
    """A notification to the suite admins who want it (iosuite_shared.push): a backup or a restore did not finish."""
    try:
        from iosuite_shared import push
        title = db.one("SELECT title FROM bkp_runs WHERE id = %s", (rid,))
        what = "Backup" if kind == "backup" else "Restore"
        push.notify_admins("backups", f"{what} failed: {(title or {}).get('title') or 'run %d' % rid}", str(e)[:300],
                           url=push.link("iobackup", f"#/run/{rid}"), once=f"backup-failed:{rid}", urgency="high")
    except Exception:  # noqa: BLE001 - the run's own outcome is what counts
        log.warning("could not send the notification for run %s", rid, exc_info=True)


def carry_out() -> str:
    """The runs that are queued, one after another (the copy's job "runs"); how many were."""
    n = 0
    while True:
        try:
            rid = _queue.get_nowait()
        except queue.Empty:
            return f"{n} run{'s' if n != 1 else ''}" if n else ""
        n += 1
        save_unsaved()
        try:
            execute(rid)
        except Exception:  # the database went away before the run began: it ends as failed once the database is back
            log.exception("run %s could not be carried out", rid)
            _unsaved.setdefault(rid, {"status": "failed", "finished": _now()})


# ---------------------------------------------------------------- the scheduler

def due(jobs: list[dict], minutes: list[_dt.datetime]) -> list[dict]:
    """The enabled jobs whose schedule fires in any of these minutes."""
    out = []
    for j in jobs:
        if not j["enabled"] or not j["cron"]:
            continue
        try:
            c = schedule.Cron(j["cron"])
        except ValueError:
            continue
        if any(c.matches(m) for m in minutes):
            out.append(j)
    return out


_looked: dict = {"at": None}   # the minute the scheduler last looked at


def schedule_look() -> str:
    """The jobs whose schedule fired since the last look, queued (the copy's job "schedule", every 15 seconds);
    which were."""
    now = _dt.datetime.now().replace(second=0, microsecond=0)
    last = _looked["at"]
    if last is None or now <= last:
        _looked["at"] = now if last is None else min(last, now)  # the first look, or the clock went back: from now, firing nothing
        return ""
    # every minute since the last look, at most 90 (a host that slept does not fire a day's worth of jobs)
    minutes, t = [], last + _dt.timedelta(minutes=1)
    while t <= now and len(minutes) < 90:
        minutes.append(t)
        t += _dt.timedelta(minutes=1)
    _looked["at"] = now
    save_unsaved()
    started = []
    try:
        pending = pending_jobs()
        for j in due(model.jobs(), minutes):
            if j["id"] in pending:
                log.info("job %s is still queued or running: this scheduled start is skipped", j["name"])
                continue
            enqueue("backup", "Backup: %s" % j["name"], {"job_id": j["id"]}, job_id=j["id"], trigger="schedule")
            started.append(j["name"])
    except Exception:
        log.exception("the scheduler could not read the jobs")
    return ", ".join(started)


def start() -> None:
    """At start: what was queued or running when the app stopped did not finish; then the copy's two jobs, the runs
    and the scheduler."""
    global _started
    from iosuite_shared import chores
    if _started:
        return
    _started = True
    for r in db.q("SELECT id FROM bkp_runs WHERE status IN ('queued', 'running')"):
        _logger(r["id"])("Interrupted: the app stopped")
        _update(r["id"], status="failed", finished=_now())
    _looked["at"] = None
    _jobs["runs"] = chores.start(carry_out, every_s=60, first_s=5, name="runs", app=config.APP, heavy=True, quiet=True,
                                 title="Carry out the backups and restores that are queued")
    _jobs["schedule"] = chores.start(schedule_look, every_s=15, first_s=15, name="schedule", app=config.APP, quiet=True,
                                     title="Queue the backups whose schedule says now")


def stop() -> None:
    """The app shuts down: its jobs leave the copy's runner (a run that is being carried out ends with the process)."""
    global _started
    for k, j in _jobs.items():
        if j is not None:
            j.cancel()
        _jobs[k] = None
    _started = False

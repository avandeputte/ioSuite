"""The job process: where ioPix's background jobs that load large models do their work.

A model that needs more memory than the server has used to take the web app down with it: the jobs ran on a thread of
the web app, and when the container's limit was reached the kernel killed the one process there was. Now such a job
hands its work to a second process (`jobs.offload(fn, *args)`), started when the first job needs it and ended when
the queue runs dry, which also gives every byte the models held back to the system.

The process itself is the suite's (iosuite_shared.helper): its heavy lane, one call at a time in a process that
stays between calls, watched once a second and stopped

- when it holds more than its ceiling (JOBS_MEMORY_MB, by default 60% of the server's memory limit), or
- when the server as a whole has less than its reserve free (MEMORY_RESERVE_MB, by default 8% of the limit),

and no offloaded job starts while the server is below that reserve (memwatch.py has the two numbers). Should the
kernel get there first, that process is the one it picks, and the web app only sees that its job was lost. jobs.py
decides what happens to a job that was lost: once more, then held.

What is ioPix's own is here: the jobs' Progress kept in step both ways, the cancels, and how a loss is counted.
Over the lane's one channel for messages while a call runs:

    web app                               job process
    the Progress of every job, with the call  ->  (helper.before_call) sets its own copy to match
    ("bump", name)  as a note                 ->  a Progress was cancelled or started in the web app: the same here
                                              <-  ("progress", {name: fields}, applied)  whatever changed, 4x a second
                                              <-  ("job", msg)   jobs.emit(msg): to the call's on_message
                                              <-  ("hook",)      a Progress.finish() that did something

Only what is in the function's own process is separate: it reads and writes the same databases and files. So a
function that is offloaded must be a module-level one, take arguments that pickle, and keep its results in the
database, in files, in its Progress or in what it emits, never in a module's variables.
"""
import atexit
import importlib
import logging
import os
import threading
import time

from iosuite_shared import helper

from iopix import config, jobs, memwatch

log = logging.getLogger("iopix.jobproc")
IN_WORKER = os.environ.get("IOPIX_JOB_WORKER") == "1"  # this is the job process itself
REPORT_EVERY = 0.25  # seconds between Progress reports from the job process

# The lane: ioPix's memory budget rather than the helper's share, and its own environment mark, so the code that asks
# whether it is in the job process (ai/semantic.py) is not fooled by a helper reading a scan.
HEAVY = helper.Heavy("iopix.jobproc", lambda: memwatch.budget(), name="analysis", what="analysis", mark="IOPIX_JOB_WORKER")

_call = None    # the call in flight: {"bumps": {name: n}, "touched": {names the job process reported}}
_inline = None  # with no job process: the on_message of the call running here
_stop = None    # the last job stopped for memory: {at, job, reason}


def enabled() -> bool:
    return config.JOBS_PROCESS and not IN_WORKER and os.name == "posix"


def status() -> dict:
    """For the status pages: the memory limit and what is in use, what the job process holds and may hold, whether
    the queue is waiting for memory, and the last time a job was stopped ({at, job, reason})."""
    s = HEAVY.status()
    return {"process": enabled(), "limit": s["limit"], "used": s["used"], "reserve": s["reserve"],
            "ceiling": s["ceiling"], "worker": s["worker"], "waiting": s["waiting"], "lastStop": _stop}


def shutdown():
    """The queue ran dry (jobs.idle_hooks), or the web app is stopping: the job process goes, and its memory with it."""
    HEAVY.release()


# ---- the web app's side ------------------------------------------------------------------------------------------

def _on_bump(name: str):
    """A Progress here was cancelled or started again (jobs.bump_hook): the job process's copy follows, and its
    reports for that name are ignored until it has (they would undo the cancel here)."""
    def counted():
        if _call is not None:
            _call["bumps"][name] = _call["bumps"].get(name, 0) + 1
    HEAVY.note(("bump", name), before=counted)


def _apply(mine: dict, changed: dict, applied: dict):
    """The job process's Progress fields, into the ones here; not for a name cancelled here since (see _on_bump)."""
    for name, fields in changed.items():
        p = jobs._progress.get(name)
        if p is None or applied.get(name, 0) != mine["bumps"].get(name, 0):
            continue
        dict.update(p, fields)
        mine["touched"].add(name)


def _heard(mine: dict, msg, on_message):
    """What the job process sends while the call runs: its Progress, a Progress.finish() that did something, and
    whatever the offloaded function itself emits."""
    if msg[0] == "progress":
        _apply(mine, msg[1], msg[2])
    elif msg[0] == "hook":
        if jobs.finished_hook:
            jobs.finished_hook()
    elif msg[0] == "job" and on_message:
        on_message(msg[1])


def _lost(mine: dict, key: str | None, what: str, lost):
    """The job process went before the job did: what it left looking alive is marked stopped, and the loss counted
    (jobs.py tries the job once more, then holds it)."""
    global _stop
    for name in mine["touched"]:  # what the lost process left "running" would look alive for ever
        p = jobs._progress.get(name)
        if p is not None and p["running"] and mine["bumps"].get(name, 0) == 0:
            p["running"] = False
            p.fail(f"Stopped: {lost}")
    _stop = {"at": int(time.time()), "job": key, "reason": str(lost)}
    log.warning("job %s stopped: %s", key or what, lost)
    jobs.note_lost(lost)


def call(fn, args: tuple, on_message=None):
    """jobs.offload: run fn(*args) in the job process and wait."""
    global _call, _inline
    key = jobs.current()
    hold = jobs.held(key) if key else None
    if hold:
        raise jobs.Held(f"paused: {hold['reason']}")
    if not enabled():
        before, _inline = _inline, on_message
        try:
            return fn(*args)
        finally:
            _inline = before
    mine = {"bumps": {}, "touched": set()}

    def begin():
        """Under the lane's lock, with the run message about to go: every Progress as the web app has it, so a
        generation a job took there means the same here. A cancel from another thread is either in this or sent
        after the run message, never lost between."""
        global _call
        _call = mine
        return {name: (dict(p), p.gen) for name, p in jobs._progress.items()}

    def failed(text: str, tb: str):
        log.error("job %s failed in the job process: %s\n%s", key or fn.__qualname__, text, tb)
        return jobs.RemoteError(text)

    try:
        return HEAVY.call(fn, args, before_send=begin, on_message=lambda m: _heard(mine, m, on_message),
                          lost_as=lambda why, own: jobs.WorkerLost(why, strike=own), failed_as=failed)
    except jobs.WorkerLost as lost:
        _lost(mine, key, fn.__qualname__, lost)
        raise
    finally:
        _call = None


def emit(msg):
    """jobs.emit: from the offloaded function to its call's on_message."""
    if IN_WORKER:
        helper.emit(("job", msg))
    elif _inline:
        _inline(msg)


# ---- the job process's side --------------------------------------------------------------------------------------

_lock = threading.Lock()  # guards the cancels applied and what was last reported
_applied = {}             # name -> cancels from the web app applied during this call
_reported = {}            # name -> the fields last sent (or as the web app had them when the call began)
_imported = False
_live = False  # a call has begun: before that, the Progress here is not the web app's and is not reported


def _begin(baseline: dict):
    """A call begins (helper.before_call): every Progress as the web app has it, so a generation a job took there
    means the same here. Run by the thread that reads the pipe, in the order the messages came, so a cancel sent
    after the run message is applied after this and never undone by it."""
    global _imported, _live
    if not _imported:  # it sets jobs.finished_hook for the web app; ours replaces it, so it is imported first
        importlib.import_module("iopix.ai.analysis")
        _imported = True
    jobs.finished_hook = lambda: helper.emit(("hook",))  # a run that did something: the web app folds the results in
    with _lock:
        jobs.baseline.clear()
        jobs.baseline.update(baseline)
        jobs.bumped.clear()
        _applied.clear()
        _reported.clear()
        for name, (fields, gen) in baseline.items():
            _reported[name] = dict(fields)
            p = jobs._progress.get(name)
            if p is not None:
                dict.clear(p)
                dict.update(p, fields)
                p.gen = gen
        _live = True


def _bump(msg):
    """A note from the web app: a Progress was cancelled or started again there."""
    if msg[0] != "bump":
        return
    name = msg[1]
    with _lock:
        _applied[name] = _applied.get(name, 0) + 1
        jobs.bumped[name] = jobs.bumped.get(name, 0) + 1
        p = jobs._progress.get(name)
        if p is not None:
            p.gen += 1
            p["running"] = False


def _report():
    """What changed in any Progress since the last report, with the cancels applied so far (the web app ignores a
    report made before a cancel of its own arrived here). Also helper.after_call: the last state before the answer,
    which the web app reads its Progress right after."""
    with _lock:
        if not _live:
            return
        changed = {}
        try:
            for name, p in list(jobs._progress.items()):
                cur = dict(p)
                if cur != _reported.get(name):
                    changed[name] = _reported[name] = cur
        except RuntimeError:  # a job thread changed a dict's size meanwhile: the next report has it
            return
        applied = dict(_applied)
    if changed:
        helper.emit(("progress", changed, applied))


def _reporter():
    while True:
        time.sleep(REPORT_EVERY)
        _report()


if IN_WORKER:
    helper.before_call, helper.after_call, helper.on_note = _begin, _report, _bump
    threading.Thread(target=_reporter, name="jobproc-report", daemon=True).start()
else:
    jobs.bump_hook = _on_bump
    jobs.idle_hooks.append(shutdown)
    atexit.register(shutdown)

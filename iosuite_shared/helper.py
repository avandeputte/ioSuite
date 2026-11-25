"""The helper: a process of its own, beside the copy, for the work that runs compiled code on what people upload.

Reading text off a scan (Tesseract, RapidOCR), a license's barcode (zxing-cpp), decoding a photo someone sent (Pillow,
libheif), making a PDF of a whole inventory: this is the work most likely to crash in a library written in C or C++, or
to take more memory than the machine has. The apps of a copy share one process, so a crash there would take every app
of the copy down with it. Here it takes down only the helper: the call that was running gets an error (HelperLost),
the next call starts a new helper, and the copy carries on.

    from iosuite_shared import helper
    text = helper.call(ocr.read, raw, mime, timeout=180)   # ocr.read(raw, mime), in the helper; its error is raised here

What it is:

- **One per copy, started by the copy.** Up to WORKERS processes (`python -m iosuite_shared.helperworker`), each one
  call at a time, started when a call needs one and ended after IDLE_S without work (what a model held goes back to the
  system). A copy never asks another server's helper: the work is done on the machine that has the file, so running
  some apps on one server and others on another changes nothing.
- **Bounded.** A call has a timeout; the helper is the process the kernel stops first when memory runs out (its
  oom_score_adj is raised), and it is stopped when it holds more than HELPER_MEMORY_MB (the machine's file; by default
  half of what the machine or container may use).
- **Not a sandbox.** It reads the same databases and files, with the same settings, as the copy (it starts with the
  copy's environment); it keeps nothing between calls that matters. A function given to call() is a module-level one
  whose arguments and result pickle.
- **Off** with HELPER=off in the machine's file (and in the tests, unless a test turns it on): the work runs in the
  copy itself, as before. Off Linux and macOS it is always off.

Work that loads a large model (ioPix's analysis) takes the other lane, `Heavy`: one call at a time in a process of
its own that stays between calls (a model loaded once serves the next job), with the app's own memory budget instead
of the helper's share, no time limit, and a two-way channel while the call runs (the app sends the call a note, the
call sends the app what it has done so far). Both lanes are the same program: one way to start a process beside the
copy, watch what it holds, bring its log lines and its answer back, and say why it went.

Its log lines go to the copy, which writes them to the one log like its own (marked with the app the module belongs to).
"""
import atexit
import logging
import os
import pickle
import subprocess
import threading
import time

from iosuite_shared import child, config, memory
from iosuite_shared.errors import Invalid

log = logging.getLogger("iosuite_shared.helper")

WORKERS = 2            # helper processes at most: one long PDF does not hold up a scan being read
IDLE_S = 90.0          # a helper with nothing to do for this long ends
CHECK_EVERY = 1.0      # seconds between looks at a running call's memory
DEFAULT_TIMEOUT = 300  # seconds a call may take unless it says otherwise
MEMORY_SHARE = 0.5     # the most a helper may hold: this share of what the machine (or its container) may use
MB = 1024 * 1024
IN_WORKER = os.environ.get("IOSUITE_HELPER_WORKER") == "1"


class HelperLost(Invalid):
    """The helper ended before the call did (it crashed, it was stopped for its memory, it took too long). The copy is
    fine; the same call made again starts a new helper (and fails again if it is the input that is the trouble). An
    Invalid: what the person who sent the file sees is why it could not be worked on, not a server error."""


class HelperError(RuntimeError):
    """The function failed in the helper with an error that could not be brought back as it was."""


_lock = threading.Condition()
_idle: list = []   # helpers waiting for work: {"proc", "conn", "since"}
_count = 0         # helpers there are, busy or idle
_reaper = None
_local = threading.local()  # inline (helper off): the call's on_message, for emit()
_info = {"calls": 0, "lost": 0, "lastLost": None}
worker_send = None  # in a helper: how it sends to the copy (helperworker sets it)


def enabled() -> bool:
    """Whether work goes to the helper (else it runs in the copy)."""
    if IN_WORKER or os.name != "posix":
        return False
    return config.as_flag(config.env("HELPER", "on"), True)


def ceiling() -> int | None:
    """Bytes a helper may hold, helper and the programs it started together; None: no ceiling known."""
    v = config.env("HELPER_MEMORY_MB")
    if v:
        try:
            n = int(v)
            return n * MB if n > 0 else None
        except ValueError:
            pass
    lim = memory.limit()
    return int(lim * MEMORY_SHARE) if lim else None


def status() -> dict:
    """For the status pages: on or off, helpers running, calls made and lost since the copy started."""
    with _lock:
        return {"on": enabled(), "running": _count, "idle": len(_idle), "ceilingMb": (ceiling() or 0) // MB, **_info}


# ---- the helpers

def _spawn() -> dict:
    proc, conn = child.spawn("iosuite_shared.helperworker", "IOSUITE_HELPER_WORKER")
    log.info("helper started (pid %d)", proc.pid)
    return {"proc": proc, "conn": conn, "since": time.monotonic()}


def _kill(w: dict) -> None:
    """The helper and whatever it started, gone and waited for."""
    child.end(w["proc"], w["conn"])


def _end(w: dict) -> None:
    """A helper that is no longer wanted: asked to go, then made to."""
    try:
        w["conn"].send(("exit",))
        w["proc"].wait(timeout=3)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    _kill(w)


def _take() -> dict:
    """A helper for one call: an idle one, else a new one, else wait for one to be free."""
    global _count
    with _lock:
        while True:
            while _idle:
                w = _idle.pop()
                if w["proc"].poll() is None:
                    return w
                _count -= 1
                _kill(w)
            if _count < WORKERS:
                _count += 1
                break
            _lock.wait(1.0)
    try:
        w = _spawn()
    except Exception:
        with _lock:
            _count -= 1
            _lock.notify()
        raise
    _start_reaper()
    return w


def _give_back(w: dict | None) -> None:
    global _count
    with _lock:
        if w is not None and w["proc"].poll() is None:
            w["since"] = time.monotonic()
            _idle.append(w)
        else:
            _count -= 1
        _lock.notify()


def _reap() -> None:
    """Every few seconds: helpers idle for IDLE_S end."""
    global _count
    while True:
        time.sleep(min(15.0, IDLE_S / 3))
        old = []
        with _lock:
            now = time.monotonic()
            for w in list(_idle):
                if now - w["since"] >= IDLE_S:
                    _idle.remove(w)
                    _count -= 1
                    old.append(w)
        for w in old:
            _end(w)
            log.info("helper ended (pid %d: nothing to do)", w["proc"].pid)


def _start_reaper() -> None:
    global _reaper
    with _lock:
        if _reaper is None or not _reaper.is_alive():
            _reaper = threading.Thread(target=_reap, name="helper-reaper", daemon=True)
            _reaper.start()


def shutdown() -> None:
    """The copy is stopping: every idle helper goes (a busy one ends with its pipe)."""
    global _count
    with _lock:
        old, _idle[:] = list(_idle), []
        _count -= len(old)
    for w in old:
        _end(w)


atexit.register(shutdown)


def call(fn, *args, timeout: float = DEFAULT_TIMEOUT, on_message=None, **kwargs):
    """fn(*args, **kwargs) in a helper; its result, or its error raised here. HelperLost when the helper ended first
    (crashed, out of memory, longer than `timeout` seconds). on_message(msg) hears what the function emit()s. With the
    helper off, fn runs here."""
    if not enabled():
        before, _local.on_message = getattr(_local, "on_message", None), on_message
        try:
            return fn(*args, **kwargs)
        finally:
            _local.on_message = before
    if not child.sendable(fn):
        raise TypeError(f"{fn.__module__}.{fn.__qualname__}: only a module-level function can go to the helper")
    what = f"{fn.__module__}.{fn.__qualname__}"
    limit = ceiling()
    w = _take()
    lost = done = None
    try:
        try:
            w["conn"].send(("run", fn.__module__, fn.__qualname__, args, kwargs, None))
        except (OSError, ValueError):
            pass  # found gone below
        end = time.monotonic() + timeout
        next_check = time.monotonic() + CHECK_EVERY
        while done is None:
            try:
                ready = w["conn"].poll(0.2)
            except (OSError, EOFError):
                ready = True
            if ready:
                try:
                    msg = w["conn"].recv()
                except (EOFError, OSError):
                    lost = lost or child.why(w["proc"])
                    break
                if msg[0] == "log":
                    logging.getLogger(msg[1]).log(msg[2], "%s", msg[3])
                elif msg[0] == "emit":
                    if on_message:
                        try:
                            on_message(msg[1])
                        except Exception:  # noqa: BLE001  the caller's handler: said, the call goes on
                            log.exception("%s: a message handler failed", what)
                elif msg[0] == "done":
                    done = msg
                continue
            now = time.monotonic()
            if lost is None and now >= end:
                lost = f"it took longer than {int(timeout)} seconds"
                _kill(w)
            elif lost is None and limit and now >= next_check:
                next_check = now + CHECK_EVERY
                held = memory.tree(w["proc"].pid)
                if held > limit:
                    lost = f"it needed more memory than the helper may use ({held // MB} MB; the most is {limit // MB} MB)"
                    _kill(w)
            if w["proc"].poll() is not None and not _readable(w):
                lost = lost or child.why(w["proc"])
                break
    except BaseException:
        _kill(w)
        _give_back(None)
        raise
    if done is None:
        _kill(w)
        _give_back(None)
        with _lock:
            _info["lost"] += 1
            _info["lastLost"] = {"at": int(time.time()), "work": what, "reason": lost}
        log.warning("helper lost during %s: %s", what, lost)
        raise HelperLost(f"This could not be finished: the process doing the work stopped ({lost}). The file may be damaged")
    _give_back(w)
    with _lock:
        _info["calls"] += 1
    _kind, ok, value, text, tb = done
    if ok:
        return value
    err = None
    if value is not None:
        try:
            err = pickle.loads(value)
        except Exception:  # noqa: BLE001  an error class that does not come back: its text does
            err = None
    if not isinstance(err, BaseException):
        log.error("%s failed in the helper: %s\n%s", what, text, tb)
        raise HelperError(text)
    raise err


def call_or(default, fn, *args, **kwargs):
    """call(fn, ...), or `default` when the helper was lost doing it (said in the log): for work a file can do without,
    such as its small picture."""
    try:
        return call(fn, *args, **kwargs)
    except HelperLost:
        return default


def _readable(w: dict) -> bool:
    try:
        return w["conn"].poll(0)
    except (OSError, EOFError):
        return False


# ---- the heavy lane: one process for the work that loads large models

HEAVY_RECYCLE = 0.5   # a process already holding this share of its ceiling is replaced before the next call
HEAVY_START = 1.25    # no call starts below reserve * this: work stopped at the reserve must not start right back up
WAIT_EVERY = 10.0     # seconds between looks while waiting for memory to come free
before_call = None    # in a helper: before_call(setup) runs before a call whose caller sent one (the app registers it)
after_call = None     # in a helper: after_call() runs when the function has returned, before the answer goes back
on_note = None        # in a helper: on_note(msg) when the copy sends the running call a note


class Heavy:
    """One helper of its own, for an app's heaviest work (ioPix's analysis jobs).

    It differs from call() in what the work needs, not in how it is done: one call at a time, the process kept
    between calls and replaced when it already holds much of its ceiling, no time limit, and the app's own memory
    budget — a ceiling for the process and a reserve of free memory under which nothing starts. While a call runs
    the two can talk: note(msg) reaches the function (a cancel), and what the function emit()s reaches on_message.

        HEAVY = helper.Heavy('iopix.jobproc', memwatch.budget)  # the module the helper imports first (it registers the hooks)
        HEAVY.call(analyse, (album,), setup=..., on_message=...)

    `budget()` gives {limit, used, free, reserve, ceiling} in bytes (None where memory cannot be read).
    `module` is imported in the helper before anything else, so it can register before_call/after_call/on_note.
    `name` names the lane in the log, `what` names the work where someone is told it was stopped, and `mark` is the
    environment name that tells the lane's own code it is in its process (so an app can tell its own lane's helper
    from the one reading a scan).
    """

    def __init__(self, module: str, budget, name: str = "heavy", what: str = "this work", mark: str | None = None):
        self.module, self.budget, self.name, self.what = module, budget, name, what
        self.mark = mark or "IOSUITE_HELPER_WORKER"  # the environment name that tells the lane's own code it is there
        self.lock = threading.Lock()        # one call at a time
        self.state = threading.Lock()       # guards the process and the call in flight
        self.worker = None                  # {"proc", "conn", "rss"}
        self.running = False
        self.info = {"waiting": None, "lastStop": None, "peak": 0}

    # -- the process
    def _spawn(self) -> dict:
        proc, conn = child.spawn("iosuite_shared.helperworker", self.mark)
        log.info("%s helper started (pid %d)", self.name, proc.pid)
        w = {"proc": proc, "conn": conn, "rss": 0}
        if self.module:
            try:
                conn.send(("prepare", self.module))
            except (OSError, ValueError):
                pass  # found gone when the call is sent
        return w

    def _discard(self, w: dict) -> None:
        with self.state:
            if self.worker is w:
                self.worker = None
        child.end(w["proc"], w["conn"])

    def release(self) -> None:
        """There is no more work (the app's queue ran dry) or the copy is stopping: the process goes, and the memory
        its models held with it. A call in flight keeps it."""
        with self.state:
            w = self.worker
        if w is None or self.running:
            return
        try:
            w["conn"].send(("exit",))
            w["proc"].wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        self._discard(w)
        log.info("%s helper ended (no more work)", self.name)

    def _ready(self) -> dict:
        """The process, started where there is none and replaced where the one there holds much of its ceiling (the
        models of the work before): each call gets most of the room."""
        w = self.worker
        if w is not None and w["proc"].poll() is None:
            ceiling = self.budget()["ceiling"]
            if not ceiling or memory.tree(w["proc"].pid) < ceiling * HEAVY_RECYCLE:
                return w
            self.release()
        elif w is not None:
            self._discard(w)
        w = self._spawn()
        with self.state:
            self.worker = w
        return w

    def _wait_for_memory(self) -> None:
        """Hold the work while the machine is short of memory: a call started now would only be stopped again."""
        first = True
        while True:
            b = self.budget()
            if not b["reserve"] or b["free"] is None or b["free"] >= b["reserve"] * HEAVY_START:
                break
            if first:
                self.release()  # a process with nothing to do is memory too
                log.warning("%s waits for memory: %s of %s in use", self.name, memory.gb(b["used"]), memory.gb(b["limit"]))
                first = False
            self.info["waiting"] = {"since": self.info["waiting"]["since"] if self.info["waiting"] else int(time.time()), "used": b["used"], "limit": b["limit"]}
            time.sleep(WAIT_EVERY)
        if not first:
            log.info("%s goes on: memory is free again", self.name)
        self.info["waiting"] = None

    def _over(self, w: dict):
        """(reason, how much of it is this call's doing) when the process has to go now, else None."""
        b = self.budget()
        rss = w["rss"] = memory.tree(w["proc"].pid)
        self.info["peak"] = max(self.info["peak"], rss)
        if b["ceiling"] and rss > b["ceiling"]:
            return (f"it needed more memory than {self.what} may use on this server (the most is {memory.gb(b['ceiling'])})", True)
        if b["reserve"] and b["free"] is not None and b["free"] < b["reserve"]:
            own = rss >= (b["ceiling"] or b["limit"] * 0.6) / 3  # a small job is not what filled the machine
            return (f"the server was running out of memory ({memory.gb(b['used'])} of {memory.gb(b['limit'])} in use, {memory.gb(rss)} of it by this job)", own)
        return None

    # -- the call
    def note(self, msg, before=None) -> None:
        """To the call running now (a cancel). Nothing happens when there is none. `before()` is called first, under
        the same lock as the run message, for a lane that keeps a count of what it has sent."""
        with self.state:
            if not self.running or self.worker is None:
                return
            if before:
                before()
            try:
                self.worker["conn"].send(("note", msg))
            except (OSError, ValueError):
                pass  # the process is gone: the call ends on its own

    def status(self) -> dict:
        """For the status pages: the memory numbers, what the process holds, whether work is waiting for memory, and
        the last time a call was stopped."""
        b = self.budget()
        w = self.worker
        return {"limit": b["limit"], "used": b["used"], "reserve": b["reserve"], "ceiling": b["ceiling"],
                "worker": (w or {}).get("rss", 0) if w else 0, "waiting": self.info["waiting"], "lastStop": self.info["lastStop"]}

    def call(self, fn, args: tuple = (), *, setup=None, on_message=None, before_send=None, lost_as=None, failed_as=None):
        """fn(*args) in the heavy helper, waited for. `setup` goes with it, for the helper's before_call. The error
        the function raised is raised here (HelperError when it does not come back as it is), or failed_as(text,
        traceback) where the lane gives one; when the process went first, lost_as(reason, own) or HelperLost.
        before_send(): called under the lock once the run message is about to go, for an app that must take the
        state it sends in step with its own."""
        if not child.sendable(fn):
            raise TypeError(f"{fn.__module__}.{fn.__qualname__}: only a module-level function can go to the helper")
        what = f"{fn.__module__}.{fn.__qualname__}"
        lost = done = None
        with self.lock:
            self._wait_for_memory()
            w = self._ready()
            with self.state:  # a note from another thread is either in `setup` or sent after the run message, never lost between
                if before_send:
                    setup = before_send()
                self.running = True
                try:
                    w["conn"].send(("run", fn.__module__, fn.__qualname__, args, {}, setup))
                except (OSError, ValueError):
                    pass  # found gone below
            own = False
            next_check = time.monotonic() + CHECK_EVERY
            try:
                while done is None:
                    try:
                        ready = w["conn"].poll(0.2)
                    except (OSError, EOFError):
                        ready = True
                    if ready:
                        try:
                            msg = w["conn"].recv()
                        except (EOFError, OSError):
                            lost = lost or child.why(w["proc"])
                            break
                        if msg[0] == "log":
                            logging.getLogger(msg[1]).log(msg[2], "%s", msg[3])
                        elif msg[0] == "emit":
                            if on_message:
                                try:
                                    on_message(msg[1])
                                except Exception:  # noqa: BLE001  the caller's handler: said, the call goes on
                                    log.exception("%s: a message handler failed", what)
                        elif msg[0] == "done":
                            done = msg
                        continue
                    if lost is None and time.monotonic() >= next_check:
                        next_check = time.monotonic() + CHECK_EVERY
                        over = self._over(w)
                        if over is not None:
                            lost, own = over
                            _kill(w)  # the pipe closes, and the loop ends at the EOF
                    if w["proc"].poll() is not None and not _readable(w):
                        lost = lost or child.why(w["proc"])
                        break
            finally:
                with self.state:
                    self.running = False
            if done is None:
                self._discard(w)
                self.info["lastStop"] = {"at": int(time.time()), "work": what, "reason": lost}
                log.warning("%s stopped during %s: %s", self.name, what, lost)
                raise (lost_as(lost, own) if lost_as else HelperLost(f"This could not be finished: {lost}"))
        _kind, ok, value, text, tb = done
        if ok:
            return value
        if failed_as:
            raise failed_as(text, tb)
        err = None
        if value is not None:
            try:
                err = pickle.loads(value)
            except Exception:  # noqa: BLE001  an error class that does not come back: its text does
                err = None
        if not isinstance(err, BaseException):
            log.error("%s failed in the %s helper: %s\n%s", what, self.name, text, tb)
            raise HelperError(text)
        raise err


def emit(msg) -> None:
    """From a function running in the helper (or here, with the helper off) to its call's on_message."""
    if IN_WORKER:
        if worker_send:
            worker_send(("emit", msg))
        return
    handler = getattr(_local, "on_message", None)
    if handler:
        handler(msg)

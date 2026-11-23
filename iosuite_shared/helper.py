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

Its log lines go to the copy, which writes them to the one log like its own (marked with the app the module belongs to).
"""
import atexit
import importlib
import logging
import os
import pickle
import signal
import subprocess
import sys
import threading
import time
from multiprocessing import Pipe
from pathlib import Path

from iosuite_shared import config
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
    lim = _limit()
    return int(lim * MEMORY_SHARE) if lim else None


def status() -> dict:
    """For the status pages: on or off, helpers running, calls made and lost since the copy started."""
    with _lock:
        return {"on": enabled(), "running": _count, "idle": len(_idle), "ceilingMb": (ceiling() or 0) // MB, **_info}


# ---- memory (Linux: /proc and the cgroup files; elsewhere nothing is known and nothing is stopped)

def _int(path: Path):
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _limit():
    """Bytes this machine or container may use, or None."""
    total = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    best = None
    try:
        line = next(ln for ln in Path("/proc/self/cgroup").read_text().splitlines() if ln.startswith("0::"))
        root = Path("/sys/fs/cgroup")
        d = root / line[3:].strip().lstrip("/")
        while True:
            n = _int(d / "memory.max")
            if n is not None and (best is None or n < best):
                best = n
            if d == root or root not in d.parents:
                break
            d = d.parent
    except (OSError, StopIteration):
        pass
    if best is not None and total is not None:
        return min(best, total)
    return best if best is not None else total


_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names else 4096


def _rss(pid: int) -> int:
    try:
        return int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * _PAGE
    except (OSError, ValueError, IndexError):
        return 0


def _tree(pid: int) -> int:
    """Resident bytes of a helper and every program it started (tesseract, pdftoppm)."""
    seen, todo, total = set(), [pid], 0
    while todo and len(seen) < 200:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        total += _rss(p)
        try:
            for task in Path(f"/proc/{p}/task").iterdir():
                todo += [int(c) for c in (task / "children").read_text().split()]
        except (OSError, ValueError):
            pass
    return total


# ---- the helpers

def _spawn() -> dict:
    here, there = Pipe()
    try:
        proc = subprocess.Popen([sys.executable, "-m", "iosuite_shared.helperworker", str(there.fileno())], pass_fds=[there.fileno()],
                                cwd=str(config.BASE), start_new_session=True,
                                env={**os.environ, "IOSUITE_HELPER_WORKER": "1", "IOSUITE_LOG_CHILD": "1", "DB_CONNECTIONS": config.child_connections()})
    finally:
        there.close()
    log.info("helper started (pid %d)", proc.pid)
    return {"proc": proc, "conn": here, "since": time.monotonic()}


def _kill(w: dict) -> None:
    """The helper and whatever it started (it has its own process group)."""
    try:
        os.killpg(w["proc"].pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            w["proc"].kill()
        except OSError:
            pass
    try:
        w["conn"].close()
    except OSError:
        pass
    try:
        w["proc"].wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


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


def _why(w: dict, given: str | None) -> str:
    if given:
        return given
    try:
        rc = w["proc"].wait(timeout=10)
    except subprocess.TimeoutExpired:
        rc = None
    if rc == -signal.SIGKILL:
        return "the system stopped it, most likely because the server ran out of memory"
    if rc is not None and rc < 0:
        try:
            return f"it crashed ({signal.Signals(-rc).name})"
        except ValueError:
            return f"it crashed (signal {-rc})"
    return f"it ended unexpectedly (exit code {rc})"


def _resolve(module: str, name: str):
    obj = importlib.import_module(module)
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


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
    try:
        same = _resolve(fn.__module__, fn.__qualname__) is fn
    except (AttributeError, ImportError):
        same = False
    if not same:
        raise TypeError(f"{fn.__module__}.{fn.__qualname__}: only a module-level function can go to the helper")
    what = f"{fn.__module__}.{fn.__qualname__}"
    limit = ceiling()
    w = _take()
    lost = done = None
    try:
        try:
            w["conn"].send(("run", fn.__module__, fn.__qualname__, args, kwargs))
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
                    lost = _why(w, lost)
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
                held = _tree(w["proc"].pid)
                if held > limit:
                    lost = f"it needed more memory than the helper may use ({held // MB} MB; the most is {limit // MB} MB)"
                    _kill(w)
            if w["proc"].poll() is not None and not _readable(w):
                lost = _why(w, lost)
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


def emit(msg) -> None:
    """From a function running in the helper (or here, with the helper off) to its call's on_message."""
    if IN_WORKER:
        if worker_send:
            worker_send(("emit", msg))
        return
    handler = getattr(_local, "on_message", None)
    if handler:
        handler(msg)

"""A process the copy starts beside itself for work that must not take the copy down with it: how the helper
(helper.py, helperworker.py) starts every one of its processes, for a scan to be read as much as for ioPix's
analysis jobs (iopix/jobproc.py).

    copy:   proc, conn = child.spawn("iosuite_shared.helperworker", "IOSUITE_HELPER_WORKER")
            conn.send(("run", ...)); conn.recv(); ...
            child.end(proc, conn)                 # or child.kill(proc), and child.why(proc) for what to say

    child:  conn = child.connection(sys.argv[1])  # python -m <module> FD
            child.first_to_go()                   # the kernel ends this process, not the copy, when memory runs out
            child.log_to_parent(send)             # its log lines go to the copy, which writes the one log

Each side keeps its own messages (helperworker.py has them). The child starts with the copy's environment, so it reads the same machine's file and the same
settings, in a session of its own: ending it ends what it started too (tesseract, ffmpeg, exiftool). Its share of
the copy's database connections is small (config.child_connections()).
"""
import importlib
import logging
import os
import signal
import subprocess
import sys
import traceback
from multiprocessing import Pipe
from multiprocessing.connection import Connection

from iosuite_shared import config


def spawn(module: str, mark: str) -> tuple:
    """Start `python -m <module> FD` with one end of a pipe; (process, the copy's end). `mark` is the environment
    name that tells the module's code it is the child (set to 1)."""
    here, there = Pipe()
    try:
        proc = subprocess.Popen([sys.executable, "-m", module, str(there.fileno())], pass_fds=[there.fileno()],
                                cwd=str(config.BASE), start_new_session=True,
                                env={**os.environ, mark: "1", "IOSUITE_LOG_CHILD": "1", "DB_CONNECTIONS": config.child_connections()})
    finally:
        there.close()
    return proc, here


def kill(proc) -> None:
    """End the process and whatever it started (it has its own process group)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass


def end(proc, conn) -> None:
    """kill(), the pipe closed, and the process waited for (so nothing of it is left behind)."""
    kill(proc)
    try:
        conn.close()
    except OSError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def why(proc) -> str:
    """Why a child that ended before its work did is gone, for the message and the log."""
    try:
        rc = proc.wait(timeout=10)
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


def resolve(module: str, name: str):
    """The object a module and a dotted name stand for (how a function is named across the pipe)."""
    obj = importlib.import_module(module)
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


def sendable(fn) -> bool:
    """Whether `fn` can be named across the pipe: a module-level function, found again by its module and name."""
    try:
        return resolve(fn.__module__, fn.__qualname__) is fn
    except (AttributeError, ImportError):
        return False


# ---- the child's side

def connection(fd) -> Connection:
    """The child's end of the pipe, from the number it was started with."""
    return Connection(int(fd))


def first_to_go(score: int = 1000) -> None:
    """When memory runs out, the kernel ends this process before the copy or the database (a process may raise its
    own score; Linux)."""
    try:
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write(str(score))
    except OSError:
        pass


class _ToParent(logging.Handler):
    def __init__(self, send):
        super().__init__()
        self._send = send

    def emit(self, record):
        try:
            text = record.getMessage()
            if record.exc_info:
                text += "\n" + "".join(traceback.format_exception(*record.exc_info)).rstrip()
            self._send(("log", record.name, record.levelno, text))
        except Exception:  # noqa: BLE001  a log line never stops the work
            pass


def log_to_parent(send) -> None:
    """Every log line of this process goes to the copy as ("log", logger, level, text), which writes it where its
    own go (one writer for the log file and its rotation): logging.getLogger(name).log(level, "%s", text) there."""
    root = logging.getLogger()
    root.handlers[:] = [_ToParent(send)]
    root.setLevel(logging.INFO)

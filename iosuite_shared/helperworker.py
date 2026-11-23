"""`python -m iosuite_shared.helperworker FD`: one helper process (see helper.py for why there is one).

Started by the copy with one end of a pipe; runs the functions the copy sends, one at a time, and ends when told to
or when the copy is gone (the pipe closes). It starts with the copy's environment, so the modules it imports read the
same machine's file and the same settings.

    copy                                      helper
    ("run", module, name, args, kwargs)  ->   imports the module, runs the function
                                         <-   ("log", logger, level, text)   its log lines, written by the copy
                                         <-   ("emit", msg)                   helper.emit(msg) in the function
                                         <-   ("done", ok, value, text, traceback)
    ("exit",)                            ->   ends
"""
import logging
import os
import pickle
import sys
import threading
import traceback
from multiprocessing.connection import Connection

os.environ["IOSUITE_HELPER_WORKER"] = "1"  # before helper is imported: work asked of the helper here runs here

from iosuite_shared import helper  # noqa: E402

_send_lock = threading.Lock()
_conn = None


def send(msg) -> None:
    with _send_lock:
        try:
            _conn.send(msg)
        except (OSError, ValueError, BrokenPipeError):
            os._exit(0)  # the copy is gone


class _ToCopy(logging.Handler):
    """Log lines go to the copy, which writes them where its own go (one writer for the log file)."""

    def emit(self, record):
        try:
            text = record.getMessage()
            if record.exc_info:
                text += "\n" + "".join(traceback.format_exception(*record.exc_info)).rstrip()
            send(("log", record.name, record.levelno, text))
        except Exception:  # noqa: BLE001
            pass


def _first_to_go() -> None:
    """When memory runs out, the kernel stops this process before the copy (a process may raise its own score)."""
    try:
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write("1000")
    except OSError:
        pass


def _run(module: str, name: str, args: tuple, kwargs: dict) -> tuple:
    try:
        fn = helper._resolve(module, name)
        return ("done", True, fn(*args, **kwargs), "", "")
    except BaseException as e:  # noqa: BLE001  every failure goes back to the caller
        tb = traceback.format_exc()
        try:
            value = pickle.dumps(e)
            pickle.loads(value)  # it must come back as it is, or not at all
        except Exception:  # noqa: BLE001
            value = None
        return ("done", False, value, f"{type(e).__name__}: {e}", tb)


def main(fd: int) -> None:
    global _conn
    _conn = Connection(fd)
    helper.worker_send = send
    _first_to_go()
    root = logging.getLogger()
    root.handlers[:] = [_ToCopy()]
    root.setLevel(logging.INFO)
    while True:
        try:
            msg = _conn.recv()
        except (EOFError, OSError):
            break  # the copy is gone
        if msg[0] == "exit":
            break
        if msg[0] == "run":
            out = _run(*msg[1:5])
            try:
                send(out)
            except Exception as e:  # noqa: BLE001  a result that does not pickle: a programming error, said there
                send(("done", False, None, f"the result could not be sent back ({type(e).__name__}: {e})", ""))
    os._exit(0)


if __name__ == "__main__":
    main(int(sys.argv[1]))

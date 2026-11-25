"""`python -m iosuite_shared.helperworker FD`: one helper process (see helper.py for why there is one).

Started by the copy with one end of a pipe; runs the functions the copy sends, one at a time, and ends when told to
or when the copy is gone (the pipe closes). It starts with the copy's environment, so the modules it imports read the
same machine's file and the same settings.

    copy                                            helper
    ("prepare", module)                        ->   imports it first, so it can register the hooks below
    ("run", module, name, args, kwargs, setup) ->   before_call(setup), runs the function, after_call()
    ("note", msg)                              ->   on_note(msg), while the function runs (a cancel)
                                               <-   ("log", logger, level, text)   its log lines, written by the copy
                                               <-   ("emit", msg)                  helper.emit(msg) in the function
                                               <-   ("done", ok, value, text, traceback)
    ("exit",)                                  ->   ends

A thread reads the pipe, so a note reaches the function while it runs; the functions themselves run on the main
thread, one at a time, in the order they came. `before_call` is run by the reading thread, in the order the messages
came, so a note sent after the run message is applied after it and never undone by it.

The hooks (helper.before_call, helper.after_call, helper.on_note) are for a lane whose work keeps something in step
with the copy while it runs: ioPix's analysis jobs set them in iopix/jobproc.py, which is the module its lane asks
for with ("prepare", ...). The short lane sets none.
"""
import importlib
import logging
import os
import pickle
import queue
import sys
import threading
import traceback

os.environ["IOSUITE_HELPER_WORKER"] = "1"  # before helper is imported: work asked of the helper here runs here

from iosuite_shared import child, helper  # noqa: E402

log = logging.getLogger("iosuite_shared.helperworker")
_send_lock = threading.Lock()
_conn = None
_runs: queue.Queue = queue.Queue()


def send(msg) -> None:
    with _send_lock:
        try:
            _conn.send(msg)
        except (OSError, ValueError, BrokenPipeError):
            os._exit(0)  # the copy is gone


def _prepare(module: str) -> None:
    """The module the lane named, imported before its first call: it registers the hooks below."""
    try:
        importlib.import_module(module)
    except Exception:  # noqa: BLE001  said in the copy's log; the call that follows fails on its own
        log.exception("the helper could not prepare %s", module)


def _hook(fn, what: str, *args) -> None:
    try:
        fn(*args)
    except Exception:  # noqa: BLE001  the lane's own code: said, and the call goes on
        log.exception("a helper %s hook failed", what)


def _run(module: str, name: str, args: tuple, kwargs: dict) -> tuple:
    try:
        fn = child.resolve(module, name)
        out = ("done", True, fn(*args, **kwargs), "", "")
    except BaseException as e:  # noqa: BLE001  every failure goes back to the caller
        tb = traceback.format_exc()
        try:
            value = pickle.dumps(e)
            pickle.loads(value)  # it must come back as it is, or not at all
        except Exception:  # noqa: BLE001
            value = None
        out = ("done", False, value, f"{type(e).__name__}: {e}", tb)
    if helper.after_call:
        _hook(helper.after_call, "after_call")  # the lane's last word before the answer goes (ioPix: its Progress)
    return out


def _read() -> None:
    """The pipe, read as the messages come: the work queued for the main thread, everything else answered here."""
    while True:
        try:
            msg = _conn.recv()
        except (EOFError, OSError):
            os._exit(0)  # the copy closed its end, or is gone: nothing here outlives it
        kind = msg[0]
        if kind == "exit":
            os._exit(0)
        elif kind == "prepare":
            _prepare(msg[1])
        elif kind == "note":
            if helper.on_note:
                _hook(helper.on_note, "on_note", msg[1])
        elif kind == "run":
            if helper.before_call:
                _hook(helper.before_call, "before_call", msg[5] if len(msg) > 5 else None)
            _runs.put(msg)


def main(fd: int) -> None:
    global _conn
    _conn = child.connection(fd)
    helper.worker_send = send
    child.first_to_go()        # when memory runs out, the kernel stops this process before the copy
    child.log_to_parent(send)  # its log lines go to the copy, which writes them where its own go
    threading.Thread(target=_read, name="helper-read", daemon=True).start()
    while True:
        msg = _runs.get()
        out = _run(msg[1], msg[2], msg[3], msg[4])
        try:
            send(out)
        except Exception as e:  # noqa: BLE001  a result that does not pickle: a programming error, said there
            send(("done", False, None, f"the result could not be sent back ({type(e).__name__}: {e})", ""))


if __name__ == "__main__":
    main(int(sys.argv[1]))

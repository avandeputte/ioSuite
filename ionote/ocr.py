"""Text in pictures for notes made in the web app (RapidOCR).

The Mac and iPhone apps read the text themselves with Apple's Vision framework and send it as ocrText, so the
server only does this for pictures added in the browser. One background thread works through a queue; the
text lands in notes.ocr_text, which MariaDB's full-text index covers. The reading itself is the suite's
(iosuite_shared.ocr.rapid_read: the model, a few hundred MB once loaded, and onnxruntime) and runs in the suite's
helper process (iosuite_shared.helper), so the model leaves memory when there is nothing to read and a crash in it
never takes the copy down.
"""
import logging
import queue
import threading

from iosuite_shared import helper, ocr as shared

from ionote import images, notes

log = logging.getLogger("ionote.ocr")
TIMEOUT = 300  # seconds one picture may take (the model is loaded on the first)
_q = queue.Queue()
_queued = set()  # ids waiting in _q: a note queued twice is read once
_qlock = threading.Lock()
_thread = None
_failed = None


available = shared.rapid_available
_read = shared.rapid_read


def status() -> dict:
    return {"installed": available(), "queued": _q.qsize(), "error": _failed}


def _work():
    global _failed
    while True:
        item = _q.get()
        with _qlock:
            _queued.discard(item)
        try:
            if isinstance(item, tuple):  # ("att", id): a picture attached to a note
                from ionote import attachments
                got = attachments.raw_for_ocr(item[1])
                if got:
                    text = helper.call(_read, got[0], timeout=TIMEOUT)
                    if text:
                        attachments.set_text(item[1], text, got[1])
                        log.info("read %d characters of text in attachment %s", len(text), item[1])
            else:
                got = images.get(item)
                if got:
                    text = helper.call(_read, got[0], timeout=TIMEOUT)
                    if text:
                        notes.set_ocr_text(item, text, got[2])
                        log.info("read %d characters of text in the picture of %s", len(text), item)
            _failed = None
        except Exception as e:
            _failed = f"{type(e).__name__}: {e}"[:300]
            log.warning("text recognition failed for %s: %s", item, _failed)
        finally:
            _q.task_done()


def _start():
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_work, name="ocr", daemon=True)
        _thread.start()


def _put(item) -> bool:
    if not available():
        return False
    _start()
    with _qlock:
        if item not in _queued:
            _queued.add(item)
            _q.put(item)
    return True


def enqueue_attachment(att_uid: str) -> bool:
    """Read the text in a picture attached to a note, in the background; False when RapidOCR is not installed."""
    return _put(("att", att_uid))


def enqueue(uid: str) -> bool:
    """Read the text in this note's picture in the background; False when RapidOCR is not installed."""
    return _put(uid)

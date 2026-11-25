"""The module the heavy lane's test names (helper.Heavy): in the helper it registers the lane's hooks, and it holds
the functions the test sends there."""
import os
import time

from iosuite_shared import helper

seen = {"setup": None, "notes": []}


def _begin(setup):
    """helper.before_call: what the copy sent with the call, in the helper before the function runs."""
    seen["setup"] = setup
    seen["notes"].clear()


def _after():
    """helper.after_call: the helper's last word before the answer goes back."""
    helper.emit(("after", seen["setup"]))


def _note(msg):
    """helper.on_note: what the copy says to the call while it runs."""
    seen["notes"].append(msg)


if helper.IN_WORKER:
    helper.before_call, helper.after_call, helper.on_note = _begin, _after, _note


def what(a):
    """What the copy sent with the call, which process this is, and the call's own argument."""
    return seen["setup"], os.getpid(), a


def until_told(limit: float = 15.0):
    """Runs until the copy sends a note (or `limit` seconds pass); gives back the notes it heard."""
    end = time.time() + limit
    while time.time() < end and not seen["notes"]:
        time.sleep(0.02)
    return list(seen["notes"])


def boom():
    raise ValueError("no good")

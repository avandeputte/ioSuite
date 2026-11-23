"""ioTask, when it is part of the suite: the tasks that are due show on their day, beside the events, and are ticked
off from the calendar.

Nothing to set up: ioTask is found in the suite's list of apps. Unlike the contacts (iocalendar/contacts.py), tasks are asked
for on the viewer's behalf: the request goes out from this server with the viewer's own credentials (the suite's shared
session cookie, or the Authorization header they came with), so ioTask answers with the lists that person sees there
and takes a tick only from someone who may change the list. Nothing is kept here.

ioTask is asked on the viewer's behalf (iosuite_shared.links.as_viewer: localhost on this machine, its
address inside the network, its public one), with the suite's Cloudflare Access service token when one is set. One
that did not answer is left alone for links.BREAK_S seconds, so a calendar without its tasks draws at once.
"""
import datetime as dt
import re

from fastapi import Request
from iosuite_shared import links

PROVIDER = "iotask"
TIMEOUT = 5    # seconds, per request
MAX_TASKS = 2000


_app = links.App(PROVIDER, asker="ioCalendar", timeout=TIMEOUT)  # ioTask, asked as the viewer (iosuite_shared.links.App)
Unavailable = links.Unavailable  # ioTask could not be asked, or would not answer: (status, why)
enabled, url, forget, ask = _app.enabled, _app.url, _app.forget, _app.ask


def _tz(tz: str | None) -> str | None:
    return tz if tz and re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz) else None


def between(request: Request, start: dt.date, end: dt.date, tz: str | None = None) -> list[dict]:
    """The tasks due from start up to end (end not included), open and done, over the lists the viewer sees in ioTask:
    [{id, title, due, allDay, done, listId, list, color, writable, priority, members (ids), repeats}], by day, the ones without a time first."""
    q = {"status": "all", "from": start.isoformat(), "to": (end - dt.timedelta(days=1)).isoformat(), "limit": MAX_TASKS}
    if _tz(tz):
        q["tz"] = tz
    lists = {c["id"]: c for c in ask(request, "/api/lists").get("items", [])}
    out = []
    for t in ask(request, "/api/tasks", q).get("items", []):
        due = t.get("due")
        # a day (or a time) to show it on; the days are checked here too (an ioTask from before from= and to= sends every task)
        if not due or not (start - dt.timedelta(days=1)).isoformat() <= due[:10] <= end.isoformat():
            continue
        c = lists.get(t.get("listId")) or {}
        out.append({"id": t.get("id"), "title": t.get("title") or "(no title)", "due": due, "allDay": bool(t.get("dueAllDay")),
                    "done": bool(t.get("done")), "listId": t.get("listId"), "list": c.get("name"), "color": c.get("color"),
                    "writable": bool(c.get("writable")), "priority": t.get("priority"),
                    "members": [m.get("id") for m in t.get("members") or []],
                    "repeats": bool(t.get("rrule") or t.get("repeatAfter"))})
    out.sort(key=lambda t: (t["due"][:10], not t["allDay"], t["due"], t["title"].lower()))
    return out


def complete(request: Request, tid: int, done: bool = True, tz: str | None = None) -> dict:
    """Tick a task off (or open it again) in ioTask, as the viewer: {done, due, moved, title}. moved: a repeating task
    went on to its next day (due) instead of closing."""
    body = {"done": bool(done)}
    if _tz(tz):
        body["tz"] = tz
    t = ask(request, f"/api/tasks/{int(tid)}/complete", body=body)
    return {"id": t.get("id"), "title": t.get("title"), "done": bool(t.get("done")), "due": t.get("due"),
            "allDay": bool(t.get("dueAllDay")), "moved": bool(t.get("moved"))}

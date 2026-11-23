"""ioDocs, when it is part of the suite: the day a passport, a driver's license or an insurance policy expires shows
on the calendar, beside the events.

Nothing to set up: ioDocs is found in the suite's list of apps. As with the bills (iocalendar/bills.py), the documents are
asked for on the viewer's behalf (iosuite_shared.links.as_viewer, with the viewer's own credentials), so each person
sees only the documents ioDocs shows them. Nothing is kept here.
"""
import datetime as dt

from fastapi import Request
from iosuite_shared import links

PROVIDER = "iodocs"
TIMEOUT = 5  # seconds, per request


_app = links.App(PROVIDER, asker="ioCalendar", timeout=TIMEOUT, no_role="No role in ioDocs", own_word=False)  # ioDocs, asked as the viewer
Unavailable = links.Unavailable  # ioDocs could not be asked, or would not answer: (status, why)
enabled, url, forget = _app.enabled, _app.url, _app.forget


def between(request: Request, start: dt.date, end: dt.date) -> list[dict]:
    """The documents the viewer sees in ioDocs that expire from start up to end (end not included):
    [{id, day, title, kind, members: [family member ids]}], by day."""
    q = {"start": start.isoformat(), "end": (end - dt.timedelta(days=1)).isoformat()}
    got = _app.ask(request, "/api/expiring", q)
    out = []
    for d in got.get("items", []):
        day = str(d.get("expiresOn") or "")[:10]
        if not start.isoformat() <= day < end.isoformat():
            continue
        out.append({"id": d.get("id"), "day": day, "title": d.get("title") or "Document", "kind": d.get("kindLabel") or "",
                    "members": [p["id"] for p in d.get("people") or [] if isinstance(p, dict) and isinstance(p.get("id"), int)]})
    out.sort(key=lambda d: (d["day"], d["title"].lower()))
    return out

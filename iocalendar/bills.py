"""ioMoney, when it is part of the suite: the household's coming bills (the recurring transactions ioMoney keeps: the
power bill, the mortgage, a subscription, a paycheck) show on the day they are due, beside the events.

Nothing to set up: ioMoney is found in the suite's list of apps. As with the tasks (iocalendar/tasks.py), the bills are asked
for on the viewer's behalf (iosuite_shared.links.as_viewer, with the viewer's own credentials), so ioMoney answers only
to someone with a role there, with the bills of the accounts that person sees. Anyone else simply has no bills on the
calendar: ioMoney's money is shown only to those it is shown to there. Nothing is kept here.
"""
import datetime as dt

from fastapi import Request
from iosuite_shared import links

PROVIDER = "iomoney"
TIMEOUT = 5  # seconds, per request


_app = links.App(PROVIDER, asker="ioCalendar", timeout=TIMEOUT, no_role="No role in ioMoney", own_word=False)  # ioMoney, asked as the viewer
Unavailable = links.Unavailable  # ioMoney could not be asked, or would not answer: (status, why)
enabled, url, forget = _app.enabled, _app.url, _app.forget


def _provider(p) -> dict | None:
    """The provider's details as ioMoney gave them: text only, and a website only when it is a web address."""
    if not isinstance(p, dict):
        return None
    out = {k: str(p[k])[:500] for k in ("accountNumber", "phone", "website", "note") if p.get(k)}
    if "website" in out and not out["website"].lower().startswith(("https://", "http://")):
        del out["website"]
    return out or None


def between(request: Request, start: dt.date, end: dt.date) -> list[dict]:
    """The bills due from start up to end (end not included) that the viewer sees in ioMoney:
    [{id, day, merchant, amount, currency, approximate, frequency, category, account, paid, transactionId: the ioMoney
    transaction that paid it (its links show on the bill's card), or None, subscription, provider: {accountNumber,
    phone, website, note} kept in ioMoney for the one billing it, or None}], by day."""
    q = {"start": start.isoformat(), "end": (end - dt.timedelta(days=1)).isoformat()}
    got = _app.ask(request, "/api/bills", q)
    out = []
    for b in got.get("items", []):
        day = str(b.get("day") or "")[:10]
        if not start.isoformat() <= day < end.isoformat():
            continue
        out.append({"id": b.get("id"), "day": day, "merchant": b.get("merchant") or "Bill", "amount": b.get("amount"),
                    "currency": b.get("currency") or got.get("currency"), "approximate": bool(b.get("approximate")),
                    "frequency": b.get("frequency"), "category": b.get("category"), "account": b.get("account"),
                    "paid": bool(b.get("paid")), "transactionId": b.get("transactionId"),
                    "subscription": bool(b.get("subscription")), "provider": _provider(b.get("provider"))})
    out.sort(key=lambda b: (b["day"], (b["merchant"] or "").lower()))
    return out

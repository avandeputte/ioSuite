"""Recurring transactions, and the bills ioCalendar shows."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from iosuite_shared import users as shared_users
from iosuite_shared.access import json_body
from iosuite_shared.errors import Invalid

from iomoney import access, model, recurring
from iomoney.routes.common import month_bounds, _u

router = APIRouter()


@router.get("/api/recurring", dependencies=[access.signed_in])
def list_recurring(request: Request):
    """The household's recurring transactions (each with its next date, the last payment and its flag: a payment
    missed, or one whose amount changed), and what was found in
    the transactions that looks recurring and is not in the list (found), with whether you may change them."""
    u = _u(request)
    return {"items": recurring.items(u), "found": recurring.found(u), "writable": shared_users.can_write(u),
            "frequencies": [{"value": f, "label": recurring.FREQ_LABEL[f]} for f in recurring.FREQS]}


@router.post("/api/recurring", dependencies=[access.signed_in])
async def add_recurring(request: Request):
    """{name, pattern (words its payee or bank's text has; the name as left out), accountId?, flow: out|in, amount,
    approximate?, frequency, day (a day it fell on), category?}; or {found: key}: what was found, added."""
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(lambda: recurring.add_found(u, b["found"]) if b.get("found") else recurring.create(u, b))
    return JSONResponse(recurring.public(r, u), status_code=201)


@router.post("/api/recurring/not", dependencies=[access.signed_in])
async def not_recurring(request: Request):
    """{key}: what was found is not recurring; not offered again."""
    u = _u(request)
    b = await json_body(request)
    recurring.dismiss(u, b.get("key"))
    return {"ok": True}


@router.patch("/api/recurring/{rid}", dependencies=[access.signed_in])
async def change_recurring(rid: int, request: Request):
    u = _u(request)
    b = await json_body(request)
    return recurring.public(recurring.update(u, recurring.item(u, rid), b), u)


@router.post("/api/recurring/{rid}/ok", dependencies=[access.signed_in])
async def recurring_flag_ok(rid: int, request: Request):
    """{kind: missed|changed, day}: the item's flag (as its flag gives them) looked at: not shown again for that day."""
    u = _u(request)
    b = await json_body(request)
    r = recurring.item(u, rid)
    recurring.set_aside(u, r, b)
    return recurring.public(r, u)


@router.get("/api/transactions/{tid}/recurring", dependencies=[access.signed_in])
def transaction_recurring(tid: int, request: Request):
    """The recurring transaction this one is (item), or one to add from it (suggestion: how often and the usual
    amount from the transactions like it), with whether you may change it."""
    u = _u(request)
    t = model.transaction(u, tid)
    out = recurring.for_transaction(u, t)
    a = model.account_row(t["account_id"])
    out["writable"] = shared_users.can_write(u) if a["owner_id"] is None else model.can_write(u, a)
    out["frequencies"] = [{"value": f, "label": recurring.FREQ_LABEL[f]} for f in recurring.FREQS]
    return out


@router.delete("/api/recurring/{rid}", dependencies=[access.signed_in])
def remove_recurring(rid: int, request: Request):
    u = _u(request)
    recurring.delete(u, recurring.item(u, rid))
    return {"ok": True}


@router.get("/api/bills", dependencies=[access.signed_in])
def list_bills(request: Request, start: str = None, end: str = None):
    """Each date a recurring transaction falls on between start and end (YYYY-MM-DD; this month as left out), paid
    or not, those of your private accounts included: what ioCalendar shows on their days."""
    if not (start and end):
        start, end = month_bounds(None)
    s, e = model.day(start), model.day(end)
    if (e - s).days > 400:
        raise Invalid("At most 400 days at a time")
    return {"currency": model.home_currency(), "items": recurring.bills(_u(request), s, e)}

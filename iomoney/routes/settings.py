"""Monarch Money and the settings (admins)."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from iosuite_shared.http import json_body
from iosuite_shared.errors import Invalid

from iomoney import access, db, model, monarch, quotes
from iomoney.routes.common import _u

router = APIRouter()


@router.get("/api/monarch", dependencies=[access.admin])
def monarch_status():
    """Whether the sign-in is kept (Keys and tokens; never the values), the last syncs and how they went."""
    return monarch.status()


@router.post("/api/monarch/sync", dependencies=[access.admin])
async def monarch_sync(request: Request):
    """{full?: true (the past two years of transactions again), accountId?: just this Monarch account's
    transactions again, years?: how far back for it (2 as left out; 0: all Monarch has), wait?: seconds (10 as left out, at most 60)}: start copying Monarch Money in, in the background. When it ends within wait: how it went ({ok, message, ...}); else
    {running: true, progress: {stage, count, started}}, and GET /api/monarch says how it goes and, at the end, how
    it went (last)."""
    b = await json_body(request) if (request.headers.get("content-length") or "0") != "0" else {}
    wait = max(0.0, min(float(b.get("wait", 10) or 0), 60.0))
    only = None
    if b.get("accountId"):
        a = model.account_row(b["accountId"])
        if not model.can_read(_u(request), a) or a["source"] != "monarch":
            raise Invalid("The account: one from Monarch Money")
        only = a["id"]
    try:
        years = max(0, min(int(b.get("years", 2)), 30))
    except (TypeError, ValueError):
        raise Invalid("How far back: a number of years, or 0 for all")
    return await run_in_threadpool(monarch.start, _u(request)["id"], bool(b.get("full")), wait, only, years)


@router.get("/api/monarch/new", dependencies=[access.admin])
def monarch_new():
    """The accounts Monarch Money reported that ioMoney did not know (after the first sync): they wait, with their
    transactions, until an admin says whether each is new or an account here made again in Monarch under a new id.
    Each comes with the accounts here it could be, likeliest first (candidates; likely: the id of a sure one)."""
    return {"items": monarch.held()}


@router.post("/api/monarch/new/{ext}", dependencies=[access.admin])
async def monarch_new_decide(ext: str, request: Request):
    """{as: 'new', private?: true (yours alone, not the household's)} or {as: 'existing', accountId}, wait?: seconds: what a waiting account is. A sync starts right away
    (its result as it ends within wait, as for POST /api/monarch/sync): a new account comes in with its history; an
    existing one takes the new id, and its transactions are matched with those kept, so none is there twice."""
    b = await json_body(request)
    r = monarch.decide(ext, str(b.get("as") or ""), b.get("accountId"), _u(request)["id"], private=bool(b.get("private")))
    wait = max(0.0, min(float(b.get("wait", 0) or 0), 60.0))
    r["sync"] = await run_in_threadpool(monarch.start, _u(request)["id"], False, wait)
    return r


@router.post("/api/monarch/code", dependencies=[access.admin])
async def monarch_code(request: Request):
    """{code}: sign in to Monarch with a six-digit code from the authenticator app (when no authenticator key is kept)."""
    b = await json_body(request)
    try:
        await run_in_threadpool(monarch.sign_in_with_code, str(b.get("code") or ""))
    except monarch.NeedsSignIn as e:
        raise Invalid(str(e))
    return monarch.status()


@router.delete("/api/monarch/session", dependencies=[access.admin])
def monarch_forget():
    """Forget the kept Monarch session: the next sync signs in again."""
    monarch.forget_session()
    return monarch.status()


@router.get("/api/settings", dependencies=[access.signed_in])
def get_settings():
    """The household's currency (what the totals are in) and whether Monarch Money is synced on its own."""
    return {"currency": model.home_currency(), "monarchAuto": model.setting("monarch_auto", "1") == "1"}


@router.put("/api/settings", dependencies=[access.admin])
async def put_settings(request: Request):
    """{currency?: 'USD', monarchAuto?: bool} (admins)."""
    b = await json_body(request)
    if "currency" in b:
        cur = model.currency(b["currency"])
        db.set_setting("currency", cur)
        await run_in_threadpool(quotes.refresh)
    if "monarchAuto" in b:
        db.set_setting("monarch_auto", "1" if b["monarchAuto"] else "0")
    return get_settings()

"""Holdings and quotes: what an investment account holds, and what it is worth."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from iosuite_shared.access import json_body
from iosuite_shared.errors import Invalid

from iomoney import access, holdings, model, quotes
from iomoney.routes.common import _u

router = APIRouter()


@router.get("/api/portfolio", dependencies=[access.signed_in])
def portfolio(request: Request, account: int = None):
    """Every holding you see, priced, with the day's change, the gain over the cost basis, the totals, the same symbol
    added up across accounts, and the allocation by kind."""
    return holdings.portfolio(_u(request), account)


@router.post("/api/accounts/{aid}/holdings", dependencies=[access.signed_in])
async def add_holding(aid: int, request: Request):
    """{symbol (as Yahoo Finance writes it: AAPL, VWCE.DE, BTC-USD), shares, costBasis? (paid for all of them),
    kind?, name?, price? (for something without a symbol)}, in a manual investment account."""
    u = _u(request)
    b = await json_body(request)
    h = await run_in_threadpool(lambda: holdings.create_holding(u, model.account(u, aid), b))
    if h["symbol"]:
        await run_in_threadpool(quotes.refresh, False, [h["symbol"]])
        await run_in_threadpool(holdings.revalue_manual_investments)
    return JSONResponse({"id": h["id"]}, status_code=201)


@router.patch("/api/holdings/{hid}", dependencies=[access.signed_in])
async def change_holding(hid: int, request: Request):
    u = _u(request)
    b = await json_body(request)
    h = await run_in_threadpool(lambda: holdings.update_holding(u, holdings.holding(u, hid), b))
    if h["symbol"]:
        await run_in_threadpool(quotes.refresh, False, [h["symbol"]])
    await run_in_threadpool(holdings.revalue_manual_investments)
    return {"id": h["id"]}


@router.delete("/api/holdings/{hid}", dependencies=[access.signed_in])
def delete_holding(hid: int, request: Request):
    u = _u(request)
    h = holdings.holding(u, hid)
    holdings.delete_holding(u, h)
    holdings.revalue_manual_investments(h["account_id"])
    return {"ok": True}


@router.get("/api/quotes/{sym}", dependencies=[access.signed_in])
async def get_quote(sym: str, request: Request, days: int = 365):
    """One symbol's quote (asked of Yahoo Finance when it is not fresh) and its closing prices."""
    if model.role_rank(_u(request)) < 1:
        raise HTTPException(403, "You have no role in ioMoney")
    s = model.symbol(sym)
    if not s:
        raise Invalid("Name a symbol")
    q = await run_in_threadpool(quotes.quote, s)
    return {**q, "closes": quotes.closes(s, max(7, min(days, 400)))}


@router.post("/api/quotes/refresh", dependencies=[access.signed_in])
async def refresh_quotes(request: Request):
    """Ask Yahoo Finance again for every quote that is more than a minute old."""
    if model.role_rank(_u(request)) < 1:
        raise HTTPException(403, "You have no role in ioMoney")

    def go():
        old = quotes.QUOTE_S
        quotes.QUOTE_S = 60
        try:
            got = quotes.refresh()
        finally:
            quotes.QUOTE_S = old
        holdings.revalue_manual_investments()
        return got
    return await run_in_threadpool(go)

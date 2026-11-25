"""The accounts: the list, one account, its balances over time, who else sees a private one."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from iosuite_shared.http import json_body
from iosuite_shared.errors import Invalid

from iomoney import access, forecast, model, payoff
from iomoney.routes.common import _u

router = APIRouter()


@router.get("/api/accounts", dependencies=[access.signed_in])
def list_accounts(request: Request, hidden: bool = False, kind: str = None, q: str = "", things: bool = False, limit: int = 500):
    """The accounts you see, the house and the cars among them. hidden: also the hidden ones; kind: one kind;
    things: only what has a value (real estate, vehicles, other assets); q: words in the name or the institution."""
    u = _u(request)
    rows = model.accounts(u, hidden=hidden, kind=kind)
    if things:
        rows = [a for a in rows if a["kind"] in model.THINGS]
    for w in q.lower().split():
        rows = [a for a in rows if w in f"{a['name']} {a['institution'] or ''} {a['subtype'] or ''}".lower()]
    rows = rows[:max(1, min(limit, 1000))]
    links = model.bank_links([a["id"] for a in rows if a["source"] == "monarch"])
    return {"items": [model.account_public(a, u, links=links) for a in rows]}


@router.get("/api/people", dependencies=[access.signed_in])
def list_people(request: Request):
    """Who a private account may be shown to: the people with a role here, [{id, name}], you first."""
    u = _u(request)
    if model.role_rank(u) < 1:
        return {"items": []}
    return {"items": model.candidates(u)}


@router.post("/api/accounts", dependencies=[access.signed_in])
async def add_account(request: Request):
    """{name, kind (cash, investment, property, vehicle, other_asset, credit, loan, other_liability), balance?,
    currency?, institution?, subtype?, mask?, inNetWorth?, hidden?, details? (a house or a car: address, year, make,
    model, vin, mileage, boughtOn, boughtFor, yearlyRate, notes), loanId?, household? (true: the household's, editors;
    false: your own), people? (your own: the ids of the others who see it, from GET /api/people)}."""
    u = _u(request)
    b = await json_body(request)
    a = await run_in_threadpool(model.create_account, u, b)
    return JSONResponse(model.account_public(a, u), status_code=201)


@router.get("/api/accounts/{aid}", dependencies=[access.signed_in])
def get_account(aid: int, request: Request):
    u = _u(request)
    return model.account_public(model.account(u, aid), u)


@router.patch("/api/accounts/{aid}", dependencies=[access.signed_in])
async def change_account(aid: int, request: Request):
    """Change the fields given (as POST /api/accounts). An account from Monarch Money takes only its name, hidden, in
    the net worth, the details, the loan, household, people and flagStale (false: do not flag its link to the bank as
    behind). people: who else sees a private account (ids); only its owner sets it, and nobody else sees it, an admin
    included."""
    u = _u(request)
    b = await json_body(request)
    a = await run_in_threadpool(lambda: model.update_account(u, model.account(u, aid), b))
    return model.account_public(a, u)


@router.delete("/api/accounts/{aid}", dependencies=[access.signed_in])
def delete_account(aid: int, request: Request):
    u = _u(request)
    model.delete_account(u, model.account(u, aid))
    return {"ok": True}


@router.get("/api/accounts/{aid}/info", dependencies=[access.signed_in])
def get_account_info(aid: int, request: Request):
    """What is kept to deal with the account's bank: accountNumber, routingNumber, iban, swift, phone, phoneAbroad,
    website, email, address, username, openedOn, notes (those set only)."""
    u = _u(request)
    return model.account_info(u, model.account(u, aid))


@router.put("/api/accounts/{aid}/info", dependencies=[access.signed_in])
async def put_account_info(aid: int, request: Request):
    """Change the fields given (an empty one is removed); for whoever may change the account."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(lambda: model.set_account_info(u, model.account(u, aid), b))


@router.get("/api/accounts/{aid}/forecast", dependencies=[access.signed_in])
def account_forecast(aid: int, request: Request, days: int = forecast.DAYS):
    """The account's balance over the coming days (7 to 366), from its recurring transactions and the transfers it
    makes at a steady pace: the events with the balance after each, a point a day, the lowest point, and whether it
    goes under the balance it should not go under (details.floor, set with PATCH /api/accounts/{id}; zero without)."""
    u = _u(request)
    return forecast.forecast(u, model.account(u, aid), days)


@router.get("/api/accounts/{aid}/payoff", dependencies=[access.signed_in])
def account_payoff(aid: int, request: Request, extra: str = None):
    """A loan's payoff from its interest rate and monthly payment (details.rate in percent a year and details.payment,
    set with PATCH /api/accounts/{id}; the payment is worked out from the balance's history when not given): when it
    is paid off, the interest still to pay, and with extra (more paid a month) what that saves."""
    u = _u(request)
    a = model.account(u, aid)
    if a["is_asset"]:
        raise Invalid("A payoff is for what is owed: a loan or a card")
    return payoff.payoff(u, a, extra)


@router.get("/api/forecast", dependencies=[access.signed_in])
def forecast_warnings(request: Request, days: int = 30):
    """The cash accounts you see that would go under their lowest balance in the coming days (30 as left out)."""
    return {"items": forecast.warnings(_u(request), days)}


@router.get("/api/accounts/{aid}/history", dependencies=[access.signed_in])
def account_history(aid: int, request: Request, days: int = 365):
    """The account's value day by day, in the household's currency (a liability as a negative number)."""
    u = _u(request)
    a = model.account(u, aid)
    return {"items": model.history(u, days, account_id=a["id"])}


@router.get("/api/accounts/{aid}/values", dependencies=[access.signed_in])
def account_values(aid: int, request: Request):
    """The values kept for the account, the latest first: from Monarch, typed in (with a note), or estimated."""
    u = _u(request)
    a = model.account(u, aid)
    return {"items": model.valuations(u, a)}


@router.post("/api/accounts/{aid}/values", dependencies=[access.signed_in])
async def add_value(aid: int, request: Request):
    """{value, day? (today), note?}: what the house or the car (or any manual account) was worth on a day."""
    u = _u(request)
    b = await json_body(request)
    a = model.account(u, aid)
    await run_in_threadpool(model.add_valuation, u, a, b)
    return model.account_public(model.account(u, aid), u)


@router.delete("/api/accounts/{aid}/values/{day}", dependencies=[access.signed_in])
def remove_value(aid: int, day: str, request: Request):
    u = _u(request)
    model.remove_valuation(u, model.account(u, aid), day)
    return {"ok": True}

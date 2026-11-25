"""The household's rules: renaming and categorizing transactions as they come in."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from iosuite_shared.http import json_body

from iomoney import access, model
from iomoney.routes.common import month_bounds, _u

router = APIRouter()


@router.get("/api/rules", dependencies=[access.signed_in])
def list_rules(request: Request):
    """The household's rules, in the order they are tried: each renames the payee, sets the category or hides the
    transactions whose payee or bank's text matches. Anyone with a role sees them; editors change them."""
    u = _u(request)
    return {"items": [model.rule_public(r, u) for r in model.rules(u)], "writable": model.may_add(u, True)}


@router.post("/api/rules", dependencies=[access.signed_in])
async def add_rule(request: Request):
    """{pattern, field? (either, merchant, description), how? (contains, is, starts), accountId?, flow? (out, in),
    amountMin?, amountMax?, setMerchant?, setCategory?, setHidden?, enabled?, apply? (true: run it over the
    transactions you have now, except those changed by hand)}."""
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(model.create_rule, u, b)
    out = model.rule_public(r, u)
    if b.get("apply"):
        out["changed"] = await run_in_threadpool(model.apply_rules)  # all of them, so their order holds
    return JSONResponse(out, status_code=201)


@router.post("/api/rules/test", dependencies=[access.signed_in])
async def test_rule(request: Request):
    """{pattern, field?, how?, accountId?, flow?, amountMin?, amountMax?}: the transactions it matches (count, how
    many of them were changed by hand and so stay as they are, and the newest few). Nothing is kept or changed."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(model.try_rule, u, b)


@router.post("/api/rules/apply", dependencies=[access.signed_in])
async def apply_rules(request: Request):
    """Every rule over every transaction (except those changed by hand): how many changed."""
    u = _u(request)
    return {"changed": await run_in_threadpool(model.apply_all_rules, u)}


@router.put("/api/rules/order", dependencies=[access.signed_in])
async def order_rules(request: Request):
    """{ids: [the rules' ids, in the order they are tried]}."""
    u = _u(request)
    b = await json_body(request)
    rs = await run_in_threadpool(model.order_rules, u, b.get("ids"))
    return {"items": [model.rule_public(r, u) for r in rs]}


@router.patch("/api/rules/{rid}", dependencies=[access.signed_in])
async def change_rule(rid: int, request: Request):
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(lambda: model.update_rule(u, model.rule(u, rid), b))
    out = model.rule_public(r, u)
    if b.get("apply"):
        out["changed"] = await run_in_threadpool(model.apply_rules)  # all of them, so their order holds
    return out


@router.delete("/api/rules/{rid}", dependencies=[access.signed_in])
def delete_rule(rid: int, request: Request):
    u = _u(request)
    model.delete_rule(u, model.rule(u, rid))
    return {"ok": True}


@router.get("/api/spending", dependencies=[access.signed_in])
def spending(request: Request, month: str = None, start: str = None, end: str = None):
    """Money out and in by category, for a month (YYYY-MM; this month as left out) or between start and end."""
    if not (start and end):
        start, end = month_bounds(month)
    return model.spending(_u(request), start, end)


@router.get("/api/cashflow", dependencies=[access.signed_in])
def cashflow(request: Request, months: int = 12):
    """Money in and out month by month (transfers left out), the current month last."""
    return {"currency": model.home_currency(), "items": model.cash_flow(_u(request), months)}

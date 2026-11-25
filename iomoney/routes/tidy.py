"""Putting the data in order: what needs a look, duplicates, payees, categories, tags, statements and the files a
bank gives."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from iosuite_shared import users as shared_users
from iosuite_shared.http import json_body

from iomoney import (access, balancecheck, duplicates, history, importer, model, payees, review, rulecheck, searches,
                     statementfile, statements, tags, transfers)
from iomoney.routes.common import _u

router = APIRouter()


@router.get("/api/tidy", dependencies=[access.signed_in])
def tidy(request: Request):
    """What there is to put in order, in a few numbers: review (transactions that need a look), duplicates (likely
    ones), transfers (pairs to check), balanceGaps (accounts whose balance and transactions disagree), payees, tags,
    changes (kept changes of the past month)."""
    u = _u(request)
    if model.role_rank(u) < 1:
        return {"review": 0, "duplicates": 0, "transfers": 0, "balanceGaps": 0, "payees": 0, "tags": 0}
    return {"review": review.count(u), "duplicates": duplicates.count(u), "transfers": len(transfers.possible(u)),
            "balanceGaps": balancecheck.check(u)["gaps"], "payees": payees.items(u, limit=1)["total"], "tags": len(tags.items(u))}


@router.get("/api/payees", dependencies=[access.signed_in])
def list_payees(request: Request, q: str = "", limit: int = 500):
    """The payees of the transactions you see, the most used first: {payee, count, total, last, category (its most
    common one), categories (how many different ones), rule (the rule that sets its category)}. q: words in the name."""
    u = _u(request)
    return {**payees.items(u, q, limit), "writable": shared_users.can_write(u)}


@router.post("/api/payees/rename", dependencies=[access.signed_in])
async def rename_payee(request: Request):
    """{name, newName}: the payee under another name, in every transaction and from now on (a rule); a name another
    payee has merges the two (editors). {changed, rule}."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(payees.rename, u, b)


@router.post("/api/payees/category", dependencies=[access.signed_in])
async def payee_category(request: Request):
    """{name, category, all?}: the payee's usual category: a rule from now on, and its transactions there are (those
    not changed by hand; all: those too) (editors). {changed, rule}."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(payees.set_category, u, b)


@router.get("/api/tags", dependencies=[access.signed_in])
def list_tags(request: Request):
    """Every tag on the transactions you see: {tag, count, total, own (set here, not Monarch's)}."""
    u = _u(request)
    return {"items": tags.items(u), "writable": shared_users.can_write(u)}


@router.put("/api/tags", dependencies=[access.signed_in])
async def rename_tag(request: Request):
    """{name, newName}: one of the tags set here under another name (one there is: the two merged) (editors)."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(tags.rename, u, b)


@router.post("/api/tags/delete", dependencies=[access.signed_in])
async def delete_tag(request: Request):
    """{name}: one of the tags set here off every transaction (editors)."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(tags.delete, u, b)


@router.get("/api/duplicates", dependencies=[access.signed_in])
def likely_duplicates(request: Request):
    """Transactions that look like one kept twice: the same account and amount, at most three days apart, and alike.
    Each group {why, whyText, items}; keep one and hide or delete the other, or say they are two (POST
    /api/duplicates/not)."""
    return {"items": duplicates.groups(_u(request))}


@router.post("/api/duplicates/not", dependencies=[access.signed_in])
async def not_duplicates(request: Request):
    """{ids: [...]}: these are different transactions; not offered again."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(duplicates.dismiss, u, b.get("ids"))


@router.get("/api/accounts/{aid}/statements", dependencies=[access.signed_in])
def account_statements(aid: int, request: Request):
    """The statements the account was reconciled against, and where the next one starts (next: {start, opening})."""
    u = _u(request)
    return statements.of(u, model.account(u, aid))


@router.get("/api/accounts/{aid}/statement", dependencies=[access.signed_in])
def statement_lines(aid: int, request: Request, start: str, end: str):
    """The transactions to tick off against a statement from start to end (YYYY-MM-DD), the hidden ones too, and the
    earlier ones the statement before left open (earlier: true). sign: 1, or -1 for an account of what is owed (there
    money out makes the balance go up)."""
    u = _u(request)
    return statements.lines(u, model.account(u, aid), start, end)


@router.post("/api/accounts/{aid}/statement/read", dependencies=[access.signed_in])
async def read_statement(aid: int, request: Request, name: str | None = None, order: str | None = None, flip: str | None = None):
    """The bank's own file as the request body (up to 20 MB), held against the account: a statement's PDF, or the CSV,
    OFX or QFX file from the bank's website. Nothing is changed and the file is not kept. name: its file name;
    order: how day and month stand in its dates (mdy, dmy, ymd), when the guess is wrong; flip: 1 or 0, whether it
    writes money out as a positive number (as left out: whichever fits). {kind, start, end, opening, closing, worked,
    adds, total, sum, matched: the transactions found (to tick), missing: the lines the account does not have (with
    differs: the transaction of another amount that looks like it), elsewhere: the lines it has outside these days,
    extra: the transactions of these days the file does not show, dateOrder, guessed, flipped}."""
    u = _u(request)
    raw = await request.body()
    return await run_in_threadpool(lambda: statementfile.read(u, model.account(u, aid), raw, name, order, flip))


@router.post("/api/accounts/{aid}/statements", dependencies=[access.signed_in])
async def reconcile_statement(aid: int, request: Request):
    """{start, end, opening, closing, ids: the transactions ticked off, anyway?}: mark them reconciled and keep the
    statement. Refused while the ticked ones do not add up to closing minus opening, unless anyway."""
    u = _u(request)
    b = await json_body(request)
    return JSONResponse(await run_in_threadpool(lambda: statements.save(u, model.account(u, aid), b)), status_code=201)


@router.delete("/api/statements/{sid}", dependencies=[access.signed_in])
def delete_statement(sid: int, request: Request):
    """Forget a statement (its transactions stay reconciled)."""
    statements.remove(_u(request), sid)
    return {"ok": True}


@router.get("/api/balance-check", dependencies=[access.signed_in])
def balance_check(request: Request, days: int = balancecheck.DAYS):
    """For each cash account and card from Monarch Money with a bank behind it: whether its balance moved, over the
    past days, by what its transactions add up to (status ok, waiting, accepted, gap or unknown), the gap, and the
    weeks in which it appeared."""
    return balancecheck.check(_u(request), days)


@router.post("/api/balance-check/{aid}/ok", dependencies=[access.signed_in])
async def balance_gap_ok(aid: int, request: Request):
    """{gap}: the account's gap was looked at and is fine as it is: not flagged while it stays the same ({gap: null}:
    flag it again)."""
    u = _u(request)
    b = await json_body(request)
    return balancecheck.accept(u, model.account(u, aid), b)


@router.get("/api/rules/upkeep", dependencies=[access.signed_in])
def rules_upkeep(request: Request):
    """What each rule does to the transactions of the past two years (matched, decides, last, and note: never, behind
    an earlier rule, or off), and the rules suggested from what was categorized by hand again and again."""
    return rulecheck.upkeep(_u(request))


@router.post("/api/rules/suggestions/not", dependencies=[access.signed_in])
async def not_this_rule(request: Request):
    """{key}: a suggested rule is not wanted; not offered again (editors)."""
    u = _u(request)
    b = await json_body(request)
    return rulecheck.dismiss(u, b.get("key"))


@router.get("/api/transactions/{tid}/changes", dependencies=[access.signed_in])
def transaction_changes(tid: int, request: Request):
    """What was changed by hand on the transaction, the latest first: {id, what (hand, bulk, undo, reset), by, at,
    undone, fields: [{field, before, after}]}."""
    u = _u(request)
    return {"items": history.of(u, model.transaction(u, tid))}


@router.post("/api/transactions/{tid}/reset", dependencies=[access.signed_in])
async def reset_transaction(tid: int, request: Request):
    """A transaction from Monarch Money back to Monarch's own: what was changed here is undone (its own tags and its
    split go), the rules apply again and the next sync refreshes it. The transaction as it is then."""
    u = _u(request)
    await run_in_threadpool(lambda: history.reset(u, model.transaction(u, tid)))
    return model.with_transfers([model.tx_public(model.transaction(u, tid), u)], u)[0]


@router.get("/api/changes", dependencies=[access.signed_in])
def recent_changes(request: Request, limit: int = 100):
    """The latest changes made by hand to the transactions you see; the ones made together (many at once) as one."""
    return {"items": history.recent(_u(request), max(1, min(limit, 300)))}


@router.post("/api/changes/undo", dependencies=[access.signed_in])
async def undo_changes(request: Request):
    """{batch} or {id}: take back the changes made together, or one change: the fields as they were before."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(lambda: history.undo(u, b.get("id"), b.get("batch")))


@router.get("/api/searches", dependencies=[access.signed_in])
def list_searches(request: Request):
    """Your saved searches of the transactions: {id, name, query (the filters, as the page's address has them)}."""
    return {"items": searches.items(_u(request))}


@router.post("/api/searches", dependencies=[access.signed_in])
async def add_search(request: Request):
    """{name, query}: keep a search under a name (a name you have already: that one is replaced)."""
    u = _u(request)
    return JSONResponse(searches.create(u, await json_body(request)), status_code=201)


@router.patch("/api/searches/{sid}", dependencies=[access.signed_in])
async def change_search(sid: int, request: Request):
    """{name?, query?, position?}."""
    u = _u(request)
    return searches.update(u, sid, await json_body(request))


@router.delete("/api/searches/{sid}", dependencies=[access.signed_in])
def delete_search(sid: int, request: Request):
    searches.delete(_u(request), sid)
    return {"ok": True}


@router.post("/api/accounts/{aid}/import", dependencies=[access.signed_in])
async def import_file(aid: int, request: Request):
    """A bank's file into an account kept by hand: {name?, text: the CSV, OFX or QFX file (up to 20 MB), preview?
    (true: add nothing, say what it holds), mapping? (CSV: which column is the date, the amount or debit and credit,
    type, payee, notes, category: numbers from 0), dateOrder? (mdy, dmy, ymd), flip? (money out is written as a
    positive number), duplicates? (true: add what the account has already too), balance? (move: the balance moves by
    what is added; keep; file: the balance an OFX file gives)}. What it holds: kind, columns, mapping, dateOrder,
    total, new, duplicates, problems, from, to, the first rows, and added (how many came in)."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(lambda: importer.run(u, model.account(u, aid), b))

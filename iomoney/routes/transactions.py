"""The transactions: the list and its filters, one transaction, transfers between the household's own accounts,
and the receipts kept with a transaction."""
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from iosuite_shared import users as shared_users
from iosuite_shared.access import json_body

from iomoney import access, categories, model, receipts, review, splits, transfers
from iomoney.routes.common import month_bounds, _u

router = APIRouter()


@router.get("/api/transactions", dependencies=[access.signed_in])
def list_transactions(request: Request, q: str = "", account: int = None, category: str = None, month: str = None,
                      start: str = None, end: str = None, flow: str = None, hidden: bool = False, reconciled: str = None,
                      amount: str = None, receipt: str = None, tag: str = None, review: str = None, limit: int = 100,
                      offset: int = 0):
    """The transactions you see, the newest first. q: words (the payee, the bank's text, the category, the notes;
    $280, 12.50, 100-200, >500 are amounts); account; category ('-': none); month (YYYY-MM) or start and end
    (YYYY-MM-DD); flow: out or in; amount: an amount, money out or in alike (280), or a range (100-200, >500, <20);
    hidden: also those left out of the sums; reconciled: yes or no; receipt: yes (only those with a receipt kept) or
    no; tag: one tag (Monarch's or set here); review: yes (only those that need a look). With total (how many match)
    and sum."""
    u = _u(request)
    if month:
        start, end = month_bounds(month)
    return model.find_transactions(u, q, account, category, start, end, flow, limit, offset, hidden, reconciled, amount, receipt, tag, review)


@router.post("/api/transactions/reconcile", dependencies=[access.signed_in])
async def reconcile_transactions(request: Request):
    """{ids: [...], reconciled: true|false}: mark transactions reconciled (checked against the statement) or not.
    How many were marked (those you may change)."""
    u = _u(request)
    b = await json_body(request)
    ids = b.get("ids") if isinstance(b.get("ids"), list) else []
    return {"changed": await run_in_threadpool(model.set_reconciled, u, ids, model.flag(b.get("reconciled", True)))}


@router.post("/api/transactions/bulk", dependencies=[access.signed_in])
async def change_transactions(request: Request):
    """{ids: [...], set: {category?, merchant?, notes?, hidden?, reconciled?, reviewed?, addTags?, removeTags?}}: the
    same change to many transactions at once (those you may change; at most 2000). {changed, skipped, batch}: the
    batch takes it all back as one (POST /api/changes/undo)."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(model.change_many, u, b.get("ids"), b.get("set") if isinstance(b.get("set"), dict) else {})


@router.post("/api/transactions/review", dependencies=[access.signed_in])
async def review_transactions(request: Request):
    """{ids: [...], reviewed: true|false} or {all: true}: mark transactions as looked at (off the Needs a look list)
    or not. {changed, left: how many still need a look}."""
    u = _u(request)
    b = await json_body(request)
    if b.get("all"):
        n = await run_in_threadpool(review.mark_all, u)
    else:
        ids = b.get("ids") if isinstance(b.get("ids"), list) else []
        n = await run_in_threadpool(review.mark, u, ids, bool(model.flag(b.get("reviewed", True))))
    return {"changed": n, "left": review.count(u)}


@router.post("/api/accounts/{aid}/transactions", dependencies=[access.signed_in])
async def add_transaction(aid: int, request: Request):
    """{day?, amount (negative: money out), merchant?, category?, group?, notes?}, in a manual account."""
    u = _u(request)
    b = await json_body(request)
    t = await run_in_threadpool(lambda: model.create_transaction(u, model.account(u, aid), b))
    return JSONResponse(model.with_transfers([model.tx_public(t, u)], u)[0], status_code=201)


@router.get("/api/transactions/{tid}", dependencies=[access.signed_in])
def get_transaction(tid: int, request: Request):
    """One transaction, as the list gives it (with its transfer, its recurring transaction, its splits, its receipts)."""
    u = _u(request)
    return model.with_transfers([model.tx_public(model.transaction(u, tid), u)], u)[0]


@router.patch("/api/transactions/{tid}", dependencies=[access.signed_in])
async def change_transaction(tid: int, request: Request):
    """{category?, group?, merchant?, notes?, hidden?, reconciled?, reviewed?, tags? (its own tags: a list)} (and day,
    amount in a manual account): kept as changed here, also by the next Monarch sync, and kept in its history."""
    u = _u(request)
    b = await json_body(request)
    t = await run_in_threadpool(lambda: model.update_transaction(u, model.transaction(u, tid), b))
    return model.with_transfers([model.tx_public(t, u)], u)[0]


@router.delete("/api/transactions/{tid}", dependencies=[access.signed_in])
def delete_transaction(tid: int, request: Request):
    u = _u(request)
    model.delete_transaction(u, model.transaction(u, tid))
    return {"ok": True}


@router.get("/api/categories", dependencies=[access.signed_in])
def list_categories(request: Request):
    """Every category (those the transactions have, those added here) with its group and how many transactions."""
    u = _u(request)
    return {"items": model.categories(u), "writable": shared_users.can_write(u)}


@router.post("/api/categories", dependencies=[access.signed_in])
async def add_category(request: Request):
    """{name, group?}: a new category."""
    u = _u(request)
    return JSONResponse(categories.add(u, await json_body(request)), status_code=201)


@router.put("/api/categories", dependencies=[access.signed_in])
async def change_category(request: Request):
    """{name, newName?, group?}: rename it (into one there is already: the two merged) or move it to another group;
    its transactions, rules and recurring transactions follow, and so does what Monarch sends later."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(categories.change, u, b)


@router.post("/api/categories/delete", dependencies=[access.signed_in])
async def delete_category(request: Request):
    """{name, moveTo?}: its transactions take moveTo, or no category."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(categories.delete, u, b)


@router.put("/api/transactions/{tid}/splits", dependencies=[access.signed_in])
async def split_transaction(tid: int, request: Request):
    """{items: [{amount, category?, notes?}]}: split the transaction over categories: two parts and more, each with
    its share (a positive number, or signed as the transaction), together the whole amount; the spending by category
    counts the parts in its place. {items: []}: whole again. The transaction comes back with its splits."""
    u = _u(request)
    b = await json_body(request)
    t = await run_in_threadpool(lambda: splits.put(u, model.transaction(u, tid), b.get("items")))
    return model.with_transfers([model.tx_public(t, u)], u)[0]


@router.post("/api/transactions/{tid}/receipts", dependencies=[access.signed_in])
async def add_receipt(tid: int, request: Request, name: str | None = None):
    """The receipt itself as the request body: a picture (JPEG, PNG, WebP, GIF, HEIC) or a PDF, up to 20 MB. name:
    its file name. The receipt as listed ({id, name, mime, size, url, added})."""
    u = _u(request)
    raw = await request.body()
    return JSONResponse(await run_in_threadpool(lambda: receipts.add(u, model.transaction(u, tid), raw, name)), status_code=201)


@router.get("/api/receipts/{rid}", dependencies=[access.signed_in])
def get_receipt(rid: int, request: Request, download: bool = False):
    """The receipt's file: shown in the browser (download=true: saved)."""
    body, mime, name = receipts.content(_u(request), rid)
    shown = mime in receipts.INLINE and not download
    headers = {"Cache-Control": "private, max-age=3600",
               "Content-Disposition": f"{'inline' if shown else 'attachment'}; filename*=UTF-8''{urllib.parse.quote(name)}"}
    if mime != "application/pdf":  # a browser's PDF viewer does not open in a sandbox; nothing else needs more than this
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return Response(body, media_type=mime if shown else "application/octet-stream", headers=headers)


@router.delete("/api/receipts/{rid}", dependencies=[access.signed_in])
def delete_receipt(rid: int, request: Request):
    receipts.remove(_u(request), rid)
    return {"ok": True}


@router.get("/api/transactions/{tid}/transfer", dependencies=[access.signed_in])
def transaction_transfer(tid: int, request: Request):
    """The other half of this transaction's transfer (other: {id, accountId, account, day, how}, or null), and the
    transactions you see that could be it (the same amount the other way, in another account, within two weeks)."""
    u = _u(request)
    t = model.transaction(u, tid)
    other = transfers.other_half(u, t)
    return {"other": other, "candidates": [] if other else transfers.candidates(u, t)}


@router.put("/api/transactions/{tid}/transfer", dependencies=[access.signed_in])
async def link_transfer(tid: int, request: Request):
    """{with: the other half's id}: link the two as one transfer, by hand."""
    u = _u(request)
    b = await json_body(request)
    await run_in_threadpool(lambda: transfers.connect(u, model.transaction(u, tid), b.get("with")))
    return {"other": transfers.other_half(u, model.transaction(u, tid))}


@router.delete("/api/transactions/{tid}/transfer", dependencies=[access.signed_in])
def unlink_transfer(tid: int, request: Request):
    """Unlink this transaction's transfer: the two are not linked again by themselves."""
    u = _u(request)
    transfers.disconnect(u, model.transaction(u, tid))
    return {"ok": True}


@router.get("/api/transfers/possible", dependencies=[access.signed_in])
def possible_transfers(request: Request):
    """The debits and credits of the same amount in two accounts, at most two weeks apart, not linked: each {out, in,
    why} (why it was not linked by itself), the nearest days first."""
    return {"items": transfers.possible(_u(request))}


@router.post("/api/transfers/not", dependencies=[access.signed_in])
async def not_a_transfer(request: Request):
    """{outId, inId}: these two are not one transfer; they leave the list of what to check and are never linked by
    themselves."""
    u = _u(request)
    b = await json_body(request)
    await run_in_threadpool(transfers.dismiss, u, b.get("outId"), b.get("inId"))
    return {"ok": True}


@router.post("/api/transfers/link", dependencies=[access.signed_in])
async def link_transfers(request: Request):
    """Go through every transaction not linked yet and link the transfers (editors): {linked, learned (transfer
    rules learned), unsure: [{out, in}] the pairs as likely as another, left for a person to link}."""
    u = _u(request)
    return await run_in_threadpool(transfers.link_all, u)


@router.get("/api/transfer-rules", dependencies=[access.signed_in])
def list_transfer_rules(request: Request):
    """The transfer rules: in an account, a payee (or bank's text) with these words is a transfer with that account.
    source learned: made when a transfer was found by itself."""
    u = _u(request)
    return {"items": [transfers.rule_public(r, u) for r in transfers.rules(u)], "writable": model.may_add(u, True)}


@router.post("/api/transfer-rules", dependencies=[access.signed_in])
async def add_transfer_rule(request: Request):
    """{accountId, pattern, otherId, days? (5)} (editors)."""
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(transfers.create_rule, u, b)
    linked = await run_in_threadpool(transfers.link)
    return JSONResponse({**transfers.rule_public(r, u), "linked": linked}, status_code=201)


@router.patch("/api/transfer-rules/{rid}", dependencies=[access.signed_in])
async def change_transfer_rule(rid: int, request: Request):
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(lambda: transfers.update_rule(u, transfers.rule(u, rid), b))
    return {**transfers.rule_public(r, u), "linked": await run_in_threadpool(transfers.link)}


@router.delete("/api/transfer-rules/{rid}", dependencies=[access.signed_in])
def delete_transfer_rule(rid: int, request: Request):
    u = _u(request)
    transfers.delete_rule(u, transfers.rule(u, rid))
    return {"ok": True}

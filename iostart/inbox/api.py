"""The Inbox page's routes (iostart/inbox/__init__.py): a person's mail that came to the suite's mailbox, filing it by
hand, their own addresses, and the mailbox itself (suite admins). A message is its sender's; one from an address
nobody has is for suite admins to give to someone. Nobody else sees it."""
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from iosuite_shared import users
from iosuite_shared.http import json_body

from iostart import access, inbox
from iostart.inbox import mail

router = APIRouter()
SHOWN = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}


def _found(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except LookupError as e:
        raise HTTPException(404, str(e))


def _suite_admin(request: Request) -> dict:
    u = request.state.user
    if not users.is_suite_admin(u):
        raise HTTPException(403, "Only a suite admin sets up the suite's mailbox")
    return u


def _ask(fn, *a):
    """Something asked of another app as the viewer: what it would not do is a 400 with its reason."""
    try:
        return fn(*a)
    except inbox.NotFiled as e:
        raise HTTPException(502 if e.retry else 400, str(e))


@router.get("/api/inbox", dependencies=[access.signed_in])
def listing(request: Request, show: str = "waiting"):
    """Your mail that came to the suite: show waiting (to file) or done (filed, let go). {items, waiting, unclaimed,
    mailbox: {ready, address}, people}; a suite admin also gets the mail from addresses nobody has (person null), and
    the people it can be given to."""
    u = request.state.user
    m = inbox.mailbox()
    admin = users.is_suite_admin(u)
    return {**inbox.listing(u, show), "mailbox": {"ready": inbox.ready(), "address": m["user"] if "@" in m["user"] else ""},
            "suiteAdmin": admin,
            # who mail from an unknown address can be given to (suite admins)
            "people": [{"id": p["id"], "name": p["displayName"]} for p in users.list_users()] if admin else []}


@router.get("/api/inbox/count", dependencies=[access.signed_in])
def count(request: Request):
    """{waiting, unclaimed}: for the menu's badge."""
    return inbox.counts(request.state.user)


@router.get("/api/inbox/me", dependencies=[access.signed_in])
def get_own(request: Request):
    """{addresses (the other addresses you send from), auto (file what is clear by itself), calendar, email (your
    account's)}."""
    u = request.state.user
    return {**inbox.own(u["id"]), "email": u.get("email") or ""}


@router.put("/api/inbox/me", dependencies=[access.signed_in])
async def set_own(request: Request):
    """{addresses?, auto?, calendar?}."""
    u = request.state.user
    b = await json_body(request)
    return {**await run_in_threadpool(inbox.set_own, u["id"], b), "email": u.get("email") or ""}


@router.get("/api/inbox/mailbox", dependencies=[access.signed_in])
def get_mailbox(request: Request):
    """The mailbox the suite reads (suite admins): {host, port, user, folder, on, passwordSet, ready, state}."""
    _suite_admin(request)
    return inbox.mailbox_public()


@router.put("/api/inbox/mailbox", dependencies=[access.signed_in])
async def set_mailbox(request: Request):
    """{host?, port?, user?, folder?, on?, password? (kept with the keys and tokens; null clears it)}."""
    u = _suite_admin(request)
    b = await json_body(request)
    return await run_in_threadpool(inbox.set_mailbox, b, u["name"])


@router.post("/api/inbox/mailbox/check", dependencies=[access.signed_in])
async def check_now(request: Request):
    """Read the mailbox now (suite admins): {read, kept}, or 400 with why it could not be read."""
    _suite_admin(request)
    try:
        return await run_in_threadpool(inbox.check)
    except mail.MailError as e:
        raise HTTPException(400, str(e))


@router.get("/api/inbox/calendars", dependencies=[access.signed_in])
async def calendars(request: Request):
    """{items}: your ioCalendar calendars an invitation can go to."""
    return {"items": await run_in_threadpool(_ask, inbox.calendars, request)}


@router.get("/api/inbox/{iid}", dependencies=[access.signed_in])
def get_item(iid: int, request: Request):
    """One message: its text (never its HTML), its files, what was read off it."""
    return inbox.public(_found(inbox.item, request.state.user, iid), full=True)


@router.get("/api/inbox/{iid}/files/{fid}", dependencies=[access.signed_in])
def get_file(iid: int, fid: int, request: Request, download: bool = False):
    body, mime, name = _found(inbox.file_content, request.state.user, iid, fid)
    shown = mime in SHOWN and not download
    headers = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
               "Content-Disposition": f"{'inline' if shown else 'attachment'}; filename*=UTF-8''{urllib.parse.quote(name)}"}
    if mime != "application/pdf":
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return Response(body, media_type=mime if shown else "application/octet-stream", headers=headers)


@router.get("/api/inbox/{iid}/matches", dependencies=[access.signed_in])
async def matches(iid: int, request: Request):
    """{items}: your ioMoney transactions the receipt could be for (money out of its amount, a few days around it)."""
    r = _found(inbox.item, request.state.user, iid)
    return {"items": await run_in_threadpool(_ask, inbox.matches, request, r)}


@router.post("/api/inbox/{iid}/file", dependencies=[access.signed_in])
async def file_it(iid: int, request: Request):
    """{to: money | docs | calendar, transaction? (money: which one), calendar? (which one), title? (docs)}: filed
    as you. The message as it is now (status filed, filed: {app, label, url})."""
    b = await json_body(request)
    return await run_in_threadpool(_found, inbox.file_by_hand, request, request.state.user, iid, b)


@router.post("/api/inbox/{iid}/give", dependencies=[access.signed_in])
async def give(iid: int, request: Request):
    """{person}: a suite admin gives mail from an address nobody has to someone."""
    u = _suite_admin(request)
    b = await json_body(request)
    return await run_in_threadpool(_found, inbox.give, u, iid, b.get("person"))


@router.post("/api/inbox/{iid}/let-go", dependencies=[access.signed_in])
def let_go(iid: int, request: Request):
    """Nothing to file: off the waiting list (listed under Done for a while)."""
    return _found(inbox.let_go, request.state.user, iid)


@router.post("/api/inbox/{iid}/back", dependencies=[access.signed_in])
def bring_back(iid: int, request: Request):
    """Back to waiting."""
    return _found(inbox.bring_back, request.state.user, iid)


@router.delete("/api/inbox/{iid}", dependencies=[access.signed_in])
def remove(iid: int, request: Request):
    """Gone at once, with its files."""
    _found(inbox.remove, request.state.user, iid)
    return {"ok": True}

"""The reader's routes (iostart/news/__init__.py): a person's feeds, their articles, what is read and starred, OPML in and out, and
the start page's headlines card. Everything here is the asking person's own: a member or more (a viewer keeps nothing
of their own, as in the other apps)."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from iosuite_shared.http import json_body

from iostart import access, news

router = APIRouter()


def _uid(request: Request) -> int:
    return request.state.user["id"]


def _found(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/api/news", dependencies=[access.member])
def overview(request: Request):
    """Your feeds, by folder and name, each with how many articles are not read: {feeds, folders, unread, starred}."""
    return news.overview(_uid(request))


@router.get("/api/news/card", dependencies=[access.signed_in])
def card(request: Request, n: int = 5):
    """The headlines card: the newest unread articles of the feeds you keep on the start page. {items, unread, feeds}."""
    u = request.state.user
    from iosuite_shared import users
    return news.card(u["id"], n) if users.is_member(u) else {"items": [], "unread": 0, "feeds": 0}


@router.post("/api/news/feeds", dependencies=[access.member])
async def add_feed(request: Request):
    """Follow a feed: {url (the feed's address, or its site's: the server finds the feed), folder?} → {feed, new}."""
    b = await json_body(request)
    return await run_in_threadpool(news.add, _uid(request), b)


@router.patch("/api/news/feeds/{sid}", dependencies=[access.member])
async def change_feed(sid: str, request: Request):
    """{title? (nothing: the feed's own name), folder?, onStart? (on the start page's card)}."""
    b = await json_body(request)
    return await run_in_threadpool(_found, news.change, _uid(request), sid, b)


@router.delete("/api/news/feeds/{sid}", dependencies=[access.member])
def remove_feed(sid: str, request: Request):
    """Stop following a feed."""
    _found(news.remove, _uid(request), sid)
    return {"ok": True}


@router.post("/api/news/feeds/{sid}/refresh", dependencies=[access.member])
def refresh_feed(sid: str, request: Request):
    """Look at one feed now. {checked, new}."""
    return _found(news.refresh_mine, _uid(request), sid)


@router.post("/api/news/refresh", dependencies=[access.member])
def refresh_all(request: Request):
    """Look now at your feeds not looked at in the last two minutes. {checked, new}."""
    return news.refresh_mine(_uid(request))


@router.post("/api/news/folders/rename", dependencies=[access.member])
async def rename_folder(request: Request):
    """{from, to}: a folder under another name ('' takes its feeds out of it). {feeds}."""
    b = await json_body(request)
    return {"feeds": news.rename_folder(_uid(request), b)}


@router.get("/api/news/items", dependencies=[access.member])
def list_items(request: Request, feed: str = "", folder: str = "", show: str = "unread", q: str = "", before: str = "", limit: int = news.PAGE):
    """Articles, the newest first: of one feed, one folder, or all; show unread, all or starred; q searches titles and
    text. {items, next}: pass `next` as `before` for the ones after."""
    return _found(news.items, _uid(request), feed, folder, show, q, before, limit)


@router.get("/api/news/items/{iid}", dependencies=[access.member])
def one_item(iid: str, request: Request):
    """One article with its text (html: cleaned by the server, safe to show)."""
    return _found(news.item, _uid(request), iid)


@router.post("/api/news/items/mark", dependencies=[access.member])
async def mark_items(request: Request):
    """{ids, read?, starred?}: those articles read or not, starred or not."""
    b = await json_body(request)
    return await run_in_threadpool(news.mark, _uid(request), b)


@router.post("/api/news/read", dependencies=[access.member])
async def mark_all_read(request: Request):
    """Everything read: {feed?} or {folder?}, else everywhere; {upto?}: only up to that article's id."""
    b = await json_body(request)
    return await run_in_threadpool(_found, news.mark_all, _uid(request), b)


@router.get("/api/news/opml", dependencies=[access.member])
def export_opml(request: Request):
    """Your feeds as an OPML file, which every reader imports."""
    return Response(news.opml_out(_uid(request)), media_type="text/x-opml; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="iostart-feeds.opml"'})


@router.post("/api/news/opml", dependencies=[access.member])
async def import_opml(request: Request):
    """Follow every feed of an OPML file (the request's body), in its folders. {added, known, total}."""
    data = await request.body()
    return await run_in_threadpool(news.opml_in, _uid(request), data)

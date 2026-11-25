"""The bookmarks' routes: the tree and its groups and links, their icons, the check for dead links and duplicates,
import and export, and the browser extension's download (the extension's own sync API is iostart/bookmarks/ext.py)."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
import io
import json
import os
import zipfile

from iosuite_shared.access import json_body

from iostart import auth
from iostart import access, config, bookmarks, status as appstatus
from iostart.bookmarks import icons as siteicons, check as bookmarkcheck, files as bookmarkfiles, sync as bookmarksync

router = APIRouter()


@router.get("/api/bookmarks", dependencies=[access.signed_in])
def list_bookmarks(request: Request):
    """What the start page shows: {groups: [{id, name, path, links}]}: the folders picked for it, with the links shown."""
    _me(request)
    return {"groups": bookmarks.groups()}


@router.get("/api/bookmarks/tree", dependencies=[access.signed_in])
def bookmarks_tree(request: Request):
    """Every folder and link, nested (the Bookmarks page): {rev, count, items}. A folder: {id, type: 'folder', name,
    start, shared, canChange, items}; a link: {id, type: 'bookmark', name, href, start (null: as its folder), onStart,
    shared, canChange, …}. canEdit: the person may keep bookmarks of their own; canShare: they manage the shared ones."""
    _me(request)
    return bookmarks.tree()


@router.get("/api/bookmarks/status", dependencies=[access.signed_in])
async def bookmarks_status(request: Request):
    """Each bookmark on the start page pinged from this server: {items: {link id: {ok, status}}}; ok is null for an
    address that cannot be pinged (mailto:…). Cached five minutes."""
    _me(request)
    return {"items": await run_in_threadpool(appstatus.of_bookmarks)}


def _me(request: Request) -> None:
    """The bookmarks read and changed in this request are the signed-in person's (theirs and the shared ones)."""
    bookmarks.as_user(request.state.user)


@router.get("/api/bookmarks/duplicates", dependencies=[access.signed_in])
def bookmarks_duplicates(request: Request):
    """Tidy up: the addresses your tree holds more than once: {groups: [{href, links: [{id, name, href, path, shared,
    onStart, canChange}]}], extra}; in each group the copy to keep comes first."""
    _me(request)
    return bookmarkcheck.duplicates()


@router.get("/api/bookmarks/check", dependencies=[access.signed_in])
def bookmarks_check(request: Request):
    """Tidy up: how far the check of your bookmarks' addresses is, and what it found: {running, done, total,
    checkedAt, items: [{id, name, href, path, shared, canChange, state: dead | gone | moved, status, to}]}."""
    _me(request)
    return bookmarkcheck.state()


@router.post("/api/bookmarks/check", dependencies=[access.signed_in])
def bookmarks_check_start(request: Request):
    """Tidy up: ask every web address of your bookmarks (yours and the shared ones) whether it still answers, in the
    background; GET says how far it is. One check at a time per person."""
    _me(request)
    return bookmarkcheck.start()


def _bm(request: Request, fn, *a, **kw):
    _me(request)
    try:
        return fn(*a, **kw)
    except bookmarks.NotFound as e:
        raise HTTPException(404, str(e))
    except bookmarks.NotAllowed as e:
        raise HTTPException(403, str(e))
    except (bookmarks.BadBookmark, bookmarkfiles.BadFile) as e:
        raise HTTPException(400, str(e))


@router.post("/api/bookmarks/groups", dependencies=[access.signed_in])
async def add_group(request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {name, parentId? (a folder; none: the top), start? (on the start page; true unless said)}"""
    b = await json_body(request)
    return _bm(request, bookmarks.add_group, b.get("name"), b.get("parentId"), bool(b.get("start", True)))


@router.patch("/api/bookmarks/groups/{gid}", dependencies=[access.signed_in])
async def update_group(gid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). Any of {name, parentId (0: the top), start,
    shared (admins)}. start on a shared folder, from someone who is not an admin: their own start page only."""
    return _bm(request, bookmarks.update_group, gid, await json_body(request))


@router.delete("/api/bookmarks/groups/{gid}", dependencies=[access.signed_in])
def delete_group(gid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). The folder and everything in it."""
    _bm(request, bookmarks.delete_group, gid)
    return {"ok": True}


@router.post("/api/bookmarks/groups/order", dependencies=[access.signed_in])
async def order_groups(request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {ids: [folder id, ...], parentId?}: these folders in this order inside the parent (none: the top); one
    named from elsewhere moves in."""
    b = await json_body(request)
    _bm(request, bookmarks.order, b.get("parentId"), [int(x) for x in b.get("ids") or []])
    return {"ok": True}


@router.post("/api/bookmarks/groups/{gid}/links", dependencies=[access.signed_in])
async def add_link(gid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {name, href, abbr?, description?, icon?, start?, tags?}; group 0 is the top level."""
    b = await json_body(request)
    return _bm(request, bookmarks.add_link, gid, b.get("name"), b.get("href"), b.get("abbr"), b.get("description"), b.get("icon"), b.get("start"), b.get("tags"))


@router.post("/api/bookmarks/groups/{gid}/order", dependencies=[access.signed_in])
async def order_links(gid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {ids: [link id, ...]} in the order wanted; a link from another folder moves into this one (0: the top)."""
    b = await json_body(request)
    _bm(request, bookmarks.order, gid, [int(x) for x in b.get("ids") or []])
    return {"ok": True}


@router.patch("/api/bookmarks/links/{lid}", dependencies=[access.signed_in])
async def update_link(lid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). Any of {name, href, abbr, description, icon, groupId, tags, start (true | false | null: as its folder), shared (admins)}."""
    return _bm(request, bookmarks.update_link, lid, await json_body(request))


@router.delete("/api/bookmarks/links/{lid}", dependencies=[access.signed_in])
def delete_link(lid: int, request: Request):
    _bm(request, bookmarks.delete_link, lid)
    return {"ok": True}


@router.get("/api/bookmarks/links/{lid}/icon.svg", dependencies=[access.signed_in])
def link_icon(lid: int, request: Request):
    """The icon uploaded for a link (an SVG; an uploaded PNG is served inside one), for everyone signed in. Cached by the browser for good: the address carries a
    version (?v=etag) that changes with the file."""
    _me(request)
    try:
        ic = bookmarks.icon(lid)
    except bookmarks.NotFound:
        ic = None
    if not ic:
        raise HTTPException(404, "No icon")
    return Response(ic["svg"], media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": f'"{ic["etag"]}"',
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:", "X-Content-Type-Options": "nosniff"})


@router.get("/api/bookmarks/site-icon", dependencies=[access.signed_in])
def site_icon(site: str, request: Request):
    """A bookmarked site's own icon, as the server fetched it (iostart/bookmarks/icons.py), for everyone signed in. Cached by the
    browser for good: the address carries a version (?v=etag). Served as the kind of image its bytes are, and as
    nothing a browser would run."""
    ic = siteicons.get(site)
    if not ic:
        raise HTTPException(404, "No icon")
    return Response(bytes(ic["data"]), media_type=ic["mime"],
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": f'"{ic["etag"]}"',
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox", "X-Content-Type-Options": "nosniff"})


@router.put("/api/bookmarks/links/{lid}/icon", dependencies=[access.signed_in])
async def upload_link_icon(lid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). The body is the file itself, an SVG or a PNG (up to 256 KB); the stored one is replaced. Returns the link."""
    data = await request.body()
    return _bm(request, bookmarks.set_icon, lid, data)


@router.delete("/api/bookmarks/links/{lid}/icon", dependencies=[access.signed_in])
def delete_link_icon(lid: int, request: Request):
    return _bm(request, bookmarks.clear_icon, lid)


@router.post("/api/bookmarks/import", dependencies=[access.signed_in])
async def import_bookmarks(request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {file, parentId?, start?}: the text of a
    bookmarks file a browser exported (HTML) or an XBEL file, added under the folder (none: the top); start: its
    folders go on the start page too (false unless said)."""
    b = await json_body(request)
    if b.get("file") is None:
        raise HTTPException(400, "Send {file}: a bookmarks file a browser exported (HTML) or an XBEL file")

    def work():
        items = bookmarkfiles.parse(str(b["file"]))
        bookmarks.add_items(b.get("parentId"), items, bool(b.get("start")))
        f, l = bookmarkfiles.count(items)
        return {"groups": f, "links": l}
    return await run_in_threadpool(_bm, request, work)


@router.get("/api/bookmarks/export.{kind}", dependencies=[access.signed_in])
def export_bookmarks(kind: str, request: Request):
    """Every bookmark as a file: export.html (what a browser imports) or export.xbel."""
    if kind not in ("html", "xbel"):
        raise HTTPException(404, "export.html or export.xbel")
    _me(request)
    items = bookmarksync.items()
    body = bookmarkfiles.to_html(items) if kind == "html" else bookmarkfiles.to_xbel(items)
    return Response(body, media_type="text/html; charset=utf-8" if kind == "html" else "application/xml; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="bookmarks.{kind}"'})


@router.get("/api/bookmarks/sync", dependencies=[access.signed_in])
def bookmarks_sync(request: Request):
    """What the Bookmarks page says about sync: the address the browser extension and the iPhone app are given, and
    the version of the extension this server holds."""
    root = auth.base_url(request, "sync")  # the extension and the app talk to the sync door (iosuite_shared.doors)
    return {"server": root, "user": request.state.user["name"] if request.state.user else "",
            "extension": _extension_version()}


EXTENSION_DIR = os.path.join(config.STATIC_DIR, "extension")


def _extension_version() -> str:
    try:
        with open(os.path.join(EXTENSION_DIR, "manifest.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "")
    except (OSError, ValueError):
        return ""


@router.get("/api/bookmarks/extension.zip", dependencies=[access.signed_in])
def bookmarks_extension():
    """The ioStart Bookmarks browser extension (static/extension) as one file: unpacked, Chrome and Edge load the
    folder; Firefox takes the signed file of the same version (the repository's releases)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in sorted(os.walk(EXTENSION_DIR)):
            for name in sorted(files):
                full = os.path.join(base, name)
                z.write(full, os.path.join("iostart-bookmarks", os.path.relpath(full, EXTENSION_DIR)))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="iostart-bookmarks-{_extension_version() or "extension"}.zip"'})

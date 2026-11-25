"""The Home Assistant card's routes (iostart/homeassistant): what the card shows, its live feed, switching things, and
the settings an admin keeps."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
import asyncio
import json

from iosuite_shared.http import json_body

from iostart import access, homeassistant as ha

router = APIRouter()


def _ha(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ha.HAError as e:
        raise HTTPException(e.status, str(e))


def _ha_card(request: Request, d: dict) -> dict:
    """The card as this viewer gets it: switching things takes an editor or an admin, so a viewer's copy offers no
    control (the page then shows the state alone). A copy: the card itself is shared between the pages."""
    if (getattr(request.state, "user", None) or {}).get("role") in ("editor", "admin") or not d.get("items"):
        return d
    return {**d, "items": [{**it, "control": False} for it in d["items"]]}


@router.get("/api/ha", dependencies=[access.signed_in])
async def get_home(request: Request):
    """The Home card and the wall's sensors: the chosen entities with their state (from the server's copy, a few seconds
    old at most), which of them go on the wall, and what needs attention. {enabled: false} until an admin sets it up.
    `control` on an entity is true for editors and admins only."""
    return _ha_card(request, await run_in_threadpool(ha.home))


@router.get("/api/ha/events", dependencies=[access.signed_in])
async def ha_events(request: Request, once: bool = False):
    """The Home card as server-sent events: the same JSON as /api/ha, sent when something in it changes (within a
    second while the live feed is up, else as the REST copy refreshes) and a comment every 20 seconds to keep the
    connection. The page's EventSource reconnects by itself. once=1: the card as it stands, then the end (a check)."""

    async def gen():
        last, seen = None, ha.feed.version
        beat = 0.0
        while True:
            if await request.is_disconnected():
                return
            d = _ha_card(request, await run_in_threadpool(ha.home))
            raw = json.dumps(d, separators=(",", ":"))
            now = asyncio.get_running_loop().time()
            if raw != last:
                last = raw
                beat = now
                yield f"data: {raw}\n\n"
                if once:
                    return
            elif now - beat > 20:
                beat = now
                yield ": keep\n\n"
            if d.get("live"):  # wait for the feed to move (or a few seconds, to notice a disconnect), without a thread
                seen = await ha.feed.wait_async(seen, 5.0)
            else:
                await asyncio.sleep(ha.STATES_TTL)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/ha/{entity_id}/set", dependencies=[access.editor])
async def ha_set(entity_id: str, request: Request):
    """Editors and admins. The popups: a thermostat takes {temperature? | low? + high?, mode?, fan?, preset?}, a cover
    {action: open | close | stop} or {position: 0-100}; on an entity the admin lets the page control. Returns the
    entity's state right after."""
    return await run_in_threadpool(_ha, ha.set_entity, entity_id, await json_body(request))


@router.post("/api/ha/{entity_id}/{action}", dependencies=[access.editor])
async def ha_act(entity_id: str, action: str, request: Request):
    """Editors and admins. toggle | on | off: switch an entity the admin lets the page control (Settings › Home
    Assistant). Returns the entity's state right after. 403 for any other entity, and for a viewer."""
    return await run_in_threadpool(_ha, ha.act, entity_id, action)


@router.get("/api/ha/search", dependencies=[access.admin])
async def ha_search(request: Request, q: str = "", n: int = 8):
    """Entities whose name or id contains every word of q (the search box; up to 50)."""
    return {"items": await run_in_threadpool(_ha, ha.search, q, max(1, min(int(n or 8), 50)))}


@router.get("/api/ha/settings", dependencies=[access.admin])
def ha_settings(request: Request):
    return ha.settings()


@router.post("/api/ha/settings", dependencies=[access.admin])
async def ha_save(request: Request):
    """Admins. Body: {url?, token?, entities?: [{id, name?, control?, wall?, alert?}], builtinAlerts?}."""
    u = request.state.user
    _ha(ha.save, await json_body(request), by=u.get("name"))
    return ha.settings()


@router.post("/api/ha/test", dependencies=[access.admin])
async def ha_test(request: Request):
    """Admins. Body: {url?, token?}: tries them (the saved ones when empty) → {ok, name, version, entities}."""
    b = await json_body(request)
    return await run_in_threadpool(_ha, ha.test, str(b.get("url") or ""), str(b.get("token") or ""))

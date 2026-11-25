"""The REST API (JSON) the start page uses. OpenAPI docs at /api/docs. Who may call a route is declared on it (iostart/access.py).

Clients authenticate with the web session cookie (the suite's, shared by every io app on the domain), HTTP Basic or
`Authorization: Bearer <app password>`, as in the other io apps.

Here: the apps and the layout, the weather, the search, what the tiles show, the timers, the rates and the wall
display. The bookmarks, the feeds, Home Assistant and TRMNL keep their routes with their code (iostart/bookmarks/api.py,
news/api.py, homeassistant/api.py, trmnl/api.py)."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool

from iosuite_shared.http import json_body

from iostart import access, apps, config, layout, status as appstatus, rates, timers, wall, weather, widgets
from iostart import search as suitesearch

router = APIRouter()


# ------------------------------------------------------------------ the apps

@router.get("/api/apps", dependencies=[access.signed_in])
def list_apps(request: Request, device: str = ""):
    """The tiles: every app this person may use, with its name, icon, colour and address (an admin tool only for its
    admins). Hidden ones are left out (Settings lists them). layout: the setup the page is drawn from on this device
    (`device`: the id this browser keeps, when it has one); layoutOf: where that setup comes from."""
    u = request.state.user
    return {"items": apps.tiles(u), "photoStrip": apps.photo_strip(), **_layout_of(u, device)}


def _layout_of(u: dict, device: str = "") -> dict:
    """{layout, layoutOf: {scope: device | account | family | none, device: {id, name} | null, devices: [{id, name}],
    family: whether an admin set a starting point for everyone}}."""
    w = layout.where(u["id"], device or None)
    return {"layout": w["layout"], "layoutOf": {"scope": w["scope"], "device": w["device"], "devices": layout.devices(u["id"]),
                                                "family": layout.family() is not None}}


@router.get("/api/apps/status", dependencies=[access.signed_in])
async def apps_status(request: Request):
    """Each app's /api/status, asked with the viewer's sign-in: {items: {key: {ok, version, why}}}. Cached a
    minute."""
    return {"items": await run_in_threadpool(appstatus.of_apps, request)}


@router.get("/api/me/layout", dependencies=[access.signed_in])
def my_layout(request: Request, device: str = ""):
    """The viewer's own start page (see iostart/layout.py): this device's setup when it has one of its own, else the
    account's, else the family's starting point."""
    return layout.get(request.state.user["id"], device or None)


@router.put("/api/me/layout", dependencies=[access.signed_in])
async def my_layout_save(request: Request, device: str = "", name: str = ""):
    """Body: a layout (iostart/layout.py: hidden, order, cards, strip, style, sizes, todayOff, units, accent…). Without
    `device` it is the account's, and {} puts it back as it comes. With `device` (the id the browser keeps) and `name`
    ("Kitchen tablet") it is that device's own."""
    u = request.state.user
    return layout.save(u["id"], await json_body(request), device or None, name)


@router.get("/api/me/layout/where", dependencies=[access.signed_in])
def my_layout_where(request: Request, device: str = ""):
    """The setup with where it comes from: {layout, layoutOf} as /api/apps has them."""
    return _layout_of(request.state.user, device)


@router.delete("/api/me/layout/devices/{device}", dependencies=[access.signed_in])
def my_layout_forget_device(device: str, request: Request):
    """That device goes back to the account's setup."""
    u = request.state.user
    layout.forget_device(u["id"], device)
    return {"devices": layout.devices(u["id"])}


@router.get("/api/layout/family", dependencies=[access.admin])
def family_layout(request: Request):
    """Admins: the setup everyone starts from (null: none), and the people with whether each has a setup of their own."""
    from iosuite_shared import users
    people = [{"id": p["id"], "name": p["name"], "displayName": p.get("displayName") or p["name"], "own": layout.has_own(p["id"]),
               "devices": len(layout.devices(p["id"]))}
              for p in users.list_users(config.APP) if p.get("role") != "none"]
    return {"layout": layout.family(), "people": people}


@router.put("/api/layout/family", dependencies=[access.admin])
async def family_layout_save(request: Request):
    """Admins. Body: a layout, the starting point for whoever has none of their own; {} takes it away."""
    return {"layout": layout.set_family(await json_body(request))}


@router.put("/api/layout/people/{user_id}", dependencies=[access.admin])
async def give_layout(user_id: int, request: Request):
    """Admins. Body: a layout, which becomes that person's on every device (they can change it afterwards)."""
    from iosuite_shared import users
    p = users.get(user_id, config.APP)
    if not p or p.get("role") == "none":
        raise HTTPException(404, "Nobody here by that id")
    layout.give(user_id, await json_body(request))
    return {"ok": True}


@router.get("/api/home/settings", dependencies=[access.admin])
def home_settings(request: Request):
    """Admins: what the home page shows everyone by default (the photo strip under the tiles)."""
    return {"photoStrip": apps.photo_strip()}


@router.post("/api/home/settings", dependencies=[access.admin])
async def home_save(request: Request):
    """Admins. Body: {photoStrip: rediscover | onthisday | off}."""
    b = await json_body(request)
    if "photoStrip" in b:
        apps.set_photo_strip(b["photoStrip"])
    return {"photoStrip": apps.photo_strip()}


# ------------------------------------------------------------------ the weather

@router.get("/api/weather", dependencies=[access.signed_in])
async def get_weather(request: Request):
    """The widget: current conditions and the 5-day forecast, from the server's copy (refreshed from AccuWeather when
    it is older than 45 minutes / 6 hours). {enabled: false} until an admin sets it up."""
    try:
        return await run_in_threadpool(weather.current)
    except weather.WeatherError as e:
        return {"enabled": True, "error": str(e), "current": None, "forecast": None, "units": weather.settings()["units"],
                "location": weather.settings()["locationName"]}


@router.get("/api/weather/place", dependencies=[access.signed_in])
def weather_place(request: Request):
    """The weather's place and units, for the other apps (ioCalendar draws its own forecast for this place): {name,
    units}; name empty while none is chosen. Never asks AccuWeather."""
    s = weather.settings()
    return {"name": s["locationName"] if s["locationKey"] else "", "units": s["units"]}


@router.get("/api/weather/settings", dependencies=[access.admin])
def weather_settings(request: Request):
    return weather.settings()


@router.post("/api/weather/settings", dependencies=[access.admin])
async def weather_save(request: Request):
    """Admins. Body: {key?, locationKey?, locationName?, units?}."""
    u = request.state.user
    b = await json_body(request)
    try:
        weather.save(b, by=u.get("name"))
    except weather.WeatherError as e:
        raise HTTPException(400, str(e))
    return weather.settings()


@router.get("/api/weather/search", dependencies=[access.admin])
async def weather_search(request: Request, q: str = "", key: str = ""):
    """Admins: places matching a city name, to pick the location in Settings. `key` tries a key before it is saved."""
    try:
        return {"items": await run_in_threadpool(weather.search, q, key)}
    except weather.WeatherError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ one search across the apps (iostart/search.py)

@router.get("/api/search", dependencies=[access.signed_in])
async def search_everywhere(request: Request, q: str = "", tz: str = "", apps: str = "", wait: bool = False):
    """What every app with a search finds for q, asked at the same time with the viewer's own sign-in and ranked
    together: {items: [item + {app, score}], apps: {key: {more} | {status, why}}, late: [key]}. Items are in the suite's
    shape (iosuite_shared.suiteitems), best first; finished tasks and events that are over are left out. apps: only
    these (comma-separated; the ones the viewer hid stay out). late: the apps that had not answered within a few
    seconds; ask again for those with apps=<them>&wait=1, which waits for them as long as an app is ever waited for."""
    only = [k for k in apps.split(",") if k] or None
    return await run_in_threadpool(suitesearch.everywhere, request, q, tz, only,
                                   widgets.TIMEOUT * 3 if wait else suitesearch.DEADLINE)


# ------------------------------------------------------------------ what the tiles show (iostart/widgets.py)

@router.get("/api/widgets/{key}", dependencies=[access.signed_in])
def widget(key: str, request: Request, tz: str = "", kind: str = "", n: int = 0, q: str = ""):
    """A glimpse of one app for its tile (the app's /api/suite/tile), asked of the app with the viewer's own sign-in;
    with q, what the app finds for the search box instead (its /api/suite/search: {items, more}, items in the suite's
    shape). tz: the viewer's time zone (IANA, e.g. Europe/Brussels), for what "today" is; kind and n: what the app's
    tile takes (ioPix: onthisday | rediscover and how many; ioCalendar: week). 404 for an app without one (its
    manifest says which have a tile, and which a search); 401/403 when the app refuses this account; 502 when it does
    not answer. The page leaves the tile as it is on any of these."""
    try:
        return widgets.get(request, key, tz, kind, n, q)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/widgets/iocalendar/calendars", dependencies=[access.signed_in])
def widget_calendars(request: Request):
    """The ioCalendar calendars this viewer may add events to (quick add in the search box)."""
    try:
        return widgets.iocalendar_calendars(request)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.post("/api/widgets/iocalendar/events", dependencies=[access.signed_in])
async def widget_add_event(request: Request):
    """Quick add: a new event in ioCalendar, made with the viewer's own sign-in. {title, start, end?, allDay,
    timezone?, calendarId?} → {id, url}."""
    b = await json_body(request)
    try:
        return await run_in_threadpool(widgets.iocalendar_add, request, b)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/widgets/iotask/lists", dependencies=[access.signed_in])
def widget_task_lists(request: Request):
    """The ioTask lists this viewer may add tasks to (quick add in the search box)."""
    try:
        return widgets.iotask_lists(request)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.post("/api/widgets/iotask/tasks", dependencies=[access.signed_in])
async def widget_add_task(request: Request):
    """Quick add: a new task in ioTask, made with the viewer's own sign-in. {title, due? (a date, or a date and
    time), listId?, timezone?} → {id, url}."""
    b = await json_body(request)
    try:
        return await run_in_threadpool(widgets.iotask_add, request, b)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.post("/api/widgets/iotask/tasks/{task_id}/done", dependencies=[access.signed_in])
async def widget_task_done(task_id: str, request: Request):
    """Ticks off a task the page lists, in ioTask and as the viewer. {done? (false opens it again), undo? (the step a
    tick gave, to take just that back), timezone?} → {ok, moved, undo}."""
    b = await json_body(request)
    try:
        return await run_in_threadpool(widgets.iotask_done, request, task_id, b)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.post("/api/widgets/ionote/notes", dependencies=[access.signed_in])
async def widget_add_note(request: Request):
    """Quick add: a new note in ioNote, the viewer's own. {title?, text?} → {id, url}."""
    b = await json_body(request)
    try:
        return await run_in_threadpool(widgets.ionote_add, request, b)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/widgets/{key}/image/{kind}/{item_id}", dependencies=[access.signed_in])
def widget_image(key: str, kind: str, item_id: str, request: Request, p: str = ""):
    """An item's picture from its app (the suite's /api/suite/items/{kind}/{id}/image), passed through: the page shows
    images from here only. A photo, a contact's face, a recipe's or a thing's picture; p names one of several
    ("preview": an ioPix photo at screen size, for the wall display)."""
    try:
        body, ctype = widgets.image(request, key, kind, item_id, p)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    return Response(body, media_type=ctype if ctype.startswith("image/") else "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


# ------------------------------------------------------------------ kitchen timers (iostart/timers.py)

def _timer(fn, *a):
    try:
        return fn(*a)
    except timers.BadTimer as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/api/timers", dependencies=[access.signed_in])
def timers_list():
    """{now, items: [{id, label, seconds, endsAt, by, byId}]}: the family's timers, running or ended a moment ago;
    now and endsAt are the server's epoch seconds."""
    return timers.listing()


@router.post("/api/timers", dependencies=[access.signed_in])
async def timers_start(request: Request):
    """A new timer: {seconds, label?} → the timer."""
    b = await json_body(request)
    return await run_in_threadpool(_timer, timers.start, request.state.user, b)


@router.post("/api/timers/{tid}/more", dependencies=[access.signed_in])
async def timers_more(tid: int, request: Request):
    """More time: {seconds} (60 by default); an ended timer starts again from now."""
    b = await json_body(request)
    return await run_in_threadpool(_timer, timers.more, tid, b)


@router.delete("/api/timers/{tid}", dependencies=[access.signed_in])
def timers_dismiss(tid: int):
    """Stop a timer, or silence one that ended."""
    _timer(timers.dismiss, tid)
    return {"ok": True}


# ------------------------------------------------------------------ exchange rates for the search box (iostart/rates.py)

@router.get("/api/rates", dependencies=[access.signed_in])
def rates_get():
    """{base: 'EUR', date, rates: {USD: 1.08, ...}}: the ECB's reference rates of the working day, for "120 usd in eur"."""
    try:
        return rates.get()
    except rates.RatesError as e:
        raise HTTPException(502, str(e))


# ------------------------------------------------------------------ the wall display on a device (iostart/wall.py)

def _wall(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    except wall.PairError as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/wall/feed", dependencies=[access.signed_in])
def wall_feed(request: Request, tz: str = ""):
    """Everything the wall display shows, in one compact answer for a device of its own (devices/tab5-wall): the time
    zone (IANA and POSIX), the weather and its next hours, today's and the coming days' events (times as epoch
    seconds, the place before its first comma), birthdays, today's tasks, the Home Assistant entities on the wall, the
    photos to show and what the viewer may change. tz: the device's zone (IANA), else the server's. A part is null when
    its app is not there or did not answer (errors says why)."""
    return _wall(wall.feed, request, tz)


@router.get("/api/wall/photo/{photo_id}.jpg", dependencies=[access.signed_in])
def wall_photo(photo_id: str, request: Request, w: int = 1280, h: int = 720):
    """An ioPix photo cut to fill w × h (at most 1920 × 1200), as a baseline JPEG."""
    body = _wall(wall.photo, request, photo_id, w, h)
    return Response(body, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/api/wall/tasks/{task_id}/done", dependencies=[access.signed_in])
def wall_task_done(task_id: str, request: Request):
    """Ticks off one of today's tasks in ioTask, as the viewer."""
    return _wall(wall.task_done, request, task_id)


@router.post("/api/wall/photos/{photo_id}/favorite", dependencies=[access.signed_in])
async def wall_favorite(photo_id: str, request: Request):
    """Body {on: bool (default true)}: the photo in (or out of) the viewer's ioPix favorites."""
    b = await json_body(request)
    return await run_in_threadpool(_wall, wall.favorite, request, photo_id, b.get("on", True) is not False)


@router.post("/api/wall/pair", dependencies=[access.public])
async def wall_pair(request: Request):
    """A device asks to be let in: {label?} → {code, token, approveUrl, expires, every}. It shows the code (and a QR
    code of approveUrl) and asks GET /api/wall/pair/{token} every `every` seconds."""
    try:
        b = await json_body(request)
    except HTTPException:
        b = {}
    return wall.pair_start(b.get("label") or "", wall.base_url(request))


@router.get("/api/wall/pair/{token}", dependencies=[access.public])
def wall_pair_poll(token: str):
    """202 {waiting: true} until someone approves the code; then once {password, name}: the device's own ioStart app
    password; 404 when the code expired."""
    got = _wall(wall.pair_poll, token)
    if got is None:
        return Response('{"waiting": true}', status_code=202, media_type="application/json")
    return got


@router.get("/api/wall/pair/code/{code}", dependencies=[access.signed_in])
def wall_pair_info(code: str):
    """The approval page (#/pair/<code>): the device waiting for this code, {code, label, age}."""
    return _wall(wall.pair_info, code)


@router.post("/api/wall/pair/code/{code}", dependencies=[access.signed_in])
def wall_pair_approve(code: str, request: Request):
    """The signed-in person lets the device in: it gets an app password of theirs (Settings › Account lists it)."""
    return _wall(wall.pair_approve, code, request.state.user)



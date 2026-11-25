"""The TRMNL routes: each person's screens and their pushes (iostart/trmnl/push.py), the devices that ask this server
what to show (iostart/trmnl/server.py), and the plugin's markup and data."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.concurrency import run_in_threadpool

from iosuite_shared import prefix
from iosuite_shared.http import json_body

from iostart import auth
from iostart import access, trmnl
from iostart.trmnl import push as trmnlpush, server as trmnlserver

router = APIRouter()


def _trmnl_state(request: Request, got: dict) -> dict:
    return {**got, **trmnlserver.state(request.state.user), "server": auth.base_url(request)}  # what TRMNL reads from: the pages' address (the port for devices serves the native apps' calls only)


@router.get("/api/trmnl", dependencies=[access.signed_in])
def trmnl_settings(request: Request):
    """Settings › TRMNL: the screens this person may put on a TRMNL, which of them the start page pushes and how the
    last push went, their time zone and clock, the address TRMNL reaches the start page at (for the plugin files),
    their TRMNL devices that ask this server itself (iostart/trmnl/server.py) and the address such a device is given."""
    return _trmnl_state(request, trmnlpush.state(request.state.user))


@router.put("/api/trmnl", dependencies=[access.signed_in])
async def trmnl_save(request: Request):
    """{tz?, clock? (12|24), hooks?: {screen: webhook URL | ''}}: which screens the start page pushes to TRMNL's cloud
    and where. The first address makes the app password they are read with; the last one removed revokes it."""
    b = await json_body(request)
    return _trmnl_state(request, await run_in_threadpool(trmnlpush.configure, request.state.user, b))


# A TRMNL device set to this server (iostart/trmnl/server.py). It has no account and cannot pass Cloudflare Access: the four
# below answer without a sign-in (main.py: is_open), to a device's own key. The paths are TRMNL's firmware's.

def _device(fn, *a):
    try:
        return fn(*a)
    except trmnlserver.NotFound as e:
        return JSONResponse({"status": 404, "message": str(e), "detail": str(e)}, status_code=404)


@router.get("/api/setup", dependencies=[access.public])
def trmnl_device_setup(request: Request):
    """A TRMNL device's first question (header ID: its MAC address): its key, and the code its screen shows until
    someone types it in Settings › TRMNL. {status: 200, api_key, friendly_id, image_url, message}."""
    return _device(trmnlserver.setup, request.headers, prefix.base_url(request))


@router.get("/api/display", dependencies=[access.public])
def trmnl_device_display(request: Request):
    """What a TRMNL device shows next (headers ID and Access-Token, and what it says of its battery and signal):
    {status: 0, image_url, filename, refresh_rate, ...}, as TRMNL's firmware reads it."""
    return _device(trmnlserver.display, request.headers, prefix.base_url(request))


@router.get("/api/current_screen", dependencies=[access.public])
def trmnl_device_current(request: Request):
    """What a TRMNL device shows now, without moving its playlist on (headers ID and Access-Token): for a client that
    only looks, as TRMNL's own apps do. {status: 200, image_url, filename, refresh_rate, ...}."""
    return _device(trmnlserver.current, request.headers, prefix.base_url(request))


@router.post("/api/log", dependencies=[access.public])
async def trmnl_device_log(request: Request):
    """A TRMNL device's own log lines (headers ID and Access-Token): the last few are kept with the device."""
    try:
        b = await json_body(request)
    except HTTPException:
        b = {}
    return _device(lambda: trmnlserver.add_log(request.headers, b) or {"status": 200})


@router.get("/api/trmnl/image/{key}.png", dependencies=[access.public])
def trmnl_device_image(key: str):
    """The picture an answer of /api/display named (the key in its address is its secret, new with every answer)."""
    got = _device(trmnlserver.image, key)
    return got if isinstance(got, JSONResponse) else Response(got, media_type="image/png", headers={"Cache-Control": "no-store"})


def _mine(fn, *a):
    try:
        return fn(*a)
    except trmnlserver.NotFound as e:
        raise HTTPException(404, str(e))


@router.post("/api/trmnl/devices", dependencies=[access.signed_in])
async def trmnl_device_claim(request: Request):
    """{code}: the signed-in person takes the TRMNL device whose screen shows this code; it shows their screens from
    its next look."""
    b = await json_body(request)
    return await run_in_threadpool(_mine, trmnlserver.claim, request.state.user, b.get("code"))


@router.put("/api/trmnl/devices/{dev_id}", dependencies=[access.signed_in])
async def trmnl_device_save(dev_id: int, request: Request):
    """{name?, refresh? (seconds), bits? (1|2|4), playlist? [{layout, screens}], pair? (true: let the device ask for a
    new key for ten minutes, after a reset)}."""
    b = await json_body(request)
    return await run_in_threadpool(_mine, trmnlserver.configure, request.state.user, dev_id, b)


@router.delete("/api/trmnl/devices/{dev_id}", dependencies=[access.signed_in])
def trmnl_device_remove(dev_id: int, request: Request):
    _mine(trmnlserver.remove, request.state.user, dev_id)
    return {"ok": True}


@router.get("/api/trmnl/devices/{dev_id}/preview.png", dependencies=[access.signed_in])
def trmnl_device_preview(dev_id: int, request: Request, at: int = 0, layout: str = "", screens: str = ""):
    """What the device shows, drawn now: entry `at` of its playlist, or (while it is edited) `layout` with `screens`
    (comma-separated, one for each place of the layout)."""
    body = _mine(trmnlserver.preview, request.state.user, dev_id, at, layout, [k for k in screens.split(",") if k])
    return Response(body, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/api/trmnl/{screen}/send", dependencies=[access.signed_in])
def trmnl_send(screen: str, request: Request):
    """Push this screen now (Settings › TRMNL's Send now): {at, ok, error}."""
    if screen not in trmnl.SCREENS:
        raise HTTPException(404, "No such TRMNL screen")
    got = trmnlpush.push(request.state.user["id"], only=screen, force=True)
    if screen not in got:
        raise HTTPException(400, "This screen is not pushed: add its TRMNL webhook address first")
    return got[screen]


@router.get("/api/trmnl/{screen}/plugin.zip", dependencies=[access.signed_in])
def trmnl_plugin(screen: str, request: Request, mode: str = "poll"):
    """The screen as a TRMNL private plugin, the zip TRMNL's Import new takes. mode poll: TRMNL (its cloud, or a
    TRMNL server of your own) asks the start page, with an app password typed in TRMNL's form; push: the start page
    sends it (strategy webhook). No password or key is in the file."""
    if screen not in trmnl.SCREENS:
        raise HTTPException(404, "No such TRMNL screen")
    body = trmnl.plugin_zip(screen, "push" if mode == "push" else "poll", auth.base_url(request))
    return Response(body, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="iosuite-trmnl-{screen}{"-push" if mode == "push" else ""}.zip"'})


@router.get("/api/trmnl/{screen}", dependencies=[access.signed_in])
def trmnl_data(screen: str, request: Request, tz: str = "", clock: str = "12"):
    """What a TRMNL plugin shows (its polling URL): the screen's data, flat and already worded, as the person signed in
    (an ioStart app password as Bearer, for TRMNL). tz: their time zone (TRMNL fills it in: trmnl.user.time_zone_iana);
    clock: 12 or 24. Screens: today, calendar, tasks, docs, health, money."""
    try:
        return trmnl.build(request, screen, tz, clock == "24")
    except trmnl.NoScreen:
        raise HTTPException(404, "No such TRMNL screen (today, calendar, tasks, docs, health, money)")


# the server (version, updates, the log, restart): iosuite_shared's server_router, mounted in main.py

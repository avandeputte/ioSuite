"""The sign-in flow for apps: how the ioStart Bookmarks browser extension and the iPhone app get an app password of
their own without anyone typing one.

    POST <address>/dav/nextcloud/index.php/login/v2            the app starts: {login: a page to open, poll: {token, endpoint}}
    GET  …/login/v2/flow/<page>                                that page, in the browser: whoever is signed in says yes
    POST …/login/v2/grant                                      the yes (the session cookie, from this site)
    POST …/login/v2/poll  {token}                              404 until then; then, once, {loginName, appPassword, server}

The app password is made in the Shared ioSuite database, for sync only (`?scope=full`, which the iPhone app asks for
its widgets and Siri: without that limit), and is listed and revocable in Settings like any other. The shape is the
login flow v2 that Nextcloud's apps use, and the address is the one the released extension and iPhone app call.
"""
import html
import json
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse
from iosuite_shared import apppasswords, prefix, sessions, users

from iostart import config
from iostart.auth import auth

BASE = "/dav/nextcloud"
router = APIRouter()


async def _json(request: Request) -> dict:
    """The body, JSON or a form (the page's Allow button posts a form)."""
    ctype = request.headers.get("content-type", "")
    try:
        if "json" in ctype:
            b = json.loads(await request.body() or b"{}")
            return b if isinstance(b, dict) else {}
        return {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Unreadable request body")


FLOW_TTL = 20 * 60
_flows: dict = {}  # poll token -> {at, page (the token in the page's address), ua, done: {loginName, appPassword} | None}


def _root(request: Request) -> str:
    """The address this server is reached at, as the client reached it."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    scheme = "https" if sessions.over_https(request) else request.url.scheme
    return (config.PUBLIC_URL.rstrip("/") if config.PUBLIC_URL and not host else f"{scheme}://{host}{prefix.of(request)}")


def _flow_by_page(page: str):
    now = time.time()
    for k in [k for k, f in _flows.items() if now - f["at"] > FLOW_TTL]:
        _flows.pop(k, None)
    return next((f for f in _flows.values() if secrets.compare_digest(f["page"], page)), None)


@router.post(BASE + "/index.php/login/v2", include_in_schema=False)
def flow_start(request: Request):
    """Anyone may start a flow: it gives nothing until somebody signed in says yes on the page."""
    _flow_by_page("")  # forgets the old ones
    if len(_flows) > 200:
        raise HTTPException(429, "Too many sign-ins waiting; try again in a few minutes")
    poll, page = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    who = request.query_params.get("client") or request.headers.get("user-agent") or ""  # ?client=: the extension names itself
    # ?scope=full: the iPhone app (ioStart), whose widgets and Siri read and add in the other apps as the person, asks
    # for an app password without a limit; everyone else gets one for sync only. The page says which it is.
    full = request.query_params.get("scope") == "full"
    _flows[poll] = {"at": time.time(), "page": page, "ua": who[:80], "done": None, "full": full}
    root = _root(request) + BASE
    return {"poll": {"token": poll, "endpoint": f"{root}/index.php/login/v2/poll"}, "login": f"{root}/index.php/login/v2/flow/{page}"}


@router.post(BASE + "/index.php/login/v2/poll", include_in_schema=False)
async def flow_poll(request: Request):
    """404 until the page said yes; then, once, the name and the app password made for the client."""
    token = str((await _json(request)).get("token") or "")
    f = _flows.get(token)
    if not f or not f["done"]:
        return JSONResponse([], status_code=404)
    _flows.pop(token, None)
    return {"server": _root(request) + BASE, **f["done"]}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>
:root {{ color-scheme: light dark; }} body {{ font: 16px/1.5 system-ui, sans-serif; margin: 0; min-height: 100vh; display: grid; place-items: center; background: Canvas; color: CanvasText; }}
main {{ max-width: 440px; padding: 28px; }} h1 {{ font-size: 22px; margin: 0 0 12px; }} p {{ margin: 0 0 14px; }} .muted {{ opacity: .7; font-size: 14px; }}
button, a.btn {{ font: inherit; padding: 10px 18px; border-radius: 10px; border: 0; background: #2f3a5a; color: #fff; cursor: pointer; text-decoration: none; display: inline-block; }}
</style></head><body><main>{body}</main></body></html>""", headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"})


@router.get(BASE + "/index.php/login/v2/flow/{page}", include_in_schema=False)
def flow_page(page: str, request: Request):
    f = _flow_by_page(page)
    if not f or f["done"]:
        return _page("ioStart", "<h1>This sign-in link is no longer valid</h1><p>Start again from the app that sent you here.</p>")
    u = auth.current_user(request)
    if not u:
        # the start page, which brings the visitor back here once signed in (static/js/main.js: ?flow=): one tab, so it
        # also works where there is only one, as in the sign-in sheet of the iPhone app
        return _page("ioStart", '<h1>Sign in to ioStart first</h1><p>Then you are asked whether the app may sync the bookmarks.</p>'
                                f'<p><a class="btn" href="{prefix.of(request)}/?flow={html.escape(page)}">Sign in</a></p>')
    who = html.escape(f["ua"] or "An app")
    grant = f'<form method="post" action="{prefix.of(request)}{BASE}/index.php/login/v2/grant"><input type="hidden" name="page" value="{html.escape(page)}"><button>Allow</button></form>'
    if f.get("full"):
        return _page("Sign in to ioStart", f"""<h1>Let this app in as you?</h1>
<p><b>{who}</b> asks for full access as <b>{html.escape(u["name"])}</b>: your bookmarks, and what its widgets and Siri show and add in your other apps (your day in ioCalendar, your tasks in ioTask).</p>
<p class="muted">It gets an app password of its own that works wherever you do. You can revoke it any time in Settings.</p>
{grant}""")
    can = "read and change" if users.is_member(u) else "read"
    return _page("Sync bookmarks with ioStart", f"""<h1>Let this app sync the bookmarks?</h1>
<p><b>{who}</b> asks to {can} your bookmarks and the shared ones as <b>{html.escape(u["name"])}</b>.</p>
<p class="muted">It gets an app password of its own, for sync only. You can revoke it any time in Settings.</p>
{grant}""")


@router.post(BASE + "/index.php/login/v2/grant", include_in_schema=False)
async def flow_grant(request: Request):
    """The yes of whoever is signed in, in the browser (the session cookie, from this site: not a password, not another site)."""
    u = auth.current_user(request)
    if not u or "authorization" in request.headers or auth.cross_site(request):
        raise HTTPException(403, "Sign in to ioStart in this browser first")
    f = _flow_by_page(str((await _json(request)).get("page") or ""))
    if not f or f["done"]:
        return _page("ioStart", "<h1>This sign-in link is no longer valid</h1><p>Start again from the app that sent you here.</p>")
    if f.get("full"):
        label, scope = (f"App: {f['ua']}" if f["ua"] else "App"), ""
    else:
        label, scope = (f"Bookmark sync: {f['ua']}" if f["ua"] else "Bookmark sync"), apppasswords.DAV
    pw = await run_in_threadpool(apppasswords.create, u["id"], auth.app, label, scope)
    f["done"] = {"loginName": u["name"], "appPassword": pw}
    return _page("ioStart", "<h1>Done</h1><p>The app is signed in. You can close this tab and go back to it.</p>")

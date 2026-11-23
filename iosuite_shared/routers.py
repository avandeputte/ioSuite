"""The routers every app mounts: /api/auth/* (sign-in, the account's own settings, passwords, sessions, app
passwords), /api/suite-admin (suite admins), /api/server (maintenance)
and /api/status. Each takes the app's Auth; Auth.router() and friends call them."""
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from iosuite_shared import admin as suite_admin, apppasswords, estate, family, pages, passkeys, persondata, proxyauth, push, sessions, suite, suiteupdates, twostep, users
from iosuite_shared.access import UNCLAIMED, json_body, public_user
from iosuite_shared.proxyauth import authlog, peer_of

STATUS_PATH = "/api/status"
log = logging.getLogger("iosuite_shared.routers")


def auth_router(self) -> APIRouter:
    auth, access, proxy, app = self, self.access, self.proxy, self.app
    r = APIRouter()

    @r.post("/api/auth/login", dependencies=[access.public])
    async def api_login(request: Request):
        body = await json_body(request)
        name, src = str(body.get("name", ""))[:64], proxy.source(request)
        visitor = proxy.visitor_of(request)
        wait = users.attempt_wait(visitor, name)
        if wait:
            authlog.warning("sign-in as %r from %s refused: %d s to wait after repeated failures", name, src, wait)
            raise HTTPException(429, f"Too many attempts; try again in {wait} seconds", headers={"Retry-After": str(wait)})
        u = await run_in_threadpool(users.authenticate, name, str(body.get("password", ""))[:1024], app)
        if not u:
            wait = users.attempt_failed(visitor, name)
            authlog.warning("failed sign-in as %r from %s (wrong user name or password%s)", name, src, f"; {wait} s wait" if wait else "")
            raise HTTPException(401, "Wrong user name or password")
        if u.get("passwordless") and proxy.external(request.headers, peer_of(request)):
            authlog.warning("one-click sign-in as %s refused from %s (outside: a password is required)", u["name"], src)
            raise HTTPException(403, "From outside your network, sign in with an account that has a password")
        two_step = not u.get("passwordless") and await run_in_threadpool(twostep.enabled, u["id"])
        if two_step:
            # the password was right: the code app's code (or a recovery code) comes with it in a second request.
            # twoStep tells the sign-in screen to ask for it; a wrong code counts like a wrong password
            code = str(body.get("code") or "")[:64].strip()
            if not code:
                return JSONResponse({"detail": "Enter the code from your code app", "twoStep": True}, status_code=401)
            if not await run_in_threadpool(twostep.check, u["id"], code):
                wait = users.attempt_failed(visitor, name)
                authlog.warning("failed sign-in as %r from %s (wrong two-step code%s)", name, src, f"; {wait} s wait" if wait else "")
                return JSONResponse({"detail": "That code is not right", "twoStep": True}, status_code=401)
        users.attempt_succeeded(visitor, name)
        if u["role"] == "none":
            authlog.warning("sign-in as %s refused: no access to %s", u["name"], app)
            raise HTTPException(403, f"Your account has no access to {auth.label}")
        authlog.info("signed in: %s (%s, %s) from %s", u["name"], u["role"],
                     "one click" if u.get("passwordless") else "password and code" if two_step else "password", src)
        u = auth.decorate(u)
        resp = JSONResponse({"user": u, "settings": users.get_settings(u["id"], app)})
        auth.sign_in(resp, request, u, "oneclick" if u.get("passwordless") else "password")
        return resp

    # ---- passkeys at the sign-in screen (iosuite_shared.passkeys): offered only where somebody has one
    @r.get("/api/auth/login/passkey", dependencies=[access.public])
    def api_passkey_offered(request: Request):
        """{available}: whether anybody has a passkey for the address this is asked at."""
        return {"available": users.any_users() and passkeys.any_at(passkeys.rp_id(sessions.host_of(request)))}

    @r.post("/api/auth/login/passkey/begin", dependencies=[access.public])
    def api_passkey_begin(request: Request):
        """What navigator.credentials.get takes: {challenge, rpId, userVerification, timeout}."""
        rp = passkeys.rp_id(sessions.host_of(request))
        if not passkeys.any_at(rp):
            raise HTTPException(404, "Nobody has a passkey here yet; add one in Settings › Account")
        return passkeys.begin_sign_in(sessions.host_of(request))

    @r.post("/api/auth/login/passkey", dependencies=[access.public])
    async def api_passkey_login(request: Request):
        """The browser's answer {id, clientDataJSON, authenticatorData, signature}: signed in, as after a password."""
        body = await json_body(request)
        src, visitor = proxy.source(request), proxy.visitor_of(request)
        wait = users.attempt_wait(visitor, "")
        if wait:
            raise HTTPException(429, f"Too many attempts; try again in {wait} seconds", headers={"Retry-After": str(wait)})
        try:
            uid = await run_in_threadpool(passkeys.sign_in, body)
        except ValueError as e:
            users.attempt_failed(visitor, "")
            authlog.warning("failed passkey sign-in from %s (%s)", src, e)
            raise HTTPException(401, str(e))
        u = await run_in_threadpool(users.get, uid, app)
        if not u or u.get("service") or u.get("passwordless"):
            raise HTTPException(401, "This passkey is not known here (it may have been removed)")
        if u["role"] == "none":
            authlog.warning("sign-in as %s refused: no access to %s", u["name"], app)
            raise HTTPException(403, f"Your account has no access to {auth.label}")
        users.attempt_succeeded(visitor, "")
        users.touch_login(u["id"])
        authlog.info("signed in: %s (%s, passkey) from %s", u["name"], u["role"], src)
        u = auth.decorate(u)
        resp = JSONResponse({"user": u, "settings": users.get_settings(u["id"], app)})
        auth.sign_in(resp, request, u, "passkey")
        return resp

    @r.get("/api/auth/accounts", dependencies=[access.public])
    def api_accounts(request: Request):
        """The accounts the sign-in screen shows as tiles, inside the network only: from outside the list is empty and
        the screen asks for a name, so the names of the household are not handed to anyone who can reach the address."""
        if not users.any_users() or proxy.external(request.headers, peer_of(request)):
            return {"accounts": []}
        return {"accounts": [auth.decorate(a) for a in users.accounts(app)]}

    @r.post("/api/auth/logout", dependencies=[access.public])
    def api_logout(request: Request):
        u = auth.current_user(request)
        if u:
            authlog.info("signed out: %s from %s", u["name"], proxy.source(request))
        sessions.end(request.cookies.get(sessions.COOKIE))
        outside = proxy.external(request.headers, peer_of(request))
        resp = JSONResponse({"ok": True, "cloudflareLogout": "/cdn-cgi/access/logout" if outside else None})
        sessions.clear_cookie(resp, sessions.host_of(request), cloudflare_cookie=not outside)
        return resp

    @r.get("/api/auth/me", dependencies=[access.public])
    def api_me(request: Request):
        return auth.me(request)

    def account(request: Request) -> dict:
        """The signed-in account, for the routes about one's own account: before the first account exists everyone
        passes `signed_in`, but there is nobody to keep app passwords, notifications or settings for."""
        u = auth.current_user(request)
        if not u:
            raise HTTPException(401, "Sign in first")
        return u

    @r.patch("/api/auth/me", dependencies=[access.signed_in])
    async def api_patch_me(request: Request):
        """The signed-in account's display name and email ({displayName, email}; empty clears). Settings › Account."""
        u = account(request)
        body = await json_body(request)
        f = {}
        if "displayName" in body:
            f["display_name"] = str(body["displayName"] or "")[:128]
        if "email" in body:
            f["email"] = str(body["email"] or "")[:254]
        try:
            nu = await run_in_threadpool(lambda: users.update(u["id"], **f))
        except ValueError as e:
            raise HTTPException(400, str(e))
        apppasswords.forget()
        if auth.on_update:  # only what one may change oneself: an app's own fields (ioPix's person tag) are the panel's
            auth.on_update(u["id"], {k: body[k] for k in ("displayName", "email") if k in body})
        return {"user": public_user(nu)}

    @r.get("/api/auth/ui.js", dependencies=[access.public])
    def api_account_ui(request: Request):
        """The account panels (static/account-panel.js): Settings › Account, the theme switch and the app passwords,
        the same in every app: ui = await import(new URL('api/auth/ui.js', document.baseURI).href)."""
        return pages.send(request, pages.SHARED / "account-panel.js", "text/javascript")

    @r.get("/api/auth/frame.js", dependencies=[access.public])
    def api_frame(request: Request):
        """The frame the apps' pages share (static/frame.js): icons, the note at the foot of the page, dialogs, the
        menu of the suite's apps, the sidebar, the theme: import { ... } from '../api/auth/frame.js'."""
        return pages.send(request, pages.SHARED / "frame.js", "text/javascript")

    @r.get("/api/auth/base.css", dependencies=[access.public])
    def api_base_css(request: Request):
        """The look the single-page io apps share (static/base.css), linked before each one's own static/app.css."""
        return pages.send(request, pages.SHARED / "base.css", "text/css")

    @r.post("/api/auth/settings", dependencies=[access.signed_in])
    async def api_my_settings(request: Request):
        u = account(request)
        return users.set_settings(u["id"], app, await json_body(request))

    async def own_password(request: Request, u: dict, current: str, what: str):
        """The account's password, asked again before a change to how it signs in (a new password, a passkey, the
        second step): a session left open on a shared computer changes none of them. Wrong ones are counted."""
        if u.get("passwordless"):
            raise HTTPException(403, "This account signs in with one click; a suite admin can give it a password under Settings › People")
        pkey = f"pw|{u['id']}"
        wait = users.login_wait(pkey)
        if wait:
            raise HTTPException(429, f"Too many attempts; try again in {wait} seconds", headers={"Retry-After": str(wait)})
        if not await run_in_threadpool(users.authenticate, u["name"], str(current or "")[:1024]):
            users.login_failed(pkey)
            authlog.warning("%s for %s refused from %s (wrong current password)", what, u["name"], proxy.source(request))
            raise HTTPException(403, "The current password is wrong")
        users.login_succeeded(pkey)

    @r.post("/api/auth/password", dependencies=[access.signed_in])
    async def api_my_password(request: Request):
        u = account(request)
        body = await json_body(request)
        new = str(body.get("password", ""))[:1024]
        if not new and not u.get("passwordless"):
            raise HTTPException(400, "A new password is needed")  # removing a password is an admin's decision, never this route's
        await own_password(request, u, body.get("current", ""), "password change")
        try:
            users.update(u["id"], password=new)
        except ValueError as e:
            raise HTTPException(400, str(e))
        apppasswords.forget()
        authlog.info("password changed: %s from %s", u["name"], proxy.source(request))
        resp = JSONResponse({"ok": True})
        auth.sign_in(resp, request, u, request.cookies.get(sessions.VIA_COOKIE) or "password")  # the old sessions are dead now; this one goes on
        return resp

    # ---- Settings › Account › Sign-in: passkeys and the second step, each off until the person turns it on
    def sign_in_ways(request: Request, u: dict) -> dict:
        rp = passkeys.rp_id(sessions.host_of(request))
        return {"available": not u.get("passwordless"), "rpId": rp, "passkeys": passkeys.list_for(u["id"], rp), "twoStep": twostep.status(u["id"])}

    @r.get("/api/auth/sign-in", dependencies=[access.signed_in])
    def api_sign_in_ways(request: Request):
        """{available (not for a one-click account), rpId, passkeys: [{id, label, created, lastUsed, rpId, here}],
        twoStep: {on, since, recoveryLeft}}."""
        return sign_in_ways(request, account(request))

    @r.post("/api/auth/passkeys/begin", dependencies=[access.signed_in])
    async def api_passkey_add_begin(request: Request):
        """{password}: what navigator.credentials.create takes, for a passkey at the address this is asked at."""
        u, body = account(request), await json_body(request)
        await own_password(request, u, body.get("password"), "a new passkey")
        try:
            return await run_in_threadpool(passkeys.begin_add, u, sessions.host_of(request))
        except ValueError as e:
            raise HTTPException(400, str(e))

    @r.post("/api/auth/passkeys", dependencies=[access.signed_in])
    async def api_passkey_add(request: Request):
        """The browser's new passkey {clientDataJSON, authenticatorData, publicKey, alg, label}."""
        u, body = account(request), await json_body(request)
        try:
            made = await run_in_threadpool(passkeys.add, u, body)
        except ValueError as e:
            raise HTTPException(400, str(e))
        authlog.info("passkey added: %s (%s) from %s", u["name"], made["label"], proxy.source(request))
        return sign_in_ways(request, u)

    @r.delete("/api/auth/passkeys/{passkey_id}", dependencies=[access.signed_in])
    def api_passkey_remove(passkey_id: int, request: Request):
        u = account(request)
        if not passkeys.remove(u["id"], passkey_id):
            raise HTTPException(404, "No such passkey")
        authlog.info("passkey removed: %s from %s", u["name"], proxy.source(request))
        return sign_in_ways(request, u)

    @r.post("/api/auth/two-step/begin", dependencies=[access.signed_in])
    async def api_two_step_begin(request: Request):
        """{password}: a secret for the code app, {secret, uri, qr (an SVG)}; not on until a code from it comes back."""
        u, body = account(request), await json_body(request)
        await own_password(request, u, body.get("password"), "two-step sign-in")
        try:
            made = await run_in_threadpool(twostep.begin, u)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {**made, "qr": twostep.qr_svg(made["uri"])}

    @r.post("/api/auth/two-step", dependencies=[access.signed_in])
    async def api_two_step_on(request: Request):
        """{code}: the first code from the code app turns it on; {recovery: [...]} is shown this once."""
        u, body = account(request), await json_body(request)
        try:
            codes = await run_in_threadpool(twostep.confirm, u["id"], str(body.get("code") or "")[:64])
        except ValueError as e:
            raise HTTPException(400, str(e))
        apppasswords.forget()  # the account password no longer signs a sync client in
        authlog.info("two-step sign-in turned on: %s from %s", u["name"], proxy.source(request))
        return {"recovery": codes, **sign_in_ways(request, u)}

    @r.post("/api/auth/two-step/off", dependencies=[access.signed_in])
    async def api_two_step_off(request: Request):
        """{password}: turn it off."""
        u, body = account(request), await json_body(request)
        await own_password(request, u, body.get("password"), "turning two-step sign-in off")
        twostep.disable(u["id"])
        apppasswords.forget()
        authlog.info("two-step sign-in turned off: %s from %s", u["name"], proxy.source(request))
        return sign_in_ways(request, u)

    @r.post("/api/auth/setup", dependencies=[access.public])
    async def api_setup(request: Request):
        """The first account (a suite admin), allowed only while no account exists, from inside the network."""
        if users.any_users():
            raise HTTPException(409, "Users already exist; sign in as an admin")
        if proxy.external(request.headers, peer_of(request)):
            authlog.warning("first-account setup refused from outside (%s)", proxy.source(request))
            raise HTTPException(403, UNCLAIMED)
        body = await json_body(request)
        try:
            u = users.create(str(body.get("name", ""))[:64], str(body.get("password", ""))[:1024], "admin", app,
                             email=str(body.get("email") or ""), display_name=str(body.get("displayName") or ""), suite_admin=True,
                             first=True)
        except users.FirstTaken as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        authlog.info("first account created and signed in: %s (suite admin) from %s", u["name"], proxy.source(request))
        resp = JSONResponse({"user": u})
        auth.sign_in(resp, request, u, "password")
        return resp

    @r.get("/api/auth/sessions", dependencies=[access.signed_in])
    def api_sessions(request: Request):
        """The signed-in account's sessions in every app: where and how each began and was last seen."""
        u = auth.current_user(request)
        return {"sessions": sessions.list_sessions(u["id"], request.cookies.get(sessions.COOKIE)) if u else []}

    @r.delete("/api/auth/sessions/{session_id}", dependencies=[access.signed_in])
    def api_end_session(session_id: str, request: Request):
        """End one of the signed-in account's sessions (another browser or device)."""
        u = account(request)
        sessions.end_one(u["id"], session_id)
        return {"ok": True}

    @r.get("/api/auth/app-passwords", dependencies=[access.signed_in])
    def api_app_passwords(request: Request):
        """The account's app passwords here; scope '' works everywhere, 'dav' for the sync protocols only. scopes:
        what this app offers (no 'dav' in an app without DAV)."""
        return {"items": apppasswords.list_for(account(request)["id"], app), "scopes": ["", *auth.scope_paths]}

    @r.post("/api/auth/app-passwords", dependencies=[access.signed_in])
    async def api_new_app_password(request: Request):
        u = account(request)
        if u.get("passwordless"):
            raise HTTPException(403, "A one-click account cannot have app passwords")
        body = await json_body(request)
        scope = str(body.get("scope") or "")
        if scope and scope not in auth.scope_paths:
            raise HTTPException(400, f"Unknown scope: {scope}")
        pw = await run_in_threadpool(apppasswords.create, u["id"], app, str(body.get("label") or "Device").strip(), scope)
        return {"password": pw, "name": u["name"], "scope": scope}

    @r.delete("/api/auth/app-passwords/{pid}", dependencies=[access.signed_in])
    def api_del_app_password(pid: int, request: Request):
        apppasswords.delete(account(request)["id"], pid)
        return {"ok": True}

    # ---- notifications (iosuite_shared.push): Settings › Account › Notifications, the same in every app
    @r.get("/api/auth/push/sw.js", dependencies=[access.public])
    def api_push_worker(request: Request):
        """The service worker that shows the notifications: push only (no caching, no fetch handler), registered with
        this folder as its scope so it never stands between the app and its pages."""
        return pages.send(request, pages.SHARED / "push-sw.js", "text/javascript")

    @r.get("/api/auth/push", dependencies=[access.signed_in])
    def api_push(request: Request):
        """{key, morning, kinds: [{kind, label, hint, on, admin}], devices: [{id, label, app, appName, created, lastOk, endpointHash}]}."""
        return push.overview(account(request))

    @r.post("/api/auth/push/devices", dependencies=[access.signed_in])
    async def api_push_add(request: Request):
        """This browser's push subscription ({subscription: {endpoint, keys}, standalone}): notifications on here."""
        u, body = account(request), await json_body(request)
        d = await run_in_threadpool(push.add_device, u["id"], body.get("subscription") or {}, app,
                                    request.headers.get("user-agent") or "", bool(body.get("standalone")))
        return {"device": d, **push.overview(u)}

    @r.delete("/api/auth/push/devices/{device_id}", dependencies=[access.signed_in])
    def api_push_remove(device_id: int, request: Request):
        u = account(request)
        if not push.remove_device(u["id"], device_id):
            raise HTTPException(404, "No such device")
        return push.overview(u)

    @r.put("/api/auth/push/prefs", dependencies=[access.signed_in])
    async def api_push_prefs(request: Request):
        """{kinds: {kind: bool}, morning: 'HH:MM'}: what this account gets, on every device."""
        u, body = account(request), await json_body(request)
        push.set_prefs(u["id"], body.get("kinds") if isinstance(body.get("kinds"), dict) else None, body.get("morning"))
        return push.overview(u)

    @r.post("/api/auth/push/test", dependencies=[access.signed_in])
    async def api_push_test(request: Request):
        """A test notification to every device of this account: {sent, devices}."""
        u = account(request)
        n = await run_in_threadpool(push.notify, u["id"], "test", "Notifications work",
                                    f"Sent from {auth.label}. Every app of the suite reaches you here.", push.link(app), None,
                                    "test", 600, "normal", False)
        return {"sent": n, "devices": len(push.devices(u["id"]))}

    @r.get("/api/auth/suite", dependencies=[access.signed_in])
    def api_suite(request: Request):
        """The suite's installed apps this account may use and where they are, for the start page and app switchers
        (suite.visible: the apps it has a role in; an admin tool only where it is an admin)."""
        return {"items": suite.visible(auth.current_user(request)), "app": app}

    @r.get("/api/auth/family", dependencies=[access.signed_in])
    def api_family(request: Request):
        """The family (iosuite_shared.family): [{id, name, displayName, initials, color, hasFace}], by display name. The
        same list, colours and initials in every app; suite admins change it in Settings › People › Family."""
        return {"items": [family.public(m) for m in family.members()]}

    @r.get("/api/auth/family/{uid}/face", dependencies=[access.signed_in])
    def api_family_face(uid: int, request: Request):
        """A member's face: their person's in ioPix, else their ioContact card's photo; 404 when there is none."""
        if not family.get(uid):
            raise HTTPException(404, "No such member")
        try:
            data, ctype = family.face(app, uid)
        except LookupError:
            raise HTTPException(404, "No face")
        return Response(data, media_type=ctype, headers={"Cache-Control": "private, max-age=3600"})

    # ---- the estate planning PDF (iosuite_shared.estate): a suite admin for anyone, a person for themselves
    estate_access = access.custom("estate", lambda u, _r: bool(u), "Sign in to use this")

    def estate_check(request: Request, uid: int) -> dict:
        me_ = auth.current_user(request)
        if not estate.may(me_, uid):
            raise HTTPException(403, "Only a suite admin can make someone else's estate PDF")
        return me_

    @r.get("/api/auth/estate/{uid}", dependencies=[estate_access])
    def api_estate_part(uid: int, request: Request):
        """This app's part of the person's estate PDF: {sections}. Nothing for a person with no role here."""
        me_ = estate_check(request, uid)
        if not users.is_suite_admin(me_) and not users.is_signed_in(me_):
            return {"sections": []}
        return {"sections": estate.local(auth, uid, me_)}

    @r.get("/api/auth/estate/{uid}/files/{ref}", dependencies=[estate_access])
    def api_estate_file(uid: int, ref: str, request: Request):
        """A file an item of this app's part names (a document's scan)."""
        me_ = estate_check(request, uid)
        if not users.is_suite_admin(me_) and not users.is_signed_in(me_):
            raise HTTPException(404, "No such file")
        try:
            data, ctype, _name = estate.local_file(auth, uid, ref)
        except LookupError:
            raise HTTPException(404, "No such file")
        return Response(data, media_type=ctype, headers={"Cache-Control": "no-store"})

    @r.get("/api/auth/estate/{uid}/pdf", dependencies=[estate_access])
    def api_estate_pdf(uid: int, request: Request):
        """The whole PDF, from every app of the suite."""
        me_ = estate_check(request, uid)
        try:
            data, name = estate.build(auth, request, me_, uid)
        except LookupError:
            raise HTTPException(404, "No such person")
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})

    return r

def admin_router(self) -> APIRouter:
    """Suite administration (suite admins only), everything in the Shared ioSuite database at /api/suite-admin/*:
    accounts with their role in every app, every app password, sessions, every app's keys and tokens (never their
    values), and the apps with their access settings (iosuite_shared.admin)."""
    auth, access = self, self.access
    r = APIRouter(prefix="/api/suite-admin")

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except LookupError as e:
            raise HTTPException(404, str(e).strip("'\""))
        except ValueError as e:
            raise HTTPException(400, str(e))

    def me(request: Request):
        """The caller; the route's access.suite_admin marker has already let only a suite admin this far."""
        return auth.current_user(request)

    @r.get("/ui.js", dependencies=[access.suite_admin])
    def api_ui(request: Request):
        """The panel itself (static/suite-admin.js), one ES module every app mounts in its Settings › People, Apps, Servers and Keys tabs:
        ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); ui.mount(el, {sub, toast})."""
        return pages.send(request, pages.SHARED / "suite-admin.js", "text/javascript")

    @r.get("", dependencies=[access.suite_admin])
    def api_overview(request: Request):
        return {**suite_admin.overview(), "me": (me(request) or {}).get("id"), "app": auth.app}

    @r.post("/users", dependencies=[access.suite_admin])
    async def api_create(request: Request):
        body = await json_body(request)
        u = await run_in_threadpool(call, suite_admin.create, me(request), body)
        authlog.info("suite admin: account %s made by %s", u["name"], (auth.current_user(request) or {}).get("name"))
        return u

    @r.patch("/users/{user_id}", dependencies=[access.suite_admin])
    async def api_update(user_id: int, request: Request):
        body = await json_body(request)
        u = await run_in_threadpool(call, suite_admin.update, me(request), user_id, body)
        if self.on_update:
            self.on_update(user_id, body)
        return u

    @r.get("/users/{user_id}/data", dependencies=[access.suite_admin])
    def api_person_data_everywhere(user_id: int, request: Request):
        """What deleting the account would remove: {apps: [{app, name, items: [{what, count, kept}], error}], shared}."""
        if not suite_admin.person(user_id):
            raise HTTPException(404, "No such user")
        return {"apps": persondata.everywhere(auth, request, user_id), "shared": persondata.shared_part(user_id)}

    @r.delete("/users/{user_id}", dependencies=[access.suite_admin])
    def api_delete(user_id: int, request: Request):
        """The account and what the person kept in every app; what was removed: {ok, apps, shared}."""
        got = call(persondata.delete_account, auth, request, me(request), user_id)
        authlog.info("suite admin: account %s deleted with its data in every app by %s", user_id, (me(request) or {}).get("name"))
        return {"ok": True, **got}

    @r.get("/person-data/{user_id}", dependencies=[access.suite_admin])
    def api_person_data(user_id: int):
        """This app's part of what the person keeps (persondata): {items: [{what, count, kept}]}."""
        return {"items": persondata.local(auth, user_id)}

    @r.delete("/person-data/{user_id}", dependencies=[access.suite_admin])
    def api_person_data_remove(user_id: int):
        """Remove this app's part (the panel asks every app before it deletes the account): what was removed."""
        return {"items": persondata.local(auth, user_id, remove=True)}

    @r.get("/photo-people", dependencies=[access.suite_admin])
    def api_photo_people(request: Request):
        """The people in ioPix's People, to link an account to (its person in photos), read from ioPix."""
        return suite_admin.photo_people(auth.app)

    @r.get("/photo-people/{person}/face.jpg", dependencies=[access.suite_admin])
    def api_photo_face(person: int, request: Request):
        return Response(call(suite_admin.photo_face, auth.app, person), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})

    @r.get("/family", dependencies=[access.suite_admin])
    def api_family_all(request: Request):
        """Everyone with an account, in the family or not, with their colour, initials and links (iosuite_shared.family),
        and the names of their ioContact cards."""
        items = family.everyone()
        cards = {}
        for m in items:
            if m["contactId"] and m["contactId"] not in cards:
                cards[m["contactId"]] = (family.contact(auth.app, m["contactId"]) or {}).get("fn")
        return {"items": [{**m, "contactName": cards.get(m["contactId"])} for m in items], "palette": family.PALETTE}

    @r.patch("/family/{user_id}", dependencies=[access.suite_admin])
    async def api_family_update(user_id: int, request: Request):
        """{inFamily?, color?, contactId?, photoPerson?} for one account (iosuite_shared.family.update)."""
        body = await json_body(request)
        m = await run_in_threadpool(call, family.update, user_id, body)
        authlog.info("suite admin: family entry of %s changed by %s: %s", m["name"], (me(request) or {}).get("name"), ", ".join(sorted(body)))
        if self.on_update:
            self.on_update(user_id, body)
        return m

    @r.get("/family/contacts", dependencies=[access.suite_admin])
    def api_family_contacts(request: Request, q: str = ""):
        """Cards in ioContact to link a member to, read from ioContact."""
        return family.contacts(auth.app, q[:100])

    @r.get("/users/{user_id}/sessions", dependencies=[access.suite_admin])
    def api_sessions(user_id: int, request: Request):
        if not suite_admin.person(user_id):
            raise HTTPException(404, "No such user")
        return {"sessions": sessions.list_sessions(user_id, request.cookies.get(sessions.COOKIE))}

    @r.delete("/users/{user_id}/sessions", dependencies=[access.suite_admin])
    def api_end_sessions(user_id: int, request: Request):
        """Every session of the account, or one with ?session=<id>."""
        call(suite_admin.end_sessions, user_id, request.query_params.get("session"))
        return {"ok": True}

    @r.get("/app-passwords", dependencies=[access.suite_admin])
    def api_app_passwords(request: Request, user: int = None, app: str = None):
        return {"items": call(suite_admin.app_passwords, user, app)}

    @r.post("/app-passwords", dependencies=[access.suite_admin])
    async def api_new_app_password(request: Request):
        body = await json_body(request)
        try:
            uid = int(body.get("userId"))
        except (TypeError, ValueError):
            raise HTTPException(400, "userId is needed")
        return await run_in_threadpool(call, suite_admin.new_app_password, uid, body.get("app"), str(body.get("label") or ""),
                                       str(body.get("scope") or ""))

    @r.patch("/app-passwords/{pid}", dependencies=[access.suite_admin])
    async def api_app_password_scope(pid: int, request: Request):
        body = await json_body(request)
        call(suite_admin.set_app_password_scope, pid, str(body.get("scope") or ""))
        return {"ok": True}

    @r.delete("/app-passwords/{pid}", dependencies=[access.suite_admin])
    def api_revoke_app_password(pid: int, request: Request):
        call(suite_admin.revoke_app_password, pid)
        return {"ok": True}

    @r.get("/keys", dependencies=[access.suite_admin])
    def api_keys(request: Request, app: str = None):
        """Every key and token the apps keep (never the values)."""
        return {"items": call(suite_admin.keys, app)}

    @r.put("/keys/{app}/{name}", dependencies=[access.suite_admin])
    async def api_set_key(app: str, name: str, request: Request):
        """{value}: replace it; '' clears it."""
        body = await json_body(request)
        who = me(request)
        k = await run_in_threadpool(call, suite_admin.set_key, who, app, name, body.get("value"))
        authlog.info("suite admin: %s %s of %s by %s", "set" if k["set"] else "cleared", name, app, (who or {}).get("name"))
        return k

    @r.delete("/keys/{app}/{name}", dependencies=[access.suite_admin])
    def api_clear_key(app: str, name: str, request: Request):
        who = me(request)
        call(suite_admin.set_key, who, app, name, None)
        authlog.info("suite admin: cleared %s of %s by %s", name, app, (who or {}).get("name"))
        return {"ok": True}

    @r.patch("/apps/{key}", dependencies=[access.suite_admin])
    async def api_app(key: str, request: Request):
        body = await json_body(request)
        mcp = "keep"
        if "mcp" in body:  # this app's MCP server: on, off, or null to follow the suite's switch
            mcp = None if body["mcp"] is None else bool(body["mcp"])
        if key == "_suite" and mcp != "keep":  # the switch every app follows unless it says otherwise
            from iosuite_shared import mcp as shared_mcp
            call(shared_mcp.set_for, "", mcp)
            return {"app": "_suite", "mcpSuite": bool(mcp)}
        return call(suite_admin.set_app, key, default_role=body.get("defaultRole"),
                    require_login=None if body.get("requireLogin") is None else bool(body["requireLogin"]), mcp=mcp)

    @r.delete("/apps/{key}", dependencies=[access.suite_admin])
    def api_forget_app(key: str, request: Request, data: int = 0):
        """Take an app off the list; ?data=1 also removes its roles, settings and app passwords."""
        if not call(suite_admin.forget_app, key, bool(data)):
            raise HTTPException(404, "No such app")
        if key == auth.app:
            auth._registered = False
        return {"ok": True}

    @r.get("/addresses", dependencies=[access.suite_admin])
    def api_addresses(request: Request):
        """Where every app answers at each of the three doors (iosuite_shared.doors): the suite's address, each
        app's own, and the copy it runs in."""
        return call(suite_admin.addresses)

    @r.get("/settings", dependencies=[access.suite_admin])
    def api_settings(request: Request):
        """Every setting the apps read as they start, the whole suite's and each app's, with the value stored now."""
        return call(suite_admin.settings)

    @r.put("/settings/{app}/{name}", dependencies=[access.suite_admin])
    async def api_set_setting(app: str, name: str, request: Request):
        """{value}: store it ('' removes it: the default again). app _suite: the whole suite's. It takes effect when
        the app starts again (POST /restart)."""
        body = await json_body(request)
        who = me(request)
        out = await run_in_threadpool(call, suite_admin.set_setting, app, name, body.get("value"))
        authlog.info("suite admin: setting %s of %s %s by %s", name, out["app"] or "the suite", "set" if out["value"] else "cleared", (who or {}).get("name"))
        return out

    @r.post("/restart", dependencies=[access.suite_admin])
    async def api_restart(request: Request):
        """Body {apps: [keys]} (none: every app): the copies running them start again within seconds, so that
        changed settings apply. An app restarts with the others of its copy."""
        body = await json_body(request) if int(request.headers.get("content-length") or 0) else {}
        who = me(request)
        asked = await run_in_threadpool(call, suiteupdates.request, "restart", (who or {}).get("name"), body.get("apps") or None)
        authlog.info("suite admin: restart asked of %s by %s", ", ".join(asked) or "no app", (who or {}).get("name"))
        return {"asked": asked}

    @r.get("/logs", dependencies=[access.suite_admin])
    async def api_logs(request: Request, app: str = "", level: str = "any", contains: str = "", requests: int = 0, since: float = 0,
                       until: float = 0, limit: int = 300, after: str = "", local: int = 0):
        """The suite's log (iosuite_shared.admin.logs): every copy's lines on one timeline, filtered by app ("-":
        nobody's), level (any, info, warning, error, auth), time (since, until: seconds since 1970) and text
        (contains); requests=1: page requests too. after: the cursors of an earlier answer (JSON {copy: cursor}), for
        what was written since. local=1: this copy's lines only (what another copy asks; after: its cursor)."""
        from iosuite_shared import logs as log
        filters = {"app": app, "level": level, "contains": contains, "requests": bool(requests), "since": since, "until": until}
        if local:
            return await run_in_threadpool(log.read, limit=limit, after=after, **filters)
        try:
            cursors = json.loads(after) if after else {}
        except ValueError:
            cursors = {}
        out = await run_in_threadpool(suite_admin.logs, request, cursors, limit, **filters)
        out["app"] = auth.app
        return out

    def updates_now():
        from iosuite_shared import updates as upd
        return {**suiteupdates.summary(), "autoCheck": upd.auto_check_enabled()}

    @r.get("/updates", dependencies=[access.suite_admin])
    def api_updates(request: Request):
        """The suite's version, the newest on GitHub and whether an update is waiting or running, with every app's
        own line (iosuite_shared.suiteupdates.summary), and the daily-check switch (autoCheck)."""
        return updates_now()

    @r.post("/updates", dependencies=[access.suite_admin])
    async def api_updates_ask(request: Request):
        """Body {action: check | update | restart}: every app asks GitHub, every app that is behind updates itself,
        or the apps named by `apps` start again (none: every app, so every copy of the program); they pick it up
        within seconds. {autoCheck: bool} saves the daily check, one switch for the suite."""
        from iosuite_shared import updates as upd
        body = await json_body(request)
        who = me(request)
        if "autoCheck" in body:
            await run_in_threadpool(upd.set_auto_check, bool(body["autoCheck"]))
        asked = []
        if body.get("action") or "autoCheck" not in body:
            asked = await run_in_threadpool(call, suiteupdates.request, body.get("action"), (who or {}).get("name"),
                                            body.get("apps") or None)
            authlog.info("suite admin: %s asked of %s by %s", body.get("action"), ", ".join(asked) or "no app", (who or {}).get("name"))
        return {"asked": asked, **await run_in_threadpool(updates_now)}

    @r.get("/jobs", dependencies=[access.suite_admin])
    async def api_jobs():
        """Every app's background jobs (iosuite_shared.jobs): what each one is, the copy that runs it, when it last
        ran, how long it took, what it said and what failed."""
        from iosuite_shared import jobs
        return await run_in_threadpool(call, jobs.summary)

    @r.post("/jobs", dependencies=[access.suite_admin])
    async def api_jobs_run(request: Request):
        """Body {app, name}: run that job now. The copy that owns it picks the request up within a few seconds,
        wherever that copy is."""
        from iosuite_shared import jobs
        body = await json_body(request)
        app, name = str(body.get("app") or ""), str(body.get("name") or "")
        who = me(request)
        asked = await run_in_threadpool(call, jobs.run_now, app, name, (who or {}).get("name") or "")
        if not asked:
            raise HTTPException(400, "No such job: it may have been renamed, or its app may not be running.")
        authlog.info("suite admin: job %s of %s asked to run by %s", name, app, (who or {}).get("name"))
        return await run_in_threadpool(call, jobs.summary)

    @r.get("/certificate", dependencies=[access.suite_admin])
    def api_certificate(request: Request):
        """The suite's own certificate (iosuite_shared.certs): what is set, the names it is asked for, the one stored,
        how the last asking went, and what this server serves."""
        from iosuite_shared import certs
        return call(certs.status)

    @r.put("/certificate", dependencies=[access.suite_admin])
    async def api_certificate_save(request: Request):
        """Body: any of on, email, ca (letsencrypt, staging, or an ACME directory's address), proof (http or
        cloudflare), names (beside the suite's addresses), token (Cloudflare's, for the proof through DNS)."""
        from iosuite_shared import certs
        body = await json_body(request)
        who = me(request)
        out = await run_in_threadpool(call, certs.save, body, (who or {}).get("name"))
        authlog.info("suite admin: the suite's certificate is %s (%s, proof %s) by %s", "on" if out["on"] else "off", out["ca"], out["proof"], (who or {}).get("name"))
        return out

    @r.post("/certificate", dependencies=[access.suite_admin])
    async def api_certificate_ask(request: Request):
        """Ask the authority for a certificate now. The answer comes when the authority has looked (up to a few
        minutes); 502 with the authority's own words when it says no. A server that has to open its HTTPS ports
        starts again right after."""
        from iosuite_shared import acme, certs
        who = me(request)
        try:
            have = await run_in_threadpool(call, certs.ask_now)
        except acme.Problem as e:
            authlog.info("suite admin: a certificate asked by %s was not given: %s", (who or {}).get("name"), e.detail)
            raise HTTPException(502, f"The certificate was not given. {e.detail}")
        authlog.info("suite admin: a certificate for %s asked by %s", ", ".join(have["names"]), (who or {}).get("name"))
        return await run_in_threadpool(call, certs.status)

    @r.get("/proxy", dependencies=[access.suite_admin])
    def api_proxy(request: Request):
        """Sign-in at a reverse proxy (Cloudflare Access...) for the whole suite: the values, the last token seen."""
        return {**proxyauth.suite_status(), "here": auth.proxy.status()}

    @r.put("/proxy", dependencies=[access.suite_admin])
    async def api_proxy_save(request: Request):
        """Body: any of AUTH_PROXY, AUTH_PROXY_HEADER, AUTH_PROXY_TRUSTED, AUTH_PROXY_CREATE, CF_ACCESS_TEAM,
        CF_ACCESS_AUD (empty clears one). CF_ACCESS_AUD: one AUD tag or several, comma-separated."""
        body = await json_body(request)
        call(proxyauth.save_suite, body)
        return {**proxyauth.suite_status(), "here": auth.proxy.status()}

    return r

# ---- the status: public, the same shape in every app
def status_router(self, updater=None, extra=None) -> APIRouter:
    """GET /api/status, open to everyone (the middleware keeps it reachable when sign-in is required): what the shell
    needs before anyone signs in.
        {ok, app, name, version (signed in, or asked from inside the network), usersExist, requireLogin, signedIn,
         isAdmin, viaProxy, user, commit (signed in)}
    `extra(request)` adds the app's own fields (a dict); it is called after the user is known, so it may answer
    differently for a visitor, an account and an admin."""
    auth, access = self, self.access
    r = APIRouter()

    @r.get(STATUS_PATH, dependencies=[access.public])
    async def api_status(request: Request):
        return await run_in_threadpool(status, auth, request, updater, extra)

    return r


def status(self, request: Request, updater=None, extra=None) -> dict:
    """What GET /api/status answers (also for an app that has to serve it from its own route): Auth.status."""
    u = self.current_user(request)
    shut = self.unclaimed(request)  # no account yet, asked from outside the network: nothing is open
    signed, admin = users.is_signed_in(u) and not shut, users.is_admin(u) and not shut
    version = (self.suite_entry or {}).get("version") or (updater.version if updater else None)
    out = {"ok": True, "app": self.app, "name": self.label, "version": version if signed or not self.outside(request) else None,
           "usersExist": users.any_users(), "requireLogin": shut or users.require_login(self.app), "signedIn": signed, "isAdmin": admin,
           "viaProxy": bool(getattr(request.state, "via_proxy", False)), "user": public_user(u)}
    if updater is not None and signed:
        out["commit"] = updater.local_commit()[:7]
    if extra:
        out.update(extra(request) or {})
    return out


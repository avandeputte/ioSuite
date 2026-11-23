"""An app of the suite asking another that runs in the same copy: handed to it in this process (iosuite_shared.inside),
with the same sign-in and the same answer, and over the network when it runs in another copy.

Nothing here opens a port, so a call that comes back proves it did not go over the network.
"""
import asyncio
import json
import threading
import time
import urllib.error

import pytest
from fastapi import FastAPI, Request

from iosuite_shared import config, doors, inside, links, prefix, suite, users
from iosuite_shared.fastapi import Auth
from iosuite_shared.host import Entry, Host


def an_app(name: str, routes=None):
    """A stand-in for an app of the suite: it says what the host handed it, and what its sign-in made of it."""
    app = FastAPI()
    auth = Auth(name, register=False)
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())

    @app.get("/api/what")
    def what(request: Request):
        u = auth.current_user(request)
        return {"app": name, "who": (u or {}).get("name"), "door": doors.of(request), "folder": prefix.of(request),
                "peer": request.client.host if request.client else None, "host": request.headers.get("host"),
                "agent": request.headers.get("user-agent"), "said": request.headers.get("x-visitor-said"),
                "base": doors.base(doors.WEB, request, name), "inside": bool(request.scope.get("iosuite.inside"))}

    @app.post("/api/echo")
    async def echo(request: Request):
        return {"body": json.loads(await request.body() or b"null"), "type": request.headers.get("content-type")}

    @app.get("/api/raw")
    def raw():
        from fastapi.responses import Response
        return Response(b"\x89PNG\r\n" + b"x" * 40, media_type="image/png")

    @app.get("/api/no")
    def no():
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "not for you"}, status_code=403)

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("something in the app")

    @app.get("/api/slow")
    def slow():
        time.sleep(2)
        return {"slow": True}

    @app.get("/api/marked")
    def marked():
        from iosuite_shared.host import CURRENT
        return {"marked": CURRENT.get()}  # what this app's log lines are marked with while it answers

    for path, fn in (routes or {}).items():
        app.get(path)(fn)
    return app


class Copy:
    """A copy of the program running these apps, in an event loop of its own, as a server does."""

    def __init__(self, *apps):
        self.host = Host([Entry(name=a, asgi=an_app(a), state="up") for a in apps], ports={80: "web", 8443: "sync", 8444: "mcp"})
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        asyncio.set_event_loop(self.loop)
        inside.attach(self.loop, self.host)
        self.ready.set()
        self.loop.run_forever()

    def __enter__(self):
        self.thread.start()
        self.ready.wait(5)
        return self

    def __exit__(self, *exc):
        inside.detach()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()


@pytest.fixture(autouse=True)
def alone(monkeypatch):
    """Nothing is attached, and the apps are reached by their own addresses when they are reached at all."""
    inside.detach()
    monkeypatch.setattr(config, "PORT", 80)
    links.ask_again()
    yield
    inside.detach()


def test_nothing_is_asked_inside_without_a_copy_running():
    assert not inside.runs("iocontact") and inside.asgi("iocontact") is None
    with pytest.raises(LookupError):
        inside.ask("iocontact", "/api/what")
    suite.register("iocontact", name="ioContact", url="https://contacts.example.com", version="1")
    assert links.addresses("iocontact") == ["https://contacts.example.com"]  # over the network, as ever


def test_an_app_of_this_copy_is_asked_in_this_process(monkeypatch):
    suite.register("iocontact", name="ioContact", url="https://contacts.example.com", version="1")
    suite.register("iopix", name="ioPix", url="https://photos.example.com", version="1")
    with Copy("iostart", "iocontact"):
        assert inside.runs("iocontact") and not inside.runs("iopix")  # iopix runs in another copy
        assert links.addresses("iocontact") == [links.HERE, "https://contacts.example.com"]
        assert links.addresses("iopix") == ["https://photos.example.com"]
        assert links.addresses("iocontact", here=False) == ["https://contacts.example.com"]
        assert links.available("iocontact") and links.available("iopix")
        r = inside.ask("iocontact", "/api/what", headers={"User-Agent": "ioCalendar", "Accept": "application/json"})
        with r:
            d = json.loads(r.read())
        assert r.status == 200 and r.headers.get("content-type") == "application/json"
        assert d == {"app": "iocontact", "who": None, "door": "web", "folder": "/contacts", "peer": inside.PEER, "host": inside.PEER,
                     "agent": "ioCalendar", "said": None, "base": "http://127.0.0.1/contacts", "inside": True}
        # what it writes into its answer is the address its settings give, as over the network (here: none stored)
        monkeypatch.setattr(config, "OF_APP", {"iocontact": {"PUBLIC_URLS": ["https://contacts.example.com"]}})
        assert json.loads(inside.ask("iocontact", "/api/what").read())["base"] == "https://contacts.example.com"
        # an app that does not run here, or is not up
        with pytest.raises(LookupError):
            inside.ask("iopix", "/api/what")


def test_the_answer_comes_back_as_over_http():
    with Copy("iocontact") as c:
        got = inside.ask("iocontact", "/api/echo", body=b'{"a": 1}', headers={"Content-Type": "application/json"})
        assert json.loads(got.read()) == {"body": {"a": 1}, "type": "application/json"}
        got = inside.ask("iocontact", "/api/raw")
        assert got.read()[:4] == b"\x89PNG" and got.headers.get("Content-Type") == "image/png"
        assert got.geturl() == "inside://iocontact/api/raw" and got.getcode() == 200 and got.info() is got.headers
        # what the app refuses is urllib's HTTPError, with its own body: a caller tells them apart as it does over HTTP
        with pytest.raises(urllib.error.HTTPError) as e:
            inside.ask("iocontact", "/api/no")
        assert e.value.code == 403 and json.loads(e.value.read()) == {"detail": "not for you"} and e.value.headers.get("content-type")
        # an app that fails answers 500, as the web server would, and the caller gets no traceback of the app's
        with pytest.raises(urllib.error.HTTPError) as e:
            inside.ask("iocontact", "/api/boom")
        assert e.value.code == 500 and "RuntimeError" in str(e.value)
        # a path that is nowhere
        with pytest.raises(urllib.error.HTTPError) as e:
            inside.ask("iocontact", "/api/nowhere")
        assert e.value.code == 404
        # one that takes longer than the caller waits, and one that answers more than the caller reads
        with pytest.raises(TimeoutError):
            inside.ask("iocontact", "/api/slow", timeout=0.2)
        with pytest.raises(OSError):
            inside.ask("iocontact", "/api/raw", limit=8)
        assert json.loads(inside.ask("iocontact", "/api/echo", body=b"null").read())["body"] is None
        assert c.host.by_name["iocontact"].state == "up"


def test_only_the_headers_the_caller_named_go_in():
    """Nothing a visitor said about themselves reaches the other app because this machine is trusted."""
    with Copy("iocontact"):
        said = {"User-Agent": "ioStart", "X-Visitor-Said": "hello", "X-Forwarded-For": "203.0.113.9",
                "X-Forwarded-Host": "evil.example.com", "Remote-User": "root", "Host": "elsewhere.example.com", "Connection": "close"}
        d = json.loads(inside.ask("iocontact", "/api/what", headers=said).read())
        assert d["said"] == "hello" and d["agent"] == "ioStart"  # a header the caller means goes along
        assert d["peer"] == inside.PEER and d["host"] == inside.PEER  # the Host is this call's, not the visitor's
        d = json.loads(inside.ask("iocontact", "/api/what", headers=said, host="home.example.com").read())
        assert d["host"] == "home.example.com"  # the caller may say which name it is answering in
        # the door is the pages' by default; at the others no cookie is read, as the host does it
        d = json.loads(inside.ask("iocontact", "/api/what", headers={"Cookie": "iosuite=x"}, door=doors.SYNC).read())
        assert d["door"] == "sync" and d["who"] is None
        d = json.loads(inside.ask("iocontact", "/api/what", headers={"Cookie": "iosuite=x"}).read())
        assert d["door"] == "web"


def test_the_sign_in_is_the_other_app_s_own(monkeypatch):
    """The app in this copy signs the caller in itself: an app password that may read, or the person's own session."""
    from iosuite_shared import apppasswords, sessions
    me = users.create("alex", "secret123", "member", "iocontact")
    with Copy("iocontact"):
        # as the reader's service account, with the app password links makes (the way links.get asks)
        d = links.json("iocalendar", "iocontact", "/api/what")
        assert d["who"] == "iocalendar-app" and d["inside"] is True and d["app"] == "iocontact"
        assert links.addresses("iocontact")[0] == links.HERE
        # the viewer's own session, passed on as it came (the way links.as_viewer asks)
        token = sessions.create(me["id"], "iocontact", "password")

        class AsAlex:  # a request as the other app's middleware reads it
            headers = {"host": "home.example.com", "user-agent": "ioStart"}
            cookies = {sessions.COOKIE: token}
        d = links.as_viewer(AsAlex(), "iocontact", "/api/what", user_agent="ioStart")
        assert d["who"] == "alex" and d["inside"] is True and d["host"] == "home.example.com" and d["agent"] == "ioStart"
        # a password that was revoked is refused here too, and links makes a new one
        pw = links.password("iocalendar", "iocontact")[1]
        svc = users.find("iocalendar-app")
        for row in apppasswords.list_for(svc["id"], "iocontact"):
            apppasswords.delete(svc["id"], row["id"])
        assert links.json("iocalendar", "iocontact", "/api/what")["who"] == "iocalendar-app"
        assert links.password("iocalendar", "iocontact")[1] != pw
        # nobody at all: the app's own middleware decides (its API needs a sign-in)
        with pytest.raises(urllib.error.HTTPError) as e:
            inside.ask("iocontact", "/api/what")
        assert e.value.code in (401, 403)


def test_an_app_in_another_copy_is_asked_over_the_network(monkeypatch):
    """The one thing that must not break: apps on different servers."""
    asked = []

    def over_the_network(req, timeout):
        asked.append((req.full_url, timeout))
        raise urllib.error.URLError("nothing listens in a test")
    monkeypatch.setattr(links, "call", over_the_network)
    suite.register("iopix", name="ioPix", url="https://photos.example.com", version="1", internal_url="http://10.0.0.9")
    with Copy("iostart", "iocontact"):
        with pytest.raises(links.Unreachable):
            links.as_viewer(None, "iopix", "/api/photos")
        assert [u for u, _t in asked] == ["http://10.0.0.9/api/photos", "https://photos.example.com/api/photos"]
        # and the app of this copy is not asked over the network at all
        asked.clear()
        assert links.as_viewer(None, "iocontact", "/api/auth/accounts") is not None and not asked


def test_an_app_that_stops_in_this_copy_is_asked_over_the_network(monkeypatch):
    suite.register("iocontact", name="ioContact", url="https://contacts.example.com", version="1")
    went = []
    monkeypatch.setattr(links, "call", lambda req, timeout: went.append(req.full_url) or (_ for _ in ()).throw(urllib.error.URLError("none")))
    with Copy("iocontact") as c:
        assert links.addresses("iocontact")[0] == links.HERE
        c.host.by_name["iocontact"].state = "starting"
        assert links.addresses("iocontact") == ["https://contacts.example.com"]  # not up: not asked here
        with pytest.raises(links.Unreachable):
            links.as_viewer(None, "iocontact", "/api/what")
        assert went == ["https://contacts.example.com/api/what"]


def test_a_call_from_the_event_loop_itself_goes_over_the_network():
    """A caller already on the copy's loop cannot wait for an answer from that same loop: it asks over the network."""
    with Copy("iocontact") as c:
        async def from_the_loop():
            with pytest.raises(LookupError):
                inside.ask("iocontact", "/api/what")                      # would hold up the loop it needs
            return json.loads((await inside.request("iocontact", "/api/what")).read())   # the way to ask from there
        d = asyncio.run_coroutine_threadsafe(from_the_loop(), c.loop).result(10)
        assert d["app"] == "iocontact" and d["inside"] is True


def test_the_app_s_own_log_lines_are_its_own():
    """A line the other app logs while it answers is marked as its own, as when the host hands it a request, and the
    caller's marker is put back after."""
    from iosuite_shared.host import CURRENT
    with Copy("iocontact"):
        token = CURRENT.set("iocalendar")
        try:
            assert json.loads(inside.ask("iocontact", "/api/marked").read()) == {"marked": "iocontact"}
            assert CURRENT.get() == "iocalendar"
        finally:
            CURRENT.reset(token)

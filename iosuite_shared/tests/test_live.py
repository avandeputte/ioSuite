"""The one live-refresh connection a page holds (iosuite_shared.live): every app's changes on it, a change made by a
request told without the app writing a line of its own, the pages of this copy told in the process, and the lines in
the Shared ioSuite database for the pages of another copy."""
import asyncio
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import db, live
from iosuite_shared.fastapi import Auth


def make_app(app: str = "iotest"):
    auth = Auth(app, app_label="ioTest", version="1.2.3", register=False)
    a = FastAPI()
    a.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    a.include_router(auth.router())
    a.include_router(auth.live_router())
    auth.install(a)

    @a.post("/api/events", dependencies=[auth.access.member_write])
    def add_event():
        return {"ok": True}

    @a.post("/api/auth/nothing", dependencies=[auth.access.public])
    def quiet():
        return {"ok": True}

    @a.post("/api/events/bad", dependencies=[auth.access.public])
    def bad():
        from fastapi import HTTPException
        raise HTTPException(409, "no")

    @a.api_route("/dav/calendars/alex/home/{name}", methods=["PUT", "DELETE", "REPORT", "PROPFIND", "POST"], dependencies=[auth.access.public])
    def synced(name: str):
        return {"ok": True}

    return a


LAN = ("192.168.1.20", 50000)   # a browser on the home network: its session cookie travels over plain HTTP


def signed_in(app, name="alex", password="secret123"):
    c = TestClient(app, base_url="http://test.example.com", client=LAN)
    c.post("/api/auth/setup", json={"name": name, "password": password})
    return c


def test_a_change_made_by_a_request_is_a_line_nobody_had_to_write():
    """Every app is on the stream without code of its own: Auth.install tells the stream about a request that
    changed something and was answered well."""
    c = signed_in(make_app())
    assert c.post("/api/events").status_code == 200
    rows = db.q("SELECT * FROM ios_changes")
    assert [(r["app"], r["what"]) for r in rows] == [("iotest", "events")]
    assert rows[0]["origin"] == live.ORIGIN and rows[0]["at"] > (time.time() - 60) * 1000


def test_signing_in_a_failed_change_and_a_plain_read_say_nothing():
    c = TestClient(make_app(), base_url="http://test.example.com", client=LAN)
    c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
    c.post("/api/auth/nothing")
    c.get("/api/events")
    c.post("/api/events/bad")
    assert db.q("SELECT * FROM ios_changes") == []


def test_what_a_device_that_syncs_changed_is_heard_and_what_it_read_is_not():
    """A calendar or a contact saved on a phone arrives outside the API (CalDAV, CardDAV): the pages hear it too.
    The reads of those protocols are requests with a body as well, and say nothing."""
    c = signed_in(make_app())
    for method in ("PROPFIND", "REPORT", "POST", "GET"):
        assert c.request(method, "/dav/calendars/alex/home/a.ics").status_code in (200, 405)
    assert db.q("SELECT * FROM ios_changes") == []
    assert c.put("/dav/calendars/alex/home/a.ics").status_code == 200
    assert c.delete("/dav/calendars/alex/home/a.ics").status_code == 200
    assert [(r["app"], r["what"]) for r in db.q("SELECT * FROM ios_changes ORDER BY id")] == [("iotest", "sync")] * 2


def test_a_tool_that_changed_something_over_mcp_is_heard():
    """An app's MCP server (iosuite_shared.mcp.make_server): a tool that changes something says so on the stream
    once it has, one that only reads or that failed does not."""
    from mcp.server.mcpserver.exceptions import ToolError

    from iosuite_shared import mcp as shared_mcp
    server = shared_mcp.make_server("iotest", instructions="", app_tools=False)

    @server.tool(annotations=shared_mcp.READ_ONLY)
    def look() -> dict:
        return {"ok": True}

    @server.tool(annotations=shared_mcp.ADDS)
    def add(title: str) -> dict:
        if not title:
            raise ToolError("A title is needed")
        return {"ok": True}

    async def calls():
        await server.call_tool("look", {})
        try:
            await server.call_tool("add", {"title": ""})
        except ToolError:
            pass
        assert db.q("SELECT * FROM ios_changes") == []
        await server.call_tool("add", {"title": "Milk"})
    asyncio.run(calls())
    for _ in range(50):  # the line is written off the loop's thread
        rows = db.q("SELECT * FROM ios_changes")
        if rows:
            break
        time.sleep(0.05)
    assert [(r["app"], r["what"]) for r in rows] == [("iotest", "mcp")]


def test_the_stream_carries_every_app_s_changes_and_needs_a_session():
    app = make_app()
    c = signed_in(app)
    out = TestClient(app, base_url="http://test.example.com", client=LAN)   # the same page, signed out
    with out.stream("GET", "/api/live") as r:   # streamed on purpose: a stream that opened would never end
        assert r.status_code in (401, 403)
    with c.stream("GET", "/api/live") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        lines = r.iter_lines()
        assert next(lines).startswith("retry:")
        live.changed("iocalendar", "events")          # another app of the suite, in this copy
        got = _event(lines)
        assert (got["app"], got["what"]) == ("iocalendar", "events") and got["at"] > 0
        live.changed("ionote", "notes", body={"id": 7})
        assert _event(lines)["body"] == {"id": 7}


def test_a_line_for_one_person_goes_only_to_that_person_s_pages():
    app = make_app()
    c = signed_in(app)
    mine = c.get("/api/auth/me").json()["user"]["id"]
    with c.stream("GET", "/api/live") as r:
        lines = r.iter_lines()
        next(lines)
        live.changed("ionote", "notes", user_id=mine + 1)   # somebody else's
        live.changed("ionote", "notes", user_id=mine)       # this person's
        got = _event(lines)
        assert got["what"] == "notes"
        # the first line was never handed out: only one event arrives, and it is the second
        assert len(live.reader.listeners) == 1


def test_the_copy_s_own_pages_hear_a_change_at_once_and_the_table_is_for_the_others():
    """A change is handed to this copy's streams in the process (no waiting on the database), and written down for
    the copies on other servers to read."""
    async def go():
        q = live.reader.join(0)
        live.changed("iopix", "photos")
        got = await asyncio.wait_for(q.get(), timeout=1)
        assert (got["app"], got["what"], got["id"]) == ("iopix", "photos", 0)
        live.reader.leave(q)
        await asyncio.sleep(0.2)   # the row is written off the loop's thread
    asyncio.run(go())
    assert [r["app"] for r in db.q("SELECT app FROM ios_changes")] == ["iopix"]


def test_a_copy_reads_the_lines_of_other_copies_only():
    """The reader skips what this process wrote (its pages already have it) and picks up the rest."""
    async def go():
        db.ex("INSERT INTO ios_changes (at, app, what, user_id, body, origin) VALUES (%s, %s, %s, %s, %s, %s)",
              (int(time.time() * 1000), "iotask", "tasks", None, None, "another-copy-1234"))
        db.ex("INSERT INTO ios_changes (at, app, what, user_id, body, origin) VALUES (%s, %s, %s, %s, %s, %s)",
              (int(time.time() * 1000), "iotask", "lists", None, None, live.ORIGIN))
        live.reader._last = 0  # as a stream that has just opened would start
        got = await asyncio.to_thread(live.reader._new)
        assert [r["what"] for r in got] == ["tasks"]
    asyncio.run(go())


def test_lines_a_page_no_longer_needs_are_forgotten():
    db.ex("INSERT INTO ios_changes (at, app, what, origin) VALUES (%s, %s, %s, %s)",
          (int((time.time() - 3600) * 1000), "iotask", "old", "x"))
    db.ex("INSERT INTO ios_changes (at, app, what, origin) VALUES (%s, %s, %s, %s)",
          (int(time.time() * 1000), "iotask", "new", "x"))
    assert live.forget_old() == 1
    assert [r["what"] for r in db.q("SELECT what FROM ios_changes")] == ["new"]


def test_the_page_s_side_of_it_is_served_and_parses():
    import shutil
    import subprocess
    app = make_app()
    signed_in(app)   # an account exists, so nothing but the open paths answers a visitor
    r = TestClient(app, base_url="http://test.example.com", client=LAN).get("/api/live.js")   # signed out: the script is no secret
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert "export function onChange" in r.text
    node = shutil.which("node")
    if node:
        out = subprocess.run([node, "--input-type=module", "--check"], input=r.text, capture_output=True, text=True)
        assert out.returncode == 0, out.stderr


def _event(lines) -> dict:
    """The next change on the stream, past the heartbeats."""
    for _ in range(40):
        line = next(lines)
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError("no change arrived on the stream")

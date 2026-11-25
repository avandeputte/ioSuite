"""The suite's one MCP server: the start page's /mcp offers every other app's tools, passed on to that app's own /mcp
as the same person with the same ioStart app password, so each app still decides what that person may do there.

A small app of the suite (ioTask's key, its own Auth, the shared MCP pieces) runs on a real port beside the start page.
"""
import socket
import threading
import time

import pytest
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from iosuite_shared import apppasswords, mcp as shared_mcp, suite, users
from iosuite_shared.fastapi import Auth

from test_mcp import H, call, rpc

STATE = {"on": True, "added": []}


def _fake_app():
    auth = Auth("iotask", app_label="ioTask", register=False)
    server = shared_mcp.make_server("iotask", app_tools=False, instructions="ioTask: tasks. add_task adds one.")

    @server.tool(annotations=shared_mcp.READ_ONLY)
    def whoami() -> dict:
        """Who is asking, and their role here."""
        u = shared_mcp.who()
        return {"name": u["name"], "role": u["role"]}

    @server.tool(annotations=shared_mcp.ADDS)
    def add_task(title: str) -> dict:
        """Add a task."""
        u = shared_mcp.need_member()
        STATE["added"].append((u["name"], title))
        return {"added": title}

    @asynccontextmanager
    async def lifespan(app):
        async with shared_mcp.running(server):
            yield

    app = FastAPI(lifespan=lifespan)
    app.middleware("http")(auth.middleware(open_prefixes=("/mcp",), before=auth.mcp_gate(lambda: STATE["on"], on_user=shared_mcp.current_user.set)))

    @app.get("/api/whoami")
    def whoami_route(request: Request):
        u = auth.current_user(request)
        return {"name": u["name"] if u else None}

    shared_mcp.mount(app, server)
    return app


@pytest.fixture(scope="module")
def task_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(_fake_app(), host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield port
    srv.should_exit = True
    t.join(5)


@pytest.fixture()
def suite_mcp(client, task_port):
    from iostart import mcp
    from iostart.apps import ORDER
    for key in ORDER:
        if key not in ("iostart", "iotask", "iocalendar"):
            suite.forget(key)
    suite.register("iotask", "ioTask", url="https://task.example.com", internal_url=f"http://127.0.0.1:{task_port}")
    suite.register("iocalendar", "ioCalendar", url=None, internal_url="http://127.0.0.1:1")  # nothing listens there
    shared_mcp.set_for("iostart", True)
    STATE.update(on=True, added=[])
    mcp.forget()
    secret = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {secret}"}


def names(auth, client):
    return {t["name"] for t in rpc(client, "tools/list", auth=auth)[1]["result"]["tools"]}


def test_other_apps_tools_are_listed_and_passed_on(client, suite_mcp):
    auth = suite_mcp
    got = names(auth, client)
    assert {"suite_version", "update_suite", "suite_apps", "iotask_whoami", "iotask_add_task"} <= got
    assert not any(n.startswith("iocalendar_") for n in got)  # it does not answer
    assert call(client, auth, "iotask_whoami") == {"name": "alex", "role": "admin"}
    assert call(client, auth, "iotask_add_task", title="Buy flour") == {"added": "Buy flour"}
    assert STATE["added"] == [("alex", "Buy flour")]
    apps = {a["app"]: a for a in call(client, auth, "suite_apps")["apps"]}
    assert apps["iotask"]["status"] == "ok" and apps["iotask"]["tools"] == 2 and "add_task" in apps["iotask"]["instructions"]
    assert apps["iocalendar"]["status"] == "unreachable"
    assert "error" in call(client, auth, "iotask_nonsense")
    assert "error" in call(client, auth, "nosuchapp_whoami")


def test_each_app_keeps_its_own_permissions(client, suite_mcp):
    from iostart import mcp
    # a viewer in ioTask sees its tools, but ioTask refuses the change
    vi = users.create("vi", "secret123", "member", "iostart")
    users.set_role(vi["id"], "iotask", "viewer")
    auth = {"Authorization": f"Bearer {apppasswords.create(vi['id'], 'iostart', 'claude')}"}
    assert call(client, auth, "iotask_whoami") == {"name": "vi", "role": "viewer"}
    assert "error" in call(client, auth, "iotask_add_task", title="x") and STATE["added"] == []
    # somebody with no role in ioTask gets none of its tools, and cannot call them
    no = users.create("no", "secret123", "member", "iostart")
    users.set_role(no["id"], "iotask", "none")
    auth = {"Authorization": f"Bearer {apppasswords.create(no['id'], 'iostart', 'claude')}"}
    mcp.forget()
    assert not any(n.startswith("iotask_") for n in names(auth, client))
    assert "error" in call(client, auth, "iotask_whoami")


def test_switched_off_app_offers_nothing(client, suite_mcp):
    STATE["on"] = False
    apps = {a["app"]: a for a in call(client, suite_mcp, "suite_apps")["apps"]}
    assert apps["iotask"]["status"] == "off" and apps["iotask"]["tools"] == 0
    assert not any(n.startswith("iotask_") for n in names(suite_mcp, client))


def test_hub_password_rules(client, suite_mcp, task_port):
    """Only an ioStart app password without a limit reaches another app (its /mcp, its API: the start page passes it
    on for the wall display); never that app's sync protocols."""
    import httpx
    alex = users.find("alex")
    full = apppasswords.create(alex["id"], "iostart", "x")
    dav = apppasswords.create(alex["id"], "iostart", "phone", apppasswords.DAV)
    base = f"http://127.0.0.1:{task_port}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    assert httpx.post(base + "/mcp", headers={**H, "Authorization": f"Bearer {full}"}, json=body).status_code == 200
    assert httpx.post(base + "/mcp", headers={**H, "Authorization": f"Bearer {dav}"}, json=body).status_code == 401
    assert httpx.post(base + "/mcp", headers={**H, "Authorization": "Bearer iostart-00000000-nope"}, json=body).status_code == 401
    assert apppasswords.authenticate_hub(None, full, "iostart") is None  # the start page checks its own the usual way
    # its API takes it too, as the same person; a scoped one stays the start page's alone; the sync protocols never
    r = httpx.get(base + "/api/whoami", headers={"Authorization": f"Bearer {full}"})
    assert r.status_code == 200 and r.json()["name"] == "alex", r.text
    assert httpx.get(base + "/api/whoami", headers={"Authorization": f"Bearer {dav}"}).status_code == 401
    assert httpx.request("PROPFIND", base + "/dav/", headers={"Authorization": f"Bearer {full}"}).status_code == 401


def test_an_app_of_this_copy_is_asked_in_the_process(client, suite_mcp):
    """One MCP server for a copy: an app this copy runs is called in the process, as the same person with their role
    in that app. Its address here points at a port nothing listens on, so an answer proves nothing went over HTTP."""
    import asyncio
    import threading

    from iosuite_shared import inside
    from iosuite_shared.host import Entry, Host

    from iostart import mcp
    suite.register("iotask", "ioTask", url=None, internal_url="http://127.0.0.1:1")
    shared_mcp.set_for("iotask", True)      # a real app's switch is the setting, not a flag of its own
    app = _fake_app()                       # mounting its MCP server is what makes it callable in the process
    loop, ready = asyncio.new_event_loop(), threading.Event()

    def run():
        asyncio.set_event_loop(loop)
        inside.attach(loop, Host([Entry(name="iotask", asgi=app, state="up")], ports={80: "web", 8444: "mcp"}))
        ready.set()
        loop.run_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    ready.wait(5)
    try:
        mcp.forget()
        assert shared_mcp.here("iotask") is not None and shared_mcp.here("iopix") is None
        assert {"iotask_whoami", "iotask_add_task"} <= names(suite_mcp, client)
        assert call(client, suite_mcp, "iotask_whoami") == {"name": "alex", "role": "admin"}
        assert call(client, suite_mcp, "iotask_add_task", title="Inside") == {"added": "Inside"}
        assert STATE["added"] == [("alex", "Inside")]
        apps = {a["app"]: a for a in call(client, suite_mcp, "suite_apps")["apps"]}
        assert apps["iotask"]["status"] == "ok" and apps["iotask"]["tools"] == 2
        # a viewer there is still only a viewer, and the app's switch still decides
        vi = users.create("ava", "secret123", "member", "iostart")
        users.set_role(vi["id"], "iotask", "viewer")
        mine = {"Authorization": f"Bearer {apppasswords.create(vi['id'], 'iostart', 'claude')}"}
        mcp.forget()
        assert call(client, mine, "iotask_whoami") == {"name": "ava", "role": "viewer"}
        assert "error" in call(client, mine, "iotask_add_task", title="no") and len(STATE["added"]) == 1
        shared_mcp.set_for("iotask", False)
        mcp.forget()
        assert not any(n.startswith("iotask_") for n in names(suite_mcp, client))
        assert "error" in call(client, suite_mcp, "iotask_whoami")
    finally:
        shared_mcp.set_for("iotask", None)
        inside.detach()
        loop.call_soon_threadsafe(loop.stop)
        t.join(5)
        loop.close()
        mcp.forget()

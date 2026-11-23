"""What every app's MCP server shares: the server instance, the annotations, who is asking, and the HTTP mount.

    from iosuite_shared import mcp as shared_mcp
    server = shared_mcp.make_server("iocalendar", "ioCalendar", __version__, instructions="...")
    current_user = shared_mcp.current_user                      # set per request by Auth.mcp_gate(on_user=current_user.set)
    @server.tool(annotations=shared_mcp.READ_ONLY)
    def overview(): u = shared_mcp.who(); ...
    shared_mcp.mount(app, server)                                # /mcp (streamable HTTP) ahead of the app's routes
    async with shared_mcp.running(server): yield                 # in the app's lifespan

MCP clients sign in like any other client of the suite: HTTP Basic with the user name and an app password, or a bearer
app password (Settings › Account); every tool acts as that account. An ioStart app password (without a limit) signs in
at every app's /mcp too: the start page's /mcp is the suite's one MCP server and passes calls on with it
(apppasswords.HUB, iostart/app/mcp.py). The switch is a setting of the app
(`enabled_for(app)`): off until a suite admin turns it on under Settings › Apps.
"""
import contextvars
import time
from contextlib import asynccontextmanager

import anyio

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from iosuite_shared import suiteupdates, users

PATH = "/mcp"
SETTING = "mcp_enabled"

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# a tool that changes something but can be repeated with the same outcome (an edit, a setting)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ADDS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DELETES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
UPDATES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)  # reaches GitHub

current_user: contextvars.ContextVar = contextvars.ContextVar("iosuite_mcp_user", default=None)  # set per request


class AppServer(MCPServer):
    """An app's MCP server. A tool that changed something says so on the pages' live stream (iosuite_shared.live), as
    a request to the app's API does: what an assistant added or changed shows on the open pages without a reload."""

    async def call_tool(self, name, arguments, context=None):
        result = await super().call_tool(name, arguments, context)
        tool = self._tool_manager.get_tool(name)
        notes = getattr(tool, "annotations", None)
        reads = getattr(notes, "read_only_hint", None) or getattr(notes, "readOnlyHint", None)  # as the library's version names it
        if tool is not None and not reads and not getattr(result, "is_error", False) and not getattr(result, "isError", False):
            from iosuite_shared import live
            live.changed(self.name, "mcp")
        return result


def make_server(app: str, label: str, version: str, instructions: str) -> MCPServer:
    return AppServer(app, title=label, version=version, instructions=instructions)


def who() -> dict:
    """The account the request acts as, or a ToolError that says how to sign in."""
    u = current_user.get()
    if not u:
        raise ToolError("Not signed in: connect with your user name and an app password (Settings › Account)")
    return u


def need_admin() -> dict:
    u = who()
    if not users.is_admin(u):
        raise ToolError("Only an admin can do this")
    return u


def need_suite_admin() -> dict:
    u = who()
    if not users.is_suite_admin(u):
        raise ToolError("Only a suite admin can do this")
    return u


def need_member() -> dict:
    """A member or more: may change their own private things."""
    u = who()
    if not users.is_member(u):
        raise ToolError("A viewer can only look; a member, editor or admin can change their own")
    return u


def add_suite_update_tools(server: MCPServer) -> None:
    """The start page's tools for updating the suite (iosuite_shared.suiteupdates), suite admins only: suite_version
    and update_suite."""

    @server.tool(annotations=UPDATES)
    async def suite_version(check: bool = True) -> dict:
        """Suite admins: the suite's version (one number for every app), the newest version on GitHub, and status:
        current, update (apps are behind: their keys in `behind`), updating, or error (GitHub could not be asked).
        copies has one line per server of the suite (one copy of the program, with the apps it runs): its version,
        whether it runs (watching), whether it can update itself, and how its last update went (state: running, ok or
        failed, with a message); apps has the same per app. check True (the default) first has every app ask GitHub
        again, which takes up to half a minute; False answers from the last check."""
        u = need_suite_admin()

        def work():
            if check:
                since = time.time()
                suiteupdates.request("check", by=u["name"])
                suiteupdates.wait_checked(since)
            return suiteupdates.summary()
        return await anyio.to_thread.run_sync(work)

    @server.tool(annotations=UPDATES)
    async def update_suite() -> dict:
        """Suite admins: update the suite to the newest version on GitHub: every server that is behind (run
        suite_version first) runs update.sh within ten seconds and starts again (settings and data stay; the
        databases are brought up to date as it starts). Call suite_version(check=False) a minute or two later: status
        current, or what is still behind and why (state failed, with a message). A copy in Docker cannot update
        itself (pull the image there)."""
        u = need_suite_admin()
        asked = await anyio.to_thread.run_sync(lambda: suiteupdates.request("update", by=u["name"]))
        if not asked:
            return {"asked": [], "note": "Every server is on the newest version known (suite_version checks GitHub again)."}
        return {"asked": asked, "note": "Each server runs update.sh within ten seconds and starts again; call suite_version(check=False) in a minute or two."}


def stdio_user(app: str, named: str, accounts: list, argv: list = None, open_install=None) -> dict:
    """The account a local MCP server acts as (`python -m <app>.mcp [--user NAME]`, over stdio): the one --user names,
    else `named` (MCP_USER), else the only admin when there is just one. `accounts` are the app's, each with its role
    there. The process ends with a line saying why when there is no such account, it has no access to the app, or
    nobody is named and the admin cannot be told. `open_install`: who it is while the suite has no account at all.

    The account and its role are read as the server starts: a role changed later counts from the next start (anyone
    who can start the process holds the database password)."""
    import sys

    from iosuite_shared import catalog
    argv = sys.argv[1:] if argv is None else argv
    if "--user" in argv:
        i = argv.index("--user")
        named = argv[i + 1] if i + 1 < len(argv) else ""
    label = catalog.name_of(app)
    if named:
        u = next((u for u in accounts if named.lower() in (u["name"].lower(), (u.get("email") or "").lower())), None)
        if not u:
            sys.exit(f"no {label} account named {named!r}")
        if u.get("role") == "none":
            sys.exit(f"the account {named!r} has no access to {label}")
        return u
    admins = [u for u in accounts if u.get("role") == "admin" or u.get("suiteAdmin")]
    if len(admins) == 1:
        return admins[0]
    if not accounts and open_install is not None:
        return open_install
    sys.exit(f"name the account: python -m {app}.mcp --user NAME (or MCP_USER=NAME)")


def diagnostics(config, version: str, updater, db, mcp_enabled, accounts: list, counts=None, **more) -> dict:
    """What an app's `diagnostics` tool says of its server, the same in every app: version and commit, Python and
    platform, where the app is, `more` (the app's own lines), the last update check and update, the database (its
    server's version, the schema's, and `counts()`: the app's rows; or the error when it cannot be asked), the MCP
    switch and the accounts with their roles in the app."""
    import platform
    import sys
    out = {"version": version, "commit": updater.local_commit()[:7], "docker": updater.in_docker(),
           "python": sys.version.split()[0], "platform": platform.platform(), "appDir": str(config.APP_DIR),
           "publicUrl": config.PUBLIC_URL or None, **more, "update": updater.status()}
    try:
        out["database"] = {"host": f"{config.DB_HOST}:{config.DB_PORT}", "name": config.DB_NAME,
                           "server": db.one("SELECT version() AS v")["v"], "schema": db.schema_version(),
                           **(counts() if counts else {})}
    except Exception as e:  # noqa: BLE001
        out["database"] = {"error": str(e)[:200]}
    out["mcp"] = {"enabled": mcp_enabled()}
    out["accounts"] = [{"name": u["name"], "role": u.get("role")} for u in accounts]
    return out


def account_list(accounts: list) -> list:
    """What an app's `list_accounts` tool answers: the accounts with their roles in the app."""
    return [{"name": u["name"], "displayName": u.get("displayName"), "email": u.get("email") or None, "role": u.get("role")}
            for u in accounts]


def clamp(n, lo: int, hi: int) -> int:
    """A number a client asked for, kept between lo and hi (a page size: each tool's cap keeps its answer readable)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = lo
    return max(lo, min(n, hi))


def enabled_for(app: str) -> bool:
    """Whether this app's MCP server is on: its own `mcp_enabled` row in the Shared ioSuite database, else the
    suite-wide one (db.get_setting falls back to it), else off. Off too while the settings cannot be read."""
    from iosuite_shared import db
    try:
        return db.get_setting(SETTING, "0", app) == "1"
    except Exception:  # noqa: BLE001  the database is away
        return False


def set_for(app: str, on) -> None:
    """Turn this app's MCP server on or off (app "": the switch every app follows unless it says otherwise).
    `on` None: the app's own row is removed, so it follows the suite's switch again."""
    from iosuite_shared import db
    db.set_setting(SETTING, None if on is None else ("1" if on else "0"), app)


def switches() -> dict:
    """{app: on} as stored: the suite's switch under "" and a row for every app that says otherwise (Settings ›
    Apps). An app with no row of its own follows the suite's."""
    from iosuite_shared import db
    out = {}
    for r in db.q("SELECT app, value FROM ios_settings WHERE name = %s", (SETTING,)):
        out[r["app"]] = r["value"] == "1"
    return out


class Switch:
    """One app's MCP server: `enabled` is the switch (the gate's test), `about` says what an assistant may do there.
    It is a setting of the Shared ioSuite database, so Settings › Apps shows every app's in one place."""

    def __init__(self, app: str, about: str):
        self.app, self.about = app, about

    def enabled(self) -> bool:
        return enabled_for(self.app)

    def info(self) -> dict:
        return {"mcpEnabled": self.enabled(), "mcpAbout": self.about}


_HERE: dict = {}    # app -> its MCP server in this process, as mount() served it


def here(app: str):
    """That app's own MCP server when this very copy runs it and it is up; None otherwise. The suite's MCP server (the
    start page) then calls the app in the process instead of over the network — one MCP server for a copy — and an app
    on another server is still called over HTTP, as it must be."""
    from iosuite_shared import inside
    s = _HERE.get(app)
    return s if s is not None and inside.runs(app) else None


@asynccontextmanager
async def as_person(app: str, user: dict):
    """A call handed to another app of this copy: it acts as the same person, with the role that person holds in that
    app (not the one they hold where the call came in), and what it logs is its own. The sign-in itself was already
    checked where the call came in: whatever signs in at the start page's MCP server signs in at every app's
    (apppasswords.HUB), which is what the request over HTTP relied on too."""
    from iosuite_shared import host
    u = await anyio.to_thread.run_sync(lambda: dict(user, role=users.role_of(user, app)))
    mine, theirs = current_user.set(u), host.CURRENT.set(app)
    try:
        yield u
    finally:
        current_user.reset(mine)
        host.CURRENT.reset(theirs)


def mount(app, server: MCPServer, path: str = PATH) -> None:
    """Serve the MCP server over streamable HTTP at `path` on the app's own port, ahead of every other route. The MCP
    library's own DNS rebinding protection is off: it takes a fixed list of hosts, and the apps are reached by LAN
    name, IP or a public name. Auth.mcp_gate does the check instead, with the names the app is known by, and every
    request is signed in anyway."""
    asgi = server.streamable_http_app(streamable_http_path=path, stateless_http=True,
                                      transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    app.router.routes[:0] = list(asgi.routes)
    _HERE[server.name] = server   # and in this process, for the suite's MCP server (here())


@asynccontextmanager
async def running(server: MCPServer):
    """The server's session manager, for the app's lifespan. It may be started again in the same process (a test
    suite that starts the app once per test)."""
    sm = server.session_manager
    sm._has_started = False
    async with sm.run():
        yield

"""`iosuite <app> <command>` and `iosuite mcp <app>`: an app from a shell.

Every app had a cli.py of its own that said the same two commands in the same words (`migrate`, `check`) and a
mcp/__main__.py that started its MCP server over stdio in the same seven lines. Both are here now, once:

    iosuite iocalendar check                      what the app has in its tables
    iosuite iocalendar migrate                    its tables (and the suite's accounts), made or brought up to date
    iosuite iocalendar import 3 holidays.ics      a command of its own (iocalendar/commands.py)
    iosuite mcp iocalendar --user alex            its MCP server over stdio, as that account

`migrate` is what the app does before anything else (iosuite_shared.app.App.prepare: its tables and the suite's
accounts). `check` says what is in them: the app's `counts` (<app>/db.py), the same numbers its diagnostics tool
gives an assistant. An app with commands of its own declares them in <app>/commands.py:

    def add(sub):                                 # argparse subparsers; `run` is called with the parsed arguments
        p = sub.add_parser("import", help="events from an .ics file into a calendar")
        p.add_argument("calendar", type=int); p.add_argument("file")
        p.set_defaults(run=lambda a: print(model.import_text(a.calendar, Path(a.file).read_text())))

and an app whose MCP tools need to know whose they are declares `set_user(account)` in its mcp package, which the
web app's gate uses too (iosuite_shared.application.create: on_mcp_user).
"""
import argparse
import sys

from iosuite_shared import app as declared, catalog


def _parser(key: str) -> argparse.ArgumentParser:
    a = declared.of(key)
    p = argparse.ArgumentParser(prog=f"iosuite {key}", description=f"{catalog.name_of(key)} from a shell")
    sub = p.add_subparsers(dest="appcmd", required=True)
    sub.add_parser("migrate", help="make its tables, or bring them up to date (the suite's accounts too)")
    sub.add_parser("check", help="reach the databases and say what is there")
    if a.has("commands"):
        a.module("commands").add(sub)
    return p


def run(key: str, argv: list) -> int:
    """`iosuite <app> ...`: the app's own commands, with migrate and check for every app."""
    a = declared.of(key)
    args = _parser(key).parse_args(argv)
    for fn in a.prepare:    # its tables and the suite's accounts: every command needs them
        fn()
    if args.appcmd == "migrate":
        print("ok: tables ready")
        return 0
    if args.appcmd == "check":
        return _check(a)
    got = args.run(args)
    return int(got) if isinstance(got, int) else 0


def _check(a) -> int:
    """What the app has: the accounts it serves and its own rows (<app>/db.py: counts)."""
    users = a.module("users") if a.has("users") else a.users
    n = len(users.all_users() if hasattr(users, "all_users") else users.list_users())
    rows = {k: v for k, v in (a.counts() if a.counts else {}).items() if v is not None}
    note = rows.pop("warning", None)
    print("ok: " + ", ".join([f"{n} account(s)"] + [f"{v} {name}" for name, v in rows.items()]))
    if note:
        print("note: " + str(note))
    return 0


def stdio(argv: list) -> int:
    """`iosuite mcp <app> [--user NAME]`: the app's MCP server over stdio, for a client that starts a local process.
    It acts as the account --user or MCP_USER names (or the only admin, when there is just one:
    iosuite_shared.mcp.stdio_user), as the app's /mcp does for a client signed in with an app password."""
    from iosuite_shared import mcp as shared_mcp
    p = argparse.ArgumentParser(prog="iosuite mcp", description="an app's MCP server over stdio")
    p.add_argument("app", choices=sorted(k for k in catalog.APPS if (catalog.APPS[k].get("mcp") or "")), help="which app's tools")
    p.add_argument("--user", default=None, help="the account every call acts as (else MCP_USER, else the only admin)")
    args = p.parse_args(argv)
    a = declared.of(args.app)
    for fn in a.prepare:
        fn()
    mcp = a.module("mcp")
    users = a.module("users") if a.has("users") else a.users
    accounts = users.all_users() if hasattr(users, "all_users") else users.list_users()
    # ioPix is usable before the first account exists (the open install), as its web app is
    me = shared_mcp.stdio_user(args.app, args.user or a.config.MCP_USER, accounts,
                               open_install={"id": 0, "name": "owner", "role": "admin"} if args.app == "iopix" else None)
    (getattr(mcp, "set_user", None) or mcp.current_user.set)(me)
    mcp.server.run()
    return 0


def main(argv: list = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    return run(argv[0], argv[1:])

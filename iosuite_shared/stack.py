"""`iosuite stack`: what a container of the suite does before it serves, in one command at every start, ahead of the
program itself: `iosuite stack … -- iosuite serve` (the image's default command, and what the compose file builder
writes). A stack is usually one container for the suite (and one for ioPix when it runs apart); with several, the
others wait until the first is healthy. No container of its own, so none is left stopped when the work is done:

  1. with `--db-admin USER` (its password in DB_ADMIN_PASSWORD): the Shared ioSuite database, the suite's one login
     (IOSUITE_DB_*) and a database for every app of this container, made when missing (iosuite_shared.provision:
     nothing is dropped, an existing login's password is never changed). The login is made for `--client-host`
     ('%' by default: a container's address is not one the server can be told ahead of time).
  2. the tables of the Shared ioSuite database, and the first admin (ADMIN_USER / ADMIN_PASSWORD) when it holds no
     account yet.
  3. what the stack file says about the suite, which lives in the Shared ioSuite database and not in the
     environment: `--set APP.NAME=VALUE` (a setting: suite.PUBLIC_URL=https://home.example.com,
     iopix.PHOTOS_DIR=/photos; iosuite_shared.config) and `--proxies LIST` (the addresses the reverse proxies connect
     from). Each is written when it differs from what this command wrote the last time, so a later `up` of the same
     file leaves alone what a suite admin has changed under Settings since; a stack file that says something new is
     applied. A setting this container's file said before and no longer says goes back to its default, unless a
     suite admin has changed it since. Containers are told apart by their INTERNAL_URL, so one that says nothing
     (ioPix's, when it runs apart) leaves what the other said.
  4. with `--demo`: the demo switch (iosuite_shared.demo): every app adds its share of the demo data (the made-up
     Calloway family) at its first start. Only on a suite with no accounts but the admin's yet, so a later `up` of a
     stack that has been used for real never adds it.

The database is waited for (a container that was only just started), a minute at most.

What follows `--` is the program: this process becomes it once the work is done (exec, so it gets the container's
signals), without the two passwords only this command needs (DB_ADMIN_PASSWORD, ADMIN_PASSWORD) in its environment.
"""
import json
import os
import sys
import time

DECLARED = "stack_declared"  # ios_settings, app '': what this command last wrote, as JSON {"proxies": "a,b", "set": {"suite.PUBLIC_URL": "…"},
#                              "by": {"suite.PUBLIC_URL": "http://iosuite"}} (by: the container that said it, its INTERNAL_URL)
WAIT_S = 60
ONLY_HERE = ("DB_ADMIN_PASSWORD", "ADMIN_PASSWORD")  # not handed on to the program that is started after `--`


def add_parser(sub):
    p = sub.add_parser("stack", help="set a container up before it serves: the databases, the first admin, what the stack file says about the suite")
    p.add_argument("--db-admin", default=None, help="a MariaDB administrator (its password in DB_ADMIN_PASSWORD): creates the databases and the login")
    p.add_argument("--client-host", default="%", help="with --db-admin: the host the login is made for (default %%: any)")
    p.add_argument("--set", action="append", default=[], metavar="APP.NAME=VALUE", help="a setting to store (suite.PUBLIC_URL=…, iopix.PHOTOS_DIR=…); repeatable")
    p.add_argument("--demo", action="store_true", help="fill a new suite with demo data: a made-up family of four, something in every app")
    p.add_argument("--proxies", default=None, help="the addresses or networks the reverse proxies connect from, commas between them ('' for none)")
    p.add_argument("then", nargs="...", metavar="-- COMMAND", help="after --: the program to become once the work is done (iosuite serve)")
    return p


def then_command(a) -> list:
    """What follows `--` on the command line, without the `--`."""
    cmd = list(getattr(a, "then", None) or [])
    return cmd[1:] if cmd[:1] == ["--"] else cmd


def _names(spec) -> list:
    return [n.strip() for n in (spec or "").split(",") if n.strip()]


DENIED = ("(1045",)  # MariaDB: Access denied for user (a wrong password)
REFUSED_HINT = ("the database server refuses this password. With the stack's own MariaDB this nearly always means its "
                "data was made by an earlier stack file, with another root password (MariaDB keeps the one it first "
                "started with): start over with an empty database folder (stop the stack, empty db/ in the stack's "
                "data folder; on Docker volumes, `docker compose down -v`), which deletes the stack's data, or put the "
                "earlier passwords back in this file (the compose builder's Open a file shows them)")


def _wait(what, attempt, log, wait_s=WAIT_S, sleep=time.sleep):
    """Run attempt() until it stops raising SystemExit / an exception that says the server is not there yet. A refused
    password is not waited for: it does not change while the server starts."""
    until = time.time() + wait_s
    while True:
        try:
            return attempt()
        except SystemExit as exc:
            msg = str(exc)
            if any(d in msg for d in DENIED):
                raise SystemExit(f"{msg[:300]}\n  {REFUSED_HINT}") from None
            if "could not connect" not in msg or time.time() >= until:
                raise
        except Exception as exc:  # noqa: BLE001 - whatever the driver says while the server starts
            msg = str(exc)
            if any(d in msg for d in DENIED):
                raise SystemExit(f"error: {what}: {msg[:300]}\n  {REFUSED_HINT}") from None
            if time.time() >= until:
                raise SystemExit(f"error: {what}: {msg[:300]}")
        log(f"  waiting for the database ({msg[:120]})")
        sleep(3)


def provision_here(admin, client, log=print, run=None, wait_s=WAIT_S, sleep=time.sleep):
    """Step 1: the databases of this container's apps and the suite's login. `run` is provision.run (the tests pass their own)."""
    from iosuite_shared import host, provision
    t = provision.target()
    if not t["password"]:
        raise SystemExit("error: IOSUITE_DB_PASSWORD is not in the environment: the suite's login needs a password")
    names = provision.databases(host.names())
    password = os.environ.get("DB_ADMIN_PASSWORD") or ""
    run = run or provision.run
    return _wait("the databases", lambda: run(admin, password, names, t, client=client or "%", log=log), log, wait_s, sleep)


def parse_set(items) -> dict:
    """{"suite.PUBLIC_URL": value, "iopix.PHOTOS_DIR": value} from the --set arguments; SystemExit on one that is not APP.NAME=VALUE."""
    out = {}
    for it in items or []:
        key, eq, value = str(it).partition("=")
        app, dot, name = key.partition(".")
        if not eq or not dot or not app.strip() or not name.strip():
            raise SystemExit(f"error: --set {it}: APP.NAME=VALUE (suite.PUBLIC_URL=https://home.example.com)")
        out[f"{app.strip().lower()}.{name.strip()}"] = value.strip()
    return out


def _suite(app) -> str:
    from iosuite_shared import admin
    return admin.SUITE if app in ("suite", "_suite") else app


def declare(settings=None, proxies=None, log=print, who=None) -> dict:
    """Step 3. Returns what was written: {"proxies": …, "set": {key: value}, "unset": [key]} with only what changed.
    `who` is this container (its INTERNAL_URL)."""
    from iosuite_shared import admin, db, proxyauth
    who = os.environ.get("INTERNAL_URL", "") if who is None else who
    settings = settings or {}
    try:
        last = json.loads(db.get_setting(DECLARED, "", "") or "{}")
    except ValueError:
        last = {}
    now = {"proxies": last.get("proxies"), "set": dict(last.get("set") or {}), "by": dict(last.get("by") or {})}
    wrote, changed = {}, False
    for key, value in settings.items():
        if now["by"].get(key) != who:
            now["by"][key] = who
            changed = True
        if (last.get("set") or {}).get(key) == value:
            continue
        app, name = key.split(".", 1)
        try:
            admin.set_setting(_suite(app), name, value)
        except (LookupError, ValueError) as e:
            raise SystemExit(f"error: --set {key}: {str(e).strip(chr(39))}")
        now["set"][key] = value
        wrote.setdefault("set", {})[key] = value
        log(f"  {key} = {value or '(the default)'}")
    for key in [k for k, by in (last.get("by") or {}).items() if by == who and k not in settings]:
        was = now["set"].pop(key, None)  # what this container's file said before and no longer says
        now["by"].pop(key, None)
        changed = True
        app, name = key.split(".", 1)
        if not was or db.settings_of("" if _suite(app) == admin.SUITE else app).get(name) != was:
            continue  # a suite admin has changed it since: theirs now
        try:
            admin.set_setting(_suite(app), name, "")
        except (LookupError, ValueError):
            continue  # a setting this version no longer has
        wrote.setdefault("unset", []).append(key)
        log(f"  {key} = (the default: the stack file no longer says)")
    if proxies is not None:
        now["proxies"] = ",".join(_names(proxies))
        if last.get("proxies") != now["proxies"]:
            proxyauth.save_suite({"AUTH_PROXY_TRUSTED": ", ".join(_names(proxies))})
            wrote["proxies"] = now["proxies"]
            log("  reverse proxy addresses: " + (now["proxies"] or "none"))
    if wrote or changed:
        db.set_setting(DECLARED, json.dumps(now, sort_keys=True), "")
    return wrote


def demo_once(log=print) -> bool:
    """Step 4: the demo on a new suite (no account but the first admin) or one that has it already."""
    from iosuite_shared import demo, users
    people = [u for u in users.list_users() if u["name"] not in demo.FAMILY_KEYS]
    if not demo.wanted() and len(people) > 1:
        log("  demo data: not added, this suite has accounts of its own")
        return False
    if not demo.wanted():
        demo.switch(True)
        log(f"  demo data: the Calloway family ({', '.join(demo.FAMILY_KEYS)}; password {demo.DEMO_PASSWORD}); every app adds its own at its first start")
    return True


def main(a, log=print):
    if a.db_admin:
        provision_here(a.db_admin, a.client_host, log=log)
    from iosuite_shared import db, users
    wanted = parse_set(getattr(a, "set", None))

    def tables():
        if not users.init():  # makes the first admin too (ADMIN_USER / ADMIN_PASSWORD) when there is no account yet
            raise RuntimeError(db.error or "the Shared ioSuite database cannot be reached")
    _wait("the Shared ioSuite database", tables, log)
    log(f"  the Shared ioSuite database is ready: {len(users.list_users())} account(s)")
    declare(wanted, a.proxies, log=log)
    if getattr(a, "demo", False):
        demo_once(log=log)
    log("ok")
    sys.stdout.flush()
    cmd = then_command(a)
    if cmd:
        for k in ONLY_HERE:
            os.environ.pop(k, None)
        os.execvp(cmd[0], cmd)  # does not return: this process is the program from here on
    return 0

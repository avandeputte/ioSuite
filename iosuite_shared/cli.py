"""The `iosuite` command: run a copy of the program, and look after the suite from a shell.

    iosuite serve [--apps iostart,iocalendar]     run the apps (the machine's APPS; none named there: every app installed)
    iosuite apps                                  the suite's apps, which of them this machine runs, and where each answers
    iosuite settings [APP]                        the settings a person may set, with the value stored now
    iosuite set APP NAME [VALUE]                  store one (APP: an app's key, or suite); no VALUE: back to the default
    iosuite check | init                          reach the Shared ioSuite database (and make its tables)
    iosuite admin NAME [--app APP]                make NAME an admin (the first account is a suite admin)
    iosuite list | create | role | password | sign-in-reset     the accounts
    iosuite edge                                  the Cloudflare edge check of app passwords (iosuite_shared.edge)
    iosuite demo [--off]                          fill the suite with demo data (iosuite_shared.demo)
    iosuite provision                             make the databases and the one login (iosuite_shared.provision)
    iosuite stack                                 a container's first start (iosuite_shared.stack)
    iosuite install                               set this machine up, or change the apps it runs (iosuite_shared.install)

Everything reads the machine's file (config.env in the program folder; --config names another one, or a folder that
holds it), which says how to reach the Shared ioSuite database. `set` and `settings` are the Settings screen
(Settings › Global settings › Settings) for when the pages cannot be reached: a wrong address stored, say.
"""
import argparse
import getpass
import os
import sys


def _parser():
    p = argparse.ArgumentParser(prog="iosuite", description="ioSuite: one program that runs the apps it is told to")
    p.add_argument("--config", default=None, help="the machine's file, or a folder that holds config.env (default: the program folder)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the apps until stopped")
    s.add_argument("--apps", default=None, help="the apps of this copy, comma-separated (default: APPS in the machine's file, else every app installed)")
    sub.add_parser("apps", help="the suite's apps: which this machine runs, and where each answers")
    st = sub.add_parser("settings", help="the settings a person may set, with the value stored now")
    st.add_argument("app", nargs="?", default=None, help="one app's (its key), or suite; default: all")
    se = sub.add_parser("set", help="store a setting in the Shared ioSuite database (applies when the app starts again)")
    se.add_argument("app", help="an app's key (iocalendar), or suite for the whole suite's")
    se.add_argument("name")
    se.add_argument("value", nargs="?", default="", help="left out: the setting is removed and the default applies again")
    sub.add_parser("init", help="create the Shared ioSuite database's tables")
    sub.add_parser("check", help="connect to the Shared ioSuite database and count the accounts")
    ad = sub.add_parser("admin", help="make NAME an admin (created when missing; the first account is a suite admin)")
    ad.add_argument("name"); ad.add_argument("--app", default=None, help="an admin of this app only (default: a suite admin)")
    sub.add_parser("list", help="every account and its roles")
    c = sub.add_parser("create", help="a new account (suite admin with --suite-admin)")
    c.add_argument("name"); c.add_argument("--email", default=""); c.add_argument("--password", default=None); c.add_argument("--suite-admin", action="store_true")
    c.add_argument("--app", default=None); c.add_argument("--role", default=None)
    r = sub.add_parser("role", help="set an account's role in an app")
    r.add_argument("name"); r.add_argument("app"); r.add_argument("role", choices=("none", "viewer", "member", "editor", "admin"))
    pw = sub.add_parser("password", help="set an account's password")
    pw.add_argument("name"); pw.add_argument("--password", default=None)
    sr = sub.add_parser("sign-in-reset", help="turn an account's two-step sign-in off and remove its passkeys (a lost phone)")
    sr.add_argument("name")
    e = sub.add_parser("edge", help="compare the Cloudflare KV namespace of the edge check with the app passwords (removes stale keys with --apply)")
    e.add_argument("--apply", action="store_true")
    e.add_argument("--account-id", default=None, help="store the Cloudflare account id in the Shared ioSuite database")
    e.add_argument("--namespace-id", default=None, help="store the KV namespace id")
    e.add_argument("--token-file", default=None, help="store the API token read from this file ('-': standard input)")
    from iosuite_shared import demo, install, provision, stack
    demo.add_parser(sub)
    provision.add_parser(sub)
    stack.add_parser(sub)
    install.add_parser(sub)
    return p


def _app_key(named: str) -> str:
    """'' for the whole suite (suite, _suite, all), else the app's key."""
    return "" if named.lower() in ("suite", "_suite", "all", "") else named.lower()


def _show(d: dict) -> str:
    v = d.get("value") or ""
    if v:
        return v
    if d.get("suite"):
        return f"(the suite's: {d['suite']})"
    return f"(default: {d['default']})" if d.get("default") else "(not set)"


def settings_cmd(a, out=print) -> int:
    from iosuite_shared import admin, catalog, config, db
    only = None if a.app is None else _app_key(a.app)
    if only and only not in catalog.APPS:
        raise SystemExit(f"error: no such app: {a.app} (the suite's apps: {', '.join(catalog.APPS)})")
    whole = db.settings_of("")
    groups = []
    if only in (None, ""):
        groups.append(("suite", [admin._with_value(d, whole) for d in config.declared("")]))
    for k in catalog.APPS:
        if only is None or only == k:
            groups.append((k, [admin._with_value(d, db.settings_of(k)) for d in config.declared(k)]))
    for name, items in groups:
        if only is None and name != "suite" and not any(d["value"] for d in items):
            continue  # the whole list: only the apps that have something set
        out(f"{name}:")
        for d in items:
            out(f"  {d['name']:28} {_show(d):40} {d['label']}")
    if only is None:
        out("(apps with nothing set are left out: iosuite settings APP lists one app's)")
    return 0


def set_cmd(a, out=print) -> int:
    from iosuite_shared import admin
    try:
        r = admin.set_setting(_app_key(a.app) or admin.SUITE, a.name, a.value)
    except (LookupError, ValueError) as e:
        raise SystemExit(f"error: {str(e).strip(chr(39))}")
    where = r["app"] or "the whole suite"
    out(f"ok: {r['name']} of {where} " + (f"is {r['value']}" if r["value"] else "is removed (the default applies)"))
    out("    it applies when the app starts again: systemctl restart iosuite, or Restart under Settings › Global settings › Settings")
    return 0


def apps_cmd(a, out=print) -> int:
    from iosuite_shared import catalog, config, host, suite
    mine = host.names()
    try:
        registered = {r["app"]: r for r in suite.apps()}
    except Exception as e:  # noqa: BLE001  the database is away: the list without where they answer
        out(f"(the Shared ioSuite database does not answer: {str(e)[:120]})")
        registered = {}
    out(f"this machine ({suite.copy_name()}) runs: {', '.join(mine) or 'nothing'}"
        + ("" if config.APPS else "  (APPS is not set: every app installed)"))
    for k in catalog.APPS:
        r = registered.get(k)
        where = f"{r['url'] or '-'}  on {r.get('copy') or '?'}" if r else "not running anywhere yet"
        out(f"  {k:12} {'here' if k in mine else '    '}  {where}")
    return 0


def main(argv=None):
    a = _parser().parse_args(argv)
    from iosuite_shared import config
    if a.config:
        config.load_file(a.config)

    if a.cmd == "serve":
        from iosuite_shared import host
        return host.run(config.apps_named(a.apps) if a.apps else None)
    if a.cmd == "provision":  # connects as the database's administrator, not as the suite
        from iosuite_shared import provision
        return provision.main(a)
    if a.cmd == "stack":  # a container's first start: the databases first, then the tables
        from iosuite_shared import stack
        return stack.main(a)
    if a.cmd == "demo":
        from iosuite_shared import demo
        return demo.main(a)
    if a.cmd == "install":  # may be what makes the database
        from iosuite_shared import install
        return install.main(a)

    from iosuite_shared import db, users
    if not users.init():
        raise SystemExit(f"error: the Shared ioSuite database cannot be reached ({config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}): {db.error}")
    if a.cmd == "apps":
        return apps_cmd(a)
    if a.cmd == "settings":
        return settings_cmd(a)
    if a.cmd == "set":
        return set_cmd(a)
    if a.cmd == "init":
        print("ok")
    elif a.cmd == "check":
        print(f"ok: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}, {len(users.list_users())} account(s)")
    elif a.cmd == "admin":
        password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass(f"Password for {a.name}: ")
        u = users.find(a.name)
        try:
            if u and a.app:
                users.update(u["id"], password=password or None, role="admin", app=a.app)
                print(f"ok: {a.name} is an admin of {a.app}")
            elif u:
                users.update(u["id"], password=password or None, suite_admin=True)
                print(f"ok: {a.name} is a suite admin")
            else:
                first = not users.any_users()
                users.create(a.name, password, "admin" if a.app else None, a.app, suite_admin=first or not a.app)
                print(f"ok: created {a.name}" + (" (suite admin)" if first or not a.app else f" (admin of {a.app})"))
        except ValueError as e:
            sys.exit(f"error: {e}")
    elif a.cmd == "list":
        for u in users.list_users():
            roles = ", ".join(f"{k}={v}" for k, v in users.roles_of(u["id"]).items()) or "-"
            print(f"{u['id']:4} {u['name']:24} {u['email'] or '':30} {'suite-admin' if u['suiteAdmin'] else '':12} {'(no password)' if u['passwordless'] else '':14} {roles}")
    elif a.cmd == "create":
        password = a.password if a.password is not None else getpass.getpass("Password (empty: one-click, a member at most): ")
        print(users.create(a.name, password, a.role, a.app, email=a.email, suite_admin=a.suite_admin))
    elif a.cmd == "role":
        u = users.find(a.name)
        if not u:
            sys.exit(f"no account {a.name}")
        users.set_role(u["id"], a.app, a.role)
        print(users.roles_of(u["id"]))
    elif a.cmd == "password":
        u = users.find(a.name)
        if not u:
            sys.exit(f"no account {a.name}")
        users.update(u["id"], password=a.password if a.password is not None else getpass.getpass("New password: "))
        print("ok")
    elif a.cmd == "sign-in-reset":
        u = users.find(a.name)
        if not u:
            sys.exit(f"no account {a.name}")
        from iosuite_shared import admin
        admin.reset_sign_in(u["id"])
        print(f"ok: {a.name} signs in with the password alone")
    elif a.cmd == "edge":
        from iosuite_shared import edge
        if a.account_id is not None or a.namespace_id is not None or a.token_file:
            token = None
            if a.token_file:
                token = (sys.stdin.read() if a.token_file == "-" else open(a.token_file, encoding="utf-8").read()).strip()
            edge.store(a.account_id, a.namespace_id, token, by="iosuite edge")
            print("stored in the Shared ioSuite database (the whole suite's keys)")
        if not edge.enabled():
            sys.exit("the edge check is off: store the account id, namespace id and token (iosuite edge --help)")
        r = edge.sync(apply=a.apply)
        print(f"{r['keys']} key(s) at the edge, {r['passwords']} app password(s)")
        for k in r["stale"]:
            print(("removed " if a.apply else "stale (no such password; --apply removes it) ") + k)
        for k in r["missing"]:
            print(f"not at the edge yet (put there on its next use): {k}")


if __name__ == "__main__":
    main()

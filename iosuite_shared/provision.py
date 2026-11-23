"""`iosuite provision --admin USER`: with a MariaDB / MySQL administrator account (root, or any account that may
CREATE DATABASE, CREATE USER and GRANT), make what the machine's file names: the Shared ioSuite database, the suite's
one login (IOSUITE_DB_*), and a database for every app this machine runs (or the apps given with --apps), each named
after its app unless Settings stores another name for it.

The suite signs in to every one of its databases with that one login, so this is all the database set-up there is.
The administrator's password comes in through DB_ADMIN_PASSWORD in the environment (else it is asked for), never on a
command line, and is not kept. Nothing is dropped: databases and the login are created when missing, and the login
gets all privileges on the suite's databases only. A login that exists already keeps its password (other machines of
the suite sign in with it too): when the machine's file names another one, provision says so instead of changing it
under them.

The login is made for this machine only: 'localhost' and '127.0.0.1' when the server is this machine, otherwise the
address this machine reaches the server from (or --client-host, e.g. a subnet like '192.168.1.%' for a machine whose
address changes, '%' for containers).
"""
import getpass
import os
import re
import socket

IDENT = re.compile(r"^[A-Za-z0-9_]+$")
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _ident(kind, value):
    if not value or not IDENT.match(value):
        raise SystemExit(f"error: the {kind} {value!r} must be letters, digits and _ only")
    return value


def own_address(host, port) -> str:
    """The address this machine reaches the database server from (no packet is sent: a UDP socket only picks the route)."""
    try:
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((host, int(port or 3306)))
            return s.getsockname()[0]
    except OSError as exc:
        raise SystemExit(f"error: cannot tell this machine's address towards {host}:{port} ({exc}); give it with --client-host")


def client_hosts(server, port, client=None, here=None) -> list:
    """The hosts the login is made for: this machine as the server sees it."""
    if client:
        return [client]
    if server.lower() in LOOPBACK:
        return ["localhost", "127.0.0.1"]
    return [(here or own_address)(server, port)]


def target() -> dict:
    """The server and the login, from the machine's file: {host, port, name, user, password}."""
    from iosuite_shared import config
    return {"host": config.DB_HOST, "port": config.DB_PORT, "name": config.DB_NAME, "user": config.DB_USER, "password": config.DB_PASSWORD}


def databases(apps) -> list:
    """The database of each of these apps: the name stored for it (Settings: DB_NAME) when the Shared ioSuite
    database can already be read, else the app's key."""
    from iosuite_shared import db
    stored = {}
    try:
        stored = {r["app"]: r["value"] for r in db.q("SELECT app, value FROM ios_settings WHERE name = 'DB_NAME' AND app != ''")}
    except Exception:  # noqa: BLE001  not there yet: this is what makes it
        pass
    return [(stored.get(a) or a).strip() for a in apps]


def plan_sql(t: dict, names, client=None, here=None) -> list:
    """What to run on the server: [(sql, args), ...]. Pure but for `here` (this machine's address towards a remote
    server), for the tests and for --dry-run."""
    user = _ident("user name", t["user"])
    hosts = client_hosts(t["host"], t["port"], client, here)
    stmts = []
    for h in hosts:
        stmts.append((f"CREATE USER IF NOT EXISTS `{user}`@%s IDENTIFIED BY %s", (h, t["password"])))
    for name in [t["name"], *names]:
        if any(s.startswith(f"CREATE DATABASE IF NOT EXISTS `{name}`") for s, _ in stmts):
            continue
        stmts.append((f"CREATE DATABASE IF NOT EXISTS `{_ident('database name', name)}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci", None))
        for h in hosts:
            stmts.append((f"GRANT ALL PRIVILEGES ON `{name}`.* TO `{user}`@%s", (h,)))
    stmts.append(("FLUSH PRIVILEGES", None))
    return stmts


def run(admin_user, admin_password, names, t=None, connect=None, log=print, client=None, here=None, check=None) -> list:
    """Create everything; the databases made or found. Raises SystemExit with the reason on failure.
    `check(t)` signs in as the suite's login afterwards (by default with a real connection when `connect` is the
    real one too): a login that already existed with another password is said here."""
    import pymysql
    t = t or target()
    if check is None and connect is None:
        check = lambda t: pymysql.connect(host=t["host"], port=int(t["port"]), user=t["user"], password=t["password"],  # noqa: E731
                                          database=t["name"], connect_timeout=10).close()
    connect = connect or (lambda host, port: pymysql.connect(host=host, port=int(port), user=admin_user, password=admin_password,
                                                             connect_timeout=10, autocommit=True))
    stmts = plan_sql(t, names, client, here)
    try:
        conn = connect(t["host"], t["port"])
    except Exception as exc:  # noqa: BLE001 - say what went wrong, in one line
        raise SystemExit(f"error: could not connect to {t['host']}:{t['port']} as {admin_user}: {exc}")
    try:
        with conn.cursor() as cur:
            for sql, args in stmts:
                try:
                    cur.execute(sql, args)
                except Exception as exc:  # noqa: BLE001
                    raise SystemExit(f"error: {t['host']}:{t['port']}: {sql.split(' ON ')[0].split(' IDENTIFIED')[0]}: {exc}")
    finally:
        conn.close()
    made = sorted({s.split("`")[1] for s, _ in stmts if s.startswith("CREATE DATABASE")})
    log(f"  {t['host']}:{t['port']}: database(s) {', '.join(made)} ready for the login {t['user']}")
    if check:
        try:
            check(t)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"error: the suite's login {t['user']} cannot sign in with the password in the machine's file ({exc}). "
                             f"It existed already, and the suite's other machines use it: put its password in this machine's "
                             f"config.env (IOSUITE_DB_PASSWORD), or change it on the server and in every machine's file")
    return made


def add_parser(sub):
    p = sub.add_parser("provision", help="create the suite's databases and its one login with a MariaDB administrator account")
    p.add_argument("--admin", required=True, help="the administrator's user name (its password from DB_ADMIN_PASSWORD, else asked for)")
    p.add_argument("--apps", default="", help="the apps to make a database for (default: the apps this machine runs)")
    p.add_argument("--client-host", default=None, help="the host the login is made for (default: this machine as the server sees it; e.g. '192.168.1.%%')")
    p.add_argument("--dry-run", action="store_true", help="only print what would be run (the password hidden)")
    return p


def main(a, log=print):
    from iosuite_shared import config, host
    apps = host.names(config.apps_named(a.apps) if a.apps else None)
    t = target()
    if not t["password"]:
        raise SystemExit("error: IOSUITE_DB_PASSWORD is not set in the machine's file: the suite's login needs a password")
    names = databases(apps)
    if a.dry_run:
        log(f"{t['host']}:{t['port']}")
        for sql, args in plan_sql(t, names, a.client_host):
            log("  " + sql + (f"   -- {args[0]}" if args else ""))
        return 0
    password = os.environ.get("DB_ADMIN_PASSWORD")
    if password is None:
        password = getpass.getpass(f"MariaDB password for {a.admin}: ")
    run(a.admin, password, names, t, client=a.client_host, log=log)
    return 0

"""The Shared ioSuite database: connections, the schema, and the suite-wide / per-app settings table.

Connections come from a small pool (Pool), in autocommit mode: a statement on its own (q, one, ex) is one round trip,
and a unit of work (tx) begins a transaction, commits or rolls back, and gives the connection back. A PyMySQL
connection is never used by two threads at once. Rows come back as dicts. The apps use Database (the pool, the
transaction and q / one / ex / many) for their own databases too.
"""
import json
import logging
import queue
import select
import threading
import time
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from iosuite_shared import config, schema

log = logging.getLogger("iosuite_shared.db")

SCHEMA_VERSION = 12  # recorded in ios_schema_version; the tables are made as SCHEMA says, and get the columns and indexes added to it later (schema.create)
PREFIX = "ios"
OPTIONS = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"

# Every table is ios_<name>, so the shared tables can sit in the same database as the apps' own (each app has its
# own three-letter prefix). Times are seconds since 1970 (UTC).
SCHEMA = [
    # one account for the whole suite. hash '' is a passwordless account: one-click sign-in on the LAN, member at most.
    """CREATE TABLE IF NOT EXISTS ios_users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        display_name VARCHAR(128) NULL,
        email VARCHAR(191) NULL,
        hash VARCHAR(255) NOT NULL DEFAULT '',
        suite_admin TINYINT NOT NULL DEFAULT 0,
        listed TINYINT NOT NULL DEFAULT 1,
        created_at BIGINT NOT NULL,
        last_login_at BIGINT NULL,
        service VARCHAR(32) NULL,
        UNIQUE KEY uq_ios_users_name (name),
        UNIQUE KEY uq_ios_users_email (email)
    )""",
    # the role an account holds in one app; no row: the app's default_role setting (member unless changed)
    """CREATE TABLE IF NOT EXISTS ios_user_roles (
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        role ENUM('none','viewer','member','editor','admin') NOT NULL,
        PRIMARY KEY (user_id, app),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # per-user, per-app values (display settings, the ioPix person tag, the ioContact "me" contact), JSON-encoded
    """CREATE TABLE IF NOT EXISTS ios_user_data (
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        value MEDIUMTEXT NOT NULL,
        PRIMARY KEY (user_id, app, name),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # a browser or app session: the cookie carries a random token, the table its hash. Shared by every app on the
    # domain. Where it began and was last seen: the visitor's address (the real one, through Cloudflare or a trusted
    # proxy), whether it came through Cloudflare, the client (web, or the app's User-Agent product) and the full User-Agent.
    """CREATE TABLE IF NOT EXISTS ios_sessions (
        token_hash CHAR(64) PRIMARY KEY,
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        via VARCHAR(16) NOT NULL,
        created_at BIGINT NOT NULL,
        expires_at BIGINT NOT NULL,
        renewed_at BIGINT NOT NULL,
        ip VARCHAR(64) NULL,
        cloudflare TINYINT NOT NULL DEFAULT 0,
        client VARCHAR(32) NOT NULL DEFAULT '',
        user_agent VARCHAR(255) NULL,
        last_seen_at BIGINT NULL,
        last_ip VARCHAR(64) NULL,
        INDEX idx_ios_sessions_user (user_id),
        INDEX idx_ios_sessions_expires (expires_at),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # app passwords: one per device, for one app (CardDAV, LDAP, MCP clients...); shown once, revocable
    """CREATE TABLE IF NOT EXISTS ios_app_passwords (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        label VARCHAR(128) NOT NULL,
        prefix CHAR(8) NOT NULL,
        hash VARCHAR(255) NOT NULL,
        created_at BIGINT NOT NULL,
        last_used_at BIGINT NULL,
        scope VARCHAR(32) NOT NULL DEFAULT '',
        INDEX idx_ios_app_passwords_prefix (prefix),
        INDEX idx_ios_app_passwords_user (user_id),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # subscription links (iosuite_shared.feeds): an address with a secret for apps that cannot sign in (a calendar app
    # subscribed to ioCalendar or to ioContact's birthdays); only a SHA-256 of the secret, shown once, stopped one at a time
    """CREATE TABLE IF NOT EXISTS ios_feed_tokens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        label VARCHAR(128) NOT NULL,
        token_hash CHAR(64) NOT NULL,
        created_at BIGINT NOT NULL,
        last_used_at BIGINT NULL,
        UNIQUE KEY uq_ios_feed_tokens_hash (token_hash),
        INDEX idx_ios_feed_tokens_user (user_id, app),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # suite-wide (app '') and per-app settings: proxy sign-in, require_login, default_role
    """CREATE TABLE IF NOT EXISTS ios_settings (
        app VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        value MEDIUMTEXT NOT NULL,
        PRIMARY KEY (app, name)
    )""",
    # keys and tokens: every credential an app keeps (an integration's API key, the sign-in one app uses to reach
    # another), one row per key the app declares; value '' while none is set (iosuite_shared.credentials)
    """CREATE TABLE IF NOT EXISTS ios_credentials (
        app VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        value MEDIUMTEXT NOT NULL,
        label VARCHAR(128) NOT NULL,
        hint VARCHAR(255) NOT NULL DEFAULT '',
        updated_at BIGINT NULL,
        updated_by VARCHAR(64) NULL,
        PRIMARY KEY (app, name)
    )""",
    # the suite's apps, each written by the app itself when it starts (iosuite_shared.suite): what it is called, its
    # version, and where it is (the address its configuration names, else the best one it was reached at; and inside the
    # network: its LAN address and port), so the start
    # page and the others link to it without anybody typing an address
    """CREATE TABLE IF NOT EXISTS ios_apps (
        app VARCHAR(32) PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        description VARCHAR(255) NULL,
        version VARCHAR(32) NULL,
        color VARCHAR(16) NULL,
        icon VARCHAR(512) NULL,
        configured_url VARCHAR(512) NULL,
        seen_url VARCHAR(512) NULL,
        internal_url VARCHAR(512) NULL,
        sync_url VARCHAR(512) NULL,
        mcp_url VARCHAR(512) NULL,
        internal_sync_url VARCHAR(512) NULL,
        internal_mcp_url VARCHAR(512) NULL,
        copy_name VARCHAR(64) NULL,
        admin_tool TINYINT NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        last_seen_at BIGINT NULL
    )""",
    # updating the apps from one place (iosuite_shared.suiteupdates): a suite admin leaves an action for an app, the
    # app takes it off and runs it, and writes back what it knows about its own version and its last update
    """CREATE TABLE IF NOT EXISTS ios_updates (
        app VARCHAR(32) PRIMARY KEY,
        action VARCHAR(16) NULL,
        requested_at BIGINT NULL,
        requested_by VARCHAR(64) NULL,
        installed VARCHAR(32) NULL,
        git_commit VARCHAR(40) NULL,
        latest VARCHAR(32) NULL,
        status VARCHAR(16) NULL,
        checked_at BIGINT NULL,
        can_run TINYINT NOT NULL DEFAULT 0,
        docker TINYINT NOT NULL DEFAULT 0,
        state VARCHAR(16) NULL,
        message VARCHAR(300) NULL,
        updated_at BIGINT NOT NULL
    )""",
    # notifications (iosuite_shared.push): each device a person turned them on on (a browser's push subscription;
    # key_id: the sender key it was made for), whichever app it was turned on in, and every app sends to all of them
    """CREATE TABLE IF NOT EXISTS ios_push_devices (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        endpoint VARCHAR(1024) NOT NULL,
        endpoint_hash CHAR(64) NOT NULL,
        p256dh VARCHAR(128) NOT NULL,
        auth VARCHAR(64) NOT NULL,
        label VARCHAR(128) NOT NULL DEFAULT '',
        app VARCHAR(32) NOT NULL DEFAULT '',
        key_id CHAR(16) NOT NULL DEFAULT '',
        created_at BIGINT NOT NULL,
        last_ok_at BIGINT NULL,
        failures INT NOT NULL DEFAULT 0,
        UNIQUE KEY uq_ios_push_devices_endpoint (endpoint_hash),
        INDEX idx_ios_push_devices_user (user_id),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # what was sent once (a reminder, a morning summary, a new version), so no app sends it again after a restart
    """CREATE TABLE IF NOT EXISTS ios_push_sent (
        user_id INT NOT NULL,
        tag VARCHAR(191) NOT NULL,
        sent_at BIGINT NOT NULL,
        PRIMARY KEY (user_id, tag),
        INDEX idx_ios_push_sent_at (sent_at),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # linked items (iosuite_shared.related): two items of the suite, each a kind (event, task, note, contact, recipe, item,
    # photo) and its id in its app; one row for both ways, the smaller end first
    """CREATE TABLE IF NOT EXISTS ios_related (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        a_kind VARCHAR(16) NOT NULL,
        a_id VARCHAR(64) NOT NULL,
        b_kind VARCHAR(16) NOT NULL,
        b_id VARCHAR(64) NOT NULL,
        created_by INT NULL,
        created_at BIGINT NOT NULL,
        UNIQUE KEY uq_ios_related (a_kind, a_id, b_kind, b_id),
        INDEX idx_ios_related_b (b_kind, b_id),
        FOREIGN KEY (created_by) REFERENCES ios_users(id) ON DELETE SET NULL
    )""",
    # two-step sign-in (iosuite_shared.twostep): the secret a person's code app makes its codes from, on once
    # confirmed_at is set; last_step: the 30-second step of the last code taken (a code works once); recovery: the
    # SHA-256 of each recovery code not used yet, a JSON list
    """CREATE TABLE IF NOT EXISTS ios_two_step (
        user_id INT PRIMARY KEY,
        secret VARCHAR(64) NOT NULL,
        created_at BIGINT NOT NULL,
        confirmed_at BIGINT NULL,
        last_step BIGINT NOT NULL DEFAULT 0,
        recovery TEXT NULL,
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # passkeys (iosuite_shared.passkeys): a public key per device or password manager, for the address (rp_id) it was
    # made at; credential_id and public_key are base64url, credential_hash the SHA-256 of the id (ids can be long)
    """CREATE TABLE IF NOT EXISTS ios_passkeys (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        credential_hash CHAR(64) NOT NULL,
        credential_id TEXT NOT NULL,
        public_key TEXT NOT NULL,
        alg INT NOT NULL,
        sign_count BIGINT NOT NULL DEFAULT 0,
        rp_id VARCHAR(191) NOT NULL,
        label VARCHAR(128) NOT NULL,
        created_at BIGINT NOT NULL,
        last_used_at BIGINT NULL,
        UNIQUE KEY uq_ios_passkeys_credential (credential_hash),
        INDEX idx_ios_passkeys_user (user_id),
        INDEX idx_ios_passkeys_rp (rp_id),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # the challenges handed to a browser for a passkey (to add one, to sign in): each used once, kept a few minutes
    """CREATE TABLE IF NOT EXISTS ios_auth_challenges (
        challenge CHAR(43) PRIMARY KEY,
        kind VARCHAR(8) NOT NULL,
        rp_id VARCHAR(191) NOT NULL,
        user_id INT NULL,
        expires_at BIGINT NOT NULL,
        INDEX idx_ios_auth_challenges_expires (expires_at)
    )""",
    # the apps' jobs (iosuite_shared.jobs): one row per job, kept by the copy that runs it, so that Settings ›
    # Servers › Jobs shows every app's chores, syncs and reminders wherever they run. run_now is a Run now somebody
    # pressed: the copy that owns the job takes the flag off and runs it.
    """CREATE TABLE IF NOT EXISTS ios_jobs (
        app VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        copy VARCHAR(64) NOT NULL DEFAULT '',
        title VARCHAR(120) NOT NULL DEFAULT '',
        every_s INT NOT NULL DEFAULT 0,
        heavy TINYINT NOT NULL DEFAULT 0,
        state VARCHAR(16) NOT NULL DEFAULT '',
        started_at BIGINT NULL,
        finished_at BIGINT NULL,
        took_ms INT NULL,
        message VARCHAR(300) NULL,
        runs INT NOT NULL DEFAULT 0,
        failures INT NOT NULL DEFAULT 0,
        run_now TINYINT NOT NULL DEFAULT 0,
        requested_by VARCHAR(64) NULL,
        next_at BIGINT NULL,
        seen_at BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (app, name),
        INDEX idx_ios_jobs_run_now (run_now)
    )""",
    # what changed, for the one live-refresh stream every page holds (iosuite_shared.live): a few minutes deep, each
    # line only "app X's Y changed" and when, so any signed-in page may hear it; user_id keeps a line to one person.
    """CREATE TABLE IF NOT EXISTS ios_changes (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        at BIGINT NOT NULL,
        app VARCHAR(32) NOT NULL,
        what VARCHAR(48) NOT NULL,
        user_id INT NULL,
        body VARCHAR(500) NULL,
        origin VARCHAR(40) NOT NULL DEFAULT '',
        INDEX idx_ios_changes_at (at)
    )""",
    # who added an item of an app and who changed it last, through what and where (iosuite_shared.stamp): one row per
    # item (kind and id as in ios_related); *_client one of stamp.CLIENTS, *_where the app password's name, the browser
    # or the job, *_via the app that asked on the person's behalf; *_name the account's name then, kept when it goes
    """CREATE TABLE IF NOT EXISTS ios_item_stamps (
        app VARCHAR(32) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        item VARCHAR(64) NOT NULL,
        created_at BIGINT NULL,
        created_by INT NULL,
        created_name VARCHAR(128) NULL,
        created_client VARCHAR(8) NULL,
        created_where VARCHAR(191) NULL,
        created_via VARCHAR(32) NULL,
        updated_at BIGINT NOT NULL,
        updated_by INT NULL,
        updated_name VARCHAR(128) NULL,
        updated_client VARCHAR(8) NULL,
        updated_where VARCHAR(191) NULL,
        updated_via VARCHAR(32) NULL,
        PRIMARY KEY (app, kind, item),
        FOREIGN KEY (created_by) REFERENCES ios_users(id) ON DELETE SET NULL,
        FOREIGN KEY (updated_by) REFERENCES ios_users(id) ON DELETE SET NULL
    )""",
    # an item's history (iosuite_shared.stamp): the last KEEP changes of each item, for DAYS days; place as *_where
    # above, ip the address the change came from (shown only to whoever made it and to suite admins), outside: from
    # outside the network; what: a few words on what changed, never the item's content
    """CREATE TABLE IF NOT EXISTS ios_item_changes (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        app VARCHAR(32) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        item VARCHAR(64) NOT NULL,
        at BIGINT NOT NULL,
        action VARCHAR(8) NOT NULL,
        what VARCHAR(255) NULL,
        user_id INT NULL,
        name VARCHAR(128) NULL,
        client VARCHAR(8) NOT NULL,
        place VARCHAR(191) NULL,
        via VARCHAR(32) NULL,
        ip VARCHAR(64) NULL,
        cloudflare TINYINT NOT NULL DEFAULT 0,
        outside TINYINT NOT NULL DEFAULT 0,
        INDEX idx_ios_item_changes_item (app, kind, item, id),
        INDEX idx_ios_item_changes_at (at),
        INDEX idx_ios_item_changes_user (user_id),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE SET NULL
    )""",
]

_overrides: dict = {}  # the tests point the library at another database


def configure(**values):
    """Override host, port, database, user, password (the tests; an app that keeps its own configuration)."""
    global _ready
    _overrides.update({k: v for k, v in values.items() if v is not None})
    settings_cache.clear()
    _pool.drain()  # the kept connections point at the old database
    _ready = False  # another database: its tables are checked again


def params() -> dict:
    p = {"host": config.DB_HOST, "port": config.DB_PORT, "database": config.DB_NAME, "user": config.DB_USER, "password": config.DB_PASSWORD}
    p.update(_overrides)
    return p


def connect(database: str | None = ...):
    p = params()
    return pymysql.connect(host=p["host"], port=int(p["port"]), user=p["user"], password=p["password"],
                           database=p["database"] if database is ... else database, charset="utf8mb4",
                           cursorclass=DictCursor, autocommit=True, connect_timeout=8, read_timeout=60, write_timeout=60)


BROKEN = (pymysql.err.OperationalError, pymysql.err.InterfaceError)  # the connection itself failed: it is closed, not kept


class Pool:
    """A few open connections, reused: `connect` makes a new one, `size` is how many are kept. A connection that sat
    unused for more than IDLE_S is pinged before it is lent again (and replaced when the server dropped it); one that
    was in use a moment ago is only looked at (_open: no round trip), so a query is one round trip to the server and
    not three. A connection
    that failed inside a unit of work is closed, and so are the kept ones (the server went away: they are gone too).
    Thread-safe: a connection is in one thread's hands at a time.

    `connect` should open connections in autocommit mode: `auto()` then runs a statement with nothing around it, and
    `tx()` begins and commits its own transaction. Connections with autocommit off work as well (both commit at the end)."""

    IDLE_S = 30.0

    def __init__(self, connect, size: int = 8):
        self._connect, self._kept = connect, queue.LifoQueue(maxsize=size)

    def borrow(self):
        try:
            con, at = self._kept.get_nowait()
        except queue.Empty:
            return self._connect()
        try:
            if time.monotonic() - at >= self.IDLE_S:
                con.ping(reconnect=False)
            elif not _open(con):
                raise pymysql.err.InterfaceError(0, "closed")
            return con
        except pymysql.MySQLError:
            _close(con)
            return self._connect()

    def give_back(self, con, broken: bool = False):
        if broken:
            _close(con)
            self.drain()
            return
        try:
            self._kept.put_nowait((con, time.monotonic()))
        except queue.Full:
            _close(con)

    def drain(self):
        """Close every kept connection (the database changed; shutdown)."""
        while True:
            try:
                _close(self._kept.get_nowait()[0])
            except queue.Empty:
                return

    @contextmanager
    def _lend(self, transaction: bool):
        con = self.borrow()
        broken, commits = False, False
        try:
            commits = not con.get_autocommit()
            if transaction and not commits:
                con.begin()
                commits = True
            yield con
            if commits:
                con.commit()
        except BaseException as e:
            broken = isinstance(e, BROKEN)
            try:
                if not broken and commits:
                    con.rollback()
            except pymysql.MySQLError:
                broken = True
            raise
        finally:
            self.give_back(con, broken)

    def tx(self):
        """A connection whose work is one transaction: committed at the end of the block, rolled back on an exception."""
        return self._lend(True)

    def auto(self):
        """A connection for statements that each stand on their own (a read, one insert): no transaction is begun."""
        return self._lend(False)


class Database:
    """One database as an app uses it: a Pool, a transaction that nested calls on the same thread share, and the
    helpers q / one / ex / many, which run inside the thread's open transaction when there is one and on their own
    otherwise. The apps keep one for their own database (`_db = Database(connect)`; `tx, q, one, ex = _db.tx, ...`)."""

    def __init__(self, connect, size: int = 8):
        self.pool = Pool(connect, size)
        self._local = threading.local()

    @contextmanager
    def tx(self):
        """One transaction: committed on success, rolled back on an exception. Nested calls share it."""
        con = getattr(self._local, "con", None)
        if con is not None:
            yield con
            return
        with self.pool.tx() as con:
            self._local.con = con
            try:
                yield con
            finally:
                self._local.con = None

    @contextmanager
    def cursor(self, kind=None):
        """A cursor for one statement: in the thread's open transaction, else on a connection of its own. `kind`: a
        PyMySQL cursor class other than the connection's (DictCursor on a connection that gives tuples)."""
        con = getattr(self._local, "con", None)
        if con is not None:
            with con.cursor(kind) as cur:
                yield cur
            return
        with self.pool.auto() as con, con.cursor(kind) as cur:
            yield cur

    def q(self, sql: str, args=None, kind=None) -> list:
        with self.cursor(kind) as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def one(self, sql: str, args=None):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def ex(self, sql: str, args=None) -> int:
        """Run one statement; returns lastrowid (inserts) or the affected row count."""
        with self.cursor() as cur:
            n = cur.execute(sql, args)
            return cur.lastrowid or n

    def many(self, sql: str, rows: list) -> None:
        if rows:
            with self.tx() as con, con.cursor() as cur:
                cur.executemany(sql, rows)


def _open(con) -> bool:
    """Whether a kept connection still looks usable, without asking the server: it was not closed here, and nothing
    waits to be read on its socket (a server that closed the connection, or went away, leaves an end-of-file there)."""
    if not con.open:
        return False
    sock = getattr(con, "_sock", None)
    try:
        return sock is None or not select.select([sock], [], [], 0)[0]
    except (OSError, ValueError):
        return False


def _close(con):
    try:
        con.close()
    except Exception:  # noqa: BLE001 - already gone
        pass


_db = Database(connect)
_pool = _db.pool



def tx():
    """A pooled connection whose work is one transaction: committed at the end of the block, rolled back on an
    exception. Nested calls on the same thread share it, and so do q / one / ex inside the block."""
    return _db.tx()


q, one, ex = _db.q, _db.one, _db.ex


_ready = False
error = None  # why the database could not be opened at start (None once it could)
_init_lock = threading.Lock()
_retry_at = 0.0


def init():
    """Create the database if the account may, then every table (idempotent)."""
    global _ready
    with _init_lock:
        if _ready:
            return
        p = params()
        try:
            con = connect(database=None)
            try:
                with con.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{p['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                con.commit()
            finally:
                con.close()
        except pymysql.MySQLError:
            pass  # no right to create databases: it has to exist already
        with tx() as con:
            with con.cursor() as cur:
                schema.create(cur, SCHEMA, OPTIONS)
                schema.ensure_version_table(cur, PREFIX)
                schema.record_version(cur, PREFIX, SCHEMA_VERSION)
        _ready = True


def ready() -> bool:
    return _ready


def available() -> bool:
    """Whether the database can be used; when the start failed, another try at most every 10 seconds."""
    global _retry_at
    if _ready:
        return True
    if time.time() < _retry_at:
        return False
    _retry_at = time.time() + 10
    from iosuite_shared import users
    return users.init()


# ---- settings: suite-wide (app '') with a per-app override
settings_cache: dict = {}  # (app, key) -> (value, at)
CACHE_S = 5.0


def get_setting(key: str, default: str = "", app: str = "") -> str:
    """The setting for this app, else the suite-wide one, else default. Cached a few seconds: asked on every request."""
    now = time.time()
    hit = settings_cache.get((app, key))
    if hit and now - hit[1] < CACHE_S:
        return hit[0] if hit[0] is not None else default
    v = None
    rows = q("SELECT app, value FROM ios_settings WHERE name = %s AND app IN (%s, '')", (key, app))
    by_app = {r["app"]: r["value"] for r in rows}
    if app in by_app:
        v = by_app[app]
    elif "" in by_app:
        v = by_app[""]
    settings_cache[(app, key)] = (v, now)
    return v if v is not None else default


def set_setting(key: str, value, app: str = ""):
    """Store (or, with None / '', remove) a setting for the app ('' : suite-wide)."""
    if value is None or str(value) == "":
        ex("DELETE FROM ios_settings WHERE app = %s AND name = %s", (app, key))
    else:
        ex("INSERT INTO ios_settings (app, name, value) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (app, key, str(value)))
    settings_cache.clear()


def settings_of(app: str = "") -> dict:
    """Every setting stored for exactly this app (no fallback), for Settings screens."""
    return {r["name"]: r["value"] for r in q("SELECT name, value FROM ios_settings WHERE app = %s", (app,))}


def json_load(s, default=None):
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default

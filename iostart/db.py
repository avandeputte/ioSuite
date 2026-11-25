"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start).

The start page keeps prt_settings (the default photo strip, the weather settings and its cached answers, the update
switch, each account's layout), prt_schema_version and the bookmarks. What the page grows later gets its tables here
too. Every table is prt_<name>, the suite's naming convention (the apps can share one database)."""

from iostart import config

from iosuite_shared import db as shared_db

SCHEMA_VERSION = 10  # 10: feeds, the reader (prt_feeds, prt_feed_items, prt_feed_subs, prt_feed_marks: iostart/news/__init__.py); 9: kitchen timers (prt_timers); 8: TRMNL devices (prt_trmnl_devices); 7: shared and personal bookmarks (owner, shared; prt_bookmark_starts)
PREFIX = "prt"

# Every table is InnoDB/utf8mb4. Accounts and app passwords live in the Shared ioSuite database (iosuite_shared,
# the app as declared: iosuite_shared.app), not here.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS prt_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # the bookmarks: one tree of folders and links, as a browser keeps them, which sync clients (the ioStart Bookmarks
    # extension, the iPhone app) read and write. An id is handed out by the app
    # (never reused: sync clients remember them). `start` picks what the start page shows: on a folder, 1 shows it as a
    # group with its links; on a link, NULL follows its folder, 1 shows it anyway and 0 hides it. `rev` / `created_rev`
    # are the store's revision (prt_settings bookmarks_rev) when the row last changed and when it was made.
    # `owner` is the account (ios_users.id) whose bookmark it is; `shared` 1: everyone sees it, and only an admin of
    # the start page changes it (iostart/bookmarks/__init__.py has the rules).
    """CREATE TABLE IF NOT EXISTS prt_bookmark_nodes (
        id INT PRIMARY KEY,
        parent_id INT NULL,
        folder TINYINT(1) NOT NULL DEFAULT 0,
        name VARCHAR(1024) NOT NULL,
        url TEXT NULL,
        abbr VARCHAR(8) NULL,
        description VARCHAR(512) NULL,
        icon VARCHAR(1024) NULL,
        tags TEXT NULL,
        start TINYINT(1) NULL,
        position INT NOT NULL DEFAULT 0,
        rev BIGINT NOT NULL DEFAULT 0,
        created_rev BIGINT NOT NULL DEFAULT 0,
        owner INT NULL,
        shared TINYINT(1) NOT NULL DEFAULT 0,
        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
        KEY idx_prt_bookmark_nodes_parent_position (parent_id, position),
        KEY idx_prt_bookmark_nodes_owner (owner, shared),
        FOREIGN KEY (parent_id) REFERENCES prt_bookmark_nodes(id) ON DELETE CASCADE
    )""",
    # an SVG uploaded for a bookmark (the Bookmarks page), served by the page itself: it wins over the icon field
    """CREATE TABLE IF NOT EXISTS prt_bookmark_node_icons (
        node_id INT PRIMARY KEY,
        svg MEDIUMTEXT NOT NULL,
        etag CHAR(16) NOT NULL,
        FOREIGN KEY (node_id) REFERENCES prt_bookmark_nodes(id) ON DELETE CASCADE
    )""",
    # a person's own choice of whether a shared folder or link is on their start page (the house, for someone who is
    # not an admin): `start` as in prt_bookmark_nodes, and it wins over the node's own for that account
    """CREATE TABLE IF NOT EXISTS prt_bookmark_starts (
        user_id INT NOT NULL,
        node_id INT NOT NULL,
        start TINYINT(1) NULL,
        PRIMARY KEY (user_id, node_id),
        FOREIGN KEY (node_id) REFERENCES prt_bookmark_nodes(id) ON DELETE CASCADE
    )""",
    # a bookmarked site's own icon (iostart/bookmarks/icons.py), one per scheme://host[:port]: what a link without an icon of
    # its own shows. data NULL: looked for, none found
    """CREATE TABLE IF NOT EXISTS prt_site_icons (
        site VARCHAR(255) PRIMARY KEY,
        data MEDIUMBLOB NULL,
        mime VARCHAR(32) NULL,
        etag CHAR(16) NULL,
        fetched_at DATETIME NOT NULL
    )""",
    # the TRMNL e-ink devices that ask this server what to show (iostart/trmnl/server.py), by MAC address. `code` is what a
    # device nobody took yet shows on its screen; `owner` (ios_users.id) the person who typed it in Settings › TRMNL,
    # whose screens it shows. settings: {playlist, refresh, bits}; state: what the device last said about itself and
    # what it was last sent. Its key is not here: with the suite's keys and tokens (trmnl_device_<id>).
    """CREATE TABLE IF NOT EXISTS prt_trmnl_devices (
        id INT AUTO_INCREMENT PRIMARY KEY,
        mac CHAR(17) NOT NULL,
        code CHAR(6) NOT NULL,
        owner INT NULL,
        name VARCHAR(60) NOT NULL DEFAULT '',
        model VARCHAR(40) NOT NULL DEFAULT '',
        width INT NOT NULL DEFAULT 800,
        height INT NOT NULL DEFAULT 480,
        settings MEDIUMTEXT NOT NULL,
        state MEDIUMTEXT NOT NULL,
        seen_at DOUBLE NOT NULL DEFAULT 0,
        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        UNIQUE KEY idx_prt_trmnl_devices_mac (mac),
        KEY idx_prt_trmnl_devices_owner (owner)
    )""",
    # kitchen timers started from the search box (iostart/timers.py): the whole family sees them, the page and the wall
    # count down, and `user_id` (who started it) gets a notification when it ends. ends_at: epoch seconds; notified 1:
    # the "done" notification went out. A timer is gone when somebody dismisses it, or a while after it ended.
    """CREATE TABLE IF NOT EXISTS prt_timers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        label VARCHAR(80) NOT NULL,
        seconds INT NOT NULL,
        ends_at DOUBLE NOT NULL,
        notified TINYINT(1) NOT NULL DEFAULT 0,
        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        KEY idx_prt_timers_ends (ends_at)
    )""",
]


def _tables() -> list:
    from iostart import news  # the reader's tables are written where they are explained (iostart/news/__init__.py)
    return SCHEMA + news.SCHEMA


# Where the database is, its pool, the transaction nested calls share, q / one / ex / many, the settings table and the
# tables made at start are the suite's (iosuite_shared.db.AppDatabase): a statement on its own is one round trip, tx()
# is one transaction (committed on success, rolled back on error), and q / one / ex inside a `with tx():` block run in it.
_db = shared_db.AppDatabase(config, PREFIX, _tables, SCHEMA_VERSION)
pool = _db.pool
connect, tx, q, one, ex, many = _db.connect, _db.tx, _db.q, _db.one, _db.ex, _db.many
get_setting, set_setting = _db.get_setting, _db.set_setting
ensure_database, migrate, reset_all = _db.ensure_database, _db.migrate, _db.reset_all


def counts() -> dict:
    """What is in the tables (`iosuite iostart check`)."""
    return {"bookmarks": one("SELECT count(*) AS n FROM prt_bookmark_nodes WHERE url IS NOT NULL")["n"],
            "feeds": one("SELECT count(*) AS n FROM prt_feeds")["n"],
            "screens": one("SELECT count(*) AS n FROM prt_trmnl_devices")["n"]}

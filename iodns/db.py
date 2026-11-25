"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""
from iodns import config

from iosuite_shared import db as shared_db

SCHEMA_VERSION = 1
PREFIX = "dns"

# Every table is dns_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
#
# The master list is a list of entries (a host name, with a note), each with records per view: a view is one answer
# to "who is asking" (Internal: the house; External: the internet; Tailscale: the tailnet), and each DNS server
# answers for one view. So calendar.example.com can be 192.168.1.151 inside, a public address outside and 100.x on
# the tailnet, and a name without an External record is never pushed to public DNS.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS dns_state (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    """CREATE TABLE IF NOT EXISTS dns_views (
        id INT AUTO_INCREMENT PRIMARY KEY,
        slug VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        description VARCHAR(255) NULL,
        position INT NOT NULL DEFAULT 0,
        UNIQUE KEY uq_dns_views_slug (slug)
    )""",
    """CREATE TABLE IF NOT EXISTS dns_entries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(253) NOT NULL,
        comment VARCHAR(512) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        updated_by VARCHAR(64) NULL,
        UNIQUE KEY uq_dns_entries_name (name)
    )""",
    # source: where the value comes from when it is not typed in, "tailscale:<server id>:<device>" (the device's tailnet
    # address, read again before every sync); value then holds the address last read
    """CREATE TABLE IF NOT EXISTS dns_records (
        id INT AUTO_INCREMENT PRIMARY KEY,
        entry_id INT NOT NULL,
        view_id INT NOT NULL,
        type VARCHAR(8) NOT NULL,
        value VARCHAR(253) NOT NULL,
        ttl INT NULL,
        source VARCHAR(255) NULL,
        UNIQUE KEY uq_dns_records_entry_view_value (entry_id, view_id, type, value),
        KEY idx_dns_records_view (view_id),
        FOREIGN KEY (entry_id) REFERENCES dns_entries(id) ON DELETE CASCADE,
        FOREIGN KEY (view_id) REFERENCES dns_views(id) ON DELETE CASCADE
    )""",
    # a DNS server ioDNS keeps in sync (or reads from: Tailscale); its password or key is in the Shared ioSuite
    # database's keys and tokens (iosuite_shared.credentials, app iodns, name server_<id>), never here
    """CREATE TABLE IF NOT EXISTS dns_servers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        kind VARCHAR(32) NOT NULL,
        url VARCHAR(512) NOT NULL DEFAULT '',
        view_id INT NULL,
        options TEXT NULL,
        enabled TINYINT NOT NULL DEFAULT 1,
        position INT NOT NULL DEFAULT 0,
        checked_at TIMESTAMP NULL,
        check_ok TINYINT NULL,
        check_message VARCHAR(512) NULL,
        differences INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_dns_servers_view (view_id),
        FOREIGN KEY (view_id) REFERENCES dns_views(id) ON DELETE SET NULL
    )""",
    # what was changed where, and by whom: the master list's changes, pushes and imports
    """CREATE TABLE IF NOT EXISTS dns_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        user_name VARCHAR(64) NULL,
        action VARCHAR(32) NOT NULL,
        server_id INT NULL,
        server_name VARCHAR(64) NULL,
        detail TEXT NULL,
        ok TINYINT NOT NULL DEFAULT 1,
        KEY idx_dns_log_at (at)
    )""",
]

VIEWS = [("internal", "Internal", "The house: what the LAN's DNS servers answer", 0),
         ("external", "External", "The internet: public DNS (Cloudflare…)", 1),
         ("tailscale", "Tailscale", "The tailnet: the DNS server Tailscale's split DNS points at", 2)]


# Where the database is, its pool, the transaction nested calls share, q / one / ex / many, the settings table and the
# tables made at start are the suite's (iosuite_shared.db.AppDatabase): a statement on its own is one round trip, tx()
# is one transaction (committed on success, rolled back on error), and q / one / ex inside a `with tx():` block run in it.
_db = shared_db.AppDatabase(config, PREFIX, SCHEMA, SCHEMA_VERSION)
connect, tx, q, one, ex, many = _db.connect, _db.tx, _db.q, _db.one, _db.ex, _db.many
marks = shared_db.marks
get_state, set_state = _db.get_state, _db.set_state   # what the app wrote down for itself (<prefix>_state)
ensure_database, reset_all = _db.ensure_database, _db.reset_all


def _views(cur) -> None:
    """The views a new install starts with."""
    cur.execute("SELECT count(*) AS n FROM dns_views")
    if not cur.fetchone()["n"]:
        cur.executemany("INSERT INTO dns_views (slug, name, description, position) VALUES (%s, %s, %s, %s)", VIEWS)


def migrate() -> None:
    _db.migrate(after=_views)


def counts() -> dict:
    """What is in the tables (`iosuite iodns check`)."""
    return {"entries": one("SELECT count(*) AS n FROM dns_entries")["n"],
            "views": one("SELECT count(*) AS n FROM dns_views")["n"],
            "servers": one("SELECT count(*) AS n FROM dns_servers")["n"]}

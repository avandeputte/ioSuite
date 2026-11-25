"""MariaDB access: one short connection per unit of work, and the schema (created at start)."""

from iocalendar import config

from iosuite_shared import db as shared_db

SCHEMA_VERSION = 3  # recorded in cal_schema_version; the tables are made as SCHEMA says, and get the columns and indexes added to it later (schema.create)
PREFIX = "cal"

# Every table is cal_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4. An
# event is kept as the iCalendar object a client sent (or the web app made), so whatever a calendar app puts in it
# (alarms, attachments, its own X- properties, changed occurrences) comes back unchanged; the columns beside it are
# what the app searches and draws from, filled in whenever the object is saved.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS cal_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite_shared, iocalendar/auth.py)
    # owner_id NULL: a shared calendar (everyone sees it); kind 'birthdays' is filled from ioContact and read-only.
    # owner_key stands in for owner_id in the unique key: NULLs never clash in a unique key, so (owner_id, slug) alone
    # would let two shared calendars share a slug
    """CREATE TABLE IF NOT EXISTS cal_calendars (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        color VARCHAR(16) NULL,
        timezone VARCHAR(64) NULL,
        kind VARCHAR(16) NOT NULL DEFAULT 'events',
        position INT NOT NULL DEFAULT 0,
        sync_token BIGINT NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT,
        UNIQUE KEY uq_cal_calendars_owner_slug (owner_key, slug)
    )""",
    # dtstart / dtend / range_* are UTC (an all-day event: its dates at midnight UTC, all_day = 1). range_start is the
    # first occurrence's start, range_end the last one's end (NULL: repeats for ever): what a time-range query needs.
    """CREATE TABLE IF NOT EXISTS cal_events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        calendar_id INT NOT NULL,
        uid VARCHAR(255) NOT NULL,
        href VARCHAR(255) NOT NULL,
        summary VARCHAR(512) NOT NULL DEFAULT '',
        location VARCHAR(1024) NULL,
        description TEXT NULL,
        all_day TINYINT NOT NULL DEFAULT 0,
        dtstart DATETIME NULL,
        dtend DATETIME NULL,
        tzid VARCHAR(64) NULL,
        rrule VARCHAR(1024) NULL,
        status VARCHAR(16) NULL,
        range_start DATETIME NULL,
        range_end DATETIME NULL,
        ics MEDIUMTEXT NOT NULL,
        etag VARCHAR(64) NOT NULL,
        changed_token BIGINT NOT NULL DEFAULT 0,
        deleted TINYINT NOT NULL DEFAULT 0,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_cal_events_calendar_href (calendar_id, href),
        KEY idx_cal_events_calendar_uid (calendar_id, uid),
        KEY idx_cal_events_calendar_changes (calendar_id, deleted, changed_token),
        KEY idx_cal_events_calendar_range (calendar_id, deleted, range_start),
        FOREIGN KEY (calendar_id) REFERENCES cal_calendars(id) ON DELETE CASCADE
    )""",
    # the people on an event (ATTENDEE, and ORGANIZER with role 'organizer'), for search and "what is X doing";
    # contact_id is the ioContact contact the web app picked them from
    """CREATE TABLE IF NOT EXISTS cal_event_people (
        id INT AUTO_INCREMENT PRIMARY KEY, event_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        name VARCHAR(255) NULL, email VARCHAR(255) NULL, contact_id INT NULL, role VARCHAR(16) NULL,
        KEY idx_cal_event_people_event (event_id), KEY idx_cal_event_people_email (email), KEY idx_cal_event_people_contact (contact_id),
        FOREIGN KEY (event_id) REFERENCES cal_events(id) ON DELETE CASCADE)""",
    # an outside calendar subscribed to by its web address (a calendar of kind 'subscribed', iocalendar/subscribe.py): where it
    # is fetched from, how often, and how the last fetch went (UTC); etag / last_modified ask the server "changed since?"
    """CREATE TABLE IF NOT EXISTS cal_subscriptions (
        calendar_id INT PRIMARY KEY,
        url VARCHAR(2048) NOT NULL,
        refresh_hours SMALLINT NOT NULL DEFAULT 6,
        etag VARCHAR(255) NULL,
        last_modified VARCHAR(64) NULL,
        checked_at DATETIME NULL,
        synced_at DATETIME NULL,
        error VARCHAR(512) NULL,
        events INT NULL,
        created_by INT NULL,
        FOREIGN KEY (calendar_id) REFERENCES cal_calendars(id) ON DELETE CASCADE)""",
]


# Where the database is, its pool, the transaction nested calls share, q / one / ex / many, the settings table and the
# tables made at start are the suite's (iosuite_shared.db.AppDatabase): a statement on its own is one round trip, tx()
# is one transaction (committed on success, rolled back on error), and q / one / ex inside a `with tx():` block run in it.
_db = shared_db.AppDatabase(config, PREFIX, SCHEMA, SCHEMA_VERSION)
pool = _db.pool
connect, tx, q, one, ex, many = _db.connect, _db.tx, _db.q, _db.one, _db.ex, _db.many
marks = shared_db.marks
get_setting, set_setting = _db.get_setting, _db.set_setting
schema_version, ensure_database, reset_all = _db.schema_version, _db.ensure_database, _db.reset_all


def _family_calendar(cur) -> None:
    """The family calendar everyone shares."""
    cur.execute("SELECT id FROM cal_calendars WHERE owner_id IS NULL AND kind = 'events' LIMIT 1")
    if not cur.fetchone():
        cur.execute("INSERT INTO cal_calendars (owner_id, slug, name, description, color) VALUES "
                    "(NULL, 'family', 'Family', 'Shared with everyone in the family', '#8e44d6')")


def migrate() -> None:
    _db.migrate(after=_family_calendar)


def counts() -> dict:
    """What is in the tables (`iosuite iocalendar check`, and the app's diagnostics tool)."""
    return {"calendars": one("SELECT count(*) AS n FROM cal_calendars")["n"],
            "events": one("SELECT count(*) AS n FROM cal_events WHERE deleted = 0")["n"],
            "tombstones": one("SELECT count(*) AS n FROM cal_events WHERE deleted = 1")["n"]}

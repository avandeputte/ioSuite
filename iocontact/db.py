"""MariaDB access (a pool of connections, iosuite_shared.db.Database) and the schema (created and migrated at start)."""

from iocontact import config

from iosuite_shared import db as shared_db

SCHEMA_VERSION = 6  # recorded in con_schema_version; the tables are made as SCHEMA says, and get the columns and indexes added to it later (schema.create)
PREFIX = "con"

# Every table is con_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4. Child rows (emails, phones...) are replaced as a whole when a contact is saved.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS con_state (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite_shared)
    # owner_id NULL: a shared address book. owner_key stands in for owner_id in the unique key: NULLs never clash in a
    # unique key, so (owner_id, slug) alone would let two shared address books share a slug
    """CREATE TABLE IF NOT EXISTS con_address_books (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        color VARCHAR(16) NULL,
        sync_token BIGINT NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT,
        UNIQUE KEY uq_con_address_books_owner_slug (owner_key, slug)
    )""",
    """CREATE TABLE IF NOT EXISTS con_contacts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        address_book_id INT NOT NULL,
        uid VARCHAR(255) NOT NULL,
        href VARCHAR(255) NOT NULL,
        kind ENUM('individual','org','group') NOT NULL DEFAULT 'individual',
        fn VARCHAR(255) NOT NULL DEFAULT '',
        prefix VARCHAR(64) NULL,
        given VARCHAR(128) NULL,
        additional VARCHAR(128) NULL,
        family VARCHAR(128) NULL,
        suffix VARCHAR(64) NULL,
        nickname VARCHAR(128) NULL,
        maiden VARCHAR(128) NULL,
        phonetic_given VARCHAR(128) NULL,
        phonetic_family VARCHAR(128) NULL,
        gender CHAR(1) NULL,
        bday_year SMALLINT NULL,
        bday_month TINYINT NULL,
        bday_day TINYINT NULL,
        bday_remind TINYINT NOT NULL DEFAULT 1,
        org VARCHAR(255) NULL,
        department VARCHAR(255) NULL,
        title VARCHAR(255) NULL,
        role VARCHAR(255) NULL,
        notes TEXT NULL,
        favorite TINYINT NOT NULL DEFAULT 0,
        iopix_person_id INT NULL,
        iopix_person_name VARCHAR(255) NULL,
        extra MEDIUMTEXT NULL,
        etag VARCHAR(64) NOT NULL,
        changed_token BIGINT NOT NULL DEFAULT 0,
        deleted TINYINT NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_con_contacts_book_href (address_book_id, href),
        KEY idx_con_contacts_book_uid (address_book_id, uid),
        KEY idx_con_contacts_book_changes (address_book_id, deleted, changed_token),
        KEY idx_con_contacts_fn (fn),
        KEY idx_con_contacts_iopix_person (iopix_person_id),
        FOREIGN KEY (address_book_id) REFERENCES con_address_books(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS con_contact_emails (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(255) NOT NULL, pref TINYINT NOT NULL DEFAULT 0,
        KEY idx_con_contact_emails_contact (contact_id), KEY idx_con_contact_emails_value (value), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_phones (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(64) NOT NULL, pref TINYINT NOT NULL DEFAULT 0,
        KEY idx_con_contact_phones_contact (contact_id), KEY idx_con_contact_phones_value (value), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_addresses (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, pobox VARCHAR(64) NULL, ext VARCHAR(128) NULL, street VARCHAR(255) NULL,
        city VARCHAR(128) NULL, region VARCHAR(128) NULL, postcode VARCHAR(32) NULL, country VARCHAR(128) NULL,
        pref TINYINT NOT NULL DEFAULT 0,
        KEY idx_con_contact_addresses_contact (contact_id), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_urls (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(512) NOT NULL,
        KEY idx_con_contact_urls_contact (contact_id), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_social_profiles (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        service VARCHAR(64) NOT NULL, value VARCHAR(512) NOT NULL,
        KEY idx_con_contact_social_profiles_contact (contact_id), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_dates (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NOT NULL, year SMALLINT NULL, month TINYINT NOT NULL, day TINYINT NOT NULL,
        KEY idx_con_contact_dates_contact (contact_id), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_tags (
        contact_id INT NOT NULL, tag VARCHAR(128) NOT NULL, PRIMARY KEY (contact_id, tag), KEY idx_con_contact_tags_tag (tag),
        FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    # relations are directed: "contact_id's <type> is related_id" (Ann's sibling is Bob). The inverse row
    # (Bob's sibling is Ann) is kept by the model. related_name holds a person who is not a contact.
    """CREATE TABLE IF NOT EXISTS con_contact_relations (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        type VARCHAR(32) NOT NULL, related_id INT NULL, related_name VARCHAR(255) NULL, label VARCHAR(64) NULL,
        KEY idx_con_contact_relations_contact (contact_id), KEY idx_con_contact_relations_related (related_id),
        FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE,
        FOREIGN KEY (related_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    # two contacts someone said are different people: never offered as duplicates again (contact_id < other_contact_id)
    """CREATE TABLE IF NOT EXISTS con_contact_non_duplicates (
        contact_id INT NOT NULL, other_contact_id INT NOT NULL, user_id INT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (contact_id, other_contact_id))""",
    # every merge, with the rows of the contacts as they were before, so it can be undone
    """CREATE TABLE IF NOT EXISTS con_contact_merges (
        id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NULL, kept_contact_id INT NOT NULL, other_ids VARCHAR(512) NOT NULL,
        names VARCHAR(1024) NULL, snapshot LONGTEXT NOT NULL, keep_etag VARCHAR(64) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, undone_at TIMESTAMP NULL, KEY idx_con_contact_merges_kept (kept_contact_id))""",
    # enrichment: what a lookup (Gravatar, GitHub...) or an assistant over MCP found, waiting for a person to accept it
    """CREATE TABLE IF NOT EXISTS con_contact_suggestions (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, field VARCHAR(32) NOT NULL, value MEDIUMTEXT NOT NULL,
        vkey VARCHAR(255) NOT NULL, source VARCHAR(64) NOT NULL, evidence VARCHAR(1024) NULL, note VARCHAR(1024) NULL,
        status ENUM('pending','accepted','dismissed') NOT NULL DEFAULT 'pending', created_by INT NULL, decided_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, decided_at TIMESTAMP NULL,
        KEY idx_con_contact_suggestions_contact_status (contact_id, status), UNIQUE KEY uq_con_contact_suggestions_value (contact_id, field, vkey),
        FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
]


# Where the database is, its pool, the transaction nested calls share, q / one / ex / many, the settings table and the
# tables made at start are the suite's (iosuite_shared.db.AppDatabase): a statement on its own is one round trip, tx()
# is one transaction (committed on success, rolled back on error), and q / one / ex inside a `with tx():` block run in it.
_db = shared_db.AppDatabase(config, PREFIX, SCHEMA, SCHEMA_VERSION)
pool = _db.pool
connect, tx, q, one, ex, many = _db.connect, _db.tx, _db.q, _db.one, _db.ex, _db.many
get_state, set_state = _db.get_state, _db.set_state   # what the app wrote down for itself (<prefix>_state)
schema_version, ensure_database, reset_all = _db.schema_version, _db.ensure_database, _db.reset_all


_collation: str | None = None


def search_collation() -> str:
    """The most forgiving utf8mb4 collation the server has, for searches: case- and accent-insensitive, so "celia"
    matches "Célia" whatever collation the tables were created with (uca1400 on MariaDB 10.10+, which also folds
    ø, ł and đ; unicode_520 before it)."""
    global _collation
    if _collation is None:
        have = {r["Collation"] for r in q("SHOW COLLATION WHERE Collation IN "
                                           "('utf8mb4_uca1400_ai_ci', 'utf8mb4_unicode_520_ci')")}
        _collation = next((c for c in ("utf8mb4_uca1400_ai_ci", "utf8mb4_unicode_520_ci") if c in have),
                          "utf8mb4_unicode_ci")
    return _collation


def _family_book(cur) -> None:
    """The family address book everyone shares."""
    cur.execute("SELECT id FROM con_address_books WHERE owner_id IS NULL LIMIT 1")
    if not cur.fetchone():
        cur.execute("INSERT INTO con_address_books (owner_id, slug, name, description) VALUES "
                    "(NULL, 'family', 'Family', 'Shared with everyone in the family')")


def migrate() -> None:
    _db.migrate(after=_family_book)


def counts() -> dict:
    """What is in the tables (`iosuite iocontact check`, and the app's diagnostics tool)."""
    return {"contacts": one("SELECT count(*) AS n FROM con_contacts WHERE deleted = 0")["n"],
            "tombstones": one("SELECT count(*) AS n FROM con_contacts WHERE deleted = 1")["n"],
            "relations": one("SELECT count(*) AS n FROM con_contact_relations")["n"],
            "addressBooks": one("SELECT count(*) AS n FROM con_address_books")["n"]}

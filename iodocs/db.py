"""MariaDB access: one short connection per unit of work, and the schema (created at start)."""

from iodocs import config

from iosuite_shared import db as shared_db

SCHEMA_VERSION = 1  # recorded in doc_schema_version; the tables are made as SCHEMA says, and get the columns and indexes added to it later (schema.create)
PREFIX = "doc"

# Every table is doc_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
# Who sees which document is iodocs/model.py's (visible_sql): each one says who may see it.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS doc_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite_shared, iodocs/auth.py)
    # a document: a passport, a driver's license, an insurance policy, a birth certificate... kind: one of
    # model.KINDS. number: the passport's or the policy's number; issuer: who gave it (a country's passport office, a
    # state's DMV, an insurer); country: a country code (US, BE) or name. Dates are days. remind_days: how many days
    # before expires_on a reminder goes (NULL: the kind's usual, 0: none). visibility: family (everyone with a role
    # here), people (the people it is for, whoever added it, editors and admins) or private (the people it is for and
    # whoever added it, nobody else). fields: its own details as a JSON list of {name, value} (nationality, class,
    # coverage...). cover: the id in doc_files of the picture the cards show (0: none). words: everything a search looks
    # in, the text read off its scans too, in lower case. renewed_by: the document that took its place.
    """CREATE TABLE IF NOT EXISTS doc_documents (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        kind VARCHAR(24) NOT NULL,
        number VARCHAR(191) NULL,
        issuer VARCHAR(255) NULL,
        country VARCHAR(64) NULL,
        issued_on DATE NULL,
        expires_on DATE NULL,
        remind_days INT NULL,
        visibility VARCHAR(8) NOT NULL DEFAULT 'people',
        archived TINYINT(1) NOT NULL DEFAULT 0,
        renewed_by INT NULL,
        notes MEDIUMTEXT NULL,
        fields MEDIUMTEXT NOT NULL,
        cover INT NOT NULL DEFAULT 0,
        words MEDIUMTEXT NOT NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_doc_documents_expires (archived, expires_on),
        KEY idx_doc_documents_kind (kind),
        KEY idx_doc_documents_by (created_by)
    )""",
    # whose a document is: the people of the family (the suite's one list, iosuite_shared.family). user_id is the
    # account in the Shared ioSuite database.
    """CREATE TABLE IF NOT EXISTS doc_people (
        doc_id INT NOT NULL,
        user_id INT NOT NULL,
        PRIMARY KEY (doc_id, user_id),
        KEY idx_doc_people_user (user_id),
        CONSTRAINT fk_doc_people_doc FOREIGN KEY (doc_id) REFERENCES doc_documents(id) ON DELETE CASCADE
    )""",
    # its scans and files: the front, the back, the pages of a policy. The bytes are in doc_file_parts, in parts of
    # PART_BYTES; thumb: a small JPEG of a picture (or of a PDF's first page). text: what OCR read off it (iodocs/ocr.py);
    # found: what was made of that, as JSON ({kind, number, expiresOn, ...}); read_at: when it was read (NULL: not yet).
    """CREATE TABLE IF NOT EXISTS doc_files (
        id INT AUTO_INCREMENT PRIMARY KEY,
        doc_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        mime VARCHAR(127) NOT NULL,
        size BIGINT NOT NULL,
        sha256 CHAR(64) NOT NULL,
        thumb MEDIUMBLOB NULL,
        position INT NOT NULL DEFAULT 0,
        text MEDIUMTEXT NULL,
        found MEDIUMTEXT NULL,
        read_at TIMESTAMP NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_doc_files_doc (doc_id, position),
        CONSTRAINT fk_doc_files_doc FOREIGN KEY (doc_id) REFERENCES doc_documents(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS doc_file_parts (
        file_id INT NOT NULL,
        n INT NOT NULL,
        data MEDIUMBLOB NOT NULL,
        PRIMARY KEY (file_id, n),
        CONSTRAINT fk_doc_file_parts_file FOREIGN KEY (file_id) REFERENCES doc_files(id) ON DELETE CASCADE
    )""",
]


# Where the database is, its pool, the transaction nested calls share, q / one / ex / many, the settings table and the
# tables made at start are the suite's (iosuite_shared.db.AppDatabase): a statement on its own is one round trip, tx()
# is one transaction (committed on success, rolled back on error), and q / one / ex inside a `with tx():` block run in it.
_db = shared_db.AppDatabase(config, PREFIX, SCHEMA, SCHEMA_VERSION)
connect, tx, q, one, ex, many = _db.connect, _db.tx, _db.q, _db.one, _db.ex, _db.many
marks = shared_db.marks
get_setting, set_setting = _db.get_setting, _db.set_setting
schema_version, ensure_database, migrate, reset_all = _db.schema_version, _db.ensure_database, _db.migrate, _db.reset_all

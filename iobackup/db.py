"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""

from iobackup import config

from iosuite_shared import db as shared_db

SCHEMA_VERSION = 1
PREFIX = "bkp"

# Every table is bkp_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
# Passwords and Google keys are never here: they are kept with the suite's keys and tokens (iosuite_shared.credentials,
# app iobackup: server_<id>_password, destination_<id>_client_secret / _refresh_token / _service_account).
SCHEMA = [
    # a MariaDB (or Galera node) to back up and restore onto: host and port, or a socket on this machine
    """CREATE TABLE IF NOT EXISTS bkp_servers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        host VARCHAR(253) NOT NULL DEFAULT '',
        port INT NULL,
        socket VARCHAR(255) NOT NULL DEFAULT '',
        user_name VARCHAR(80) NOT NULL DEFAULT '',
        tls TINYINT NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bkp_servers_name (name)
    )""",
    # where backups are kept: kind local (options: path) or gdrive (options: auth, folder_name, folder_id, client_id,
    # account)
    """CREATE TABLE IF NOT EXISTS bkp_destinations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        options TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bkp_destinations_name (name)
    )""",
    # what to back up, where, when and how many to keep. databases: a JSON list, or "all"; schedule: the form's
    # fields as JSON, cron: the five-field expression it makes ('' for on demand only); export_files: also write the
    # files the apps keep in their databases out as plain files in the backup (iobackup/blobfiles.py)
    """CREATE TABLE IF NOT EXISTS bkp_jobs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        server_id INT NOT NULL,
        destination_id INT NOT NULL,
        databases_json TEXT NOT NULL,
        include_users TINYINT NOT NULL DEFAULT 1,
        keep_count INT NOT NULL DEFAULT 7,
        schedule_json TEXT NOT NULL,
        cron VARCHAR(128) NOT NULL DEFAULT '',
        enabled TINYINT NOT NULL DEFAULT 1,
        desync TINYINT NOT NULL DEFAULT 0,
        lock_all TINYINT NOT NULL DEFAULT 0,
        compress_level TINYINT NOT NULL DEFAULT 6,
        export_files TINYINT NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bkp_jobs_name (name),
        KEY idx_bkp_jobs_server (server_id),
        KEY idx_bkp_jobs_destination (destination_id),
        FOREIGN KEY (server_id) REFERENCES bkp_servers(id),
        FOREIGN KEY (destination_id) REFERENCES bkp_destinations(id)
    )""",
    # every backup and restore, with its log: kind backup or restore; status queued, running, ok, failed, cancelled;
    # trigger_kind schedule or manual; payload what to do (JSON), result what came of it (JSON)
    """CREATE TABLE IF NOT EXISTS bkp_runs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        kind VARCHAR(16) NOT NULL,
        title VARCHAR(255) NOT NULL,
        job_id INT NULL,
        trigger_kind VARCHAR(16) NOT NULL DEFAULT 'manual',
        user_name VARCHAR(64) NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        queued_at DATETIME NOT NULL,
        started_at DATETIME NULL,
        finished_at DATETIME NULL,
        payload TEXT NULL,
        result TEXT NULL,
        log MEDIUMTEXT NOT NULL,
        KEY idx_bkp_runs_job (job_id),
        KEY idx_bkp_runs_status (status)
    )""",
]


# Where the database is, its pool, the transaction nested calls share, q / one / ex / many, the settings table and the
# tables made at start are the suite's (iosuite_shared.db.AppDatabase): a statement on its own is one round trip, tx()
# is one transaction (committed on success, rolled back on error), and q / one / ex inside a `with tx():` block run in it.
_db = shared_db.AppDatabase(config, PREFIX, SCHEMA, SCHEMA_VERSION)
connect, tx, q, one, ex, many = _db.connect, _db.tx, _db.q, _db.one, _db.ex, _db.many
marks = shared_db.marks
ensure_database, migrate, reset_all = _db.ensure_database, _db.migrate, _db.reset_all


def counts() -> dict:
    """What is in the tables (`iosuite iobackup check`)."""
    return {"servers": one("SELECT count(*) AS n FROM bkp_servers")["n"],
            "destinations": one("SELECT count(*) AS n FROM bkp_destinations")["n"],
            "jobs": one("SELECT count(*) AS n FROM bkp_jobs")["n"]}

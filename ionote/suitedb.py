"""The Shared ioSuite database: the MariaDB database the suite's apps share (accounts, sessions, roles, the suite's
list of apps, every stored setting), named in the machine's file (IOSUITE_DB_*) and read by iosuite_shared itself.
"""
from iosuite_shared import config


def public() -> dict:
    """Where the Shared ioSuite database is (no password), for the startup log line."""
    return {"host": config.DB_HOST, "port": config.DB_PORT, "database": config.DB_NAME, "user": config.DB_USER}

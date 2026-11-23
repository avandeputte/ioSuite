"""ioBackup: the application (what is its own: its tables and jobs, its routes; the rest is every app's:
iosuite_shared.application).

Who may call a route is declared on the route (iobackup/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from iosuite_shared import application, users as shared_users

from iobackup import __version__, api, config, db, engine, gdrive, model, tasks
from iobackup.auth import auth, updater


def _jobs() -> list:
    if config.env_flag("BACKGROUND", True):
        tasks.start()  # the queued backups and restores and the scheduler, as two of the copy's jobs
    return []          # they leave the runner with tasks.stop


app = application.create(
    auth, updater, __version__, config,
    description="Backups of MariaDB and Galera servers, on demand or on a schedule, to a local folder or Google Drive, "
                "keeping the newest N, and a restore of exactly the databases, tables and users picked.",
    prepare=(db.migrate, shared_users.init), jobs=_jobs, stop=(tasks.stop,),
    limit_for=lambda path, ctype: config.MAX_JSON_BYTES, not_found=(model.NotFound,),
    related=False, routers=(api.router,))


@app.exception_handler(engine.EngineError)
async def engine_error(request: Request, e: engine.EngineError):
    """A dump, a restore or a backup file that went wrong (the server refused, a checksum differs): 400, with why."""
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(gdrive.DriveError)
async def drive_error(request: Request, e: gdrive.DriveError):
    """Google Drive answered with an error or could not be reached: 502, with what it said."""
    return JSONResponse({"detail": str(e)}, status_code=502)

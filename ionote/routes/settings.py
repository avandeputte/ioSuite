"""Settings: the switches admins set, the change log, export and import. Sign-in at a proxy is set for the whole suite (Settings › Security, suite admins: iosuite_shared's routers). The status, the version, updates, restart and the server log are iosuite_shared's routers (/api/status,
/api/server, /api/log), mounted in ionote/main.py."""
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from iosuite_shared import users
from starlette.concurrency import run_in_threadpool

from ionote import access, backup, config, notes
from iosuite_shared.http import attachment, user_name

router = APIRouter()
# the app's own settings live in the suite's one home for them (the Shared ioSuite database, declared in ionote's
# app.json); the MCP switch is the suite's too: Settings › Apps (iosuite_shared.mcp.set_for)


@router.get("/api/settings", dependencies=[access.public])
def api_settings(request: Request):
    return {"app_name": config.live("APP_NAME", "ioNote"), "require_login": users.require_login(config.APP),
            "colors": list(notes.COLORS)}


# ---- the change log, export and import
@router.get("/api/changes", dependencies=[access.member])
def api_changes(limit: int = 200, before: int = None):
    """The change log: who created, edited, deleted or recoloured what, newest first."""
    return {"changes": notes.change_log(limit, before)}


@router.get("/api/export.zip", dependencies=[access.signed_in])
async def api_export(trash: int = 0, pictures: int = 1):
    f = await run_in_threadpool(backup.export_zip, bool(trash), bool(pictures))
    return StreamingResponse(backup.pieces(f), media_type="application/zip", headers=attachment(time.strftime("ionote-export-%Y%m%d-%H%M.zip")))


@router.post("/api/import", dependencies=[access.member_write])
async def api_import(request: Request, file: UploadFile = File(...)):
    try:  # the upload is a temporary file (on disk once large): read from there, not into memory
        return await run_in_threadpool(backup.import_zip, file.file, user_name(request))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"Could not import: {e}")

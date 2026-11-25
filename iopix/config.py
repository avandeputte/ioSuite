"""Settings: ioPix's own are kept in the Shared ioSuite database and read once, as it starts (Settings › Apps › All
settings changes them; app.json lists them). The settings every app of the suite shares come from
iosuite_shared.config.standard.

Everything this app writes on its own (index, caches, state, models, backups)
lives under DATA_DIR, inside the app's own folder by default. The library is
only ever read, except for the explicit edits the owner asks for (sidecars,
image files when enabled, digiKam's database while digiKam is closed), which
are backed up first; EDITING=0 and DB_WRITE=0 switch them off.
"""
import os
from pathlib import Path

from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
env, env_flag, env_int = _own["env"], _own["env_flag"], _own["env_int"]
DATA_DIR = _own["DATA_DIR"]
DB_HOST, DB_PORT, DB_NAME = _own["DB_HOST"], _own["DB_PORT"], _own["DB_NAME"]
DB_USER, DB_PASSWORD = _own["DB_USER"], _own["DB_PASSWORD"]


def _path(name: str, default: Path) -> Path:
    return Path(env(name, str(default))).expanduser().resolve()


# With nothing stored, ioPix starts on a library of its own: no digiKam, the photos in a folder beside the data folders
# (<the machine's DATA_DIR>/photos, made when missing). Settings › Apps › All settings (or the installer's
# question) names the real ones.
DIGIKAM_DB_DIR = _path("DIGIKAM_DB_DIR", shared.DATA_DIR / "digikam")
DIGIKAM_DB = DIGIKAM_DB_DIR / "digikam4.db"
# Used when the library has a single album root; otherwise digiKam's own
# per-root paths are used.
PHOTOS_ROOT = _path("PHOTOS_ROOT", shared.DATA_DIR / "photos")
if not env("PHOTOS_ROOT"):
    PHOTOS_ROOT.mkdir(parents=True, exist_ok=True)

INDEX_DB = DATA_DIR / "index.db"
CACHE_DIR = DATA_DIR / "cache"

# Grid thumbnails: fixed height, width follows the aspect ratio up to a cap.
THUMB_HEIGHT = env_int("THUMB_HEIGHT", 360)
THUMB_MAX_WIDTH = env_int("THUMB_MAX_WIDTH", 1080)
THUMB_QUALITY = env_int("THUMB_QUALITY", 76)
# Lightbox previews: longest edge.
PREVIEW_SIZE = env_int("PREVIEW_SIZE", 2560)
PREVIEW_QUALITY = env_int("PREVIEW_QUALITY", 86)
# Previews are only made for photos you open; the oldest are pruned at startup and
# every few hours once the folder grows past this many megabytes.
PREVIEW_CACHE_MAX_MB = env_int("PREVIEW_CACHE_MAX_MB", 8000)
# The cropped and small copies of thumbnails and the chapter frames of videos (cache/c, cache/s, cache/vf) are
# made on request, in a fixed set of shapes and sizes; together they are pruned the same way past this size.
VARIANT_CACHE_MAX_MB = env_int("VARIANT_CACHE_MAX_MB", 2000)

# Build all grid thumbnails in the background after startup.
PREWARM = env_flag("PREWARM", True)
# cores the one running background job may use (Settings can change it); half the machine by default
def cpu_count() -> int:
    """The cores this process may use: the container's share under Docker/LXC, not the host's count."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return os.cpu_count() or 4


BG_THREADS = env_int("BG_THREADS", max(1, cpu_count() // 2))
PREWARM_WORKERS = env_int("PREWARM_WORKERS", 0) or None  # None: BG_THREADS

# The AI analysis jobs run in a process of their own (iopix/jobproc.py), so a model that needs more memory than the
# server has takes that process down, not the web app. JOBS_PROCESS=0 runs them inside the web app, as before 1.147.
JOBS_PROCESS = env_flag("JOBS_PROCESS", True)
# The most memory that job process may hold, and the free memory the server keeps (megabytes). Unset: a share of the
# memory limit of the container or the machine (iopix/memwatch.py: 60% and 8%). 0 turns the one off.
JOBS_MEMORY_MB = env_int("JOBS_MEMORY_MB", -1)
MEMORY_RESERVE_MB = env_int("MEMORY_RESERVE_MB", -1)

# How often to check whether digiKam changed its database (seconds).
REINDEX_POLL = env_int("REINDEX_POLL", 20)
# After a change to a few photos (an edit here, a face named, edits applied to digiKam), only their rows of the search
# index are rewritten, in place; a full rebuild follows once things have been quiet for a while. INDEX_PATCH=0
# rebuilds the whole index at every change, as before 1.148.
INDEX_PATCH = env_flag("INDEX_PATCH", True)

for _d in (DATA_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
for _p in (DIGIKAM_DB_DIR, PHOTOS_ROOT):
    if DATA_DIR == _p or _p in DATA_DIR.parents:
        raise SystemExit(f"DATA_DIR ({DATA_DIR}) must not be inside the read-only library folder {_p}")
# AUTO_MODELS: models to download on first start when missing, e.g. "siglip2,yolox,geonames"
# (keys as in ai/models.py). The installer sets it for the features chosen.
AUTO_MODELS = [k.strip() for k in env("AUTO_MODELS").split(",") if k.strip()]
# Allow metadata edits (XMP sidecars; image files too when the write_files setting is on).
EDITING = env_flag("EDITING", True)
# Allow "Apply to digiKam database" (only ever runs on request, and only while digiKam is closed).
DB_WRITE = env_flag("DB_WRITE", True)
SEMANTIC = env_flag("SEMANTIC", True)
ANALYSIS = env_flag("ANALYSIS", True)
# Threads for sharpness scoring and object detection; by default the shared BG_THREADS budget.
ANALYSIS_WORKERS = env_int("ANALYSIS_WORKERS", 0) or None  # None: BG_THREADS
# How to tell whether digiKam is running before writing its database: "pgrep" looks for the
# process on this machine; "none" (Docker, a container, digiKam on another machine: it cannot be
# seen) does not check.
DIGIKAM_CHECK = env("DIGIKAM_CHECK", "pgrep").strip().lower()
# Describe every photo in a sentence with a local captioning model (BLIP base), for search.
CAPTIONS = env_flag("CAPTIONS", True)


# Folders that sync tools, NAS systems and operating systems keep beside the photos: their contents (GoodSync's
# backup copies in _gsdata_/_saved_, a Synology's @eaDir thumbnails, recycle bins...) are not the library. iopix
# leaves them out of every listing, the index and its jobs, and its file scanner does not go into them; nothing in
# them is changed or deleted. Folders whose name starts with a dot are skipped as well.
SYSTEM_DIRS = frozenset({"_gsdata_", "@eaDir", "#recycle", "@Recycle", "@Recently-Snapshot", "#snapshot", "lost+found",
                         "$RECYCLE.BIN", "System Volume Information"})


def is_system_folder(rel: str) -> bool:
    """A library-relative folder path ("/2017/_gsdata_/_saved_") inside one of SYSTEM_DIRS or a dot folder."""
    return any(seg in SYSTEM_DIRS or seg.startswith(".") for seg in (rel or "").split("/") if seg)


# digiKam's database (dkdb.py): these are the starting point, Settings › digiKam database can override them (and holds
# the password of a MySQL one)
DIGIKAM_DB_TYPE = env("DIGIKAM_DB_TYPE", "none").lower()  # none (no digiKam at all: ioPix keeps the library itself), sqlite, or mysql
DIGIKAM_DB_HOST = env("DIGIKAM_DB_HOST", "127.0.0.1")
DIGIKAM_DB_PORT = env("DIGIKAM_DB_PORT", "3306")
DIGIKAM_DB_NAME = env("DIGIKAM_DB_NAME", "digikam")
DIGIKAM_DB_USER = env("DIGIKAM_DB_USER", "digikam")
# auto (a full copy before destructive operations) or skip (never)
DIGIKAM_DB_BACKUP = env("DIGIKAM_DB_BACKUP", "auto")
# a command that writes a full MySQL dump to stdout, used instead of mysqldump (e.g. through docker exec)
DIGIKAM_DB_DUMP = env("DIGIKAM_DB_DUMP").strip()
SCANNER_LOOP = env_flag("SCANNER_LOOP", True)  # SCANNER_LOOP=0 (the test suite): file scanner passes only on request
EXIFTOOL = env("EXIFTOOL") or None  # a particular exiftool binary; else the one on PATH or digiKam's bundled copy
SIDECAR_COMPAT = env_flag("SIDECAR_COMPAT", False)  # new sidecars are named photo.xmp (digiKam's "compatible file name" setting)
DIGIKAM_MYSQL_DATES = env("DIGIKAM_MYSQL_DATES").strip().lower()  # "utc" or "local" settles how a MySQL library stores its dates; empty: detected


def sidecar_compat_env() -> bool:
    """SIDECAR_COMPAT=1: new sidecars are named photo.xmp (digiKam's "compatible file name" setting)."""
    return bool(SIDECAR_COMPAT)


def mysql_dates_env() -> str:
    """DIGIKAM_MYSQL_DATES: "utc" or "local" settles how a MySQL library stores its dates; empty: detected."""
    return DIGIKAM_MYSQL_DATES


def own_db() -> dict:
    """ioPix's own database: beside the Shared ioSuite database, under the same login (DB_NAME names another than iopix)."""
    return {"host": DB_HOST, "port": DB_PORT, "database": DB_NAME, "user": DB_USER, "password": DB_PASSWORD}

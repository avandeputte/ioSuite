"""What ioPix's job queue may use of this server's memory (jobs.py, jobproc.py ask before a job starts and while one
runs, so a job is stopped by the app, with a message, before the kernel has to choose).

The numbers themselves are read by the suite (iosuite_shared.memory: the limit, what is in use, what a process and
its children hold); here are the two settings ioPix applies to them:

- budget(): the numbers the queue acts on, with config.MEMORY_RESERVE_MB and JOBS_MEMORY_MB applied.
"""
from iosuite_shared.memory import MB, gb, limit, tree, used

from iopix import config

__all__ = ["MB", "budget", "gb", "limit", "tree", "used"]
RESERVE_SHARE, RESERVE_MIN = 0.08, 256 * MB   # free memory the queue keeps: 8% of the limit, at least 256 MB
CEILING_SHARE = 0.6                             # what the job process itself may hold: 60% of the limit


def budget() -> dict:
    """{limit, used, free, reserve, ceiling} in bytes; all None where memory cannot be read (nothing is limited then).
    reserve: the free memory below which no job starts and the job process is stopped. ceiling: the most the job
    process may hold itself. Both are a share of the limit unless set (MEMORY_RESERVE_MB, JOBS_MEMORY_MB; 0 turns
    the one off)."""
    lim, use = limit(), used()
    if lim is None or use is None:
        return {"limit": lim, "used": use, "free": None, "reserve": None, "ceiling": None}
    reserve = config.MEMORY_RESERVE_MB * MB if config.MEMORY_RESERVE_MB >= 0 else max(RESERVE_MIN, int(lim * RESERVE_SHARE))
    ceiling = config.JOBS_MEMORY_MB * MB if config.JOBS_MEMORY_MB >= 0 else int(lim * CEILING_SHARE)
    return {"limit": lim, "used": use, "free": max(0, lim - use), "reserve": min(reserve, lim // 2) or None, "ceiling": ceiling or None}

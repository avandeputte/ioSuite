"""Housekeeping an app does on its own while it runs: purging what was deleted long ago, sending the morning's
reminders, fetching what another service holds, pruning a cache.

    purge = chores.start(model.purge_deleted, name="purge of old deletion markers", app=config.APP)
    ...
    purge.cancel()                                      # in the app's shutdown

This is the front door of the copy's one job runner (iosuite_shared.jobs): the copy runs every app's jobs from one
loop, and each run is written to the Shared ioSuite database, so Settings › Servers › Jobs shows what ran, when, how
long it took and what failed, for every app and every copy of the suite. `heavy=True` keeps a job from running while
another heavy job of the copy is running.
"""
from iosuite_shared import jobs


def start(fn, every_s: float = 86400, name: str = None, first_s: float = 5, app: str = "", heavy: bool = False,
          title: str = "") -> jobs.Job:
    """Run `fn` (blocking: it gets a thread) `first_s` seconds after the app started (after the start-up work, not in
    its way) and then every `every_s` seconds for as long as the app runs. A run that fails is logged and shown on
    Settings › Servers › Jobs, and the next one still happens. A run that is still going when the next falls due is
    not started twice. `app` is the app the job belongs to, for the screen. Call it in the app's lifespan and cancel
    what it returns at shutdown."""
    return jobs.register(fn, every_s=every_s, name=name, first_s=first_s, app=app, heavy=heavy, title=title)

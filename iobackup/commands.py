"""ioBackup's own commands from a shell, beside the migrate and check every app has (iosuite_shared.appcli):

    iosuite iobackup jobs         the jobs, with their schedule and next run
    iosuite iobackup run JOB      back up now (the job's name or number), without the web app; prints the log
    iosuite iobackup runs         the last runs
"""
from iosuite_shared.errors import Invalid


def add(sub) -> None:
    sub.add_parser("jobs", help="the jobs, with their schedule and next run").set_defaults(run=_jobs)
    p = sub.add_parser("run", help="back up now, here, without the web app (prints the log)")
    p.add_argument("job", help="the job's name or number")
    p.set_defaults(run=_run)
    sub.add_parser("runs", help="the last runs").set_defaults(run=_runs)


def _jobs(_a) -> None:
    from iobackup import model, schedule, tasks
    for j in model.jobs():
        n = schedule.next_after(j["cron"]) if j["enabled"] else None
        print(f"{j['id']:4}  {j['name']:24} {j['cron'] or 'on demand':16} next: {tasks.iso(n) or '-'}")


def _run(a) -> int:
    from iobackup import model, tasks
    j = next((x for x in model.jobs() if x["name"] == a.job or str(x["id"]) == a.job), None)
    if not j:
        raise Invalid(f"no job {a.job!r}")
    rid = tasks.enqueue("backup", "Backup: %s" % j["name"], {"job_id": j["id"]}, job_id=j["id"], by="cli")
    tasks.execute(rid)
    r = tasks.run(rid)
    print("\n".join(r["log"]))
    return 0 if r["status"] == "ok" else 1


def _runs(_a) -> None:
    from iobackup import tasks
    for r in tasks.runs(30):
        print(f"{r['id']:5}  {r['status']:9} {r['queued']}  {r['title']}")

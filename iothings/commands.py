"""ioThings' own commands from a shell, beside the migrate and check every app has (iosuite_shared.appcli):

    iosuite iothings import-homebox FILE [NAME]      the things in a Homebox CSV export, added as NAME
"""
from pathlib import Path

from iosuite_shared.errors import Invalid


def add(sub) -> None:
    p = sub.add_parser("import-homebox", help="the things in a Homebox CSV export")
    p.add_argument("file")
    p.add_argument("name", nargs="?", default=None, help="the account they are added as (default: the first admin)")
    p.set_defaults(run=_homebox)


def _homebox(a) -> None:
    from iothings import homebox, users
    u = users.find(a.name) if a.name else next((x for x in users.all_users() if x["role"] == "admin"), None)
    if not u:
        raise Invalid("no such account (or no admin to add them as)")
    r = homebox.keep(u, homebox.read(Path(a.file).read_bytes()))
    print(f"ok: {r['added']} added, {r['changed']} changed, {len(r['skipped'])} skipped, "
          f"{r['locations']} new places, {r['labels']} new labels")
    for s in r["skipped"]:
        print("  " + s)

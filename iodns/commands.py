"""ioDNS's own commands from a shell, beside the migrate and check every app has (iosuite_shared.appcli):

    iosuite iodns compare VIEW            what each server has against what is kept here
    iosuite iodns push VIEW [--prune]     write the view to its servers
    iosuite iodns import SERVER [MODE]    read a server's zone in (merge or replace)
    iosuite iodns ddns [--push]           the addresses that move (dynamic DNS)
    iosuite iodns export                  everything kept here, as JSON
"""
import json


def add(sub) -> None:
    p = sub.add_parser("compare", help="what each server has against what is kept here")
    p.add_argument("view")
    p.set_defaults(run=_compare)
    p = sub.add_parser("push", help="write the view to its servers")
    p.add_argument("view")
    p.add_argument("--prune", action="store_true", help="also remove what is on the server but not here")
    p.set_defaults(run=_push)
    p = sub.add_parser("import", help="read a server's zone in")
    p.add_argument("server", type=int)
    p.add_argument("mode", nargs="?", default="merge", choices=("merge", "replace"))
    p.set_defaults(run=_import)
    p = sub.add_parser("ddns", help="the addresses that move (dynamic DNS)")
    p.add_argument("--push", action="store_true", help="write the new address to the servers")
    p.set_defaults(run=_ddns)
    sub.add_parser("export", help="everything kept here, as JSON").set_defaults(run=_export)


def _compare(a) -> None:
    from iodns import sync
    st = sync.status(a.view, by="cli")
    for s in st["servers"]:
        print(f"{s['name']:24} {'ok' if s['ok'] else 'unreachable':12} {s['count']:5} records  "
              f"{s['differences'] if s['ok'] else s['error']} differences")
    for r in st["rows"]:
        if r["state"] != "ok":
            print(f"  {r['state']:10} {r['name']}")


def _push(a) -> None:
    from iodns import sync
    print(json.dumps(sync.push_all(a.view, "cli", prune=a.prune), indent=2))


def _import(a) -> None:
    from iodns import sync
    print(json.dumps(sync.import_from(a.server, a.mode, "cli"), indent=2))


def _ddns(a) -> None:
    from iodns import ddns
    print(json.dumps(ddns.run("cli", a.push), indent=2, default=str))


def _export(_a) -> None:
    from iodns import model
    print(json.dumps(model.export(), indent=2))

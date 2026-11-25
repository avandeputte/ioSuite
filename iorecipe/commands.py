"""ioRecipe's own commands from a shell, beside the migrate and check every app has (iosuite_shared.appcli):

    iosuite iorecipe import URL [--private NAME]      a recipe from a web page, shared or as that person's own
"""
from iosuite_shared.errors import Invalid


def add(sub) -> None:
    p = sub.add_parser("import", help="a recipe from a web page")
    p.add_argument("url")
    p.add_argument("--private", default=None, metavar="NAME", help="as that account's own recipe (default: shared with the family)")
    p.set_defaults(run=_import)


def _import(a) -> None:
    from iorecipe import api, users
    u = users.find(a.private) if a.private else next((x for x in users.all_users() if x["role"] == "admin"), None)
    if not u:
        raise Invalid("no such account (or no admin to add it as)")
    r = api.import_from(u, a.url, family=not a.private)
    print(f"ok: {r['title']} ({len(r['ingredients'])} ingredients, {len(r['steps'])} steps)")

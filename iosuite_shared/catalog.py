"""The suite's apps as they come: one manifest per app (<app>/app.json, in the app's package).

Every app's folder in the repository holds its app.json: its key, its name, its folder on an address the suite
shares, what it serves at the sync door, its colour, how the suite installer sets it up, its settings, the kinds of
items it has (what the linked-items panel and the start page's search box find in it) and the notifications it sends.
Nothing else in the suite keeps a list of the apps: the folders (suite.FOLDERS), the installer, the settings screen
(config.declared), the notifications (push.KINDS), the linked items (related.KINDS) and the Docker Compose builder are
all read from here.

Every install carries every app's package (the program folder is one checkout), whichever of them it runs, so an
app run alone still knows the others' folders, for when they run beside it or on another server. An app
that runs nowhere is simply not in the suite's list of apps (suite.visible): nothing here makes it show.

A new app: its package folder and its app.json (copy one). The manifest's fields:

  key, name, description   the folder and the app's key (iocalendar), its name (ioCalendar), a word or two for the
                           suite's list of apps ("Calendar"); tag: one line for the website
  color                    its colour (#963522)
  folder                   its folder on an address the suite shares (/calendar/; none for the start page)
  sync                     the path prefixes it serves at the sync door (iosuite_shared.doors): ["/dav", "/ics/"]
  devices                  the calls of its API (/api/) the sync door serves as well: the ones its native apps make,
                           each named with its methods, * for one part of the path
                           (["GET /api/sync", "GET,PUT /api/notes/*/image"]). Nothing else of /api/ is served there.
  homeOnly                 of its sync prefixes, the ones the port for devices does not serve (the pages' port only):
                           links whose secret in the address is their only sign-in, lookups a profile never needs
                           (["/.well-known/", "/ics/"])
  media                    the path prefixes it serves at both doors, read only: what its pages and a native app both
                           show (ioPix: ["/thumb/", "/preview/"])
  order                    where it comes in lists (the website, the builder, the installer)
  adminTool                for suite admins only (ioDNS, ioBackup)
  heavy                    installed last (ioPix: a large image, the AI models)
  aside, otherPorts        what the installer's lists add after its name ("the start page"), and the ports it opens beside the copy's doors ("LDAP 3890")
  compose                  the Docker Compose builder: name (its sub-domain by default), what (one word)
  extras, system           what it needs beyond the suite's own packages: optional sets of Python packages
                           (pyproject.toml's extras: "ai"), and system packages (apt names: tesseract-ocr)
  apart                    the installer offers to run it as a copy of its own (ioPix: long scans, large models)
  ask                      [{name, question, also}]: settings of its own the installer asks for when the app is first
                           added to a suite (ioPix: the photos folder); an answer is stored, with the settings in
                           `also` beside it; no answer leaves the default
  settings                 [{name, label, hint, type, default, choices}]: its own settings, kept in the Shared ioSuite
                           database (iosuite_shared.config.declared), for Settings › Apps › All settings and `iosuite set`
  items                    [{kind, label, plural, href, id}]: the kinds of items it has; href opens one in the app
                           ("#/event/{id}"); id "uuid" for UUIDs (default: a number)
  notifications            [{kind, label, hint, admin}]: what Account › Notifications offers from it
  access                   who gets in, where it differs from the suite's usual (iosuite_shared.app): defaultRole (the
                           role an account holds while nobody gave it one: "none" for an app that is not for everyone),
                           writeRole (what `canWrite` stands for: "member" where everything is one's own), proxyExempt
                           (path prefixes that sign in themselves, whatever a reverse proxy let through: ["/mcp", "/dav"]),
                           davScope (what a sync-only app password opens: ["/dav", "/.well-known/caldav"])
  mcp                      one line on what an AI assistant may do in it (its MCP switch under Settings › Apps)
  limits, bodies           how large a request body may be: limits {name: MiB, or {setting, default} for a size
                           that is one of its settings}, always with `json` (any body no rule names); bodies
                           [{path, type, limit}]: the first whose path and content type fit (shell patterns, either
                           may be left out) names the limit. The app's config has them as MAX_<NAME>_BYTES
  start                    the start page: rank (where its tile comes; none: after those that have one, by name),
                           tile (it answers /api/suite/tile), find {head, rank} (it answers /api/suite/search: the
                           search box's section for it), searchUrl (its own search, "#/search/{q}": the "Search in" row)
                           See iosuite_shared.suiteitems for the endpoints; an app with items answers
                           /api/suite/items/{kind}/{id} for them.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the program folder: every app's package beside this one
MANIFEST = "app.json"
KEY = re.compile(r"^io[a-z]{2,20}$")
KIND = re.compile(r"^[a-z_]{2,30}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ROLES = ("none", "viewer", "member", "editor", "admin")
# a call the sync door serves: its methods, then its path under /api/ with * for one part ("GET,PUT /api/notes/*/image")
CALL = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)(,(GET|POST|PUT|PATCH|DELETE))* /api(/(\*|[A-Za-z0-9._~-]+))+$")
# of an account (/api/auth/), the sync door serves a native app's own sign-in and what it reads and keeps of its person,
# never what makes or changes an account (a password, a passkey, an app password for something else, a person)
ACCOUNT_CALLS = {"/api/auth/device": {"POST", "DELETE"}, "/api/auth/me": {"GET"}, "/api/auth/settings": {"POST"}}


def validate(apps: list[dict]) -> list[dict]:
    """The manifests, checked and in their order; ValueError on the first that is wrong."""
    seen_folder, seen_kind, seen_note = {}, {}, {}
    for m in apps:
        k = m.get("key")
        if not isinstance(k, str) or not KEY.fullmatch(k):
            raise ValueError(f"{MANIFEST}: key {k!r} is not io + a few letters")
        for f in ("name", "description", "color", "order"):
            if m.get(f) in (None, ""):
                raise ValueError(f"{k}/{MANIFEST}: no {f}")
        if not COLOR.fullmatch(str(m["color"])):
            raise ValueError(f"{k}/{MANIFEST}: color {m['color']!r} is not #rrggbb")
        for pre in m.get("sync") or []:
            if not re.fullmatch(r"/[A-Za-z0-9._~/-]{1,60}", str(pre)) or str(pre).startswith(("/api", "/mcp", "/static")):
                raise ValueError(f"{k}/{MANIFEST}: sync {pre!r} is not a path prefix of its own (/dav, /ics/)")
        for pre in m.get("homeOnly") or []:
            if not any(str(pre).startswith(str(s)) for s in m.get("sync") or []):
                raise ValueError(f"{k}/{MANIFEST}: homeOnly {pre!r} is not below one of its sync prefixes")
        for call in m.get("devices") or []:
            if not isinstance(call, str) or not CALL.fullmatch(call):
                raise ValueError(f"{k}/{MANIFEST}: devices {call!r} is not methods and a path of its API (\"GET,PUT /api/notes/*/image\")")
            methods, path = call.split(" ")
            if path.startswith("/api/auth/") and not set(methods.split(",")) <= ACCOUNT_CALLS.get(path, set()):
                raise ValueError(f"{k}/{MANIFEST}: devices {call!r}: of an account, the port for devices serves a native app's "
                                 f"sign-in and its person's own settings, nothing that changes an account")
        for pre in m.get("media") or []:  # served at both doors
            if (not re.fullmatch(r"/[A-Za-z0-9._~/-]{1,60}", str(pre)) or str(pre).startswith(("/api", "/mcp", "/static"))
                    or any(str(pre).startswith(str(s).rstrip("/")) or str(s).startswith(str(pre).rstrip("/")) for s in m.get("sync") or [])):
                raise ValueError(f"{k}/{MANIFEST}: media {pre!r} is not a path prefix of its own, apart from its sync prefixes (/thumb/)")
        for pre in m.get("pages") or []:  # under a sync prefix, yet a page a signed-in person opens: served with the pages
            if not re.fullmatch(r"/[A-Za-z0-9._~/-]{1,80}", str(pre)) or not any(str(pre).startswith(s) for s in m.get("sync") or []):
                raise ValueError(f"{k}/{MANIFEST}: pages {pre!r} is not below one of its sync prefixes")
        f = m.get("folder")
        if f is not None:
            if not re.fullmatch(r"[a-z0-9-]{2,30}", str(f)):
                raise ValueError(f"{k}/{MANIFEST}: folder {f!r}")
            if f in seen_folder:
                raise ValueError(f"{k}/{MANIFEST}: folder {f} is {seen_folder[f]}'s already")
            seen_folder[f] = k
        for it in m.get("items") or []:
            if not KIND.fullmatch(str(it.get("kind"))) or not it.get("label") or not it.get("plural") or "{id}" not in str(it.get("href")):
                raise ValueError(f"{k}/{MANIFEST}: an item needs kind, label, plural and an href with {{id}}: {it}")
            if it["kind"] in seen_kind:
                raise ValueError(f"{k}/{MANIFEST}: item kind {it['kind']} is {seen_kind[it['kind']]}'s already")
            seen_kind[it["kind"]] = k
        for n in m.get("notifications") or []:
            if not KIND.fullmatch(str(n.get("kind"))) or not n.get("label") or not n.get("hint"):
                raise ValueError(f"{k}/{MANIFEST}: a notification needs kind, label and hint: {n}")
            if n["kind"] in seen_note:
                raise ValueError(f"{k}/{MANIFEST}: notification {n['kind']} is {seen_note[n['kind']]}'s already")
            seen_note[n["kind"]] = k
        st = m.get("start") or {}
        if st.get("searchUrl") and "{q}" not in st["searchUrl"]:
            raise ValueError(f"{k}/{MANIFEST}: start.searchUrl needs {{q}}")
        if st.get("find") and not (st["find"].get("head") and isinstance(st["find"].get("rank"), int)):
            raise ValueError(f"{k}/{MANIFEST}: start.find needs head and rank")
        for d in m.get("settings") or []:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,40}", str(d.get("name"))) or not d.get("label") or d.get("type") not in ("text", "number", "switch", "choice"):
                raise ValueError(f"{k}/{MANIFEST}: a setting needs a NAME, a label and a type (text, number, switch, choice): {d}")
            if d["type"] == "choice" and not d.get("choices"):
                raise ValueError(f"{k}/{MANIFEST}: the choice {d['name']} has no choices")
        names = {d["name"] for d in m.get("settings") or []}
        acc = m.get("access") or {}
        if set(acc) - {"defaultRole", "writeRole", "proxyExempt", "davScope"} or acc.get("defaultRole", "none") not in ROLES \
                or acc.get("writeRole", "member") not in ROLES:
            raise ValueError(f"{k}/{MANIFEST}: access is defaultRole, writeRole (a role), proxyExempt, davScope (path prefixes): {acc}")
        lim = m.get("limits") or {}
        for name, v in lim.items():
            ok = isinstance(v, (int, float)) and v > 0 or (isinstance(v, dict) and v.get("setting") in names and isinstance(v.get("default"), int))
            if not re.fullmatch(r"[a-z]{2,20}", str(name)) or not ok:
                raise ValueError(f"{k}/{MANIFEST}: a limit is a name and its MiB, or {{setting, default}}: {name}: {v}")
        if (lim or m.get("bodies")) and "json" not in lim:
            raise ValueError(f"{k}/{MANIFEST}: limits needs json, the size of any body no rule names")
        for rule in m.get("bodies") or []:
            if rule.get("limit") not in lim or not (rule.get("path") or rule.get("type")) or set(rule) - {"path", "type", "limit"}:
                raise ValueError(f"{k}/{MANIFEST}: a body rule is a path or a type (or both) and one of its limits: {rule}")
        for q in m.get("ask") or []:
            if q.get("name") not in names or not q.get("question") or any(n not in names for n in q.get("also") or {}):
                raise ValueError(f"{k}/{MANIFEST}: ask needs the name of one of its settings and a question: {q}")
    return sorted(apps, key=lambda m: (m["order"], m["key"]))


def gather(root) -> list[dict]:
    """Every <app>/app.json in the repository at root, checked and in order."""
    found = []
    for p in sorted(Path(root).glob(f"io*/{MANIFEST}")):
        m = json.loads(p.read_text(encoding="utf-8"))
        if m.get("key") != p.parent.name:
            raise ValueError(f"{p}: key {m.get('key')!r} is not its folder's name")
        found.append(m)
    return validate(found)


def install_order() -> list[str]:
    """The apps in the order the installer lists and installs them: the heavy ones (ioPix) last."""
    return sorted(APPS, key=lambda k: (bool(APPS[k].get("heavy")), APPS[k]["order"]))


def name_of(app: str) -> str:
    return (APPS.get(app) or {}).get("name") or app


LIST = gather(ROOT)
APPS = {m["key"]: m for m in LIST}                                    # key -> manifest, in order
FOLDERS = {k: m["folder"] for k, m in APPS.items() if m.get("folder")}  # key -> folder on an address the suite shares
# kind of item -> {app, label, plural, href, id}
ITEMS = {it["kind"]: {"app": k, **{f: v for f, v in it.items() if f != "kind"}} for k, m in APPS.items() for it in m.get("items") or []}
NOTIFICATIONS = [{"app": k, **n} for k, m in APPS.items() for n in m.get("notifications") or []]
